from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from src.adapters.llm import (
    LLMMessage,
    LLMRequestError,
    StructuredOutputError,
    TeamoRouterClient,
)
from src.infrastructure.config.settings import LLMSettings


class Answer(BaseModel):
    value: str


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
        with pytest.raises(LLMRequestError, match="HTTP 400"):
            await TeamoRouterClient(settings(), client=http).complete_structured(
                messages=[LLMMessage(role="user", content="answer")],
                response_model=Answer,
                schema_name="answer_v1",
            )
    assert calls == ["gpt-5.6-sol"]

    calls.clear()

    def malformed(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content)["model"])
        return response("gpt-5.6-sol", {"wrong": "shape"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(malformed)) as http:
        with pytest.raises(StructuredOutputError, match="validation"):
            await TeamoRouterClient(settings(), client=http).complete_structured(
                messages=[LLMMessage(role="user", content="answer")],
                response_model=Answer,
                schema_name="answer_v1",
            )
    assert calls == ["gpt-5.6-sol"]


@pytest.mark.asyncio
async def test_explicit_policy_can_route_directly_to_fallback() -> None:
    models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        models.append(model)
        return response(model, {"value": "policy"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await TeamoRouterClient(settings(), client=http).complete_structured(
            messages=[LLMMessage(role="user", content="answer")],
            response_model=Answer,
            schema_name="answer_v1",
            force_fallback=True,
        )

    assert models == ["gpt-5.6-luna"]
    assert result.requested_model == "gpt-5.6-sol"
    assert result.actual_model == "gpt-5.6-luna"
