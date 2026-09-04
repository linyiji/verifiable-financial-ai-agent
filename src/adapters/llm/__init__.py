"""Structured LLM provider boundary with secret-safe audit metadata."""

from src.adapters.llm.mimo import MimoClient
from src.adapters.llm.provider import (
    LLMFailureClassification,
    LLMMessage,
    LLMProvider,
    LLMProviderError,
    LLMProviderUnavailableError,
    LLMRequestError,
    LLMStructuredResponse,
    StructuredOutputError,
)
from src.adapters.llm.router import (
    MIMO_PRIMARY_TEAMOROUTER_SECONDARY,
    SUPPORTED_PLANNER_PROVIDERS,
    LockedPlannerProvider,
    PlannerProviderHealth,
    PlannerProviderLockError,
    PlannerProviderRouter,
    PlannerProviderSelection,
    PlannerProviderUnavailableError,
)
from src.adapters.llm.teamorouter import (
    OpenAICompatiblePlannerClient,
    TeamoRouterClient,
)

__all__ = [
    "LLMMessage",
    "LLMFailureClassification",
    "LLMProvider",
    "LLMProviderError",
    "LLMProviderUnavailableError",
    "LLMRequestError",
    "LLMStructuredResponse",
    "LockedPlannerProvider",
    "MIMO_PRIMARY_TEAMOROUTER_SECONDARY",
    "MimoClient",
    "OpenAICompatiblePlannerClient",
    "PlannerProviderHealth",
    "PlannerProviderLockError",
    "PlannerProviderRouter",
    "PlannerProviderSelection",
    "PlannerProviderUnavailableError",
    "SUPPORTED_PLANNER_PROVIDERS",
    "StructuredOutputError",
    "TeamoRouterClient",
]
