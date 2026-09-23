from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
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


@dataclass(frozen=True)
class TerminalSettlementBudget:
    """Absolute monotonic outer deadline, supplied by the orchestration owner."""

    deadline: float

    def remaining(self):
        return max(0.0, self.deadline - asyncio.get_running_loop().time())

    def require_remaining(self):
        if self.remaining() <= 0:
            raise BindingDenied("RESULT_UNKNOWN", "terminal settlement budget exhausted")


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
    __table_args__ = (CheckConstraint("aggregate_schema_version IN (1, 2)",
                                    name="ck_research_runs_aggregate_schema_version"),)

    aggregate_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)

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
            if terminal_failure is not None and session.bind.dialect.name == "postgresql":
                from sqlalchemy import text

                await session.execute(text("SET LOCAL lock_timeout = '30s'"))
                await session.execute(text("SET LOCAL statement_timeout = '120s'"))
                terminal_failure["search_path"] = await session.scalar(text("SHOW search_path"))
            row = await session.scalar(
                select(ResearchRunAggregateRow)
                .where(ResearchRunAggregateRow.run_id == run_id)
                .with_for_update()
            )
            if row is None:
                raise BindingDenied("STATE_REFRESH_REQUIRED", run_id)
            try:
                aggregate = self._from_row(row)
                validate_root(aggregate)
            except (BindingDenied, KeyError, TypeError, ValueError) as exc:
                if (terminal_failure is not None
                        and (row.status == "FAILED" or await session.get(
                            RuntimeEventRow, terminal_failure["event_id"],
                        ) is not None)):
                    raise BindingDenied(
                        "INTEGRITY_STOP", "terminal failure root corrupt"
                    ) from exc
                raise
            if terminal_failure is not None:
                await self._replay_failure(session, aggregate, terminal_failure)
                if terminal_failure["baseline"] is None:
                    last_event = await session.scalar(select(RuntimeEventRow).where(
                        RuntimeEventRow.run_id == run_id,
                    ).order_by(RuntimeEventRow.sequence.desc()).limit(1))
                    terminal_failure["baseline"] = {
                        "payload": deepcopy(row.payload), "status": row.status,
                        "projection_revision": row.projection_revision,
                        "projection_sequence": row.projection_sequence,
                        "last_event_sequence": last_event.sequence if last_event else 0,
                    }
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
            from src.runtime.scheduler import liveness_committed, liveness_facts

            liveness_before = liveness_facts(aggregate)
            token = _binding_session.set(session)
            try:
                saved_authority = (aggregate.aggregate_schema_version,
                                   aggregate.confirmed_risk_semantic_binding)
                yield aggregate
                if saved_authority != (aggregate.aggregate_schema_version,
                                       aggregate.confirmed_risk_semantic_binding):
                    raise BindingDenied("CONFIRMED_AUTHORITY_MISMATCH", "transaction identity")
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
            if terminal_failure is not None:
                await session.flush()
                # Raw SQL and database-side effects in this transaction can bypass
                # already-loaded ORM objects. Expire the whole set before proving
                # the durable root, event, children and referenced materials.
                session.expire_all()
                row = await session.scalar(
                    select(ResearchRunAggregateRow)
                    .where(ResearchRunAggregateRow.run_id == run_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if row is None:
                    raise BindingDenied("INTEGRITY_STOP", "terminal failure root missing")
                await self._validate_failure_full_set(
                    session, row, terminal_failure, expected_revision=row.projection_revision,
                )
                terminal_failure["phase"] = "COMMIT_ENTERED"
        self._runs.pop(run_id, None)
        liveness_committed(aggregate, liveness_before)

    async def finalize_failure(self, owner, proposed, *, unknown, payload, event_store,
                               budget=None):
        from src.application.terminal_failure import FailureReplay, failure_command

        # PostgreSQL owns the product event log. Other compositions retain the
        # repository adapter contract (their event store is supplied separately).
        async with self._sessions() as session:
            if session.get_bind().dialect.name != "postgresql":
                return await super().finalize_failure(
                    owner, proposed, unknown=unknown, payload=payload, event_store=event_store,
                )
        command = failure_command(owner, proposed, unknown, payload)
        command.update(phase="PRECOMMIT", baseline=None, outcome=None)
        budget = budget or TerminalSettlementBudget(asyncio.get_running_loop().time() + 180)
        for attempt in range(2):
            try:
                budget.require_remaining()
                async with asyncio.timeout_at(budget.deadline):
                    async with self._binding_transaction(
                        owner.run_id, terminal_failure=command,
                    ) as aggregate:
                        compare_whole(aggregate, proposed)
                        validate_root(aggregate, owner)
                        for field in ("run", "goal", "scheme", "runtime", "node_binding",
                                      "artifacts"):
                            setattr(aggregate, field, deepcopy(getattr(proposed, field)))
                        await self._close_execution_state(aggregate, owner, unknown=unknown)
                command["outcome"] = "COMMITTED"
                return command["event"]
            except FailureReplay as replay:
                command["outcome"] = "COMMITTED"
                return replay.event
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                if isinstance(exc, BindingDenied) and exc.code == "INTEGRITY_STOP":
                    raise
                phase = command["phase"]
                command["outcome"] = (
                    "COMMIT_AMBIGUOUS" if phase == "COMMIT_ENTERED"
                    else "KNOWN_NOT_COMMITTED"
                )
                if phase == "COMMIT_ENTERED":
                    result = await self._read_failure_outcome(owner, command, budget)
                    if result is not None:
                        command["outcome"] = "COMMITTED"
                        return result
                if attempt or budget.remaining() <= 0:
                    if isinstance(exc, (asyncio.CancelledError, TimeoutError)):
                        raise BindingDenied(
                            "RESULT_UNKNOWN", "failure settlement unresolved"
                        ) from exc
                    raise
                command["phase"] = "PRECOMMIT"
        raise BindingDenied("RESULT_UNKNOWN", "failure settlement unresolved")

    async def _read_failure_outcome(self, owner, command, budget):
        """Fresh locked readback; None means exact no-effect, never partial success."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        if command["baseline"] is None:
            raise BindingDenied("RESULT_UNKNOWN", "failure baseline unavailable")
        fresh_engine = create_async_engine(
            self._sessions.kw["bind"].url, poolclass=NullPool,
            connect_args={"server_settings": {"search_path": command["search_path"]}},
        )
        try:
            budget.require_remaining()
            async with asyncio.timeout_at(budget.deadline):
                # NullPool opens a distinct physical connection after the attempt.
                fresh_sessions = async_sessionmaker(fresh_engine, expire_on_commit=False)
                async with fresh_sessions() as session, session.begin():
                    from sqlalchemy import text

                    await session.execute(text("SET LOCAL lock_timeout = '30s'"))
                    await session.execute(text("SET LOCAL statement_timeout = '120s'"))
                    row = await session.scalar(select(ResearchRunAggregateRow).where(
                        ResearchRunAggregateRow.run_id == owner.run_id,
                    ).with_for_update())
                    if row is None:
                        raise BindingDenied("INTEGRITY_STOP", "failure root missing")
                    event_row = await session.get(RuntimeEventRow, command["event_id"])
                    last = await session.scalar(select(RuntimeEventRow).where(
                        RuntimeEventRow.run_id == owner.run_id,
                    ).order_by(RuntimeEventRow.sequence.desc()).limit(1))
                    if event_row is not None:
                        if (last is None or last.event_id != event_row.event_id
                                or row.projection_revision
                                != command["baseline"]["projection_revision"] + 1):
                            raise BindingDenied("INTEGRITY_STOP", "partial terminal failure set")
                        return await self._validate_failure_full_set(
                            session, row, command,
                            expected_revision=command["baseline"]["projection_revision"] + 1,
                        )
                    baseline = command["baseline"]
                    if (row.payload == baseline["payload"]
                            and row.status == baseline["status"]
                            and row.projection_revision == baseline["projection_revision"]
                            and row.projection_sequence == baseline["projection_sequence"]
                            and (last.sequence if last else 0)
                            == baseline["last_event_sequence"]):
                        return None
                    raise BindingDenied("INTEGRITY_STOP", "partial terminal failure set")
        except BindingDenied as exc:
            if exc.code not in {"INTEGRITY_STOP", "RESULT_UNKNOWN"}:
                raise BindingDenied("INTEGRITY_STOP", "failure authority mismatch") from exc
            raise
        except (asyncio.CancelledError, TimeoutError, Exception) as exc:
            raise BindingDenied("RESULT_UNKNOWN", "failure readback unresolved") from exc
        finally:
            await fresh_engine.dispose()

    @property
    def atomic_terminal_success(self):
        return self._sessions.kw["bind"].dialect.name == "postgresql"

    async def finalize_success(self, owner, proposed, *, released_at, budget, report_store):
        """D1 repository primitive. The caller retains the same outer deadline.

        Normal service routing is deliberately separate. No exception from this
        operation authorizes failure finalization or a new execution owner.
        """
        from src.domain.node_binding import canonical_value, digest

        command = {
            "owner": owner, "proposed": deepcopy(proposed), "released_at": released_at,
            "identity": digest(canonical_value(owner), "terminal-success/v1"),
            "baseline": None, "report_store": report_store,
        }
        budget.require_remaining()
        self._validate_success_proposal(command)
        reads = 0
        for attempt in range(2):
            budget.require_remaining()
            try:
                result = await self._success_transaction(command, budget, readback=False)
                if result is not None:
                    self._runs.pop(owner.run_id, None)
                    return result
            except BindingDenied:
                raise
            except (Exception, asyncio.CancelledError):
                # No error/timeout is interpreted as evidence of a rollback.
                pass
            while reads < 2 and budget.remaining() > 0:
                reads += 1
                try:
                    result = await self._success_transaction(command, budget, readback=True)
                except BindingDenied:
                    raise
                except (Exception, asyncio.CancelledError):
                    continue
                if result is not None:
                    self._runs.pop(owner.run_id, None)
                    return result
                # Root-serialized no-effect proof is the sole retry authority.
                break
            else:
                break
            if attempt == 1:
                break
        raise BindingDenied("RESULT_UNKNOWN", "terminal settlement outcome unavailable")

    async def read_terminal_success(self, run_id, *, budget, report_store):
        """Fresh commandless replay; never claims or mutates an execution owner."""
        command = {"run_id": run_id, "owner": None, "baseline": None,
                   "report_store": report_store}
        for _ in range(2):
            budget.require_remaining()
            try:
                return await self._success_transaction(command, budget, readback=True)
            except BindingDenied:
                raise
            except (Exception, asyncio.CancelledError):
                pass
        raise BindingDenied("RESULT_UNKNOWN", "terminal settlement read unavailable")

    @staticmethod
    def _validate_success_proposal(command):
        value = command["proposed"]
        validate_root(value, command["owner"])
        review = value.artifacts.review
        record = value.artifacts.canonical_record
        result = value.artifacts.released_result
        if (
            value.run.status is not RunStatus.RELEASED
            or value.runtime.run_status is not RunStatus.RELEASED
            or value.run.completed_at is None
            or command["released_at"].tzinfo is None
            or review is None or review.status.value != "PASS"
            or value.runtime.binding_ref != value.node_binding.reference()
            or record is None or result is None
            or record.run_id != value.run.run_id or result.run_id != value.run.run_id
            or result.canonical_record_id != record.record_id
            or review.review_id not in record.review_refs
            or record.actual_graph != value.runtime.actual_graph.model_dump(mode="json")
            or record.planned_graph != value.runtime.planned_graph.model_dump(mode="json")
        ):
            raise BindingDenied("IDENTITY_MISMATCH", "terminal success proposal")

    async def _success_transaction(self, command, budget, *, readback):
        from sqlalchemy import text

        session = self._sessions()
        driver = None
        raw = None
        connection = None
        deadline = min(budget.deadline, asyncio.get_running_loop().time() + 180)
        acknowledged = False
        command["attempt_deadline"] = deadline
        try:
            async with asyncio.timeout_at(deadline):
                command["phase"] = "BEGIN"
                # Pin the physical checkout through commit AND outcome cleanup.
                # A session-owned checkout is returned by commit/rollback, which
                # would let another caller reuse an uncertain connection before
                # invalidation (or let cleanup terminate that caller's work).
                connection = await session.bind.connect()
                await session.close()
                session = self._sessions(bind=connection)
                await session.begin()
                if connection.dialect.name != "postgresql":
                    raise BindingDenied("IDENTITY_MISMATCH", "PostgreSQL settlement required")
                raw = await connection.get_raw_connection()
                driver = raw.driver_connection
                await session.execute(text("SET LOCAL lock_timeout = '30s'"))
                await session.execute(text("SET LOCAL statement_timeout = '120s'"))
                run_id = command["owner"].run_id if command["owner"] else command["run_id"]
                row = await session.scalar(select(ResearchRunAggregateRow).where(
                    ResearchRunAggregateRow.run_id == run_id,
                ).with_for_update())
                if row is None:
                    raise BindingDenied("STATE_REFRESH_REQUIRED", run_id)
                command["phase"] = "PRECOMMIT"
                current = self._from_row(row)
                validate_root(current)
                if current.runtime.binding_ref != current.node_binding.reference():
                    raise BindingDenied("IDENTITY_MISMATCH", "terminal root reference")
                result = await self._inspect_success(session, row, current, command)
                if result is not None or readback:
                    await session.rollback()
                    if asyncio.get_running_loop().time() >= deadline:
                        raise TimeoutError("terminal readback expired")
                    budget.require_remaining()
                    if result is not None:
                        from src.runtime.scheduler import resume_liveness

                        scope = resume_liveness.get()
                        if scope is not None and scope.run_id == run_id:
                            scope.settled()
                    return result
                compare_whole(current, command["proposed"])
                validate_root(current, command["owner"])
                if command["proposed"].run.updated_at != max(
                    current.run.updated_at, command["proposed"].run.completed_at,
                ):
                    raise BindingDenied("IDENTITY_MISMATCH", "terminal updated_at")
                await self._verify_success_materials(
                    session, command["proposed"], command["report_store"],
                )
                for binding in current.node_binding.results.values():
                    await self.verify_materials(binding.output_records, run_id=run_id,
                                                session=session)
                proposed = deepcopy(command["proposed"])
                await self._close_execution_state(proposed, command["owner"], unknown=False)
                proposed.node_binding.binding_revision += 1
                proposed.runtime.binding_ref = proposed.node_binding.reference()
                row.payload = self._payload(proposed)
                row.status = "RELEASED"
                row.updated_at = proposed.run.completed_at
                events = await self._persist_success_events(session, row, proposed, command)
                session.info["wp02_root_write"] = (run_id, proposed.node_binding.binding_revision)
                await self._persist_children(session, proposed)
                await session.flush()
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError("terminal settlement expired before COMMIT")
                # This await is the ambiguity boundary, including cancellation.
                command["phase"] = "COMMIT_ENTERED"
                command["outcome"] = "COMMIT_AMBIGUOUS"
                await self._commit_success(session)
                acknowledged = True
                from src.runtime.scheduler import resume_liveness

                scope = resume_liveness.get()
                if scope is not None and scope.run_id == run_id:
                    scope.settled()
                command["phase"] = "COMMIT_ACKNOWLEDGED"
                command["outcome"] = "COMMITTED"
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError("terminal settlement acknowledgement arrived overdue")
                return proposed, events
        finally:
            # Stop the physical writer before returning from an uncertain await.
            # asyncpg.terminate aborts its transport synchronously; never shield a
            # still-authorized writer or reuse its connection for resolution.
            discard = not acknowledged or budget.remaining() <= 0
            if discard and driver is not None and raw.is_valid:
                driver.terminate()
                # Outside SQLAlchemy's greenlet this is its synchronous force
                # termination path. Return the invalidated pool slot even when
                # the outer deadline leaves no time for session housekeeping.
                raw.invalidate()
                raw.close()
            remaining = budget.remaining()
            if remaining > 0:
                try:
                    async with asyncio.timeout(min(remaining, 1.0)):
                        if not acknowledged:
                            await session.invalidate()
                        await session.close()
                        if connection is not None:
                            await connection.close()
                except (Exception, asyncio.CancelledError):
                    if driver is not None and raw.is_valid:
                        driver.terminate()
                        raw.invalidate()
                        raw.close()

    async def _commit_success(self, session):
        await session.commit()

    async def _persist_success_events(self, session, row, value, command):
        from uuid import NAMESPACE_URL, uuid5

        from sqlalchemy import insert, update

        from src.domain.runtime_event import RuntimeEventType, normalize_runtime_event_v1
        from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore

        await PostgresRuntimeEventStore._lock_run_event_writes(session, value.run.run_id)
        await PostgresRuntimeEventStore._reject_post_terminal_write(session, value.run.run_id)
        events = []
        for kind, timestamp, payload in (
            (RuntimeEventType.RELEASE_COMPLETED, command["released_at"], {
                "canonical_record_id": value.artifacts.canonical_record.record_id,
                "result_id": value.artifacts.released_result.result_id,
            }),
            (RuntimeEventType.RUN_COMPLETED, value.run.completed_at, {"status": "RELEASED"}),
        ):
            identity = "terminal-success/v1:" + kind.value + ":" + command["identity"]
            event_id = "EVT-" + str(uuid5(NAMESPACE_URL, identity))
            sequence = await session.scalar(insert(RuntimeEventRow).values(
                event_id=event_id, run_id=value.run.run_id, sequence=None, payload={},
            ).returning(RuntimeEventRow.sequence))
            event = RuntimeEvent(event_id=event_id, run_id=value.run.run_id, type=kind,
                                 timestamp=timestamp, sequence=sequence, payload=payload)
            normalize_runtime_event_v1(event)
            await session.execute(update(RuntimeEventRow).where(
                RuntimeEventRow.event_id == event_id,
            ).values(payload=event.model_dump(mode="json")))
            events.append(event)
        row.projection_sequence = events[-1].sequence
        row.projection_revision += 1
        return tuple(events)

    async def _inspect_success(self, session, row, value, command):
        from uuid import NAMESPACE_URL, uuid5

        from src.domain.node_binding import OwnerToken, canonical_value, digest
        from src.infrastructure.database.models import RuntimeEventCounterRow
        from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore

        raw = list(await session.scalars(select(RuntimeEventRow).where(
            RuntimeEventRow.run_id == value.run.run_id,
        ).order_by(RuntimeEventRow.sequence)))
        events = [PostgresRuntimeEventStore._decode_row(value.run.run_id, item) for item in raw]
        counter = await session.get(RuntimeEventCounterRow, value.run.run_id)
        tail = events[-1].sequence if events else 0
        if [event.sequence for event in events] != list(range(1, tail + 1)) or (
            (counter.last_sequence if counter else 0) != tail
        ):
            raise BindingDenied("IDENTITY_MISMATCH", "terminal event allocator")
        terminal = [event for event in events if event.type.value in {
            "release.completed", "run.completed",
        }]
        root = value.node_binding
        if (not terminal and value.run.status is not RunStatus.RELEASED
                and root.lifecycle != "CLOSED"):
            if (value.artifacts.released_result is not None
                    or value.artifacts.canonical_record is not None):
                raise BindingDenied("IDENTITY_MISMATCH", "partial release children")
            if command["owner"] is None:
                return None
            compare_whole(value, command["proposed"])
            validate_root(value, command["owner"])
            snapshot = (row.payload, row.status, row.updated_at, row.projection_sequence,
                        row.projection_revision, tail, await self._success_children(session, value))
            if command["baseline"] is not None and command["baseline"] != snapshot:
                raise BindingDenied("IDENTITY_MISMATCH", "settlement no-effect baseline")
            command["baseline"] = deepcopy(snapshot)
            command["outcome"] = "KNOWN_NOT_COMMITTED"
            return None
        if (len(terminal) != 2 or len(events) < 2 or events[-2:] != terminal
                or [e.type.value for e in terminal] != ["release.completed", "run.completed"]
                or value.run.status is not RunStatus.RELEASED or row.status != "RELEASED"
                or value.runtime.run_status is not RunStatus.RELEASED or root.lifecycle != "CLOSED"
                or value.runtime.binding_ref != root.reference()
                or row.projection_revision < 2
                or row.updated_at != value.run.completed_at
                or value.run.updated_at < value.run.completed_at
                or row.projection_sequence != terminal[-1].sequence):
            raise BindingDenied("IDENTITY_MISMATCH", "partial terminal settlement")
        owner = command["owner"] or OwnerToken(run_id=value.run.run_id,
                                               owner_id=root.owner_id,
                                               owner_generation=root.owner_generation - 1)
        if (root.owner_id != owner.owner_id or root.owner_generation != owner.owner_generation + 1):
            raise BindingDenied("STALE_WRITE_REJECTED", "terminal settlement owner")
        identity = digest(canonical_value(owner), "terminal-success/v1")
        record, result = value.artifacts.canonical_record, value.artifacts.released_result
        if record is None or result is None or result.canonical_record_id != record.record_id:
            raise BindingDenied("IDENTITY_MISMATCH", "terminal release identity")
        for event in terminal:
            expected = "EVT-" + str(uuid5(NAMESPACE_URL,
                "terminal-success/v1:" + event.type.value + ":" + identity))
            if event.event_id != expected or event.task_id is not None:
                raise BindingDenied("IDENTITY_MISMATCH", "terminal event identity")
        if (terminal[0].payload != {"canonical_record_id": record.record_id,
                                    "result_id": result.result_id}
                or terminal[1].payload != {"status": "RELEASED"}
                or terminal[1].timestamp != value.run.completed_at):
            raise BindingDenied("IDENTITY_MISMATCH", "terminal event correspondence")
        self._validate_success_proposal({
            "owner": None, "proposed": value, "released_at": terminal[0].timestamp,
        })
        await self._success_children(session, value)
        await self._verify_success_materials(session, value, command["report_store"])
        if command["owner"] is not None:
            expected = deepcopy(command["proposed"])
            await self._close_execution_state(expected, owner, unknown=False)
            expected.node_binding.binding_revision += 1
            expected.runtime.binding_ref = expected.node_binding.reference()
            if (self._payload(expected) != self._payload(value)
                    or command["released_at"] != terminal[0].timestamp):
                raise BindingDenied("IDENTITY_MISMATCH", "terminal command replay")
            if command["baseline"] is not None and (
                row.projection_revision != command["baseline"][4] + 1
                or terminal[-1].sequence != command["baseline"][5] + 2
            ):
                raise BindingDenied("IDENTITY_MISMATCH", "terminal publication revision")
        command["outcome"] = "COMMITTED"
        return value, tuple(terminal)

    async def _verify_success_materials(self, session, value, report_store):
        from src.application.closure_policy import release_requirement_gaps

        if release_requirement_gaps(value):
            raise BindingDenied("IDENTITY_MISMATCH", "terminal release requirements")
        for binding in value.node_binding.results.values():
            await self.verify_materials(binding.output_records, run_id=value.run.run_id,
                                        session=session)
        if value.node_binding.replan is not None:
            from src.application.risk_replan import control

            await self.verify_materials([control(value).candidate.output_record],
                                        run_id=value.run.run_id, session=session)
        for artifact in value.artifacts.report_artifacts:
            if (artifact.run_id != value.run.run_id
                    or artifact.canonical_record_id != value.artifacts.canonical_record.record_id
                    or artifact.released_result_id != value.artifacts.released_result.result_id):
                raise BindingDenied("IDENTITY_MISMATCH", "terminal report identity")
        # Verify the already-prepared bytes with their existing controlled owner.
        # Only read-only filesystem work may outlive cancellation; no DB writer
        # is dispatched to a thread or detached task.
        html = [a for a in value.artifacts.report_artifacts if a.artifact_type == "text/html"]
        if len(html) != 1:
            raise BindingDenied("IDENTITY_MISMATCH", "required HTML report")
        for artifact in value.artifacts.report_artifacts:
            try:
                await asyncio.to_thread(report_store.read_verified, artifact)
            except (ValueError, OSError) as exc:
                raise BindingDenied("IDENTITY_MISMATCH", "terminal report bytes") from exc

    async def _success_children(self, session, value):
        """Compare the actual required normalized children with the aggregate."""
        groups = (
            (TaskRow, value.runtime.actual_graph.tasks, "task_id"),
            (CalculationRecordRow, value.artifacts.calculations, "calculation_id"),
            (CorrectionRecordRow, value.artifacts.corrections, "correction_id"),
            (ReplanRecordRow, value.artifacts.replans, "replan_id"),
            (ReviewRecordRow, [value.artifacts.review]
             if value.artifacts.review else [], "review_id"),
            (CanonicalExecutionRecordRow, [value.artifacts.canonical_record]
             if value.artifacts.canonical_record else [], "record_id"),
            (ReleasedResearchResultRow, [value.artifacts.released_result]
             if value.artifacts.released_result else [], "result_id"),
            (ReportArtifactRecordRow, value.artifacts.report_artifacts, "artifact_id"),
        )
        snapshot = []
        for model, records, key in groups:
            rows = list(await session.scalars(
                select(model).where(model.run_id == value.run.run_id)))
            actual = {getattr(item, key): item.payload for item in rows}
            expected = {getattr(item, key): item.model_dump(mode="json") for item in records}
            if actual != expected:
                raise BindingDenied("IDENTITY_MISMATCH", "terminal child " + model.__tablename__)
            snapshot.append(actual)
        scheme = await session.get(ResearchSchemeSnapshotRow, value.scheme.scheme_id)
        if (scheme is None or not scheme.confirmed
                or scheme.payload != value.scheme.model_dump(mode="json")):
            raise BindingDenied("IDENTITY_MISMATCH", "terminal Scheme")
        rows = list(await session.scalars(select(TaskDependencyRow).where(
            TaskDependencyRow.run_id == value.run.run_id,
        )))
        actual = {(r.graph_kind, r.task_id, r.position, r.dependency_task_id) for r in rows}
        expected = {(kind, task.task_id, position, dependency)
                    for kind, graph in (("PLANNED", value.runtime.planned_graph),
                                        ("ACTUAL", value.runtime.actual_graph))
                    for task in graph.tasks
                    for position, dependency in enumerate(task.dependencies)}
        if actual != expected:
            raise BindingDenied("IDENTITY_MISMATCH", "terminal graph dependencies")
        return snapshot

    async def _replay_failure(self, session, aggregate, command):
        from src.application.terminal_failure import FailureReplay
        from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore

        PostgresRuntimeEventStore._require_postgresql(session)
        row = await session.get(RuntimeEventRow, command["event_id"])
        if row is not None:
            root = await session.get(ResearchRunAggregateRow, aggregate.run.run_id)
            event = await self._validate_failure_full_set(session, root, command)
            raise FailureReplay(event)

    async def _validate_failure_full_set(self, session, row, command, *, expected_revision=None):
        """One locked proof for every PostgreSQL failure COMMITTED exit."""
        from src.application.terminal_failure import verify_failure_replay
        from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
        from src.runtime.events import EventReconciliationRequired

        try:
            value = self._from_row(row)
            validate_root(value)
            owner = command["owner"]
            root = value.node_binding
            event_row = await session.get(RuntimeEventRow, command["event_id"])
            latest = await session.scalar(select(RuntimeEventRow).where(
                RuntimeEventRow.run_id == row.run_id,
            ).order_by(RuntimeEventRow.sequence.desc()).limit(1))
            if event_row is None or latest is None:
                raise BindingDenied("INTEGRITY_STOP", "terminal event missing")
            event = PostgresRuntimeEventStore._decode_row(row.run_id, event_row)
            metadata = event.payload.get("terminal_failure")
            if not isinstance(metadata, dict):
                raise BindingDenied("INTEGRITY_STOP", "terminal failure metadata missing")
            revision = metadata.get("terminal_failure_projection_revision")
            if type(revision) is not int or revision < 1:
                raise BindingDenied("INTEGRITY_STOP", "terminal revision anchor missing")
            predecessor = await session.scalar(select(RuntimeEventRow).where(
                RuntimeEventRow.run_id == row.run_id,
                RuntimeEventRow.sequence == event.sequence - 1,
            ))
            causal_id = metadata.get("causal_task_failed_event_id")
            causal = await session.get(RuntimeEventRow, causal_id) if causal_id else None
            if metadata.get("request_digest") != command["request_digest"]:
                raise BindingDenied("IDENTITY_MISMATCH", "terminal failure command")
            if (row.projection_revision < revision
                    or (expected_revision is not None and revision != expected_revision)
                    or row.projection_sequence != event.sequence
                    or latest.event_id != event.event_id
                    or metadata.get("predecessor_event_id") != (
                        predecessor.event_id if predecessor else None
                    )
                    or metadata.get("predecessor_sequence") != (
                        predecessor.sequence if predecessor else 0
                    )
                    or (causal_id is None) != (
                        metadata.get("causal_task_failed_sequence") is None
                    )
                    or (causal_id is not None and (
                        causal is None or causal.run_id != row.run_id
                        or causal.sequence != metadata["causal_task_failed_sequence"]
                        or causal.payload.get("type") != "task.failed"
                    ))
                    or row.status != "FAILED"
                    or value.run.status is not RunStatus.FAILED
                    or value.runtime.run_status is not RunStatus.FAILED
                    or value.run.run_id != row.run_id
                    or value.run.research_object_id != row.object_id
                    or root.owner_generation != owner["owner_generation"] + 1
                    or root.lifecycle not in {"CLOSED", "RESULT_UNKNOWN",
                                              "EXTERNAL_FAILURE_PAUSED"}
                    or (root.owner_id is None) !=
                    (root.lifecycle == "EXTERNAL_FAILURE_PAUSED")
                    or (root.owner_id is not None and root.owner_id != owner["owner_id"])):
                raise BindingDenied("INTEGRITY_STOP", "terminal revision lineage")
            verify_failure_replay(value, event, command)
            await self._success_children(session, value)
            for binding in root.results.values():
                await self.verify_materials(binding.output_records, run_id=row.run_id,
                                            session=session)
            if root.replan is not None:
                from src.application.risk_replan import control

                await self.verify_materials([control(value).candidate.output_record],
                                            run_id=row.run_id, session=session)
            return event
        except BindingDenied as exc:
            if exc.code == "INTEGRITY_STOP" or (
                exc.code == "IDENTITY_MISMATCH"
                and exc.subject == "terminal failure command"
            ):
                raise
            raise BindingDenied("INTEGRITY_STOP", "terminal failure full set") from exc
        except (KeyError, TypeError, ValueError, AttributeError,
                EventReconciliationRequired) as exc:
            raise BindingDenied("INTEGRITY_STOP", "terminal failure full set") from exc

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
                aggregate, command, predecessor, causal, row.projection_revision + 1,
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
        aggregate = cls._from_row(row)
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
            aggregate = self._from_row(row)
            validate_root(aggregate)
            return {**projection(aggregate), "projection_revision": row.projection_revision,
                    "projection_sequence": row.projection_sequence}

    async def get_run_fresh(self, run_id):
        async with self._sessions() as session:
            row = await session.get(ResearchRunAggregateRow, run_id)
            return (self._from_row(row)
                    if row is not None else None)

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
            current = self._from_row(row)
            from src.application.repository import compare_confirmed_identity

            compare_confirmed_identity(current, aggregate)
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
            aggregate = self._from_row(row)
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
            authoritative = self._from_row(row)
            from src.application.repository import compare_confirmed_identity

            compare_confirmed_identity(authoritative, aggregate)
            if projection_sequence <= row.projection_sequence:
                return
            if row.payload.get("node_binding") is not None or row.payload.get(
                "node_binding_required"
            ):
                # Events can advance a watermark, never replace committed business facts.
                authoritative = self._from_row(row)
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
        aggregate = self._from_row(row)
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
        return [self._from_row(row) for row in rows]

    @classmethod
    @observe("persistence.aggregate_serialization", aggregate="aggregate")
    def _payload(cls, aggregate: RunAggregate) -> dict:
        from src.application.repository import confirmed_risk_authority

        confirmed_risk_authority(aggregate)
        authority = ({
            "aggregate_schema_version": 2,
            "confirmed_risk_semantic_binding":
                aggregate.confirmed_risk_semantic_binding.model_dump(mode="json"),
        } if aggregate.aggregate_schema_version == 2 else {})
        return {
            **authority,
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
        from src.application.repository import validate_new_confirmation

        validate_new_confirmation(aggregate)
        return ResearchRunAggregateRow(
            aggregate_schema_version=2,
            run_id=aggregate.run.run_id,
            object_id=aggregate.run.research_object_id,
            status=aggregate.run.status.value,
            payload=cls._payload(aggregate),
            updated_at=aggregate.run.created_at,
        )

    @staticmethod
    @observe("persistence.children", aggregate="aggregate")
    async def _persist_children(session: AsyncSession, aggregate: RunAggregate) -> None:
        from src.application.repository import confirmed_risk_authority

        confirmed_risk_authority(aggregate)
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

    @classmethod
    def _from_row(cls, row: ResearchRunAggregateRow) -> RunAggregate:
        aggregate = cls._to_aggregate(row.payload, row.aggregate_schema_version)
        if (aggregate.run.run_id != row.run_id
                or aggregate.run.research_object_id != row.object_id):
            raise BindingDenied("CONFIRMED_AUTHORITY_MISMATCH", "durable Run identity")
        return aggregate

    @staticmethod
    def _to_aggregate(payload: dict, aggregate_schema_version: int) -> RunAggregate:
        if type(aggregate_schema_version) is not int or aggregate_schema_version not in (1, 2):
            raise BindingDenied("CONFIRMED_AUTHORITY_CORRUPT", "row schema version")
        if aggregate_schema_version == 2:
            if (type(payload.get("aggregate_schema_version")) is not int
                    or payload["aggregate_schema_version"] != 2
                    or not payload.get("confirmed_risk_semantic_binding")):
                raise BindingDenied("CONFIRMED_AUTHORITY_CORRUPT", "required v2 envelope")
        elif ("aggregate_schema_version" in payload
              or "confirmed_risk_semantic_binding" in payload):
            raise BindingDenied("CONFIRMED_AUTHORITY_CORRUPT", "mixed v1 envelope")
        from src.domain.risk_admission import ConfirmedRiskSemanticBindingV1

        try:
            receipt = (ConfirmedRiskSemanticBindingV1.model_validate(
                payload["confirmed_risk_semantic_binding"]
            ) if aggregate_schema_version == 2 else None)
        except ValueError as exc:
            raise BindingDenied("CONFIRMED_AUTHORITY_CORRUPT", "receipt schema") from exc
        runtime_payload = payload["runtime"]
        binding = payload.get("node_binding")
        if binding is not None and payload.get("node_binding_required") != SCHEMA:
            raise BindingDenied("STATE_REFRESH_REQUIRED", "binding marker mismatch")
        if payload.get("node_binding_required") and (
            payload["node_binding_required"] != SCHEMA or binding is None
        ):
            if not (binding is None and receipt is not None
                    and receipt.risk_semantic_mode == "D01_V1"):
                raise BindingDenied("STATE_REFRESH_REQUIRED", "missing/unknown required binding")
            # The shared gate checks Run identity before issuing AUTHORITY_MISSING.
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
            aggregate_schema_version=aggregate_schema_version,
            confirmed_risk_semantic_binding=receipt,
        )
        if aggregate_schema_version == 1:
            from src.application.models import _HistoricalCodecProvenance

            aggregate._historical_codec_provenance = _HistoricalCodecProvenance.PERSISTED_V1
        aggregate.artifacts = CompletedRunArtifacts.model_validate(payload["artifacts"])
        from src.application.repository import confirmed_risk_authority

        confirmed_risk_authority(aggregate)
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
    aggregate = SQLAlchemyApplicationRepository._from_row(row)
    if aggregate.node_binding is None:
        return
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
    if row is not None:
        SQLAlchemyApplicationRepository._from_row(row)
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
