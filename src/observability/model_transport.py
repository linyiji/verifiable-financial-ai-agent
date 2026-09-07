"""Bounded metadata from HTTPX/httpcore events, never headers/bodies/error text.

Inspection is best-effort: unsupported transports remain UNKNOWN. This module
does not select routes, create clients, change policy, or emit network traffic.
"""

import os
from datetime import UTC, datetime
from importlib.metadata import version
from uuid import uuid4
from weakref import WeakKeyDictionary

import h11
import httpcore
import httpx

_ACTIVE = 0
_CLIENT_IDS = WeakKeyDictionary()
_VERSIONS = {"httpx_version": version("httpx"), "httpcore_version": version("httpcore")}
EXCEPTION_NAMES = {
    value: f"{module.__name__}.{name}"
    for module in (httpx, httpcore, h11)
    for name, value in vars(module).items()
    if isinstance(value, type)
    and issubclass(value, Exception)
    and name.endswith(("Error", "Timeout"))
}


def now():
    return datetime.now(UTC).isoformat()


class TransportObservation:
    def __init__(self, timing, *, owned, provider, model, route, task_profile=None):
        self.timing = timing
        self.enabled = timing.recorder is not None
        self.owned = owned
        self.method = None
        self.client = None
        if self.enabled:
            global _ACTIVE
            _ACTIVE += 1
            timing.set(
                **_VERSIONS,
                process_id=os.getpid(),
                client_created_at="UNKNOWN",
                request_started_at=now(),
                client_ownership="ATTEMPT" if owned else "CALLER",
                provider=provider,
                attempted_model=model,
                provider_route_id=route,
                effective_provider_route=route or "UNKNOWN",
                task_profile=task_profile,
                concurrent_http_attempts=_ACTIVE,
                effective_proxy_route="UNKNOWN",
                connection_established="UNKNOWN",
                request_sent="UNKNOWN",
                response_headers_received="UNKNOWN",
                response_body_reading="UNKNOWN",
                response_complete="UNKNOWN",
                transport_stage="UNKNOWN",
                client_closed=False,
            )

    def bind(self, client, url):
        self.client = client
        if not self.enabled:
            return
        try:
            self.timing.set(
                trust_env=client.trust_env,
                transport_client_id=_CLIENT_IDS.setdefault(client, str(uuid4())),
                client_created_at=now() if self.owned else "UNKNOWN",
                request_started_at=now(),
            )
            # Read the selected mount, not a second proxy-environment resolution.
            transport = client._transport_for_url(httpx.URL(url))
            pool = getattr(transport, "_pool", None)
            if type(pool) is httpcore.AsyncHTTPProxy:
                proxy = pool._proxy_url
                self.timing.set(
                    effective_proxy_route="PROXY",
                    proxy_host=proxy.host.decode("ascii"),
                    proxy_port=proxy.port,
                )
            elif type(pool) is httpcore.AsyncConnectionPool:
                self.timing.set(effective_proxy_route="DIRECT")
        except Exception:
            pass  # Unsupported custom transports must not alter request behavior.

    @property
    def extensions(self):
        return {"trace": self.trace} if self.enabled else {}

    async def trace(self, name, info):
        try:
            self._trace(name, info)
        except Exception:
            pass  # Diagnostic hooks never fail the provider operation.

    def _trace(self, name, info):
        if name == "connection.connect_tcp.complete":
            self.timing.set(connection_established="YES", transport_stage="TCP_CONNECTED")
        elif name == "connection.start_tls.complete":
            self.timing.set(transport_stage="TLS_ESTABLISHED")
        elif name in {"http11.send_request_headers.started", "http2.send_request_headers.started"}:
            request = info.get("request")
            self.method = getattr(request, "method", None)
        elif name in {"http11.send_request_body.complete", "http2.send_request_body.complete"}:
            if self.method not in {None, b"CONNECT"}:
                self.timing.set(request_sent="YES", transport_stage="REQUEST_SENT")
        elif name in {
            "http11.receive_response_headers.complete",
            "http2.receive_response_headers.complete",
        }:
            # CONNECT headers are proxy metadata, not the provider response.
            if self.method not in {None, b"CONNECT"}:
                value = info.get("return_value")
                if isinstance(value, tuple) and len(value) == 4:
                    protocol, status, _, _headers = value
                    self.timing.set(
                        http_status=status,
                        http_version=protocol.decode("ascii"),
                        response_headers_received="YES",
                        transport_stage="RESPONSE_HEADERS",
                    )
        elif name in {
            "http11.receive_response_body.started",
            "http2.receive_response_body.started",
        }:
            if self.method not in {None, b"CONNECT"}:
                self.timing.set(response_body_reading="YES", transport_stage="RESPONSE_BODY")

    def complete(self, response):
        if self.enabled:
            self.timing.set(
                http_status=response.status_code,
                http_version=response.http_version,
                response_headers_received="YES",
                response_complete="YES",
                transport_stage="RESPONSE_COMPLETE",
            )

    def finish(self, exc):
        if not self.enabled:
            return
        global _ACTIVE
        _ACTIVE -= 1
        self.timing.set(
            attempt_completed_at=now(), client_closed=bool(self.client and self.client.is_closed)
        )
        chain = []
        seen = set()
        current = exc
        while current is not None and id(current) not in seen and len(seen) < 6:
            seen.add(id(current))
            name = EXCEPTION_NAMES.get(type(current))
            if name:
                chain.append(name)
            current = current.__cause__ or current.__context__
        if chain:
            self.timing.set(transport_exception_chain=chain)
        if exc is not None:
            self.timing.set(transport_exception_class=EXCEPTION_NAMES.get(type(exc), "UNKNOWN"))
        code = next(
            (
                code
                for cls, code in (
                    (httpx.ConnectTimeout, "connect_timeout"),
                    (httpx.ReadTimeout, "read_timeout"),
                    (httpx.WriteTimeout, "write_timeout"),
                    (httpx.PoolTimeout, "pool_timeout"),
                    (httpx.RemoteProtocolError, "remote_protocol_error"),
                    (httpx.TransportError, "transport_error"),
                )
                if isinstance(exc, cls)
            ),
            None,
        )
        if code:
            self.timing.set(transport_failure_code=code)
