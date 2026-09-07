"""Frozen Phase 4 product-facing wire contracts.

The models in this module are intentionally independent from FastAPI and from the
Phase 3 mutable runtime.  They describe only the reviewed, safe product surface;
internal persistence locators and provider payloads have no representation here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_serializer,
    field_validator,
    model_validator,
)

from src.domain.incremental import IncrementalResearchContext

PHASE4_CONTRACT_VERSION = "phase4-core/v1"
PHASE4_EVENT_CONTRACT_VERSION = "phase4-runtime-event/v1"
LOCAL_ACCESS_SCOPE = "LOCAL_SINGLE_USER"
SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"

SafeJsonObject = dict[str, JsonValue]


def _nonblank_wire_text(value: str) -> str:
    if not value.strip():
        raise ValueError("wire text must not be blank")
    return value


NonBlank = Annotated[str, Field(min_length=1), AfterValidator(_nonblank_wire_text)]
Sha256 = Annotated[str, Field(pattern=SHA256_PATTERN)]
RunStatusV1 = Literal[
    "DRAFT",
    "SCHEME_GENERATING",
    "AWAITING_CONFIRMATION",
    "PLANNING",
    "RUNNING",
    "REVIEW",
    "PROVING",
    "RELEASED",
    "FAILED",
    "CANCELLED",
]
RunStageV1 = Literal[
    "PREPARE",
    "CONFIRM",
    "PLANNING",
    "RESEARCH",
    "REVIEW",
    "PROVING",
    "COMPLETE",
    "FAILED",
    "CANCELLED",
]
TaskStatusV1 = Literal[
    "CREATED",
    "WAITING",
    "READY",
    "RUNNING",
    "WAITING_FOR_CAPABILITY",
    "SELF_CORRECTING",
    "BLOCKED",
    "REVIEW",
    "COMPLETED",
    "FAILED",
    "CAPABILITY_BUILD_FAILED",
    "CANCELLED",
]
FinancialUnitV1 = Literal["RATIO", "PERCENT", "CURRENCY", "COUNT", "SHARES", "INDEX", "MULTIPLE"]
FinancialPeriodBasisV1 = Literal["FY", "QUARTER", "TTM", "LTM", "CURRENT", "DAILY"]
FinancialActualityV1 = Literal["UNKNOWN", "ACTUAL", "ESTIMATE"]
ProofStatusProjectionV1 = Literal[
    "NOT_REQUIRED",
    "PENDING",
    "PROVING",
    "GENERATED_UNVERIFIED",
    "VERIFIED",
    "INVALID",
    "ERROR",
    "UNSUPPORTED",
]
TechnicalPriceBasisV1 = Literal["ADJUSTED_CLOSE", "RAW_CLOSE"]
CorporateActionStatusV1 = Literal[
    "NONE_DETECTED",
    "RESOLVED",
    "UNRESOLVED",
    "UNASSESSED",
]


class FrozenWireModel(BaseModel):
    """Closed and immutable public DTO base."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    @model_validator(mode="after")
    def timestamps_are_utc(self) -> FrozenWireModel:
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if isinstance(value, datetime) and (
                value.tzinfo is None or value.utcoffset() != timedelta(0)
            ):
                raise ValueError(f"{field_name} must be an RFC3339 UTC instant")
        return self


class AvailabilityStatus(StrEnum):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    NOT_GENERATED = "NOT_GENERATED"
    NOT_RELEASED = "NOT_RELEASED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class AvailabilityV1(FrozenWireModel):
    status: AvailabilityStatus
    reason_code: str | None
    retryable: bool = False

    @model_validator(mode="after")
    def reason_matches_status(self) -> AvailabilityV1:
        if self.status is AvailabilityStatus.AVAILABLE:
            if self.reason_code is not None:
                raise ValueError("AVAILABLE must not carry a reason_code")
        elif self.reason_code is None or not self.reason_code.strip():
            raise ValueError("non-AVAILABLE status requires a stable reason_code")
        return self

    @classmethod
    def available(cls) -> AvailabilityV1:
        return cls(status=AvailabilityStatus.AVAILABLE, reason_code=None, retryable=False)

    @classmethod
    def unavailable(
        cls,
        status: AvailabilityStatus,
        reason_code: str,
        *,
        retryable: bool = False,
    ) -> AvailabilityV1:
        if status is AvailabilityStatus.AVAILABLE:
            raise ValueError("use AvailabilityV1.available for AVAILABLE")
        return cls(status=status, reason_code=reason_code, retryable=retryable)


class ErrorCodeV1(StrEnum):
    INVALID_CURSOR = "INVALID_CURSOR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_GENERATED = "NOT_GENERATED"
    NOT_RELEASED = "NOT_RELEASED"
    CONFLICT = "CONFLICT"
    CURSOR_AHEAD = "CURSOR_AHEAD"
    SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"
    UNSUPPORTED_EVENT = "UNSUPPORTED_EVENT"
    TERMINAL = "TERMINAL"
    REQUEST_VALIDATION_ERROR = "REQUEST_VALIDATION_ERROR"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    TRANSIENT_BACKEND_ERROR = "TRANSIENT_BACKEND_ERROR"


class RecoveryV1(StrEnum):
    NONE = "NONE"
    RETRY = "RETRY"
    SNAPSHOT_RELOAD = "SNAPSHOT_RELOAD"
    REAUTHENTICATE = "REAUTHENTICATE"


class ErrorResourceV1(FrozenWireModel):
    type: NonBlank
    id: NonBlank


class ErrorBodyV1(FrozenWireModel):
    code: ErrorCodeV1
    message: NonBlank
    retryable: bool
    recovery: RecoveryV1
    request_id: str | None = None
    resource: ErrorResourceV1 | None = None
    details: SafeJsonObject = Field(default_factory=dict)


class ErrorEnvelopeV1(FrozenWireModel):
    schema_version: Literal["phase4-error/v1"] = "phase4-error/v1"
    error: ErrorBodyV1


class PrepareResearchRunRequestV1(FrozenWireModel):
    research_object_id: NonBlank
    research_goal: NonBlank
    as_of: date
    preferences: SafeJsonObject = Field(default_factory=dict)
    base_run_id: NonBlank | None = Field(default=None, exclude_if=lambda v: v is None)
    base_research_view_version: NonBlank | None = Field(
        default=None, exclude_if=lambda v: v is None
    )

    @model_validator(mode="after")
    def paired_base(self):
        if (self.base_run_id is None) != (self.base_research_view_version is None):
            raise ValueError("explicit base Run and view identity must be paired")
        return self


class ConfirmResearchRunRequestV1(FrozenWireModel):
    draft_id: NonBlank
    draft_version: int = Field(ge=1)
    draft_hash: Sha256
    research_object_id: NonBlank
    confirm_scheme: Literal[True]


class CreateResearchObjectRequestV1(FrozenWireModel):
    symbol: NonBlank
    company_name: NonBlank
    exchange: NonBlank
    sector: str | None = None
    currency: NonBlank = "USD"

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        """Apply the existing Object identity normalization before hashing."""

        if isinstance(value, str):
            return value.strip().upper()
        return value


class ObjectIdentityV1(FrozenWireModel):
    object_id: NonBlank
    symbol: NonBlank
    company_name: NonBlank
    object_type: NonBlank = "public_company"
    exchange: NonBlank
    sector: str | None = None
    currency: NonBlank = "USD"
    identity_version: int = Field(default=1, ge=1)


class GoalProjectionV1(FrozenWireModel):
    goal_id: NonBlank
    research_object_id: NonBlank
    goal_type: NonBlank = "comprehensive_equity_research"
    goal_text: NonBlank
    as_of: date
    preferences: SafeJsonObject = Field(default_factory=dict)
    created_at: datetime


