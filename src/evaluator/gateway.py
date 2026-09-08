"""Owner-operated gateway. Never a generic proxy, no issuance HTTP endpoint."""

import asyncio
import json
import logging
import uuid
from dataclasses import asdict
from time import perf_counter
from types import SimpleNamespace

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.adapters.fmp.models import FMPEndpoint
from src.adapters.fmp.provider import HttpxFMPTransport
from src.adapters.llm.routes import configured_incremental_provider
from src.evaluator.contracts import (
    PATHS,
    ROUTES,
    DataOperation,
    EvaluationAuthorizationError,
    ModelOperation,
)

log = logging.getLogger("vfa.evaluation.audit")


class OwnerUpstreams:
    def __init__(self, settings, *, http=None):
        if settings.vfa_credential_mode != "byok":
            raise ValueError("Gateway requires explicit Owner BYOK authority")
        self.clients = {r: configured_incremental_provider(settings, route_id=r) for r in ROUTES}
        self.models = {
            r: {"provider": c.provider_name, "model": c.model_name} for r, c in self.clients.items()
        }
        self.data_transport = HttpxFMPTransport(settings.fmp)
        self.http = http
        self.secrets = tuple(
            c._settings.api_key.get_secret_value() for c in self.clients.values()
        ) + tuple(k.get_secret_value() for k in settings.fmp.credentials)

    async def model(self, operation):
        client = self.clients[operation.route_id]
        schema = SimpleNamespace(model_json_schema=lambda: operation.response_schema)
        body = client._request_template(
            messages=operation.messages, response_model=schema, schema_name=operation.schema_name
        )
        body.update(model=client.model_name, stream=False)
        body["max_completion_tokens"] = 8192

        # Exactly one fixed-route HTTP attempt; all recovery remains in the product.
        async def invoke(http):
            try:
                response = await http.post(
                    client._completion_url,
                    json=body,
                    headers={
                        "Authorization": "Bearer " + client._settings.api_key.get_secret_value()
                    },
                )
                if response.status_code != 200:
                    code = (
                        "read_timeout"
                        if response.status_code == 408
                        else "quota_or_rate_limit"
                        if response.status_code == 429
                        else "authentication_failure"
                        if response.status_code in {401, 403}
                        else "provider_unavailable"
                        if response.status_code >= 500
                        else "request_rejected"
                    )
                    return {"provider_failure": code}
                if len(response.content) > 8_000_000:
                    return {"provider_failure": "invalid_provider_response"}
                payload = response.json()
                actual = payload.get("model", client.model_name)
                if actual != client.model_name:
                    return {"provider_failure": "invalid_provider_response"}
                # Never forward headers, reasoning_content, tool calls or upstream diagnostics.
                content = payload["choices"][0]["message"]["content"]
                output = json.loads(content) if isinstance(content, str) else content
                if not isinstance(output, dict):
                    return {"provider_failure": "invalid_provider_response"}
                usage = payload.get("usage", {})
                return {
                    "output": output,
                    **self.models[operation.route_id],
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                }
            except httpx.ConnectTimeout:
                return {"provider_failure": "connect_timeout"}
            except httpx.ReadTimeout:
                return {"provider_failure": "read_timeout"}
            except httpx.RemoteProtocolError:
                return {"provider_failure": "remote_protocol_error"}
            except httpx.RequestError:
                return {"provider_failure": "provider_unavailable"}
            except Exception:
                return {"provider_failure": "invalid_provider_response"}

        if self.http is not None:
            return await invoke(self.http)
        async with httpx.AsyncClient(timeout=60, follow_redirects=False, trust_env=False) as http:
            return await invoke(http)

    async def data(self, operation):
        result = await self.data_transport.request(
            endpoint=FMPEndpoint(operation.operation),
            path=PATHS[operation.operation],
            params=operation.params,
        )
        return asdict(result)


