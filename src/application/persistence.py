from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    UniqueConstraint,
    delete,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from src.application.models import CompletedRunArtifacts, ResearchRunDraft, RunAggregate
from src.application.repository import (
    InMemoryApplicationRepository,
    compare_whole,
    initialize_binding,
    node_invocation,
    validate_root,
)
from src.data.persistence import SQLAlchemyEvidenceRepository
from src.data.repository import EvidenceRepository
from src.domain.calculation import CalculationRecord
from src.domain.enums import RunStatus
from src.domain.evidence import EvidenceRecord
from src.domain.node_binding import (
    SCHEMA,
    BindingDenied,
    BindingReference,
    NodeBindingState,
    calculation_core,
)
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.runtime_event import RuntimeEvent
from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph
from src.infrastructure.database.base import Base
from src.infrastructure.database.models import (
    CorrectionRecordRow,
    ReplanRecordRow,
    ReportArtifactRecordRow,
    TaskDependencyRow,
)
from src.observability.performance import observe
from src.runtime.state import RuntimeState

_binding_session = ContextVar("recovery_admission_session", default=None)


class ResearchObjectRow(Base):
    __tablename__ = "research_objects"

    object_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchRunDraftRow(Base):
    __tablename__ = "research_run_drafts"

    draft_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    draft_version: Mapped[int] = mapped_column(BigInteger, default=1)
    draft_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_admission_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    consumed_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class ResearchRunAggregateRow(Base):
    __tablename__ = "research_runs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    projection_revision: Mapped[int] = mapped_column(BigInteger, default=1)
    projection_sequence: Mapped[int] = mapped_column(BigInteger, default=0)


class ResearchGoalRow(Base):
    __tablename__ = "research_goals"

    goal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ResearchSchemeSnapshotRow(Base):
    __tablename__ = "research_scheme_snapshots"

    scheme_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    goal_id: Mapped[str] = mapped_column(String(128), index=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSON)


class TaskRow(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class RuntimeEventRow(Base):
    __tablename__ = "runtime_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_runtime_events_run_sequence"),
        CheckConstraint("sequence > 0", name="ck_runtime_events_positive_sequence"),
    )

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    sequence: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict] = mapped_column(JSON)