class SchemeProjectionV1(FrozenWireModel):
    scheme_id: NonBlank
    research_object_id: NonBlank
    goal_id: NonBlank
    research_scope: tuple[str, ...] = ()
    data_requirements: tuple[str, ...] = ()
    agent_requirements: tuple[str, ...] = ()
    skill_requirements: tuple[str, ...] = ()
    calculation_requirements: tuple[str, ...] = ()
    assurance_requirements: SafeJsonObject = Field(default_factory=dict)
    report_requirements: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    generated_by: NonBlank
    generated_model: str | None = None
    created_at: datetime
    confirmed_at: datetime | None = None
    incremental_context: IncrementalResearchContext | None = Field(
        default=None, exclude_if=lambda v: v is None
    )


class ResearchRunDraftV1(FrozenWireModel):
    schema_version: Literal["phase4-run-draft/v1"] = "phase4-run-draft/v1"
    draft_id: NonBlank
    draft_version: int = Field(default=1, ge=1)
    status: Literal["AWAITING_CONFIRMATION"] = "AWAITING_CONFIRMATION"
    preview_kind: Literal["SCHEME_ONLY"] = "SCHEME_ONLY"
    planned_graph_availability: AvailabilityV1
    object_id: NonBlank
    goal: GoalProjectionV1
    scheme_snapshot: SchemeProjectionV1
    prepare_request_hash: Sha256
    draft_hash: Sha256
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def exact_identity_and_lifecycle(self) -> ResearchRunDraftV1:
        if self.goal.research_object_id != self.object_id:
            raise ValueError("draft goal belongs to another object")
        if self.scheme_snapshot.research_object_id != self.object_id:
            raise ValueError("draft scheme belongs to another object")
        if self.scheme_snapshot.goal_id != self.goal.goal_id:
            raise ValueError("draft scheme belongs to another goal")
        if self.scheme_snapshot.confirmed_at is not None:
            raise ValueError("prepared scheme must not be confirmed")
        expected = AvailabilityV1.unavailable(
            AvailabilityStatus.NOT_GENERATED,
            "PLAN_CREATED_ON_CONFIRM",
        )
        if self.planned_graph_availability != expected:
            raise ValueError("prepare cannot publish a planned graph")
        if self.expires_at <= self.created_at:
            raise ValueError("draft expiry must follow creation")
        return self


class AutoStartV1(FrozenWireModel):
    required: Literal[True] = True
    admitted: Literal[True] = True


class RunAdmissionV1(FrozenWireModel):
    schema_version: Literal["phase4-run-admission/v1"] = "phase4-run-admission/v1"
    admission_id: NonBlank
    run_id: NonBlank
    object_id: NonBlank
    draft_id: NonBlank
    draft_version: int = Field(ge=1)
    draft_hash: Sha256
    goal_id: NonBlank
    scheme_id: NonBlank
    planned_graph_id: NonBlank
    status: Literal["PLANNING"] = "PLANNING"
    auto_start: AutoStartV1 = Field(default_factory=AutoStartV1)
    confirmation_request_hash: Sha256
    admitted_at: datetime
    projection_ref: NonBlank
    events_ref: NonBlank

    @model_validator(mode="after")
    def refs_name_exact_run(self) -> RunAdmissionV1:
        if self.projection_ref != f"/api/research-runs/{self.run_id}/projection":
            raise ValueError("projection_ref must name the admitted run")
        if self.events_ref != f"/api/research-runs/{self.run_id}/events":
            raise ValueError("events_ref must name the admitted run")
        return self


class ResponseMetaV1(FrozenWireModel):
    schema_version: Literal["phase4-response-meta/v1"] = "phase4-response-meta/v1"
    request_id: str | None = None
    idempotency_replayed: bool


class ConfirmRunResponseV1(FrozenWireModel):
    schema_version: Literal["phase4-confirm-response/v1"] = "phase4-confirm-response/v1"
    admission: RunAdmissionV1
    response_meta: ResponseMetaV1


class ResearchObjectDetailV1(FrozenWireModel):
    object: ObjectIdentityV1
    latest_released_run_id: str | None
    released_result_availability: AvailabilityV1
    run_count: int = Field(ge=0)
    last_activity: SafeRuntimeActivityV1 | None = None
    created_at: datetime
    updated_at: datetime


class ResearchObjectCollectionV1(FrozenWireModel):
    items: tuple[ResearchObjectDetailV1, ...]
    next_cursor: str | None = None


class RunProgressV1(FrozenWireModel):
    method: Literal["ACTUAL_TASK_MEAN_V1"] = "ACTUAL_TASK_MEAN_V1"
    completed_tasks: int = Field(ge=0)
    total_tasks: int = Field(ge=0)
    fraction: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> RunProgressV1:
        if self.completed_tasks > self.total_tasks:
            raise ValueError("completed_tasks cannot exceed total_tasks")
        return self


class SafeRuntimeActivityV1(FrozenWireModel):
    event_id: NonBlank
    type: NonBlank
    sequence: int = Field(ge=1)
    timestamp: datetime
    task_id: str | None = None
    message_code: NonBlank
    status: str | None = None
    actor_id: str | None = None
    actor_type: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    calculation_refs: tuple[str, ...] = ()
    claim_refs: tuple[str, ...] = ()
    judgment_refs: tuple[str, ...] = ()
    review_refs: tuple[str, ...] = ()
    proof_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    trace_bundle_refs: tuple[str, ...] = ()


class RunCollectionActivityV1(FrozenWireModel):
    """Frozen compact activity shape used only by Run collection rows."""

    event_id: NonBlank
    type: NonBlank
    sequence: int = Field(ge=1)
    timestamp: datetime
    task_id: str | None = None
    message_code: NonBlank


class RunCollectionObjectV1(FrozenWireModel):
    object_id: NonBlank
    symbol: NonBlank
    company_name: NonBlank


class RunCollectionItemV1(FrozenWireModel):
    run_id: NonBlank
    object: RunCollectionObjectV1
    status: RunStatusV1
    stage: RunStageV1
    progress: RunProgressV1
    activity: RunCollectionActivityV1 | None
    graph_version: int | None = Field(default=None, ge=1)
    projection_revision: int = Field(ge=1)
    projection_sequence: int = Field(ge=0)
    as_of: date
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    terminal: bool
    result_availability: AvailabilityV1


class AvailableRunHistoryItemV1(FrozenWireModel):
    """One history row that satisfies the full frozen Run collection contract."""

    availability: Literal["AVAILABLE"] = "AVAILABLE"
    run: RunCollectionItemV1


class UnavailableIncompatibleRunHistoryItemV1(FrozenWireModel):
    """Identity-preserving history row for a payload that cannot be projected safely.

    This deliberately excludes graph, progress, release, event-watermark, Review,
    Report, proof, and metric claims.  The remaining fields come from the durable
    aggregate columns and its exact Research Object row.
    """

    availability: Literal["UNAVAILABLE_INCOMPATIBLE"] = "UNAVAILABLE_INCOMPATIBLE"
    run_id: NonBlank
    object: RunCollectionObjectV1
    status: RunStatusV1
    updated_at: datetime
    reason_code: Literal["LEGACY_OR_INCOMPATIBLE"] = "LEGACY_OR_INCOMPATIBLE"


RunHistoryItemV1 = AvailableRunHistoryItemV1 | UnavailableIncompatibleRunHistoryItemV1


class ResearchRunHistoryCollectionV1(FrozenWireModel):
    schema_version: Literal["phase4-run-history-collection/v1"] = "phase4-run-history-collection/v1"
    items: tuple[RunHistoryItemV1, ...]
    next_cursor: str | None = None


class ResearchRunCollectionV1(FrozenWireModel):
    schema_version: Literal["phase4-run-collection/v1"] = "phase4-run-collection/v1"
    items: tuple[RunCollectionItemV1, ...]
    next_cursor: str | None = None


