"""Deterministic classification, finite detection, Lead proposal and independent gate."""

from collections import Counter

from src.adapters.llm.provider import LLMFailureClassification as Code
from src.adapters.llm.provider import LLMProviderError
from src.domain.recovery import (
    Action,
    Candidate,
    Capability,
    FailureAssessment,
    Health,
    RecoveryContext,
    RecoveryDecision,
)
from src.domain.recovery import (
    FailureClass as Failure,
)


def classify(exc, *, stage=None):
    if stage == "RESEARCH":
        return FailureAssessment(
            failure_class=Failure.RESEARCH_SEMANTIC_FAILURE,
            failure_stage="RESEARCH",
            recoverable=False,
        )
    if stage in {"IDENTITY", "RUNTIME"}:
        return FailureAssessment(
            failure_class=Failure.NON_RECOVERABLE_RUNTIME_FAILURE,
            failure_stage=stage,
            recoverable=False,
        )
    mapping = {
        Code.READ_TIMEOUT: Failure.READ_TIMEOUT,
        Code.CONNECT_TIMEOUT: Failure.PROVIDER_UNAVAILABLE,
        Code.PROVIDER_UNAVAILABLE: Failure.PROVIDER_UNAVAILABLE,
        Code.REMOTE_PROTOCOL_ERROR: Failure.REMOTE_PROTOCOL_ERROR,
        Code.QUOTA_OR_RATE_LIMIT: Failure.RATE_LIMIT,
        # Adapter folds HTTP 408 together with 5xx; do not invent a precise 5xx.
        Code.RETRYABLE_HTTP_FAILURE: Failure.PROVIDER_UNAVAILABLE,
    }
    if isinstance(exc, LLMProviderError):
        code = exc.failure_classification
        if code in mapping:
            return FailureAssessment(
                failure_class=mapping[code], failure_stage="PROVIDER", recoverable=True
            )
        if code in {Code.INVALID_PROVIDER_RESPONSE, Code.SEMANTIC_SCHEMA_FAILURE}:
            return FailureAssessment(
                failure_class=Failure.OUTPUT_CONTRACT_FAILURE,
                failure_stage="OUTPUT",
                recoverable=False,
            )
        return FailureAssessment(
            failure_class=Failure.NON_RECOVERABLE_RUNTIME_FAILURE,
            failure_stage="RUNTIME",
            recoverable=False,
        )
    return FailureAssessment(
        failure_class=Failure.UNKNOWN, failure_stage="RUNTIME", recoverable=False
    )


class ProviderDetector:
    """Registry resolution, never discovery or network I/O."""

    def __init__(self, routes):
        if len(routes) > 3 or any(key != route.route for key, route in routes.items()):
            raise ValueError("Invalid governed registry")
        self.routes = dict(routes)

    def candidates(self, capabilities, history, budget, health=None, evidence=None):
        counts = Counter(history)
        result = []
        for key, route in self.routes.items():
            capability = capabilities.get(key, Capability.UNKNOWN)
            exhausted = counts[key] >= budget.max_same_route_attempts
            available = (
                route.authority_exists
                and not exhausted
                and (health or {}).get(key) != Health.UNAVAILABLE
            )
            eligible = available and capability == Capability.VERIFIED
            result.append(
                Candidate(
                    **route.model_dump(
                        exclude={
                            "health",
                            "capability",
                            "exhausted",
                            "eligible",
                            "next_allowed_action",
                            "capability_evidence_refs",
                        }
                    ),
                    capability_evidence_refs=(evidence or {}).get(key, ()),
                    health=(health or {}).get(key, Health.UNKNOWN),
                    capability=capability,
                    exhausted=exhausted,
                    eligible=eligible,
                    next_allowed_action=Action.SWITCH_PROVIDER
                    if eligible
                    else Action.CAPABILITY_CHECK
                    if available and capability in {Capability.UNKNOWN, Capability.CANDIDATE}
                    else Action.FAIL_TASK,
                )
            )
        return tuple(result)


class ResearchLeadRecoverySupervisor:
    """Deterministic Lead policy, matching the existing replan-decider pattern.

    No ranking/learning. Fixed registered order, known capability before unknown.
    An alternative supervisor may propose decisions, never execute them.
    """

    def decide(self, context: RecoveryContext):
        def decision(action, reason, route=None):
            return RecoveryDecision(
                scope=context.scope,
                action=action,
                target_route=route,
                reason_code=reason,
                evidence_refs=context.evidence_refs,
            )

        if not context.failure.recoverable:
            return decision(Action.FAIL_TASK, "NONRECOVERABLE")
        if (
            context.remaining_attempts <= 0
            or context.remaining_decisions <= 0
            or context.remaining_seconds <= 0
        ):
            return decision(Action.FAIL_TASK, "BUDGET_EXHAUSTED")
        current = next(c for c in context.candidates if c.route == context.current_route)
        for candidate in context.candidates:
            if candidate.eligible:
                action = (
                    Action.RETRY_SAME_ROUTE
                    if candidate.route == current.route
                    else (
                        Action.SWITCH_MODEL
                        if candidate.provider == current.provider
                        else Action.SWITCH_PROVIDER
                    )
                )
                return decision(action, "NEXT_GOVERNED_ROUTE", candidate.route)
        if context.remaining_checks > 0:
            for candidate in context.candidates:
                if candidate.next_allowed_action == Action.CAPABILITY_CHECK:
                    return decision(Action.CAPABILITY_CHECK, "CAPABILITY_REQUIRED", candidate.route)
        return decision(Action.FAIL_TASK, "NO_ALLOWED_ROUTE")


def policy_allows(decision, context, budget, *, model_switches, provider_switches, cost=None):
    if decision.scope != context.scope or not set(decision.evidence_refs).issubset(
        context.evidence_refs
    ):
        return False
    if decision.action in {Action.FAIL_TASK, Action.FAIL_RUN}:
        return True
    if (
        not context.failure.recoverable
        or context.remaining_attempts <= 0
        or context.remaining_decisions <= 0
        or context.remaining_seconds <= 0
    ):
        return False
    if budget.max_total_recovery_cost is not None and (
        cost is None or cost >= budget.max_total_recovery_cost
    ):
        return False
    candidate = next((c for c in context.candidates if c.route == decision.target_route), None)
    current = next((c for c in context.candidates if c.route == context.current_route), None)
    if (
        candidate is None
        or current is None
        or not candidate.authority_exists
        or candidate.exhausted
        or candidate.health == Health.UNAVAILABLE
    ):
        return False
    if decision.action == Action.CAPABILITY_CHECK:
        return (
            context.remaining_checks > 0
            and candidate.capability in {Capability.UNKNOWN, Capability.CANDIDATE}
            and provider_switches < budget.max_cross_provider_switches
        )
    if not candidate.eligible or candidate.capability != Capability.VERIFIED:
        return False
    if decision.action == Action.RETRY_SAME_ROUTE:
        return candidate.route == current.route
    if decision.action == Action.SWITCH_MODEL:
        return (
            candidate.route != current.route
            and candidate.provider == current.provider
            and model_switches < budget.max_model_fallbacks
        )
    if decision.action == Action.SWITCH_PROVIDER:
        return (
            candidate.provider != current.provider
            and provider_switches < budget.max_cross_provider_switches
        )
    # Semantic replan/correction and waits are represented but not executed here.
    return False
