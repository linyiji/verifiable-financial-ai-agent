from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from src.adapters.llm import (
    LLMFailureClassification,
    LLMMessage,
    LLMProviderUnavailableError,
    LLMRequestError,
    StructuredOutputError,
    TeamoRouterClient,
)
from src.infrastructure.config.settings import LLMSettings


class Answer(BaseModel):
    value: str


class BrokenSchema(BaseModel):
    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        del cls, args, kwargs
        raise ValueError("schema cannot be generated")


def settings() -> LLMSettings:
    return LLMSettings(
        provider="teamorouter",
        api_key="redaction-sentinel",
        base_url="https://router.invalid/v1",
        primary_model="gpt-5.6-sol",
        fallback_model="gpt-5.6-luna",
    )


def response(model: str, content: object, *, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        json={
            "model": model,
            "choices": [{"message": {"content": json.dumps(content)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        },
        headers={"x-request-id": "request-safe-1"},
    )


@pytest.mark.asyncio
async def test_primary_structured_response_records_safe_routing_metadata() -> None:
    requested_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_payloads.append(json.loads(request.content))
        return response("gpt-5.6-sol", {"value": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TeamoRouterClient(settings(), client=http)
        result = await client.complete_structured(
            messages=[LLMMessage(role="user", content="return an answer")],
            response_model=Answer,
            schema_name="answer_v1",
        )

    assert result.output.value == "ok"
    assert result.requested_model == result.actual_model == "gpt-5.6-sol"
    assert result.attempted_models == ("gpt-5.6-sol",)
    assert result.request_id == "request-safe-1"
    assert requested_payloads[0]["response_format"]["type"] == "json_schema"
    assert "redaction-sentinel" not in repr(client)
    assert "redaction-sentinel" not in repr(result)


@pytest.mark.asyncio
async def test_rate_limit_routes_to_configured_fallback_only() -> None:
    models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        models.append(model)
        if model == "gpt-5.6-sol":
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return response("gpt-5.6-luna", {"value": "fallback"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await TeamoRouterClient(settings(), client=http).complete_structured(
            messages=[LLMMessage(role="user", content="answer")],
            response_model=Answer,
            schema_name="answer_v1",
        )

    assert models == ["gpt-5.6-sol", "gpt-5.6-luna"]
    assert result.requested_model == "gpt-5.6-sol"
    assert result.actual_model == "gpt-5.6-luna"
    assert result.used_model_fallback is True


@pytest.mark.asyncio
async def test_exhausted_retryable_route_records_every_actual_attempt() -> None:
    models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        models.append(json.loads(request.content)["model"])
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(LLMProviderUnavailableError) as caught:
            await TeamoRouterClient(settings(), client=http).complete_structured(
                messages=[LLMMessage(role="user", content="answer")],
                response_model=Answer,
                schema_name="answer_v1",
            )

    assert models == ["gpt-5.6-sol", "gpt-5.6-luna"]
    assert caught.value.attempted_models == tuple(models)
    assert caught.value.failure_classification is LLMFailureClassification.RETRYABLE_HTTP_FAILURE


@pytest.mark.asyncio
async def test_timeout_routes_to_configured_fallback_only() -> None:
    models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        models.append(model)
        if model == "gpt-5.6-sol":
            raise httpx.ReadTimeout("bounded timeout", request=request)
        return response("gpt-5.6-luna", {"value": "fallback"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await TeamoRouterClient(settings(), client=http).complete_structured(
            messages=[LLMMessage(role="user", content="answer")],
            response_model=Answer,
            schema_name="answer_v1",
        )

    assert models == ["gpt-5.6-sol", "gpt-5.6-luna"]
    assert result.actual_model == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_nonretryable_request_and_invalid_structure_do_not_switch_model() -> None:
    statuses = [400, 200]
    calls: list[str] = []

    def bad_request(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content)["model"])
        return httpx.Response(statuses[0], json={"error": {"message": "invalid"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(bad_request)) as http:
        with pytest.raises(LLMRequestError, match="HTTP 400") as request_error:
            await TeamoRouterClient(settings(), client=http).complete_structured(
                messages=[LLMMessage(role="user", content="answer")],
                response_model=Answer,
                schema_name="answer_v1",
            )
    assert calls == ["gpt-5.6-sol"]
    assert request_error.value.attempted_models == ("gpt-5.6-sol",)
    assert request_error.value.failure_classification is LLMFailureClassification.REQUEST_REJECTED

    calls.clear()

    def malformed(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content)["model"])
        return response("gpt-5.6-sol", {"wrong": "shape"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(malformed)) as http:
        with pytest.raises(StructuredOutputError, match="validation") as structured_error:
            await TeamoRouterClient(settings(), client=http).complete_structured(
                messages=[LLMMessage(role="user", content="answer")],
                response_model=Answer,
                schema_name="answer_v1",
            )
    assert calls == ["gpt-5.6-sol"]
    assert structured_error.value.attempted_models == ("gpt-5.6-sol",)
    assert (
        structured_error.value.failure_classification
        is LLMFailureClassification.STRUCTURED_OUTPUT_INVALID
    )


@pytest.mark.asyncio
async def test_preflight_failure_is_explicit_and_records_no_http_attempt() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response("gpt-5.6-sol", {"value": "should-not-run"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(LLMRequestError, match="preflight") as caught:
            await TeamoRouterClient(settings(), client=http).complete_structured(
                messages=[LLMMessage(role="user", content="answer")],
                response_model=BrokenSchema,
                schema_name="broken_v1",
            )

    assert calls == 0
    assert caught.value.attempted_models == ()
    assert caught.value.failure_classification is LLMFailureClassification.PREFLIGHT_FAILURE
    assert "redaction-sentinel" not in str(caught.value)


@pytest.mark.asyncio
async def test_direct_fallback_without_primary_failure_is_rejected_at_preflight() -> None:
    models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        models.append(model)
        return response(model, {"value": "policy"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(LLMRequestError) as caught:
            await TeamoRouterClient(settings(), client=http).complete_structured(
                messages=[LLMMessage(role="user", content="answer")],
                response_model=Answer,
                schema_name="answer_v1",
                force_fallback=True,
            )

    assert models == []
    assert caught.value.attempted_models == ()
    assert caught.value.failure_classification is LLMFailureClassification.PREFLIGHT_FAILURE