class ResearchRunDetailV1(FrozenWireModel):
    reexecution_of_run_id: NonBlank | None = Field(default=None, exclude_if=lambda v: v is None)
    base_run_id: NonBlank | None = Field(default=None, exclude_if=lambda v: v is None)
    base_research_view_version: NonBlank | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    run_id: NonBlank
    research_object_id: NonBlank
    goal_id: NonBlank
    scheme_id: NonBlank
    status: RunStatusV1
    stage: RunStageV1
    as_of: date
    planned_graph_id: str | None
    actual_graph_id: str | None
    execution_target: NonBlank
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    terminal: bool
    projection_revision: int = Field(ge=1)
    projection_sequence: int = Field(ge=0)


class TaskProjectionV1(FrozenWireModel):
    task_id: NonBlank
    run_id: NonBlank
    parent_task_id: str | None = None
    task_type: NonBlank
    goal: NonBlank
    assigned_agent: NonBlank
    skill_id: NonBlank
    dependencies: tuple[str, ...] = ()
    origin: NonBlank
    reason_code: str | None = None
    status: TaskStatusV1
    progress: float = Field(ge=0.0, le=1.0)
    attempt_count: int = Field(ge=0)
    task_input_evidence_ids: tuple[str, ...] = ()
    task_output_evidence_ids: tuple[str, ...] = ()
    evidence_acquisition_status: str | None = None
    evidence_source_coverage: SafeJsonObject = Field(default_factory=dict)
    created_at: datetime


class GraphProjectionV1(FrozenWireModel):
    graph_id: NonBlank
    run_id: NonBlank
    version: int = Field(ge=1)
    tasks: tuple[TaskProjectionV1, ...]


class TypedGraphOperationV1(FrozenWireModel):
    operation: Literal["add_node", "add_edge", "remove_edge"]
    task_id: NonBlank
    dependency_task_id: str | None = None


class PathChangeProjectionV1(FrozenWireModel):
    path_change_id: NonBlank
    source_kind: Literal["CORRECTION", "REPLAN"]
    source_id: NonBlank
    change_kind: Literal["SELF_CORRECTION", "ADD_TASK", "CHANGE_DEPENDENCY"]
    status: NonBlank
    decision: str | None = None
    reason_code: str | None = None
    task_refs: tuple[str, ...] = ()
    operations: tuple[TypedGraphOperationV1, ...] = ()
    graph_version_before: int | None = Field(default=None, ge=1)
    graph_version_after: int | None = Field(default=None, ge=1)
    created_at: datetime
    resolved_at: datetime | None = None


class RunLifecycleV1(FrozenWireModel):
    status: RunStatusV1
    stage: RunStageV1
    progress: RunProgressV1
    terminal: bool
    terminal_outcome: str | None
    safe_failure: SafeJsonObject | None


class ReviewSummaryV1(FrozenWireModel):
    availability: AvailabilityV1
    review_id: NonBlank | None = None
    status: Literal["PASS", "REVIEW", "BLOCK"] | None = None

    @model_validator(mode="after")
    def identity_closes(self) -> ReviewSummaryV1:
        if (self.review_id is None) != (self.status is None):
            raise ValueError("Review summary identity/status must be jointly present")
        available = self.availability.status is AvailabilityStatus.AVAILABLE
        if available != (self.review_id is not None):
            raise ValueError(
                "Review summary identity/status must be present exactly when AVAILABLE"
            )
        return self


class ResultSummaryV1(FrozenWireModel):
    availability: AvailabilityV1
    released_result_id: NonBlank | None = None
    canonical_record_id: NonBlank | None = None
    released_at: datetime | None = None

    @model_validator(mode="after")
    def identity_closes(self) -> ResultSummaryV1:
        present = sum(
            value is not None
            for value in (self.released_result_id, self.canonical_record_id, self.released_at)
        )
        if present not in {0, 3}:
            raise ValueError("Result summary identity/time tuple is partial")
        available = self.availability.status is AvailabilityStatus.AVAILABLE
        if available != (present == 3):
            raise ValueError("Result summary identity/time must be present exactly when AVAILABLE")
        return self


class ArtifactSummaryV1(FrozenWireModel):
    availability: AvailabilityV1
    report_id: NonBlank | None = None
    representation_ids: tuple[NonBlank, ...] = ()

    @model_validator(mode="after")
    def identity_closes(self) -> ArtifactSummaryV1:
        if len(set(self.representation_ids)) != len(self.representation_ids):
            raise ValueError("Artifact summary representation identities must be unique")
        if (self.report_id is None) != (not self.representation_ids):
            raise ValueError("Artifact summary report and representation identities are partial")
        available = self.availability.status is AvailabilityStatus.AVAILABLE
        if available != (self.report_id is not None):
            raise ValueError("Artifact summary identities must be present exactly when AVAILABLE")
        return self


class ExecutionSummaryV1(FrozenWireModel):
    availability: AvailabilityV1
    canonical_record_id: NonBlank | None = None

    @model_validator(mode="after")
    def identity_closes(self) -> ExecutionSummaryV1:
        available = self.availability.status is AvailabilityStatus.AVAILABLE
        if available != (self.canonical_record_id is not None):
            raise ValueError("Execution identity must be present exactly when AVAILABLE")
        return self


class ProofSummaryV1(FrozenWireModel):
    availability: AvailabilityV1
    policy: Literal["NOT_REQUIRED", "MUST_PROVE", "MIXED", "UNKNOWN"]
    status: ProofStatusProjectionV1 | None
    proof_refs: tuple[str, ...] = ()


class TerminalStateV1(FrozenWireModel):
    is_terminal: bool
    outcome: str | None
    event_id: str | None
    sequence: int | None = Field(default=None, ge=1)


class AtomicRunProjectionV1(FrozenWireModel):
    projection_schema_version: Literal["phase4-run-projection/v1"] = "phase4-run-projection/v1"
    projection_revision: int = Field(ge=1)
    projection_sequence: int = Field(ge=0)
    generated_at: datetime
    object: ObjectIdentityV1
    run: ResearchRunDetailV1
    goal: GoalProjectionV1
    confirmed_scheme: SchemeProjectionV1
    planned_graph: GraphProjectionV1
    actual_graph: GraphProjectionV1 | None
    graph_version: int | None = Field(default=None, ge=1)
    tasks: tuple[TaskProjectionV1, ...]
    path_changes: tuple[PathChangeProjectionV1, ...]
    activity: tuple[SafeRuntimeActivityV1, ...]
    lifecycle: RunLifecycleV1
    review: ReviewSummaryV1
    result: ResultSummaryV1
    artifacts: ArtifactSummaryV1
    proof: ProofSummaryV1
    execution: ExecutionSummaryV1
    terminal: TerminalStateV1

    @field_serializer("run")
    def serialize_embedded_run(self, run: ResearchRunDetailV1) -> dict[str, object]:
        """The embedded Run is the frozen 14-field record, not standalone GET Run."""

        return run.model_dump(
            mode="json",
            exclude={"terminal", "projection_revision", "projection_sequence"},
        )

    @model_validator(mode="after")
    def exact_identity(self) -> AtomicRunProjectionV1:
        run_id = self.run.run_id
        object_id = self.object.object_id
        if self.projection_revision != self.run.projection_revision:
            raise ValueError("torn projection revision disagrees with embedded run")
        if self.projection_sequence != self.run.projection_sequence:
            raise ValueError("torn projection sequence disagrees with embedded run")
        if self.run.research_object_id != object_id:
            raise ValueError("run and object identity disagree")
        if self.goal.research_object_id != object_id or self.goal.goal_id != self.run.goal_id:
            raise ValueError("goal identity does not close to run/object")
        if (
            self.confirmed_scheme.research_object_id != object_id
            or self.confirmed_scheme.goal_id != self.run.goal_id
            or self.confirmed_scheme.scheme_id != self.run.scheme_id
            or self.confirmed_scheme.confirmed_at is None
        ):
            raise ValueError("confirmed scheme identity does not close")
        graphs = [self.planned_graph]
        if self.actual_graph is not None:
            graphs.append(self.actual_graph)
        if any(graph.run_id != run_id for graph in graphs):
            raise ValueError("graph belongs to another run")
        if any(task.run_id != run_id for task in self.tasks):
            raise ValueError("task belongs to another run")
        return self


