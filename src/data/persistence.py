from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.enums import EvidenceStatus
from src.domain.evidence import EvidenceRecord
from src.infrastructure.database.base import Base


class EvidenceRecordRow(Base):
    __tablename__ = "evidence_records"

    evidence_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    object_id: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(128))
    source_locator: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period: Mapped[str] = mapped_column(String(64))
    as_of: Mapped[date] = mapped_column(Date)
    raw_artifact_ref: Mapped[str] = mapped_column(String(2048))
    normalized_field: Mapped[str] = mapped_column(String(256))
    normalized_value: Mapped[Any] = mapped_column(JSON)
    unit: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    snapshot_hash: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SQLAlchemyEvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: EvidenceRecord) -> EvidenceRecord:
        self._session.add(_to_row(entity))
        await self._session.flush()
        return entity

    async def get(self, evidence_id: str) -> EvidenceRecord | None:
        row = await self._session.get(EvidenceRecordRow, evidence_id)
        return _to_domain(row) if row else None

    async def list(self) -> list[EvidenceRecord]:
        rows = (await self._session.scalars(select(EvidenceRecordRow))).all()
        return [_to_domain(row) for row in rows]

    async def list_by_run(self, run_id: str) -> list[EvidenceRecord]:
        statement = select(EvidenceRecordRow).where(EvidenceRecordRow.run_id == run_id)
        rows = (await self._session.scalars(statement)).all()
        return [_to_domain(row) for row in rows]


def _to_row(record: EvidenceRecord) -> EvidenceRecordRow:
    payload = record.model_dump(mode="python")
    payload["normalized_value"] = json.loads(
        json.dumps(payload["normalized_value"], default=str)
    )
    payload["status"] = record.status.value
    return EvidenceRecordRow(**payload)


def _to_domain(row: EvidenceRecordRow) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=row.evidence_id,
        run_id=row.run_id,
        object_id=row.object_id,
        provider=row.provider,
        source_locator=row.source_locator,
        retrieved_at=row.retrieved_at,
        period=row.period,
        as_of=row.as_of,
        raw_artifact_ref=row.raw_artifact_ref,
        normalized_field=row.normalized_field,
        normalized_value=row.normalized_value,
        unit=row.unit,
        currency=row.currency,
        snapshot_hash=row.snapshot_hash,
        status=EvidenceStatus(row.status),
        created_at=row.created_at,
    )
