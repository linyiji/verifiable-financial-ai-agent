"""Versioned, secret-free Owner policy. Registration is never an authorization grant.

The descriptor is the source for governed runtime candidates/grants/default budgets.
Independent planning/data descriptors validate their separate contracts; they do not
borrow Specialist authority. Explicit constructor overrides must be frozen by V1
admission, including their source, and never rewrite a historical policy snapshot.
"""

import hashlib
import json
from types import MappingProxyType
from typing import Literal

from pydantic import model_validator

from src.domain.recovery import Frozen, RecoveryBudget, RouteId

OWNER_POLICY_VERSION = "recoverable-owner-policy/v1"
MODEL_POLICY_VERSION = "bounded-model-execution/v1"


class DynamicGrant(Frozen):
    requested_route: RouteId
    actual_routes: tuple[RouteId, ...]


class OwnerTaskPolicy(Frozen):
    version: Literal["recoverable-owner-policy/v1"] = OWNER_POLICY_VERSION
    task_profile: str
    kind: Literal["SPECIALIST", "GENERATED", "NATIVE_DATA"]
    candidates: tuple[RouteId, ...] = ()
    preferred_route: RouteId | None = None
    dynamic_grants: tuple[DynamicGrant, ...] = ()
    cross_provider_allowed: bool = False
    recovery_budget: RecoveryBudget | None = None
    ordered_route_walk: bool = False
    exact_check_consumption: Literal["SEPARATE_EXECUTION", "CONSUME_ONCE", "NOT_APPLICABLE"]
    substituted_check_consumption: Literal["CONSUME_ONCE", "NOT_APPLICABLE"] = "CONSUME_ONCE"
    outer_deadline_seconds: float | None = None
    budget_source: str = "RecoveryBudget defaults retained by Owner V1"
    preferred_override_source: str = "Settings.specialist_provider_routes; candidate gate applies"
    reason: str

    @model_validator(mode="after")
    def independent_authority(self):
        if self.kind == "NATIVE_DATA":
            if self.candidates or self.dynamic_grants or self.recovery_budget is not None:
                raise ValueError("Native data cannot borrow model authority")
            return self
        if self.preferred_route not in self.candidates or self.recovery_budget is None:
            raise ValueError("Model profile needs an authorized preferred route and budget")
        for grant in self.dynamic_grants:
            if grant.requested_route not in self.candidates:
                raise ValueError("Substitution source must be an authorized candidate")
            for actual in grant.actual_routes:
                if (
                    actual not in self.candidates
                    or actual.split("-")[0] != (grant.requested_route.split("-")[0])
                ):
                    raise ValueError("Substitution cannot expand candidates or cross providers")
        return self

    def effective_budget(self, explicit: RecoveryBudget | None = None) -> RecoveryBudget:
        if self.recovery_budget is None:
            raise ValueError("Native data does not inherit a model execution budget")
        return explicit if explicit is not None else self.recovery_budget

    def physical_call_ceiling(self, explicit: RecoveryBudget | None = None) -> int:
        budget = self.effective_budget(explicit)
        # The ordered walk already applies its execution cap to ALL physical calls.
        return budget.max_total_attempts_per_task + (
            0 if self.ordered_route_walk else budget.max_capability_checks
        )


_STANDARD = ("teamorouter-sol", "teamorouter-luna", "teamorouter-terra", "mimo-direct")
_GENERATED = _STANDARD[:3]
_MIMO_FIRST = ("mimo-direct", "teamorouter-sol", "teamorouter-luna")
_LUNA_TERRA = (
    DynamicGrant(requested_route="teamorouter-luna", actual_routes=("teamorouter-terra",)),
)