def create_gateway(store, upstreams):
    # FMP authenticates through query parameters; transport logs must never persist them.
    logging.getLogger("httpx").disabled = True
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    app.state.upstreams = upstreams

    @app.middleware("http")
    async def bounded_request(request, call_next):
        try:
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 512_000:
                    return JSONResponse({"error": "EVALUATION_REQUEST_INVALID"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        except Exception:
            # Never return exception bodies, authorization headers or raw prompts.
            return JSONResponse({"error": "EVALUATION_AUTHORITY_UNAVAILABLE"}, status_code=503)

    @app.exception_handler(EvaluationAuthorizationError)
    async def authority_error(request, exc):
        log.info("authorization_rejection=%s", exc.code)
        return JSONResponse({"error": exc.code}, status_code=403)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"error": "EVALUATION_REQUEST_INVALID"}, status_code=422)

    def bearer(request):
        value = request.headers.get("authorization", "")
        if not value.startswith("Bearer ") or len(value) > 100:
            raise EvaluationAuthorizationError("EVALUATION_CREDENTIAL_INVALID")
        return value[7:]

    def safe_response(body, token):
        encoded = json.dumps(body, default=str)
        if any(s and s in encoded for s in (*upstreams.secrets, token)):
            raise EvaluationAuthorizationError("EVALUATION_AUTHORITY_UNAVAILABLE")
        return JSONResponse(json.loads(encoded))

    @app.get("/v1/session")
    async def session(request: Request):
        token = bearer(request)
        result = store.authorize(token)
        result["routes"] = {
            r: upstreams.models[r] for r in result["allowed_routes"] if r in upstreams.models
        }
        result["gateway_status"] = "CONFIGURED"
        # No upstream call, paid quota reservation, health/capability claim.
        return safe_response(result, token)

    async def dispatch(request, operation, kind):
        token = bearer(request)
        route = operation.route_id if kind == "llm" else operation.operation
        if kind == "llm" and route not in upstreams.models:
            raise EvaluationAuthorizationError("EVALUATION_ROUTE_NOT_ALLOWED")
        grant = store.authorize(token, kind=kind, route=route)
        correlation = str(uuid.uuid4())
        started = perf_counter()
        # Reservation is never refunded: disconnects/failures cannot evade quota.
        try:
            async with asyncio.timeout(80):
                body = await (
                    upstreams.model(operation) if kind == "llm" else upstreams.data(operation)
                )
            body["gateway_request_id"] = correlation
            body["latency_seconds"] = perf_counter() - started
            response = safe_response(body, token)
        except TimeoutError:
            log.info(
                "request=%s credential=%s kind=%s route=%s outcome=OVERALL_DEADLINE_EXCEEDED",
                correlation,
                grant["credential_id"],
                kind,
                route,
            )
            if kind == "llm":
                return JSONResponse(
                    {
                        "provider_failure": "overall_deadline_exceeded",
                        "gateway_request_id": correlation,
                        "latency_seconds": perf_counter() - started,
                    }
                )
            return JSONResponse({"error": "EVALUATION_AUTHORITY_UNAVAILABLE"}, status_code=503)
        except Exception:
            log.info(
                "request=%s credential=%s kind=%s route=%s outcome=FAILED",
                correlation,
                grant["credential_id"],
                kind,
                route,
            )
            return JSONResponse({"error": "EVALUATION_AUTHORITY_UNAVAILABLE"}, status_code=503)
        log.info(
            "request=%s credential=%s kind=%s route=%s outcome=%s",
            correlation,
            grant["credential_id"],
            kind,
            route,
            "PROVIDER_FAILURE" if "provider_failure" in body else "RETURNED",
        )
        return response

    @app.post("/v1/model")
    async def model(operation: ModelOperation, request: Request):
        return await dispatch(request, operation, "llm")

    @app.post("/v1/data")
    async def data(operation: DataOperation, request: Request):
        return await dispatch(request, operation, "data")

    return app
