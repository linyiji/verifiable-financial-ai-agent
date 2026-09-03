from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel


class LLMProviderError(RuntimeError):
    """Base provider error. Messages must never include authorization material."""


class LLMProviderUnavailableError(LLMProviderError):
    """Retryable provider failure exhausted the configured model route."""

    def __init__(
        self,
        message: str,
        *,
        requested_model: str | None = None,
        attempted_models: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.requested_model = requested_model
        self.attempted_models = attempted_models


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
    async def complete_structured(
        self,
        *,
        messages: list[LLMMessage],
        response_model: type[StructuredModel],
        schema_name: str,
        force_fallback: bool = False,
    ) -> LLMStructuredResponse[StructuredModel]: ...
