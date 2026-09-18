"""Actual installed HTTPX/httpcore framing and pool code; synthetic network only."""

import asyncio
import errno
import json
import ssl
from contextlib import contextmanager, suppress
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

import httpcore
import httpx
import pytest
from pydantic import BaseModel, ValidationError

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.provider import LLMMessage
from src.adapters.llm.teamorouter import TeamoRouterClient, context_call_observer
from src.domain.recovery import attempt_failure_facts
from src.infrastructure.config.settings import LLMSettings

SECRET = "SENTINEL_SECRET-userinfo-query-prompt-body-header-message"
MODELS = ["gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra"]
REAL_CLIENT = httpx.AsyncClient


class Output(BaseModel):
    ok: bool


class Stream(httpcore.AsyncNetworkStream):
    def __init__(self, backend):
        self.backend = backend
        self.buffer = b""
        self.response = b""
        self.method = None
        self.closed = False

    async def write(self, buffer, timeout=None):  # noqa: ASYNC109 -- HTTPcore interface
        assert not self.closed
        self.buffer += buffer
        if b"\r\n\r\n" not in self.buffer:
            return
        headers, body = self.buffer.split(b"\r\n\r\n", 1)
        self.method = headers.split(b" ", 1)[0]
        if self.method == b"POST" and self.backend.failure == "write_error":
            raise httpcore.WriteError(SECRET)
        length = next(
            (
                int(h.split(b":", 1)[1])
                for h in headers.split(b"\r\n")
                if h.lower().startswith(b"content-length:")
            ),
            0,
        )
        if len(body) < length:
            return
        if self.method == b"CONNECT":
            self.backend.connects += 1
            status = 407 if self.backend.failure == "proxy_denied" else 200
            self.response = f"HTTP/1.1 {status} {SECRET}\r\n\r\n".encode()
        else:
            self.backend.posts += 1
            request = json.loads(body)
            self.backend.wire.append(
                {
                    "body_hash": sha256(body).hexdigest(),
                    "model": request["model"],
                    "timeout": timeout,
                }
            )
            status = 400 if self.backend.failure == "400" else 200
            payload = json.dumps(
                {
                    "model": request["model"],
                    "choices": [{"message": {"content": '{"ok":true}'}}],
                    "ignored": SECRET,
                }
            ).encode()
            self.response = (
                f"HTTP/1.1 {status} OK\r\nContent-Length: {len(payload)}\r\n"
                f"X-Sensitive: {SECRET}\r\n\r\n"
            ).encode() + payload
        self.buffer = b""

    async def read(self, max_bytes, timeout=None):  # noqa: ASYNC109 -- HTTPcore interface
        assert not self.closed
        await asyncio.sleep(0)
        if self.method == b"CONNECT" and self.backend.failure == "connect_read":
            raise httpcore.ReadError(SECRET)
        if self.method == b"POST":
            if self.backend.barrier is not None:
                await self.backend.barrier()
            if self.backend.failure in {"read_timeout", "read_error"}:
                cls = (
                    httpcore.ReadTimeout
                    if self.backend.failure == "read_timeout"
                    else httpcore.ReadError
                )
                raise cls(SECRET) from OSError(errno.ECONNRESET, SECRET)
        value, self.response = self.response, b""
        return value

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):  # noqa: ASYNC109
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED and ssl_context.check_hostname
        self.backend.tls += 1
        if self.backend.failure == "tls_error":
            await self.aclose()
            raise httpcore.ConnectError(SECRET) from ssl.SSLError(errno.ECONNRESET, SECRET)
        return self

    async def aclose(self):
        self.closed = True

    def get_extra_info(self, name):
        return False if name == "is_readable" else None


class Backend(httpcore.AsyncNetworkBackend):
    def __init__(self, failure=None, barrier=None):
        self.failure, self.barrier = failure, barrier
        self.streams, self.wire = [], []
        self.connects = self.posts = self.tls = 0

    async def connect_tcp(self, host, port, **kwargs):
        stream = Stream(self)
        self.streams.append(stream)
        return stream


def local_client(mode, backend, **kwargs):
    transport = httpx.AsyncHTTPTransport(
        trust_env=False,
        proxy=f"http://user:{SECRET}@proxy.invalid:8080" if mode == "proxy" else None,
    )
    transport._pool._network_backend = backend
    return REAL_CLIENT(transport=transport, trust_env=False, **kwargs)


