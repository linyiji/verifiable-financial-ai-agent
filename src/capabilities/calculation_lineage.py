from __future__ import annotations

from collections.abc import Sequence

from src.domain.calculation import CalculationRecord
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.review import ReviewRecord


def link_calculation_lineage(
    calculations: Sequence[CalculationRecord],
    *,
    review: ReviewRecord,
    canonical_record: CanonicalExecutionRecord,
) -> list[CalculationRecord]:
    """Return linked copies after Review and Canonical records have been built.

    Existing records are never mutated. Reapplying the same links is idempotent, while an attempt
    to replace an established lineage ID fails explicitly.
    """

    if review.run_id != canonical_record.run_id:
        raise ValueError("review and canonical record belong to different runs")
    if review.review_id not in canonical_record.review_refs:
        raise ValueError("canonical record does not reference the review")

    canonical_calculation_ids = set(canonical_record.calculation_refs)
    canonical_evidence_ids = set(canonical_record.evidence_refs)
    linked: list[CalculationRecord] = []
    for calculation in calculations:
        if calculation.run_id != canonical_record.run_id:
            raise ValueError(
                f"calculation {calculation.calculation_id} belongs to a different run"
            )
        if calculation.calculation_id not in canonical_calculation_ids:
            raise ValueError(
                f"canonical record does not reference calculation {calculation.calculation_id}"
            )
        missing_evidence = set(calculation.input_evidence_ids) - canonical_evidence_ids
        if missing_evidence:
            missing = ", ".join(sorted(missing_evidence))
            raise ValueError(
                f"canonical record omits calculation evidence for "
                f"{calculation.calculation_id}: {missing}"
            )
        _require_compatible_link(
            field="review_record_id",
            current=calculation.review_record_id,
            requested=review.review_id,
        )
        _require_compatible_link(
            field="canonical_record_id",
            current=calculation.canonical_record_id,
            requested=canonical_record.record_id,
        )
        linked.append(
            calculation.model_copy(
                deep=True,
                update={
                    "review_record_id": review.review_id,
                    "canonical_record_id": canonical_record.record_id,
                },
            )
        )
    return linked


def _require_compatible_link(*, field: str, current: str | None, requested: str) -> None:
    if current is not None and current != requested:
        raise ValueError(f"cannot replace existing {field}: {current}")
