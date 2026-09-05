"""PostgreSQL durability contracts and pure fenced-admission transitions.

This module contains no storage implementation.  In particular it provides no
in-memory or SQLite substitute and no generic JSON-payload repository.  The
protocols describe the transaction and row-lock boundaries a production
PostgreSQL adapter must implement; the pure functions make scheduler state
changes deterministic and independently testable.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import InitVar, dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal, Protocol, Self, runtime_checkable

from pydantic import ValidationError

from src.domain.calculation import CalculationRecord
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.enums import TaskStatus
from src.domain.evidence import EvidenceRecord
from src.domain.proof import ProofRecord
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.report import ReportArtifactRecord
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.review import ReviewRecord
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph, Task
from src.phase4_product.admission import (
    CONFIRM_ROUTE_TEMPLATE,
    CREATE_OBJECT_ROUTE_TEMPLATE,
    PREPARE_ROUTE_TEMPLATE,
    ResearchRunDraftRecordV1,
    RunSchedulerAdmissionV1,
    SchedulerAdmissionState,
    confirmation_request_hash,
    create_object_request_hash,
    draft_hash_is_valid,
    prepare_request_hash,
)
from src.phase4_product.contracts import (
    LOCAL_ACCESS_SCOPE,
    ConfirmResearchRunRequestV1,
    CreateResearchObjectRequestV1,
    ErrorCodeV1,
    PrepareResearchRunRequestV1,
    ResearchRunDraftV1,
    RunAdmissionV1,
)
from src.phase4_product.errors import ProductError, product_error
from src.phase4_product.hashing import idempotency_key_digest
from src.phase4_product.reconstruction import (
    ExactRunSnapshotRepository,
    PersistedRunSnapshot,
    ProjectionWatermark,
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DurableIdempotencyOutcomeV1:
    """Immutable request-bound result stored independently of response metadata."""

    outcome_id: str
    effective_access_scope_key: Literal["LOCAL_SINGLE_USER"]
    idempotency_key_digest: str
    method: Literal["POST"]
    route_template: Literal["/api/research-runs"]
    confirmation_request_hash: str
    admission: RunAdmissionV1
    created_at: datetime

    def __post_init__(self) -> None:
        _validate_mutation_outcome_identity(
            outcome_id=self.outcome_id,
            effective_access_scope_key=self.effective_access_scope_key,
            idempotency_key_digest=self.idempotency_key_digest,
            method=self.method,
            route_template=self.route_template,
            expected_route=CONFIRM_ROUTE_TEMPLATE,
            request_hash=self.confirmation_request_hash,
            created_at=self.created_at,
        )
        if self.admission.confirmation_request_hash != self.confirmation_request_hash:
            raise _integrity_error(
                "idempotency outcome request hash disagrees with its immutable admission",
                resource_type="idempotency_outcome",
                resource_id=self.outcome_id,
                reason_code="IDEMPOTENCY_OUTCOME_IDENTITY_MISMATCH",
            )


@dataclass(frozen=True, slots=True)
class DurableObjectCreateOutcomeV1:
    """Request-bound durable identity returned by ``POST /api/objects`` replay."""

    outcome_id: str
    effective_access_scope_key: Literal["LOCAL_SINGLE_USER"]
    idempotency_key_digest: str
    method: Literal["POST"]
    route_template: Literal["/api/objects"]
    request_hash: str
    object_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        _validate_mutation_outcome_identity(
            outcome_id=self.outcome_id,
            effective_access_scope_key=self.effective_access_scope_key,
            idempotency_key_digest=self.idempotency_key_digest,
            method=self.method,
            route_template=self.route_template,
            expected_route=CREATE_OBJECT_ROUTE_TEMPLATE,
            request_hash=self.request_hash,
            created_at=self.created_at,
        )
        _require_nonblank(self.object_id, field_name="object_id")


@dataclass(frozen=True, slots=True)
class DurablePrepareOutcomeV1:
    """Exact immutable draft returned by a request-bound Prepare replay."""

    outcome_id: str
    effective_access_scope_key: Literal["LOCAL_SINGLE_USER"]
    idempotency_key_digest: str
    method: Literal["POST"]
    route_template: Literal["/api/research-runs/prepare"]
    request_hash: str
    draft: ResearchRunDraftV1
    created_at: datetime

    def __post_init__(self) -> None:
        _validate_mutation_outcome_identity(
            outcome_id=self.outcome_id,
            effective_access_scope_key=self.effective_access_scope_key,
            idempotency_key_digest=self.idempotency_key_digest,
            method=self.method,
            route_template=self.route_template,
            expected_route=PREPARE_ROUTE_TEMPLATE,
            request_hash=self.request_hash,
            created_at=self.created_at,
        )
        if self.draft.prepare_request_hash != self.request_hash:
            raise _integrity_error(
                "Prepare idempotency outcome request hash disagrees with its immutable draft",
                resource_type="research_run_draft",
                resource_id=self.draft.draft_id,
                reason_code="IDEMPOTENCY_OUTCOME_IDENTITY_MISMATCH",
            )
        if not draft_hash_is_valid(self.draft):
            raise _integrity_error(
                "stored Prepare outcome draft failed its immutable hash check",
                resource_type="research_run_draft",
                resource_id=self.draft.draft_id,
                reason_code="DRAFT_HASH_INTEGRITY_FAILURE",
            )


DurableMutationOutcomeV1 = (
    DurableObjectCreateOutcomeV1 | DurablePrepareOutcomeV1 | DurableIdempotencyOutcomeV1
)


@dataclass(frozen=True, slots=True)
class AtomicObjectCreateCommit:
    """All-or-nothing Object identity plus its durable replay outcome."""

    outcome: DurableObjectCreateOutcomeV1
    # Transient request metadata used to prove the stored digest.  Adapters
    # persist only ``outcome`` and must never retain this opaque raw key.
    idempotency_key: InitVar[str]
    request: CreateResearchObjectRequestV1
    research_object: ResearchObject

    def __post_init__(self, idempotency_key: str) -> None:
        _validate_atomic_idempotency_key(
            outcome=self.outcome,
            idempotency_key=idempotency_key,
            resource_type="research_object",
            resource_id=self.outcome.object_id,
        )
        if (
            self.outcome.request_hash != create_object_request_hash(self.request)
            or self.outcome.object_id != self.research_object.object_id
            or self.request.symbol != self.research_object.symbol
            or self.request.company_name != self.research_object.company_name
            or self.request.exchange != self.research_object.exchange
            or self.request.sector != self.research_object.sector
            or self.request.currency != self.research_object.currency
        ):
            raise _integrity_error(
                "Object creation request, outcome and Research Object disagree",
                resource_type="research_object",
                resource_id=self.outcome.object_id,
                reason_code="OBJECT_CREATE_OUTCOME_IDENTITY_MISMATCH",
            )


@dataclass(frozen=True, slots=True)
class AtomicPrepareCommit:
    """All-or-nothing Prepare draft, Goal, Scheme and replay outcome."""

    outcome: DurablePrepareOutcomeV1
    # Transient only; the raw key is not part of the durable write set.
    idempotency_key: InitVar[str]
    request: PrepareResearchRunRequestV1
    draft_record: ResearchRunDraftRecordV1
    goal: ResearchGoal
    scheme: ResearchSchemeSnapshot

    def __post_init__(self, idempotency_key: str) -> None:
        draft = self.outcome.draft
        _validate_atomic_idempotency_key(
            outcome=self.outcome,
            idempotency_key=idempotency_key,
            resource_type="research_run_draft",
            resource_id=draft.draft_id,
        )
        if not draft_hash_is_valid(draft):
            raise _integrity_error(
                "Prepare draft failed its immutable hash check",
                resource_type="research_run_draft",
                resource_id=draft.draft_id,
                reason_code="DRAFT_HASH_INTEGRITY_FAILURE",
            )
        if (
            self.outcome.request_hash != prepare_request_hash(self.request)
            or self.draft_record.consumed
            or self.draft_record.draft != draft
        ):
            raise _integrity_error(
                "Prepare outcome and unconsumed draft row disagree",
                resource_type="research_run_draft",
                resource_id=draft.draft_id,
                reason_code="PREPARE_WRITE_SET_IDENTITY_MISMATCH",
            )
        if self.goal.model_dump(mode="json") != draft.goal.model_dump(
            mode="json"
        ) or self.scheme.model_dump(mode="json") != draft.scheme_snapshot.model_dump(mode="json"):
            raise _integrity_error(
                "Prepare draft, Goal and Scheme do not form one exact identity closure",
                resource_type="research_run_draft",
                resource_id=draft.draft_id,
                reason_code="PREPARE_WRITE_SET_IDENTITY_MISMATCH",
            )


@dataclass(frozen=True, slots=True)
class AtomicConfirmCommit:
    """The exact all-or-nothing write set for one accepted Confirm request."""

    consumed_draft: ResearchRunDraftRecordV1
    idempotency_outcome: DurableIdempotencyOutcomeV1
    # Request/key are transient validation inputs; only their canonical
    # digests/hashes in ``idempotency_outcome`` are persisted.
    idempotency_key: InitVar[str]
    request: ConfirmResearchRunRequestV1
    scheduler_admission: RunSchedulerAdmissionV1
    goal: ResearchGoal
    scheme: ResearchSchemeSnapshot
    run: ResearchRun
    planned_graph: PlannedTaskGraph
    actual_graph: ActualRuntimeGraph | None
    tasks: tuple[Task, ...]
    initial_events: tuple[RuntimeEvent, ...]
    projection_revision: Literal[1] = 1

    def __post_init__(self, idempotency_key: str) -> None:
        public_admission = self.idempotency_outcome.admission
        draft = self.consumed_draft
        scheduler = self.scheduler_admission
        _validate_atomic_idempotency_key(
            outcome=self.idempotency_outcome,
            idempotency_key=idempotency_key,
            resource_type="idempotency_outcome",
            resource_id=self.idempotency_outcome.outcome_id,
        )
        if not draft_hash_is_valid(draft.draft):
            raise _integrity_error(
                "consumed Confirm draft failed its immutable hash check",
                resource_type="research_run_draft",
                resource_id=draft.draft.draft_id,
                reason_code="DRAFT_HASH_INTEGRITY_FAILURE",
            )
        if (
            self.idempotency_outcome.confirmation_request_hash
            != confirmation_request_hash(self.request)
            or self.request.draft_id != draft.draft.draft_id
            or self.request.draft_version != draft.draft.draft_version
            or self.request.draft_hash != draft.draft.draft_hash
            or self.request.research_object_id != draft.draft.object_id
        ):
            raise _integrity_error(
                "Confirm request does not bind the persisted outcome and consumed draft",
                resource_type="idempotency_outcome",
                resource_id=self.idempotency_outcome.outcome_id,
                reason_code="CONFIRM_REQUEST_HASH_MISMATCH",
            )
        if self.projection_revision != 1:
            raise _integrity_error(
                "initial admission projection revision must be exactly one",
                resource_type="projection",
                resource_id=self.run.run_id,
                reason_code="INITIAL_PROJECTION_REVISION_INVALID",
            )
        if not draft.consumed:
            raise _integrity_error(
                "atomic Confirm write set contains an unconsumed draft",
                resource_type="research_run_draft",
                resource_id=draft.draft.draft_id,
                reason_code="DRAFT_NOT_CONSUMED",
            )
        if (
            draft.consumed_admission_id != public_admission.admission_id
            or draft.consumed_run_id != public_admission.run_id
            or public_admission.run_id != self.run.run_id
            or public_admission.object_id != self.run.research_object_id
            or public_admission.goal_id != self.goal.goal_id
            or public_admission.scheme_id != self.scheme.scheme_id
            or self.run.goal_id != self.goal.goal_id
            or self.run.scheme_id != self.scheme.scheme_id
            or public_admission.planned_graph_id != self.planned_graph.graph_id
            or self.run.planned_graph_id != self.planned_graph.graph_id
            or scheduler.admission_id != public_admission.admission_id
            or scheduler.run_id != self.run.run_id
            or scheduler.idempotency_outcome_id != self.idempotency_outcome.outcome_id
        ):
            raise _integrity_error(
                "atomic Confirm write-set identities do not form one admission",
                resource_type="scheduler_admission",
                resource_id=scheduler.admission_id,
                reason_code="CONFIRM_WRITE_SET_IDENTITY_MISMATCH",
            )
        if (
            public_admission.draft_id != draft.draft.draft_id
            or public_admission.draft_version != draft.draft.draft_version
            or public_admission.draft_hash != draft.draft.draft_hash
            or public_admission.object_id != draft.draft.object_id
        ):
            raise _integrity_error(
                "consumed draft and immutable admission identities disagree",
                resource_type="research_run_draft",
                resource_id=draft.draft.draft_id,
                reason_code="CONFIRM_WRITE_SET_IDENTITY_MISMATCH",
            )
        if (
            scheduler.state is not SchedulerAdmissionState.PENDING
            or scheduler.delivery_attempt_count != 0
            or scheduler.lease_generation != 0
            or scheduler.next_attempt_at != public_admission.admitted_at
            or scheduler.created_at != public_admission.admitted_at
            or scheduler.updated_at != public_admission.admitted_at
            or any(
                value is not None
                for value in (
                    scheduler.lease_owner,
                    scheduler.lease_expires_at,
                    scheduler.start_committed_at,
                    scheduler.run_started_event_id,
                    scheduler.run_started_sequence,
                    scheduler.acknowledged_at,
                    scheduler.failed_at,
                    scheduler.failure_code,
                )
            )
        ):
            raise _integrity_error(
                "atomic Confirm must insert one pristine PENDING scheduler admission",
                resource_type="scheduler_admission",
                resource_id=scheduler.admission_id,
                reason_code="INITIAL_ADMISSION_STATE_INVALID",
            )
        if (
            self.run.status.value != public_admission.status
            or self.run.started_at is not None
            or self.run.completed_at is not None
        ):
            raise _integrity_error(
                "admitted Run is not in the pristine frozen PLANNING state",
                resource_type="research_run",
                resource_id=self.run.run_id,
                reason_code="CONFIRM_RUN_STATUS_MISMATCH",
            )
        if (
            self.goal.research_object_id != self.run.research_object_id
            or self.scheme.research_object_id != self.run.research_object_id
            or self.scheme.goal_id != self.goal.goal_id
            or self.run.as_of != self.goal.as_of
            or self.scheme.confirmed_at is None
            or self.planned_graph.run_id != self.run.run_id
        ):
            raise _integrity_error(
                "atomic Confirm Object/Goal/Scheme/graph closure failed",
                resource_type="research_run",
                resource_id=self.run.run_id,
                reason_code="CONFIRM_WRITE_SET_IDENTITY_MISMATCH",
            )
        draft_goal = draft.draft.goal.model_dump(mode="json")
        committed_goal = self.goal.model_dump(mode="json")
        draft_scheme = draft.draft.scheme_snapshot.model_dump(mode="json")
        committed_scheme = self.scheme.model_dump(mode="json")
        committed_scheme["confirmed_at"] = draft_scheme["confirmed_at"]
        if committed_goal != draft_goal or committed_scheme != draft_scheme:
            raise _integrity_error(
                "confirmed Goal/Scheme differ from the immutable prepared draft",
                resource_type="research_run_draft",
                resource_id=draft.draft.draft_id,
                reason_code="CONFIRM_WRITE_SET_IDENTITY_MISMATCH",
            )
        if self.actual_graph is None:
            if self.run.actual_graph_id is not None:
                raise _integrity_error(
                    "Run names an Actual Graph absent from its atomic write set",
                    resource_type="graph",
                    resource_id=self.run.actual_graph_id,
                    reason_code="ACTUAL_GRAPH_IDENTITY_MISMATCH",
                )
            authoritative_tasks = tuple(self.planned_graph.tasks)
        else:
            if (
                self.actual_graph.run_id != self.run.run_id
                or self.run.actual_graph_id != self.actual_graph.graph_id
            ):
                raise _integrity_error(
                    "Actual Graph does not belong to the admitted Run",
                    resource_type="graph",
                    resource_id=self.actual_graph.graph_id,
                    reason_code="ACTUAL_GRAPH_IDENTITY_MISMATCH",
                )
            authoritative_tasks = tuple(self.actual_graph.tasks)
        task_ids = [task.task_id for task in self.tasks]
        authoritative_task_ids = [task.task_id for task in authoritative_tasks]
        planned_tasks = tuple(self.planned_graph.tasks)
        graph_tasks = (
            (*planned_tasks, *tuple(self.actual_graph.tasks))
            if self.actual_graph is not None
            else planned_tasks
        )
        task_index = {task.task_id: task for task in self.tasks}
        authoritative_task_index = {task.task_id: task for task in authoritative_tasks}
        if (
            len(task_ids) != len(set(task_ids))
            or len(authoritative_task_ids) != len(set(authoritative_task_ids))
            or set(task_ids) != set(authoritative_task_ids)
            or any(task.run_id != self.run.run_id for task in self.tasks)
            or any(task.run_id != self.run.run_id for task in graph_tasks)
            or any(
                task_index[task_id].model_dump(mode="json")
                != authoritative_task_index[task_id].model_dump(mode="json")
                for task_id in task_index.keys() & authoritative_task_index.keys()
            )
            or (
                self.actual_graph is not None
                and [task.model_dump(mode="json") for task in self.actual_graph.tasks]
                != [task.model_dump(mode="json") for task in self.planned_graph.tasks]
            )
        ):
            raise _integrity_error(
                "atomic Confirm Task rows disagree with the authoritative graph",
                resource_type="research_run",
                resource_id=self.run.run_id,
                reason_code="TASK_GRAPH_IDENTITY_MISMATCH",
            )
        if not self.initial_events:
            raise _integrity_error(
                "atomic Confirm requires its initial RuntimeEvents",
                resource_type="projection",
                resource_id=self.run.run_id,
                reason_code="INITIAL_EVENTS_MISSING",
            )
        if [event.sequence for event in self.initial_events] != list(
            range(1, len(self.initial_events) + 1)
        ) or any(event.run_id != self.run.run_id for event in self.initial_events):
            raise _integrity_error(
                "atomic Confirm initial RuntimeEvents are not one contiguous Run sequence",
                resource_type="projection",
                resource_id=self.run.run_id,
                reason_code="INITIAL_EVENT_SEQUENCE_INVALID",
            )
        event_ids = [event.event_id for event in self.initial_events]
        if (
            len(event_ids) != len(set(event_ids))
            or sum(event.type is RuntimeEventType.RUN_CREATED for event in self.initial_events) != 1
        ):
            raise _integrity_error(
                "atomic Confirm requires unique Events and exactly one run.created",
                resource_type="projection",
                resource_id=self.run.run_id,
                reason_code="INITIAL_EVENT_IDENTITY_INVALID",
            )
        allowed_initial_events = {
            RuntimeEventType.RUN_CREATED,
            RuntimeEventType.SCHEME_GENERATED,
            RuntimeEventType.SCHEME_CONFIRMED,
            RuntimeEventType.PLAN_GENERATED,
            RuntimeEventType.TASK_CREATED,
        }
        if any(event.type not in allowed_initial_events for event in self.initial_events):
            raise _integrity_error(
                "atomic Confirm contains a RuntimeEvent outside the frozen setup phase",
                resource_type="projection",
                resource_id=self.run.run_id,
                reason_code="INITIAL_EVENT_PHASE_INVALID",
            )
        expected_event_types = (
            RuntimeEventType.RUN_CREATED,
            RuntimeEventType.SCHEME_GENERATED,
            RuntimeEventType.SCHEME_CONFIRMED,
            RuntimeEventType.PLAN_GENERATED,
            *(RuntimeEventType.TASK_CREATED for _task in self.planned_graph.tasks),
        )
        if tuple(event.type for event in self.initial_events) != expected_event_types:
            raise _integrity_error(
                "atomic Confirm initial RuntimeEvent inventory/order is incomplete",
                resource_type="projection",
                resource_id=self.run.run_id,
                reason_code="INITIAL_EVENT_IDENTITY_INVALID",
            )
        expected_non_task_payloads = (
            {"object_id": self.run.research_object_id},
            {
                "scheme_id": self.scheme.scheme_id,
                "generated_by": self.scheme.generated_by,
                "generated_at": self.scheme.created_at.isoformat(),
                "generation_stage": "prepare",
                "retrospective": True,
            },
            {"scheme_id": self.scheme.scheme_id},
            {
                "graph_id": self.planned_graph.graph_id,
                "task_count": len(self.planned_graph.tasks),
            },
        )
        for event, expected_payload in zip(
            self.initial_events[:4],
            expected_non_task_payloads,
            strict=True,
        ):
            if event.task_id is not None or event.payload != expected_payload:
                raise _integrity_error(
                    "Confirm setup RuntimeEvent payload does not bind its write-set record",
                    resource_type="projection",
                    resource_id=self.run.run_id,
                    reason_code="INITIAL_EVENT_IDENTITY_INVALID",
                )
        created_task_ids: list[str] = []
        for event, planned_task in zip(
            self.initial_events[4:],
            self.planned_graph.tasks,
            strict=True,
        ):
            if event.type is RuntimeEventType.TASK_CREATED:
                task = task_index.get(event.task_id or "")
                if (
                    task is None
                    or task.status is not TaskStatus.CREATED
                    or task.task_id != planned_task.task_id
                    or event.payload != {"task_type": task.task_type}
                ):
                    raise _integrity_error(
                        "task.created does not bind one CREATED Task in the Confirm write set",
                        resource_type="projection",
                        resource_id=self.run.run_id,
                        reason_code="INITIAL_EVENT_IDENTITY_INVALID",
                    )
                created_task_ids.append(task.task_id)
        if len(created_task_ids) != len(set(created_task_ids)) or set(created_task_ids) != set(
            task_index
        ):
            raise _integrity_error(
                "task.created events must cover the exact Confirm Task set",
                resource_type="projection",
                resource_id=self.run.run_id,
                reason_code="INITIAL_EVENT_IDENTITY_INVALID",
            )


@dataclass(frozen=True, slots=True)
class ProjectionCommitFence:
    """Optimistic Run revision fence held under a PostgreSQL row lock."""

    run_id: str
    expected_revision: int

    def __post_init__(self) -> None:
        _require_nonblank(self.run_id, field_name="run_id")
        if isinstance(self.expected_revision, bool) or self.expected_revision < 1:
            raise _request_error("expected_revision", "INVALID_PROJECTION_REVISION")


@dataclass(frozen=True, slots=True)
class ProjectionWriteSet:
    """Typed projection members committed with events and one revision bump.

    Empty member collections mean "no writes of this type" and never mean
    "replace by an inferred/default JSON object".  The PostgreSQL adapter must
    persist fields and relations in reviewed typed columns/tables.
    """

    fence: ProjectionCommitFence
    run: ResearchRun | None = None
    planned_graph: PlannedTaskGraph | None = None
    actual_graph: ActualRuntimeGraph | None = None
    tasks: tuple[Task, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    calculations: tuple[CalculationRecord, ...] = ()
    reviews: tuple[ReviewRecord, ...] = ()
    proofs: tuple[ProofRecord, ...] = ()
    canonical_records: tuple[CanonicalExecutionRecord, ...] = ()
    released_results: tuple[ReleasedResearchResult, ...] = ()
    report_artifacts: tuple[ReportArtifactRecord, ...] = ()
    events: tuple[RuntimeEvent, ...] = ()

    def __post_init__(self) -> None:
        run_id = self.fence.run_id
        owned_records: tuple[object, ...] = (
            *((self.run,) if self.run is not None else ()),
            *((self.planned_graph,) if self.planned_graph is not None else ()),
            *((self.actual_graph,) if self.actual_graph is not None else ()),
            *self.tasks,
            *self.evidence,
            *self.calculations,
            *self.reviews,
            *self.proofs,
            *self.canonical_records,
            *self.released_results,
            *self.report_artifacts,
            *self.events,
        )
        if not owned_records:
            raise _request_error("write_set", "EMPTY_PROJECTION_WRITE_SET")
        if any(getattr(record, "run_id", run_id) != run_id for record in owned_records):
            raise _integrity_error(
                "projection write set contains a foreign Run identity",
                resource_type="projection",
                resource_id=run_id,
                reason_code="PROJECTION_WRITE_SET_IDENTITY_MISMATCH",
            )


@runtime_checkable
class PostgreSQLAdmissionRepository(Protocol):
    """Exact row-locked admission operations inside the owning transaction."""

    dialect_name: Literal["postgresql"]

    async def get_draft_for_update(
        self,
        draft_id: str,
    ) -> ResearchRunDraftRecordV1 | None: ...

    async def get_idempotency_outcome_for_update(
        self,
        *,
        effective_access_scope_key: Literal["LOCAL_SINGLE_USER"],
        method: str,
        route_template: str,
        idempotency_key_digest: str,
    ) -> DurableMutationOutcomeV1 | None: ...

    async def insert_object_create_commit(self, commit: AtomicObjectCreateCommit) -> None:
        """Insert Object plus immutable outcome; never commit internally."""

    async def insert_prepare_commit(self, commit: AtomicPrepareCommit) -> None:
        """Insert Goal/Scheme/draft/outcome atomically; never commit internally."""

    async def insert_confirm_commit(self, commit: AtomicConfirmCommit) -> None:
        """Insert the whole Confirm write set; never commit internally."""


@runtime_checkable
class PostgreSQLSchedulerAdmissionRepository(Protocol):
    """Fenced scheduler rows accessed under ``SELECT ... FOR UPDATE``."""

    dialect_name: Literal["postgresql"]

    async def get_for_update(
        self,
        admission_id: str,
    ) -> RunSchedulerAdmissionV1 | None: ...

    async def list_due_admission_ids(
        self,
        *,
        due_at: datetime,
        limit: int,
    ) -> Sequence[str]:
        """Return stable IDs only; each ID must be claimed under its own row lock."""

    async def replace_fenced(
        self,
        admission: RunSchedulerAdmissionV1,
        *,
        expected_lease_generation: int,
    ) -> bool:
        """CAS the typed row and return false when the lease fence is stale."""


@runtime_checkable
class PostgreSQLProjectionRepository(ExactRunSnapshotRepository, Protocol):
    """Typed projection writes and exact same-snapshot reconstruction reads."""

    dialect_name: Literal["postgresql"]

    async def publish(self, write_set: ProjectionWriteSet) -> ProjectionWatermark:
        """Persist members/events and bump revision exactly once, without committing."""

    async def read_exact_run_snapshot(
        self,
        *,
        object_id: str,
        run_id: str,
    ) -> PersistedRunSnapshot | None:
        """Read every member plus revision/event tail in one MVCC snapshot."""


@runtime_checkable
class PostgreSQLProductUnitOfWork(Protocol):
    """One production PostgreSQL transaction; repositories never self-commit."""

    dialect_name: Literal["postgresql"]
    admission: PostgreSQLAdmissionRepository
    scheduler: PostgreSQLSchedulerAdmissionRepository
    projection: PostgreSQLProjectionRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


@runtime_checkable
class PostgreSQLProductUnitOfWorkFactory(Protocol):
    """Create a fresh PostgreSQL transaction boundary per business unit."""

    def __call__(self) -> PostgreSQLProductUnitOfWork: ...


class DurabilityCapability(StrEnum):
    DURABLE_DRAFT_CONSUMPTION = "DURABLE_DRAFT_CONSUMPTION"
    REQUEST_BOUND_IDEMPOTENCY = "REQUEST_BOUND_IDEMPOTENCY"
    FENCED_SCHEDULER_ADMISSION = "FENCED_SCHEDULER_ADMISSION"
    PROJECTION_REVISION = "PROJECTION_REVISION"
    ATOMIC_EVENT_PROJECTION_PUBLICATION = "ATOMIC_EVENT_PROJECTION_PUBLICATION"
    UNIQUE_TERMINAL_FINALIZATION = "UNIQUE_TERMINAL_FINALIZATION"
    STABLE_REVIEW_CHECK_IDENTITIES = "STABLE_REVIEW_CHECK_IDENTITIES"
    ARTIFACT_REPRESENTATION_SLOTS = "ARTIFACT_REPRESENTATION_SLOTS"
    APPEND_ONLY_ARTIFACT_ATTEMPTS = "APPEND_ONLY_ARTIFACT_ATTEMPTS"
    ANCHOR_MANIFESTS = "ANCHOR_MANIFESTS"
    RELEASE_VALIDATION = "RELEASE_VALIDATION"


@dataclass(frozen=True, slots=True)
class DurabilityCapabilities:
    """Observed database capabilities, never inferred from application classes."""

    backend: str
    schema_revision: str | None
    supported: frozenset[DurabilityCapability]

    @classmethod
    def phase3_postgresql(cls) -> DurabilityCapabilities:
        """Describe the inspected Phase 3 migration head without overstating it."""

        return cls(
            backend="postgresql",
            schema_revision="20260904_0006",
            supported=frozenset(),
        )


@dataclass(frozen=True, slots=True)
class MigrationGap:
    code: str
    capability: DurabilityCapability
    contract_requirement: str
    schema_delta: str
    why_phase3_is_insufficient: str


_GAPS_BY_CAPABILITY: dict[DurabilityCapability, MigrationGap] = {
    DurabilityCapability.DURABLE_DRAFT_CONSUMPTION: MigrationGap(
        code="P4_DURABLE_DRAFT_CONSUMPTION",
        capability=DurabilityCapability.DURABLE_DRAFT_CONSUMPTION,
        contract_requirement=(
            "Persist immutable draft hash/version/expiry and one consumption tombstone."
        ),
        schema_delta="Add typed draft lifecycle columns and atomic consumption constraints.",
        why_phase3_is_insufficient=(
            "research_run_drafts retains a generic payload but no constrained consumption identity."
        ),
    ),
    DurabilityCapability.REQUEST_BOUND_IDEMPOTENCY: MigrationGap(
        code="P4_REQUEST_BOUND_IDEMPOTENCY",
        capability=DurabilityCapability.REQUEST_BOUND_IDEMPOTENCY,
        contract_requirement="Persist one scope/method/route/key/request-bound immutable outcome.",
        schema_delta=(
            "Add an idempotency outcomes relation with scoped uniqueness and admission FK."
        ),
        why_phase3_is_insufficient="The only idempotency authority is process-local memory.",
    ),
    DurabilityCapability.FENCED_SCHEDULER_ADMISSION: MigrationGap(
        code="P4_FENCED_SCHEDULER_ADMISSION",
        capability=DurabilityCapability.FENCED_SCHEDULER_ADMISSION,
        contract_requirement=(
            "Persist PENDING/LEASED/ACKNOWLEDGED/FAILED delivery with generations."
        ),
        schema_delta=(
            "Add scheduler admission, due-time, lease, fence, start and ack columns/constraints."
        ),
        why_phase3_is_insufficient=(
            "FastAPI background delivery has no durable outbox or worker fence."
        ),
    ),
    DurabilityCapability.PROJECTION_REVISION: MigrationGap(
        code="P4_PROJECTION_REVISION",
        capability=DurabilityCapability.PROJECTION_REVISION,
        contract_requirement="Store a monotonic per-Run projection_revision beginning at one.",
        schema_delta="Add a constrained projection_revision column to the Run authority.",
        why_phase3_is_insufficient="research_runs has no durable projection revision.",
    ),
    DurabilityCapability.ATOMIC_EVENT_PROJECTION_PUBLICATION: MigrationGap(
        code="P4_ATOMIC_EVENT_PROJECTION_PUBLICATION",
        capability=DurabilityCapability.ATOMIC_EVENT_PROJECTION_PUBLICATION,
        contract_requirement=(
            "Commit state, events and one revision bump in one serialized transaction."
        ),
        schema_delta=(
            "Bind typed child writes, event append and revision CAS in one PostgreSQL UoW."
        ),
        why_phase3_is_insufficient=(
            "Aggregate and RuntimeEvent repositories open separate transactions."
        ),
    ),
    DurabilityCapability.UNIQUE_TERMINAL_FINALIZATION: MigrationGap(
        code="P4_UNIQUE_TERMINAL_FINALIZATION",
        capability=DurabilityCapability.UNIQUE_TERMINAL_FINALIZATION,
        contract_requirement="Retain exactly one final failure fact/event per unsuccessful Run.",
        schema_delta=(
            "Add terminal fact uniqueness and constraints binding status/event/completion."
        ),
        why_phase3_is_insufficient=(
            "No terminal fact relation prevents duplicate finalization paths."
        ),
    ),
    DurabilityCapability.STABLE_REVIEW_CHECK_IDENTITIES: MigrationGap(
        code="P4_STABLE_REVIEW_CHECK_IDENTITIES",
        capability=DurabilityCapability.STABLE_REVIEW_CHECK_IDENTITIES,
        contract_requirement="Address Review checks by stable check_id and typed subject identity.",
        schema_delta=(
            "Add Review-check identity/subject relations; do not derive IDs from text or order."
        ),
        why_phase3_is_insufficient="Review checks live in JSON and have no check_id.",
    ),
    DurabilityCapability.ARTIFACT_REPRESENTATION_SLOTS: MigrationGap(
        code="P4_ARTIFACT_REPRESENTATION_SLOTS",
        capability=DurabilityCapability.ARTIFACT_REPRESENTATION_SLOTS,
        contract_requirement="Persist independent fixed HTML/PDF availability slots.",
        schema_delta=(
            "Add typed report/format slot rows with release and Object identity constraints."
        ),
        why_phase3_is_insufficient=(
            "Only successful artifact payloads exist; absence has no exact state."
        ),
    ),
    DurabilityCapability.APPEND_ONLY_ARTIFACT_ATTEMPTS: MigrationGap(
        code="P4_APPEND_ONLY_ARTIFACT_ATTEMPTS",
        capability=DurabilityCapability.APPEND_ONLY_ARTIFACT_ATTEMPTS,
        contract_requirement=(
            "Retain every per-format generation attempt and safe terminal outcome."
        ),
        schema_delta="Add append-only generation-attempt rows and current-attempt slot FK.",
        why_phase3_is_insufficient="Failed/pending attempts and retry history are not retained.",
    ),
    DurabilityCapability.ANCHOR_MANIFESTS: MigrationGap(
        code="P4_ANCHOR_MANIFESTS",
        capability=DurabilityCapability.ANCHOR_MANIFESTS,
        contract_requirement="Persist immutable hash-bound Claim anchor manifests and exact joins.",
        schema_delta=(
            "Add manifest and anchor identity relations bound to O/R/X/L/report/Claim/metric."
        ),
        why_phase3_is_insufficient="No durable anchor manifest or anchor relation exists.",
    ),
    DurabilityCapability.RELEASE_VALIDATION: MigrationGap(
        code="P4_RELEASE_VALIDATION",
        capability=DurabilityCapability.RELEASE_VALIDATION,
        contract_requirement=(
            "Persist exactly one policy/hash-bound ALLOWED validation for release."
        ),
        schema_delta=(
            "Add ReleaseValidationRecord relation with unique release closure constraints."
        ),
        why_phase3_is_insufficient=(
            "Release eligibility is evaluated transiently and is not retained."
        ),
    ),
}

REQUIRED_PHASE4_DURABILITY_CAPABILITIES = frozenset(_GAPS_BY_CAPABILITY)


@dataclass(frozen=True, slots=True)
class DurabilityPreflight:
    backend: str
    schema_revision: str | None
    missing_capabilities: tuple[DurabilityCapability, ...]
    migration_gaps: tuple[MigrationGap, ...]

    @property
    def postgresql(self) -> bool:
        return self.backend == "postgresql"

    @property
    def migration_required(self) -> bool:
        return bool(self.migration_gaps)

    @property
    def ready(self) -> bool:
        return self.postgresql and not self.missing_capabilities

    def require_ready(self) -> None:
        """Fail closed instead of silently selecting SQLite/memory/JSON fallbacks."""

        if not self.postgresql:
            raise product_error(
                ErrorCodeV1.UNAVAILABLE,
                "Phase 4 durable Product execution requires PostgreSQL",
                resource_type="projection",
                resource_id="phase4-durability",
                details={"reason_code": "POSTGRESQL_REQUIRED"},
            )
        if self.missing_capabilities:
            raise product_error(
                ErrorCodeV1.UNAVAILABLE,
                "the installed schema cannot satisfy the frozen Phase 4 durability contract",
                resource_type="projection",
                resource_id="phase4-durability",
                details={"reason_code": "PHASE4_MIGRATION_REQUIRED"},
            )


def evaluate_durability_preflight(
    capabilities: DurabilityCapabilities,
) -> DurabilityPreflight:
    """Return the complete deterministic gap set for an observed schema."""

    missing = tuple(
        capability
        for capability in DurabilityCapability
        if capability not in capabilities.supported
    )
    gaps = tuple(_GAPS_BY_CAPABILITY[capability] for capability in missing)
    return DurabilityPreflight(
        backend=capabilities.backend.strip().lower(),
        schema_revision=capabilities.schema_revision,
        missing_capabilities=missing,
        migration_gaps=gaps,
    )


def phase3_postgresql_preflight() -> DurabilityPreflight:
    """Expose the audited Phase 3 head decision: a Phase 4 migration is required."""

    return evaluate_durability_preflight(DurabilityCapabilities.phase3_postgresql())


@dataclass(frozen=True, slots=True)
class SchedulerLeaseFence:
    admission_id: str
    run_id: str
    owner: str
    generation: int
    expires_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("admission_id", "run_id", "owner"):
            _require_nonblank(getattr(self, field_name), field_name=field_name)
        if isinstance(self.generation, bool) or self.generation < 1:
            raise _request_error("generation", "INVALID_LEASE_GENERATION")
        _require_utc(self.expires_at, field_name="expires_at")


def lease_scheduler_admission(
    admission: RunSchedulerAdmissionV1,
    *,
    worker_id: str,
    leased_at: datetime,
    lease_duration: timedelta,
) -> tuple[RunSchedulerAdmissionV1, SchedulerLeaseFence]:
    """Lease a due PENDING or expired LEASED admission with a new fence."""

    _require_nonblank(worker_id, field_name="worker_id")
    _require_utc(leased_at, field_name="leased_at")
    if lease_duration <= timedelta(0):
        raise _request_error("lease_duration", "INVALID_LEASE_DURATION")
    if admission.state in {
        SchedulerAdmissionState.ACKNOWLEDGED,
        SchedulerAdmissionState.FAILED,
    }:
        raise _scheduler_error(
            ErrorCodeV1.TERMINAL,
            admission,
            "scheduler admission is already terminal",
            "ADMISSION_TERMINAL",
        )
    if admission.state is SchedulerAdmissionState.LEASED:
        if admission.lease_expires_at is None:
            raise _scheduler_integrity(admission, "LEASE_FIELDS_INCOMPLETE")
        if admission.lease_expires_at > leased_at:
            raise _scheduler_error(
                ErrorCodeV1.CONFLICT,
                admission,
                "scheduler admission is held by a current worker lease",
                "ADMISSION_LEASE_HELD",
            )
    elif admission.next_attempt_at is not None and admission.next_attempt_at > leased_at:
        raise _scheduler_error(
            ErrorCodeV1.CONFLICT,
            admission,
            "scheduler admission is not due",
            "ADMISSION_NOT_DUE",
        )
    if admission.delivery_attempt_count >= admission.max_delivery_attempts:
        raise _scheduler_error(
            ErrorCodeV1.TERMINAL,
            admission,
            "scheduler admission delivery attempts are exhausted",
            "ADMISSION_DELIVERY_EXHAUSTED",
        )
    _require_transition_time(admission, leased_at)
    generation = admission.lease_generation + 1
    expires_at = leased_at + lease_duration
    leased = _replace_admission(
        admission,
        state=SchedulerAdmissionState.LEASED,
        delivery_attempt_count=admission.delivery_attempt_count + 1,
        next_attempt_at=None,
        lease_owner=worker_id,
        lease_generation=generation,
        lease_expires_at=expires_at,
        updated_at=leased_at,
    )
    return leased, SchedulerLeaseFence(
        admission_id=leased.admission_id,
        run_id=leased.run_id,
        owner=worker_id,
        generation=generation,
        expires_at=expires_at,
    )


def require_current_scheduler_fence(
    admission: RunSchedulerAdmissionV1,
    fence: SchedulerLeaseFence,
    *,
    at: datetime,
) -> RunSchedulerAdmissionV1:
    """Reject stale owners/generations and expired leases before any write."""

    _require_utc(at, field_name="at")
    if (
        admission.admission_id != fence.admission_id
        or admission.run_id != fence.run_id
        or admission.state is not SchedulerAdmissionState.LEASED
        or admission.lease_owner != fence.owner
        or admission.lease_generation != fence.generation
        or admission.lease_expires_at != fence.expires_at
    ):
        raise _scheduler_error(
            ErrorCodeV1.CONFLICT,
            admission,
            "scheduler lease fence is stale",
            "STALE_ADMISSION_FENCE",
        )
    if admission.lease_expires_at is None or admission.lease_expires_at <= at:
        raise _scheduler_error(
            ErrorCodeV1.CONFLICT,
            admission,
            "scheduler worker lease has expired",
            "ADMISSION_LEASE_EXPIRED",
        )
    return admission


def record_scheduler_run_start(
    admission: RunSchedulerAdmissionV1,
    fence: SchedulerLeaseFence,
    *,
    started_at: datetime,
    run_started_event_id: str,
    run_started_sequence: int,
) -> RunSchedulerAdmissionV1:
    """Record the one already-committed Run start under the current fence.

    Identical redelivery is a no-op.  A different time/event/sequence for an
    existing start is an integrity failure, never a second start.
    """

    _require_nonblank(run_started_event_id, field_name="run_started_event_id")
    _require_utc(started_at, field_name="started_at")
    if isinstance(run_started_sequence, bool) or run_started_sequence < 1:
        raise _request_error("run_started_sequence", "INVALID_EVENT_SEQUENCE")
    require_current_scheduler_fence(admission, fence, at=started_at)
    existing = (
        admission.start_committed_at,
        admission.run_started_event_id,
        admission.run_started_sequence,
    )
    incoming = (started_at, run_started_event_id, run_started_sequence)
    if all(value is not None for value in existing):
        if existing != incoming:
            raise _scheduler_integrity(admission, "RUN_START_IDENTITY_MISMATCH")
        return admission
    if any(value is not None for value in existing):
        raise _scheduler_integrity(admission, "RUN_START_FIELDS_INCOMPLETE")
    _require_transition_time(admission, started_at)
    return _replace_admission(
        admission,
        start_committed_at=started_at,
        run_started_event_id=run_started_event_id,
        run_started_sequence=run_started_sequence,
        updated_at=started_at,
    )


def acknowledge_scheduler_admission(
    admission: RunSchedulerAdmissionV1,
    fence: SchedulerLeaseFence,
    *,
    acknowledged_at: datetime,
) -> RunSchedulerAdmissionV1:
    """Acknowledge only the current fenced delivery after Run start commit."""

    _require_utc(acknowledged_at, field_name="acknowledged_at")
    if admission.state is SchedulerAdmissionState.ACKNOWLEDGED:
        if (
            admission.admission_id == fence.admission_id
            and admission.run_id == fence.run_id
            and admission.lease_generation == fence.generation
        ):
            return admission
        raise _scheduler_error(
            ErrorCodeV1.CONFLICT,
            admission,
            "acknowledgment fence is stale",
            "STALE_ADMISSION_FENCE",
        )
    require_current_scheduler_fence(admission, fence, at=acknowledged_at)
    if (
        admission.start_committed_at is None
        or admission.run_started_event_id is None
        or admission.run_started_sequence is None
    ):
        raise _scheduler_error(
            ErrorCodeV1.CONFLICT,
            admission,
            "scheduler admission cannot be acknowledged before Run start commit",
            "RUN_START_NOT_COMMITTED",
        )
    _require_transition_time(admission, acknowledged_at)
    return _replace_admission(
        admission,
        state=SchedulerAdmissionState.ACKNOWLEDGED,
        next_attempt_at=None,
        lease_owner=None,
        lease_expires_at=None,
        acknowledged_at=acknowledged_at,
        updated_at=acknowledged_at,
    )


def release_scheduler_admission(
    admission: RunSchedulerAdmissionV1,
    fence: SchedulerLeaseFence,
    *,
    released_at: datetime,
    next_attempt_at: datetime,
) -> RunSchedulerAdmissionV1:
    """Release a current lease for deterministic redelivery of the same Run."""

    _require_utc(released_at, field_name="released_at")
    _require_utc(next_attempt_at, field_name="next_attempt_at")
    require_current_scheduler_fence(admission, fence, at=released_at)
    _require_transition_time(admission, released_at)
    if next_attempt_at < released_at:
        raise _request_error("next_attempt_at", "INVALID_NEXT_ATTEMPT_TIME")
    if admission.delivery_attempt_count >= admission.max_delivery_attempts:
        raise _scheduler_error(
            ErrorCodeV1.TERMINAL,
            admission,
            "scheduler admission delivery attempts are exhausted",
            "ADMISSION_DELIVERY_EXHAUSTED",
        )
    return _replace_admission(
        admission,
        state=SchedulerAdmissionState.PENDING,
        next_attempt_at=next_attempt_at,
        lease_owner=None,
        lease_expires_at=None,
        updated_at=released_at,
    )


def fail_scheduler_admission(
    admission: RunSchedulerAdmissionV1,
    *,
    failed_at: datetime,
    failure_code: str,
    fence: SchedulerLeaseFence | None = None,
) -> RunSchedulerAdmissionV1:
    """Mark delivery permanently failed; caller must use the terminal Run finalizer."""

    _require_nonblank(failure_code, field_name="failure_code")
    _require_utc(failed_at, field_name="failed_at")
    if admission.state is SchedulerAdmissionState.FAILED:
        if admission.failure_code == failure_code:
            return admission
        raise _scheduler_integrity(admission, "ADMISSION_FAILURE_IDENTITY_MISMATCH")
    if admission.state is SchedulerAdmissionState.ACKNOWLEDGED:
        raise _scheduler_error(
            ErrorCodeV1.TERMINAL,
            admission,
            "acknowledged scheduler admission cannot be failed",
            "ADMISSION_ACKNOWLEDGED",
        )
    if admission.state is SchedulerAdmissionState.LEASED:
        if fence is None:
            raise _scheduler_error(
                ErrorCodeV1.CONFLICT,
                admission,
                "leased scheduler admission requires its current fence",
                "ADMISSION_FENCE_REQUIRED",
            )
        require_current_scheduler_fence(admission, fence, at=failed_at)
    elif fence is not None:
        raise _scheduler_error(
            ErrorCodeV1.CONFLICT,
            admission,
            "PENDING scheduler admission cannot accept a worker fence",
            "STALE_ADMISSION_FENCE",
        )
    _require_transition_time(admission, failed_at)
    return _replace_admission(
        admission,
        state=SchedulerAdmissionState.FAILED,
        next_attempt_at=None,
        lease_owner=None,
        lease_expires_at=None,
        failed_at=failed_at,
        failure_code=failure_code,
        updated_at=failed_at,
    )


# Short, discoverable aliases for adapters and focused contract tests.
lease_admission = lease_scheduler_admission
require_current_fence = require_current_scheduler_fence
record_run_start = record_scheduler_run_start
acknowledge_admission = acknowledge_scheduler_admission
release_admission = release_scheduler_admission
fail_admission = fail_scheduler_admission


def _replace_admission(
    admission: RunSchedulerAdmissionV1,
    **updates: object,
) -> RunSchedulerAdmissionV1:
    payload = admission.model_dump(mode="python")
    payload.update(updates)
    try:
        return RunSchedulerAdmissionV1.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        raise _scheduler_integrity(admission, "INVALID_ADMISSION_TRANSITION") from exc


def _require_transition_time(
    admission: RunSchedulerAdmissionV1,
    transition_at: datetime,
) -> None:
    if transition_at < admission.updated_at:
        raise _scheduler_error(
            ErrorCodeV1.CONFLICT,
            admission,
            "scheduler transition time precedes the retained state",
            "STALE_ADMISSION_TRANSITION",
        )


def _scheduler_integrity(
    admission: RunSchedulerAdmissionV1,
    reason_code: str,
) -> ProductError:
    return _integrity_error(
        "persisted scheduler admission failed its state or identity invariants",
        resource_type="scheduler_admission",
        resource_id=admission.admission_id,
        reason_code=reason_code,
    )


def _scheduler_error(
    code: ErrorCodeV1,
    admission: RunSchedulerAdmissionV1,
    message: str,
    reason_code: str,
) -> ProductError:
    return product_error(
        code,
        message,
        resource_type="scheduler_admission",
        resource_id=admission.admission_id,
        details={"reason_code": reason_code},
    )


def _integrity_error(
    message: str,
    *,
    resource_type: str,
    resource_id: str,
    reason_code: str,
) -> ProductError:
    return product_error(
        ErrorCodeV1.INTEGRITY_FAILURE,
        message,
        resource_type=resource_type,
        resource_id=resource_id,
        details={"reason_code": reason_code},
    )


def _request_error(field_name: str, reason_code: str) -> ProductError:
    return product_error(
        ErrorCodeV1.REQUEST_VALIDATION_ERROR,
        "durability transition input is invalid",
        details={"reason_code": reason_code, "field": field_name},
    )


def _validate_mutation_outcome_identity(
    *,
    outcome_id: str,
    effective_access_scope_key: str,
    idempotency_key_digest: str,
    method: str,
    route_template: str,
    expected_route: str,
    request_hash: str,
    created_at: datetime,
) -> None:
    for field_name, value in (
        ("outcome_id", outcome_id),
        ("idempotency_key_digest", idempotency_key_digest),
    ):
        _require_nonblank(value, field_name=field_name)
    if effective_access_scope_key != LOCAL_ACCESS_SCOPE:
        raise _request_error("effective_access_scope_key", "INVALID_ACCESS_SCOPE")
    _require_sha256(idempotency_key_digest, field_name="idempotency_key_digest")
    if method != "POST":
        raise _request_error("method", "INVALID_HTTP_METHOD")
    if route_template != expected_route:
        raise _request_error("route_template", "INVALID_ROUTE_TEMPLATE")
    _require_sha256(request_hash, field_name="request_hash")
    _require_utc(created_at, field_name="created_at")


def _validate_atomic_idempotency_key(
    *,
    outcome: DurableMutationOutcomeV1,
    idempotency_key: str,
    resource_type: str,
    resource_id: str,
) -> None:
    """Prove that the persisted digest came from the exact scoped raw key."""

    try:
        expected = idempotency_key_digest(
            idempotency_key,
            method=outcome.method,
            route_template=outcome.route_template,
            effective_access_scope_key=outcome.effective_access_scope_key,
        )
    except ValueError as exc:
        raise _request_error("idempotency_key", "INVALID_IDEMPOTENCY_KEY") from exc
    if outcome.idempotency_key_digest != expected:
        raise _integrity_error(
            "idempotency outcome key digest does not bind the exact scoped request key",
            resource_type=resource_type,
            resource_id=resource_id,
            reason_code="IDEMPOTENCY_KEY_DIGEST_MISMATCH",
        )


def _require_nonblank(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise _request_error(field_name, "INVALID_IDENTITY")


def _require_sha256(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise _request_error(field_name, "INVALID_SHA256")


def _require_utc(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise _request_error(field_name, "UTC_TIMESTAMP_REQUIRED")
