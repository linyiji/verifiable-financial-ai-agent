"""Bounded metadata from HTTPX/httpcore events, never headers/bodies/error text.

Inspection is best-effort: unsupported transports remain UNKNOWN. This module
does not select routes, create clients, change policy, or emit network traffic.
"""

import asyncio
import builtins
import os
import ssl
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import version
from uuid import uuid4
from weakref import WeakKeyDictionary

import h11
import httpcore
import httpx

from src.domain.recovery import SafeTransportEvidence, attempt_failure_facts, retain_attempt_facts

_ACTIVE = 0
_CLIENT_IDS = WeakKeyDictionary()
_POOL_IDS = WeakKeyDictionary()
_PROCESS_NONCE = uuid4().hex
# Exact types only: subclass names/modules and exception messages are untrusted.
_SAFE_TYPES = {
    value: (value.__name__, value.__module__)
    for module in (httpx, httpcore, h11, ssl, builtins, asyncio)
    for name, value in vars(module).items()
    if isinstance(value, type)
    and issubclass(value, BaseException)
    and (
        module not in (builtins, asyncio)
        or name
        in {
            "OSError",
            "ConnectionResetError",
            "ConnectionRefusedError",
            "BrokenPipeError",
            "TimeoutError",
            "RuntimeError",
            "ValueError",
            "CancelledError",
        }
    )
}


