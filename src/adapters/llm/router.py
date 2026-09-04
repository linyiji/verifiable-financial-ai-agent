from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.adapters.llm.provider import LLMProvider, LLMStructuredResponse

MIMO_PRIMARY_TEAMOROUTER_SECONDARY = "MIMO_PRIMARY_TEAMOROUTER_SECONDARY"
SUPPORTED_PLANNER_PROVIDERS = frozenset({"mimo", "teamorouter"})


class PlannerProviderUnavailableError(RuntimeError):
    """Every registered provider failed its owned planner preflight."""

    def __init__(self, health_checks: tuple[PlannerProviderHealth, ...]) -> None:
        super().__init__("all governed planner providers are unavailable")
        self.health_checks = health_checks


class PlannerProviderLockError(RuntimeError):
    """A selected authoritative provider/model identity was violated."""


@dataclass(frozen=True, slots=True)
class PlannerProviderHealth:
    provider: str
    model: str | None
    passed: bool
    failure_classification: str | None = None


@dataclass(frozen=True, slots=True)
class PlannerProviderSelection:
    provider: LockedPlannerProvider
    provider_name: str
    model_name: str
    policy_id: str
    selection_reason: str
    fallback_used: bool
    health_checked_at: datetime
    health_checks: tuple[PlannerProviderHealth, ...]

    def safe_evidence(self) -> dict[str, Any]:
        return {
            "selected_provider": self.provider_name,
            "selected_model": self.model_name,
            "policy_id": self.policy_id,
            "selection_reason": self.selection_reason,
            "fallback_used": self.fallback_used,
            "health_checked_at": self.health_checked_at.isoformat(),
            "health_checks": [
                {
                    "provider": item.provider,
                    "model": item.model,
                    "passed": item.passed,
                    "failure_classification": item.failure_classification,
                }
                for item in self.health_checks
            ],
            "provider_model_locked": True,
            "mid_run_failover_enabled": False,
        }


class LockedPlannerProvider:
    """Pin one truthful provider/model identity for an authoritative Run."""

    def __init__(self, delegate: LLMProvider, *, provider_name: str, model_name: str) -> None:
        if provider_name not in SUPPORTED_PLANNER_PROVIDERS:
            raise ValueError("unknown planner provider")
        if getattr(delegate, "provider_name", None) != provider_name:
            raise ValueError("planner provider identity does not match its registration")
        if not model_name:
            raise ValueError("planner model lock must not be empty")
        self._delegate = delegate
        self.provider_name = provider_name
        self.model_name = model_name

    def __repr__(self) -> str:
        return f"LockedPlannerProvider(provider={self.provider_name!r}, model={self.model_name!r})"

    async def complete_structured(self, **kwargs: Any) -> Any:
        response = await self._delegate.complete_structured(**kwargs)
        if not isinstance(response, LLMStructuredResponse):
            raise PlannerProviderLockError("provider returned an unknown owned result type")
        if response.provider != self.provider_name or response.actual_model != self.model_name:
            raise PlannerProviderLockError("authoritative provider/model lock was violated")
        return response


PlannerPreflight = Callable[[LLMProvider], Awaitable[PlannerProviderHealth]]


class PlannerProviderRouter:
    """Select and lock a registered planner provider before Run creation."""

    def __init__(
        self,
        providers: Iterable[LLMProvider],
        *,
        preference_order: tuple[str, ...] = ("mimo", "teamorouter"),
        policy_id: str = MIMO_PRIMARY_TEAMOROUTER_SECONDARY,
    ) -> None:
        registered: dict[str, LLMProvider] = {}
        for provider in providers:
            name = getattr(provider, "provider_name", None)
            if name not in SUPPORTED_PLANNER_PROVIDERS:
                raise ValueError("unknown planner provider")
            if name in registered:
                raise ValueError("planner provider registered more than once")
            registered[name] = provider
        if (
            not preference_order
            or len(preference_order) != len(set(preference_order))
            or not set(preference_order).issubset(SUPPORTED_PLANNER_PROVIDERS)
        ):
            raise ValueError("invalid planner provider preference order")
        self._providers = registered
        self._preference_order = preference_order
        self._policy_id = policy_id
        self._selection_attempted = False
        self._selection: PlannerProviderSelection | None = None

    @property
    def selection(self) -> PlannerProviderSelection | None:
        return self._selection

    async def select(self, preflight: PlannerPreflight) -> PlannerProviderSelection:
        if self._selection_attempted:
            raise PlannerProviderLockError("planner provider selection is immutable")
        self._selection_attempted = True
        checks: list[PlannerProviderHealth] = []
        for index, name in enumerate(self._preference_order):
            provider = self._providers.get(name)
            if provider is None:
                checks.append(
                    PlannerProviderHealth(
                        provider=name,
                        model=None,
                        passed=False,
                        failure_classification="not_configured",
                    )
                )
                continue
            health = await preflight(provider)
            if health.provider != name:
                raise PlannerProviderLockError("preflight returned a false provider identity")
            checks.append(health)
            if not health.passed or not health.model:
                continue
            lock_factory = getattr(provider, "lock_to_model", None)
            locked_delegate = lock_factory(health.model) if callable(lock_factory) else provider
            locked = LockedPlannerProvider(
                locked_delegate,
                provider_name=name,
                model_name=health.model,
            )
            configured_model = getattr(provider, "model_name", health.model)
            fallback_used = index > 0 or health.model != configured_model
            self._selection = PlannerProviderSelection(
                provider=locked,
                provider_name=name,
                model_name=health.model,
                policy_id=self._policy_id,
                selection_reason=(
                    "preferred_provider_healthy"
                    if index == 0
                    else "preferred_provider_unavailable_secondary_healthy"
                ),
                fallback_used=fallback_used,
                health_checked_at=datetime.now(UTC),
                health_checks=tuple(checks),
            )
            return self._selection
        raise PlannerProviderUnavailableError(tuple(checks))
