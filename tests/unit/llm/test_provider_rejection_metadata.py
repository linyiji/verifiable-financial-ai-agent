"""Offline wire response -> current Recovery receipt; no external provider I/O."""

import json
from hashlib import sha256

import httpx
import pytest
from pydantic import ValidationError

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.provider import LLMMessage
from src.adapters.llm.teamorouter import TeamoRouterClient, _safe_rejection_facts
from src.agentic.recovery import AdaptiveRecovery, RecoveryStopped
from src.domain.recovery import (
    Candidate,
    ProviderRejectionDetail,
    RecoveryBudget,
    SafeFailureEvidence,
)
from src.infrastructure.database.recovery import MemoryRecoveryEvidenceStore
from tests.unit.agentic.test_adaptive_recovery import Output, context
from tests.unit.llm.test_teamorouter import settings

SECRET = "SENSITIVE_SENTINEL prompt messages tool arguments API-key private reasoning"
MODELS = ["gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra"]
CASES = ["structured", "extra", "html", "empty", "429", "500", "header", "malformed"]


def response_for(case, model):
    body = {
        "error": {
            "code": "unsupported_parameter",
            "type": "invalid_request_error",
            "category": "parameter",
            "param": "response_format",
        },
        "request_id": "fixture-correlation-1",
        "model": model,
    }
    headers = {"x-request-id": "fixture-header-1"} if case == "header" else {}
    if case == "extra":
        body["error"].update(message=SECRET, nested={"code": SECRET}, authorization=SECRET)
        body.update(messages=SECRET, cookies=SECRET, tools=SECRET)
    if case in {"html", "empty"}:
        return httpx.Response(400, text=f"<html>{SECRET}</html>" if case == "html" else "")
    if case == "malformed":
        body = {
            "error": {"code": [SECRET], "type": {"text": SECRET}, "param": SECRET},
            "model": SECRET,
            "request_id": {"secret": SECRET},
        }
    if case == "success":
        body = {
            "model": model,
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Offline valid output",
                                "key_findings": ["Fixture"],
                                "risks": [],
                                "limitations": [],
                                "requires_follow_up": False,
                            }
                        )
                    }
                }
            ],
        }
    status = 200 if case == "success" else int(case) if case.isdigit() else 400
    return httpx.Response(status, json=body, headers=headers)


