from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from src.application.models import CompletedRunArtifacts, ResearchRunDraft, RunAggregate
from src.application.repository import InMemoryApplicationRepository
from src.domain.enums import RunStatus
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph
from src.infrastructure.database.base import Base
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


class ResearchRunAggregateRow(Base):
    __tablename__ = "research_runs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
            await session.commit()

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
        return aggregate
