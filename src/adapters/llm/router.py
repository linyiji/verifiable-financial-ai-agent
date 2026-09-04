from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from src.adapters.llm.provider import LLMProvider, LLMStructuredResponse

MIMO_PRIMARY_TEAMOROUTER_SECONDARY = "MIMO_PRIMARY_TEAMOROUTER_SECONDARY"
MIMO_PRIMARY_TEAMOROUTER_SECONDARY_V2 = "MIMO_PRIMARY_TEAMOROUTER_SECONDARY_V2"
CONTROLLED_PROVIDER_FAILOVER_V1 = "CONTROLLED_PROVIDER_FAILOVER_V1"
SUPPORTED_PLANNER_PROVIDERS = frozenset({"mimo", "teamorouter"})


class PlannerWorkload(StrEnum):
    SCHEME_PLANNER = "SCHEME_PLANNER"
    LEAD_PLANNER = "LEAD_PLANNER"
    GENERATED_CAPABILITY = "GENERATED_CAPABILITY"


REQUIRED_PLANNER_WORKLOADS = tuple(PlannerWorkload)


class PlannerProviderUnavailableError(RuntimeError):
    """Every registered provider failed its owned planner preflight."""

    def __init__(self, health_checks: tuple[PlannerProviderHealth, ...]) -> None:
        super().__init__("all governed planner providers are unavailable")
        self.health_checks = health_checks


class WorkloadProviderUnavailableError(RuntimeError):
    """Neither governed provider passed one required workload preflight."""

    def __init__(
        self,
        workload_type: PlannerWorkload,
        health_checks: tuple[PlannerProviderHealth, ...],
    ) -> None:
        super().__init__(f"all governed providers are unavailable for {workload_type.value}")
        self.workload_type = workload_type
        self.health_checks = health_checks


class PlannerProviderLockError(RuntimeError):
    """A selected authoritative provider/model identity was violated."""


@dataclass(frozen=True, slots=True)
class PlannerProviderHealth:
    provider: str
    model: str | None
    passed: bool
    failure_classification: str | None = None
    workload_type: PlannerWorkload | None = None
    attempt: int | None = None
    elapsed_seconds: float | None = None
    retryable: bool | None = None

    def safe_evidence(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "workload_type": self.workload_type.value if self.workload_type else None,
            "passed": self.passed,
            "failure_classification": self.failure_classification,
            "attempt": self.attempt,
            "elapsed_seconds": self.elapsed_seconds,
            "retryable": self.retryable,
        }


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

    def __init__(
        self,
        delegate: LLMProvider,
        *,
        provider_name: str,
        model_name: str,
        workload_type: PlannerWorkload | None = None,
    ) -> None:
        if provider_name not in SUPPORTED_PLANNER_PROVIDERS:
            raise ValueError("unknown planner provider")
        if getattr(delegate, "provider_name", None) != provider_name:
            raise ValueError("planner provider identity does not match its registration")
        if not model_name:
            raise ValueError("planner model lock must not be empty")
        self._delegate = delegate
        self._provider_name = provider_name
        self._model_name = model_name
        self._workload_type = workload_type

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def execution_policy(self) -> Any:
        return getattr(self._delegate, "execution_policy", None)

    @property
    def workload_type(self) -> PlannerWorkload | None:
        return self._workload_type

    def __repr__(self) -> str:
        return f"LockedPlannerProvider(provider={self.provider_name!r}, model={self.model_name!r})"

    async def complete_structured(self, **kwargs: Any) -> Any:
        if self.workload_type is not None:
            supplied_workload = kwargs.get("workload_type")
            if supplied_workload != self.workload_type.value:
                raise PlannerProviderLockError(
                    "authoritative workload provider binding was violated"
                )
        response = await self._delegate.complete_structured(**kwargs)
        if not isinstance(response, LLMStructuredResponse):
            raise PlannerProviderLockError("provider returned an unknown owned result type")
        if response.provider != self.provider_name or response.actual_model != self.model_name:
            raise PlannerProviderLockError("authoritative provider/model lock was violated")
        return response


@dataclass(frozen=True, slots=True)
class WorkloadProviderBinding:
    workload_type: PlannerWorkload
    provider: LockedPlannerProvider
    provider_name: str
    model_name: str
    selection_reason: str
    fallback_used: bool
    health_checked_at: datetime
    health_checks: tuple[PlannerProviderHealth, ...]

    def safe_evidence(self) -> dict[str, Any]:
        return {
            "workload_type": self.workload_type.value,
            "provider": self.provider_name,
            "model": self.model_name,
            "selection_reason": self.selection_reason,
            "fallback_used": self.fallback_used,
            "health_checked_at": self.health_checked_at.isoformat(),
            "health_checks": [item.safe_evidence() for item in self.health_checks],
        }