class MethodParameterV1(FrozenWireModel):
    name: NonBlank
    value: NonBlank


class MethodMetadataV1(FrozenWireModel):
    method: NonBlank
    parameters: tuple[MethodParameterV1, ...] = ()
    observation_count: int | None = Field(default=None, ge=1)
    warmup_required: int | None = Field(default=None, ge=1)
    warmup_satisfied: bool | None = None
    first_as_of: date | None = None
    last_as_of: date | None = None
    is_wilder: bool | None = None
    ema_adjust: bool | None = None


class MetricProofProjectionV1(FrozenWireModel):
    policy_id: NonBlank
    requirement: Literal["NOT_REQUIRED", "MUST_PROVE"]
    status: ProofStatusProjectionV1
    proof_refs: tuple[str, ...] = ()


class ReleasedFinancialMetricProjectionV1(FrozenWireModel):
    run_id: NonBlank
    metric_id: NonBlank
    name: NonBlank
    canonical_value: NonBlank
    canonical_unit: FinancialUnitV1
    display_value: NonBlank
    display_unit: NonBlank
    period: NonBlank
    period_basis: FinancialPeriodBasisV1
    actuality: FinancialActualityV1
    as_of: date
    currency: str | None
    formula_id: NonBlank
    capability_id: NonBlank
    calculation_id: NonBlank
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    claim_refs: tuple[str, ...] = Field(min_length=1)
    proof: MetricProofProjectionV1
    method_metadata: MethodMetadataV1 | None = None
    technical_price_basis: TechnicalPriceBasisV1 | None = None
    corporate_action_status: CorporateActionStatusV1 | None = None
    corporate_action_guard_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class TypedReleasedClaimV1(FrozenWireModel):
    claim_id: NonBlank
    run_id: NonBlank
    claim_type: NonBlank
    statement: NonBlank
    metric_id: NonBlank
    value: NonBlank
    unit: FinancialUnitV1
    period: NonBlank
    period_basis: FinancialPeriodBasisV1
    actuality: FinancialActualityV1
    as_of: date
    currency: str | None
    calculation_refs: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    judgment_refs: tuple[str, ...] = ()


class ReleasedResultProjectionV1(FrozenWireModel):
    object_id: NonBlank
    run_id: NonBlank
    released_result_id: NonBlank
    canonical_record_id: NonBlank
    released_at: datetime
    metrics: tuple[ReleasedFinancialMetricProjectionV1, ...]
    claims: tuple[TypedReleasedClaimV1, ...]
    material_calculation_dispositions: tuple[SafeJsonObject, ...]
    research_source_coverage: SafeJsonObject | None
    limitations: tuple[str, ...]
    availability: AvailabilityV1


class ReviewSubjectV1(FrozenWireModel):
    subject_type: Literal[
        "RUN",
        "TASK",
        "EVIDENCE",
        "CALCULATION",
        "METRIC",
        "CLAIM",
        "JUDGMENT",
        "PROOF",
        "CANONICAL_RECORD",
        "RELEASED_RESULT",
    ]
    subject_id: NonBlank
    run_id: NonBlank


class ReviewCorrectionRefV1(FrozenWireModel):
    correction_id: NonBlank
    run_id: NonBlank
    task_id: NonBlank
    relation: Literal["ADDRESSES_CHECK"] = "ADDRESSES_CHECK"
    status: Literal["RESOLVED", "FAILED", "ESCALATED"]
    resolved_at: datetime | None = None


class FinancialReviewCheckProjectionV1(FrozenWireModel):
    check_id: NonBlank
    check_code: NonBlank
    status: Literal["PASS", "REVIEW", "BLOCK"]
    subjects: tuple[ReviewSubjectV1, ...]
    expected: SafeJsonObject
    actual: SafeJsonObject
    detail: str | None = None
    exception_state: Literal["NONE", "OPEN", "RESOLVED"]
    correction_refs: tuple[ReviewCorrectionRefV1, ...] = ()
    created_at: datetime
    resolved_at: datetime | None = None

    @model_validator(mode="after")
    def exception_closure(self) -> FinancialReviewCheckProjectionV1:
        if self.exception_state == "NONE":
            if self.status != "PASS" or self.correction_refs or self.resolved_at is not None:
                raise ValueError("NONE is only a pristine PASS check")
        elif self.exception_state == "OPEN":
            if self.status == "PASS" or self.resolved_at is not None:
                raise ValueError("OPEN is an unresolved REVIEW/BLOCK check")
        else:
            if self.status == "PASS" or not self.correction_refs or self.resolved_at is None:
                raise ValueError(
                    "RESOLVED is only a corrected REVIEW/BLOCK with refs and resolved_at"
                )
        if self.resolved_at is not None and self.resolved_at < self.created_at:
            raise ValueError("Check resolved_at cannot precede created_at")
        return self


class FinancialReviewProjectionV1(FrozenWireModel):
    schema_version: Literal["phase4-financial-review/v1"] = "phase4-financial-review/v1"
    projection_revision: int = Field(ge=1)
    projection_sequence: int = Field(ge=0)
    object_id: NonBlank
    run_id: NonBlank
    canonical_record_id: str | None
    released_result_id: str | None
    review_id: str | None
    status: Literal["PASS", "REVIEW", "BLOCK"] | None
    reviewer: str | None
    input_snapshot_hash: Sha256 | None
    reviewed_evidence_refs: tuple[str, ...] = ()
    reviewed_calculation_refs: tuple[str, ...] = ()
    reviewed_metric_refs: tuple[str, ...] = ()
    reviewed_claim_refs: tuple[str, ...] = ()
    reviewed_judgment_refs: tuple[str, ...] = ()
    required_proof_calculation_refs: tuple[str, ...] = ()
    checks: tuple[FinancialReviewCheckProjectionV1, ...] = ()
    availability: AvailabilityV1

    @model_validator(mode="after")
    def nullable_pairs_and_absence(self) -> FinancialReviewProjectionV1:
        if (self.canonical_record_id is None) != (self.released_result_id is None):
            raise ValueError("canonical/result ids must be both null or both present")
        identity = (self.review_id, self.status, self.reviewer, self.input_snapshot_hash)
        if any(value is None for value in identity) and any(
            value is not None for value in identity
        ):
            raise ValueError("review identity, status and reviewer share nullability")
        absent = self.review_id is None
        absent_arrays = (
            self.reviewed_evidence_refs,
            self.reviewed_calculation_refs,
            self.reviewed_metric_refs,
            self.reviewed_claim_refs,
            self.reviewed_judgment_refs,
            self.required_proof_calculation_refs,
            self.checks,
        )
        if absent and (
            any(absent_arrays) or self.availability.status is AvailabilityStatus.AVAILABLE
        ):
            raise ValueError("absent review requires empty arrays and cannot be AVAILABLE")
        if not absent and self.availability.status is not AvailabilityStatus.AVAILABLE:
            raise ValueError("retained valid review must be AVAILABLE")
        if not absent and not self.checks:
            raise ValueError("retained review requires durable Checks")
        if len({item.check_id for item in self.checks}) != len(self.checks):
            raise ValueError("review check IDs must be unique")
        return self