def adapter(model=MODELS[0], client=None):
    return TeamoRouterClient(
        LLMSettings(
            provider="teamorouter",
            api_key=SECRET,
            base_url="https://origin.invalid/v1",
            primary_model=model,
            fallback_model=model,
        ),
        client=client,
        execution_policy=ProviderExecutionPolicyV1(
            max_attempts=1, bounded_backoff_seconds=(), overall_workload_deadline_seconds=90
        ),
    )


async def invoke(provider):
    facts = {}
    token = attempt_failure_facts.set(facts)
    try:
        try:
            result = await provider.complete_structured(
                messages=[LLMMessage(role="user", content=SECRET)],
                response_model=Output,
                schema_name="answer",
            )
            outcome = {"ok": result.output.ok}
        except Exception as exc:
            outcome = {
                "class": type(exc).__name__,
                "classification": getattr(exc, "failure_classification", None),
                "retryable": getattr(exc, "retryable", None),
            }
        return facts, outcome
    finally:
        attempt_failure_facts.reset(token)


@contextmanager
def owned_factory(mode, failures=(None,), barrier=None):
    made, backends = [], []
    pending = iter(failures)

    def factory(**kwargs):
        backend = Backend(next(pending, None), barrier)
        client = local_client(mode, backend, **kwargs)
        made.append(client)
        backends.append(backend)
        return client

    with patch("src.adapters.llm.teamorouter.httpx.AsyncClient", factory):
        yield made, backends


def evidence(facts):
    from src.domain.recovery import SafeTransportEvidence

    return SafeTransportEvidence.model_validate(facts["transport_evidence"])


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    "mode,failure",
    [
        (mode, failure)
        for mode in ["direct", "proxy"]
        for failure in [
            None,
            "tls_error",
            "read_timeout",
            "read_error",
            "400",
            "proxy_denied",
            "connect_read",
            "write_error",
        ]
        if mode == "proxy" or failure not in {"proxy_denied", "connect_read"}
    ],
)
async def test_actual_httpcore_stage_matrix(mode, model, failure):
    with owned_factory(mode, [failure]) as (clients, backends):
        facts, outcome = await invoke(adapter(model))
    e = evidence(facts)
    assert clients[0].is_closed and e.client_closed is True
    assert all(s.closed for s in backends[0].streams)
    assert e.client_ownership == "ATTEMPT" and e.pool_identity and e.client_identity
    assert e.proxy_route == mode.upper()
    assert e.process_identity and e.attempt_identity
    assert SECRET not in e.model_dump_json()
    assert (
        "origin.invalid" not in e.model_dump_json() and "proxy.invalid" not in e.model_dump_json()
    )
    if mode == "proxy":
        assert e.proxy_connect_started is True
        if failure != "connect_read":
            assert e.proxy_connect_completed is True
            assert e.proxy_connect_http_status == (407 if failure == "proxy_denied" else 200)
            assert e.proxy_connect_status_present is True
    else:
        assert e.proxy_connect_started is None and e.proxy_connect_completed is None
        assert e.proxy_connect_http_status is None
    if failure not in {"proxy_denied", "connect_read"}:
        assert e.tls_started is True
        assert e.tls_namespace == ("PROXY_START_TLS" if mode == "proxy" else "CONNECTION_START_TLS")
        assert e.proxy_tls_started is (True if mode == "proxy" else None)
        assert e.connection_tls_started is (True if mode == "direct" else None)
        if mode == "proxy":
            assert e.proxy_tunnel_established is True
    if failure in {"tls_error", "proxy_denied", "connect_read"}:
        assert e.target_headers_started is None
        assert e.target_body_completed is None
        assert e.provider_http_status is None and facts["dispatch_state"] == "UNKNOWN"
        assert e.tls_completed is None
    else:
        assert e.tls_completed is True and e.target_headers_started is True
        if failure == "write_error":
            assert e.target_body_completed is None and facts["dispatch_state"] == "UNKNOWN"
        else:
            assert e.target_body_started is True and e.target_body_completed is True
            assert facts["dispatch_state"] == "DISPATCHED"
    if failure in {None, "400"}:
        assert e.provider_response_headers_received is True
        assert e.provider_http_status == (400 if failure == "400" else 200)
        assert e.provider_http_status_present is True
        assert e.exception_class is None
    else:
        assert e.provider_http_status is None
        assert e.provider_response_headers_received is None
        assert e.exception_module == "httpx"
        assert e.cause_exception_module == "httpcore"
        if failure in {"read_timeout", "read_error", "tls_error"}:
            assert e.errno == errno.ECONNRESET
            assert e.inner_exception_module in {"builtins", "ssl"}
            assert e.context_exception_module == "httpcore"
    if failure is None:
        assert outcome == {"ok": True}