async def exercise_rejection(case, model="gpt-5.6-sol", store=None):
    store = store if store is not None else MemoryRecoveryEvidenceStore()
    calls = []

    def handler(request):
        calls.append(request)
        return response_for(case, model)

    route = "teamorouter-" + model.rsplit("-", 1)[1]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TeamoRouterClient(
            settings().model_copy(update={"primary_model": model, "fallback_model": model}),
            client=http,
            execution_policy=ProviderExecutionPolicyV1(
                max_attempts=1, overall_workload_deadline_seconds=90
            ),
        )
        recovery = AdaptiveRecovery(
            {
                route: Candidate(
                    route=route, provider="teamorouter", model=model, authority_exists=True
                )
            },
            {route: client},
            store,
            budget=RecoveryBudget(max_total_attempts_per_task=1, max_capability_checks=0),
        )
        try:
            await recovery.execute(
                context(),
                client,
                messages=[LLMMessage(role="user", content=SECRET)],
                response_model=Output,
                schema_name="answer",
            )
        except RecoveryStopped:
            assert case != "success"
    rows = await store.records("RUN-local")
    row = next(r for r in rows if r.kind == "ATTEMPT_COMPLETED")
    assert len(calls) == 1
    assert SECRET not in "".join(r.model_dump_json() for r in rows)
    return rows, row, calls


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("case", CASES)
async def test_offline_rejection_matrix(case, model):
    _, row, calls = await exercise_rejection(case, model)
    f = row.safe_failure
    detail = f.provider_rejection
    assert row.requested_model == model and row.provider == "teamorouter"
    assert row.attempt_id and row.latency_ms >= 0 and row.outcome == "FAIL"
    assert f.http_status == (int(case) if case.isdigit() else 400)
    assert f.dispatch_state == "DISPATCHED" and f.dispatch_basis == "HTTP_RESPONSE"
    assert f.safe_code == "HTTP_RESPONSE"
    assert f.retryable == f.provider_retryable == (case in {"429", "500"})
    assert f.normalized_failure_class == (
        "quota_or_rate_limit"
        if case == "429"
        else "retryable_http_failure"
        if case == "500"
        else "request_rejected"
    )
    assert row.failure_class == (
        "RATE_LIMIT"
        if case == "429"
        else "PROVIDER_UNAVAILABLE"
        if case == "500"
        else "NON_RECOVERABLE_RUNTIME_FAILURE"
    )
    assert calls[0].method == "POST"
    assert str(calls[0].url) == "https://router.invalid/v1/chat/completions"
    assert calls[0].headers["authorization"] == "Bearer redaction-sentinel"
    assert json.loads(calls[0].content)["model"] == model
    if case in {"html", "empty", "malformed"}:
        assert detail.provider_error_code is None
        assert detail.rejected_parameter is None
        assert f.resolved_model is None and f.request_id_sha256 is None
        assert detail.provider_rejection_detail_parse_status == (
            "NO_DETAIL" if case == "empty" else "INVALID_SAFE_DETAIL"
        )
        assert detail.provider_rejection_detail_present == (None if case == "html" else False)
    else:
        assert detail.provider_error_code == "unsupported_parameter"
        assert detail.provider_error_type == "invalid_request_error"
        assert detail.provider_error_category == "parameter"
        assert detail.rejected_parameter == "response_format"
        assert detail.provider_rejection_detail_present is True
        assert detail.provider_rejection_detail_parse_status == "PARSED"
        assert f.resolved_model == model
        value = "fixture-header-1" if case == "header" else "fixture-correlation-1"
        assert f.request_id_sha256 == "sha256:" + sha256(value.encode()).hexdigest()
        assert value not in row.model_dump_json()


@pytest.mark.parametrize("model", MODELS)
async def test_success_path_has_no_rejection_receipt(model):
    _, row, _ = await exercise_rejection("success", model)
    assert row.outcome == "PASS" and row.safe_failure is None


@pytest.mark.parametrize(
    "value",
    [SECRET, "sk-live-secret", "a" * 100000, ["model"], {"code": "invalid_parameter"}, 1, True],
)
@pytest.mark.parametrize(
    "field,key",
    [
        ("provider_error_code", "code"),
        ("provider_error_type", "type"),
        ("provider_error_category", "category"),
        ("rejected_parameter", "param"),
    ],
)
def test_values_are_closed_at_extraction_and_receipt_boundary(field, key, value):
    facts = _safe_rejection_facts(httpx.Response(400, json={"error": {key: value}}))
    detail = facts["provider_rejection"]
    assert detail[field] is None
    assert detail["provider_rejection_detail_parse_status"] == "INVALID_SAFE_DETAIL"
    with pytest.raises(ValidationError):
        ProviderRejectionDetail(**{field: value})


@pytest.mark.parametrize(
    "raw",
    [b"null", b"[]", b'"text"', b"{", b"\xff", b"[" * 2000, b" " * 20000, b'{"error":"oops"}'],
)
def test_malformed_encoding_depth_schema_and_size_are_bounded(raw):
    facts = _safe_rejection_facts(httpx.Response(400, content=raw))
    assert (
        facts["provider_rejection"]["provider_rejection_detail_parse_status"]
        == "INVALID_SAFE_DETAIL"
    )
    assert SafeFailureEvidence(**facts).provider_rejection.provider_error_code is None


