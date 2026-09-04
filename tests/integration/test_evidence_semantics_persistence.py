from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.data.persistence import EvidenceRecordRow, SQLAlchemyEvidenceRepository
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


@pytest.mark.asyncio
async def test_evidence_ownership_metadata_round_trips_through_sql() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[EvidenceRecordRow.__table__])

    observed_at = datetime(2026, 9, 4, 12, tzinfo=UTC)
    provider_timestamp = datetime(2026, 9, 4, 11, 59, tzinfo=UTC)
    record = EvidenceRecord(
        evidence_id="EVD-SEMANTICS-1",
        run_id="RUN-SEMANTICS",
        object_id="OBJ-NVDA",
        provider="fmp",
        source_locator="fmp://income-statement?symbol=NVDA",
        producer_task_id="RUN-SEMANTICS:evidence",
        source_endpoint="income",
        evidence_purpose="fundamental_financials",
        evidence_category=EvidenceCategory.FINANCIAL_STATEMENT,
        retrieved_at=observed_at,
        observed_at=observed_at,
        provider_timestamp=provider_timestamp,
        period="FY2026",
        period_basis=FinancialPeriodBasis.FY,
        actuality=FinancialActuality.ESTIMATE,
        statement_series="fmp:NVDA:USD:FY:ESTIMATE",
        statement_cohort="fmp:NVDA:USD:FY:ESTIMATE:FY2026:filing-1",
        technical_price_basis=TechnicalPriceBasis.RAW_CLOSE,
        corporate_action_status=CorporateActionStatus.NONE_DETECTED,
        cash_flow_sign_convention=CashFlowSignConvention.NOT_APPLICABLE,
        cash_flow_normalization_applied=True,
        as_of=date(2026, 1, 25),
        raw_artifact_ref="artifact://safe-reference",
        normalized_field="revenue",
        normalized_value="215900000000",
        unit="CURRENCY",
        currency="USD",
        snapshot_hash="safe-hash",
        status=EvidenceStatus.ACCEPTED,
        created_at=observed_at,
    )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        repository = SQLAlchemyEvidenceRepository(session)
        await repository.add(record)
        await session.commit()
        loaded = await repository.get(record.evidence_id)

    await engine.dispose()
    assert loaded is not None
    assert loaded.producer_task_id == record.producer_task_id
    assert loaded.source_endpoint == record.source_endpoint
    assert loaded.evidence_purpose == record.evidence_purpose
    assert loaded.evidence_category is EvidenceCategory.FINANCIAL_STATEMENT
    assert loaded.observed_at is not None
    assert loaded.provider_timestamp is not None
    assert loaded.period_basis is FinancialPeriodBasis.FY
    assert loaded.actuality is FinancialActuality.ESTIMATE
    assert loaded.statement_series == "fmp:NVDA:USD:FY:ESTIMATE"
    assert loaded.statement_cohort == "fmp:NVDA:USD:FY:ESTIMATE:FY2026:filing-1"
    assert loaded.technical_price_basis is TechnicalPriceBasis.RAW_CLOSE
    assert loaded.corporate_action_status is CorporateActionStatus.NONE_DETECTED
    assert loaded.cash_flow_sign_convention is CashFlowSignConvention.NOT_APPLICABLE
    assert loaded.cash_flow_normalization_applied is True