@dataclass(frozen=True, slots=True)
class RunProviderBindingV1:
    policy_id: str
    bindings: Mapping[PlannerWorkload, WorkloadProviderBinding]
    finalized_at: datetime
    mid_run_failover_enabled: bool = False

    def __post_init__(self) -> None:
        if self.policy_id != MIMO_PRIMARY_TEAMOROUTER_SECONDARY_V2:
            raise ValueError("unsupported workload provider selection policy")
        copied = dict(self.bindings)
        if set(copied) != set(REQUIRED_PLANNER_WORKLOADS):
            raise ValueError("provider binding map must contain every required workload")
        for workload, binding in copied.items():
            if binding.workload_type is not workload:
                raise ValueError("provider binding workload identity mismatch")
        if self.mid_run_failover_enabled:
            raise ValueError("Phase 3 authoritative mid-run provider failover is disabled")
        object.__setattr__(self, "bindings", MappingProxyType(copied))

    def binding_for(self, workload: PlannerWorkload) -> WorkloadProviderBinding:
        return self.bindings[workload]

    def safe_evidence(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "finalized_at": self.finalized_at.isoformat(),
            "bindings": {
                workload.value: self.bindings[workload].safe_evidence()
                for workload in REQUIRED_PLANNER_WORKLOADS
            },
            "binding_map_locked": True,
            "mid_run_failover_enabled": False,
        }


@dataclass(frozen=True, slots=True)
class ControlledProviderFailoverRecordV1:
    """Inactive provenance contract for a future explicit-boundary policy."""

    provider_before: str
    model_before: str
    provider_after: str
    model_after: str
    workload_type: PlannerWorkload
    task_id: str
    attempt_before: int
    attempt_after: int
    failure_class: str
    selection_policy_id: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.selection_policy_id != CONTROLLED_PROVIDER_FAILOVER_V1:
            raise ValueError("controlled failover record requires its governed policy id")
        if self.attempt_after <= self.attempt_before:
            raise ValueError("controlled failover must advance at an explicit attempt boundary")


PlannerPreflight = Callable[[LLMProvider], Awaitable[PlannerProviderHealth]]
WorkloadPreflight = Callable[[LLMProvider], Awaitable[PlannerProviderHealth]]


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


class WorkloadProviderRouter:
    """Finalize one immutable provider/model binding per required workload."""

    def __init__(
        self,
        providers: Iterable[LLMProvider],
        *,
        preference_order: tuple[str, ...] = ("mimo", "teamorouter"),
        policy_id: str = MIMO_PRIMARY_TEAMOROUTER_SECONDARY_V2,
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
        if policy_id != MIMO_PRIMARY_TEAMOROUTER_SECONDARY_V2:
            raise ValueError("unsupported workload provider selection policy")
        if preference_order != ("mimo", "teamorouter"):
            raise ValueError("V2 policy requires MiMo primary and TeamoRouter secondary")
        self._providers = registered
        self._preference_order = preference_order
        self._policy_id = policy_id
        self._selection_attempted = False
        self._binding_map: RunProviderBindingV1 | None = None

    @property
    def binding_map(self) -> RunProviderBindingV1 | None:
        return self._binding_map

    async def select(
        self,
        preflights: Mapping[PlannerWorkload, WorkloadPreflight],
    ) -> RunProviderBindingV1:
        if self._selection_attempted:
            raise PlannerProviderLockError("run provider binding map is immutable")
        self._selection_attempted = True
        if set(preflights) != set(REQUIRED_PLANNER_WORKLOADS):
            raise ValueError("exact workload preflights are required before provider binding")

        bindings: dict[PlannerWorkload, WorkloadProviderBinding] = {}
        for workload in REQUIRED_PLANNER_WORKLOADS:
            checks: list[PlannerProviderHealth] = []
            selected: WorkloadProviderBinding | None = None
            for index, name in enumerate(self._preference_order):
                provider = self._providers.get(name)
                if provider is None:
                    checks.append(
                        PlannerProviderHealth(
                            provider=name,
                            model=None,
                            passed=False,
                            failure_classification="not_configured",
                            workload_type=workload,
                            retryable=False,
                        )
                    )
                    continue
                health = await preflights[workload](provider)
                if health.provider != name:
                    raise PlannerProviderLockError("preflight returned a false provider identity")
                if health.workload_type is not workload:
                    raise PlannerProviderLockError("preflight returned a false workload identity")
                checks.append(health)
                if not health.passed or not health.model:
                    continue
                lock_factory = getattr(provider, "lock_to_model", None)
                delegate = lock_factory(health.model) if callable(lock_factory) else provider
                locked = LockedPlannerProvider(
                    delegate,
                    provider_name=name,
                    model_name=health.model,
                    workload_type=workload,
                )
                selected = WorkloadProviderBinding(
                    workload_type=workload,
                    provider=locked,
                    provider_name=name,
                    model_name=health.model,
                    selection_reason=(
                        "preferred_provider_healthy_for_workload"
                        if index == 0
                        else "preferred_provider_unavailable_secondary_healthy_for_workload"
                    ),
                    fallback_used=index > 0,
                    health_checked_at=datetime.now(UTC),
                    health_checks=tuple(checks),
                )
                break
            if selected is None:
                raise WorkloadProviderUnavailableError(workload, tuple(checks))
            bindings[workload] = selected

        self._binding_map = RunProviderBindingV1(
            policy_id=self._policy_id,
            bindings=bindings,
            finalized_at=datetime.now(UTC),
        )
        return self._binding_map
