"""Shared adapter policy, with no admission, runtime, or paid requests."""

import json

import httpx
import pytest

from src.adapters.llm.teamorouter import TeamoRouterClient
from src.agentic.llm_integration import PlannerProviderSchemeGenerator
from src.agentic.planning_errors import IncrementalSchemeFailure
from src.observability.performance import Recorder, configure
from tests.phase4.backend_product.test_incremental_scheme_repair import (
    real_inputs,
    valid_incremental,
)
from tests.unit.llm.test_agentic_llm_integration import valid_scheme
from tests.unit.llm.test_teamorouter import response, settings


@pytest.mark.parametrize("incremental", [False, True])
async def test_model_backed_scheme_paths_share_timeout_retry_and_fallback(incremental):
    _, obj, goal, context = real_inputs()
    requests = []
    recorder = Recorder(forbidden_values=("redaction-sentinel", "PRIVATE_BODY"))

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("PRIVATE_BODY", request=request)
        proposal = valid_incremental(context) if incremental else valid_scheme()
        return response("gpt-5.6-luna", proposal)

    configure(recorder)
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            provider = TeamoRouterClient(settings(), client=http)
            generator = PlannerProviderSchemeGenerator(provider)
            scheme = await generator.generate(
                research_object=obj,
                goal=goal,
                **({"incremental_context": context} if incremental else {}),
            )
    finally:
        configure(None)
    assert scheme.generated_model == "gpt-5.6-luna"
    assert [json.loads(r.content)["model"] for r in requests] == [
        "gpt-5.6-sol",
        "gpt-5.6-luna",
    ]
    assert all(
        r.extensions["timeout"]
        == {
            "connect": 10.0,
            "read": 60.0,
            "write": 30.0,
            "pool": 10.0,
        }
        for r in requests
    )
    logical = [r for r in recorder.records if r["operation"] == "model.logical_call"]
    assert len(logical) == 1
    assert logical[0]["read_timeout_s"] == 60
    assert logical[0]["attempt_deadline_s"] == 90
    assert logical[0]["workload_deadline_s"] == 180
    assert logical[0]["max_attempts"] == 2
    attempts = [r for r in recorder.records if r["operation"] == "model.attempt"]
    assert len(attempts) == 2 and attempts[0]["failure_code"] == "read_timeout"
    assert attempts[1]["outcome"] == "SUCCESS"
    assert all(r["logical_call_id"] == logical[0]["logical_call_id"] for r in attempts)
    backoff = [r for r in recorder.records if r["operation"] == "model.retry_backoff"]
    assert len(backoff) == 1 and backoff[0]["configured_delay_s"] == 1
    text = json.dumps(recorder.snapshot())
    assert "PRIVATE_BODY" not in text and "redaction-sentinel" not in text
    assert goal.goal_text not in text


async def test_exhausted_incremental_timeout_is_not_empty_or_fallback_scheme():
    _, obj, goal, context = real_inputs()
    recorder = Recorder()
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        raise httpx.ReadTimeout("PRIVATE_BODY", request=request)

    configure(recorder)
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            generator = PlannerProviderSchemeGenerator(TeamoRouterClient(settings(), client=http))
            with pytest.raises(IncrementalSchemeFailure) as error:
                await generator.generate(
                    research_object=obj, goal=goal, incremental_context=context
                )
    finally:
        configure(None)
    assert count == error.value.attempted_count == 2
    assert error.value.reason_code == "INCREMENTAL_MODEL_INVOCATION_READ_TIMEOUT"
    assert not generator.decisions and generator.last_audit is None
    calls = [r for r in recorder.records if r["operation"] == "model.logical_call"]
    assert len(calls) == 1 and calls[0]["failure_code"] == "read_timeout"
    assert "PRIVATE_BODY" not in json.dumps(recorder.snapshot())
