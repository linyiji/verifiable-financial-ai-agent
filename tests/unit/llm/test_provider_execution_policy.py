from __future__ import annotations

import asyncio
import json
from time import perf_counter

import httpx
import pytest
from pydantic import BaseModel

from src.adapters.llm import (
    LLMFailureClassification,
    LLMMessage,
    LLMProviderUnavailableError,
    LLMRequestError,
    ProviderExecutionPolicyV1,
    StructuredOutputError,
    TeamoRouterClient,
)
from src.infrastructure.config.settings import LLMSettings


class Answer(BaseModel):
    value: str


def _settings() -> LLMSettings:
    return LLMSettings(
        provider="teamorouter",
        api_key="deadline-credential-sentinel",
        base_url="https://router.invalid/v1",
        primary_model="primary-model",
        fallback_model="fallback-model",
    )


def _policy(**updates: object) -> ProviderExecutionPolicyV1:
    values: dict[str, object] = {
        "connect_timeout_seconds": 0.02,
        "read_timeout_seconds": 0.02,
        "write_timeout_seconds": 0.02,
        "pool_timeout_seconds": 0.02,
        "max_attempts": 2,
        "bounded_backoff_seconds": (0.01,),
        "per_attempt_deadline_seconds": 0.04,
        "overall_workload_deadline_seconds": 0.09,
    }
    values.update(updates)
    return ProviderExecutionPolicyV1(**values)


async def _complete(client: TeamoRouterClient) -> None:
    await client.complete_structured(
        messages=[LLMMessage(role="user", content="return an answer")],
        response_model=Answer,
        schema_name="answer_v1",
        workload_type="GENERATED_CAPABILITY",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_type", "classification"),
    (
        (httpx.ConnectTimeout, LLMFailureClassification.CONNECT_TIMEOUT),
        (httpx.ReadTimeout, LLMFailureClassification.READ_TIMEOUT),
        (httpx.RemoteProtocolError, LLMFailureClassification.REMOTE_PROTOCOL_ERROR),
    ),
)
async def test_transport_failures_are_safe_and_attempts_are_bounded(
    error_type: type[httpx.TransportError],
    classification: LLMFailureClassification,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise error_type("unsafe upstream detail omitted", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TeamoRouterClient(_settings(), client=http, execution_policy=_policy())
        with pytest.raises(LLMProviderUnavailableError) as caught:
            await _complete(client)

    assert attempts == 2
    assert caught.value.failure_classification is classification
    assert caught.value.workload_type == "GENERATED_CAPABILITY"
    assert caught.value.attempt == 2
    assert caught.value.retryable is True
    assert "deadline-credential-sentinel" not in str(caught.value)
    assert "deadline-credential-sentinel" not in repr(caught.value)


class _TricklingStream(httpx.AsyncByteStream):
    def __init__(self, active: list[int], cancelled: list[int]) -> None:
        self._active = active
        self._cancelled = cancelled

    async def __aiter__(self):
        self._active[0] += 1
        try:
            while True:
                await asyncio.sleep(0.005)
                yield b" "
        finally:
            self._active[0] -= 1
            self._cancelled[0] += 1


@pytest.mark.asyncio
async def test_wall_clock_deadline_cancels_trickling_reads_and_retry_loop() -> None:
    attempts = 0
    active = [0]
    cancelled = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            200,
            stream=_TricklingStream(active, cancelled),
            request=request,
        )

    policy = _policy(
        per_attempt_deadline_seconds=0.025,
        overall_workload_deadline_seconds=0.06,
    )
    started = perf_counter()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TeamoRouterClient(_settings(), client=http, execution_policy=policy)
        with pytest.raises(LLMProviderUnavailableError) as caught:
            await _complete(client)
    elapsed = perf_counter() - started

    assert caught.value.failure_classification is (
        LLMFailureClassification.OVERALL_DEADLINE_EXCEEDED
    )
    assert elapsed < 0.15
    assert attempts <= policy.max_attempts
    assert active[0] == 0
    assert cancelled[0] == attempts


def test_execution_policy_rejects_unbounded_or_escaping_budgets() -> None:
    with pytest.raises(ValueError, match="positive"):
        _policy(connect_timeout_seconds=0)
    with pytest.raises(ValueError, match="must not exceed"):
        _policy(
            per_attempt_deadline_seconds=0.01,
            overall_workload_deadline_seconds=1.0,
        )

    policy = _policy(bounded_backoff_seconds=(0.01, 0.02))
    assert policy.httpx_timeout.connect == 0.02
    assert policy.httpx_timeout.read == 0.02
    assert policy.httpx_timeout.write == 0.02
    assert policy.httpx_timeout.pool == 0.02
    assert policy.backoff_seconds(1) == 0.01
    assert policy.backoff_seconds(99) == 0.02


@pytest.mark.asyncio
async def test_successful_response_stays_inside_owned_policy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        return httpx.Response(
            200,
            json={
                "model": model,
                "choices": [{"message": {"content": json.dumps({"value": "ok"})}}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TeamoRouterClient(_settings(), client=http, execution_policy=_policy())
        result = await client.complete_structured(
            messages=[LLMMessage(role="user", content="answer")],
            response_model=Answer,
            schema_name="answer_v1",
            workload_type="SCHEME_PLANNER",
        )

    assert result.output.value == "ok"
    assert result.attempted_models == ("primary-model",)


@pytest.mark.asyncio
async def test_authentication_and_quota_have_distinct_safe_classifications() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(401, request=request))
    ) as http:
        with pytest.raises(LLMRequestError) as authentication:
            await _complete(TeamoRouterClient(_settings(), client=http, execution_policy=_policy()))
    assert authentication.value.failure_classification is (
        LLMFailureClassification.AUTHENTICATION_FAILURE
    )
    assert authentication.value.retryable is False

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(429, request=request))
    ) as http:
        with pytest.raises(LLMProviderUnavailableError) as quota:
            await _complete(TeamoRouterClient(_settings(), client=http, execution_policy=_policy()))
    assert quota.value.failure_classification is LLMFailureClassification.QUOTA_OR_RATE_LIMIT
    assert quota.value.retryable is True


@pytest.mark.asyncio
async def test_invalid_wire_body_and_semantic_schema_failure_are_distinct() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"not-json", request=request)
        )
    ) as http:
        with pytest.raises(StructuredOutputError) as invalid:
            await _complete(TeamoRouterClient(_settings(), client=http, execution_policy=_policy()))
    assert invalid.value.failure_classification is (
        LLMFailureClassification.INVALID_PROVIDER_RESPONSE
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "model": "primary-model",
                    "choices": [{"message": {"content": json.dumps({"wrong": "shape"})}}],
                },
                request=request,
            )
        )
    ) as http:
        with pytest.raises(StructuredOutputError) as semantic:
            await _complete(TeamoRouterClient(_settings(), client=http, execution_policy=_policy()))
    assert semantic.value.failure_classification is (
        LLMFailureClassification.SEMANTIC_SCHEMA_FAILURE
    )
