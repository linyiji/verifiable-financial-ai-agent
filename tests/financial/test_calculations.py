from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.capabilities.financial.common import (
    MissingEvidenceError,
    NonPositivePriorRevenueError,
    PeriodMismatchError,
    UnacceptedEvidenceError,
    ZeroDenominatorError,
    decimal_value,
)
from src.capabilities.financial.growth import RevenueGrowthCapability, calculate_revenue_growth
from src.capabilities.financial.profitability import (
    EbitdaMarginCapability,
    calculate_ebitda_margin,
)
from src.domain.capability import CapabilityContext
from src.domain.enums import EvidenceStatus
from src.domain.evidence import EvidenceRecord
from src.domain.financial_validation import REVENUE_GROWTH_VALIDATION_REASON


def evidence(
    evidence_id: str,
    field: str,
    period: str,
    value: object,
    status: EvidenceStatus = EvidenceStatus.ACCEPTED,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="RUN-1",
        object_id="OBJ-NVDA",
        provider="fixture",
        retrieved_at=datetime.now(UTC),
        period=period,
        as_of=date(2026, 1, 25),
        raw_artifact_ref=f"fixture://{evidence_id}",
        normalized_field=field,
        normalized_value=value,
        unit="USD_BILLION",
        currency="USD",
        snapshot_hash=f"sha256:{evidence_id}",
        status=status,
    )


def test_formula_normal_negative_and_deterministic() -> None:
    first = calculate_revenue_growth(Decimal("130.5"), Decimal("215.9"))
    second = calculate_revenue_growth(Decimal("130.5"), Decimal("215.9"))
    assert first == second == Decimal("0.6544061302681992337164750958")
    assert calculate_revenue_growth(Decimal("100"), Decimal("80")) == Decimal("-0.2")
    assert calculate_ebitda_margin(Decimal("25"), Decimal("100")) == Decimal("0.25")


def test_nonpositive_prior_and_missing_inputs_fail_explicitly() -> None:
    with pytest.raises(NonPositivePriorRevenueError, match=REVENUE_GROWTH_VALIDATION_REASON):
        calculate_revenue_growth(Decimal("0"), Decimal("1"))
    with pytest.raises(NonPositivePriorRevenueError, match=REVENUE_GROWTH_VALIDATION_REASON):
        calculate_revenue_growth(Decimal("-100"), Decimal("-80"))
    with pytest.raises(ZeroDenominatorError):
        calculate_ebitda_margin(Decimal("1"), Decimal("0"))
    with pytest.raises(MissingEvidenceError):
        decimal_value(None)


@pytest.mark.asyncio
async def test_revenue_growth_requires_accepted_evidence() -> None:
    capability = RevenueGrowthCapability()
    with pytest.raises(UnacceptedEvidenceError):
        await capability.execute(
            {
                "calculation_id": "CALC-1",
                "prior": evidence("E-1", "revenue", "FY2025", 130.5, EvidenceStatus.REJECTED),
                "current": evidence("E-2", "revenue", "FY2026", 215.9),
            },
            CapabilityContext(run_id="RUN-1", task_id="TASK-A"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_value", ["0", "-100"])
async def test_revenue_growth_capability_rejects_nonpositive_prior(
    prior_value: str,
) -> None:
    with pytest.raises(NonPositivePriorRevenueError, match=REVENUE_GROWTH_VALIDATION_REASON):
        await RevenueGrowthCapability().execute(
            {
                "calculation_id": "CALC-NONPOSITIVE",
                "prior": evidence("E-1", "revenue", "FY2025", prior_value),
                "current": evidence("E-2", "revenue", "FY2026", "80"),
            },
            CapabilityContext(run_id="RUN-1", task_id="TASK-A"),
        )


@pytest.mark.asyncio
async def test_revenue_growth_creates_traceable_calculation() -> None:
    record = await RevenueGrowthCapability().execute(
        {
            "calculation_id": "CALC-GROWTH",
            "prior": evidence("E-1", "revenue", "FY2025", 130.5),
            "current": evidence("E-2", "revenue", "FY2026", 215.9),
        },
        CapabilityContext(run_id="RUN-1", task_id="TASK-A", accepted_evidence_ids=["E-1", "E-2"]),
    )
    assert record.input_evidence_ids == ["E-1", "E-2"]
    assert record.output_value == Decimal("0.6544061302681992337164750958")
    assert record.capability_version == "1.1.0"
    assert record.parameters == {
        "formula_expression": "(current_revenue - prior_revenue) / prior_revenue",
        "semantic_precondition": "prior_revenue > 0",
        "financial_validation_reason": REVENUE_GROWTH_VALIDATION_REASON,
    }


@pytest.mark.asyncio
async def test_ebitda_margin_requires_period_alignment() -> None:
    with pytest.raises(PeriodMismatchError):
        await EbitdaMarginCapability().execute(
            {
                "calculation_id": "CALC-MARGIN",
                "ebitda": evidence("E-3", "ebitda", "FY2026", 142.5),
                "revenue": evidence("E-2", "revenue", "FY2025", 215.9),
            },
            CapabilityContext(run_id="RUN-1", task_id="TASK-A"),
        )
