from datetime import datetime
from enum import StrEnum

from pydantic import Field

from src.domain.base import DomainModel, JsonObject, utc_now


class RuntimeEventType(StrEnum):
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_STATUS_CHANGED = "run.status_changed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    SCHEME_GENERATION_STARTED = "scheme.generation_started"
    SCHEME_GENERATED = "scheme.generated"
    SCHEME_CONFIRMED = "scheme.confirmed"
    PLAN_GENERATED = "plan.generated"
    TASK_CREATED = "task.created"
    TASK_READY = "task.ready"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_SELF_CORRECTING = "task.self_correcting"
    TASK_CORRECTION_RESOLVED = "task.correction_resolved"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    REPLAN_REQUESTED = "replan.requested"
    REPLAN_APPROVED = "replan.approved"
    REPLAN_REJECTED = "replan.rejected"
    GRAPH_TASK_ADDED = "graph.task_added"
    GRAPH_EDGE_ADDED = "graph.edge_added"
    GRAPH_EDGE_REMOVED = "graph.edge_removed"
    GRAPH_VERSION_CHANGED = "graph.version_changed"
    EVIDENCE_ACCEPTED = "evidence.accepted"
    EVIDENCE_CONFLICT = "evidence.conflict"
    CALCULATION_STARTED = "calculation.started"
    CALCULATION_COMPLETED = "calculation.completed"
    CAPABILITY_GAP_DETECTED = "capability.gap_detected"
    WORKSPACE_CREATED = "workspace.created"
    CAPABILITY_GENERATION_STARTED = "capability.generation_started"
    CAPABILITY_TESTED = "capability.tested"
    CAPABILITY_VALIDATED = "capability.validated"
    REVIEW_STARTED = "review.started"
    REVIEW_REQUIRED = "review.required"
    REVIEW_RESOLVED = "review.resolved"
    PROOF_STARTED = "proof.started"
    PROOF_VERIFIED = "proof.verified"
    RELEASE_COMPLETED = "release.completed"


class RuntimeEvent(DomainModel):
    event_id: str
    run_id: str
    task_id: str | None = None
    type: RuntimeEventType
    timestamp: datetime = Field(default_factory=utc_now)
    sequence: int = Field(ge=1)
    payload: JsonObject = Field(default_factory=dict)
