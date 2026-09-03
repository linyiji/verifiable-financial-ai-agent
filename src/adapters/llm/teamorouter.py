from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from src.adapters.llm.provider import (
    LLMMessage,
    LLMProviderUnavailableError,
    LLMRequestError,
    LLMStructuredResponse,
    StructuredOutputError,
)
from src.infrastructure.config.settings import LLMSettings

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class _RetryableProviderFailure(RuntimeError):
    pass


class TeamoRouterClient:
    """OpenAI-compatible structured-output client for TeamoRouter.

    The injected settings retain the API key as ``SecretStr``. Public results and
    exceptions expose only routing metadata and never authorization values.
    """

    provider_name = "teamorouter"

    def __init__(
        self,
        settings: LLMSettings,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        if settings.provider.lower() != self.provider_name:
            raise ValueError(f"unsupported LLM provider: {settings.provider}")
        if not settings.enabled:
            raise ValueError("TeamoRouter API key is not configured")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._settings = settings
        self._client = client
        self._timeout_seconds = timeout_seconds

    def __repr__(self) -> str:
        return (
            "TeamoRouterClient(provider='teamorouter', "
            f"base_url={self._settings.base_url!r}, "
            f"primary_model={self._settings.primary_model!r}, "
            f"fallback_model={self._settings.fallback_model!r}, credential_set=True)"
        )

    async def complete_structured(
        self,
        *,
        messages: list[LLMMessage],
        response_model: type[StructuredModel],
        schema_name: str,
        force_fallback: bool = False,
    ) -> LLMStructuredResponse[StructuredModel]:
        requested_model = self._settings.primary_model
        route = (
            [self._settings.fallback_model]
            if force_fallback
            else [requested_model, self._settings.fallback_model]
        )
        attempted: list[str] = []
        last_retryable: _RetryableProviderFailure | None = None
        for model in route:
            if model in attempted:
                continue
            attempted.append(model)
            try:
                return await self._send(
                    model=model,
                    requested_model=requested_model,
                    attempted_models=tuple(attempted),
                    messages=messages,
                    response_model=response_model,
                    schema_name=schema_name,
                )
            except _RetryableProviderFailure as exc:
                last_retryable = exc
                continue
        detail = str(last_retryable) if last_retryable else "provider route unavailable"
        raise LLMProviderUnavailableError(
            f"TeamoRouter models unavailable after {len(attempted)} attempt(s): {detail}",
            requested_model=requested_model,
            attempted_models=tuple(attempted),
        )

    async def _send(
        self,
        *,
        model: str,
        requested_model: str,
        attempted_models: tuple[str, ...],
        messages: list[LLMMessage],
        response_model: type[StructuredModel],
        schema_name: str,
    ) -> LLMStructuredResponse[StructuredModel]:
        payload = {
            "model": model,
            "messages": [message.model_dump(mode="json") for message in messages],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            },
        }
        headers = {
            "Authorization": f"Bearer {self._settings.api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        try:
            if self._client is None:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(
                        self._completion_url, json=payload, headers=headers
                    )
            else:
                response = await self._client.post(
                    self._completion_url,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise _RetryableProviderFailure(type(exc).__name__) from None

        if response.status_code in {408, 429} or response.status_code >= 500:
            raise _RetryableProviderFailure(f"HTTP {response.status_code}")
        if response.is_error:
            raise LLMRequestError(
                f"TeamoRouter rejected structured request: HTTP {response.status_code}"
            )

        try:
            body = response.json()
            content = _extract_content(body)
            decoded = json.loads(content) if isinstance(content, str) else content
            output = response_model.model_validate(decoded)
        except (ValueError, TypeError, KeyError, IndexError, ValidationError) as exc:
            raise StructuredOutputError(
                f"TeamoRouter response failed {schema_name} validation: {type(exc).__name__}"
            ) from None

        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        actual_model = body.get("model")
        if not isinstance(actual_model, str) or not actual_model:
            actual_model = model
        request_id = response.headers.get("x-request-id")
        return LLMStructuredResponse(
            output=output,
            provider=self.provider_name,
            requested_model=requested_model,
            actual_model=actual_model,
            attempted_models=attempted_models,
            request_id=request_id,
            input_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
        )

    @property
    def _completion_url(self) -> str:
        return f"{self._settings.base_url.rstrip('/')}/chat/completions"


def _extract_content(body: dict[str, Any]) -> str | dict[str, Any]:
    content = body["choices"][0]["message"]["content"]
    if isinstance(content, (str, dict)):
        return content
    if isinstance(content, list):
        text = "".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}
        )
        if text:
            return text
    raise TypeError("unsupported structured content shape")


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None