@pytest.mark.parametrize("mode", ["direct", "proxy"])
@pytest.mark.parametrize("failure", [None, "read_timeout", "read_error"])
async def test_new_attempt_after_success_or_error(mode, failure):
    with owned_factory(mode, [failure, None]) as (clients, backends):
        provider = adapter()
        a, _ = await invoke(provider)
        b, result = await invoke(provider)
    ea, eb = evidence(a), evidence(b)
    assert result == {"ok": True} and eb.exception_class is None and eb.errno is None
    assert ea.client_identity != eb.client_identity and ea.pool_identity != eb.pool_identity
    assert ea.attempt_identity != eb.attempt_identity
    assert ea.process_identity == eb.process_identity
    assert len(clients) == 2 and all(c.is_closed for c in clients)
    assert all(s.closed for b in backends for s in b.streams)
    assert provider._client is None


@pytest.mark.parametrize("mode", ["direct", "proxy"])
async def test_injected_client_retains_ownership_and_identity(mode):
    backend = Backend("read_timeout")
    client = local_client(mode, backend)
    async with client:
        a, _ = await invoke(adapter(client=client))
        backend.failure = None
        b, result = await invoke(adapter(client=client))
        assert result == {"ok": True} and not client.is_closed
        ea, eb = evidence(a), evidence(b)
        assert ea.client_identity == eb.client_identity and ea.pool_identity == eb.pool_identity
        assert ea.client_closed is False and eb.client_closed is False
        assert ea.client_ownership == eb.client_ownership == "CALLER"
    assert client.is_closed and all(s.closed for s in backend.streams)
    _, closed = await invoke(adapter(client=client))
    assert closed["class"] == "RuntimeError" and backend.posts == 2


async def test_concurrency_barrier_proves_no_serialization_or_cross_close():
    entered = 0
    ready = asyncio.Event()

    async def barrier():
        nonlocal entered
        entered += 1
        if entered == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), 2)
        assert all(not c.is_closed for c in clients)

    with owned_factory("proxy", ["read_timeout", None], barrier) as (clients, _):
        provider = adapter()
        a, b = await asyncio.gather(invoke(provider), invoke(provider))
    ea, eb = evidence(a[0]), evidence(b[0])
    assert ea.exception_class == "ReadTimeout" and eb.exception_class is None
    assert ea.client_identity != eb.client_identity and ea.pool_identity != eb.pool_identity
    assert ea.attempt_identity != eb.attempt_identity
    assert all(c.is_closed for c in clients)
    assert attempt_failure_facts.get() is None


@pytest.mark.parametrize(
    "method",
    [
        "_safe_bind",
        "_safe_trace",
        "_safe_complete",
        "_safe_finish",
        "_legacy_bind",
        "_trace",
        "_legacy_complete",
        "_legacy_finish",
    ],
)
async def test_benign_observer_failure_does_not_fail_success(method, monkeypatch):
    from src.observability.model_transport import TransportObservation
    from src.observability.performance import Recorder, configure

    def broken(*args, **kwargs):
        raise ValueError(SECRET)

    monkeypatch.setattr(TransportObservation, method, broken)
    configure(Recorder())
    try:
        with owned_factory("proxy"):
            facts, result = await invoke(adapter())
        assert result == {"ok": True}
        assert evidence(facts).telemetry_error is True
    finally:
        configure(None)
        # _legacy_finish injection deliberately skips the legacy diagnostic decrement.
        from src.observability import model_transport

        model_transport._ACTIVE = 0


async def test_enforcement_guard_not_swallowed():
    class Guard:
        async def prepare(self, provider, payload):
            pass

        def dispatch(self, provider, payload):
            raise RuntimeError("ENFORCEMENT_DENIED")

    token = context_call_observer.set(Guard())
    try:
        with owned_factory("proxy") as (clients, backends):
            facts, result = await invoke(adapter())
        assert result["class"] == "RuntimeError"
        assert clients[0].is_closed and backends[0].posts == 0
        assert evidence(facts).provider_http_status is None
    finally:
        context_call_observer.reset(token)