def _model_policy(profile, candidates, *, dynamic=False, ordered=False, generated=False):
    return OwnerTaskPolicy(
        task_profile=profile,
        kind="GENERATED" if generated else "SPECIALIST",
        candidates=candidates,
        preferred_route=candidates[0],
        dynamic_grants=_LUNA_TERRA if dynamic else (),
        cross_provider_allowed="mimo-direct" in candidates,
        recovery_budget=(
            RecoveryBudget(
                max_total_attempts_per_task=4, max_model_fallbacks=2, max_capability_checks=3
            )
            if ordered
            else RecoveryBudget()
        ),
        ordered_route_walk=ordered,
        exact_check_consumption="CONSUME_ONCE" if ordered else "SEPARATE_EXECUTION",
        outer_deadline_seconds=180 if generated else None,
        budget_source=(
            "Closure-8/9 explicit 4 physical calls / 3 checks / 300s"
            if ordered
            else "RecoveryBudget defaults retained by Owner V1"
        ),
        preferred_override_source=(
            "GovernedCodeBuilder.initial_route; candidate gate applies"
            if generated
            else "Settings.specialist_provider_routes; candidate gate applies"
        ),
        reason=(
            "Owner retained ordered same-intent recovery exception"
            if ordered
            else "Existing prospective authority; no new model or substitution grant"
        ),
    )


TASK_POLICIES = MappingProxyType(
    {
        policy.task_profile: policy
        for policy in (
            _model_policy("GENERATED_CAPABILITY:gross_margin", _GENERATED, generated=True),
            _model_policy("fundamental_analysis", _STANDARD, dynamic=True),
            _model_policy("valuation_analysis", _STANDARD, dynamic=True),
            _model_policy("risk_analysis", _STANDARD, dynamic=True),
            _model_policy("risk_follow_up", _STANDARD, dynamic=True, ordered=True),
            _model_policy("peer_analysis", _MIMO_FIRST),
            _model_policy("research_news_analysis", _MIMO_FIRST),
            _model_policy("report_synthesis", _STANDARD, ordered=True),
            _model_policy(
                "GENERATED_CAPABILITY:free_cash_flow_margin",
                _GENERATED,
                dynamic=True,
                generated=True,
            ),
            OwnerTaskPolicy(
                task_profile="evidence_collection",
                kind="NATIVE_DATA",
                exact_check_consumption="NOT_APPLICABLE",
                substituted_check_consumption="NOT_APPLICABLE",
                budget_source=(
                    "Explicit finite V1 Intent/Run DATA_REQUEST budget required; no invented cap"
                ),
                preferred_override_source="CapabilityExecutionPolicy + configured native adapters",
                reason="FMP structured evidence and Bocha Web discovery; no model authorization",
            ),
        )
    }
)

TASK_CANDIDATES = {
    key: value.candidates for key, value in TASK_POLICIES.items() if value.candidates
}
DYNAMIC_GRANTS = {
    (key, grant.requested_route): grant.actual_routes
    for key, value in TASK_POLICIES.items()
    for grant in value.dynamic_grants
}


class IndependentCallPolicy(Frozen):
    name: str
    purpose: Literal["PLANNING", "DATA_REQUEST"]
    authority_source: str
    dynamic_substitution_allowed: bool = False
    capability_checks: int = 0
    validation_passes: int | None = None
    per_attempt_seconds: float | None = None
    workload_seconds: float | None = None
    physical_accounting: str


INDEPENDENT_CALL_POLICIES = (
    IndependentCallPolicy(
        name="SCHEME_PLANNER",
        purpose="PLANNING",
        authority_source="configured_incremental_provider exact route; not TASK_CANDIDATES",
        validation_passes=2,
        per_attempt_seconds=90,
        workload_seconds=180,
        physical_accounting="Each HTTP attempt across validation passes; Sol may fallback Luna",
    ),
    IndependentCallPolicy(
        name="LEAD_PLANNER",
        purpose="PLANNING",
        authority_source="configured_incremental_provider exact route; production fail_closed",
        validation_passes=1,
        per_attempt_seconds=90,
        workload_seconds=180,
        physical_accounting="Each HTTP attempt; standalone max_validation_attempts override frozen",
    ),
    IndependentCallPolicy(
        name="FMP",
        purpose="DATA_REQUEST",
        authority_source="CapabilityExecutionPolicy",
        per_attempt_seconds=20,
        physical_accounting=(
            "Every HTTP attempt including bounded transient retry and allowed slot rotation"
        ),
    ),
    IndependentCallPolicy(
        name="BOCHA_WEB",
        purpose="DATA_REQUEST",
        authority_source="CapabilityExecutionPolicy",
        per_attempt_seconds=20,
        physical_accounting=(
            "Every Web Search POST and original-source GET; Bocha AI is out of scope"
        ),
    ),
)

