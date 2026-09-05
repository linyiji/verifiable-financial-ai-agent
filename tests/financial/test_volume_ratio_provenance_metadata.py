from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext

import pytest

import src.assurance.independent_financial_review as independent_review
import src.output.financial_metrics as financial_metrics
from src.adapters.finrobot.technical import VolumeRatio20Capability
from src.domain.capability import CapabilityContext
from src.domain.enums import (
    CorporateActionStatus,
    EvidenceCategory,
    EvidenceStatus,
    TechnicalPriceBasis,
)
from src.domain.evidence import EvidenceRecord
from src.domain.report import CanonicalReportDTO


def _history() -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    retrieved_at = datetime(2026, 9, 5, tzinfo=UTC)
    for index in range(20):
        as_of = date(2026, 8, 1) + timedelta(days=index)
        common = {
            "run_id": "RUN-VOLUME-PROVENANCE",
            "object_id": "OBJ-NVDA",
            "provider": "fmp",
            "source_locator": "/stable/historical-price-eod/full",
            "source_endpoint": "/stable/historical-price-eod/full",
            "evidence_purpose": "historical_market_context",
            "evidence_category": EvidenceCategory.MARKET,
            "retrieved_at": retrieved_at,
            "period": "DAILY",
            "as_of": as_of,
            "raw_artifact_ref": "artifact://live-history",
            "snapshot_hash": "sha256:live-history",
            "status": EvidenceStatus.ACCEPTED,
        }
        records.extend(
            (
                EvidenceRecord(
                    evidence_id=f"EVD-CLOSE-{index:02d}",
                    normalized_field="close",
                    normalized_value=str(100 + index),
                    unit="CURRENCY",
                    currency="USD",
                    technical_price_basis=TechnicalPriceBasis.RAW_CLOSE,
                    corporate_action_status=CorporateActionStatus.UNASSESSED,
                    **common,
                ),
                EvidenceRecord(
                    evidence_id=f"EVD-VOLUME-{index:02d}",
                    normalized_field="volume",
                    normalized_value=str(1_000 + index),
                    unit="COUNT",
                    **common,
                ),
            )
        )
    return records


@pytest.mark.asyncio
async def test_volume_ratio_retains_only_supported_provenance_across_release_views() -> None:
    history = _history()
    context = CapabilityContext(
        run_id="RUN-VOLUME-PROVENANCE",
        task_id="TASK-VOLUME-PROVENANCE",
        accepted_evidence_ids=[item.evidence_id for item in history],
    )
    calculation = await VolumeRatio20Capability().execute(
        {"history": history, "calculation_id": "CALC-VOLUME-PROVENANCE"}, context
    )
    volume_evidence = tuple(item for item in history if item.normalized_field == "volume")
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        expected_value = Decimal("1019") / (
            sum((Decimal(str(1_000 + index)) for index in range(20)), start=Decimal(0))
            / Decimal(20)
        )
    assert calculation.output_value == expected_value
    assert calculation.input_evidence_ids == [item.evidence_id for item in volume_evidence]
    assert len(calculation.input_evidence_ids) == 20
    assert "technical_price_basis" not in calculation.input_values_snapshot
    assert "corporate_action_status" not in calculation.input_values_snapshot
    metric = financial_metrics._metric(calculation, volume_evidence)
    assert metric.canonical_value == str(expected_value)
    assert metric.evidence_ids == tuple(calculation.input_evidence_ids)
    assert metric.technical_price_basis is None
    assert metric.corporate_action_status is None
    assert metric.corporate_action_guard_refs == ()
    assert independent_review._snapshot_matches(calculation, volume_evidence)
    assert independent_review._metric_matches(calculation, metric, volume_evidence)
    dto = CanonicalReportDTO(
        canonical_record_id="CANONICAL-VOLUME-PROVENANCE",
        released_result_id="RELEASED-VOLUME-PROVENANCE",
        run_id=context.run_id,
        research_object="NVDA",
        released_metrics=(metric,),
        calculation_refs=(calculation.calculation_id,),
    )
    serialized_metric = dto.model_dump(mode="json")["released_metrics"][0]
    assert serialized_metric["technical_price_basis"] is None
    assert serialized_metric["corporate_action_status"] is None
    assert serialized_metric["evidence_ids"] == calculation.input_evidence_ids
