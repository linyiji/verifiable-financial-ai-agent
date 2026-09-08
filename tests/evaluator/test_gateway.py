"""Offline access-boundary acceptance. Generated test tokens never leave tmp_path."""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import PureWindowsPath

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from src.adapters.fmp.models import FMPEndpoint
from src.adapters.llm.provider import LLMMessage
from src.adapters.llm.routes import configured_incremental_provider
from src.agentic.recovery import AdaptiveRecovery
from src.domain.agent_output import StandardResearchAgentStructuredOutput as Output
from src.domain.recovery import Candidate, Capability
from src.evaluator.bundle import decrypt_bundle, encrypt_bundle, secure_prompt
from src.evaluator.client import (
    EvaluatorGatewayFinancialData,
    EvaluatorGatewayLLM,
    GatewaySession,
    activate,
    clear_session,
)
from src.evaluator.contracts import (
    PATHS,
    CredentialPolicy,
    DataOperation,
    EvaluationAuthorizationError,
    gateway_url,
)
from src.evaluator.gateway import OwnerUpstreams, create_gateway
from src.evaluator.launcher import prepare_session, print_readiness
from src.evaluator.store import CredentialStore
from src.infrastructure.config.settings import Settings
from src.infrastructure.database.recovery import MemoryRecoveryEvidenceStore
from src.phase4_product.hashing import canonical_json_sha256 as digest
from tests.unit.agentic.test_adaptive_recovery import context

OUTPUT = dict(
    summary="Offline structured result",
    key_findings=["Observed"],
    risks=[],
    limitations=[],
    requires_follow_up=False,
)
MODELS = {
    "teamorouter-sol": {"provider": "teamorouter", "model": "gpt-5.6-sol"},
    "teamorouter-luna": {"provider": "teamorouter", "model": "gpt-5.6-luna"},
    "mimo-direct": {"provider": "mimo", "model": "mimo-v2.5"},
}


class FakeUpstreams:
    secrets = ("synthetic-upstream-secret",)
    models = MODELS

    def __init__(self):
        self.calls = []
        self.fail = None
        self.leak = False

    async def model(self, op):
        self.calls.append(("model", op.route_id))
        if op.route_id == self.fail:
            return {"provider_failure": "read_timeout"}
        return {
            "output": OUTPUT if not self.leak else {"secret": self.secrets[0]},
            **MODELS[op.route_id],
            "input_tokens": 2,
            "output_tokens": 2,
        }

    async def data(self, op):
        self.calls.append(("data", op.operation))
        return {
            "endpoint": op.operation,
            "status": "AVAILABLE",
            "http_status": 200,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "payload": [{"symbol": "NVDA"}],
            "error_code": None,
        }


def policy(**changes):
    return CredentialPolicy(
        **{
            **dict(
                routes=set(MODELS),
                financial_data_allowed=True,
                expires_at=2_000_000_000,
                max_llm_requests=10,
                max_data_requests=10,
                requests_per_minute=30,
            ),
            **changes,
        }
    )


@pytest.fixture
def rig(tmp_path):
    now = [1_900_000_000]
    store = CredentialStore(tmp_path / "test.gateway.sqlite", clock=lambda: now[0])
    cid, token = store.issue(policy())
    upstream = FakeUpstreams()
    app = create_gateway(store, upstream)

    class Rig(tuple):
        def __repr__(self):
            return "OfflineGatewayRig(credential=REDACTED)"

    return Rig((store, cid, token, upstream, app, now))


def operation(route="mimo-direct"):
    return {
        "route_id": route,
        "messages": [{"role": "user", "content": "Bounded test"}],
        "schema_name": "test",
        "response_schema": Output.model_json_schema(),
    }


async def session_for(rig):
    store, cid, token, upstream, app, now = rig
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1")
    session = GatewaySession("http://127.0.0.1", SecretStr(token), allow_loopback=True, http=http)
    await session.readiness()
    return session, http