class ExecutionProjectionV1(FrozenWireModel):
    projection_revision: int = Field(ge=1)
    projection_sequence: int = Field(ge=0)
    object_id: NonBlank
    run_id: NonBlank
    canonical_record_id: NonBlank
    released_result_id: str | None = None
    object_snapshot_ref: NonBlank
    planned_graph: SafeJsonObject
    actual_graph: SafeJsonObject
    task_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    calculation_refs: tuple[str, ...] = ()
    metric_refs: tuple[str, ...] = ()
    claim_refs: tuple[str, ...] = ()
    judgment_refs: tuple[str, ...] = ()
    decision_refs: tuple[str, ...] = ()
    correction_refs: tuple[str, ...] = ()
    replan_refs: tuple[str, ...] = ()
    generated_capability_refs: tuple[str, ...] = ()
    review_refs: tuple[str, ...] = ()
    proof_refs: tuple[str, ...] = ()
    trace_refs: tuple[str, ...] = ()
    token_usage: int = Field(ge=0)
    cost: float = Field(ge=0.0)
    latency_ms: int = Field(ge=0)
    runtime_outcome: NonBlank
    events: tuple[SafeRuntimeActivityV1, ...] = ()
    next_cursor: str | None = None
    availability: AvailabilityV1


class AvailabilityRefV1(FrozenWireModel):
    availability: AvailabilityV1


class TaskAvailabilityRefV1(AvailabilityRefV1):
    task_id: NonBlank


class EvidenceAvailabilityRefV1(AvailabilityRefV1):
    evidence_id: NonBlank


class CalculationAvailabilityRefV1(AvailabilityRefV1):
    calculation_id: NonBlank


class TechnicalIndicatorJudgmentDetailV1(FrozenWireModel):
    schema_version: Literal["phase4-technical-judgment/v1"] = "phase4-technical-judgment/v1"
    judgment_id: NonBlank
    run_id: NonBlank
    task_id: NonBlank
    judgment_type: Literal["rsi_state", "macd_state", "moving_average_state"]
    value: Literal["OVERBOUGHT", "OVERSOLD", "BULLISH", "BEARISH", "NEUTRAL"]
    evidence_refs: tuple[str, ...] = ()
    calculation_refs: tuple[str, ...] = ()
    policy_id: NonBlank
    skill_version: NonBlank
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    limitations: tuple[str, ...] = ()
    requires_review: Literal[True] = True


class JudgmentAvailabilityV1(AvailabilityRefV1):
    judgment_id: NonBlank
    run_id: NonBlank
    detail: TechnicalIndicatorJudgmentDetailV1 | None = None

    @model_validator(mode="after")
    def detail_matches_availability(self) -> JudgmentAvailabilityV1:
        available = self.availability.status is AvailabilityStatus.AVAILABLE
        if available != (self.detail is not None):
            raise ValueError("Judgment detail is present exactly when AVAILABLE")
        if self.detail is not None and (
            self.detail.judgment_id != self.judgment_id or self.detail.run_id != self.run_id
        ):
            raise ValueError("Judgment detail identity mismatch")
        return self


class ReviewAvailabilityRefV1(AvailabilityRefV1):
    review_id: NonBlank
    check_ids: tuple[str, ...] = ()


class ProofTraceRefV1(AvailabilityRefV1):
    proof_id: NonBlank
    calculation_id: NonBlank
    requirement: Literal["NOT_REQUIRED", "MUST_PROVE"]
    status: ProofStatusProjectionV1
    verification_id: str | None = None


class AnchorBaseV1(FrozenWireModel):
    anchor_id: str | None
    anchor_kind: NonBlank
    object_id: NonBlank
    run_id: NonBlank
    claim_id: NonBlank
    availability: AvailabilityV1

    @model_validator(mode="after")
    def id_matches_availability(self) -> AnchorBaseV1:
        if (self.anchor_id is None) == (self.availability.status is AvailabilityStatus.AVAILABLE):
            raise ValueError("anchor_id is required exactly when the anchor is AVAILABLE")
        return self


class RepresentationClaimAnchorV1(AnchorBaseV1):
    metric_id: NonBlank
    report_id: NonBlank
    released_result_id: NonBlank
    canonical_record_id: NonBlank
    format: Literal["HTML", "PDF"]
    artifact_id: str | None

    @model_validator(mode="after")
    def artifact_matches_anchor_availability(self) -> RepresentationClaimAnchorV1:
        available = self.availability.status is AvailabilityStatus.AVAILABLE
        if available != (self.artifact_id is not None):
            raise ValueError("artifact_id is required exactly when the anchor is AVAILABLE")
        return self


class ReviewCheckAnchorV1(AnchorBaseV1):
    review_id: NonBlank
    check_id: NonBlank


class TaskAnchorV1(AnchorBaseV1):
    task_id: NonBlank


class ExecutionEventAnchorV1(AnchorBaseV1):
    canonical_record_id: NonBlank
    task_id: NonBlank
    event_refs: tuple[str, ...] = Field(min_length=1)


class TraceRepresentationV1(FrozenWireModel):
    format: Literal["HTML", "PDF"]
    artifact_id: str | None
    availability: AvailabilityV1
    claim_anchor: RepresentationClaimAnchorV1

    @model_validator(mode="after")
    def representation_matches_anchor(self) -> TraceRepresentationV1:
        if (
            self.format != self.claim_anchor.format
            or self.artifact_id != self.claim_anchor.artifact_id
            or self.availability != self.claim_anchor.availability
        ):
            raise ValueError("trace representation and Claim anchor disagree")
        return self


class TraceReportV1(FrozenWireModel):
    report_id: NonBlank
    representations: tuple[TraceRepresentationV1, TraceRepresentationV1]

    @field_validator("representations")
    @classmethod
    def fixed_html_pdf_order(
        cls, value: tuple[TraceRepresentationV1, TraceRepresentationV1]
    ) -> tuple[TraceRepresentationV1, TraceRepresentationV1]:
        if tuple(item.format for item in value) != ("HTML", "PDF"):
            raise ValueError("representations must be exactly HTML then PDF")
        return value


class ClaimAnchorSetV1(FrozenWireModel):
    anchor_manifest_id: NonBlank
    anchor_manifest_sha256: Sha256
    representations: tuple[RepresentationClaimAnchorV1, RepresentationClaimAnchorV1]
    review_anchors: tuple[ReviewCheckAnchorV1, ...]
    task_anchors: tuple[TaskAnchorV1, ...]
    execution_anchors: tuple[ExecutionEventAnchorV1, ...]

    @field_validator("representations")
    @classmethod
    def fixed_html_pdf_order(
        cls,
        value: tuple[RepresentationClaimAnchorV1, RepresentationClaimAnchorV1],
    ) -> tuple[RepresentationClaimAnchorV1, RepresentationClaimAnchorV1]:
        if tuple(item.format for item in value) != ("HTML", "PDF"):
            raise ValueError("representations must be exactly HTML then PDF")
        return value


