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
    TASK_WAITING_FOR_CAPABILITY = "task.waiting_for_capability"
    TASK_RESUMED = "task.resumed"
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
    CAPABILITY_BUILD_REQUESTED = "capability.build_requested"
    CAPABILITY_BUILD_STARTED = "capability.build_started"
    CAPABILITY_GENERATED = "capability.generated"
    CAPABILITY_STATIC_VALIDATED = "capability.static_validated"
    CAPABILITY_SANDBOX_STARTED = "capability.sandbox_started"
    CAPABILITY_TEST_PASSED = "capability.test_passed"
    CAPABILITY_TEST_FAILED = "capability.test_failed"
    CAPABILITY_FINANCIAL_VALIDATED = "capability.financial_validated"
    CAPABILITY_APPROVED = "capability.approved"
    CAPABILITY_REGISTERED = "capability.registered"
    CAPABILITY_BUILD_FAILED = "capability.build_failed"
    WORKSPACE_CREATED = "workspace.created"
    CAPABILITY_GENERATION_STARTED = "capability.generation_started"
    CAPABILITY_TESTED = "capability.tested"
    CAPABILITY_VALIDATED = "capability.validated"
    REVIEW_STARTED = "review.started"
    REVIEW_REQUIRED = "review.required"
    REVIEW_RESOLVED = "review.resolved"
    PROOF_STARTED = "proof.started"
    PROOF_REQUIRED = "proof.required"
    PROOF_GENERATED = "proof.generated"
    PROOF_VERIFIED = "proof.verified"
    PROOF_FAILED = "proof.failed"
    RELEASE_COMPLETED = "release.completed"


class RuntimeEvent(DomainModel):
    event_id: str
    run_id: str
    task_id: str | None = None
    type: RuntimeEventType
    timestamp: datetime = Field(default_factory=utc_now)
    sequence: int = Field(ge=1)
    payload: JsonObject = Field(default_factory=dict)