class CalculationRecordRow(Base):
    __tablename__ = "calculation_records"

    calculation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ReviewRecordRow(Base):
    __tablename__ = "review_records"

    review_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class CanonicalExecutionRecordRow(Base):
    __tablename__ = "canonical_execution_records"

    record_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ReleasedResearchResultRow(Base):
    __tablename__ = "released_research_results"

    result_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class SessionFactoryEvidenceRepository(EvidenceRepository):
    """Give the existing session-scoped SQL evidence repository an app lifetime."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, entity: EvidenceRecord) -> EvidenceRecord:
        async with self._sessions() as session:
            await guard_record_write(session, entity.run_id, entity.producer_task_id)
            added = await SQLAlchemyEvidenceRepository(session).add(entity)
            await session.commit()
            return added

    async def get(self, evidence_id: str) -> EvidenceRecord | None:
        async with self._sessions() as session:
            entity = await SQLAlchemyEvidenceRepository(session).get(evidence_id)
            return _sqlite_evidence_read(session, entity)

    async def list(self) -> list[EvidenceRecord]:
        async with self._sessions() as session:
            return await SQLAlchemyEvidenceRepository(session).list()

    async def list_by_run(self, run_id: str) -> list[EvidenceRecord]:
        async with self._sessions() as session:
            return await SQLAlchemyEvidenceRepository(session).list_by_run(run_id)


class SQLAlchemyApplicationRepository(InMemoryApplicationRepository):
    """SQL-backed application aggregate repository with a live runtime identity map.

    The JSON aggregate is the Phase-1 persistence/checkpoint view. Evidence keeps its
    normalized table in ``src.data.persistence``. The three tables here are owned by
    Integration and intentionally avoid duplicating domain or calculation logic.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        super().__init__()
        self._sessions = sessions

    async def add_object(self, entity: ResearchObject) -> ResearchObject:
        await super().add_object(entity)
        async with self._sessions() as session:
            session.add(
                ResearchObjectRow(
                    object_id=entity.object_id,
                    payload=entity.model_dump(mode="json"),
                    created_at=entity.created_at,
                )
            )
            await session.commit()
        return entity

    async def get_object(self, object_id: str) -> ResearchObject | None:
        cached = await super().get_object(object_id)
        if cached is not None:
            return cached
        async with self._sessions() as session:
            row = await session.get(ResearchObjectRow, object_id)
        if row is None:
            return None
        entity = ResearchObject.model_validate(row.payload)
        self._objects[object_id] = entity
        return entity

    async def list_objects(self) -> list[ResearchObject]:
        async with self._sessions() as session:
            rows = (await session.scalars(select(ResearchObjectRow))).all()
        return [ResearchObject.model_validate(row.payload) for row in rows]

    async def add_draft(self, draft: ResearchRunDraft) -> ResearchRunDraft:
        await super().add_draft(draft)
        async with self._sessions() as session:
            session.add(
                ResearchRunDraftRow(
                    draft_id=draft.draft_id,
                    object_id=draft.goal.research_object_id,
                    payload=draft.model_dump(mode="json"),
                    created_at=draft.goal.created_at,
                )
            )
            session.add(
                ResearchGoalRow(
                    goal_id=draft.goal.goal_id,
                    object_id=draft.goal.research_object_id,
                    payload=draft.goal.model_dump(mode="json"),
                )
            )
            session.add(
                ResearchSchemeSnapshotRow(
                    scheme_id=draft.scheme_snapshot.scheme_id,
                    goal_id=draft.goal.goal_id,
                    confirmed=False,
                    payload=draft.scheme_snapshot.model_dump(mode="json"),
                )
            )
            await session.commit()
        return draft

    async def get_draft(self, draft_id: str) -> ResearchRunDraft | None:
        cached = await super().get_draft(draft_id)
        if cached is not None:
            return cached
        async with self._sessions() as session:
            row = await session.get(ResearchRunDraftRow, draft_id)
        if row is None:
            return None
        draft = ResearchRunDraft.model_validate(row.payload)
        self._drafts[draft_id] = draft
        return draft

    async def add_run(self, aggregate: RunAggregate) -> None:
        initialize_binding(aggregate)
        async with self._sessions() as session:
            session.add(self._row(aggregate))
            session.info["wp02_root_write"] = (
                aggregate.run.run_id,
                aggregate.node_binding.binding_revision,
            )
            await self._persist_children(session, aggregate)
            await session.commit()

    @asynccontextmanager
    async def _binding_transaction(self, run_id, *, resume_replay=None, terminal_failure=None):
        async with self._sessions() as session, session.begin():
            row = await session.scalar(
                select(ResearchRunAggregateRow)
                .where(ResearchRunAggregateRow.run_id == run_id)
                .with_for_update()
            )
            if row is None:
                raise BindingDenied("STATE_REFRESH_REQUIRED", run_id)
            aggregate = self._to_aggregate(row.payload)
            validate_root(aggregate)
            if terminal_failure is not None:
                await self._replay_failure(session, aggregate, terminal_failure)
            # The locked durable root owns receipts; exact replay exits without writes.
            if resume_replay is not None:
                self._committed_resume_replay(aggregate, *resume_replay)
            previous_resume_events = len(
                (aggregate.node_binding.external_failure_resume or {}).get("audit", [])
            )
            previous_replan_events = len((aggregate.node_binding.replan or {}).get("audit", []))
            for result in aggregate.node_binding.results.values():
                await self.verify_materials(result.output_records, run_id=run_id, session=session)
            if aggregate.node_binding.replan is not None:
                from src.application.risk_replan import control

                await self.verify_materials([control(aggregate).candidate.output_record],
                                            run_id=run_id, session=session)
            token = _binding_session.set(session)
            try:
                yield aggregate
            finally:
                _binding_session.reset(token)
            aggregate.node_binding.binding_revision += 1
            aggregate.runtime.binding_ref = aggregate.node_binding.reference()
            if aggregate.node_binding.replan is not None:
                await self._persist_replan_events(
                    session, row, aggregate, previous_replan_events
                )
            if aggregate.node_binding.external_failure_resume is not None:
                await self._persist_resume_events(session, row, aggregate, previous_resume_events)
            if terminal_failure is not None:
                await self._persist_terminal_failure(session, row, aggregate, terminal_failure)
            row.payload = self._payload(aggregate)
            row.status = aggregate.run.status.value
            if terminal_failure is not None:
                row.updated_at = aggregate.run.completed_at
            session.info["wp02_root_write"] = (run_id, aggregate.node_binding.binding_revision)
            await self._persist_children(session, aggregate)
        self._runs.pop(run_id, None)

    async def finalize_failure(self, owner, proposed, *, unknown, payload, event_store):
        from src.application.terminal_failure import FailureReplay, failure_command

        # PostgreSQL owns the product event log. Other compositions retain the
        # repository adapter contract (their event store is supplied separately).
        async with self._sessions() as session:
            if session.get_bind().dialect.name != "postgresql":
                return await super().finalize_failure(
                    owner, proposed, unknown=unknown, payload=payload, event_store=event_store,
                )
        command = failure_command(owner, proposed, unknown, payload)
        try:
            async with self._binding_transaction(
                owner.run_id, terminal_failure=command,
            ) as aggregate:
                compare_whole(aggregate, proposed)
                validate_root(aggregate, owner)
                for field in ("run", "goal", "scheme", "runtime", "node_binding", "artifacts"):
                    setattr(aggregate, field, deepcopy(getattr(proposed, field)))
                await self._close_execution_state(aggregate, owner, unknown=unknown)
        except FailureReplay as replay:
            return replay.event
        return command["event"]

    async def _replay_failure(self, session, aggregate, command):
        from src.application.terminal_failure import FailureReplay, verify_failure_replay
        from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore

        PostgresRuntimeEventStore._require_postgresql(session)
        row = await session.get(RuntimeEventRow, command["event_id"])
        if row is not None:
            event = PostgresRuntimeEventStore._decode_row(aggregate.run.run_id, row)
            verify_failure_replay(aggregate, event, command)
            raise FailureReplay(event)

    async def _persist_terminal_failure(self, session, row, aggregate, command):
        from sqlalchemy import insert, update

        from src.application.terminal_failure import failure_payload
        from src.domain.runtime_event import RuntimeEventType, normalize_runtime_event_v1
        from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore

        run_id = aggregate.run.run_id
        await PostgresRuntimeEventStore._lock_run_event_writes(session, run_id)
        await PostgresRuntimeEventStore._reject_post_terminal_write(session, run_id)
        predecessor = await session.scalar(select(RuntimeEventRow).where(
            RuntimeEventRow.run_id == run_id,
        ).order_by(RuntimeEventRow.sequence.desc()).limit(1))
        causal = await session.scalar(select(RuntimeEventRow).where(
            RuntimeEventRow.run_id == run_id,
            RuntimeEventRow.payload["type"].as_string() == "task.failed",
        ).order_by(RuntimeEventRow.sequence.desc()).limit(1))
        sequence = await session.scalar(insert(RuntimeEventRow).values(
            event_id=command["event_id"], run_id=run_id, sequence=None, payload={},
        ).returning(RuntimeEventRow.sequence))
        event = RuntimeEvent(
            event_id=command["event_id"], run_id=run_id,
            type=RuntimeEventType.RUN_FAILED, timestamp=aggregate.run.completed_at,
            sequence=sequence, payload=failure_payload(
                aggregate, command, predecessor, causal,
            ),
        )
        normalize_runtime_event_v1(event)
        await session.execute(update(RuntimeEventRow).where(
            RuntimeEventRow.event_id == event.event_id,
        ).values(payload=event.model_dump(mode="json")))
        row.projection_sequence = sequence
        row.projection_revision += 1
        command["event"] = event

    async def _persist_resume_events(self, session, row, aggregate, previous_count):
        from sqlalchemy import insert, update

        from src.application.external_failure_resume import current_envelope
        from src.domain.runtime_event import RuntimeEventType, normalize_runtime_event_v1
        from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore

        events = aggregate.node_binding.external_failure_resume["audit"][previous_count:]
        if not events:
            return
        if session.bind.dialect.name != "postgresql":
            raise BindingDenied("RESUME_POSTGRESQL_AUTHORITY_REQUIRED")
        await PostgresRuntimeEventStore._lock_run_event_writes(session, aggregate.run.run_id)
        row.projection_revision += 1
        for item in events:
            sequence = await session.scalar(insert(RuntimeEventRow).values(
                event_id=item["event_id"], run_id=aggregate.run.run_id,
                sequence=None, payload={},
            ).returning(RuntimeEventRow.sequence))
            event = RuntimeEvent(
                event_id=item["event_id"], run_id=aggregate.run.run_id,
                task_id=current_envelope(aggregate).task_id,
                type=RuntimeEventType(item["type"]),
                timestamp=datetime.fromisoformat(item["timestamp"]), sequence=sequence,
                payload={"external_failure": item},
            )
            normalize_runtime_event_v1(event)
            await session.execute(update(RuntimeEventRow).where(
                RuntimeEventRow.event_id == event.event_id
            ).values(payload=event.model_dump(mode="json")))
            row.projection_sequence = sequence

    async def _persist_replan_events(self, session, row, aggregate, previous_count):
        from datetime import datetime

        from sqlalchemy import insert, update

        from src.domain.runtime_event import (
            RuntimeEvent,
            RuntimeEventType,
            normalize_runtime_event_v1,
        )
        from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore

        events = aggregate.node_binding.replan["audit"][previous_count:]
        if not events:
            return
        row.projection_revision += 1
        if session.bind.dialect.name != "postgresql":
            raise BindingDenied("REPLAN_POSTGRESQL_AUTHORITY_REQUIRED")
        await PostgresRuntimeEventStore._lock_run_event_writes(session, aggregate.run.run_id)
        for item in events:
            sequence = await session.scalar(insert(RuntimeEventRow).values(
                event_id=item["event_id"], run_id=aggregate.run.run_id,
                sequence=None, payload={},
            ).returning(RuntimeEventRow.sequence))
            event = RuntimeEvent(
                event_id=item["event_id"], run_id=aggregate.run.run_id,
                task_id=aggregate.node_binding.replan["candidate"]["task_id"],
                type=RuntimeEventType(item["type"]), timestamp=datetime.fromisoformat(
                    item["timestamp"]), sequence=sequence, payload={"risk_replan": item},
            )
            normalize_runtime_event_v1(event)
            await session.execute(update(RuntimeEventRow).where(
                RuntimeEventRow.event_id == event.event_id).values(
                    payload=event.model_dump(mode="json")))
            row.projection_sequence = sequence
            if item["type"] == "replan.fulfilled":
                finalization = aggregate.node_binding.replan["finalization"]
                for task_id in (finalization["fulfilling_child_task_id"],
                                finalization["source_task_id"]):
                    completion_id = item["event_id"] + "-" + (
                        "parent" if task_id == finalization["source_task_id"] else "child")
                    sequence = await session.scalar(insert(RuntimeEventRow).values(
                        event_id=completion_id, run_id=aggregate.run.run_id,
                        sequence=None, payload={},
                    ).returning(RuntimeEventRow.sequence))
                    task = aggregate.runtime.task(task_id)
                    completion = RuntimeEvent(
                        event_id=completion_id, run_id=aggregate.run.run_id, task_id=task_id,
                        type=RuntimeEventType.TASK_COMPLETED, timestamp=event.timestamp,
                        sequence=sequence, payload={"attempt": task.attempt_count},
                    )
                    normalize_runtime_event_v1(completion)
                    await session.execute(update(RuntimeEventRow).where(
                        RuntimeEventRow.event_id == completion_id).values(
                            payload=completion.model_dump(mode="json")))
                    row.projection_sequence = sequence
            if item["type"] == "research.cancelled":
                terminal_id = item["event_id"] + "-terminal"
                sequence = await session.scalar(insert(RuntimeEventRow).values(
                    event_id=terminal_id, run_id=aggregate.run.run_id,
                    sequence=None, payload={},
                ).returning(RuntimeEventRow.sequence))
                terminal = RuntimeEvent(
                    event_id=terminal_id, run_id=aggregate.run.run_id,
                    type=RuntimeEventType.RUN_FAILED, timestamp=event.timestamp,
                    sequence=sequence, payload={"status": "CANCELLED",
                        "failure_stage": "CANCELLATION", "failure_code": "RUN_CANCELLED",
                        "safe_message": "Research was explicitly cancelled."},
                )
                normalize_runtime_event_v1(terminal)
                await session.execute(update(RuntimeEventRow).where(
                    RuntimeEventRow.event_id == terminal_id).values(
                        payload=terminal.model_dump(mode="json")))
                row.projection_sequence = sequence

    async def _current_recovery_records(self, run_id, task_id):
        from src.infrastructure.database.recovery import RecoveryEvidenceStore

        session = _binding_session.get()
        if session is None:
            raise BindingDenied("RECOVERY_EVIDENCE_MISMATCH", "admission transaction missing")
        return await RecoveryEvidenceStore.records_in_session(session, run_id, task_id)

    async def verify_materials(self, materials, *, run_id, session=None):
        await super().verify_materials(materials, run_id=run_id)
        if session is None:
            session = _binding_session.get()
        if session is None:
            async with self._sessions() as reader:
                return await self.verify_materials(materials, run_id=run_id, session=reader)
        from src.data.persistence import EvidenceRecordRow, _to_domain
        from src.domain.node_binding import canonical_value

        for material in materials:
            if material.kind == "EVIDENCE":
                row = await session.get(EvidenceRecordRow, material.record_id)
                if (
                    row is None
                    or canonical_value(_sqlite_evidence_read(session, _to_domain(row)))
                    != material.payload_snapshot
                ):
                    raise BindingDenied("IDENTITY_MISMATCH", material.record_id)
            elif material.kind == "CALCULATION_CORE":
                row = await session.get(CalculationRecordRow, material.record_id)
                if (
                    row is None
                    or calculation_core(CalculationRecord.model_validate(row.payload))
                    != material.payload_snapshot
                ):
                    raise BindingDenied("IDENTITY_MISMATCH", material.record_id)

    @classmethod
    async def claim_execution_in_session(cls, session, row):
        from uuid import uuid4

        from src.domain.node_binding import OwnerToken

        row = await session.scalar(
            select(ResearchRunAggregateRow)
            .where(ResearchRunAggregateRow.run_id == row.run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise BindingDenied("STATE_REFRESH_REQUIRED", "claim root missing")
        aggregate = cls._to_aggregate(row.payload)
        root = validate_root(aggregate)
        if root.lifecycle != "UNCLAIMED" or root.owner_generation != 0 or root.owner_id:
            raise BindingDenied("OWNER_ALREADY_CLAIMED", aggregate.run.run_id)
        root.lifecycle, root.owner_generation, root.owner_id = "ACTIVE", 1, str(uuid4())
        root.binding_revision += 1
        aggregate.runtime.binding_ref = root.reference()
        row.payload = cls._payload(aggregate)
        return OwnerToken(run_id=aggregate.run.run_id, owner_generation=1, owner_id=root.owner_id)

    async def _resume_terminal_event(self, aggregate):
        from src.application.resume_runtime import require_terminal_event
        from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore

        session = _binding_session.get()
        if session is None:
            raise BindingDenied("RESUME_TRANSACTION_REQUIRED")
        await PostgresRuntimeEventStore._lock_run_event_writes(session, aggregate.run.run_id)
        row = await session.scalar(select(RuntimeEventRow).where(
            RuntimeEventRow.run_id == aggregate.run.run_id
        ).order_by(RuntimeEventRow.sequence.desc()).limit(1))
        require_terminal_event(aggregate, RuntimeEvent.model_validate(row.payload) if row else None)

    async def external_resume_pending_run_ids(self):
        async with self._sessions() as session:
            return list(await session.scalars(select(ResearchRunAggregateRow.run_id).where(
                ResearchRunAggregateRow.status == "RUNNING",
                ResearchRunAggregateRow.payload["node_binding"]["lifecycle"].as_string()
                == "EXTERNAL_RESUME_PENDING",
                ResearchRunAggregateRow.payload["node_binding"]["external_failure_resume"][
                    "current_cycle_id"].as_string().is_not(None),
            ).limit(16)))

    async def recovery_pending_run_ids(self):
        async with self._sessions() as session:
            return list(await session.scalars(
                select(ResearchRunAggregateRow.run_id).where(
                    ResearchRunAggregateRow.payload["node_binding"]["lifecycle"].as_string()
                    == "RECOVERY_PENDING"
                ).limit(16)
            ))

    async def replan_work_run_ids(self):
        from sqlalchemy import or_

        async with self._sessions() as session:
            state = ResearchRunAggregateRow.payload["node_binding"]["replan"]
            return list(await session.scalars(select(ResearchRunAggregateRow.run_id).where(
                ResearchRunAggregateRow.status == "WAITING_REPLAN",
                or_(state["wait_reason"].as_string() == "DECISION_APPLY",
                    state["resume_eligible"].as_boolean().is_(True)),
            ).limit(16)))

    async def replan_projection(self, run_id):
        from src.application.risk_replan import projection

        async with self._sessions() as session:
            row = await session.get(ResearchRunAggregateRow, run_id)
            if row is None:
                raise BindingDenied("REPLAN_NOT_FOUND")
            aggregate = self._to_aggregate(row.payload)
            validate_root(aggregate)
            return {**projection(aggregate), "projection_revision": row.projection_revision,
                    "projection_sequence": row.projection_sequence}

    async def get_run_fresh(self, run_id):
        async with self._sessions() as session:
            row = await session.get(ResearchRunAggregateRow, run_id)
            return self._to_aggregate(row.payload) if row is not None else None

    @observe("persistence.run_save", aggregate="aggregate")
    async def save_run(self, aggregate: RunAggregate) -> None:
        async with self._sessions() as session, session.begin():
            row = await session.scalar(
                select(ResearchRunAggregateRow)
                .where(ResearchRunAggregateRow.run_id == aggregate.run.run_id)
                .with_for_update()
            )
            if row is None:
                raise BindingDenied("STATE_REFRESH_REQUIRED", aggregate.run.run_id)
            current = self._to_aggregate(row.payload)
            if current.node_binding is not None or aggregate.node_binding is not None:
                compare_whole(current, aggregate)
                aggregate = deepcopy(aggregate)
                aggregate.node_binding.binding_revision += 1
                aggregate.runtime.binding_ref = aggregate.node_binding.reference()
                session.info["wp02_root_write"] = (
                    aggregate.run.run_id,
                    aggregate.node_binding.binding_revision,
                )
            row.status = aggregate.run.status.value
            row.payload = self._payload(aggregate)
            row.updated_at = aggregate.run.completed_at or aggregate.run.created_at
            await self._persist_children(session, aggregate)
        self._runs.pop(aggregate.run.run_id, None)

    @asynccontextmanager
    async def projection_publication(self, event: RuntimeEvent):
        """Capture the publication reference under the root's existing write lock.

        The durable event authorizes only its watermark, not any business mutation.
        Keep this transaction open through the guarded watermark save so a lawful
        binding transition cannot invalidate the publisher's own snapshot.
        """
        async with self._sessions() as session, session.begin():
            row = await session.scalar(
                select(ResearchRunAggregateRow)
                .where(ResearchRunAggregateRow.run_id == event.run_id)
                .with_for_update()
            )
            if row is None:
                raise BindingDenied("STATE_REFRESH_REQUIRED", event.run_id)
            persisted = await session.get(RuntimeEventRow, event.event_id)
            if (
                persisted is None
                or persisted.run_id != event.run_id
                or persisted.sequence != event.sequence
                or RuntimeEvent.model_validate(persisted.payload) != event
            ):
                raise BindingDenied("IDENTITY_MISMATCH", "publication event")
            aggregate = self._to_aggregate(row.payload)
            if aggregate.node_binding is not None:
                validate_root(aggregate)
                if event.task_id is not None:
                    aggregate.runtime.task(event.task_id)
            yield aggregate, session

    @asynccontextmanager
    async def _watermark_session(self, session):
        if session is not None:
            if not session.in_transaction():
                raise RuntimeError("watermark publication requires an active transaction")
            yield session
        else:
            async with self._sessions() as owned, owned.begin():
                yield owned

    @observe("persistence.watermark_transaction", aggregate="aggregate")
    async def save_run_with_projection_watermark(
        self,
        aggregate: RunAggregate,
        *,
        projection_sequence: int,
        expected_binding_ref=None,
        publication_session: AsyncSession | None = None,
    ) -> None:
        """Persist one aggregate and its public event watermark atomically."""

        if projection_sequence < 1:
            raise ValueError("projection_sequence must be positive")
        async with self._watermark_session(publication_session) as session:
            row = await session.scalar(
                select(ResearchRunAggregateRow)
                .where(ResearchRunAggregateRow.run_id == aggregate.run.run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if row is None:
                raise KeyError(aggregate.run.run_id)
            if projection_sequence <= row.projection_sequence:
                return
            if row.payload.get("node_binding") is not None or row.payload.get(
                "node_binding_required"
            ):
                # Events can advance a watermark, never replace committed business facts.
                authoritative = self._to_aggregate(row.payload)
                if (
                    expected_binding_ref is None
                    or authoritative.node_binding.reference() != expected_binding_ref
                ):
                    raise BindingDenied("STALE_WRITE_REJECTED", "watermark binding reference")
                row.projection_sequence = projection_sequence
                row.projection_revision += 1
                return
            row.status = aggregate.run.status.value
            row.payload = self._payload(aggregate)
            row.updated_at = aggregate.run.completed_at or aggregate.run.created_at
            row.projection_sequence = projection_sequence
            row.projection_revision += 1
            await self._persist_children(session, aggregate)

    async def get_calculation(self, calculation_id):
        async with self._sessions() as session:
            row = await session.get(CalculationRecordRow, calculation_id)
            return CalculationRecord.model_validate(row.payload) if row is not None else None

    async def save_calculation(self, calculation: CalculationRecord) -> None:
        async with self._sessions() as session:
            await guard_record_write(session, calculation.run_id, calculation.task_id)
            payload = calculation.model_dump(mode="json")
            row = await session.get(CalculationRecordRow, calculation.calculation_id)
            if row is not None:
                if row.payload != payload:
                    raise ValueError("calculation identity is immutable")
                return
            session.add(
                CalculationRecordRow(
                    calculation_id=calculation.calculation_id,
                    run_id=calculation.run_id,
                    payload=payload,
                )
            )
            await session.commit()

    async def save_runtime_events(self, events: list[RuntimeEvent]) -> None:
        async with self._sessions() as session:
            if session.get_bind().dialect.name == "postgresql":
                from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore

                # This compatibility writer can insert missing events too. Lock
                # roots before any read can autoflush event/counter/FK writes.
                for run_id in sorted({event.run_id for event in events}):
                    await PostgresRuntimeEventStore._lock_run_event_writes(session, run_id)
            for event in events:
                row = await session.get(RuntimeEventRow, event.event_id)
                payload = event.model_dump(mode="json")
                if row is None:
                    session.add(
                        RuntimeEventRow(
                            event_id=event.event_id,
                            run_id=event.run_id,
                            sequence=event.sequence,
                            payload=payload,
                        )
                    )
                else:
                    if row.run_id != event.run_id or row.sequence != event.sequence:
                        raise ValueError("persisted runtime event identity is immutable")
                    row.payload = payload
            await session.commit()

    async def get_run(self, run_id: str) -> RunAggregate | None:
        cached = await super().get_run(run_id)
        if cached is not None:
            return cached
        async with self._sessions() as session:
            row = await session.get(ResearchRunAggregateRow, run_id)
        if row is None:
            return None
        aggregate = self._to_aggregate(row.payload)
        self._runs[run_id] = aggregate
        return aggregate

    async def list_runs_for_object(self, object_id: str) -> list[RunAggregate]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ResearchRunAggregateRow).where(
                        ResearchRunAggregateRow.object_id == object_id
                    )
                )
            ).all()
        return [self._to_aggregate(row.payload) for row in rows]

    @classmethod
    @observe("persistence.aggregate_serialization", aggregate="aggregate")
    def _payload(cls, aggregate: RunAggregate) -> dict:
        return {
            "node_binding_required": SCHEMA if aggregate.node_binding else None,
            "node_binding": aggregate.node_binding.model_dump(mode="json")
            if aggregate.node_binding
            else None,
            "run": aggregate.run.model_dump(mode="json"),
            "goal": aggregate.goal.model_dump(mode="json"),
            "scheme": aggregate.scheme.model_dump(mode="json"),
            "runtime": {
                "planned_graph": aggregate.runtime.planned_graph.model_dump(mode="json"),
                "actual_graph": aggregate.runtime.actual_graph.model_dump(mode="json"),
                "run_status": aggregate.runtime.run_status.value,
                "completed_output_refs": aggregate.runtime.completed_output_refs,
                "evidence_refs": aggregate.runtime.evidence_refs,
                "workspace_refs": aggregate.runtime.workspace_refs,
                "review_state": aggregate.runtime.review_state,
                "proof_state": aggregate.runtime.proof_state,
                "cost": aggregate.runtime.cost,
                "binding_ref": aggregate.runtime.binding_ref.model_dump(mode="json")
                if aggregate.runtime.binding_ref
                else None,
            },
            "artifacts": aggregate.artifacts.model_dump(mode="json"),
        }

    @classmethod
    def _row(cls, aggregate: RunAggregate) -> ResearchRunAggregateRow:
        # Initial insertion only. Historical deserialization never calls this helper.
        initialize_binding(aggregate)
        return ResearchRunAggregateRow(
            run_id=aggregate.run.run_id,
            object_id=aggregate.run.research_object_id,
            status=aggregate.run.status.value,
            payload=cls._payload(aggregate),
            updated_at=aggregate.run.created_at,
        )

    @staticmethod
    @observe("persistence.children", aggregate="aggregate")
    async def _persist_children(session: AsyncSession, aggregate: RunAggregate) -> None:
        incoming = [
            *aggregate.runtime.actual_graph.tasks,
            *aggregate.artifacts.calculations,
            *aggregate.artifacts.corrections,
            *aggregate.artifacts.replans,
            *aggregate.artifacts.report_artifacts,
        ]
        incoming.extend(
            item
            for item in (
                aggregate.artifacts.review,
                aggregate.artifacts.canonical_record,
                aggregate.artifacts.released_result,
            )
            if item is not None
        )
        if any(item.run_id != aggregate.run.run_id for item in incoming):
            raise BindingDenied("IDENTITY_MISMATCH", "foreign child entity")
        if aggregate.node_binding is not None:
            expected = (aggregate.run.run_id, aggregate.node_binding.binding_revision)
            if session.info.get("wp02_root_write") != expected:
                raise BindingDenied("STALE_WRITE_REJECTED", "unguarded child writer")
            validate_root(aggregate)
        else:
            root_row = await session.get(ResearchRunAggregateRow, aggregate.run.run_id)
            if root_row is not None and (
                root_row.payload.get("node_binding")
                or root_row.payload.get("node_binding_required")
            ):
                raise BindingDenied("STALE_WRITE_REJECTED", "legacy child writer")
        if aggregate.node_binding is not None:
            locks = [
                (ResearchSchemeSnapshotRow, aggregate.scheme.scheme_id),
                (TaskDependencyRow, aggregate.run.run_id),
            ]
            locks.extend((TaskRow, task.task_id) for task in aggregate.runtime.actual_graph.tasks)
            for model, records, identity in (
                (CalculationRecordRow, aggregate.artifacts.calculations, "calculation_id"),
                (CorrectionRecordRow, aggregate.artifacts.corrections, "correction_id"),
                (ReplanRecordRow, aggregate.artifacts.replans, "replan_id"),
                (
                    ReviewRecordRow,
                    [aggregate.artifacts.review] if aggregate.artifacts.review else [],
                    "review_id",
                ),
                (
                    CanonicalExecutionRecordRow,
                    [aggregate.artifacts.canonical_record]
                    if aggregate.artifacts.canonical_record
                    else [],
                    "record_id",
                ),
                (
                    ReleasedResearchResultRow,
                    [aggregate.artifacts.released_result]
                    if aggregate.artifacts.released_result
                    else [],
                    "result_id",
                ),
                (ReportArtifactRecordRow, aggregate.artifacts.report_artifacts, "artifact_id"),
            ):
                locks.extend((model, getattr(record, identity)) for record in records)
            for model, identity in sorted(locks, key=lambda pair: (pair[0].__tablename__, pair[1])):
                if model is TaskDependencyRow:
                    await session.scalars(
                        select(TaskDependencyRow)
                        .where(TaskDependencyRow.run_id == identity)
                        .order_by(
                            TaskDependencyRow.graph_kind,
                            TaskDependencyRow.task_id,
                            TaskDependencyRow.position,
                        )
                        .with_for_update()
                    )
                else:
                    await session.get(model, identity, with_for_update=True)
        scheme = await session.get(ResearchSchemeSnapshotRow, aggregate.scheme.scheme_id)
        if scheme is None:
            session.add(
                ResearchSchemeSnapshotRow(
                    scheme_id=aggregate.scheme.scheme_id,
                    goal_id=aggregate.goal.goal_id,
                    confirmed=aggregate.scheme.confirmed_at is not None,
                    payload=aggregate.scheme.model_dump(mode="json"),
                )
            )
        else:
            if (
                scheme.confirmed
                or aggregate.run.reexecution_of_run_id
                or (
                    aggregate.node_binding is not None
                    and aggregate.node_binding.binding_revision != 0
                )
            ):
                if not scheme.confirmed or scheme.payload != aggregate.scheme.model_dump(
                    mode="json"
                ):
                    raise ValueError("re-execution cannot rewrite confirmed Scheme")
            else:
                scheme.confirmed = aggregate.scheme.confirmed_at is not None
                scheme.payload = aggregate.scheme.model_dump(mode="json")

        for task in sorted(aggregate.runtime.actual_graph.tasks, key=lambda item: item.task_id):
            row = await session.get(TaskRow, task.task_id)
            if row is not None and row.run_id != aggregate.run.run_id:
                raise BindingDenied("IDENTITY_MISMATCH", "existing foreign child")
            if row is None:
                session.add(
                    TaskRow(
                        task_id=task.task_id,
                        run_id=aggregate.run.run_id,
                        payload=task.model_dump(mode="json"),
                    )
                )
            else:
                row.payload = task.model_dump(mode="json")

        await session.flush()
        await session.execute(
            delete(TaskDependencyRow).where(TaskDependencyRow.run_id == aggregate.run.run_id)
        )
        for graph_kind, tasks in (
            ("PLANNED", aggregate.runtime.planned_graph.tasks),
            ("ACTUAL", aggregate.runtime.actual_graph.tasks),
        ):
            for task in tasks:
                session.add_all(
                    TaskDependencyRow(
                        run_id=aggregate.run.run_id,
                        graph_kind=graph_kind,
                        task_id=task.task_id,
                        dependency_task_id=dependency_task_id,
                        position=position,
                    )
                    for position, dependency_task_id in enumerate(task.dependencies)
                )

        for calculation in aggregate.artifacts.calculations:
            row = await session.get(CalculationRecordRow, calculation.calculation_id)
            if row is not None and row.run_id != aggregate.run.run_id:
                raise BindingDenied("IDENTITY_MISMATCH", "existing foreign child")
            if row is None:
                session.add(
                    CalculationRecordRow(
                        calculation_id=calculation.calculation_id,
                        run_id=aggregate.run.run_id,
                        payload=calculation.model_dump(mode="json"),
                    )
                )
            else:
                if aggregate.node_binding is not None and calculation_core(
                    CalculationRecord.model_validate(row.payload)
                ) != calculation_core(calculation):
                    raise BindingDenied("IDENTITY_MISMATCH", calculation.calculation_id)
                row.payload = calculation.model_dump(mode="json")

        for correction in aggregate.artifacts.corrections:
            row = await session.get(CorrectionRecordRow, correction.correction_id)
            if row is not None and row.run_id != aggregate.run.run_id:
                raise BindingDenied("IDENTITY_MISMATCH", "existing foreign child")
            if row is None:
                session.add(
                    CorrectionRecordRow(
                        correction_id=correction.correction_id,
                        run_id=aggregate.run.run_id,
                        payload=correction.model_dump(mode="json"),
                    )
                )
            else:
                row.payload = correction.model_dump(mode="json")

        for replan in aggregate.artifacts.replans:
            row = await session.get(ReplanRecordRow, replan.replan_id)
            if row is not None and row.run_id != aggregate.run.run_id:
                raise BindingDenied("IDENTITY_MISMATCH", "existing foreign child")
            if row is None:
                session.add(
                    ReplanRecordRow(
                        replan_id=replan.replan_id,
                        run_id=aggregate.run.run_id,
                        payload=replan.model_dump(mode="json"),
                    )
                )
            else:
                row.payload = replan.model_dump(mode="json")

        review = aggregate.artifacts.review
        if review is not None:
            row = await session.get(ReviewRecordRow, review.review_id)
            if row is not None and row.run_id != aggregate.run.run_id:
                raise BindingDenied("IDENTITY_MISMATCH", "existing foreign child")
            if row is None:
                session.add(
                    ReviewRecordRow(
                        review_id=review.review_id,
                        run_id=aggregate.run.run_id,
                        payload=review.model_dump(mode="json"),
                    )
                )
            else:
                row.payload = review.model_dump(mode="json")

        canonical = aggregate.artifacts.canonical_record
        if canonical is not None:
            row = await session.get(CanonicalExecutionRecordRow, canonical.record_id)
            if row is not None and row.run_id != aggregate.run.run_id:
                raise BindingDenied("IDENTITY_MISMATCH", "existing foreign child")
            if row is None:
                session.add(
                    CanonicalExecutionRecordRow(
                        record_id=canonical.record_id,
                        run_id=aggregate.run.run_id,
                        payload=canonical.model_dump(mode="json"),
                    )
                )
            else:
                row.payload = canonical.model_dump(mode="json")

        result = aggregate.artifacts.released_result
        if result is not None:
            row = await session.get(ReleasedResearchResultRow, result.result_id)
            if row is not None and row.run_id != aggregate.run.run_id:
                raise BindingDenied("IDENTITY_MISMATCH", "existing foreign child")
            if row is None:
                session.add(
                    ReleasedResearchResultRow(
                        result_id=result.result_id,
                        run_id=aggregate.run.run_id,
                        payload=result.model_dump(mode="json"),
                    )
                )
            else:
                row.payload = result.model_dump(mode="json")

        for artifact in aggregate.artifacts.report_artifacts:
            row = await session.get(ReportArtifactRecordRow, artifact.artifact_id)
            if row is not None and row.run_id != aggregate.run.run_id:
                raise BindingDenied("IDENTITY_MISMATCH", "existing foreign child")
            payload = artifact.model_dump(mode="json")
            if row is None:
                session.add(
                    ReportArtifactRecordRow(
                        artifact_id=artifact.artifact_id,
                        run_id=aggregate.run.run_id,
                        payload=payload,
                    )
                )
            elif row.run_id != aggregate.run.run_id or row.payload != payload:
                raise ValueError("report artifact records are immutable and exact-Run bound")

    @staticmethod
    def _to_aggregate(payload: dict) -> RunAggregate:
        runtime_payload = payload["runtime"]
        binding = payload.get("node_binding")
        if binding is not None and payload.get("node_binding_required") != SCHEMA:
            raise BindingDenied("STATE_REFRESH_REQUIRED", "binding marker mismatch")
        if payload.get("node_binding_required") and (
            payload["node_binding_required"] != SCHEMA or binding is None
        ):
            raise BindingDenied("STATE_REFRESH_REQUIRED", "missing/unknown required binding")
        if binding is not None and binding.get("schema_version") != SCHEMA:
            raise BindingDenied("STATE_REFRESH_REQUIRED", "missing binding schema")
        try:
            binding = NodeBindingState.model_validate(binding) if binding is not None else None
        except ValueError as exc:
            raise BindingDenied("STATE_REFRESH_REQUIRED", "invalid node binding schema") from exc
        runtime = RuntimeState(
            run_id=payload["run"]["run_id"],
            planned_graph=PlannedTaskGraph.model_validate(runtime_payload["planned_graph"]),
            actual_graph=ActualRuntimeGraph.model_validate(runtime_payload["actual_graph"]),
            run_status=RunStatus(runtime_payload["run_status"]),
            completed_output_refs=runtime_payload["completed_output_refs"],
            evidence_refs=runtime_payload["evidence_refs"],
            workspace_refs=runtime_payload["workspace_refs"],
            review_state=runtime_payload["review_state"],
            proof_state=runtime_payload["proof_state"],
            cost=runtime_payload["cost"],
            binding_ref=BindingReference.model_validate(runtime_payload["binding_ref"])
            if runtime_payload.get("binding_ref")
            else None,
        )
        aggregate = RunAggregate(
            run=ResearchRun.model_validate(payload["run"]),
            goal=ResearchGoal.model_validate(payload["goal"]),
            scheme=ResearchSchemeSnapshot.model_validate(payload["scheme"]),
            runtime=runtime,
            node_binding=binding,
        )
        aggregate.artifacts = CompletedRunArtifacts.model_validate(payload["artifacts"])
        task_by_id = {task.task_id: task for task in aggregate.runtime.actual_graph.tasks}
        output_task_ids: set[str] = set()
        for output in aggregate.artifacts.agent_outputs:
            task = task_by_id.get(output.task_id)
            if (
                output.run_id != aggregate.run.run_id
                or task is None
                or task.run_id != output.run_id
                or task.assigned_agent != output.actor
                or output.task_id in output_task_ids
            ):
                raise ValueError(
                    "persisted research Agent output is not uniquely bound to its exact Run/Task"
                )
            output_task_ids.add(output.task_id)
        canonical = aggregate.artifacts.canonical_record
        if canonical is not None and set(canonical.agent_output_refs) != {
            output.output_id
            for output in aggregate.artifacts.agent_outputs
            if output.status == "SUCCESS"
        }:
            raise ValueError(
                "canonical Agent output refs do not match the exact persisted success set"
            )
        released = aggregate.artifacts.released_result
        for artifact in aggregate.artifacts.report_artifacts:
            if (
                artifact.run_id != aggregate.run.run_id
                or canonical is None
                or released is None
                or artifact.canonical_record_id != canonical.record_id
                or artifact.released_result_id != released.result_id
            ):
                raise ValueError("persisted report artifact crossed its released Run identity")
        return aggregate


async def guard_record_write(session, run_id, task_id):
    """Root before record, in the caller's transaction. No provider await here."""
    row = await session.scalar(
        select(ResearchRunAggregateRow)
        .where(ResearchRunAggregateRow.run_id == run_id)
        .with_for_update()
    )
    if row is None:
        raise BindingDenied("STATE_REFRESH_REQUIRED", run_id)
    if row.payload.get("node_binding") is None and not row.payload.get("node_binding_required"):
        return
    aggregate = SQLAlchemyApplicationRepository._to_aggregate(row.payload)
    admission = node_invocation.get()
    if admission is None or admission.run_id != run_id or admission.task_id != task_id:
        raise BindingDenied("STALE_WRITE_REJECTED", "missing invocation")
    # Validation methods are stateless and share the same authoritative snapshot.
    InMemoryApplicationRepository._validate_admission(aggregate, admission, require_started=True)


async def reject_bound_write(session, run_id):
    row = await session.scalar(
        select(ResearchRunAggregateRow)
        .where(ResearchRunAggregateRow.run_id == run_id)
        .with_for_update()
    )
    if row is not None and (
        row.payload.get("node_binding") is not None or row.payload.get("node_binding_required")
    ):
        raise BindingDenied("POLICY_DENIED", "new-bound writer excluded")


def _sqlite_evidence_read(session, entity):
    # SQLite drops timezone offsets. New-bound fixture writers use UTC; PostgreSQL
    # retains timestamptz. This adapter does not claim SQLite row-lock equivalence.
    if entity is not None and session.bind.dialect.name == "sqlite":
        for key in ("created_at", "retrieved_at", "observed_at", "provider_timestamp"):
            value = getattr(entity, key)
            if value is not None and value.tzinfo is None:
                setattr(entity, key, value.replace(tzinfo=UTC))
    return entity