@pytest.mark.asyncio
async def test_readiness_no_paid_calls_or_quota(rig):
    store, cid, token, upstream, app, now = rig
    before = store.authorize(token)
    session, http = await session_for(rig)
    try:
        assert session.metadata["gateway_status"] == "CONFIGURED"
        assert store.authorize(token) == before
        assert upstream.calls == []
    finally:
        await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,code",
    [
        ("wrong", "EVALUATION_CREDENTIAL_INVALID"),
        ("expired", "EVALUATION_CREDENTIAL_EXPIRED"),
        ("revoked", "EVALUATION_CREDENTIAL_REVOKED"),
        ("scope", "EVALUATION_ROUTE_NOT_ALLOWED"),
        ("quota", "EVALUATION_BUDGET_EXHAUSTED"),
        ("rate", "EVALUATION_RATE_LIMITED"),
    ],
)
async def test_denials_no_upstream(rig, case, code):
    store, cid, token, upstream, app, now = rig
    if case == "wrong":
        token = "vfa_" + "x" * 43
    if case == "expired":
        now[0] = 2_000_000_001
    if case == "revoked":
        store.revoke(cid)
    if case == "scope":
        cid, token = store.issue(policy(routes={"teamorouter-sol"}))
    if case == "quota":
        cid, token = store.issue(policy(max_llm_requests=0))
    if case == "rate":
        cid, token = store.issue(policy(requests_per_minute=1))
        store.authorize(token, kind="data")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.post(
            "/v1/model", json=operation(), headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 403
        assert response.json()["error"] == code
        if case in {"wrong", "expired", "revoked"}:
            assert (
                await http.get("/v1/session", headers={"Authorization": "Bearer " + token})
            ).status_code == 403
    assert upstream.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"url": "https://arbitrary.invalid"},
        {"model": "arbitrary"},
        {"provider": "other"},
        {"method": "GET"},
        {"path": "/anything"},
        {"headers": {"Authorization": "not allowed"}},
    ],
)
async def test_no_arbitrary_model_authority(rig, extra):
    store, cid, token, upstream, app, now = rig
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.post(
            "/v1/model", json={**operation(), **extra}, headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 422
        assert upstream.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("route", list(MODELS))
async def test_model_routes_keep_identity_and_validate_output(rig, route):
    session, http = await session_for(rig)
    try:
        client = EvaluatorGatewayLLM(session, route)
        result = await client.complete_structured(
            messages=[LLMMessage(role="user", content="test")],
            response_model=Output,
            schema_name="test",
        )
        assert result.actual_model == MODELS[route]["model"]
        assert result.provider == MODELS[route]["provider"]
        assert client.lock_to_model(result.actual_model) is client
        with pytest.raises(EvaluationAuthorizationError):
            client.lock_to_model("arbitrary")
        assert rig[3].calls == [("model", route)]
    finally:
        await http.aclose()


@pytest.mark.parametrize("op", list(PATHS))
def test_data_operations_allow_registered_shapes(op):
    params = {"symbol": "NVDA"}
    if op in {"income", "balance", "cashflow"}:
        params.update(limit=199, period="annual")
    if op == "historical":
        params.update(limit=199, **{"from": "2025-01-01", "to": "2026-02-03"})
    if op == "news":
        params = {"symbols": "NVDA", "limit": 100, "page": 0}
    DataOperation(operation=op, params=params)
    with pytest.raises(ValidationError):
        DataOperation(operation=op, params={**params, "apikey": "not permitted"})


@pytest.mark.asyncio
async def test_data_boundary_envelope_and_quota(rig):
    session, http = await session_for(rig)
    try:
        transport = EvaluatorGatewayFinancialData(session)
        result = await transport.request(
            endpoint=FMPEndpoint.PROFILE, path=PATHS["profile"], params={"symbol": "NVDA"}
        )
        assert result.payload == [{"symbol": "NVDA"}]
        assert rig[0].authorize(rig[2])["data_remaining"] == 9
        with pytest.raises(EvaluationAuthorizationError):
            await transport.request(endpoint=FMPEndpoint.PROFILE, path="https://invalid", params={})
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_secret_not_returned_or_logged(rig, caplog):
    session, http = await session_for(rig)
    caplog.set_level(logging.INFO)
    rig[3].leak = True
    try:
        with pytest.raises(EvaluationAuthorizationError):
            await EvaluatorGatewayLLM(session, "mimo-direct").complete_structured(
                messages=[LLMMessage(role="user", content="test")],
                response_model=Output,
                schema_name="test",
            )
        assert rig[2] not in caplog.text
        assert rig[3].secrets[0] not in caplog.text
        assert rig[2] not in repr(session)
    finally:
        await http.aclose()


def test_atomic_quota_and_verifier_only(rig):
    store, cid, token, *_ = rig
    cid, token = store.issue(policy(max_llm_requests=3))

    def reserve(_):
        try:
            store.authorize(token, kind="llm", route="mimo-direct")
            return True
        except EvaluationAuthorizationError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(12))) == 3
    with store.connection() as db:
        assert token not in str([tuple(row) for row in db.execute("SELECT * FROM credentials")])


