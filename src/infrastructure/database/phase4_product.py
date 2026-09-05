"""Concrete PostgreSQL transaction adapters for the Phase 4 Product core."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from src.application.models import CompletedRunArtifacts
from src.application.persistence import (
    CalculationRecordRow,
    CanonicalExecutionRecordRow,
    ReleasedResearchResultRow,
    ResearchGoalRow,
    ResearchObjectRow,
    ResearchRunAggregateRow,
    ResearchRunDraftRow,
    ResearchSchemeSnapshotRow,
    ReviewRecordRow,
    RuntimeEventRow,
    TaskRow,
)
from src.domain.calculation import CalculationRecord
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.enums import RunStatus
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.review import ReviewRecord
from src.domain.runtime_event import RuntimeEvent
from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph, Task
from src.infrastructure.database.base import Base
from src.phase4_product.admission import ResearchRunDraftRecordV1, RunSchedulerAdmissionV1
from src.phase4_product.durability import (
    AtomicConfirmCommit,
    AtomicObjectCreateCommit,
    AtomicPrepareCommit,
    DurableIdempotencyOutcomeV1,
    DurableMutationOutcomeV1,
    DurableObjectCreateOutcomeV1,
    DurablePrepareOutcomeV1,
    ProjectionWriteSet,
)
from src.phase4_product.errors import product_error
from src.phase4_product.reconstruction import PersistedRunSnapshot, ProjectionWatermark

PHASE4_SINGLE_INSTANCE_SCOPE = "PHASE4_SINGLE_INSTANCE_SCOPE"
_TERMINAL_RUN_STATUSES = (
    RunStatus.RELEASED.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
)


class Phase4IdempotencyOutcomeRow(Base):
    __tablename__ = "phase4_idempotency_outcomes"

    outcome_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    access_scope: Mapped[str] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(16))
    route_template: Mapped[str] = mapped_column(String(256))
    key_digest: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    draft_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Phase4SchedulerAdmissionRow(Base):
    __tablename__ = "phase4_scheduler_admissions"

    admission_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True)
    outcome_id: Mapped[str] = mapped_column(String(128), unique=True)
    state: Mapped[str] = mapped_column(String(32))
    delivery_attempt_count: Mapped[int] = mapped_column(Integer)
    max_delivery_attempts: Mapped[int] = mapped_column(Integer)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_generation: Mapped[int] = mapped_column(BigInteger)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    start_committed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    run_started_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_started_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Phase4RunProjectionRow(Base):
    __tablename__ = "phase4_run_projections"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(128), index=True)
    revision: Mapped[int] = mapped_column(BigInteger)
    sequence: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Phase4PlannedGraphRow(Base):
    __tablename__ = "phase4_planned_graphs"
    graph_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class Phase4ActualGraphRow(Base):
    __tablename__ = "phase4_actual_graphs"
    graph_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


def _scheduler_row(value: RunSchedulerAdmissionV1) -> dict[str, Any]:
    payload = value.model_dump(mode="json")
    return {
        "admission_id": value.admission_id,
        "run_id": value.run_id,
        "outcome_id": value.idempotency_outcome_id,
        "state": value.state.value,
        "delivery_attempt_count": value.delivery_attempt_count,
        "max_delivery_attempts": value.max_delivery_attempts,
        "next_attempt_at": value.next_attempt_at,
        "lease_owner": value.lease_owner,
        "lease_generation": value.lease_generation,
        "lease_expires_at": value.lease_expires_at,
        "start_committed_at": value.start_committed_at,
        "run_started_event_id": value.run_started_event_id,
        "run_started_sequence": value.run_started_sequence,
        "acknowledged_at": value.acknowledged_at,
        "failed_at": value.failed_at,
        "failure_code": value.failure_code,
        "policy_version": value.policy_version,
        "payload": payload,
        "created_at": value.created_at,
        "updated_at": value.updated_at,
    }


def _outcome_row(value: DurableMutationOutcomeV1) -> Phase4IdempotencyOutcomeRow:
    if isinstance(value, DurableObjectCreateOutcomeV1):
        kind, object_id, draft_id, run_id = "OBJECT", value.object_id, None, None
        request_hash = value.request_hash
        payload: dict[str, Any] = {"object_id": value.object_id}
    elif isinstance(value, DurablePrepareOutcomeV1):
        kind, object_id, draft_id, run_id = (
            "PREPARE",
            value.draft.object_id,
            value.draft.draft_id,
            None,
        )
        request_hash = value.request_hash
        payload = value.draft.model_dump(mode="json")
    else:
        kind, object_id, draft_id, run_id = (
            "CONFIRM",
            value.admission.object_id,
            value.admission.draft_id,
            value.admission.run_id,
        )
        request_hash = value.confirmation_request_hash
        payload = value.admission.model_dump(mode="json")
    return Phase4IdempotencyOutcomeRow(
        outcome_id=value.outcome_id,
        access_scope=value.effective_access_scope_key,
        method=value.method,
        route_template=value.route_template,
        key_digest=value.idempotency_key_digest,
        request_hash=request_hash,
        kind=kind,
        object_id=object_id,
        draft_id=draft_id,
        run_id=run_id,
        payload=payload,
        created_at=value.created_at,
    )


def _decode_outcome(row: Phase4IdempotencyOutcomeRow) -> DurableMutationOutcomeV1:
    common = {
        "outcome_id": row.outcome_id,
        "effective_access_scope_key": row.access_scope,
        "idempotency_key_digest": row.key_digest,
        "method": row.method,
        "route_template": row.route_template,
        "created_at": row.created_at,
    }
    if row.kind == "OBJECT":
        return DurableObjectCreateOutcomeV1(
            **common, request_hash=row.request_hash, object_id=row.payload["object_id"]
        )
    if row.kind == "PREPARE":
        from src.phase4_product.contracts import ResearchRunDraftV1

        return DurablePrepareOutcomeV1(
            **common,
            request_hash=row.request_hash,
            draft=ResearchRunDraftV1.model_validate(row.payload),
        )
    from src.phase4_product.contracts import RunAdmissionV1

    return DurableIdempotencyOutcomeV1(
        **common,
        confirmation_request_hash=row.request_hash,
        admission=RunAdmissionV1.model_validate(row.payload),
    )


def _aggregate_payload(commit: AtomicConfirmCommit) -> dict[str, Any]:
    actual_graph = commit.actual_graph or ActualRuntimeGraph(
        graph_id=f"ACTUAL-{commit.run.run_id}",
        run_id=commit.run.run_id,
        tasks=list(commit.tasks),
    )
    return {
        "run": commit.run.model_dump(mode="json"),
        "goal": commit.goal.model_dump(mode="json"),
        "scheme": commit.scheme.model_dump(mode="json"),
        "runtime": {
            "planned_graph": commit.planned_graph.model_dump(mode="json"),
            "actual_graph": actual_graph.model_dump(mode="json"),
            "run_status": commit.run.status.value,
            "completed_output_refs": {},
            "evidence_refs": [],
            "workspace_refs": [],
            "review_state": {},
            "proof_state": {},
            "cost": 0.0,
        },
        "artifacts": CompletedRunArtifacts().model_dump(mode="json"),
    }


class SQLAlchemyPhase4AdmissionRepository:
    dialect_name = "postgresql"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_run_admission_scope(self, scope_key: str) -> None:
        """Serialize Confirm admission for one PostgreSQL-owned execution scope."""

        if not isinstance(scope_key, str) or not scope_key.strip():
            raise ValueError("run admission scope key must be non-empty")
        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(scope_key, 0)))
        )

    async def get_active_run_id_for_update(self, scope_key: str) -> str | None:
        """Return one authoritative admitted nonterminal Run, if present."""

        if scope_key != PHASE4_SINGLE_INSTANCE_SCOPE:
            raise ValueError("run admission scope is not configured")
        return await self.session.scalar(
            select(ResearchRunAggregateRow.run_id)
            .where(ResearchRunAggregateRow.status.not_in(_TERMINAL_RUN_STATUSES))
            .order_by(ResearchRunAggregateRow.run_id)
            .limit(1)
            .with_for_update()
        )

    async def get_draft_for_update(self, draft_id: str) -> ResearchRunDraftRecordV1 | None:
        row = await self.session.scalar(
            select(ResearchRunDraftRow)
            .where(ResearchRunDraftRow.draft_id == draft_id)
            .with_for_update()
        )
        if row is None:
            return None
        from src.phase4_product.contracts import ResearchRunDraftV1

        draft = ResearchRunDraftV1.model_validate(row.payload)
        return ResearchRunDraftRecordV1(
            draft=draft,
            consumed_at=row.consumed_at,
            consumed_admission_id=row.consumed_admission_id,
            consumed_run_id=row.consumed_run_id,
        )

    async def get_idempotency_outcome_for_update(
        self,
        *,
        effective_access_scope_key: str,
        method: str,
        route_template: str,
        idempotency_key_digest: str,
    ) -> DurableMutationOutcomeV1 | None:
        row = await self.session.scalar(
            select(Phase4IdempotencyOutcomeRow)
            .where(
                Phase4IdempotencyOutcomeRow.access_scope == effective_access_scope_key,
                Phase4IdempotencyOutcomeRow.method == method,
                Phase4IdempotencyOutcomeRow.route_template == route_template,
                Phase4IdempotencyOutcomeRow.key_digest == idempotency_key_digest,
            )
            .with_for_update()
        )
        return None if row is None else _decode_outcome(row)

    async def insert_object_create_commit(self, commit: AtomicObjectCreateCommit) -> None:
        self.session.add(
            ResearchObjectRow(
                object_id=commit.research_object.object_id,
                payload=commit.research_object.model_dump(mode="json"),
                created_at=commit.research_object.created_at,
            )
        )
        self.session.add(_outcome_row(commit.outcome))

    async def insert_prepare_commit(self, commit: AtomicPrepareCommit) -> None:
        draft = commit.draft_record.draft
        self.session.add(
            ResearchGoalRow(
                goal_id=commit.goal.goal_id,
                object_id=commit.goal.research_object_id,
                payload=commit.goal.model_dump(mode="json"),
            )
        )
        self.session.add(
            ResearchSchemeSnapshotRow(
                scheme_id=commit.scheme.scheme_id,
                goal_id=commit.scheme.goal_id,
                confirmed=False,
                payload=commit.scheme.model_dump(mode="json"),
            )
        )
        self.session.add(
            ResearchRunDraftRow(
                draft_id=draft.draft_id,
                object_id=draft.object_id,
                payload=draft.model_dump(mode="json"),
                created_at=draft.created_at,
                draft_version=draft.draft_version,
                draft_hash=draft.draft_hash,
                expires_at=draft.expires_at,
            )
        )
        self.session.add(_outcome_row(commit.outcome))

    async def insert_confirm_commit(self, commit: AtomicConfirmCommit) -> None:
        draft = commit.consumed_draft
        await self.session.execute(
            update(ResearchRunDraftRow)
            .where(
                ResearchRunDraftRow.draft_id == draft.draft.draft_id,
                ResearchRunDraftRow.consumed_at.is_(None),
            )
            .values(
                consumed_at=draft.consumed_at,
                consumed_admission_id=draft.consumed_admission_id,
                consumed_run_id=draft.consumed_run_id,
            )
        )
        await self.session.execute(
            update(ResearchSchemeSnapshotRow)
            .where(ResearchSchemeSnapshotRow.scheme_id == commit.scheme.scheme_id)
            .values(confirmed=True, payload=commit.scheme.model_dump(mode="json"))
        )
        self.session.add(
            ResearchRunAggregateRow(
                run_id=commit.run.run_id,
                object_id=commit.run.research_object_id,
                status=commit.run.status.value,
                payload=_aggregate_payload(commit),
                updated_at=commit.run.updated_at,
                projection_revision=1,
                projection_sequence=len(commit.initial_events),
            )
        )
        self.session.add(
            Phase4PlannedGraphRow(
                graph_id=commit.planned_graph.graph_id,
                run_id=commit.run.run_id,
                payload=commit.planned_graph.model_dump(mode="json"),
            )
        )
        if commit.actual_graph is not None:
            self.session.add(
                Phase4ActualGraphRow(
                    graph_id=commit.actual_graph.graph_id,
                    run_id=commit.run.run_id,
                    payload=commit.actual_graph.model_dump(mode="json"),
                )
            )
        for task in commit.tasks:
            self.session.add(
                TaskRow(
                    task_id=task.task_id,
                    run_id=commit.run.run_id,
                    payload=task.model_dump(mode="json"),
                )
            )
        self.session.add(_outcome_row(commit.idempotency_outcome))
        self.session.add(Phase4SchedulerAdmissionRow(**_scheduler_row(commit.scheduler_admission)))
        for event in commit.initial_events:
            self.session.add(
                RuntimeEventRow(
                    event_id=event.event_id,
                    run_id=event.run_id,
                    sequence=event.sequence,
                    payload=event.model_dump(mode="json"),
                )
            )


class SQLAlchemyPhase4SchedulerAdmissionRepository:
    dialect_name = "postgresql"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_update(self, admission_id: str) -> RunSchedulerAdmissionV1 | None:
        row = await self.session.scalar(
            select(Phase4SchedulerAdmissionRow)
            .where(Phase4SchedulerAdmissionRow.admission_id == admission_id)
            .with_for_update()
        )
        return None if row is None else RunSchedulerAdmissionV1.model_validate(row.payload)

    async def list_due_admission_ids(self, *, due_at: datetime, limit: int) -> list[str]:
        rows = await self.session.scalars(
            select(Phase4SchedulerAdmissionRow.admission_id)
            .where(
                Phase4SchedulerAdmissionRow.state == "PENDING",
                Phase4SchedulerAdmissionRow.next_attempt_at <= due_at,
            )
            .order_by(
                Phase4SchedulerAdmissionRow.next_attempt_at,
                Phase4SchedulerAdmissionRow.admission_id,
            )
            .limit(limit)
        )
        return list(rows)

    async def replace_fenced(
        self,
        admission: RunSchedulerAdmissionV1,
        *,
        expected_lease_generation: int,
    ) -> bool:
        result = await self.session.execute(
            update(Phase4SchedulerAdmissionRow)
            .where(
                Phase4SchedulerAdmissionRow.admission_id == admission.admission_id,
                Phase4SchedulerAdmissionRow.lease_generation == expected_lease_generation,
            )
            .values(**_scheduler_row(admission))
        )
        return result.rowcount == 1


class SQLAlchemyPhase4ProjectionRepository:
    dialect_name = "postgresql"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def publish(self, write_set: ProjectionWriteSet) -> ProjectionWatermark:
        root = await self.session.scalar(
            select(ResearchRunAggregateRow)
            .where(ResearchRunAggregateRow.run_id == write_set.fence.run_id)
            .with_for_update()
        )
        if root is None:
            raise product_error("NOT_FOUND", "research run was not found")
        if root.projection_revision != write_set.fence.expected_revision:
            raise product_error(
                "CONFLICT",
                "projection revision fence is stale",
                resource_type="projection",
                resource_id=write_set.fence.run_id,
                details={"reason_code": "STALE_PROJECTION_REVISION"},
            )
        expected = root.projection_sequence + 1
        if write_set.events and [event.sequence for event in write_set.events] != list(
            range(expected, expected + len(write_set.events))
        ):
            raise product_error(
                "INTEGRITY_FAILURE",
                "projection events do not extend the durable watermark",
                resource_type="projection",
                resource_id=write_set.fence.run_id,
            )
        for event in write_set.events:
            self.session.add(
                RuntimeEventRow(
                    event_id=event.event_id,
                    run_id=event.run_id,
                    sequence=event.sequence,
                    payload=event.model_dump(mode="json"),
                )
            )
        if write_set.run is not None:
            root.status = write_set.run.status.value
            root.updated_at = write_set.run.updated_at
            root.payload = {**root.payload, "run": write_set.run.model_dump(mode="json")}
        for task in write_set.tasks:
            await self.session.execute(
                pg_insert(TaskRow)
                .values(
                    task_id=task.task_id,
                    run_id=task.run_id,
                    payload=task.model_dump(mode="json"),
                )
                .on_conflict_do_update(
                    index_elements=[TaskRow.task_id],
                    set_={"payload": task.model_dump(mode="json")},
                )
            )
        new_sequence = root.projection_sequence + len(write_set.events)
        root.projection_revision += 1
        root.projection_sequence = new_sequence
        return ProjectionWatermark(revision=root.projection_revision, sequence=new_sequence)

    async def read_exact_run_snapshot(
        self,
        *,
        object_id: str,
        run_id: str,
    ) -> PersistedRunSnapshot | None:
        root = await self.session.scalar(
            select(ResearchRunAggregateRow).where(
                ResearchRunAggregateRow.run_id == run_id,
                ResearchRunAggregateRow.object_id == object_id,
            )
        )
        if root is None:
            return None
        obj = await self.session.get(ResearchObjectRow, object_id)
        goal = await self.session.get(ResearchGoalRow, root.payload["run"]["goal_id"])
        scheme = await self.session.get(ResearchSchemeSnapshotRow, root.payload["run"]["scheme_id"])
        planned_rows = (
            await self.session.scalars(
                select(Phase4PlannedGraphRow).where(Phase4PlannedGraphRow.run_id == run_id)
            )
        ).all()
        actual_rows = (
            await self.session.scalars(
                select(Phase4ActualGraphRow).where(Phase4ActualGraphRow.run_id == run_id)
            )
        ).all()
        task_rows = (
            await self.session.scalars(select(TaskRow).where(TaskRow.run_id == run_id))
        ).all()
        event_rows = (
            await self.session.scalars(
                select(RuntimeEventRow)
                .where(
                    RuntimeEventRow.run_id == run_id,
                    RuntimeEventRow.sequence <= root.projection_sequence,
                )
                .order_by(RuntimeEventRow.sequence)
            )
        ).all()
        calculation_rows = (
            await self.session.scalars(
                select(CalculationRecordRow).where(CalculationRecordRow.run_id == run_id)
            )
        ).all()
        review_rows = (
            await self.session.scalars(
                select(ReviewRecordRow).where(ReviewRecordRow.run_id == run_id)
            )
        ).all()
        canonical_rows = (
            await self.session.scalars(
                select(CanonicalExecutionRecordRow).where(
                    CanonicalExecutionRecordRow.run_id == run_id
                )
            )
        ).all()
        released_rows = (
            await self.session.scalars(
                select(ReleasedResearchResultRow).where(ReleasedResearchResultRow.run_id == run_id)
            )
        ).all()
        if obj is None or goal is None or scheme is None:
            return PersistedRunSnapshot(
                requested_object_id=object_id,
                requested_run_id=run_id,
                projection_revision=root.projection_revision,
                projection_sequence=root.projection_sequence,
            )
        return PersistedRunSnapshot(
            requested_object_id=object_id,
            requested_run_id=run_id,
            projection_revision=root.projection_revision,
            projection_sequence=root.projection_sequence,
            research_objects=(ResearchObject.model_validate(obj.payload),),
            goals=(ResearchGoal.model_validate(goal.payload),),
            schemes=(ResearchSchemeSnapshot.model_validate(scheme.payload),),
            runs=(ResearchRun.model_validate(root.payload["run"]),),
            planned_graphs=tuple(
                PlannedTaskGraph.model_validate(row.payload) for row in planned_rows
            ),
            actual_graphs=tuple(
                ActualRuntimeGraph.model_validate(row.payload) for row in actual_rows
            ),
            tasks=tuple(Task.model_validate(row.payload) for row in task_rows),
            events=tuple(RuntimeEvent.model_validate(row.payload) for row in event_rows),
            calculations=tuple(
                CalculationRecord.model_validate(row.payload) for row in calculation_rows
            ),
            reviews=tuple(ReviewRecord.model_validate(row.payload) for row in review_rows),
            canonical_records=tuple(
                CanonicalExecutionRecord.model_validate(row.payload) for row in canonical_rows
            ),
            released_results=tuple(
                ReleasedResearchResult.model_validate(row.payload) for row in released_rows
            ),
        )


class PostgreSQLProductUnitOfWork:
    dialect_name = "postgresql"

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        isolation_level: Literal["READ COMMITTED", "REPEATABLE READ"] = "REPEATABLE READ",
    ) -> None:
        self._sessions = sessions
        self._isolation_level = isolation_level
        self.session: AsyncSession | None = None
        self.admission: SQLAlchemyPhase4AdmissionRepository
        self.scheduler: SQLAlchemyPhase4SchedulerAdmissionRepository
        self.projection: SQLAlchemyPhase4ProjectionRepository

    async def __aenter__(self) -> Self:
        self.session = self._sessions()
        await self.session.connection(
            execution_options={"isolation_level": self._isolation_level}
        )
        if self.session.get_bind().dialect.name != "postgresql":
            await self.session.rollback()
            await self.session.close()
            raise RuntimeError("Phase 4 Product UoW requires PostgreSQL")
        self.admission = SQLAlchemyPhase4AdmissionRepository(self.session)
        self.scheduler = SQLAlchemyPhase4SchedulerAdmissionRepository(self.session)
        self.projection = SQLAlchemyPhase4ProjectionRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if self.session is None:
            return
        if exc_type is not None and self.session.in_transaction():
            await self.session.rollback()
        elif self.session.in_transaction():
            await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("unit of work is not active")
        await self.session.commit()

    async def rollback(self) -> None:
        if self.session is not None:
            await self.session.rollback()


class PostgreSQLProductUnitOfWorkFactory:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        isolation_level: Literal["READ COMMITTED", "REPEATABLE READ"] = "REPEATABLE READ",
    ) -> None:
        self.sessions = sessions
        self.isolation_level = isolation_level

    def __call__(self) -> PostgreSQLProductUnitOfWork:
        return PostgreSQLProductUnitOfWork(
            self.sessions,
            isolation_level=self.isolation_level,
        )
