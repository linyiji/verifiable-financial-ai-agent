from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, String, false, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.enums import (
    CashFlowSignConvention,
    CorporateActionStatus,
    EvidenceCategory,
    EvidenceStatus,
    FinancialActuality,
    FinancialPeriodBasis,
    TechnicalPriceBasis,
)
from src.domain.evidence import EvidenceRecord
from src.infrastructure.database.base import Base


class EvidenceRecordRow(Base):
    __tablename__ = "evidence_records"

    evidence_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    object_id: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(128))
    source_locator: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    producer_task_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    source_endpoint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_purpose: Mapped[str | None] = mapped_column(String(256), nullable=True)
    evidence_category: Mapped[str] = mapped_column(String(32), default=EvidenceCategory.OTHER.value)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period: Mapped[str] = mapped_column(String(64))
    period_basis: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actuality: Mapped[str] = mapped_column(
        String(16),
        default=FinancialActuality.UNKNOWN.value,
        server_default=FinancialActuality.UNKNOWN.value,
    )
    statement_series: Mapped[str | None] = mapped_column(String(512), nullable=True)
    statement_cohort: Mapped[str | None] = mapped_column(String(768), nullable=True)
    technical_price_basis: Mapped[str | None] = mapped_column(String(32), nullable=True)
    corporate_action_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cash_flow_sign_convention: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cash_flow_normalization_applied: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
    )
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
    payload["normalized_value"] = json.loads(json.dumps(payload["normalized_value"], default=str))
    payload["status"] = record.status.value
    payload["evidence_category"] = record.evidence_category.value
    for field in (
        "period_basis",
        "actuality",
        "technical_price_basis",
        "corporate_action_status",
        "cash_flow_sign_convention",
    ):
        value = getattr(record, field)
        payload[field] = value.value if value is not None else None
    return EvidenceRecordRow(**payload)


def _to_domain(row: EvidenceRecordRow) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=row.evidence_id,
        run_id=row.run_id,
        object_id=row.object_id,
        provider=row.provider,
        source_locator=row.source_locator,
        producer_task_id=row.producer_task_id,
        source_endpoint=row.source_endpoint,
        evidence_purpose=row.evidence_purpose,
        evidence_category=EvidenceCategory(row.evidence_category),
        retrieved_at=row.retrieved_at,
        observed_at=row.observed_at,
        provider_timestamp=row.provider_timestamp,
        period=row.period,
        period_basis=(FinancialPeriodBasis(row.period_basis) if row.period_basis else None),
        actuality=FinancialActuality(row.actuality),
        statement_series=row.statement_series,
        statement_cohort=row.statement_cohort,
        technical_price_basis=(
            TechnicalPriceBasis(row.technical_price_basis) if row.technical_price_basis else None
        ),
        corporate_action_status=(
            CorporateActionStatus(row.corporate_action_status)
            if row.corporate_action_status
            else None
        ),
        cash_flow_sign_convention=(
            CashFlowSignConvention(row.cash_flow_sign_convention)
            if row.cash_flow_sign_convention
            else None
        ),
        cash_flow_normalization_applied=row.cash_flow_normalization_applied,
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
