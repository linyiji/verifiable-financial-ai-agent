"""Structured correction and Research Lead replan decisions."""

from enum import StrEnum

from pydantic import model_validator

from src.domain.base import DomainModel
from src.domain.decision import StructuredAgentDecision
from src.domain.enums import ReplanDecision
from src.domain.task import ReplanRequest


class SelfCorrectionAction(StrEnum):
    RETRY_TOOL = "RETRY_TOOL"
    CHANGE_EVIDENCE = "CHANGE_EVIDENCE"
    ADJUST_PARAMETERS = "ADJUST_PARAMETERS"
    ADJUST_OUTPUT_FORMAT = "ADJUST_OUTPUT_FORMAT"
    CHANGE_CAPABILITY = "CHANGE_CAPABILITY"
    ESCALATE_REPLAN_REQUEST = "ESCALATE_REPLAN_REQUEST"


class SelfCorrectionDecision(DomainModel):
    """A task-local correction choice; it cannot add a top-level task."""

    action: SelfCorrectionAction
    decision: StructuredAgentDecision
    next_attempt: int

    @model_validator(mode="after")
    def validate_task_local_decision(self) -> "SelfCorrectionDecision":
        if self.decision.task_id is None:
            raise ValueError("self-correction decisions must reference a task")
        if self.next_attempt < 1:
            raise ValueError("next_attempt must be positive")
        return self


class LeadReplanDecision(DomainModel):
    """Reviewed request; graph mutation remains the Graph Engine's responsibility."""

    request: ReplanRequest
    decision: StructuredAgentDecision

    @model_validator(mode="after")
    def validate_lead_decision(self) -> "LeadReplanDecision":
        if self.request.decision is ReplanDecision.PENDING:
            raise ValueError("a lead replan decision cannot remain pending")
        if self.request.decided_by is None:
            raise ValueError("a decided replan request must name the Research Lead")
        if self.decision.run_id != self.request.run_id:
            raise ValueError("structured decision and request must reference the same run")
        if self.decision.task_id != self.request.requesting_task_id:
            raise ValueError("structured decision and request must reference the same task")
        return self


class ResearchLeadReplanDecider:
    """The only agentic component allowed to approve a proposed graph change."""

    def __init__(self, lead_agent_id: str = "research_lead") -> None:
        self.lead_agent_id = lead_agent_id

    def decide(
        self,
        request: ReplanRequest,
        *,
        outcome: ReplanDecision,
        decision_id: str,
        reason_code: str,
        summary: str,
    ) -> LeadReplanDecision:
        if request.decision is not ReplanDecision.PENDING:
            raise ValueError("only pending replan requests can be decided")
        if request.decided_by is not None or request.created_task_ids:
            raise ValueError("pending replan request contains unauthorized mutation state")
        if outcome is ReplanDecision.PENDING:
            raise ValueError("Research Lead must approve or reject the request")

        reviewed_request = request.model_copy(
            update={"decision": outcome, "decided_by": self.lead_agent_id}
        )
        structured = StructuredAgentDecision(
            decision_id=decision_id,
            run_id=request.run_id,
            task_id=request.requesting_task_id,
            decision_type=f"REPLAN_{outcome.value}",
            reason_code=reason_code,
            summary=summary,
            requires_review=False,
        )
        return LeadReplanDecision(request=reviewed_request, decision=structured)
