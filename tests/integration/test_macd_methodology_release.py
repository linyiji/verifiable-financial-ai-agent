from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters.finrobot.professional_reporting import (
    ProfessionalHTMLRenderer,
    ProfessionalPDFRenderer,
)
from src.application.persistence import ReleasedResearchResultRow
from src.domain.enums import (
    CorporateActionStatus,
    FinancialActuality,
    FinancialPeriodBasis,
    FinancialUnit,
    MaterialCalculationDispositionStatus,
    TechnicalPriceBasis,
)
from src.domain.financial_semantics import (
    MaterialCalculationDisposition,
    MaterialFinancialClaim,
    ReleasedFinancialMetric,
    TechnicalMethodMetadata,
)
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.report import CanonicalReportDTO
from src.infrastructure.database.artifacts import SQLAlchemyRunRecordRepository
from src.infrastructure.database.base import Base


def _released_result() -> ReleasedResearchResult:
    method = TechnicalMethodMetadata(
        method="MACD_EMA_12_26_9_FIRST_OBSERVATION_SEED",
        parameters=(("fast", "12"), ("slow", "26"), ("signal", "9")),
        observation_count=200,
        warmup_required=34,
        warmup_satisfied=True,
        first_as_of=date(2026, 1, 1),
        last_as_of=date(2026, 7, 19),
        ema_adjust=False,
        ema_seed="first_observation",
        fast_span=12,
        slow_span=26,
        signal_span=9,
        decimal_context_policy_id="macd-decimal-context-v1",
        decimal_precision=28,
        decimal_rounding="ROUND_HALF_EVEN",
        technical_price_basis=TechnicalPriceBasis.RAW_CLOSE,
    )
    metric = ReleasedFinancialMetric(
        metric_id="METRIC-MACD-LINE",
        calculation_id="CALC-MACD-LINE",
        name="MACD Line 12/26 EMA",
        canonical_value="7.0000000000000000000000000",
        canonical_unit=FinancialUnit.CURRENCY,
        display_value="7.00",
        display_unit="USD",
        period="DAILY",
        period_basis=FinancialPeriodBasis.DAILY,
        actuality=FinancialActuality.ACTUAL,
        as_of=date(2026, 7, 19),
        currency="USD",
        formula_id="macd_line_close_12_26_adjust_false_v1",
        capability_id="technical_macd_12_26_9",
        evidence_ids=("E-MACD-1",),
        method_metadata=method,
        technical_price_basis=TechnicalPriceBasis.RAW_CLOSE,
        corporate_action_status=CorporateActionStatus.UNASSESSED,
        limitations=("RAW_CLOSE methodology fixture.",),
    )
    claim = MaterialFinancialClaim(
        claim_id="CLAIM-MACD-LINE",
        run_id="RUN-MACD-METHOD",
        claim_type="MATERIAL_FINANCIAL_METRIC",
        statement="MACD Line 12/26 EMA was 7.00USD for DAILY as of 2026-07-19.",
        metric_id=metric.metric_id,
        value=metric.canonical_value,
        unit=metric.canonical_unit,
        period=metric.period,
        period_basis=metric.period_basis,
        actuality=metric.actuality,
        as_of=metric.as_of,
        currency=metric.currency,
        calculation_refs=(metric.calculation_id,),
        evidence_refs=metric.evidence_ids,
    )
    disposition = MaterialCalculationDisposition(
        calculation_id=metric.calculation_id,
        metric_id=metric.metric_id,
        status=MaterialCalculationDispositionStatus.REPORTABLE,
    )
    return ReleasedResearchResult(
        result_id="RESULT-MACD-METHOD",
        run_id="RUN-MACD-METHOD",
        canonical_record_id="CANONICAL-MACD-METHOD",
        structured_financial_results={"research_object": "NVDA"},
        released_metrics=(metric,),
        material_claims=(claim,),
        material_calculation_dispositions=(disposition,),
    )


@pytest.mark.asyncio
async def test_macd_methodology_persists_across_restart_and_renders(tmp_path) -> None:
    database_path = tmp_path / "macd-methodology.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[ReleasedResearchResultRow.__table__],
        )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await SQLAlchemyRunRecordRepository(sessions).save_released(_released_result())
    await engine.dispose()

    restarted_engine = create_async_engine(database_url)
    restarted_sessions = async_sessionmaker(restarted_engine, expire_on_commit=False)
    restored = await SQLAlchemyRunRecordRepository(restarted_sessions).get_released(
        "RUN-MACD-METHOD"
    )
    await restarted_engine.dispose()

    assert restored is not None
    metadata = restored.released_metrics[0].method_metadata
    assert metadata is not None
    assert metadata.model_dump(mode="json") == _released_result().released_metrics[
        0
    ].method_metadata.model_dump(mode="json")

    dto = CanonicalReportDTO(
        canonical_record_id="CANONICAL-MACD-METHOD",
        released_result_id=restored.result_id,
        run_id=restored.run_id,
        research_object="NVDA",
        released_metrics=restored.released_metrics,
    )
    html = ProfessionalHTMLRenderer().render(dto)
    pdf = ProfessionalPDFRenderer().render(dto)
    for token in (b"macd-decimal-context-v1", b"ROUND_HALF_EVEN", b"RAW_CLOSE"):
        assert token in html
        assert token in pdf
