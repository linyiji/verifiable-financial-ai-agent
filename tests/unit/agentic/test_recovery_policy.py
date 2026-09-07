import pytest

from src.adapters.llm.provider import LLMFailureClassification as Code
from src.adapters.llm.provider import LLMProviderError
from src.agentic.recovery_policy import classify, policy_allows
from src.domain.recovery import (
    Action,
    Candidate,
    Capability,
    FailureAssessment,
    FailureClass,
    RecoveryBudget,
    RecoveryContext,
    RecoveryDecision,
    Scope,
)


def scope():
    return Scope(
        run_id="RUN-test",
        task_id="RUN-test:fundamentals",
        object_id="OBJ-test",
        scheme_id="SCHEME-test",
        agent_id="fundamental_analyst",
        task_profile="fundamental_analysis",
        context_hash="sha256:" + "a" * 64,
        contract_hash="sha256:" + "b" * 64,
    )


def context(capability=Capability.VERIFIED):
    return RecoveryContext(
        scope=scope(),
        failure=FailureAssessment(
            failure_class=FailureClass.READ_TIMEOUT, failure_stage="PROVIDER", recoverable=True
        ),
        current_route="teamorouter-sol",
        candidates=(
            Candidate(
                route="teamorouter-sol",
                provider="teamorouter",
                model="gpt-5.6-sol",
                authority_exists=True,
                exhausted=True,
            ),
            Candidate(
                route="mimo-direct",
                provider="mimo",
                model="mimo-v2.5",
                authority_exists=True,
                capability=capability,
                eligible=capability == Capability.VERIFIED,
            ),
        ),
        attempt_history=("teamorouter-sol",),
        remaining_attempts=2,
        remaining_checks=1,
        remaining_decisions=4,
        remaining_seconds=100,
    )


@pytest.mark.parametrize(
    "code,expected",
    [
        (Code.READ_TIMEOUT, True),
        (Code.PROVIDER_UNAVAILABLE, True),
        (Code.REMOTE_PROTOCOL_ERROR, True),
        (Code.QUOTA_OR_RATE_LIMIT, True),
        (Code.RETRYABLE_HTTP_FAILURE, True),
        (Code.SEMANTIC_SCHEMA_FAILURE, False),
        (Code.AUTHENTICATION_FAILURE, False),
    ],
)
def test_classifier_uses_owned_classification(code, expected):
    assert classify(LLMProviderError("secret", failure_classification=code)).recoverable is expected


def test_generic_error_is_not_provider_recovery():
    assert not classify(ValueError("read timeout pretend")).recoverable


@pytest.mark.parametrize(
    "capability", [Capability.UNKNOWN, Capability.UNSUPPORTED, Capability.QUARANTINED]
)
def test_unknown_or_bad_capability_cannot_switch(capability):
    ctx = context(capability)
    d = RecoveryDecision(
        scope=ctx.scope,
        action=Action.SWITCH_PROVIDER,
        target_route="mimo-direct",
        reason_code="NEXT_GOVERNED_ROUTE",
    )
    assert not policy_allows(d, ctx, RecoveryBudget(), model_switches=0, provider_switches=0)


def test_unknown_capability_can_only_be_checked():
    ctx = context(Capability.UNKNOWN)
    d = RecoveryDecision(
        scope=ctx.scope,
        action=Action.CAPABILITY_CHECK,
        target_route="mimo-direct",
        reason_code="CAPABILITY_REQUIRED",
    )
    assert policy_allows(d, ctx, RecoveryBudget(), model_switches=0, provider_switches=0)
    assert not policy_allows(
        d,
        ctx.model_copy(update={"remaining_checks": 0}),
        RecoveryBudget(),
        model_switches=0,
        provider_switches=0,
    )


@pytest.mark.parametrize(
    "change", [{"remaining_attempts": 0}, {"remaining_decisions": 0}, {"remaining_seconds": 0}]
)
def test_hard_budget(change):
    ctx = context().model_copy(update=change)
    d = RecoveryDecision(
        scope=ctx.scope,
        action=Action.SWITCH_PROVIDER,
        target_route="mimo-direct",
        reason_code="NEXT_GOVERNED_ROUTE",
    )
    assert not policy_allows(d, ctx, RecoveryBudget(), model_switches=0, provider_switches=0)


def test_identity_and_switch_cost_authority():
    ctx = context()
    d = RecoveryDecision(
        scope=ctx.scope,
        action=Action.SWITCH_PROVIDER,
        target_route="mimo-direct",
        reason_code="NEXT_GOVERNED_ROUTE",
    )
    assert policy_allows(d, ctx, RecoveryBudget(), model_switches=0, provider_switches=0)
    assert not policy_allows(d, ctx, RecoveryBudget(), model_switches=0, provider_switches=1)
    assert not policy_allows(
        d, ctx, RecoveryBudget(max_total_recovery_cost=1), model_switches=0, provider_switches=0
    )
    assert not policy_allows(
        d.model_copy(update={"scope": ctx.scope.model_copy(update={"object_id": "OBJ-other"})}),
        ctx,
        RecoveryBudget(),
        model_switches=0,
        provider_switches=0,
    )


def test_registered_name_cannot_impersonate_another_provider():
    with pytest.raises(ValueError):
        Candidate(
            route="teamorouter-sol", provider="mimo", model="mimo-v2.5", authority_exists=True
        )


def test_unavailable_route_cannot_be_checked_even_by_supervisor():
    from src.domain.recovery import Health

    ctx = context(Capability.UNKNOWN)
    ctx = ctx.model_copy(
        update={
            "candidates": (
                ctx.candidates[0],
                ctx.candidates[1].model_copy(update={"health": Health.UNAVAILABLE}),
            )
        }
    )
    decision = RecoveryDecision(
        scope=ctx.scope,
        action=Action.CAPABILITY_CHECK,
        target_route="mimo-direct",
        reason_code="CAPABILITY_REQUIRED",
    )
    assert not policy_allows(decision, ctx, RecoveryBudget(), model_switches=0, provider_switches=0)


def test_research_failure_plane_is_not_infrastructure():
    assert (
        classify(ValueError("evidence conflict"), stage="RESEARCH").failure_class
        == FailureClass.RESEARCH_SEMANTIC_FAILURE
    )
    assert not classify(ValueError("identity"), stage="IDENTITY").recoverable
