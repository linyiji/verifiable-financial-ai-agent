"""Explicit V1 physical HTTP boundary shared by model/planning/data adapters.

Only injected into opted-in execution. The delegate must perform ONE attempt (no
hidden retry); production factory sets retries=0. Each client-level retry/redirect
invokes this boundary again. Response receipt is not a validated task output.
"""

import asyncio
import json
from hashlib import sha256
from uuid import uuid4

import httpx

from src.domain.execution_contract import ContractDenied


class LedgerHTTPTransport(httpx.AsyncBaseTransport):
    def __init__(
        self, *, ledger, token, purpose, route, clock, timeout, transport=None, allowed_origins=()
    ):
        self.ledger = ledger
        self.token = token
        self.purpose = purpose
        self.route = route
        self.clock = clock
        self.timeout = timeout
        self.transport = transport or httpx.AsyncHTTPTransport(retries=0)
        self.allowed_origins = frozenset(allowed_origins)

    async def handle_async_request(self, request):
        # Exact origins are prospective authority, never derived from redirects.
        origin = (request.url.scheme, request.url.host, request.url.port)
        if origin not in self.allowed_origins:
            raise ContractDenied("HTTP_ORIGIN_NOT_AUTHORIZED")
        route = self.route
        try:
            wire = json.loads(request.content) if request.content else {}
        except (ValueError, httpx.RequestNotRead):
            wire = {}
        if isinstance(wire, dict) and "model" in wire:
            # An internal fallback must reserve its actual prospective candidate.
            route = {
                "gpt-5.6-sol": "teamorouter-sol",
                "gpt-5.6-luna": "teamorouter-luna",
                "gpt-5.6-terra": "teamorouter-terra",
                "mimo-v2.5": "mimo-direct",
            }.get(wire["model"])
            if route is None:
                raise ContractDenied("WIRE_MODEL_NOT_AUTHORIZED")
            if route.split("-")[0] != self.route.split("-")[0]:
                raise ContractDenied("CROSS_PROVIDER_REQUIRES_SEPARATE_TRANSPORT")
        call_id = "HTTP-" + str(uuid4())
        call = await self.ledger.reserve(
            self.token, call_id, self.purpose, route, self.clock(), self.timeout
        )
        call = await self.ledger.dispatch(self.token, call_id, self.clock())
        try:
            remaining = min(call["timeout"], call["absolute_deadline"] - self.clock())
            async with asyncio.timeout(max(0, remaining)):
                response = await self.transport.handle_async_request(request)
                body = await response.aread()
        except BaseException:
            # No refund. A timed-out socket may already have delivered the request.
            await self.ledger.mark_unknown(self.token, call_id, self.clock())
            raise
        try:
            await self.ledger.save_result(
                self.token,
                call_id,
                {
                    "kind": "HTTP_RESPONSE_RECEIPT",
                    "http_status": response.status_code,
                    "response_sha256": sha256(body).hexdigest(),
                    "response_bytes": len(body),
                    "task_output_validated": False,
                },
                self.clock(),
            )
            await self.ledger.settle(self.token, call_id, self.clock())
        except BaseException:
            await response.aclose()
            raise
        # Never persist request URL/query, authorization headers or response bodies.
        return response

    async def aclose(self):
        await self.transport.aclose()
