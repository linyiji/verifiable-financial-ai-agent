"""Specialist agent boundary without graph mutation authority."""

from typing import Protocol, runtime_checkable

from pydantic import Field, model_validator

from src.domain.base import DomainModel, JsonObject
from src.domain.decision import StructuredAgentDecision
from src.domain.enums import ReplanDecision
from src.domain.task import ReplanRequest, Task


class SpecialistExecutionContext(DomainModel):
    """Task-scoped input; graph state is intentionally not exposed."""

    task: Task
    accepted_evidence_ids: list[str] = Field(default_factory=list)
    inputs: JsonObject = Field(default_factory=dict)


class SpecialistResult(DomainModel):
    output: JsonObject = Field(default_factory=dict)
    decision: StructuredAgentDecision
    replan_request: ReplanRequest | None = None

    @model_validator(mode="after")
    def request_must_match_decision_task(self) -> "SpecialistResult":
        if self.replan_request is not None:
            if self.decision.task_id != self.replan_request.requesting_task_id:
                raise ValueError("replan request and decision must reference the same task")
            if self.decision.run_id != self.replan_request.run_id:
                raise ValueError("replan request and decision must reference the same run")
            if self.replan_request.decision is not ReplanDecision.PENDING:
                raise ValueError("specialists can only submit pending replan requests")
            if self.replan_request.decided_by is not None:
                raise ValueError("specialists cannot decide replan requests")
            if self.replan_request.created_task_ids:
                raise ValueError("specialists cannot create graph tasks")
        return self


@runtime_checkable
class SpecialistAgent(Protocol):
    agent_id: str
    supported_task_types: frozenset[str]

    async def execute(self, context: SpecialistExecutionContext) -> SpecialistResult: ...
