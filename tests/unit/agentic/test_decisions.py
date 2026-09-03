import pytest
from pydantic import ValidationError

from src.agentic.decisions import (
    ResearchLeadReplanDecider,
    SelfCorrectionAction,
    SelfCorrectionDecision,
)
from src.domain.decision import StructuredAgentDecision
from src.domain.enums import ReplanDecision
from src.domain.task import ReplanRequest


def _structured_decision(task_id: str | None = "TASK-1") -> StructuredAgentDecision:
    return StructuredAgentDecision(
        decision_id="DECISION-1",
        run_id="RUN-1",
        task_id=task_id,
        decision_type="SELF_CORRECTION",
        reason_code="TRANSIENT_TOOL_FAILURE",
        summary="Retry the task-scoped tool call with the same accepted evidence.",
        requires_review=False,
    )


def _request() -> ReplanRequest:
    return ReplanRequest(
        replan_id="REPLAN-1",
        run_id="RUN-1",
        requesting_task_id="TASK-1",
        requested_by="fundamental_analyst",
        reason_code="MISSING_EVIDENCE_TASK",
        reason_detail="The confirmed scheme requires evidence not covered by the initial source.",
        proposed_graph_change={"add_task_type": "supplemental_evidence_collection"},
    )


def test_self_correction_is_a_structured_task_local_decision() -> None:
    correction = SelfCorrectionDecision(
        action=SelfCorrectionAction.RETRY_TOOL,
        decision=_structured_decision(),
        next_attempt=2,
    )

    assert correction.decision.task_id == "TASK-1"
    assert correction.action is SelfCorrectionAction.RETRY_TOOL


def test_self_correction_requires_task_and_positive_attempt() -> None:
    with pytest.raises(ValidationError, match="reference a task"):
        SelfCorrectionDecision(
            action=SelfCorrectionAction.RETRY_TOOL,
            decision=_structured_decision(task_id=None),
            next_attempt=1,
        )
    with pytest.raises(ValidationError, match="positive"):
        SelfCorrectionDecision(
            action=SelfCorrectionAction.RETRY_TOOL,
            decision=_structured_decision(),
            next_attempt=0,
        )


@pytest.mark.parametrize("outcome", [ReplanDecision.APPROVED, ReplanDecision.REJECTED])
def test_only_research_lead_decider_resolves_replan_without_applying_graph_change(
    outcome: ReplanDecision,
) -> None:
    original = _request()
    result = ResearchLeadReplanDecider().decide(
        original,
        outcome=outcome,
        decision_id=f"DECISION-{outcome.value}",
        reason_code="LEAD_REVIEW_COMPLETE",
        summary=f"Research Lead {outcome.value.lower()} the proposed graph change.",
    )

    assert original.decision is ReplanDecision.PENDING
    assert original.decided_by is None
    assert result.request.decision is outcome
    assert result.request.decided_by == "research_lead"
    assert result.request.proposed_graph_change == original.proposed_graph_change
    assert result.request.created_task_ids == []
    assert result.decision.decision_type == f"REPLAN_{outcome.value}"
    assert result.decision.summary


def test_replan_decider_rejects_pending_outcome_and_already_decided_request() -> None:
    decider = ResearchLeadReplanDecider()
    request = _request()

    with pytest.raises(ValueError, match="approve or reject"):
        decider.decide(
            request,
            outcome=ReplanDecision.PENDING,
            decision_id="DECISION-PENDING",
            reason_code="NO_DECISION",
            summary="No decision.",
        )

    request.decision = ReplanDecision.REJECTED
    with pytest.raises(ValueError, match="only pending"):
        decider.decide(
            request,
            outcome=ReplanDecision.APPROVED,
            decision_id="DECISION-RETRY",
            reason_code="RETRY",
            summary="Invalid repeated decision.",
        )
