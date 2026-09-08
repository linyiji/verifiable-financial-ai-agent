"""Evaluator transport boundaries: no direct provider credentials or fallback."""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import httpx
from pydantic import SecretStr

from src.adapters.fmp.models import FMPAccessStatus, FMPEndpoint, FMPResponseEnvelope
from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.provider import (
    LLMFailureClassification,
    LLMProviderUnavailableError,
    LLMRequestError,
    LLMStructuredResponse,
    StructuredOutputError,
)
from src.evaluator.contracts import PATHS, ROUTES, EvaluationAuthorizationError, gateway_url

# Set only by in-process launcher after authenticated readiness. Not an env var.
_session = None


class GatewaySession:
    def __init__(self, url, token: SecretStr, *, allow_loopback=False, http=None):
        self.url = gateway_url(url, allow_loopback=allow_loopback)
        self._token, self.http, self.metadata = token, http, None

    def __repr__(self):
        return "GatewaySession(credential=REDACTED)"

    async def request(self, path, body=None):
        if path not in {"/v1/session", "/v1/model", "/v1/data"}:
            raise EvaluationAuthorizationError("EVALUATION_REQUEST_INVALID")

        async def send(http):
            try:
                response = await http.request(
                    "GET" if body is None else "POST",
                    self.url + path,
                    json=body,
                    headers={"Authorization": "Bearer " + self._token.get_secret_value()},
                )
                if response.status_code != 200:
                    code = response.json().get("error", "")
                    raise EvaluationAuthorizationError(code)
                if len(response.content) > 8_000_000:
                    raise ValueError()
                return response.json()
            except EvaluationAuthorizationError:
                raise
            except Exception:
                # Gateway authority unavailable is not an upstream-model failure.
                raise EvaluationAuthorizationError() from None

        if self.http is not None:
            return await send(self.http)
        async with httpx.AsyncClient(timeout=95, follow_redirects=False, trust_env=False) as http:
            return await send(http)

    async def readiness(self):
        result = await self.request("/v1/session")
        if result.get("credential_valid") is not True or not isinstance(result.get("routes"), dict):
            raise EvaluationAuthorizationError()
        if set(result["routes"]) - ROUTES:
            raise EvaluationAuthorizationError()
        for route, config in result["routes"].items():
            expected = "mimo" if route == "mimo-direct" else "teamorouter"
            if config.get("provider") != expected or not isinstance(config.get("model"), str):
                raise EvaluationAuthorizationError()
        self.metadata = result
        return result


def activate(session):
    global _session
    if session.metadata is None:
        raise EvaluationAuthorizationError()
    _session = session


def clear_session():
    global _session
    _session = None


def active_session():
    if _session is None or _session.metadata is None:
        raise EvaluationAuthorizationError()
    return _session


class EvaluatorGatewayLLM:
    def __init__(self, session, route_id, *, policy=None):
        if route_id not in session.metadata["routes"]:
            raise EvaluationAuthorizationError("EVALUATION_ROUTE_NOT_ALLOWED")
        self.session, self.route_id = session, route_id
        config = session.metadata["routes"][route_id]
        self.provider_name, self._model = config["provider"], config["model"]
        self.route_ids = {self._model: route_id}
        self.task_profile = None
        self._execution_policy = policy or ProviderExecutionPolicyV1(
            max_attempts=1, bounded_backoff_seconds=(), overall_workload_deadline_seconds=90
        )
        # Existing composition redaction introspection; this is NOT an upstream key.
        self._settings = SimpleNamespace(
            api_key=session._token,
            primary_model=self._model,
            fallback_model=self._model,
            provider=self.provider_name,
        )

    def __repr__(self):
        return f"EvaluatorGatewayLLM(route={self.route_id!r})"

    @property
    def model_name(self):
        return self._model

    @property
    def execution_policy(self):
        return self._execution_policy

    def lock_to_model(self, model_name):
        if model_name != self.model_name:
            raise EvaluationAuthorizationError("EVALUATION_ROUTE_NOT_ALLOWED")
        return self

    async def complete_structured(
        self, *, messages, response_model, schema_name, force_fallback=False, workload_type=None
    ):
        if force_fallback:
            raise EvaluationAuthorizationError("EVALUATION_ROUTE_NOT_ALLOWED")
        try:
            async with asyncio.timeout(self.execution_policy.overall_workload_deadline_seconds):
                body = await self.session.request(
                    "/v1/model",
                    {
                        "route_id": self.route_id,
                        "messages": [m.model_dump(mode="json") for m in messages],
                        "response_schema": response_model.model_json_schema(),
                        "schema_name": schema_name,
                    },
                )
        except TimeoutError:
            # Dispatch may still consume quota upstream; no automatic replay.
            raise EvaluationAuthorizationError() from None
        if "provider_failure" in body:
            try:
                code = LLMFailureClassification(body["provider_failure"])
            except ValueError:
                code = LLMFailureClassification.INVALID_PROVIDER_RESPONSE
            recoverable = code in {
                LLMFailureClassification.READ_TIMEOUT,
                LLMFailureClassification.CONNECT_TIMEOUT,
                LLMFailureClassification.REMOTE_PROTOCOL_ERROR,
                LLMFailureClassification.PROVIDER_UNAVAILABLE,
                LLMFailureClassification.QUOTA_OR_RATE_LIMIT,
            }
            error = LLMProviderUnavailableError if recoverable else LLMRequestError
            raise error(
                "Governed upstream operation failed",
                requested_model=self.model_name,
                attempted_models=(self.model_name,),
                failure_classification=code,
                provider=self.provider_name,
                model=self.model_name,
                attempt=1,
            )
        if (body.get("provider"), body.get("model")) != (self.provider_name, self.model_name):
            raise EvaluationAuthorizationError()
        try:
            output = response_model.model_validate(body["output"])
        except Exception:
            raise StructuredOutputError(
                "Gateway output contract invalid",
                failure_classification=LLMFailureClassification.SEMANTIC_SCHEMA_FAILURE,
            ) from None
        return LLMStructuredResponse(
            output=output,
            provider=self.provider_name,
            requested_model=self.model_name,
            actual_model=self.model_name,
            attempted_models=(self.model_name,),
            request_id=body.get("gateway_request_id"),
            input_tokens=body.get("input_tokens"),
            output_tokens=body.get("output_tokens"),
        )


class EvaluatorGatewayFinancialData:
    def __init__(self, session):
        self.session = session

    async def request(self, *, endpoint, path, params):
        if PATHS.get(endpoint.value) != path:
            raise EvaluationAuthorizationError("EVALUATION_REQUEST_INVALID")
        body = await self.session.request(
            "/v1/data", {"operation": endpoint.value, "params": params}
        )
        try:
            if body["endpoint"] != endpoint.value:
                raise ValueError()
            return FMPResponseEnvelope(
                endpoint=FMPEndpoint(body["endpoint"]),
                status=FMPAccessStatus(body["status"]),
                http_status=int(body["http_status"]),
                retrieved_at=datetime.fromisoformat(body["retrieved_at"]),
                payload=body["payload"],
                error_code=body.get("error_code"),
            )
        except Exception:
            raise EvaluationAuthorizationError() from None