@pytest.mark.parametrize(
    "mutation", ["wrong-pass", "ciphertext", "url", "version", "garbage", "oversize"]
)
def test_bundle_rejects_tamper(rig, mutation):
    raw = encrypt_bundle(
        rig[2], "strong offline passphrase", url="https://gateway.example", credential_id=rig[1]
    )
    password = "strong offline passphrase"
    if mutation == "wrong-pass":
        password = "a different passphrase"
    elif mutation == "garbage":
        raw = b"not json"
    elif mutation == "oversize":
        raw = b"x" * 65537
    else:
        obj = json.loads(raw)
        obj[{"ciphertext": "ciphertext", "url": "gateway_url", "version": "version"}[mutation]] = (
            "AAAA"
            if mutation == "ciphertext"
            else "https://changed.example"
            if mutation == "url"
            else 99
        )
        raw = json.dumps(obj).encode()
    with pytest.raises(EvaluationAuthorizationError) as caught:
        decrypt_bundle(raw, password)
    assert rig[2] not in str(caught.value)


@pytest.mark.asyncio
async def test_session_only_unicode_spaces_and_windows_path_contract(rig, tmp_path, capsys):
    raw = encrypt_bundle(
        rig[2],
        "strong offline passphrase",
        url="http://127.0.0.1",
        credential_id=rig[1],
        allow_loopback=True,
    )
    path = tmp_path / "评估 bundle with spaces.vfaeval"
    path.write_bytes(raw)
    before = set(tmp_path.iterdir())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=rig[4])) as http:
        try:
            session = await prepare_session(
                path, "strong offline passphrase", allow_loopback=True, http=http
            )
            print_readiness(session.metadata)
            assert rig[2] not in capsys.readouterr().out
            assert set(tmp_path.iterdir()) == before
            settings = Settings(
                _env_file=None,
                vfa_credential_mode="evaluator",
                teamorouter_api_key=None,
                mimo_api_key=None,
                fmp_api_key=None,
            )
            assert configured_incremental_provider(settings).provider_name == "teamorouter"
        finally:
            clear_session()
    # Pure syntax test only; no claim native Windows toolchain was executed on macOS.
    assert PureWindowsPath("C:/Users/Evaluator/评估 bundle.vfaeval").drive == "C:"


@pytest.mark.asyncio
async def test_existing_recovery_same_task_switches_only_through_gateway(rig):
    rig[3].fail = "mimo-direct"
    session, http = await session_for(rig)
    clients = {r: EvaluatorGatewayLLM(session, r) for r in MODELS}
    routes = {
        r: Candidate(route=r, provider=c.provider_name, model=c.model_name, authority_exists=True)
        for r, c in clients.items()
    }
    store = MemoryRecoveryEvidenceStore()
    certs = {
        (
            "fundamental_analysis",
            "teamorouter-sol",
            "gpt-5.6-sol",
            digest(Output.model_json_schema()),
        ): Capability.VERIFIED
    }
    recovery = AdaptiveRecovery(routes, clients, store, capabilities=certs)
    try:
        result = await recovery.execute(
            context=context(),
            initial_provider=clients["mimo-direct"],
            messages=[LLMMessage(role="user", content="test")],
            response_model=Output,
            schema_name="test",
        )
        assert result.provider == "teamorouter"
        assert rig[3].calls == [("model", "mimo-direct"), ("model", "teamorouter-sol")]
        records = await store.records("RUN-local", "RUN-local:fundamentals")
        assert all(r.scope.run_id == "RUN-local" for r in records)
    finally:
        await http.aclose()


def test_insecure_password_prompt_fails_closed(monkeypatch):
    import getpass
    import warnings

    def unsafe(*args):
        warnings.warn("unsafe terminal", getpass.GetPassWarning, stacklevel=2)
        raise AssertionError("must never read echoed input")

    monkeypatch.setattr(getpass, "getpass", unsafe)
    with pytest.raises(getpass.GetPassWarning):
        secure_prompt("Passphrase")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://u:p@example.com",
        "https://example.com?token=value",
        "https://example.com/other",
        "file:///tmp/file",
    ],
)
def test_gateway_url_rejects_unsafe_authority(url):
    with pytest.raises(EvaluationAuthorizationError):
        gateway_url(url)