async def test_unexpected_parser_exception_does_not_replace_http_failure(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(httpx.Response, "json", broken)
    _, row, _ = await exercise_rejection("structured")
    assert row.safe_failure.normalized_failure_class == "request_rejected"
    assert row.safe_failure.retryable is False
    assert (
        row.safe_failure.provider_rejection.provider_rejection_detail_parse_status
        == "INVALID_SAFE_DETAIL"
    )


def test_missing_and_partial_details_are_explicit():
    old = SafeFailureEvidence.model_validate({"http_status": 400})
    assert old.provider_rejection.provider_rejection_detail_present is None
    assert old.provider_rejection.provider_rejection_detail_parse_status == "UNKNOWN"
    for body in ({}, {"error": {}}, {"error": None}, {"error": {"code": None}}):
        d = _safe_rejection_facts(httpx.Response(400, json=body))["provider_rejection"]
        assert d["provider_rejection_detail_parse_status"] == "NO_DETAIL"
        assert d["provider_rejection_detail_present"] is False
    facts = _safe_rejection_facts(
        httpx.Response(
            400,
            json={
                "error": {"code": "invalid_model", "param": SECRET},
                "model": SECRET,
            },
        )
    )
    d = facts["provider_rejection"]
    assert d["provider_error_code"] == "invalid_model" and d["rejected_parameter"] is None
    assert d["provider_rejection_detail_present"] is True
    assert d["provider_rejection_detail_parse_status"] == "INVALID_SAFE_DETAIL"


@pytest.mark.parametrize("case", CASES + ["success", "401", "403", "408", "502", "302"])
async def test_observation_preserves_wire_bytes_classification_and_recovery(case, monkeypatch):
    import src.adapters.llm.teamorouter as adapter

    observed, _, observed_calls = await exercise_rejection(case)
    # Pre-change path: status handling without the new observational extraction.
    monkeypatch.setattr(adapter, "_safe_rejection_facts", lambda response: {})
    plain, _, plain_calls = await exercise_rejection(case)
    assert [(r.method, r.url, r.content, dict(r.headers)) for r in observed_calls] == [
        (r.method, r.url, r.content, dict(r.headers)) for r in plain_calls
    ]

    def semantics(rows):
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
                r.safe_failure.normalized_failure_class if r.safe_failure else None,
                r.safe_failure.retryable if r.safe_failure else None,
                r.safe_failure.provider_retryable if r.safe_failure else None,
            )
            for r in rows
        ]

    assert semantics(observed) == semantics(plain)


async def test_rejection_metadata_is_not_inherited_by_later_wire_attempt():
    from src.adapters.llm.provider import LLMProviderUnavailableError
    from src.domain.recovery import attempt_failure_facts

    replies = [response_for("structured", "gpt-5.6-sol"), httpx.Response(500, text="")]
    replies[0].status_code = 429
    facts = {}
    token = attempt_failure_facts.set(facts)
    try:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: replies.pop(0))
        ) as http:
            client = TeamoRouterClient(settings(), client=http)
            with pytest.raises(LLMProviderUnavailableError):
                await client.complete_structured(
                    messages=[LLMMessage(role="user", content=SECRET)],
                    response_model=Output,
                    schema_name="answer",
                )
        safe = SafeFailureEvidence(**facts)
        assert safe.http_status == 500 and safe.resolved_model is None
        assert safe.request_id_sha256 is None
        assert safe.provider_rejection.provider_error_code is None
        assert safe.provider_rejection.provider_rejection_detail_parse_status == "NO_DETAIL"
    finally:
        attempt_failure_facts.reset(token)


def test_only_digest_of_untrusted_request_identifier_can_escape():
    facts = _safe_rejection_facts(httpx.Response(400, json={"request_id": SECRET}))
    assert facts["request_id_sha256"] == "sha256:" + sha256(SECRET.encode()).hexdigest()
    assert SECRET not in json.dumps(facts)
    for value in ("x" * 257, "é", [], {}, 42):
        facts = _safe_rejection_facts(httpx.Response(400, json={"request_id": value}))
        assert "request_id_sha256" not in facts