class TraceBundleV1(FrozenWireModel):
    schema_version: Literal["phase4-trace/v1"] = "phase4-trace/v1"
    projection_revision: int = Field(ge=1)
    projection_sequence: int = Field(ge=0)
    anchor_manifest_id: NonBlank
    anchor_manifest_sha256: Sha256
    object_id: NonBlank
    run_id: NonBlank
    claim_id: NonBlank
    metric_id: NonBlank
    calculation_id: NonBlank
    claim: TypedReleasedClaimV1
    released_metric: ReleasedFinancialMetricProjectionV1
    task_refs: tuple[TaskAvailabilityRefV1, ...]
    primary_task_id: str | None
    evidence_refs: tuple[EvidenceAvailabilityRefV1, ...]
    calculation_refs: tuple[CalculationAvailabilityRefV1, ...]
    judgment_refs: tuple[JudgmentAvailabilityV1, ...]
    review_refs: tuple[ReviewAvailabilityRefV1, ...]
    proof_refs: tuple[ProofTraceRefV1, ...]
    canonical_record_id: NonBlank
    released_result_id: NonBlank
    report: TraceReportV1
    review_anchors: tuple[ReviewCheckAnchorV1, ...]
    task_anchors: tuple[TaskAnchorV1, ...]
    execution_anchors: tuple[ExecutionEventAnchorV1, ...]
    availability: AvailabilityV1

    @model_validator(mode="after")
    def trace_identity_closes(self) -> TraceBundleV1:
        if self.claim.claim_id != self.claim_id or self.claim.run_id != self.run_id:
            raise ValueError("trace Claim identity mismatch")
        if self.claim.metric_id != self.metric_id:
            raise ValueError("trace metric identity mismatch")
        if self.released_metric.metric_id != self.metric_id:
            raise ValueError("released metric identity mismatch")
        if self.released_metric.run_id != self.run_id:
            raise ValueError("released metric belongs to another run")
        if self.released_metric.calculation_id != self.calculation_id:
            raise ValueError("trace calculation identity mismatch")
        if self.report.report_id != self.released_result_id:
            raise ValueError("report_id must equal released_result_id")
        if self.primary_task_id is not None and self.primary_task_id not in {
            item.task_id for item in self.task_refs
        }:
            raise ValueError("primary_task_id must name an exact task ref")
        return self


class ClaimDetailV1(FrozenWireModel):
    schema_version: Literal["phase4-claim-detail/v1"] = "phase4-claim-detail/v1"
    projection_revision: int = Field(ge=1)
    projection_sequence: int = Field(ge=0)
    object_id: NonBlank
    run_id: NonBlank
    claim_id: NonBlank
    claim: TypedReleasedClaimV1
    released_metric: ReleasedFinancialMetricProjectionV1
    task_refs: tuple[TaskAvailabilityRefV1, ...]
    primary_task_id: str | None
    evidence: tuple[SafeJsonObject, ...]
    calculations: tuple[SafeJsonObject, ...]
    judgment_refs: tuple[JudgmentAvailabilityV1, ...]
    review_refs: tuple[ReviewAvailabilityRefV1, ...]
    proof_refs: tuple[ProofTraceRefV1, ...]
    canonical_record_id: NonBlank
    released_result_id: NonBlank
    anchors: ClaimAnchorSetV1
    availability: AvailabilityV1


class RendererIdentityV1(FrozenWireModel):
    renderer_id: NonBlank
    renderer_version: NonBlank


class ReportArtifactRepresentationV1(FrozenWireModel):
    format: Literal["HTML", "PDF"]
    required_for_release: bool
    content_type: Literal["text/html; charset=utf-8", "application/pdf"]
    availability: AvailabilityV1
    artifact_id: str | None
    safe_failure_code: str | None
    generation_attempt_id: str | None
    generation_attempt_count: int = Field(ge=0)
    sha256: Sha256 | None
    size_bytes: int | None = Field(default=None, gt=0)
    renderer: RendererIdentityV1 | None
    generated_at: datetime | None
    authorized_ref: str | None

    @model_validator(mode="after")
    def slot_invariants(self) -> ReportArtifactRepresentationV1:
        if self.format == "HTML":
            if not self.required_for_release or self.content_type != "text/html; charset=utf-8":
                raise ValueError("HTML slot policy mismatch")
        elif self.required_for_release or self.content_type != "application/pdf":
            raise ValueError("PDF slot policy mismatch")
        status = self.availability.status
        available = status is AvailabilityStatus.AVAILABLE
        retained_success_fields = (
            self.artifact_id,
            self.sha256,
            self.size_bytes,
            self.renderer,
            self.generated_at,
        )
        if available and (
            any(item is None for item in retained_success_fields)
            or self.authorized_ref is None
            or self.generation_attempt_id is None
            or self.generation_attempt_count < 1
        ):
            raise ValueError("AVAILABLE representation requires complete immutable metadata")
        if available and self.safe_failure_code is not None:
            raise ValueError("AVAILABLE representation cannot carry safe_failure_code")
        if status is AvailabilityStatus.NOT_GENERATED:
            if self.generation_attempt_count != 0 or any(
                item is not None
                for item in (
                    self.artifact_id,
                    self.generation_attempt_id,
                    self.sha256,
                    self.size_bytes,
                    self.renderer,
                    self.generated_at,
                    self.authorized_ref,
                    self.safe_failure_code,
                )
            ):
                raise ValueError("NOT_GENERATED representation cannot claim an attempt")
        elif status is AvailabilityStatus.PENDING:
            if (
                self.generation_attempt_id is None
                or self.generation_attempt_count < 1
                or self.renderer is None
                or any(
                    item is not None
                    for item in (
                        self.artifact_id,
                        self.safe_failure_code,
                        self.sha256,
                        self.size_bytes,
                        self.generated_at,
                        self.authorized_ref,
                    )
                )
            ):
                raise ValueError("PENDING representation has inconsistent attempt state")
        elif status is AvailabilityStatus.FAILED:
            if (
                self.generation_attempt_id is None
                or self.generation_attempt_count < 1
                or self.renderer is None
                or self.safe_failure_code is None
                or any(
                    item is not None
                    for item in (
                        self.artifact_id,
                        self.sha256,
                        self.size_bytes,
                        self.generated_at,
                        self.authorized_ref,
                    )
                )
            ):
                raise ValueError("FAILED representation has inconsistent attempt state")
        elif status is AvailabilityStatus.UNAVAILABLE:
            if (
                any(item is None for item in retained_success_fields)
                or self.generation_attempt_id is None
                or self.generation_attempt_count < 1
                or self.safe_failure_code is not None
                or self.authorized_ref is not None
            ):
                raise ValueError("UNAVAILABLE representation must retain successful metadata")
        elif status is AvailabilityStatus.NOT_RELEASED:
            raise ValueError("NOT_RELEASED is a report-group boundary, not a representation state")
        if self.authorized_ref is not None:
            if not available or not self.authorized_ref.startswith("/api/research-runs/"):
                raise ValueError("authorized_ref must be an AVAILABLE same-origin resource path")
            if "://" in self.authorized_ref or "?" in self.authorized_ref:
                raise ValueError("authorized_ref must not contain a token or storage scheme")
        return self


class ReportArtifactGroupV1(FrozenWireModel):
    schema_version: Literal["phase4-report-artifacts/v1"] = "phase4-report-artifacts/v1"
    object_id: NonBlank
    run_id: NonBlank
    report_id: NonBlank
    canonical_record_id: NonBlank
    released_result_id: NonBlank
    release_policy_version: Literal["phase4-release-eligibility/v1"] = (
        "phase4-release-eligibility/v1"
    )
    artifact_policy_version: Literal["phase4-html-required-pdf-optional/v1"] = (
        "phase4-html-required-pdf-optional/v1"
    )
    anchor_manifest_id: str | None
    anchor_manifest_sha256: Sha256 | None
    availability: AvailabilityV1
    representations: tuple[ReportArtifactRepresentationV1, ReportArtifactRepresentationV1]

    @model_validator(mode="after")
    def group_closure(self) -> ReportArtifactGroupV1:
        if self.report_id != self.released_result_id:
            raise ValueError("report_id must equal released_result_id")
        if tuple(item.format for item in self.representations) != ("HTML", "PDF"):
            raise ValueError("artifact group requires exact HTML/PDF slots")
        if self.availability.status is AvailabilityStatus.AVAILABLE:
            if self.anchor_manifest_id is None or self.anchor_manifest_sha256 is None:
                raise ValueError("AVAILABLE group requires an anchor manifest")
            if self.representations[0].availability.status is not AvailabilityStatus.AVAILABLE:
                raise ValueError("AVAILABLE released report requires HTML")
        return self