@pytest.mark.asyncio
async def test_evaluation_quota_stops_recovery_without_switch(rig):
    session, http = await session_for(rig)
    clients = {r: EvaluatorGatewayLLM(session, r) for r in MODELS}
    routes = {
        r: Candidate(route=r, provider=c.provider_name, model=c.model_name, authority_exists=True)
        for r, c in clients.items()
    }
    records = MemoryRecoveryEvidenceStore()
    recovery = AdaptiveRecovery(routes, clients, records)
    rig[0].revoke(rig[1])
    try:
        with pytest.raises(EvaluationAuthorizationError):
            await recovery.execute(
                context=context(),
                initial_provider=clients["mimo-direct"],
                messages=[LLMMessage(role="user", content="test")],
                response_model=Output,
                schema_name="test",
            )
        assert rig[3].calls == []
        assert [r.kind for r in records.values] == [
            "ATTEMPT_STARTED",
            "ATTEMPT_COMPLETED",
            "TERMINAL",
        ]
        assert records.values[1].outcome == "FAIL"
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_owner_fixed_model_and_data_transport_never_forwards_auth(rig, caplog):
    settings = Settings(
        _env_file=None,
        teamorouter_api_key="synthetic-owner-teamo",
        mimo_api_key="synthetic-owner-mimo",
        fmp_api_key="synthetic-owner-fmp",
    )
    observed = []

    def handler(request):
        observed.append((request.url.host, request.url.path))
        if request.method == "POST":
            obj = json.loads(request.content)
            assert obj["model"] in {m["model"] for m in MODELS.values()}
            assert request.headers["Authorization"].startswith("Bearer synthetic-owner-")
            return httpx.Response(
                200,
                json={
                    "model": obj["model"],
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(OUTPUT),
                                "reasoning_content": "must not forward",
                            }
                        }
                    ],
                },
                headers={"Set-Cookie": "private", "x-upstream-secret": "not forwarded"},
            )
        assert request.url.params["apikey"] == "synthetic-owner-fmp"
        return httpx.Response(200, json=[{"symbol": "NVDA"}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as owner_http:
        owner = OwnerUpstreams(settings, http=owner_http)
        owner.data_transport._http_transport = httpx.MockTransport(handler)
        app = create_gateway(rig[0], owner)
        caplog.set_level(logging.INFO)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            headers = {"Authorization": "Bearer " + rig[2]}
            for route in MODELS:
                result = await http.post("/v1/model", json=operation(route), headers=headers)
                assert result.status_code == 200
                assert result.json()["model"] == MODELS[route]["model"]
                assert "set-cookie" not in result.headers
                assert "must not forward" not in result.text
            result = await http.post(
                "/v1/data",
                json={"operation": "profile", "params": {"symbol": "NVDA"}},
                headers=headers,
            )
            assert result.status_code == 200
        assert "synthetic-owner-" not in caplog.text
        assert rig[2] not in caplog.text
        assert observed[-1] == ("financialmodelingprep.com", "/stable/profile")


@pytest.mark.asyncio
async def test_data_denial_does_not_become_fmp_retry(rig):
    from datetime import date

    from src.adapters.fmp.provider import FMPProvider
    from src.data.provider import ProviderRequest

    session, http = await session_for(rig)
    rig[0].revoke(rig[1])
    provider = FMPProvider(EvaluatorGatewayFinancialData(session))
    try:
        with pytest.raises(EvaluationAuthorizationError):
            await provider.fetch(
                ProviderRequest(symbol="NVDA", dataset="company_profile", as_of=date(2026, 9, 8))
            )
        assert rig[3].calls == []
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_readiness_loopback_real_http_no_provider_or_quota(rig, tmp_path):
    import socket

    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(rig[4], log_level="critical", access_log=False))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.01)
        assert server.started
        raw = encrypt_bundle(
            rig[2],
            "strong offline passphrase",
            url=f"http://127.0.0.1:{port}",
            credential_id=rig[1],
            allow_loopback=True,
        )
        path = tmp_path / "loopback evaluation.vfaeval"
        path.write_bytes(raw)
        before = rig[0].authorize(rig[2])
        session = await prepare_session(path, "strong offline passphrase", allow_loopback=True)
        assert session.metadata["credential_valid"]
        assert rig[0].authorize(rig[2]) == before
        assert rig[3].calls == []
    finally:
        clear_session()
        server.should_exit = True
        await task
        sock.close()


