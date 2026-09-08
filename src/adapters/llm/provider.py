from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel


class LLMFailureClassification(StrEnum):
    MODEL_IDENTITY_MISMATCH = "model_identity_mismatch"
    PREFLIGHT_FAILURE = "preflight_failure"
    AUTHENTICATION_FAILURE = "authentication_failure"
    QUOTA_OR_RATE_LIMIT = "quota_or_rate_limit"
    RETRYABLE_HTTP_FAILURE = "retryable_http_failure"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RETRYABLE_TRANSPORT_FAILURE = "provider_unavailable"
    CONNECT_TIMEOUT = "connect_timeout"
    READ_TIMEOUT = "read_timeout"
    OVERALL_DEADLINE_EXCEEDED = "overall_deadline_exceeded"
    REMOTE_PROTOCOL_ERROR = "remote_protocol_error"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"
    SEMANTIC_SCHEMA_FAILURE = "semantic_schema_failure"
    STRUCTURED_OUTPUT_INVALID = "semantic_schema_failure"
    SEMANTIC_VALIDATION_FAILED = "semantic_schema_failure"
    REQUEST_REJECTED = "request_rejected"


class LLMProviderError(RuntimeError):
    """Secret-safe provider error carrying only actual HTTP-attempt provenance."""

    def __init__(
        self,
        message: str,
        *,
        requested_model: str | None = None,
        attempted_models: tuple[str, ...] = (),
        failure_classification: LLMFailureClassification | None = None,
        provider: str | None = None,
        model: str | None = None,
        workload_type: str | None = None,
        attempt: int | None = None,
        elapsed_seconds: float | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.requested_model = requested_model
        self.attempted_models = attempted_models
        self.failure_classification = failure_classification
        self.provider = provider
        self.model = model
        self.workload_type = workload_type
        self.attempt = attempt
        self.elapsed_seconds = elapsed_seconds
        self.retryable = retryable


class LLMProviderUnavailableError(LLMProviderError):
    """Retryable provider failure exhausted the configured model route."""

    def __init__(
        self,
        message: str,
        *,
        requested_model: str | None = None,
        attempted_models: tuple[str, ...] = (),
        failure_classification: LLMFailureClassification | None = None,
        provider: str | None = None,
        model: str | None = None,
        workload_type: str | None = None,
        attempt: int | None = None,
        elapsed_seconds: float | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(
            message,
            requested_model=requested_model,
            attempted_models=attempted_models,
            failure_classification=failure_classification,
            provider=provider,
            model=model,
            workload_type=workload_type,
            attempt=attempt,
            elapsed_seconds=elapsed_seconds,
            retryable=retryable,
        )


class LLMRequestError(LLMProviderError):
    """Non-retryable request/auth/schema negotiation failure."""


class StructuredOutputError(LLMProviderError):
    """Provider answered, but its content failed the requested Pydantic schema."""


class LLMMessage(BaseModel):
    role: str
    content: str


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class LLMStructuredResponse(Generic[StructuredModel]):
    output: StructuredModel
    provider: str
    requested_model: str
    actual_model: str
    attempted_models: tuple[str, ...]
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def used_model_fallback(self) -> bool:
        return self.actual_model != self.requested_model


@runtime_checkable
class LLMProvider(Protocol):
    provider_name: str

    @property
    def model_name(self) -> str: ...

    async def complete_structured(
        self,
        *,
        messages: list[LLMMessage],
        response_model: type[StructuredModel],
        schema_name: str,
        force_fallback: bool = False,
        workload_type: str | None = None,
    ) -> LLMStructuredResponse[StructuredModel]: ...
