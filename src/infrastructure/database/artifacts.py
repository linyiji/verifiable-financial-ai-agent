"""Typed durable repositories for run records stored as canonical JSON payloads."""

from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.persistence import (
    CalculationRecordRow,
    CanonicalExecutionRecordRow,
    ReleasedResearchResultRow,
    ReviewRecordRow,
    TaskRow,
)
from src.domain.calculation import CalculationRecord
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.correction import CorrectionRecord
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.review import ReviewRecord
from src.domain.task import ReplanRequest, Task
from src.infrastructure.database.models import CorrectionRecordRow, ReplanRecordRow

ModelT = TypeVar("ModelT", bound=BaseModel)


class SQLAlchemyRunRecordRepository:
    """Read/write individual durable records without duplicating domain logic."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save_task(self, entity: Task) -> Task:
        await self._upsert(TaskRow, "task_id", entity.task_id, entity.run_id, entity)
        return entity

    async def list_tasks(self, run_id: str) -> list[Task]:
        return await self._list(TaskRow, Task, run_id)

    async def save_calculation(self, entity: CalculationRecord) -> CalculationRecord:
        await self._upsert(
            CalculationRecordRow,
            "calculation_id",
            entity.calculation_id,
            entity.run_id,
            entity,
        )
        return entity

    async def list_calculations(self, run_id: str) -> list[CalculationRecord]:
        return await self._list(CalculationRecordRow, CalculationRecord, run_id)

    async def save_correction(self, entity: CorrectionRecord) -> CorrectionRecord:
        await self._upsert(
            CorrectionRecordRow,
            "correction_id",
            entity.correction_id,
            entity.run_id,
            entity,
        )
        return entity

    async def list_corrections(self, run_id: str) -> list[CorrectionRecord]:
        return await self._list(CorrectionRecordRow, CorrectionRecord, run_id)

    async def save_replan(self, entity: ReplanRequest) -> ReplanRequest:
        await self._upsert(
            ReplanRecordRow,
            "replan_id",
            entity.replan_id,
            entity.run_id,
            entity,
        )
        return entity

    async def list_replans(self, run_id: str) -> list[ReplanRequest]:
        return await self._list(ReplanRecordRow, ReplanRequest, run_id)

    async def save_review(self, entity: ReviewRecord) -> ReviewRecord:
        await self._upsert(
            ReviewRecordRow,
            "review_id",
            entity.review_id,
            entity.run_id,
            entity,
        )
        return entity

    async def list_reviews(self, run_id: str) -> list[ReviewRecord]:
        return await self._list(ReviewRecordRow, ReviewRecord, run_id)

    async def save_canonical(self, entity: CanonicalExecutionRecord) -> CanonicalExecutionRecord:
        await self._upsert(
            CanonicalExecutionRecordRow,
            "record_id",
            entity.record_id,
            entity.run_id,
            entity,
        )
        return entity

    async def get_canonical(self, run_id: str) -> CanonicalExecutionRecord | None:
        return await self._one(CanonicalExecutionRecordRow, CanonicalExecutionRecord, run_id)

    async def save_released(self, entity: ReleasedResearchResult) -> ReleasedResearchResult:
        await self._upsert(
            ReleasedResearchResultRow,
            "result_id",
            entity.result_id,
            entity.run_id,
            entity,
        )
        return entity

    async def get_released(self, run_id: str) -> ReleasedResearchResult | None:
        return await self._one(ReleasedResearchResultRow, ReleasedResearchResult, run_id)

    async def _upsert(
        self,
        row_type: type[Any],
        id_field: str,
        entity_id: str,
        run_id: str,
        entity: BaseModel,
    ) -> None:
        async with self._sessions() as session:
            row = await session.get(row_type, entity_id)
            payload = entity.model_dump(mode="json")
            if row is None:
                session.add(row_type(**{id_field: entity_id, "run_id": run_id, "payload": payload}))
            else:
                if row.run_id != run_id:
                    raise ValueError(f"record {entity_id} cannot move between runs")
                row.payload = payload
            await session.commit()

    async def _list(
        self,
        row_type: type[Any],
        model_type: type[ModelT],
        run_id: str,
    ) -> list[ModelT]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(row_type)
                    .where(row_type.run_id == run_id)
                    .order_by(*row_type.__table__.primary_key.columns)
                )
            ).all()
        return [model_type.model_validate(row.payload) for row in rows]

    async def _one(
        self,
        row_type: type[Any],
        model_type: type[ModelT],
        run_id: str,
    ) -> ModelT | None:
        async with self._sessions() as session:
            rows = (
                await session.scalars(select(row_type).where(row_type.run_id == run_id).limit(2))
            ).all()
        if len(rows) > 1:
            raise ValueError(f"run {run_id} has multiple {row_type.__tablename__} records")
        return model_type.model_validate(rows[0].payload) if rows else None