async def test_cancellation_still_closes_owned_client():
    entered = asyncio.Event()

    async def barrier():
        entered.set()
        await asyncio.Event().wait()

    with owned_factory("proxy", barrier=barrier) as (clients, _):
        task = asyncio.create_task(invoke(adapter()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert clients[0].is_closed


async def test_unknown_malformed_and_untrusted_data_are_bounded():
    from src.domain.recovery import SafeTransportEvidence
    from src.observability.model_transport import TransportObservation

    facts = {}
    token = attempt_failure_facts.set(facts)
    try:
        o = TransportObservation(
            SimpleNamespace(recorder=None),
            owned=False,
            provider="teamorouter",
            model=MODELS[0],
            route=None,
        )
        await o.trace("unknown." + SECRET, {"headers": {SECRET: SECRET}})
        await o.trace("http11.receive_response_headers.complete", {"return_value": (200, [])})
        await o.trace("http11.send_request_headers.started", None)
        o.finish(type(SECRET, (httpx.ReadError,), {})(SECRET))
        e = evidence(facts)
        assert e.target_headers_started is None and e.provider_http_status is None
        assert e.exception_class is None and e.telemetry_error is True
        assert SECRET not in e.model_dump_json()
        assert len(e.model_dump_json()) < 4096
        assert SafeTransportEvidence().proxy_connect_started is None
        with pytest.raises(ValidationError):
            e.telemetry_error = False
        with pytest.raises(ValidationError):
            SafeTransportEvidence(message=SECRET)
        with pytest.raises(ValidationError):
            SafeTransportEvidence(target_body_started="true")
    finally:
        attempt_failure_facts.reset(token)


async def test_explicit_cause_context_cycles_and_errno_limits():
    from src.observability.model_transport import TransportObservation

    facts = {}
    token = attempt_failure_facts.set(facts)
    try:
        o = TransportObservation(
            SimpleNamespace(recorder=None),
            owned=True,
            provider="teamorouter",
            model=MODELS[0],
            route=None,
        )
        root = httpx.ReadError(SECRET)
        root.__cause__ = OSError(errno.ECONNRESET, SECRET)
        root.__context__ = httpcore.ConnectError(SECRET)
        root.__cause__.__cause__ = root
        o.finish(root)
        e = evidence(facts)
        assert e.cause_exception_module == "builtins" and e.context_exception_module == "httpcore"
        assert e.errno == errno.ECONNRESET
        assert len(e.model_dump_json()) < 4096 and SECRET not in e.model_dump_json()
    finally:
        attempt_failure_facts.reset(token)


async def recovery_fixture(
    failure, model=MODELS[0], store=None, task_profile="fundamental_analysis"
):
    """Invoke only the bounded Recovery owner against a synthetic network, never a Research Run."""
    from src.agentic.recovery import AdaptiveRecovery, RecoveryStopped
    from src.domain.recovery import Candidate, RecoveryBudget
    from src.infrastructure.database.recovery import MemoryRecoveryEvidenceStore
    from tests.unit.agentic.test_adaptive_recovery import context, task

    provider = adapter(model)
    route = "teamorouter-" + model.rsplit("-", 1)[-1]
    store = store or MemoryRecoveryEvidenceStore()
    owner = AdaptiveRecovery(
        {route: Candidate(route=route, provider="teamorouter", model=model, authority_exists=True)},
        {route: provider},
        store,
        budget=RecoveryBudget(max_total_attempts_per_task=1, max_capability_checks=0),
    )
    ctx = context(
        task().model_copy(
            update={
                "task_id": "RUN-local:" + task_profile,
                "task_type": task_profile,
            }
        )
    )
    with owned_factory("proxy", [failure]) as (clients, backends):
        try:
            await owner.execute(
                ctx,
                provider,
                messages=[LLMMessage(role="user", content=SECRET)],
                response_model=Output,
                schema_name="answer",
            )
        except RecoveryStopped:
            pass
    rows = await store.records("RUN-local")
    row = next(
        r for r in rows if r.kind == "ATTEMPT_COMPLETED" and r.scope.task_profile == task_profile
    )
    return rows, row, clients, backends


@pytest.mark.parametrize("failure", [None, "tls_error", "read_timeout", "400"])
@pytest.mark.parametrize("model", MODELS)
async def test_current_recovery_projection(failure, model):
    rows, row, clients, _ = await recovery_fixture(failure, model)
    assert row.transport_evidence.client_closed is True
    assert row.transport_evidence.client_ownership == "ATTEMPT"
    assert row.attempt_id and row.transport_evidence.attempt_identity
    from src.domain.recovery import RecoveryEvidence

    historical = row.model_dump(mode="json", exclude={"transport_evidence"})
    assert RecoveryEvidence.model_validate(historical).transport_evidence is None
    assert "transport_evidence" not in historical
    assert row.outcome == ("PASS" if failure is None else "FAIL")
    assert all(c.is_closed for c in clients)
    assert SECRET not in "".join(r.model_dump_json() for r in rows)
    if failure == "tls_error":
        assert row.safe_failure.safe_code == "TRANSPORT_ERROR"
        assert row.safe_failure.dispatch_state == "UNKNOWN"
        assert row.transport_evidence.trace_cause_exception_module == "ssl"
    if failure == "400":
        assert row.safe_failure.normalized_failure_class == "request_rejected"
        assert row.safe_failure.retryable is False


async def test_risk_valuation_context_isolation():
    # Two owner invocations overlap at their synthetic network read and share one adapter.
    from src.agentic.recovery import AdaptiveRecovery, RecoveryStopped
    from src.domain.recovery import Candidate, RecoveryBudget
    from src.infrastructure.database.recovery import MemoryRecoveryEvidenceStore
    from tests.unit.agentic.test_adaptive_recovery import context, task

    provider = adapter()
    store = MemoryRecoveryEvidenceStore()
    owner = AdaptiveRecovery(
        {
            "teamorouter-sol": Candidate(
                route="teamorouter-sol",
                provider="teamorouter",
                model=MODELS[0],
                authority_exists=True,
            )
        },
        {"teamorouter-sol": provider},
        store,
        budget=RecoveryBudget(max_total_attempts_per_task=1, max_capability_checks=0),
    )
    entered = 0
    ready = asyncio.Event()

    async def barrier():
        nonlocal entered
        entered += 1
        if entered == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), 2)

    async def call(profile):
        ctx = context(
            task().model_copy(update={"task_id": "RUN-local:" + profile, "task_type": profile})
        )
        try:
            await owner.execute(
                ctx,
                provider,
                messages=[LLMMessage(role="user", content=SECRET)],
                response_model=Output,
                schema_name="answer",
            )
        except RecoveryStopped:
            pass

    with owned_factory("proxy", ["read_timeout", None], barrier) as (clients, _):
        await asyncio.gather(call("risk_analysis"), call("valuation_analysis"))
    rows = [r for r in await store.records() if r.kind == "ATTEMPT_COMPLETED"]
    risk = next(r for r in rows if r.scope.task_profile == "risk_analysis")
    valuation = next(r for r in rows if r.scope.task_profile == "valuation_analysis")
    assert risk.transport_evidence.exception_class == "ReadTimeout"
    assert valuation.transport_evidence.exception_class is None
    assert risk.transport_evidence.client_identity != valuation.transport_evidence.client_identity
    assert risk.transport_evidence.pool_identity != valuation.transport_evidence.pool_identity
    assert risk.attempt_id != valuation.attempt_id and all(c.is_closed for c in clients)


