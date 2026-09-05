"""Strict, read-only reconstruction of one persisted Phase 4 product Run.

The functions in this module deliberately accept a complete record set read in
one database snapshot.  They never perform a secondary lookup, choose a
``latest`` or ``first`` row, join by display text, or manufacture an absent
record.  A caller either receives one identity-closed reconstruction or a
typed :class:`ProductError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Generic, Literal, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from src.domain.calculation import CalculationRecord
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.enums import ProofRequirement, ProofStatus, ReviewStatus, RunStatus
from src.domain.evidence import EvidenceRecord
from src.domain.proof import (
    ProofArtifactReference,
    ProofInputCommitment,
    ProofPolicyDecision,
    ProofRecord,
    ProofVerificationRecord,
)
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.report import ReportArtifactRecord
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.review import ReviewRecord
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph, Task
from src.phase4_product.artifacts import (
    ArtifactProjectionError,
    ValidatedAnchorManifest,
    validate_anchor_manifest,
)
from src.phase4_product.contracts import AvailabilityStatus, AvailabilityV1, ErrorCodeV1
from src.phase4_product.errors import ProductError, product_error
from src.phase4_product.hashing import require_sha256_identity

RecordT = TypeVar("RecordT")
ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ProjectionWatermark:
    """The durable revision and event tail read with the reconstructed rows."""

    revision: int
    sequence: int

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or self.revision < 1:
            raise _integrity("projection_revision must be an integer greater than zero")
        if isinstance(self.sequence, bool) or self.sequence < 0:
            raise _integrity("projection_sequence must be a non-negative integer")

    def etag(self, run_id: str) -> str:
        """Return the frozen ETag only from the two verified persisted values."""

        _require_nonblank(run_id, field_name="run_id")
        return f'"p4:{run_id}:{self.revision}:{self.sequence}"'


@dataclass(frozen=True, slots=True)
class ReconstructedResource(Generic[RecordT]):
    """An exact retained record or an explicit non-available state."""

    availability: AvailabilityV1
    value: RecordT | None = None

    def __post_init__(self) -> None:
        available = self.availability.status is AvailabilityStatus.AVAILABLE
        if available != (self.value is not None):
            raise _integrity(
                "resource value must be present exactly when its availability is AVAILABLE"
            )

    @classmethod
    def available(cls, value: RecordT) -> ReconstructedResource[RecordT]:
        return cls(availability=AvailabilityV1.available(), value=value)

    @classmethod
    def absent(
        cls,
        status: AvailabilityStatus,
        reason_code: str,
        *,
        retryable: bool = False,
    ) -> ReconstructedResource[RecordT]:
        return cls(
            availability=AvailabilityV1.unavailable(
                status,
                reason_code,
                retryable=retryable,
            )
        )

    def require(self, *, resource_type: str, resource_id: str) -> RecordT:
        """Return the record or raise the matching frozen Product error."""

        if self.value is not None:
            return self.value
        error_code = {
            AvailabilityStatus.NOT_GENERATED: ErrorCodeV1.NOT_GENERATED,
            AvailabilityStatus.NOT_RELEASED: ErrorCodeV1.NOT_RELEASED,
        }.get(self.availability.status, ErrorCodeV1.UNAVAILABLE)
        reason_code = self.availability.reason_code or "RESOURCE_UNAVAILABLE"
        raise product_error(
            error_code,
            "the exact requested resource is not available",
            resource_type=_public_resource_type(resource_type),
            resource_id=resource_id,
            details={"reason_code": reason_code},
        )


@dataclass(frozen=True, slots=True)
class PersistedReviewCheckIdentity:
    """Stable identity relation required to validate Review-check anchors.

    Phase 3 ``ReviewCheck`` values have no stable ``check_id``.  A Phase 4
    PostgreSQL repository must therefore supply these rows from a dedicated
    relation rather than deriving an ID from check text or list position.
    """

    check_id: str
    review_id: str
    run_id: str

    def __post_init__(self) -> None:
        for name in ("check_id", "review_id", "run_id"):
            _require_nonblank(getattr(self, name), field_name=name)


@dataclass(frozen=True, slots=True)
class PersistedReleaseValidation:
    """One durable ``ReleaseValidationRecordV1`` row.

    This is deliberately a persistence representation rather than a public
    response DTO.  Keeping every frozen field explicit lets exact snapshot
    reconstruction observe validation cardinality and prevents a RELEASED Run
    from being reconstructed from a caller-supplied boolean eligibility flag.
    The hash preimages are owned by the release writer/Parent composition; this
    reader validates their identities and the complete release binding.
    """

    validation_id: str
    run_id: str
    object_id: str
    decision: Literal["ALLOWED", "BLOCKED"]
    reason_codes: tuple[str, ...]
    review_id: str
    canonical_record_id: str
    released_result_id: str
    release_policy_version: str
    review_policy_version: str
    proof_policy_id: str
    proof_policy_hash: str
    material_output_policy_version: str
    material_output_manifest_hash: str
    artifact_policy_version: str
    artifact_manifest_hash: str
    review_input_snapshot_hash: str
    closure_hash: str
    evaluated_at: datetime
    released_at: datetime | None

    def __post_init__(self) -> None:
        for field_name in (
            "validation_id",
            "run_id",
            "object_id",
            "review_id",
            "canonical_record_id",
            "released_result_id",
            "release_policy_version",
            "review_policy_version",
            "proof_policy_id",
            "material_output_policy_version",
            "artifact_policy_version",
        ):
            _require_nonblank(getattr(self, field_name), field_name=field_name)
        if self.decision not in {"ALLOWED", "BLOCKED"}:
            raise _integrity("ReleaseValidation decision is not in the frozen vocabulary")
        _require_unique_refs(
            self.reason_codes,
            owner_type="release_validation",
            owner_id=self.validation_id,
            field="reason_codes",
        )
        for reason_code in self.reason_codes:
            if (
                not reason_code.isascii()
                or not reason_code.replace("_", "").isalnum()
                or reason_code != reason_code.upper()
            ):
                raise _integrity("ReleaseValidation reason code is not a stable uppercase token")
        for field_name in (
            "proof_policy_hash",
            "material_output_manifest_hash",
            "artifact_manifest_hash",
            "review_input_snapshot_hash",
            "closure_hash",
        ):
            try:
                require_sha256_identity(getattr(self, field_name), field_name=field_name)
            except ValueError as exc:
                raise _integrity(str(exc)) from exc
        _require_utc(self.evaluated_at, field_name="evaluated_at")
        if self.released_at is not None:
            _require_utc(self.released_at, field_name="released_at")
        if self.decision == "ALLOWED":
            if self.reason_codes or self.released_at is None:
                raise _integrity(
                    "ALLOWED ReleaseValidation requires released_at and no blocking reasons"
                )
        elif not self.reason_codes or self.released_at is not None:
            raise _integrity(
                "BLOCKED ReleaseValidation requires reasons and cannot carry released_at"
            )


@dataclass(frozen=True, slots=True)
class PersistedRunSnapshot:
    """All authoritative rows for one Run from one PostgreSQL MVCC snapshot.

    Collections remain collections even for database-unique records so that
    duplicate rows, foreign rows, and missing rows are observable to the
    validator.  ``selected_review_id`` is optional only because a single
    Review row is unambiguous; multiple Review rows require an explicit durable
    relation and are never resolved by recency or position.
    """

    requested_object_id: str
    requested_run_id: str
    projection_revision: int | None = None
    projection_sequence: int | None = None
    research_objects: tuple[ResearchObject, ...] = ()
    goals: tuple[ResearchGoal, ...] = ()
    schemes: tuple[ResearchSchemeSnapshot, ...] = ()
    runs: tuple[ResearchRun, ...] = ()
    planned_graphs: tuple[PlannedTaskGraph, ...] = ()
    actual_graphs: tuple[ActualRuntimeGraph, ...] = ()
    tasks: tuple[Task, ...] = ()
    events: tuple[RuntimeEvent, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    calculations: tuple[CalculationRecord, ...] = ()
    reviews: tuple[ReviewRecord, ...] = ()
    selected_review_id: str | None = None
    review_check_identities: tuple[PersistedReviewCheckIdentity, ...] = ()
    proof_policy_decisions: tuple[ProofPolicyDecision, ...] = ()
    proof_input_commitments: tuple[ProofInputCommitment, ...] = ()
    proofs: tuple[ProofRecord, ...] = ()
    proof_artifacts: tuple[ProofArtifactReference, ...] = ()
    proof_verifications: tuple[ProofVerificationRecord, ...] = ()
    canonical_records: tuple[CanonicalExecutionRecord, ...] = ()
    released_results: tuple[ReleasedResearchResult, ...] = ()
    release_validations: tuple[PersistedReleaseValidation, ...] = ()
    report_artifacts: tuple[ReportArtifactRecord, ...] = ()
    anchor_manifests: tuple[ValidatedAnchorManifest, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank(self.requested_object_id, field_name="requested_object_id")
        _require_nonblank(self.requested_run_id, field_name="requested_run_id")
        if self.selected_review_id is not None:
            _require_nonblank(self.selected_review_id, field_name="selected_review_id")


@runtime_checkable
class ExactRunSnapshotRepository(Protocol):
    """Read one complete Run closure without broad or fallback queries."""

    async def read_exact_run_snapshot(
        self,
        *,
        object_id: str,
        run_id: str,
    ) -> PersistedRunSnapshot | None:
        """Read all rows and both watermarks in one repeatable PostgreSQL snapshot."""


@dataclass(frozen=True, slots=True)
class ProofClosure:
    decisions: tuple[ProofPolicyDecision, ...]
    input_commitments: tuple[ProofInputCommitment, ...]
    proofs: tuple[ProofRecord, ...]
    artifacts: tuple[ProofArtifactReference, ...]
    verifications: tuple[ProofVerificationRecord, ...]


@dataclass(frozen=True, slots=True)
class ReportArtifactClosure:
    """The two fixed report slots plus retained non-report artifacts."""

    html: ReconstructedResource[ReportArtifactRecord]
    pdf: ReconstructedResource[ReportArtifactRecord]
    other: tuple[ReportArtifactRecord, ...]


@dataclass(frozen=True, slots=True)
class ReconstructedProductRun:
    """Identity-closed, immutable view over the exact supplied persisted rows."""

    research_object: ResearchObject
    goal: ResearchGoal
    scheme: ResearchSchemeSnapshot
    run: ResearchRun
    planned_graph: PlannedTaskGraph
    actual_graph: ReconstructedResource[ActualRuntimeGraph]
    tasks: tuple[Task, ...]
    events: tuple[RuntimeEvent, ...]
    evidence: tuple[EvidenceRecord, ...]
    calculations: tuple[CalculationRecord, ...]
    review: ReconstructedResource[ReviewRecord]
    proof: ReconstructedResource[ProofClosure]
    canonical_record: ReconstructedResource[CanonicalExecutionRecord]
    released_result: ReconstructedResource[ReleasedResearchResult]
    release_validation: ReconstructedResource[PersistedReleaseValidation]
    report_artifacts: ReportArtifactClosure
    anchor_manifests: ReconstructedResource[tuple[ValidatedAnchorManifest, ...]]
    watermark: ProjectionWatermark


def reconstruct_product_run(snapshot: PersistedRunSnapshot) -> ReconstructedProductRun:
    """Validate and reconstruct exactly one persisted Product Run.

    Any cross-Run member, duplicate identity, dangling dependency/reference,
    torn watermark, ambiguous Review, or incomplete terminal closure fails
    closed.  Missing nonterminal components remain explicit Availability
    values; a RELEASED Run may not hide missing release facts this way.
    """

    watermark = _validate_watermark(snapshot)
    research_object = _required_exact_one(
        snapshot.research_objects,
        id_field="object_id",
        expected_id=snapshot.requested_object_id,
        resource_type="research_object",
        root=True,
    )
    run = _required_exact_one(
        snapshot.runs,
        id_field="run_id",
        expected_id=snapshot.requested_run_id,
        resource_type="research_run",
        root=True,
    )
    if run.research_object_id != research_object.object_id:
        raise _identity(
            "research Run belongs to another Object",
            "research_run",
            run.run_id,
        )

    goal = _required_exact_one(
        snapshot.goals,
        id_field="goal_id",
        expected_id=run.goal_id,
        resource_type="research_goal",
    )
    scheme = _required_exact_one(
        snapshot.schemes,
        id_field="scheme_id",
        expected_id=run.scheme_id,
        resource_type="research_scheme",
    )
    _validate_goal_scheme(research_object, goal, scheme, run)

    if run.planned_graph_id is None:
        raise _integrity(
            "persisted admitted Run omits its exact planned graph identity",
            resource_type="research_run",
            resource_id=run.run_id,
        )
    planned_graph = _required_exact_one(
        snapshot.planned_graphs,
        id_field="graph_id",
        expected_id=run.planned_graph_id,
        resource_type="graph",
    )
    if run.actual_graph_id is None:
        if snapshot.actual_graphs:
            raise _integrity(
                "Run without actual_graph_id contains an Actual Graph row",
                resource_type="research_run",
                resource_id=run.run_id,
            )
        actual_graph: ReconstructedResource[ActualRuntimeGraph] = ReconstructedResource.absent(
            AvailabilityStatus.NOT_GENERATED,
            "ACTUAL_GRAPH_NOT_GENERATED",
        )
    else:
        actual_graph = ReconstructedResource.available(
            _required_exact_one(
                snapshot.actual_graphs,
                id_field="graph_id",
                expected_id=run.actual_graph_id,
                resource_type="graph",
            )
        )
    tasks = _validate_graphs_and_tasks(run, planned_graph, actual_graph, snapshot.tasks)
    events = _validate_events(run, tasks, snapshot.events, watermark)
    evidence = _validate_evidence(run, research_object, tasks, snapshot.evidence)
    calculations = _validate_calculations(run, tasks, evidence, snapshot.calculations)

    review = _reconstruct_review(snapshot, run, evidence, calculations)
    proof = _reconstruct_proof(snapshot, run, evidence, calculations, review)
    canonical = _reconstruct_canonical(
        snapshot,
        research_object,
        goal,
        scheme,
        run,
        planned_graph,
        actual_graph,
        tasks,
        evidence,
        calculations,
        review,
        proof,
    )
    result = _reconstruct_result(snapshot, run, evidence, calculations, canonical, review, proof)
    report_artifacts = _reconstruct_report_artifacts(snapshot, run, canonical, result)
    release_validation = _reconstruct_release_validation(
        snapshot,
        research_object,
        run,
        review,
        proof,
        canonical,
        result,
    )
    manifests = _reconstruct_anchor_manifests(
        snapshot,
        research_object,
        run,
        tasks,
        events,
        review,
        canonical,
        result,
        report_artifacts,
    )
    _validate_terminal_release_closure(
        run,
        review,
        proof,
        canonical,
        result,
        release_validation,
        report_artifacts,
        manifests,
    )

    return ReconstructedProductRun(
        research_object=research_object,
        goal=goal,
        scheme=scheme,
        run=run,
        planned_graph=planned_graph,
        actual_graph=actual_graph,
        tasks=tasks,
        events=events,
        evidence=evidence,
        calculations=calculations,
        review=review,
        proof=proof,
        canonical_record=canonical,
        released_result=result,
        release_validation=release_validation,
        report_artifacts=report_artifacts,
        anchor_manifests=manifests,
        watermark=watermark,
    )


def _validate_watermark(snapshot: PersistedRunSnapshot) -> ProjectionWatermark:
    if snapshot.projection_revision is None:
        raise product_error(
            ErrorCodeV1.UNAVAILABLE,
            "durable projection revision is unavailable",
            resource_type="research_run",
            resource_id=snapshot.requested_run_id,
            details={"reason_code": "PROJECTION_REVISION_NOT_PERSISTED"},
        )
    if snapshot.projection_sequence is None:
        raise product_error(
            ErrorCodeV1.UNAVAILABLE,
            "atomic event watermark is unavailable",
            resource_type="research_run",
            resource_id=snapshot.requested_run_id,
            details={"reason_code": "PROJECTION_SEQUENCE_NOT_ATOMIC"},
        )
    return ProjectionWatermark(snapshot.projection_revision, snapshot.projection_sequence)


def _validate_goal_scheme(
    research_object: ResearchObject,
    goal: ResearchGoal,
    scheme: ResearchSchemeSnapshot,
    run: ResearchRun,
) -> None:
    if goal.research_object_id != research_object.object_id:
        raise _identity("Goal belongs to another Object", "research_goal", goal.goal_id)
    if scheme.research_object_id != research_object.object_id or scheme.goal_id != goal.goal_id:
        raise _identity(
            "Scheme belongs to another Object or Goal", "research_scheme", scheme.scheme_id
        )
    if run.goal_id != goal.goal_id or run.scheme_id != scheme.scheme_id:
        raise _identity("Run Goal/Scheme identity closure failed", "research_run", run.run_id)
    if scheme.confirmed_at is None:
        raise _integrity(
            "an admitted Run cannot reference an unconfirmed Scheme",
            resource_type="research_scheme",
            resource_id=scheme.scheme_id,
        )


def _validate_graphs_and_tasks(
    run: ResearchRun,
    planned: PlannedTaskGraph,
    actual: ReconstructedResource[ActualRuntimeGraph],
    persisted_tasks: tuple[Task, ...],
) -> tuple[Task, ...]:
    if planned.run_id != run.run_id:
        raise _identity("Task graph belongs to another Run", "research_run", run.run_id)
    tasks_by_id = _unique_by(persisted_tasks, "task_id", "task")
    planned_by_id = _unique_by(tuple(planned.tasks), "task_id", "planned task")
    source_tasks = tuple(actual.value.tasks) if actual.value is not None else tuple(planned.tasks)
    source_by_id = _unique_by(
        source_tasks,
        "task_id",
        "actual task" if actual.value is not None else "planned task",
    )
    if actual.value is not None:
        if actual.value.run_id != run.run_id:
            raise _identity("Actual Graph belongs to another Run", "graph", actual.value.graph_id)
        if set(planned_by_id) - set(source_by_id):
            raise _integrity(
                "actual graph omits a Task from the immutable planned graph",
                resource_type="research_run",
                resource_id=run.run_id,
            )
    if set(tasks_by_id) != set(source_by_id):
        raise _integrity(
            "normalized Task rows and authoritative graph Task identities disagree",
            resource_type="research_run",
            resource_id=run.run_id,
        )
    for task_id, task in tasks_by_id.items():
        if task.run_id != run.run_id or source_by_id[task_id].run_id != run.run_id:
            raise _identity("Task belongs to another Run", "task", task_id)
        if _model_json(task) != _model_json(source_by_id[task_id]):
            raise _integrity(
                "normalized Task row disagrees with the authoritative graph snapshot",
                resource_type="task",
                resource_id=task_id,
            )
    for task in planned.tasks:
        if task.run_id != run.run_id:
            raise _identity("planned Task belongs to another Run", "task", task.task_id)
    _validate_dependency_graph(tuple(planned.tasks), graph_kind="PLANNED", run_id=run.run_id)
    if actual.value is not None:
        _validate_dependency_graph(
            tuple(actual.value.tasks),
            graph_kind="ACTUAL",
            run_id=run.run_id,
        )
    for task in persisted_tasks:
        if task.parent_task_id is not None and task.parent_task_id not in tasks_by_id:
            raise _integrity(
                "Task parent reference is not present in the same actual graph",
                resource_type="task",
                resource_id=task.task_id,
            )
    return persisted_tasks


def _validate_dependency_graph(
    tasks: tuple[Task, ...],
    *,
    graph_kind: str,
    run_id: str,
) -> None:
    by_id = {task.task_id: task for task in tasks}
    for task in tasks:
        if len(task.dependencies) != len(set(task.dependencies)):
            raise _integrity(
                f"{graph_kind} Task contains duplicate dependencies",
                resource_type="task",
                resource_id=task.task_id,
            )
        unknown = set(task.dependencies) - set(by_id)
        if unknown:
            raise _integrity(
                f"{graph_kind} Task dependency closure is incomplete",
                resource_type="task",
                resource_id=task.task_id,
                details={"reason_code": "TASK_DEPENDENCY_CLOSURE_INCOMPLETE"},
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise _integrity(
                f"{graph_kind} Task dependencies contain a cycle",
                resource_type="research_run",
                resource_id=run_id,
            )
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency_id in by_id[task_id].dependencies:
            visit(dependency_id)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in by_id:
        visit(task_id)


def _validate_events(
    run: ResearchRun,
    tasks: tuple[Task, ...],
    events: tuple[RuntimeEvent, ...],
    watermark: ProjectionWatermark,
) -> tuple[RuntimeEvent, ...]:
    _unique_by(events, "event_id", "runtime event")
    task_ids = {task.task_id for task in tasks}
    sequences = [event.sequence for event in events]
    expected = list(range(1, watermark.sequence + 1))
    if sequences != expected:
        raise _integrity(
            "RuntimeEvents are not the exact ordered contiguous prefix named by the watermark",
            resource_type="research_run",
            resource_id=run.run_id,
            details={"reason_code": "PROJECTION_WATERMARK_TORN"},
        )
    for event in events:
        if event.run_id != run.run_id:
            raise _identity("RuntimeEvent belongs to another Run", "projection", run.run_id)
        if event.task_id is not None and event.task_id not in task_ids:
            raise _integrity(
                "RuntimeEvent names a Task absent from the exact actual graph",
                resource_type="projection",
                resource_id=run.run_id,
            )

    started = [event for event in events if event.type is RuntimeEventType.RUN_STARTED]
    completed = [event for event in events if event.type is RuntimeEventType.RUN_COMPLETED]
    failed = [event for event in events if event.type is RuntimeEventType.RUN_FAILED]
    terminal = run.status in {RunStatus.RELEASED, RunStatus.FAILED, RunStatus.CANCELLED}
    if run.started_at is None:
        if started:
            raise _integrity("Run start event exists without persisted started_at")
    elif len(started) != 1:
        raise _integrity("persisted started_at requires exactly one run.started event")
    if terminal:
        if run.completed_at is None:
            raise _integrity("terminal Run is missing completed_at")
        expected_terminal_type = (
            RuntimeEventType.RUN_COMPLETED
            if run.status is RunStatus.RELEASED
            else RuntimeEventType.RUN_FAILED
        )
        expected_events = completed if run.status is RunStatus.RELEASED else failed
        forbidden_events = failed if run.status is RunStatus.RELEASED else completed
        if len(expected_events) != 1 or forbidden_events:
            raise _integrity("Run terminal state and terminal event cardinality disagree")
        if not events or events[-1].type is not expected_terminal_type:
            raise _integrity("terminal event must be the final business event")
        if run.status in {RunStatus.FAILED, RunStatus.CANCELLED}:
            payload_status = failed[0].payload.get("status")
            if payload_status != run.status.value:
                raise _integrity("run.failed payload status disagrees with persisted Run status")
    elif completed or failed or run.completed_at is not None:
        raise _integrity("nonterminal Run contains terminal state or events")
    return events


def _validate_evidence(
    run: ResearchRun,
    research_object: ResearchObject,
    tasks: tuple[Task, ...],
    evidence: tuple[EvidenceRecord, ...],
) -> tuple[EvidenceRecord, ...]:
    by_id = _unique_by(evidence, "evidence_id", "evidence")
    task_ids = {task.task_id for task in tasks}
    for record in evidence:
        if record.run_id != run.run_id or record.object_id != research_object.object_id:
            raise _identity(
                "Evidence belongs to another Object or Run", "evidence", record.evidence_id
            )
        if record.producer_task_id is not None and record.producer_task_id not in task_ids:
            raise _integrity(
                "Evidence producer Task is absent from the exact actual graph",
                resource_type="evidence",
                resource_id=record.evidence_id,
            )
    for task in tasks:
        for field_name in ("task_input_evidence_ids", "task_output_evidence_ids"):
            refs = tuple(getattr(task, field_name))
            _require_unique_refs(refs, owner_type="task", owner_id=task.task_id, field=field_name)
            unknown = set(refs) - set(by_id)
            if unknown:
                raise _integrity(
                    "Task Evidence reference closure is incomplete",
                    resource_type="task",
                    resource_id=task.task_id,
                    details={
                        "reason_code": "EVIDENCE_REFERENCE_CLOSURE_INCOMPLETE",
                        "field": field_name,
                    },
                )
    return evidence


def _validate_calculations(
    run: ResearchRun,
    tasks: tuple[Task, ...],
    evidence: tuple[EvidenceRecord, ...],
    calculations: tuple[CalculationRecord, ...],
) -> tuple[CalculationRecord, ...]:
    _unique_by(calculations, "calculation_id", "calculation")
    task_ids = {task.task_id for task in tasks}
    evidence_ids = {record.evidence_id for record in evidence}
    for record in calculations:
        if record.run_id != run.run_id:
            raise _identity(
                "Calculation belongs to another Run", "calculation", record.calculation_id
            )
        if record.task_id not in task_ids:
            raise _integrity(
                "Calculation Task is absent from the exact actual graph",
                resource_type="calculation",
                resource_id=record.calculation_id,
            )
        refs = tuple(record.input_evidence_ids)
        _require_unique_refs(
            refs,
            owner_type="calculation",
            owner_id=record.calculation_id,
            field="input_evidence_ids",
        )
        unknown = set(refs) - evidence_ids
        if unknown:
            raise _integrity(
                "Calculation Evidence dependency closure is incomplete",
                resource_type="calculation",
                resource_id=record.calculation_id,
                details={"reason_code": "EVIDENCE_REFERENCE_CLOSURE_INCOMPLETE"},
            )
    return calculations


def _reconstruct_review(
    snapshot: PersistedRunSnapshot,
    run: ResearchRun,
    evidence: tuple[EvidenceRecord, ...],
    calculations: tuple[CalculationRecord, ...],
) -> ReconstructedResource[ReviewRecord]:
    _unique_by(snapshot.reviews, "review_id", "review")
    for review in snapshot.reviews:
        if review.run_id != run.run_id:
            raise _identity("Review belongs to another Run", "review", review.review_id)
    if not snapshot.reviews:
        if snapshot.selected_review_id is not None:
            raise _integrity("selected Review identity has no retained Review record")
        return ReconstructedResource.absent(
            AvailabilityStatus.NOT_GENERATED,
            "FINANCIAL_REVIEW_NOT_GENERATED",
        )
    if snapshot.selected_review_id is None:
        if len(snapshot.reviews) != 1:
            raise product_error(
                ErrorCodeV1.UNAVAILABLE,
                "multiple Review rows have no exact durable selection relation",
                resource_type="research_run",
                resource_id=run.run_id,
                details={"reason_code": "REVIEW_SELECTION_NOT_PERSISTED"},
            )
        selected = snapshot.reviews[0]
    else:
        matches = [
            review for review in snapshot.reviews if review.review_id == snapshot.selected_review_id
        ]
        if len(matches) != 1:
            raise _integrity("selected Review identity is missing or duplicated")
        selected = matches[0]

    evidence_ids = {record.evidence_id for record in evidence}
    calculation_ids = {record.calculation_id for record in calculations}
    _validate_known_refs(
        tuple(selected.reviewed_evidence_refs),
        evidence_ids,
        owner_type="review",
        owner_id=selected.review_id,
        field="reviewed_evidence_refs",
    )
    _validate_known_refs(
        tuple(selected.reviewed_calculation_refs),
        calculation_ids,
        owner_type="review",
        owner_id=selected.review_id,
        field="reviewed_calculation_refs",
    )
    _validate_known_refs(
        tuple(selected.required_proof_calculation_refs),
        calculation_ids,
        owner_type="review",
        owner_id=selected.review_id,
        field="required_proof_calculation_refs",
    )
    # Phase 3 persists E/K references on ReviewRecord, but not the complete
    # ordered M/C/J input preimage or stable typed Check subjects/corrections
    # needed to recompute and authorize the independent Review hash.  Exposing
    # this row as AVAILABLE after restart would trust the row's own claims.
    return ReconstructedResource.absent(
        AvailabilityStatus.UNAVAILABLE,
        "REVIEW_INPUT_PREIMAGE_NOT_PERSISTED",
    )


def _reconstruct_proof(
    snapshot: PersistedRunSnapshot,
    run: ResearchRun,
    evidence: tuple[EvidenceRecord, ...],
    calculations: tuple[CalculationRecord, ...],
    review: ReconstructedResource[ReviewRecord],
) -> ReconstructedResource[ProofClosure]:
    decision_by_id = _unique_by(snapshot.proof_policy_decisions, "decision_id", "proof decision")
    commitment_by_id = _unique_by(
        snapshot.proof_input_commitments,
        "commitment_id",
        "proof input commitment",
    )
    proof_by_id = _unique_by(snapshot.proofs, "proof_id", "proof")
    artifact_by_id = _unique_by(snapshot.proof_artifacts, "artifact_id", "proof artifact")
    verification_by_id = _unique_by(
        snapshot.proof_verifications,
        "verification_id",
        "proof verification",
    )
    del decision_by_id, commitment_by_id, artifact_by_id, verification_by_id
    calculation_by_id = {record.calculation_id: record for record in calculations}
    evidence_ids = {record.evidence_id for record in evidence}

    decision_calculations: set[str] = set()
    for decision in snapshot.proof_policy_decisions:
        if decision.run_id != run.run_id or decision.calculation_id not in calculation_by_id:
            raise _identity(
                "Proof policy decision belongs to another Run or Calculation",
                "proof",
                decision.decision_id,
            )
        calculation = calculation_by_id[decision.calculation_id]
        if decision.formula_id != calculation.formula_id:
            raise _integrity("Proof policy decision formula does not match its Calculation")
        if decision.calculation_id in decision_calculations:
            raise _integrity("Calculation has more than one Proof policy decision")
        decision_calculations.add(decision.calculation_id)

    commitment_calculations: set[str] = set()
    for commitment in snapshot.proof_input_commitments:
        if commitment.run_id != run.run_id or commitment.calculation_id not in calculation_by_id:
            raise _identity(
                "Proof input commitment belongs to another Run or Calculation",
                "proof",
                commitment.commitment_id,
            )
        calculation = calculation_by_id[commitment.calculation_id]
        if (
            commitment.formula_id != calculation.formula_id
            or commitment.capability_id != calculation.capability_id
            or commitment.implementation_hash != calculation.implementation_hash
        ):
            raise _integrity("Proof input commitment disagrees with its Calculation")
        _validate_known_refs(
            tuple(commitment.input_evidence_refs),
            evidence_ids,
            owner_type="proof_input_commitment",
            owner_id=commitment.commitment_id,
            field="input_evidence_refs",
        )
        if commitment.calculation_id in commitment_calculations:
            raise _integrity("Calculation has more than one Proof input commitment")
        commitment_calculations.add(commitment.calculation_id)

    proof_calculations: set[str] = set()
    for proof_record in snapshot.proofs:
        if (
            proof_record.run_id != run.run_id
            or proof_record.calculation_id not in calculation_by_id
        ):
            raise _identity(
                "Proof belongs to another Run or Calculation",
                "proof",
                proof_record.proof_id,
            )
        if proof_record.calculation_id in proof_calculations:
            raise _integrity("Calculation has more than one retained Proof record")
        proof_calculations.add(proof_record.calculation_id)
    for artifact in snapshot.proof_artifacts:
        if artifact.proof_id not in proof_by_id:
            raise _integrity(
                "Proof artifact references an absent Proof",
                resource_type="proof",
                resource_id=artifact.artifact_id,
            )
    verification_proofs: set[str] = set()
    for verification in snapshot.proof_verifications:
        proof_record = proof_by_id.get(verification.proof_id)
        if proof_record is None:
            raise _integrity(
                "Proof verification references an absent Proof",
                resource_type="proof",
                resource_id=verification.verification_id,
            )
        if (
            verification.image_id != proof_record.image_id
            or verification.receipt_hash != proof_record.receipt_hash
            or verification.journal_hash != proof_record.journal_hash
        ):
            raise _integrity("Proof verification identity/hash closure failed")
        if verification.proof_id in verification_proofs:
            raise _integrity("Proof has more than one retained verification")
        verification_proofs.add(verification.proof_id)

    for calculation in calculations:
        if calculation.proof_ref is not None and calculation.proof_ref not in proof_by_id:
            raise _integrity(
                "Calculation proof_ref names an absent Proof",
                resource_type="calculation",
                resource_id=calculation.calculation_id,
            )
    if not any(
        (
            snapshot.proof_policy_decisions,
            snapshot.proof_input_commitments,
            snapshot.proofs,
            snapshot.proof_artifacts,
            snapshot.proof_verifications,
        )
    ):
        reason = "PROOF_POLICY_NOT_PERSISTED"
        if review.value is not None and review.value.required_proof_calculation_refs:
            reason = "REQUIRED_PROOF_NOT_GENERATED"
        return ReconstructedResource.absent(AvailabilityStatus.UNAVAILABLE, reason)
    closure = ProofClosure(
        decisions=snapshot.proof_policy_decisions,
        input_commitments=snapshot.proof_input_commitments,
        proofs=snapshot.proofs,
        artifacts=snapshot.proof_artifacts,
        verifications=snapshot.proof_verifications,
    )
    return ReconstructedResource.available(closure)


def _reconstruct_canonical(
    snapshot: PersistedRunSnapshot,
    research_object: ResearchObject,
    goal: ResearchGoal,
    scheme: ResearchSchemeSnapshot,
    run: ResearchRun,
    planned: PlannedTaskGraph,
    actual: ReconstructedResource[ActualRuntimeGraph],
    tasks: tuple[Task, ...],
    evidence: tuple[EvidenceRecord, ...],
    calculations: tuple[CalculationRecord, ...],
    review: ReconstructedResource[ReviewRecord],
    proof: ReconstructedResource[ProofClosure],
) -> ReconstructedResource[CanonicalExecutionRecord]:
    _unique_by(snapshot.canonical_records, "record_id", "canonical execution record")
    if not snapshot.canonical_records:
        return ReconstructedResource.absent(
            AvailabilityStatus.NOT_GENERATED,
            "CANONICAL_EXECUTION_RECORD_NOT_GENERATED",
        )
    if len(snapshot.canonical_records) != 1:
        raise _integrity("Run has more than one Canonical Execution Record")
    record = snapshot.canonical_records[0]
    if record.run_id != run.run_id:
        raise _identity(
            "Canonical Execution Record belongs to another Run",
            "canonical_execution",
            record.record_id,
        )
    if (
        record.object_snapshot_ref != research_object.object_id
        or record.goal_ref != goal.goal_id
        or record.scheme_ref != scheme.scheme_id
    ):
        raise _identity(
            "Canonical Execution Record Object/Goal/Scheme closure failed",
            "canonical_execution",
            record.record_id,
        )
    actual_graph = actual.require(resource_type="graph", resource_id=run.run_id)
    if record.planned_graph != _model_json(planned) or record.actual_graph != _model_json(
        actual_graph
    ):
        raise _integrity(
            "Canonical Execution Record graph snapshots disagree with the exact persisted graphs",
            resource_type="canonical_execution",
            resource_id=record.record_id,
        )
    _validate_known_refs(
        tuple(record.task_refs),
        {item.task_id for item in tasks},
        owner_type="canonical_record",
        owner_id=record.record_id,
        field="task_refs",
    )
    _validate_known_refs(
        tuple(record.evidence_refs),
        {item.evidence_id for item in evidence},
        owner_type="canonical_record",
        owner_id=record.record_id,
        field="evidence_refs",
    )
    _validate_known_refs(
        tuple(record.calculation_refs),
        {item.calculation_id for item in calculations},
        owner_type="canonical_record",
        owner_id=record.record_id,
        field="calculation_refs",
    )
    review_ids = {review.value.review_id} if review.value is not None else set()
    _validate_known_refs(
        tuple(record.review_refs),
        review_ids,
        owner_type="canonical_record",
        owner_id=record.record_id,
        field="review_refs",
    )
    proof_ids = {item.proof_id for item in proof.value.proofs} if proof.value is not None else set()
    _validate_known_refs(
        tuple(record.proof_refs),
        proof_ids,
        owner_type="canonical_record",
        owner_id=record.record_id,
        field="proof_refs",
    )
    for calculation in calculations:
        if calculation.canonical_record_id is not None and (
            calculation.canonical_record_id != record.record_id
        ):
            raise _identity(
                "Calculation canonical_record_id names another record",
                "calculation",
                calculation.calculation_id,
            )
    return ReconstructedResource.available(record)


def _reconstruct_result(
    snapshot: PersistedRunSnapshot,
    run: ResearchRun,
    evidence: tuple[EvidenceRecord, ...],
    calculations: tuple[CalculationRecord, ...],
    canonical: ReconstructedResource[CanonicalExecutionRecord],
    review: ReconstructedResource[ReviewRecord],
    proof: ReconstructedResource[ProofClosure],
) -> ReconstructedResource[ReleasedResearchResult]:
    _unique_by(snapshot.released_results, "result_id", "released result")
    if not snapshot.released_results:
        return ReconstructedResource.absent(
            AvailabilityStatus.NOT_RELEASED,
            "RUN_NOT_RELEASED",
        )
    if len(snapshot.released_results) != 1:
        raise _integrity("Run has more than one Released Research Result")
    result = snapshot.released_results[0]
    if result.run_id != run.run_id:
        raise _identity(
            "Released Result belongs to another Run", "released_result", result.result_id
        )
    canonical_record = canonical.require(
        resource_type="canonical_execution",
        resource_id=result.canonical_record_id or "MISSING",
    )
    if result.canonical_record_id != canonical_record.record_id:
        raise _identity(
            "Released Result names another Canonical Execution Record",
            "released_result",
            result.result_id,
        )

    calculation_ids = {record.calculation_id for record in calculations}
    evidence_ids = {record.evidence_id for record in evidence}
    metric_ids = [metric.metric_id for metric in result.released_metrics]
    claim_ids = [claim.claim_id for claim in result.material_claims]
    if len(metric_ids) != len(set(metric_ids)) or len(claim_ids) != len(set(claim_ids)):
        raise _integrity("Released metric or Claim identities are duplicated")
    for metric in result.released_metrics:
        if metric.calculation_id not in calculation_ids:
            raise _integrity("Released metric references an absent Calculation")
        _validate_known_refs(
            tuple(metric.evidence_ids),
            evidence_ids,
            owner_type="released_metric",
            owner_id=metric.metric_id,
            field="evidence_ids",
        )
    judgment_ids = _exact_judgment_ids(result)
    for claim in result.material_claims:
        if claim.run_id != run.run_id:
            raise _identity("material Claim belongs to another Run", "claim", claim.claim_id)
        _validate_known_refs(
            tuple(claim.calculation_refs),
            calculation_ids,
            owner_type="claim",
            owner_id=claim.claim_id,
            field="calculation_refs",
        )
        _validate_known_refs(
            tuple(claim.evidence_refs),
            evidence_ids,
            owner_type="claim",
            owner_id=claim.claim_id,
            field="evidence_refs",
        )
        _validate_known_refs(
            tuple(claim.judgment_refs),
            judgment_ids,
            owner_type="claim",
            owner_id=claim.claim_id,
            field="judgment_refs",
        )
    if set(canonical_record.metric_refs) != set(metric_ids):
        raise _integrity("Canonical metric_refs do not exactly match the Released Result")
    if set(canonical_record.claim_refs) != set(claim_ids):
        raise _integrity("Canonical claim_refs do not exactly match the Released Result")
    if set(canonical_record.judgment_refs) != judgment_ids:
        raise _integrity("Canonical judgment_refs do not exactly match the Released Result")
    if review.value is not None:
        _validate_known_refs(
            tuple(review.value.reviewed_metric_refs),
            set(metric_ids),
            owner_type="review",
            owner_id=review.value.review_id,
            field="reviewed_metric_refs",
        )
        _validate_known_refs(
            tuple(review.value.reviewed_claim_refs),
            set(claim_ids),
            owner_type="review",
            owner_id=review.value.review_id,
            field="reviewed_claim_refs",
        )
        _validate_known_refs(
            tuple(review.value.reviewed_judgment_refs),
            judgment_ids,
            owner_type="review",
            owner_id=review.value.review_id,
            field="reviewed_judgment_refs",
        )
    _validate_released_proof_policy(result, proof)
    return ReconstructedResource.available(result)


def _validate_released_proof_policy(
    result: ReleasedResearchResult,
    proof: ReconstructedResource[ProofClosure],
) -> None:
    material_calculations = {metric.calculation_id for metric in result.released_metrics}
    if not material_calculations:
        return
    closure = proof.require(resource_type="proof", resource_id=result.run_id)
    decisions = {decision.calculation_id: decision for decision in closure.decisions}
    if set(decisions) & material_calculations != material_calculations:
        raise product_error(
            ErrorCodeV1.UNAVAILABLE,
            "material Calculations lack explicit retained Proof policy decisions",
            resource_type="research_run",
            resource_id=result.run_id,
            details={"reason_code": "PROOF_POLICY_NOT_PERSISTED"},
        )
    proofs = {item.calculation_id: item for item in closure.proofs}
    verification_by_proof = {item.proof_id: item for item in closure.verifications}
    for calculation_id in material_calculations:
        decision = decisions[calculation_id]
        if decision.requirement is ProofRequirement.NOT_REQUIRED:
            continue
        proof_record = proofs.get(calculation_id)
        if proof_record is None:
            raise _integrity("MUST_PROVE Calculation has no retained Proof")
        verification = verification_by_proof.get(proof_record.proof_id)
        if (
            proof_record.status is not ProofStatus.VERIFIED
            or verification is None
            or not verification.verified
            or verification.status is not ProofStatus.VERIFIED
        ):
            raise _integrity("MUST_PROVE Calculation lacks an exact VERIFIED Proof closure")


def _reconstruct_release_validation(
    snapshot: PersistedRunSnapshot,
    research_object: ResearchObject,
    run: ResearchRun,
    review: ReconstructedResource[ReviewRecord],
    proof: ReconstructedResource[ProofClosure],
    canonical: ReconstructedResource[CanonicalExecutionRecord],
    result: ReconstructedResource[ReleasedResearchResult],
) -> ReconstructedResource[PersistedReleaseValidation]:
    """Select the one exact successful validation without hiding cardinality."""

    _unique_by(snapshot.release_validations, "validation_id", "release validation")
    for validation in snapshot.release_validations:
        if validation.run_id != run.run_id or validation.object_id != research_object.object_id:
            raise _identity(
                "ReleaseValidation belongs to another Object or Run",
                "release_validation",
                validation.validation_id,
            )

    allowed = tuple(
        validation
        for validation in snapshot.release_validations
        if validation.decision == "ALLOWED"
    )
    if run.status is not RunStatus.RELEASED:
        if allowed:
            raise _integrity(
                "non-RELEASED Run contains an ALLOWED ReleaseValidation",
                resource_type="release_validation",
                resource_id=allowed[0].validation_id,
            )
        return ReconstructedResource.absent(
            AvailabilityStatus.NOT_RELEASED,
            "RELEASE_VALIDATION_NOT_ALLOWED",
        )
    if len(allowed) != 1:
        raise _integrity(
            "RELEASED Run requires exactly one ALLOWED ReleaseValidation",
            resource_type="research_run",
            resource_id=run.run_id,
            details={"reason_code": "RELEASE_VALIDATION_CARDINALITY_INVALID"},
        )

    validation = allowed[0]
    review_record = review.require(resource_type="review", resource_id=run.run_id)
    canonical_record = canonical.require(
        resource_type="canonical_execution",
        resource_id=run.run_id,
    )
    released_result = result.require(resource_type="released_result", resource_id=run.run_id)
    if (
        validation.review_id != review_record.review_id
        or validation.canonical_record_id != canonical_record.record_id
        or validation.released_result_id != released_result.result_id
    ):
        raise _identity(
            "ReleaseValidation does not bind the selected Review/Canonical/Result closure",
            "release_validation",
            validation.validation_id,
        )
    if (
        validation.release_policy_version != "phase4-release-eligibility/v1"
        or validation.review_policy_version != "phase4-independent-financial-review/v1"
        or validation.material_output_policy_version != "phase4-full-material-output/v1"
        or validation.artifact_policy_version != "phase4-html-required-pdf-optional/v1"
    ):
        raise _integrity(
            "ReleaseValidation uses an unsupported release policy family",
            resource_type="release_validation",
            resource_id=validation.validation_id,
        )
    if (
        review_record.input_snapshot_hash is None
        or validation.review_input_snapshot_hash != review_record.input_snapshot_hash
        or validation.released_at != released_result.released_at
        or validation.evaluated_at > validation.released_at
    ):
        raise _integrity(
            "ReleaseValidation Review hash or release time does not match retained records",
            resource_type="release_validation",
            resource_id=validation.validation_id,
        )

    closure = proof.require(resource_type="proof", resource_id=run.run_id)
    material_calculation_ids = {
        metric.calculation_id for metric in released_result.released_metrics
    }
    material_policy_ids = {
        decision.policy_id
        for decision in closure.decisions
        if decision.calculation_id in material_calculation_ids
    }
    if material_policy_ids != {validation.proof_policy_id}:
        raise _integrity(
            "ReleaseValidation Proof policy does not exactly cover material Calculations",
            resource_type="release_validation",
            resource_id=validation.validation_id,
        )
    # The legacy snapshot has no immutable release-time preimages for the
    # proof, material-output, artifact, and closure hashes.  Checking their
    # syntax here would turn attacker-controlled digest strings into apparent
    # restart authority.  Fail closed until the Parent-approved migration
    # persists those exact preimages and the reader recomputes every digest.
    raise product_error(
        ErrorCodeV1.UNAVAILABLE,
        "release validation cannot be reconstructed from the retained snapshot",
        resource_type="research_run",
        resource_id=run.run_id,
        details={"reason_code": "RELEASE_VALIDATION_PREIMAGE_NOT_PERSISTED"},
    )


def _reconstruct_report_artifacts(
    snapshot: PersistedRunSnapshot,
    run: ResearchRun,
    canonical: ReconstructedResource[CanonicalExecutionRecord],
    result: ReconstructedResource[ReleasedResearchResult],
) -> ReportArtifactClosure:
    _unique_by(snapshot.report_artifacts, "artifact_id", "report artifact")
    html_records: list[ReportArtifactRecord] = []
    pdf_records: list[ReportArtifactRecord] = []
    other: list[ReportArtifactRecord] = []
    for artifact in snapshot.report_artifacts:
        if artifact.run_id != run.run_id:
            raise _identity(
                "Report artifact belongs to another Run", "report_artifact", artifact.artifact_id
            )
        if artifact.artifact_type == "text/html":
            html_records.append(artifact)
        elif artifact.artifact_type == "application/pdf":
            pdf_records.append(artifact)
        else:
            other.append(artifact)
    if len(html_records) > 1 or len(pdf_records) > 1:
        raise _integrity("fixed report representation slot has multiple retained success records")
    if snapshot.report_artifacts:
        canonical_record = canonical.require(
            resource_type="canonical_execution",
            resource_id=run.run_id,
        )
        released_result = result.require(resource_type="released_result", resource_id=run.run_id)
        for artifact in snapshot.report_artifacts:
            if (
                artifact.canonical_record_id != canonical_record.record_id
                or artifact.released_result_id != released_result.result_id
            ):
                raise _identity(
                    "Report artifact release identity closure failed",
                    "report_artifact",
                    artifact.artifact_id,
                )
            if artifact.size_bytes <= 0:
                raise _integrity(
                    "successful Report artifact must have non-empty bytes",
                    resource_type="report_artifact",
                    resource_id=artifact.artifact_id,
                )
    absent_status = (
        AvailabilityStatus.NOT_GENERATED
        if result.value is not None
        else AvailabilityStatus.NOT_RELEASED
    )
    html_reason = "HTML_ARTIFACT_NOT_GENERATED" if result.value is not None else "RUN_NOT_RELEASED"
    pdf_reason = "PDF_ARTIFACT_NOT_GENERATED" if result.value is not None else "RUN_NOT_RELEASED"
    html = (
        ReconstructedResource.available(html_records[0])
        if html_records
        else ReconstructedResource.absent(absent_status, html_reason)
    )
    pdf = (
        ReconstructedResource.available(pdf_records[0])
        if pdf_records
        else ReconstructedResource.absent(absent_status, pdf_reason)
    )
    return ReportArtifactClosure(html=html, pdf=pdf, other=tuple(other))


def _reconstruct_anchor_manifests(
    snapshot: PersistedRunSnapshot,
    research_object: ResearchObject,
    run: ResearchRun,
    tasks: tuple[Task, ...],
    events: tuple[RuntimeEvent, ...],
    review: ReconstructedResource[ReviewRecord],
    canonical: ReconstructedResource[CanonicalExecutionRecord],
    result: ReconstructedResource[ReleasedResearchResult],
    artifacts: ReportArtifactClosure,
) -> ReconstructedResource[tuple[ValidatedAnchorManifest, ...]]:
    _unique_by(snapshot.anchor_manifests, "anchor_manifest_id", "anchor manifest")
    if not snapshot.anchor_manifests:
        return ReconstructedResource.absent(
            AvailabilityStatus.NOT_GENERATED,
            "ANCHOR_MANIFEST_NOT_GENERATED",
        )
    canonical_record = canonical.require(
        resource_type="canonical_execution",
        resource_id=run.run_id,
    )
    released_result = result.require(resource_type="released_result", resource_id=run.run_id)
    claim_by_id = {claim.claim_id: claim for claim in released_result.material_claims}
    metric_by_id = {metric.metric_id: metric for metric in released_result.released_metrics}
    task_ids = {task.task_id for task in tasks}
    event_by_id = {event.event_id: event for event in events}
    check_by_id = _unique_by(
        snapshot.review_check_identities,
        "check_id",
        "review check identity",
    )
    review_record = review.value
    html_id = artifacts.html.value.artifact_id if artifacts.html.value is not None else None
    pdf_id = artifacts.pdf.value.artifact_id if artifacts.pdf.value is not None else None
    expected_artifact_ids = {"HTML": html_id, "PDF": pdf_id}
    seen_claims: set[str] = set()
    for manifest in snapshot.anchor_manifests:
        try:
            revalidated = validate_anchor_manifest(
                manifest.payload,
                expected_object_id=research_object.object_id,
                expected_run_id=run.run_id,
                expected_canonical_record_id=canonical_record.record_id,
                expected_released_result_id=released_result.result_id,
                expected_claim_id=manifest.claim_id,
                expected_metric_id=manifest.metric_id,
            )
        except ArtifactProjectionError as exc:
            raise _integrity(
                "retained anchor manifest failed its schema, identity, or hash check",
                resource_type="anchor_manifest",
                resource_id=manifest.anchor_manifest_id,
                details={"reason_code": "ANCHOR_MANIFEST_INTEGRITY_FAILURE"},
            ) from exc
        if revalidated != manifest:
            raise _integrity(
                "retained anchor manifest value disagrees with its validated payload",
                resource_type="anchor_manifest",
                resource_id=manifest.anchor_manifest_id,
                details={"reason_code": "ANCHOR_MANIFEST_INTEGRITY_FAILURE"},
            )
        if (
            manifest.object_id != research_object.object_id
            or manifest.run_id != run.run_id
            or manifest.canonical_record_id != canonical_record.record_id
            or manifest.released_result_id != released_result.result_id
            or manifest.report_id != released_result.result_id
        ):
            raise _identity(
                "anchor manifest release identity closure failed",
                "anchor_manifest",
                manifest.anchor_manifest_id,
            )
        claim = claim_by_id.get(manifest.claim_id)
        metric = metric_by_id.get(manifest.metric_id)
        if claim is None or metric is None or claim.metric_id != metric.metric_id:
            raise _integrity(
                "anchor manifest references an absent or mismatched Claim/metric",
                resource_type="anchor_manifest",
                resource_id=manifest.anchor_manifest_id,
            )
        if manifest.claim_id in seen_claims:
            raise _integrity("Claim has more than one anchor manifest")
        seen_claims.add(manifest.claim_id)
        for anchor in manifest.representations:
            if anchor.artifact_id != expected_artifact_ids[anchor.format]:
                raise _integrity("representation anchor names a different Report artifact")
        for anchor in manifest.review_anchors:
            if review_record is None or anchor.review_id != review_record.review_id:
                raise _identity(
                    "Review anchor names another or absent Review",
                    "anchor_manifest",
                    manifest.anchor_manifest_id,
                )
            check = check_by_id.get(anchor.check_id)
            if check is None:
                raise product_error(
                    ErrorCodeV1.UNAVAILABLE,
                    (
                        "Review-check anchor cannot be verified without a stable "
                        "persisted check identity"
                    ),
                    resource_type="anchor_manifest",
                    resource_id=manifest.anchor_manifest_id,
                    details={"reason_code": "REVIEW_CHECK_IDENTITY_NOT_PERSISTED"},
                )
            if check.run_id != run.run_id or check.review_id != review_record.review_id:
                raise _identity(
                    "Review-check identity belongs to another Review or Run",
                    "review",
                    review_record.review_id,
                )
        for anchor in manifest.task_anchors:
            if anchor.task_id not in task_ids:
                raise _integrity("Task anchor references an absent actual-graph Task")
        for anchor in manifest.execution_anchors:
            if anchor.task_id not in task_ids:
                raise _integrity("execution anchor references an absent actual-graph Task")
            for event_id in anchor.event_refs:
                event = event_by_id.get(event_id)
                if event is None or event.task_id != anchor.task_id:
                    raise _integrity("execution anchor Event/Task closure failed")
    if seen_claims != set(claim_by_id):
        raise _integrity("anchor manifests do not close exactly over every material Claim")
    return ReconstructedResource.available(snapshot.anchor_manifests)


def _validate_terminal_release_closure(
    run: ResearchRun,
    review: ReconstructedResource[ReviewRecord],
    proof: ReconstructedResource[ProofClosure],
    canonical: ReconstructedResource[CanonicalExecutionRecord],
    result: ReconstructedResource[ReleasedResearchResult],
    release_validation: ReconstructedResource[PersistedReleaseValidation],
    artifacts: ReportArtifactClosure,
    manifests: ReconstructedResource[tuple[ValidatedAnchorManifest, ...]],
) -> None:
    if run.status is not RunStatus.RELEASED:
        if (
            result.value is not None
            or artifacts.html.value is not None
            or artifacts.pdf.value is not None
        ):
            raise _integrity("non-RELEASED Run exposes released result or report artifacts")
        return
    review_record = review.require(resource_type="review", resource_id=run.run_id)
    if review_record.status is not ReviewStatus.PASS:
        raise _integrity("RELEASED Run does not have an exact PASS Review")
    proof.require(resource_type="proof", resource_id=run.run_id)
    canonical_record = canonical.require(
        resource_type="canonical_execution",
        resource_id=run.run_id,
    )
    released_result = result.require(resource_type="released_result", resource_id=run.run_id)
    validation = release_validation.require(
        resource_type="release_validation",
        resource_id=run.run_id,
    )
    html = artifacts.html.require(resource_type="report_artifact", resource_id=run.run_id)
    manifests.require(resource_type="anchor_manifest", resource_id=run.run_id)
    if canonical_record.runtime_outcome != RunStatus.RELEASED.value:
        raise _integrity("RELEASED Run Canonical Execution Record is not terminal-success")
    if html.released_result_id != released_result.result_id:
        raise _integrity("required HTML artifact belongs to another Released Result")
    if validation.released_result_id != released_result.result_id:
        raise _integrity("ReleaseValidation belongs to another Released Result")


def _required_exact_one(
    records: tuple[ModelT, ...],
    *,
    id_field: str,
    expected_id: str,
    resource_type: str,
    root: bool = False,
) -> ModelT:
    _unique_by(records, id_field, resource_type)
    if not records:
        if root:
            raise product_error(
                ErrorCodeV1.NOT_FOUND,
                "the exact requested resource does not exist",
                resource_type=_public_resource_type(resource_type),
                resource_id=expected_id,
            )
        raise _integrity(
            f"persisted Run closure is missing {resource_type}",
            resource_type=_public_resource_type(resource_type),
            resource_id=expected_id,
        )
    if len(records) != 1:
        raise _integrity(f"persisted Run closure contains multiple {resource_type} rows")
    record = records[0]
    if getattr(record, id_field) != expected_id:
        raise _identity(
            f"{resource_type} identity does not match its exact persisted reference",
            resource_type,
            expected_id,
        )
    return record


def _unique_by(
    records: tuple[RecordT, ...],
    id_field: str,
    resource_type: str,
) -> dict[str, RecordT]:
    result: dict[str, RecordT] = {}
    for record in records:
        identifier = getattr(record, id_field)
        if not isinstance(identifier, str) or not identifier.strip():
            raise _integrity(f"{resource_type} contains a blank identity")
        if identifier in result:
            raise _integrity(
                f"{resource_type} identity is duplicated",
                details={"reason_code": "DUPLICATE_PERSISTED_IDENTITY"},
            )
        result[identifier] = record
    return result


def _validate_known_refs(
    refs: tuple[str, ...],
    known: set[str],
    *,
    owner_type: str,
    owner_id: str,
    field: str,
) -> None:
    _require_unique_refs(refs, owner_type=owner_type, owner_id=owner_id, field=field)
    unknown = set(refs) - known
    if unknown:
        raise _integrity(
            "persisted reference closure is incomplete",
            resource_type=owner_type,
            resource_id=owner_id,
            details={"reason_code": "REFERENCE_CLOSURE_INCOMPLETE", "field": field},
        )


def _require_unique_refs(
    refs: tuple[str, ...],
    *,
    owner_type: str,
    owner_id: str,
    field: str,
) -> None:
    if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
        raise _integrity(
            "persisted reference contains a blank identity",
            resource_type=owner_type,
            resource_id=owner_id,
            details={"field": field},
        )
    if len(refs) != len(set(refs)):
        raise _integrity(
            "persisted reference list contains duplicate identities",
            resource_type=owner_type,
            resource_id=owner_id,
            details={"field": field},
        )


def _exact_judgment_ids(result: ReleasedResearchResult) -> set[str]:
    judgment_ids: list[str] = []
    for judgment in result.judgments:
        identifier = judgment.get("judgment_id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise product_error(
                ErrorCodeV1.UNAVAILABLE,
                "released Judgment detail has no stable typed identity",
                resource_type="released_result",
                resource_id=result.result_id,
                details={"reason_code": "JUDGMENT_DETAIL_NOT_TYPED"},
            )
        judgment_ids.append(identifier)
    if len(judgment_ids) != len(set(judgment_ids)):
        raise _integrity("Released Result contains duplicate Judgment identities")
    return set(judgment_ids)


def _model_json(model: BaseModel) -> dict[str, object]:
    return model.model_dump(mode="json")


def _require_utc(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise _integrity(f"{field_name} must be an RFC3339 UTC instant")


def _require_nonblank(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise product_error(
            ErrorCodeV1.REQUEST_VALIDATION_ERROR,
            f"{field_name} must be a non-blank string",
            details={"reason_code": "INVALID_IDENTITY", "field": field_name},
        )


def _identity(message: str, resource_type: str, resource_id: str) -> ProductError:
    return product_error(
        ErrorCodeV1.IDENTITY_MISMATCH,
        message,
        resource_type=_public_resource_type(resource_type),
        resource_id=resource_id,
    )


def _integrity(
    message: str,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, object] | None = None,
) -> ProductError:
    return product_error(
        ErrorCodeV1.INTEGRITY_FAILURE,
        message,
        resource_type=(_public_resource_type(resource_type) if resource_type is not None else None),
        resource_id=resource_id,
        details=details,
    )


def _public_resource_type(resource_type: str) -> str:
    aliases = {
        "actual_runtime_graph": "graph",
        "canonical_record": "canonical_execution",
        "financial_review": "review",
        "planned_task_graph": "graph",
        "proof_artifact": "proof",
        "proof_closure": "proof",
        "proof_input_commitment": "proof",
        "proof_policy_decision": "proof",
        "proof_verification": "proof",
        "release_validation": "research_run",
        "released_metric": "released_result",
        "review_check": "review",
        "runtime_event": "projection",
    }
    return aliases.get(resource_type, resource_type)
