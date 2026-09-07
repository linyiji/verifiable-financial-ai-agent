from __future__ import annotations

from pydantic import Field, model_validator

from src.domain.base import JsonObject, TimestampedModel
from src.domain.enums import (
    EvidenceAcquisitionStatus,
    ReplanDecision,
    TaskOrigin,
    TaskStatus,
)


class Task(TimestampedModel):
    task_id: str
    run_id: str
    parent_task_id: str | None = None
    task_type: str
    goal: str
    assigned_agent: str = Field(description="Canonical runtime Agent ID, not a display name")
    skill_id: str
    dependencies: list[str] = Field(default_factory=list)
    origin: TaskOrigin = TaskOrigin.PLAN
    reason_code: str | None = None
    status: TaskStatus = TaskStatus.CREATED
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    attempt_count: int = Field(default=0, ge=0)
    result_ref: str | None = None
    task_input_evidence_ids: list[str] = Field(default_factory=list)
    task_output_evidence_ids: list[str] = Field(default_factory=list)
    evidence_acquisition_status: EvidenceAcquisitionStatus | None = None
    evidence_source_coverage: JsonObject = Field(default_factory=dict)


class PlannedTaskGraph(TimestampedModel):
    graph_id: str
    run_id: str
    version: int = Field(default=1, ge=1)
    tasks: list[Task]

    @model_validator(mode="after")
    def dependencies_reference_known_tasks(self) -> PlannedTaskGraph:
        ids = {task.task_id for task in self.tasks}
        if len(ids) != len(self.tasks):
            raise ValueError("task ids must be unique")
        unknown = {
            dependency
            for task in self.tasks
            for dependency in task.dependencies
            if dependency not in ids
        }
        if unknown:
            raise ValueError(f"unknown task dependencies: {sorted(unknown)}")
        return self


class ActualRuntimeGraph(PlannedTaskGraph):
    mutation_history: list[JsonObject] = Field(default_factory=list)


class ReplanRequest(TimestampedModel):
    replan_id: str
    run_id: str
    requesting_task_id: str
    requested_by: str
    reason_code: str
    reason_detail: str
    proposed_graph_change: JsonObject
    decision: ReplanDecision = ReplanDecision.PENDING
    decided_by: str | None = None
    created_task_ids: list[str] = Field(default_factory=list)