async def test_http2_status_and_dual_tls_namespaces():
    from src.observability.model_transport import TransportObservation

    facts = {}
    token = attempt_failure_facts.set(facts)
    try:
        o = TransportObservation(
            SimpleNamespace(recorder=None),
            owned=False,
            provider="teamorouter",
            model=MODELS[0],
            route=None,
        )
        for name in [
            "connection.start_tls.started",
            "connection.start_tls.complete",
            "proxy.start_tls.started",
            "proxy.start_tls.complete",
        ]:
            await o.trace(name, {})
        await o.trace(
            "http2.send_request_headers.started", {"request": SimpleNamespace(method=b"POST")}
        )
        await o.trace("http2.receive_response_headers.complete", {"return_value": (400, [])})
        o.finish(None)
        e = evidence(facts)
        assert e.connection_tls_completed is True and e.proxy_tls_completed is True
        assert e.provider_http_status == 400
        assert e.target_body_completed is None
    finally:
        attempt_failure_facts.reset(token)


async def test_url_userinfo_query_and_headers_never_enter_snapshot():
    from src.observability.model_transport import TransportObservation

    facts = {}
    token = attempt_failure_facts.set(facts)
    try:
        o = TransportObservation(
            SimpleNamespace(recorder=None),
            owned=False,
            provider="teamorouter",
            model=MODELS[0],
            route=None,
        )
        async with local_client("proxy", Backend()) as client:
            o.bind(client, f"https://user:{SECRET}@origin.invalid/v1?token={SECRET}")
            await o.trace(
                "http11.send_request_headers.started",
                {
                    "request": SimpleNamespace(
                        method=b"POST",
                        url=SECRET,
                        headers={"Authorization": SECRET},
                        content=SECRET,
                    )
                },
            )
            await o.trace(
                "http11.receive_response_headers.complete",
                {
                    "return_value": (
                        b"HTTP/1.1",
                        400,
                        SECRET,
                        [(b"Authorization", SECRET.encode())],
                    ),
                },
            )
            o.finish(httpx.ReadError(SECRET))
        serialized = evidence(facts).model_dump_json()
        assert SECRET not in serialized and "origin.invalid" not in serialized
        assert "Authorization" not in serialized
    finally:
        attempt_failure_facts.reset(token)