@pytest.mark.parametrize(
    "params",
    [
        {"symbol": "NVDA", "from": "2025-01-01"},
        {"symbol": "NVDA", "limit": 200, "from": "2025-01-01", "to": "2029-01-01"},
        {"symbol": "NVDA", "limit": 0, "from": "2025-01-01", "to": "2026-01-01"},
        {
            "symbol": "https://arbitrary.invalid",
            "limit": 200,
            "from": "2025-01-01",
            "to": "2026-01-01",
        },
    ],
)
def test_historical_request_bounds(params):
    with pytest.raises(ValidationError):
        DataOperation(operation="historical", params=params)


@pytest.mark.asyncio
async def test_revoked_bundle_still_decrypts_but_cannot_activate(rig, tmp_path):
    path = tmp_path / "revoked.vfaeval"
    raw = encrypt_bundle(
        rig[2],
        "strong offline passphrase",
        url="http://127.0.0.1",
        credential_id=rig[1],
        allow_loopback=True,
    )
    path.write_bytes(raw)
    assert (
        decrypt_bundle(raw, "strong offline passphrase", allow_loopback=True)[1].get_secret_value()
        == rig[2]
    )
    rig[0].revoke(rig[1])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=rig[4])) as http:
        with pytest.raises(EvaluationAuthorizationError, match="REVOKED"):
            await prepare_session(path, "strong offline passphrase", allow_loopback=True, http=http)


@pytest.mark.asyncio
async def test_missing_evaluator_session_never_uses_byok(monkeypatch):
    from src.adapters.llm import routes

    clear_session()
    monkeypatch.setattr(routes, "TeamoRouterClient", lambda *a, **k: pytest.fail("direct fallback"))
    with pytest.raises(EvaluationAuthorizationError):
        routes.configured_incremental_provider(
            Settings(_env_file=None, vfa_credential_mode="evaluator")
        )


def test_no_evaluator_credential_setting_or_environment_authority():
    assert not any("token" in name for name in Settings.model_fields)


@pytest.mark.asyncio
async def test_failed_import_clears_previous_authority(rig, tmp_path):
    from src.evaluator.client import active_session

    session, http = await session_for(rig)
    activate(session)
    try:
        with pytest.raises(EvaluationAuthorizationError):
            await prepare_session(tmp_path / "missing.vfaeval", "strong offline passphrase")
        with pytest.raises(EvaluationAuthorizationError):
            active_session()
    finally:
        clear_session()
        await http.aclose()


@pytest.mark.asyncio
async def test_production_recovery_composition_preserves_candidate_order(rig, tmp_path):
    from unittest.mock import AsyncMock, MagicMock

    from src.agentic.recovery_composition import build_adaptive_recovery

    session, http = await session_for(rig)
    activate(session)
    sessions = MagicMock()
    database = AsyncMock()
    database.scalars.return_value = []
    sessions.return_value.__aenter__.return_value = database
    try:
        # Gateway wire order is sorted; supervisor order must not inherit that.
        assert list(session.metadata["routes"])[0] == "mimo-direct"
        recovery = await build_adaptive_recovery(
            Settings(_env_file=None, vfa_credential_mode="evaluator", artifact_root=str(tmp_path)),
            sessions,
        )
        assert list(recovery.clients) == ["teamorouter-sol", "teamorouter-luna", "mimo-direct"]
        assert rig[3].calls == []
    finally:
        clear_session()
        await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["scope", "quota"])
async def test_data_authority_denial_never_dispatches(rig, denial):
    changes = {"financial_data_allowed": False} if denial == "scope" else {"max_data_requests": 0}
    _, token = rig[0].issue(policy(**changes))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=rig[4])) as http:
        response = await http.post(
            "http://127.0.0.1/v1/data",
            headers={"Authorization": "Bearer " + token},
            json={"operation": "profile", "params": {"symbol": "NVDA"}},
        )
    assert response.status_code == 403
    assert rig[3].calls == []


@pytest.mark.asyncio
async def test_zero_quota_readiness_banner_is_restricted(rig, capsys):
    session, http = await session_for(rig)
    try:
        print_readiness({**session.metadata, "llm_remaining": 0})
        output = capsys.readouterr().out
        assert "READY FOR REAL RESEARCH" not in output
        assert "EXHAUSTED QUOTA" in output
    finally:
        await http.aclose()