# Shared production adaptive route transport defaults, independently of task deadline.
ADAPTIVE_TRANSPORT_POLICY = MappingProxyType(
    {
        "connect_timeout_seconds": 10.0,
        "read_timeout_seconds": 60.0,
        "write_timeout_seconds": 30.0,
        "pool_timeout_seconds": 10.0,
        "max_attempts": 1,
        "bounded_backoff_seconds": (),
        "per_attempt_deadline_seconds": 90.0,
        "overall_workload_deadline_seconds": 90.0,
    }
)


def effective_recovery_budget(profile: str, explicit: RecoveryBudget | None = None):
    return TASK_POLICIES[profile].effective_budget(explicit)


def effective_policy_snapshot(
    profile: str,
    *,
    budget: RecoveryBudget | None = None,
    preferred_route: RouteId | None = None,
    override_source: str | None = None,
) -> dict:
    """Freeze configuration, not authorization: a snapshot never grants more scope.

    The V1 admission layer separately validates any explicit Owner authorization
    and total Intent/Run ceiling. A constructor override alone is not that grant.
    """
    policy = TASK_POLICIES[profile]
    if (budget is not None or preferred_route is not None) and not override_source:
        raise ValueError("Explicit overrides require a retained source")
    if preferred_route is not None and preferred_route not in policy.candidates:
        raise ValueError("Preferred override is outside prospective candidates")
    payload = policy.model_dump(mode="json")
    if budget is not None:
        payload["recovery_budget"] = policy.effective_budget(budget).model_dump(mode="json")
    if preferred_route is not None:
        payload["preferred_route"] = preferred_route
    payload["effective_override_source"] = override_source
    payload["physical_call_ceiling"] = (
        policy.physical_call_ceiling(budget) if policy.recovery_budget is not None else None
    )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {"policy": payload, "sha256": "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()}


def policy_parity_payload() -> dict:
    """Canonical safe matrix suitable for offline parity artifacts, never runtime evidence."""
    return {
        "policy_version": OWNER_POLICY_VERSION,
        "profiles": [policy.model_dump(mode="json") for policy in TASK_POLICIES.values()],
        "independent_calls": [
            policy.model_dump(mode="json") for policy in INDEPENDENT_CALL_POLICIES
        ],
        "adaptive_transport": dict(ADAPTIVE_TRANSPORT_POLICY),
        "unknown_cost": None,
        "run_intent_total_budget": "EXPLICIT_REQUIRED_FOR_V1_ADMISSION",
        "incremental_planning": "Telemetry alias of Scheme/Graph, not a third execution",
        "quality_review": "DECLARED_NOT_EXECUTABLE",
    }


def render_policy_table() -> str:
    """Identical machine-generated block embedded in both language documents."""
    lines = [
        "| TaskProfile | Preferred | Candidates | Dynamic grants | Cross-provider | "
        "Execution/check/physical | Check | Outer seconds |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for profile, policy in TASK_POLICIES.items():
        budget = policy.recovery_budget
        counts = (
            f"{budget.max_total_attempts_per_task}/{budget.max_capability_checks}/"
            f"{policy.physical_call_ceiling()}"
            if budget
            else "N/A"
        )
        grants = (
            ", ".join(
                f"{g.requested_route}→{'/'.join(g.actual_routes)}" for g in policy.dynamic_grants
            )
            or "NONE"
        )
        lines.append(
            f"| {profile} | {policy.preferred_route or 'NATIVE_DATA'} | "
            f"{', '.join(policy.candidates) or 'NONE'} | {grants} | "
            f"{'YES' if policy.cross_provider_allowed else 'NO'} | {counts} | "
            f"{policy.exact_check_consumption} | {policy.outer_deadline_seconds or 'N/A'} |"
        )
    return "\n".join(lines)
