from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from src.adapters.llm.provider import (
    LLMFailureClassification,
    LLMMessage,
    LLMProviderUnavailableError,
    LLMRequestError,
    LLMStructuredResponse,
    StructuredOutputError,
)
from src.infrastructure.config.settings import LLMSettings

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class _RetryableProviderFailure(RuntimeError):
    def __init__(self, message: str, classification: LLMFailureClassification) -> None:
        super().__init__(message)
        self.classification = classification


class OpenAICompatiblePlannerClient:
    """Owned structured-output client for a registered OpenAI-compatible provider.

    The injected settings retain the API key as ``SecretStr``. Public results and
    exceptions expose only routing metadata and never authorization values.
    """

    provider_name = ""

    def __init__(
        self,
        settings: LLMSettings,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not self.provider_name:
            raise TypeError("OpenAICompatiblePlannerClient must be specialized")
        if settings.provider.lower() != self.provider_name:
            raise ValueError(
                f"{self.provider_name} client received settings for an unsupported provider"
            )
        if not settings.enabled:
            raise ValueError(f"{self.provider_name} API key is not configured")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._settings = settings
        self._client = client
        self._timeout_seconds = timeout_seconds

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(provider={self.provider_name!r}, "
            f"base_url={self._settings.base_url!r}, "
            f"primary_model={self._settings.primary_model!r}, "
            f"fallback_model={self._settings.fallback_model!r}, credential_set=True)"
        )

    @property
    def model_name(self) -> str:
        return self._settings.primary_model

    def lock_to_model(self, model_name: str) -> OpenAICompatiblePlannerClient:
        if model_name not in {
            self._settings.primary_model,
            self._settings.fallback_model,
        }:
            raise ValueError("cannot lock to a model outside the governed provider route")
        locked_settings = self._settings.model_copy(
            update={"primary_model": model_name, "fallback_model": model_name}
        )
        return type(self)(
            locked_settings,
            client=self._client,
            timeout_seconds=self._timeout_seconds,
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
        try:
            _validate_completion_url(self._completion_url)
            request_template = _structured_request_template(
                messages=messages,
                response_model=response_model,
                schema_name=schema_name,
            )
        except Exception:
            raise LLMRequestError(
                f"{self.provider_name} {schema_name} request failed preflight",
                requested_model=requested_model,
                attempted_models=(),
                failure_classification=LLMFailureClassification.PREFLIGHT_FAILURE,
            ) from None
        if force_fallback:
            raise LLMRequestError(
                f"{self.provider_name} direct fallback routing is disabled",
                requested_model=requested_model,
                attempted_models=(),
                failure_classification=LLMFailureClassification.PREFLIGHT_FAILURE,
            )
        route = [requested_model, self._settings.fallback_model]
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
                    request_template=request_template,
                    response_model=response_model,
                    schema_name=schema_name,
                )
            except _RetryableProviderFailure as exc:
                last_retryable = exc
                continue
        detail = str(last_retryable) if last_retryable else "provider route unavailable"
        raise LLMProviderUnavailableError(
            f"{self.provider_name} models unavailable after {len(attempted)} attempt(s): {detail}",
            requested_model=requested_model,
            attempted_models=tuple(attempted),
            failure_classification=(
                last_retryable.classification if last_retryable is not None else None
            ),
        )

    async def _send(
        self,
        *,
        model: str,
        requested_model: str,
        attempted_models: tuple[str, ...],
        request_template: dict[str, Any],
        response_model: type[StructuredModel],
        schema_name: str,
    ) -> LLMStructuredResponse[StructuredModel]:
        payload = {"model": model, **request_template}
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
        except httpx.TransportError as exc:
            raise _RetryableProviderFailure(
                type(exc).__name__, LLMFailureClassification.RETRYABLE_TRANSPORT_FAILURE
            ) from None

        if response.status_code in {408, 429} or response.status_code >= 500:
            raise _RetryableProviderFailure(
                f"HTTP {response.status_code}",
                LLMFailureClassification.RETRYABLE_HTTP_FAILURE,
            )
        if response.is_error:
            raise LLMRequestError(
                f"{self.provider_name} rejected structured request: HTTP {response.status_code}",
                requested_model=requested_model,
                attempted_models=attempted_models,
                failure_classification=LLMFailureClassification.REQUEST_REJECTED,
            )

        try:
            body = response.json()
            content = _extract_content(body)
            decoded = json.loads(content) if isinstance(content, str) else content
            output = response_model.model_validate(decoded)
        except (ValueError, TypeError, KeyError, IndexError, ValidationError) as exc:
            raise StructuredOutputError(
                f"{self.provider_name} response failed {schema_name} validation: "
                f"{type(exc).__name__}",
                requested_model=requested_model,
                attempted_models=attempted_models,
                failure_classification=LLMFailureClassification.STRUCTURED_OUTPUT_INVALID,
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


class TeamoRouterClient(OpenAICompatiblePlannerClient):
    """TeamoRouter specialization of the owned OpenAI-compatible boundary."""

    provider_name = "teamorouter"


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


def _structured_request_template(
    *,
    messages: list[LLMMessage],
    response_model: type[StructuredModel],
    schema_name: str,
) -> dict[str, Any]:
    if not messages:
        raise ValueError("at least one LLM message is required")
    if not schema_name.strip():
        raise ValueError("schema_name must not be empty")
    template = {
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
    json.dumps(template, separators=(",", ":"))
    return template


def _validate_completion_url(value: str) -> None:
    url = httpx.URL(value)
    if url.scheme not in {"http", "https"} or not url.host:
        raise ValueError("completion URL must be absolute HTTP(S)")


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None
