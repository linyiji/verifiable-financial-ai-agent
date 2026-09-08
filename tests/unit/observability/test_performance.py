from __future__ import annotations

import asyncio
import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from src.adapters.fmp.provider import FMPProvider, HttpxFMPTransport
from src.adapters.llm import (
    LLMMessage,
    LLMProviderUnavailableError,
    LLMRequestError,
    StructuredOutputError,
    TeamoRouterClient,
)
from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.data.provider import ProviderRequest
from src.infrastructure.config.settings import FMPSettings, LLMSettings
from src.observability.performance import Recorder, configure, measured_lock, observe, span


class Answer(BaseModel):
    value: str


@pytest.fixture
def recorder(tmp_path):
    recorder = Recorder(tmp_path / "metadata.json", forbidden_values=("secret-canary",))
    configure(recorder)
    yield recorder
    configure(None)


def client(http, **policy):
    return TeamoRouterClient(
        LLMSettings(
            provider="teamorouter",
            api_key="secret-canary",
            base_url="https://router.invalid/v1",
            primary_model="gpt-5.6-sol",
            fallback_model="gpt-5.6-luna",
        ),
        client=http,
        execution_policy=ProviderExecutionPolicyV1(bounded_backoff_seconds=(0.001,), **policy),
    )


def response(model="gpt-5.6-sol", *, content=None):
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [
                {"message": {"content": json.dumps(content or {"value": "private-output-canary"})}}
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            "private_reasoning": "reasoning-canary",
        },
    )


@observe("test.task", task="task")
async def invoke(task, provider):
    return await provider.complete_structured(
        messages=[
            LLMMessage(role="system", content="system-canary"),
            LLMMessage(role="user", content="prompt-canary"),
        ],
        response_model=Answer,
        schema_name="answer",
    )


def task(run="RUN-A"):
    return SimpleNamespace(run_id=run, task_id=run + ":risk", assigned_agent="risk_analyst")


def records(recorder, name):
    return [r for r in recorder.records if r["operation"] == name]


@pytest.mark.asyncio
async def test_success_identity_metadata_and_no_private_content(recorder):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response())) as http:
        result = await invoke(task(), client(http))
    assert result.output.value == "private-output-canary"
    (logical,) = records(recorder, "model.logical_call")
    (attempt,) = records(recorder, "model.attempt")
    (network,) = records(recorder, "model.http")
    assert attempt["logical_call_id"] == logical["span_id"]
    assert network["parent_span_id"] == attempt["attempt_id"]
    assert attempt["attempt_number"] == 1 and attempt["actual_model_reported"] is True
    assert attempt["input_tokens"] == 12 and attempt["output_tokens"] == 4
    assert logical["duration_ms"] >= attempt["duration_ms"] >= network["duration_ms"] >= 0
    assert all(r["run_id"] == "RUN-A" and r["task_id"] == "RUN-A:risk" for r in recorder.records)
    await recorder.flush()
    text = recorder.path.read_text()
    assert all(
        s not in text
        for s in (
            "secret-canary",
            "system-canary",
            "prompt-canary",
            "private-output-canary",
            "reasoning-canary",
            "Authorization",
            "router.invalid",
        )
    )