class ReleasedObjectCoreV1(FrozenWireModel):
    schema_version: Literal["phase4-released-object-core/v1"] = "phase4-released-object-core/v1"
    projection_revision: int = Field(ge=1)
    generated_at: datetime
    object: ObjectIdentityV1
    latest_released_run_id: str | None
    current_released_result_availability: AvailabilityV1
    source_run_id: str | None
    released_result_id: str | None
    canonical_record_id: str | None
    released_at: datetime | None
    metrics: tuple[ReleasedFinancialMetricProjectionV1, ...]
    claim_refs: tuple[str, ...]
    report_artifacts: ReportArtifactGroupV1 | None
    runs: tuple[RunCollectionItemV1, ...]
    run_count: int = Field(ge=0)

    @model_validator(mode="after")
    def released_identity_is_all_or_none(self) -> ReleasedObjectCoreV1:
        identities = (
            self.latest_released_run_id,
            self.source_run_id,
            self.released_result_id,
            self.canonical_record_id,
            self.released_at,
        )
        if any(item is None for item in identities) and any(
            item is not None for item in identities
        ):
            raise ValueError("released object identity must be complete or absent")
        if self.source_run_id != self.latest_released_run_id:
            raise ValueError("source_run_id must equal latest_released_run_id")
        if self.run_count != len(self.runs):
            raise ValueError("run_count must match the exact object-owned history")
        return self


# Phase 4.5 exact-Run Results Workspace contracts.  These deliberately remain
# small navigation/projection contracts rather than another aggregate model.
ResultsSurfaceNameV1 = Literal[
    "A_REPORT",
    "B_FINANCIAL_REVIEW",
    "C_EXECUTION_RECORD",
]
ResultsSurfaceStatusV1 = Literal["READY", "PARTIAL", "UNAVAILABLE"]
ResultsRelationStatusV1 = Literal["AVAILABLE", "UNAVAILABLE", "NOT_APPLICABLE"]
ExecutionActorTypeV1 = Literal["RESEARCH_LEAD", "SPECIALIST", "SUPPORTING_EXECUTION"]


class ResultsSurfaceAvailabilityV1(FrozenWireModel):
    status: ResultsSurfaceStatusV1
    reason_code: NonBlank | None = None

    @model_validator(mode="after")
    def reason_closes(self) -> ResultsSurfaceAvailabilityV1:
        if self.status == "READY" and self.reason_code is not None:
            raise ValueError("READY Results surface cannot carry a reason")
        if self.status != "READY" and self.reason_code is None:
            raise ValueError("non-READY Results surface requires an authoritative reason")
        return self


class ReviewCheckSelectorV1(FrozenWireModel):
    """Non-durable locator scoped to one exact persisted ReviewRecord."""

    review_id: NonBlank
    check_code: NonBlank
    subject_refs: tuple[NonBlank, ...]

    @field_validator("subject_refs")
    @classmethod
    def canonical_exact_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Review selector subject refs must be unique")
        return tuple(sorted(value))


class ResultsRelationRefV1(FrozenWireModel):
    run_id: NonBlank
    relation_type: Literal[
        "REVIEW_SUBJECT",
        "CORRECTION",
        "REPLAN",
        "PROOF",
        "TASK",
        "AGENT_OUTPUT",
        "EXECUTION_EVENT",
        "REPORT_CONTRIBUTION",
    ]
    status: Literal["AVAILABLE", "NOT_APPLICABLE", "NOT_OBSERVED"]
    target_ref: NonBlank | None = None

    @model_validator(mode="after")
    def target_matches_status(self) -> ResultsRelationRefV1:
        if (self.status == "AVAILABLE") != (self.target_ref is not None):
            raise ValueError("relation target is present exactly when AVAILABLE")
        return self


class ReportAnchorRefV1(FrozenWireModel):
    run_id: NonBlank
    report_id: NonBlank
    artifact_id: NonBlank
    anchor: NonBlank


class ReportContributionRefV1(FrozenWireModel):
    run_id: NonBlank
    report_id: NonBlank
    artifact_id: NonBlank
    report_anchor: NonBlank
    task_id: NonBlank
    actor_id: NonBlank
    agent_output_id: NonBlank
    execution_event_id: NonBlank | None = None
    calculation_id: NonBlank | None = None
    evidence_refs: tuple[NonBlank, ...] = ()
    review_id: NonBlank | None = None


class ReportSectionRefV1(FrozenWireModel):
    section_key: NonBlank
    title: NonBlank
    anchor: ReportAnchorRefV1 | None = None


class ReportSurfaceV1(FrozenWireModel):
    schema_version: Literal["phase4.5-report-surface/v1"] = "phase4.5-report-surface/v1"
    run_id: NonBlank
    object_id: NonBlank
    released_result_id: NonBlank
    canonical_execution_record_id: NonBlank
    report_id: NonBlank
    artifact_id: NonBlank
    title: NonBlank
    company_name: NonBlank
    symbol: NonBlank
    as_of: date
    sections: tuple[ReportSectionRefV1, ...]
    anchors: tuple[ReportAnchorRefV1, ...]
    source_contributions: tuple[ReportContributionRefV1, ...]
    availability: ResultsSurfaceAvailabilityV1

    @model_validator(mode="after")
    def exact_report_identity(self) -> ReportSurfaceV1:
        if self.report_id != self.released_result_id:
            raise ValueError("Report identity must equal its exact ReleasedResult identity")
        if any(
            anchor.run_id != self.run_id
            or anchor.report_id != self.report_id
            or anchor.artifact_id != self.artifact_id
            for anchor in self.anchors
        ):
            raise ValueError("Report anchor crossed Run/Report/representation identity")
        if any(
            section.anchor is not None
            and (
                section.anchor.run_id != self.run_id
                or section.anchor.report_id != self.report_id
                or section.anchor.artifact_id != self.artifact_id
            )
            for section in self.sections
        ):
            raise ValueError("Report section crossed Run/Report/representation identity")
        if any(
            contribution.run_id != self.run_id
            or contribution.report_id != self.report_id
            or contribution.artifact_id != self.artifact_id
            for contribution in self.source_contributions
        ):
            raise ValueError("Report contribution crossed Run/Report/representation identity")
        if len({item.anchor for item in self.anchors}) != len(self.anchors):
            raise ValueError("Report representation anchors must be unique")
        return self


class FinancialReviewCheckV1(FrozenWireModel):
    selector: ReviewCheckSelectorV1
    status: Literal["PASS", "REVIEW", "BLOCK"]
    safe_explanation: str | None = None
    input_refs: tuple[ResultsRelationRefV1, ...]
    output_refs: tuple[ResultsRelationRefV1, ...] = ()


class FinancialReviewSurfaceV1(FrozenWireModel):
    schema_version: Literal["phase4.5-financial-review-surface/v1"] = (
        "phase4.5-financial-review-surface/v1"
    )
    run_id: NonBlank
    object_id: NonBlank
    released_result_id: NonBlank
    canonical_execution_record_id: NonBlank
    review_id: NonBlank
    reviewer: NonBlank
    verdict: Literal["PASS", "REVIEW", "BLOCK"]
    checks: tuple[FinancialReviewCheckV1, ...]
    availability: ResultsSurfaceAvailabilityV1

    @model_validator(mode="after")
    def exact_review_identity(self) -> FinancialReviewSurfaceV1:
        if not self.checks:
            raise ValueError("available Financial Review requires persisted checks")
        selectors = set()
        for check in self.checks:
            if check.selector.review_id != self.review_id:
                raise ValueError("Review selector belongs to another ReviewRecord")
            if any(ref.run_id != self.run_id for ref in (*check.input_refs, *check.output_refs)):
                raise ValueError("Review relation crossed Run identity")
            key = (check.selector.check_code, check.selector.subject_refs)
            if key in selectors:
                raise ValueError("ambiguous scoped Review selector")
            selectors.add(key)
        return self


class ExecutionInputRefV1(FrozenWireModel):
    run_id: NonBlank
    ref_id: NonBlank


