"""Current producer -> recovery -> receipt, with local transport facts only."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.provider import LLMMessage
from src.adapters.llm.teamorouter import TeamoRouterClient
from src.agentic.recovery import RecoveryStopped
from src.agentic.recovery_policy import classify
from src.domain.recovery import RecoveryBudget, attempt_failure_facts
from tests.unit.agentic.test_adaptive_recovery import Output, context, setup
from tests.unit.llm.test_teamorouter import settings

SECRET = "SENTINEL_SECRET prompt Authorization cookie private-reasoning response-body"
CASES = [
    "read_timeout",
    "untraced_timeout",
    "preflight",
    "401",
    "400",
    "429",
    "503",
    "invalid_response",
    "schema",
    "unknown",
    "connect_timeout",
    "proxy_timeout",
    "http11_headers_timeout",
    "http2_headers_timeout",
    "unknown_untraced",
]


async def exercise(case, store=None, fallback=False, evidence=True):
    seen = []
    captured = []

    async def handle(request):
        seen.append(request)

        async def no_trace(name, info):
            pass

        trace = request.extensions.get("trace", no_trace)
        if case not in {"untraced_timeout", "connect_timeout", "unknown_untraced"}:
            await trace(
                "http11.send_request_headers.started",
                {
                    "request": SimpleNamespace(
                        method=b"CONNECT" if case == "proxy_timeout" else b"POST"
                    )
                },
            )
            await trace("http11.send_request_body.complete", {})
        if case in {"http11_headers_timeout", "http2_headers_timeout"}:
            protocol = case.split("_")[0]
            await trace(
                f"{protocol}.send_request_headers.started",
                {"request": SimpleNamespace(method=b"POST")},
            )
            value = (
                (b"HTTP/1.1", 503, b"Unavailable", [(b"x-request-id", SECRET.encode())])
                if protocol == "http11"
                else (503, [(b"x-request-id", SECRET.encode())])
            )
            await trace(f"{protocol}.receive_response_headers.complete", {"return_value": value})
            raise httpx.ReadTimeout(SECRET)
        if case in {"read_timeout", "untraced_timeout", "proxy_timeout"}:
            raise httpx.ReadTimeout(SECRET)
        if case == "connect_timeout":
            raise httpx.ConnectTimeout(SECRET)
        if case in {"unknown", "unknown_untraced"}:
            raise RuntimeError(SECRET)
        if case in {"invalid_response", "schema"}:
            return httpx.Response(
                200,
                json={
                    "model": "gpt-5.6-luna",
                    "secret": SECRET,
                    "choices": []
                    if case == "invalid_response"
                    else [{"message": {"content": "{}"}}],
                },
                headers={"x-request-id": SECRET},
            )
        return httpx.Response(int(case), text=SECRET, headers={"x-request-id": SECRET})

    recovery, clients, memory = setup(
        budget=None
        if fallback
        else RecoveryBudget(max_total_attempts_per_task=1, max_capability_checks=0)
    )
    if store is not None:
        recovery.store = store
    else:
        store = memory
    model = "gpt-5.6-luna" if fallback else "gpt-5.6-sol"
    route = "teamorouter-luna" if fallback else "teamorouter-sol"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        config = settings().model_copy(update={"primary_model": model, "fallback_model": model})
        adapter = TeamoRouterClient(
            config,
            client=http,
            execution_policy=ProviderExecutionPolicyV1(
                max_attempts=1, per_attempt_deadline_seconds=1, overall_workload_deadline_seconds=1
            ),
        )

        class Capture:
            provider_name = adapter.provider_name
            model_name = adapter.model_name

            async def complete_structured(self, **kwargs):
                # Disable only retention plumbing for a paired semantics comparison.
                token = attempt_failure_facts.set(None) if not evidence else None
                try:
                    return await adapter.complete_structured(**kwargs)
                except Exception as exc:
                    captured.append(
                        (
                            type(exc).__name__,
                            getattr(exc, "failure_classification", None),
                            getattr(exc, "retryable", None),
                            classify(exc),
                        )
                    )
                    raise
                finally:
                    if token is not None:
                        attempt_failure_facts.reset(token)

        recovery.clients[route] = Capture()
        initial = recovery.clients["teamorouter-sol"]
        try:
            await recovery.execute(
                context(),
                initial,
                messages=[] if case == "preflight" else [LLMMessage(role="user", content=SECRET)],
                response_model=Output,
                schema_name="answer",
            )
        except RecoveryStopped:
            pass
    records = await store.records("RUN-local")
    assert attempt_failure_facts.get() is None
    text = "".join(r.model_dump_json() for r in records)
    for forbidden in [SECRET, "Authorization", "redaction-sentinel", "private-reasoning"]:
        assert forbidden not in text
    failures = [r for r in records if r.kind == "ATTEMPT_COMPLETED" and r.outcome == "FAIL"]
    target = next(r for r in failures if r.model == model)
    return records, target, seen, captured


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES)
async def test_current_path_failure_matrix(case):
    records, row, seen, captured = await exercise(case)
    f = row.safe_failure
    assert row.attempt_id and row.scope.run_id == "RUN-local"
    assert row.requested_model == "gpt-5.6-sol" and row.provider == "teamorouter"
    assert row.latency_ms is not None and row.latency_ms >= 0
    assert f.retryable == captured[0][3].recoverable
    assert row.failure_class == captured[0][3].failure_class
    assert f.provider_retryable == captured[0][2]
    if case == "preflight":
        assert not seen and f.dispatch_state == "NOT_DISPATCHED"
        assert f.local_reason == "LOCAL_PREFLIGHT_REJECTED"
        assert f.retryable is False
    elif case in {"untraced_timeout", "connect_timeout", "proxy_timeout", "unknown_untraced"}:
        assert f.dispatch_state == "UNKNOWN" and f.http_status is None
    else:
        assert f.dispatch_state == "DISPATCHED"
    if case == "read_timeout":
        assert f.safe_code == "READ_TIMEOUT" and f.normalized_failure_class == "read_timeout"
        assert f.retryable is True and f.http_status is None
    if case in {"http11_headers_timeout", "http2_headers_timeout"}:
        assert f.http_status == 503 and f.request_id_sha256.startswith("sha256:")
        assert f.safe_code == "READ_TIMEOUT" and f.normalized_failure_class == "read_timeout"
    if case.isdigit():
        assert f.http_status == int(case)
        assert f.retryable == (case in {"429", "503"})
        assert f.request_id_sha256.startswith("sha256:")
    if case in {"unknown", "unknown_untraced"}:
        assert f.safe_code == "UNKNOWN_EXCEPTION" and f.normalized_failure_class == "UNKNOWN"
        assert f.http_status is None and f.provider_retryable is None
    if case in {"invalid_response", "schema"}:
        assert f.resolved_model == "gpt-5.6-luna" and f.http_status == 200
        assert f.retryable is False


@pytest.mark.asyncio
async def test_fallback_identity_and_unknown_are_not_overwritten():
    records, luna, _, _ = await exercise("400", fallback=True)
    sol = next(r for r in records if r.kind == "ATTEMPT_COMPLETED" and r.model == "gpt-5.6-sol")
    assert sol.attempt_id != luna.attempt_id
    assert sol.safe_failure.normalized_failure_class == "read_timeout"
    assert sol.safe_failure.dispatch_state == "UNKNOWN"  # uninstrumented fake provider
    assert sol.safe_failure.http_status is None
    assert luna.safe_failure.http_status == 400
    assert luna.safe_failure.retryable is False
    assert sol.scope == luna.scope
    for row in (sol, luna):
        start = next(
            r for r in records if r.kind == "ATTEMPT_STARTED" and r.attempt_id == row.attempt_id
        )
        for field in (
            "scope",
            "provider",
            "model",
            "requested_model",
            "attempt_number",
            "capability_check",
        ):
            assert getattr(start, field) == getattr(row, field)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES)
async def test_retention_does_not_change_classification_or_decisions(case):
    a, _, calls_a, errors_a = await exercise(case, fallback=case != "preflight")
    b, _, calls_b, errors_b = await exercise(case, fallback=case != "preflight", evidence=False)
    assert errors_a == errors_b and len(calls_a) == len(calls_b)

    def decisions(rows):
        return [
            (
                r.kind,
                r.route,
                r.model,
                r.attempt_number,
                r.outcome,
                r.failure_class,
                r.reason_code,
                r.action,
                r.decision.action if r.decision else None,
            )
            for r in rows
        ]

    assert decisions(a) == decisions(b)


@pytest.mark.asyncio
async def test_concurrent_attempt_context_isolation():
    values = await asyncio.gather(exercise("401"), exercise("read_timeout"), exercise("preflight"))
    assert [v[1].safe_failure.http_status for v in values] == [401, None, None]
    assert [v[1].safe_failure.dispatch_state for v in values] == [
        "DISPATCHED",
        "DISPATCHED",
        "NOT_DISPATCHED",
    ]


def test_historical_receipt_defaults_remain_unknown():
    from src.domain.recovery import SafeFailureEvidence

    f = SafeFailureEvidence()
    assert f.retryable is None and f.http_status is None and f.dispatch_state == "UNKNOWN"