def _exception_fields(exc, prefix=""):
    identity = _SAFE_TYPES.get(type(exc))
    if identity is None:
        return {}
    return {prefix + "exception_class": identity[0], prefix + "exception_module": identity[1]}


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
        self.safe_enabled = attempt_failure_facts.get() is not None
        self.evidence = SafeTransportEvidence(
            process_identity=sha256(f"{_PROCESS_NONCE}:{os.getpid()}".encode()).hexdigest()[:32],
            attempt_identity=uuid4().hex,
            client_ownership="ATTEMPT" if owned else "CALLER",
        )
        self.method = None
        self.client = None
        self._observe(self._start, provider, model, route, task_profile)

    def _start(self, provider, model, route, task_profile):
        timing = self.timing
        owned = self.owned
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

    def _legacy_bind(self, client, url):
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
        return {"trace": self.trace} if self.enabled or self.safe_enabled else {}

    async def trace(self, name, info):
        # Separate observers so a broken optional recorder cannot hide durable facts.
        if self.safe_enabled:
            self._observe(self._safe_trace, name, info)
        if self.enabled:
            self._observe(self._trace, name, info)

    def _trace(self, name, info):
        if name == "connection.connect_tcp.complete":
            self.timing.set(connection_established="YES", transport_stage="TCP_CONNECTED")
        elif name in {"connection.start_tls.complete", "proxy.start_tls.complete"}:
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

    def _legacy_complete(self, response):
        if self.enabled:
            self.timing.set(
                http_status=response.status_code,
                http_version=response.http_version,
                response_headers_received="YES",
                response_complete="YES",
                transport_stage="RESPONSE_COMPLETE",
            )

    def _legacy_finish(self, exc):
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

    def telemetry_error(self):
        self.evidence = self.evidence.model_copy(update={"telemetry_error": True})

    def _observe(self, callback, *args):
        try:
            callback(*args)
        except Exception:
            self.telemetry_error()

    def _update(self, **facts):
        self.evidence = SafeTransportEvidence.model_validate(
            {**self.evidence.model_dump(), **facts}
        )

    def bind(self, client, url):
        self.client = client
        if self.safe_enabled:
            self._observe(self._safe_bind, client, url)
        self._observe(self._legacy_bind, client, url)

    def _safe_bind(self, client, url):
        self._update(client_identity=_CLIENT_IDS.setdefault(client, str(uuid4())).replace("-", ""))
        # Inspect exactly the mount HTTPX selected; never resolve or change proxy routing.
        transport = client._transport_for_url(httpx.URL(url))
        pool = getattr(transport, "_pool", None)
        if type(pool) in {httpcore.AsyncHTTPProxy, httpcore.AsyncConnectionPool}:
            self._update(
                pool_identity=_POOL_IDS.setdefault(pool, uuid4().hex),
                proxy_route="PROXY" if type(pool) is httpcore.AsyncHTTPProxy else "DIRECT",
            )

    def _safe_trace(self, name, info):
        if name in {
            "connection.connect_tcp.failed",
            "connection.start_tls.failed",
            "proxy.start_tls.failed",
            "http11.send_request_headers.failed",
            "http2.send_request_headers.failed",
            "http11.send_request_body.failed",
            "http2.send_request_body.failed",
            "http11.receive_response_headers.failed",
            "http2.receive_response_headers.failed",
            "http11.receive_response_body.failed",
            "http2.receive_response_body.failed",
        }:
            if name in {"connection.start_tls.failed", "proxy.start_tls.failed"}:
                self._update(
                    tls_namespace=(
                        "PROXY_START_TLS"
                        if name == "proxy.start_tls.failed"
                        else "CONNECTION_START_TLS"
                    )
                )
            exc = info.get("exception")
            if isinstance(exc, BaseException) and self.evidence.trace_exception_class is None:
                self._capture_exception(exc, traced=True)
        if name in {"http11.send_request_headers.started", "http2.send_request_headers.started"}:
            self.method = getattr(info.get("request"), "method", None)
            if self.method == b"CONNECT":
                self._update(proxy_connect_started=True)
            elif self.method == b"POST":
                self._update(target_headers_started=True)
        elif name in {"http11.send_request_body.started", "http2.send_request_body.started"}:
            if self.method == b"POST":
                self._update(target_body_started=True)
        elif name in {"http11.send_request_body.complete", "http2.send_request_body.complete"}:
            if self.method == b"POST":
                self._update(target_body_completed=True)
        elif name in {
            "http11.receive_response_headers.complete",
            "http2.receive_response_headers.complete",
        }:
            value = info.get("return_value")
            status = None
            if isinstance(value, tuple):
                status = value[1] if len(value) == 4 else value[0] if len(value) == 2 else None
            valid = type(status) is int and 100 <= status <= 599
            if self.method == b"CONNECT":
                self._update(proxy_connect_completed=True)
                if valid:
                    self._update(
                        proxy_connect_status_present=True, proxy_connect_http_status=status
                    )
                # HTTPcore accepts exactly 2xx CONNECT, but tunnel evidence is recorded
                # only at its subsequent proxy TLS event, after the CONNECT exchange.
            elif self.method == b"POST":
                self._update(provider_response_headers_received=True)
                if valid:
                    self._update(provider_http_status_present=True, provider_http_status=status)
        elif name in {
            "connection.start_tls.started",
            "connection.start_tls.complete",
            "proxy.start_tls.started",
            "proxy.start_tls.complete",
        }:
            proxy = name.startswith("proxy.")
            completed = name.endswith(".complete")
            namespace = "PROXY_START_TLS" if proxy else "CONNECTION_START_TLS"
            field = ("proxy" if proxy else "connection") + "_tls_"
            self._update(
                tls_namespace=namespace,
                **{field + ("completed" if completed else "started"): True},
                **{"tls_completed" if completed else "tls_started": True},
            )
            if proxy:
                # proxy.start_tls is emitted only after HTTPcore accepts the tunnel.
                self._update(proxy_tunnel_established=True)

    def complete(self, response):
        if self.safe_enabled:
            self._observe(self._safe_complete, response)
        self._observe(self._legacy_complete, response)

    def _safe_complete(self, response):
        # A response returned by client.post is the target response, even for custom transports.
        self._update(provider_response_headers_received=True)
        if type(response.status_code) is int and 100 <= response.status_code <= 599:
            self._update(
                provider_http_status_present=True, provider_http_status=response.status_code
            )

    def _safe_finish(self, exc):
        if self.client is not None:
            self._update(client_closed=self.client.is_closed)
        if exc is None:
            return
        self._capture_exception(exc)

    def _capture_exception(self, exc, *, traced=False):
        prefix = "trace_" if traced else ""
        fields = _exception_fields(exc, prefix)
        fields.update(_exception_fields(exc.__cause__, prefix + "cause_"))
        fields.update(_exception_fields(exc.__context__, prefix + "context_"))
        # Bounded traversal; retain just one innermost known type and first safe errno.
        current, seen = exc, set()
        for _ in range(6):
            if current is None or id(current) in seen:
                break
            seen.add(id(current))
            if self.evidence.inner_exception_class is None:
                fields.update(_exception_fields(current, "inner_"))
            if type(current) in _SAFE_TYPES:
                code = getattr(current, "errno", None)
                if self.evidence.errno is None and type(code) is int and -(2**31) <= code < 2**31:
                    fields.setdefault("errno", code)
            current = current.__cause__ or current.__context__
        self._update(**fields)

    def finish(self, exc):
        if self.safe_enabled:
            self._observe(self._safe_finish, exc)
        self._observe(self._legacy_finish, exc)
        if self.safe_enabled:
            try:
                retain_attempt_facts(transport_evidence=self.evidence)
            except Exception:
                self.telemetry_error()