@pytest.mark.asyncio
async def test_fallback_one_logical_two_distinct_attempts_one_backoff(recorder):
    calls = []

    def handler(request):
        model = json.loads(request.content)["model"]
        calls.append(model)
        return (
            httpx.Response(429, json={"error": "secret-canary"})
            if len(calls) == 1
            else response(model)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await invoke(task(), client(http))
    attempts = records(recorder, "model.attempt")
    assert len(records(recorder, "model.logical_call")) == 1
    assert len(attempts) == 2 and len({r["attempt_id"] for r in attempts}) == 2
    assert [r["attempt_number"] for r in attempts] == [1, 2]
    assert attempts[0]["failure_code"] == "quota_or_rate_limit"
    assert attempts[1]["outcome"] == "SUCCESS"
    assert "input_tokens" not in attempts[0] and "output_tokens" not in attempts[0]
    assert attempts[1]["input_tokens"] == 12 and attempts[1]["output_tokens"] == 4
    (backoff,) = records(recorder, "model.retry_backoff")
    assert (
        attempts[0]["end_monotonic_ns"]
        <= backoff["start_monotonic_ns"]
        < backoff["end_monotonic_ns"]
        <= attempts[1]["start_monotonic_ns"]
    )
    assert calls == ["gpt-5.6-sol", "gpt-5.6-luna"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["authentication", "schema", "missing_model", "invalid_body"])
async def test_nonretryable_and_missing_metadata(recorder, mode):
    def handler(_):
        if mode == "authentication":
            return httpx.Response(401, json={"error": "secret-canary"})
        if mode == "schema":
            return response(content={"wrong": "private-output-canary"})
        if mode == "invalid_body":
            return httpx.Response(200, json=[])
        value = response()
        body = json.loads(value.content)
        del body["model"]
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises((LLMRequestError, StructuredOutputError)):
            await invoke(task(), client(http))
    (attempt,) = records(recorder, "model.attempt")
    assert not records(recorder, "model.retry_backoff")
    if mode == "schema":
        assert attempt["input_tokens"] == 12 and attempt["outcome"] == "FAILURE"
    if mode == "missing_model":
        assert attempt["actual_model_reported"] is False and "actual_model" not in attempt


@pytest.mark.asyncio
async def test_timeout_and_cancellation_finish_spans_without_changing_exceptions(recorder):
    async def handler(_):
        await asyncio.sleep(2)
        return response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(LLMProviderUnavailableError):
            await invoke(
                task(),
                client(
                    http, per_attempt_deadline_seconds=0.01, overall_workload_deadline_seconds=0.021
                ),
            )
        assert len(records(recorder, "model.attempt")) == 2
        assert records(recorder, "model.attempt")[0]["failure_code"] == "OWNED_TIMEOUT"
        assert records(recorder, "model.attempt")[-1]["outcome"] in {"FAILURE", "CANCELLED"}
        job = asyncio.create_task(invoke(task("RUN-B"), client(http)))
        await asyncio.sleep(0.005)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
    assert records(recorder, "model.logical_call")[-1]["outcome"] == "CANCELLED"


@pytest.mark.asyncio
async def test_concurrent_contexts_do_not_bleed(recorder):
    async def handler(_):
        await asyncio.sleep(0.001)
        return response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await asyncio.gather(
            invoke(task("RUN-A"), client(http)), invoke(task("RUN-B"), client(http))
        )
    for attempt in records(recorder, "model.attempt"):
        logical = next(r for r in recorder.records if r["span_id"] == attempt["logical_call_id"])
        assert (
            logical["run_id"] == attempt["run_id"]
            and attempt["task_id"] == attempt["run_id"] + ":risk"
        )
    with span("test.outside"):
        pass
    assert "run_id" not in recorder.records[-1]


@pytest.mark.asyncio
async def test_preflight_has_no_attempt(recorder):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response())) as http:
        with pytest.raises(LLMRequestError):
            await client(http).complete_structured(
                messages=[], response_model=Answer, schema_name="answer"
            )
    assert len(records(recorder, "model.logical_call")) == 1 and not records(
        recorder, "model.attempt"
    )


@pytest.mark.asyncio
async def test_lock_wait_excludes_work_and_releases_after_error(recorder):
    lock = asyncio.Lock()
    await lock.acquire()

    async def release():
        await asyncio.sleep(0.01)
        lock.release()

    job = asyncio.create_task(release())
    with pytest.raises(ValueError):
        async with measured_lock(lock, "test.lock_wait"):
            await asyncio.sleep(0.02)
            raise ValueError("secret-canary")
    await job
    assert not lock.locked()
    (wait,) = records(recorder, "test.lock_wait")
    assert wait["duration_ms"] >= 5 and wait["outcome"] == "SUCCESS"


@pytest.mark.asyncio
async def test_bounded_sink_failure_and_allowlist(recorder, tmp_path):
    recorder.limit = 1
    with span(
        "test.safe",
        prompt="prompt-canary",
        actual_model="gpt-secret-canary",
        input_tokens=True,
        provider={"secret": "x"},
    ):
        pass
    with span("test.dropped"):
        pass
    assert recorder.dropped == 1 and len(recorder.records) == 1
    assert not {"prompt", "actual_model", "input_tokens", "provider"} & recorder.records[0].keys()
    recorder.path = tmp_path  # directory replacement fails; never breaks workload
    await recorder.flush()
    assert recorder.flush_failed
    configure(None)
    async with measured_lock(asyncio.Lock(), "test.disabled"):
        with span("test.disabled"):
            pass
    assert len(recorder.records) == 1


@pytest.mark.asyncio
async def test_data_retry_spans_count_real_http_not_evidence_rows(recorder):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": "secret-canary"})
        return httpx.Response(200, json=[{"symbol": "NVDA", "price": 100}])

    settings = FMPSettings(api_key="secret-canary", base_url="https://data.invalid")
    provider = FMPProvider(HttpxFMPTransport(settings, http_transport=httpx.MockTransport(handler)))

    @observe("test.data", run="run_id")
    async def probe(run_id):
        return await provider.probe(
            ProviderRequest(symbol="NVDA", dataset="quote", as_of=date(2026, 9, 7))
        )

    await probe("RUN-DATA")
    assert len(calls) == len(records(recorder, "data.http_attempt")) == 2
    assert len(records(recorder, "data.retry_backoff")) == 1
    assert len(records(recorder, "data.request_lock_wait")) == 2
    assert [r["http_status"] for r in records(recorder, "data.http_attempt")] == [503, 200]
    text = json.dumps(recorder.snapshot())
    assert "secret-canary" not in text and "NVDA" not in text and "data.invalid" not in text
