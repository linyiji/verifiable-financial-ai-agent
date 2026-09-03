from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType

import pytest

from src.capabilities.calculation_lineage import link_calculation_lineage
from src.capabilities.financial import growth, profitability
from src.capabilities.financial.growth import RevenueGrowthCapability
from src.capabilities.financial.profitability import EbitdaMarginCapability
from src.capabilities.provenance import calculation_source_provenance, sha256_source_bytes
from src.domain.calculation import CalculationRecord
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.capability import CapabilityContext
from src.domain.enums import EvidenceStatus, ReviewStatus
from src.domain.evidence import EvidenceRecord
from src.domain.review import ReviewRecord


def _evidence(evidence_id: str, field: str, period: str, value: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="RUN-PROVENANCE",
        object_id="OBJ-NVDA",
        provider="fixture",
        retrieved_at=datetime(2026, 9, 4, tzinfo=UTC),
        period=period,
        as_of=date(2026, 9, 4),
        raw_artifact_ref=f"fixture://{evidence_id}",
        normalized_field=field,
        normalized_value=value,
        unit="USD_BILLION",
        currency="USD",
        snapshot_hash=f"sha256:{evidence_id}",
        status=EvidenceStatus.ACCEPTED,
    )


async def _calculations() -> list[CalculationRecord]:
    context = CapabilityContext(run_id="RUN-PROVENANCE", task_id="TASK-CALC")
    prior_revenue = _evidence("EVD-PRIOR", "revenue", "FY2025", "130.5")
    current_revenue = _evidence("EVD-CURRENT", "revenue", "FY2026", "215.9")
    ebitda = _evidence("EVD-EBITDA", "ebitda", "FY2026", "142.5")
    growth = await RevenueGrowthCapability().execute(
        {
            "calculation_id": "CALC-GROWTH",
            "prior": prior_revenue,
            "current": current_revenue,
        },
        context,
    )
    margin = await EbitdaMarginCapability().execute(
        {
            "calculation_id": "CALC-MARGIN",
            "ebitda": ebitda,
            "revenue": current_revenue,
        },
        context,
    )
    return [growth, margin]


def _module_source_hash(module: ModuleType) -> str:
    assert module.__file__ is not None
    return sha256_source_bytes(Path(module.__file__).read_bytes())


@pytest.mark.asyncio
async def test_native_calculations_capture_reproducible_source_provenance() -> None:
    first, second = await _calculations()
    repeated, _ = await _calculations()
    variant = await RevenueGrowthCapability().execute(
        {
            "calculation_id": "CALC-GROWTH-VARIANT",
            "prior": _evidence(
                "EVD-PRIOR-VARIANT", "revenue", "FY2024", "100"
            ).model_copy(update={"run_id": "RUN-OTHER"}),
            "current": _evidence(
                "EVD-CURRENT-VARIANT", "revenue", "FY2025", "120"
            ).model_copy(update={"run_id": "RUN-OTHER"}),
        },
        CapabilityContext(run_id="RUN-OTHER", task_id="TASK-OTHER"),
    )

    for record, capability, source_hash in (
        (first, RevenueGrowthCapability, _module_source_hash(growth)),
        (second, EbitdaMarginCapability, _module_source_hash(profitability)),
    ):
        assert record.code_hash == source_hash
        assert record.source_ref == capability.definition.implementation_ref
        assert record.capability_version == "1.0.0"
        assert record.runtime_version is not None
        assert record.runtime_version.startswith("Python 3.11.")
        assert record.proof_ref is None

    assert first.formula_id == "revenue_growth_v1"
    assert second.formula_id == "ebitda_margin_v1"
    assert first.code_hash == repeated.code_hash
    assert first.code_hash == variant.code_hash
    assert first.input_values_snapshot != variant.input_values_snapshot


def test_source_hash_is_path_independent_and_changes_with_source_bytes(tmp_path) -> None:
    first_path = tmp_path / "first.py"
    second_path = tmp_path / "nested" / "second.py"
    second_path.parent.mkdir()
    first_path.write_bytes(b"def calculate():\n    return 1\n")
    second_path.write_bytes(first_path.read_bytes())

    first = calculation_source_provenance(first_path, source_ref="module:calculate")
    second = calculation_source_provenance(second_path, source_ref="module:calculate")
    assert first.code_hash == second.code_hash

    second_path.write_bytes(b"def calculate():\n    return 2\n")
    changed = calculation_source_provenance(second_path, source_ref="module:calculate")
    assert changed.code_hash != first.code_hash


@pytest.mark.asyncio
async def test_linker_copies_calculation_to_evidence_review_and_canonical_lineage() -> None:
    calculations = await _calculations()
    original_evidence = [list(item.input_evidence_ids) for item in calculations]
    review = ReviewRecord(
        review_id="REVIEW-PROVENANCE",
        run_id="RUN-PROVENANCE",
        status=ReviewStatus.PASS,
    )
    canonical = CanonicalExecutionRecord(
        record_id="CER-PROVENANCE",
        run_id="RUN-PROVENANCE",
        planned_graph={},
        actual_graph={},
        calculation_refs=[item.calculation_id for item in calculations],
        evidence_refs=[evidence_id for ids in original_evidence for evidence_id in ids],
        review_refs=[review.review_id],
        runtime_outcome="RELEASED",
    )

    linked = link_calculation_lineage(
        calculations,
        review=review,
        canonical_record=canonical,
    )

    assert all(item.review_record_id is None for item in calculations)
    assert all(item.canonical_record_id is None for item in calculations)
    assert all(item.proof_ref is None for item in linked)
    for index, item in enumerate(linked):
        assert item is not calculations[index]
        assert item.input_evidence_ids == original_evidence[index]
        assert item.review_record_id == review.review_id
        assert item.canonical_record_id == canonical.record_id

    relinked = link_calculation_lineage(linked, review=review, canonical_record=canonical)
    assert relinked == linked


@pytest.mark.asyncio
async def test_linker_rejects_lineage_replacement() -> None:
    calculation = (await _calculations())[0].model_copy(
        update={"review_record_id": "REVIEW-OTHER"}
    )
    review = ReviewRecord(
        review_id="REVIEW-PROVENANCE",
        run_id="RUN-PROVENANCE",
        status=ReviewStatus.PASS,
    )
    canonical = CanonicalExecutionRecord(
        record_id="CER-PROVENANCE",
        run_id="RUN-PROVENANCE",
        planned_graph={},
        actual_graph={},
        calculation_refs=[calculation.calculation_id],
        evidence_refs=list(calculation.input_evidence_ids),
        review_refs=[review.review_id],
        runtime_outcome="RELEASED",
    )

    with pytest.raises(ValueError, match="cannot replace existing review_record_id"):
        link_calculation_lineage([calculation], review=review, canonical_record=canonical)
