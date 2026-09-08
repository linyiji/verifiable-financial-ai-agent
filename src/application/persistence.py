from __future__ import annotations

from datetime import datetime

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
from src.application.repository import InMemoryApplicationRepository
from src.data.persistence import SQLAlchemyEvidenceRepository
from src.data.repository import EvidenceRepository
from src.domain.calculation import CalculationRecord
from src.domain.enums import RunStatus
from src.domain.evidence import EvidenceRecord
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
            added = await SQLAlchemyEvidenceRepository(session).add(entity)
            await session.commit()
            return added

    async def get(self, evidence_id: str) -> EvidenceRecord | None:
        async with self._sessions() as session:
            return await SQLAlchemyEvidenceRepository(session).get(evidence_id)

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
        await super().add_run(aggregate)
        async with self._sessions() as session:
            session.add(self._row(aggregate))
            await self._persist_children(session, aggregate)
            await session.commit()

    @observe("persistence.run_save", aggregate="aggregate")
    async def save_run(self, aggregate: RunAggregate) -> None:
        await super().save_run(aggregate)
        async with self._sessions() as session:
            row = await session.get(ResearchRunAggregateRow, aggregate.run.run_id)
            if row is None:
                session.add(self._row(aggregate))
            else:
                row.status = aggregate.run.status.value
                row.payload = self._payload(aggregate)
                row.updated_at = aggregate.run.completed_at or aggregate.run.created_at
            await self._persist_children(session, aggregate)
            await session.commit()

    @observe("persistence.watermark_transaction", aggregate="aggregate")
    async def save_run_with_projection_watermark(
        self,
        aggregate: RunAggregate,
        *,
        projection_sequence: int,
    ) -> None:
        """Persist one aggregate and its public event watermark atomically."""

        if projection_sequence < 1:
            raise ValueError("projection_sequence must be positive")
        await super().save_run(aggregate)
        async with self._sessions() as session, session.begin():
            row = await session.scalar(
                select(ResearchRunAggregateRow)
                .where(ResearchRunAggregateRow.run_id == aggregate.run.run_id)
                .with_for_update()
            )
            if row is None:
                raise KeyError(aggregate.run.run_id)
            if projection_sequence <= row.projection_sequence:
                return
            row.status = aggregate.run.status.value
            row.payload = self._payload(aggregate)
            row.updated_at = aggregate.run.completed_at or aggregate.run.created_at
            row.projection_sequence = projection_sequence
            row.projection_revision += 1
            await self._persist_children(session, aggregate)

    async def save_calculation(self, calculation: CalculationRecord) -> None:
        async with self._sessions() as session:
            payload = calculation.model_dump(mode="json")
            row = await session.get(CalculationRecordRow, calculation.calculation_id)
            if row is not None:
                if row.payload != payload:
                    raise ValueError("calculation identity is immutable")
                return
            session.add(CalculationRecordRow(calculation_id=calculation.calculation_id,
                run_id=calculation.run_id, payload=payload))
            await session.commit()

    async def save_runtime_events(self, events: list[RuntimeEvent]) -> None:
        async with self._sessions() as session:
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
            },
            "artifacts": aggregate.artifacts.model_dump(mode="json"),
        }

    @classmethod
    def _row(cls, aggregate: RunAggregate) -> ResearchRunAggregateRow:
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
            if aggregate.run.reexecution_of_run_id:
                if (
                    not scheme.confirmed
                    or scheme.payload != aggregate.scheme.model_dump(mode="json")
                ):
                    raise ValueError("re-execution cannot rewrite confirmed Scheme")
            else:
                scheme.confirmed = aggregate.scheme.confirmed_at is not None
                scheme.payload = aggregate.scheme.model_dump(mode="json")

        for task in aggregate.runtime.actual_graph.tasks:
            row = await session.get(TaskRow, task.task_id)
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
            if row is None:
                session.add(
                    CalculationRecordRow(
                        calculation_id=calculation.calculation_id,
                        run_id=aggregate.run.run_id,
                        payload=calculation.model_dump(mode="json"),
                    )
                )
            else:
                row.payload = calculation.model_dump(mode="json")

        for correction in aggregate.artifacts.corrections:
            row = await session.get(CorrectionRecordRow, correction.correction_id)
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
        )
        aggregate = RunAggregate(
            run=ResearchRun.model_validate(payload["run"]),
            goal=ResearchGoal.model_validate(payload["goal"]),
            scheme=ResearchSchemeSnapshot.model_validate(payload["scheme"]),
            runtime=runtime,
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