@pytest.mark.parametrize("trusted", [True, False])
async def test_real_loopback_verified_tls_and_invalid_certificate(tmp_path, trusted):
    import ipaddress
    from datetime import UTC, datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local-test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certificate, private_key = tmp_path / "local.pem", tmp_path / "local.key"
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private_key.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certificate, private_key)
    calls = []
    handlers = set()

    async def handle(reader, writer):
        handlers.add(asyncio.current_task())
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            length = next(
                int(h.split(b":", 1)[1])
                for h in headers.split(b"\r\n")
                if h.lower().startswith(b"content-length:")
            )
            await reader.readexactly(length)
            calls.append(True)
            payload = json.dumps(
                {"model": MODELS[0], "choices": [{"message": {"content": '{"ok":true}'}}]}
            ).encode()
            writer.write(
                f"HTTP/1.1 200 OK\r\nContent-Length: {len(payload)}\r\n\r\n".encode() + payload
            )
            await writer.drain()
        finally:
            writer.close()
            with suppress(ConnectionResetError):
                await writer.wait_closed()
            handlers.discard(asyncio.current_task())

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=server_context)
    port = server.sockets[0].getsockname()[1]
    client_context = ssl.create_default_context(cafile=str(certificate) if trusted else None)
    try:
        async with REAL_CLIENT(verify=client_context, trust_env=False) as client:
            provider = adapter(client=client)
            provider._settings = provider._settings.model_copy(
                update={
                    "base_url": f"https://127.0.0.1:{port}/v1",
                }
            )
            facts, result = await invoke(provider)
        e = evidence(facts)
        assert e.connection_tls_started is True
        if trusted:
            assert result == {"ok": True} and e.connection_tls_completed is True
            assert e.provider_http_status == 200 and len(calls) == 1
        else:
            assert result["classification"] == "provider_unavailable"
            assert e.connection_tls_completed is None and e.provider_http_status is None
            assert e.inner_exception_class == "SSLCertVerificationError"
            assert not calls
    finally:
        server.close()
        await server.wait_closed()
        if handlers:
            await asyncio.gather(*handlers)


@pytest.mark.parametrize("prefix", ["connection", "proxy"])
async def test_tls_failure_namespace_without_guessed_start(prefix):
    from src.observability.model_transport import TransportObservation

    facts = {}
    token = attempt_failure_facts.set(facts)
    try:
        o = TransportObservation(
            SimpleNamespace(recorder=None),
            owned=False,
            provider="teamorouter",
            model=MODELS[0],
            route=None,
        )
        await o.trace(prefix + ".start_tls.failed", {"exception": httpcore.ConnectError(SECRET)})
        o.finish(None)
        e = evidence(facts)
        assert e.tls_namespace == prefix.upper() + "_START_TLS"
        assert e.tls_started is None and e.tls_completed is None
        assert e.trace_exception_class == "ConnectError"
    finally:
        attempt_failure_facts.reset(token)