class ExecutionObservableRecordV1(FrozenWireModel):
    run_id: NonBlank
    event_id: NonBlank
    task_id: NonBlank | None = None
    event_type: NonBlank
    status: NonBlank


class ExecutionOutputRecordV1(FrozenWireModel):
    run_id: NonBlank
    output_id: NonBlank
    task_id: NonBlank
    status: Literal["SUCCESS", "FAILED"]
    summary: str | None = None
    key_findings: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class ExecutionActorSummaryV1(FrozenWireModel):
    run_id: NonBlank
    actor_id: NonBlank
    actor_type: ExecutionActorTypeV1
    display_role: NonBlank
    status: NonBlank
    event_count: int = Field(ge=0)
    record_count: int = Field(ge=0)


class ExecutionActorDetailV1(FrozenWireModel):
    run_id: NonBlank
    actor_id: NonBlank
    actor_type: ExecutionActorTypeV1
    input_refs: tuple[ExecutionInputRefV1, ...]
    observable_process: tuple[ExecutionObservableRecordV1, ...]
    outputs: tuple[ExecutionOutputRecordV1, ...]
    report_contributions: tuple[ReportContributionRefV1, ...]
    quarantined_input_ref_count: int = Field(ge=0)

    @model_validator(mode="after")
    def exact_actor_identity(self) -> ExecutionActorDetailV1:
        if any(item.run_id != self.run_id for item in self.input_refs):
            raise ValueError("Execution input crossed Run identity")
        if any(item.run_id != self.run_id for item in self.observable_process):
            raise ValueError("Execution process record crossed Run identity")
        if any(item.run_id != self.run_id for item in self.outputs):
            raise ValueError("Execution output crossed Run identity")
        if any(
            item.run_id != self.run_id or item.actor_id != self.actor_id
            for item in self.report_contributions
        ):
            raise ValueError("Execution contribution crossed Run/Actor identity")
        return self


class ExecutionRecordSurfaceV1(FrozenWireModel):
    schema_version: Literal["phase4.5-execution-record-surface/v1"] = (
        "phase4.5-execution-record-surface/v1"
    )
    run_id: NonBlank
    object_id: NonBlank
    released_result_id: NonBlank
    canonical_execution_record_id: NonBlank
    actors: tuple[ExecutionActorSummaryV1, ...]
    actor_details: tuple[ExecutionActorDetailV1, ...]
    availability: ResultsSurfaceAvailabilityV1

    @model_validator(mode="after")
    def exact_execution_identity(self) -> ExecutionRecordSurfaceV1:
        actor_keys = {(item.actor_type, item.actor_id) for item in self.actors}
        detail_keys = {(item.actor_type, item.actor_id) for item in self.actor_details}
        if len(actor_keys) != len(self.actors):
            raise ValueError("Execution actor catalog contains duplicate identities")
        if len(detail_keys) != len(self.actor_details):
            raise ValueError("Execution actor detail contains duplicate identities")
        if any(item.run_id != self.run_id for item in self.actors):
            raise ValueError("Execution actor crossed Run identity")
        if any(
            item.run_id != self.run_id or (item.actor_type, item.actor_id) not in actor_keys
            for item in self.actor_details
        ):
            raise ValueError("Execution actor detail is not owned by this catalog/Run")
        return self


class CrossViewEndpointV1(FrozenWireModel):
    surface: ResultsSurfaceNameV1
    run_id: NonBlank
    identity_id: NonBlank
    artifact_id: NonBlank | None = None
    target_anchor: NonBlank | None = None
    check_selector: ReviewCheckSelectorV1 | None = None

    @model_validator(mode="after")
    def scoped_fields_match_surface(self) -> CrossViewEndpointV1:
        if self.artifact_id is not None and self.surface != "A_REPORT":
            raise ValueError("Report artifact identity is valid only on the Report surface")
        if self.target_anchor is not None and (
            self.surface != "A_REPORT" or self.artifact_id is None
        ):
            raise ValueError("Report anchor requires an exact Report representation")
        if self.check_selector is not None and (
            self.surface != "B_FINANCIAL_REVIEW"
            or self.check_selector.review_id != self.identity_id
        ):
            raise ValueError("Review selector is scoped to its exact Review endpoint")
        return self


class CrossViewRefV1(FrozenWireModel):
    run_id: NonBlank
    source: CrossViewEndpointV1
    target: CrossViewEndpointV1
    status: ResultsRelationStatusV1
    reason_code: NonBlank | None = None

    @model_validator(mode="after")
    def exact_cross_view_identity(self) -> CrossViewRefV1:
        if self.source.run_id != self.run_id or self.target.run_id != self.run_id:
            raise ValueError("CrossViewRef crossed Run identity")
        if self.status == "AVAILABLE" and self.reason_code is not None:
            raise ValueError("AVAILABLE CrossViewRef cannot carry a reason")
        if self.status != "AVAILABLE" and self.reason_code is None:
            raise ValueError("unavailable CrossViewRef requires an authoritative reason")
        return self


class ResultsSurfaceRefV1(FrozenWireModel):
    surface: ResultsSurfaceNameV1
    run_id: NonBlank
    object_id: NonBlank
    released_result_id: NonBlank
    canonical_execution_record_id: NonBlank
    surface_id: NonBlank
    href: NonBlank
    availability: ResultsSurfaceAvailabilityV1

    @model_validator(mode="after")
    def href_is_exact_run_relative(self) -> ResultsSurfaceRefV1:
        expected_suffix = {
            "A_REPORT": "report-view",
            "B_FINANCIAL_REVIEW": "review-view",
            "C_EXECUTION_RECORD": "execution-view",
        }[self.surface]
        if self.href != f"/api/research-runs/{self.run_id}/{expected_suffix}":
            raise ValueError("Results surface href is not scoped to its exact Run/surface")
        return self


class ResultsWorkspaceV1(FrozenWireModel):
    schema_version: Literal["phase4.5-results-workspace/v1"] = "phase4.5-results-workspace/v1"
    run_id: NonBlank
    object_id: NonBlank
    as_of: date
    run_status: RunStatusV1
    released_result_id: NonBlank
    canonical_execution_record_id: NonBlank
    report_surface: ResultsSurfaceRefV1
    review_surface: ResultsSurfaceRefV1
    execution_surface: ResultsSurfaceRefV1
    cross_view_refs: tuple[CrossViewRefV1, ...]

    @model_validator(mode="after")
    def exact_workspace_identity(self) -> ResultsWorkspaceV1:
        expected_surfaces = (
            (self.report_surface, "A_REPORT"),
            (self.review_surface, "B_FINANCIAL_REVIEW"),
            (self.execution_surface, "C_EXECUTION_RECORD"),
        )
        for surface, expected_name in expected_surfaces:
            if surface.surface != expected_name:
                raise ValueError("Results surface is in the wrong workspace slot")
            if (
                surface.run_id != self.run_id
                or surface.object_id != self.object_id
                or surface.released_result_id != self.released_result_id
                or surface.canonical_execution_record_id != self.canonical_execution_record_id
            ):
                raise ValueError("Results surface crossed exact workspace identity")
        if any(item.run_id != self.run_id for item in self.cross_view_refs):
            raise ValueError("Results cross-view navigation crossed Run identity")
        surface_ids = {
            "A_REPORT": self.report_surface.surface_id,
            "B_FINANCIAL_REVIEW": self.review_surface.surface_id,
            "C_EXECUTION_RECORD": self.execution_surface.surface_id,
        }
        if any(
            endpoint.identity_id != surface_ids[endpoint.surface]
            for item in self.cross_view_refs
            for endpoint in (item.source, item.target)
        ):
            raise ValueError("Results cross-view navigation names another surface identity")
        return self


ResearchObjectDetailV1.model_rebuild()
