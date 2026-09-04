from collections.abc import Iterable

from src.domain.base import JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.enums import CalculationStatus, EvidenceStatus, ReviewStatus
from src.domain.evidence import EvidenceRecord
from src.domain.review import ReviewRecord


class DeterministicReviewer:
    """Independent control-plane checks; it is never invoked as an Agent tool."""

    def review(
        self,
        *,
        review_id: str,
        run_id: str,
        evidence: Iterable[EvidenceRecord],
        calculations: Iterable[CalculationRecord],
        semantic_findings: Iterable[JsonObject] = (),
    ) -> ReviewRecord:
        evidence_by_id = {record.evidence_id: record for record in evidence}
        findings: list[JsonObject] = []
        semantic = list(semantic_findings)
        status = ReviewStatus.PASS

        if semantic:
            status = ReviewStatus.REVIEW

        for record in evidence_by_id.values():
            if record.status is not EvidenceStatus.ACCEPTED:
                status = ReviewStatus.BLOCK
                findings.append(
                    {
                        "code": "EVIDENCE_NOT_ACCEPTED",
                        "evidence_id": record.evidence_id,
                        "status": record.status.value,
                    }
                )

        for calculation in calculations:
            if calculation.status is not CalculationStatus.PASS:
                status = ReviewStatus.BLOCK
                findings.append(
                    {
                        "code": "CALCULATION_FAILED",
                        "calculation_id": calculation.calculation_id,
                    }
                )
            missing = sorted(set(calculation.input_evidence_ids) - evidence_by_id.keys())
            if missing:
                status = ReviewStatus.BLOCK
                findings.append(
                    {
                        "code": "EVIDENCE_REFERENCE_MISSING",
                        "calculation_id": calculation.calculation_id,
                        "missing": missing,
                    }
                )
                continue
            periods = [
                evidence_by_id[evidence_id].period for evidence_id in calculation.input_evidence_ids
            ]
            if calculation.formula_id == "ebitda_margin_v1" and len(set(periods)) > 1:
                status = ReviewStatus.BLOCK
                findings.append(
                    {
                        "code": "PERIOD_MISMATCH",
                        "calculation_id": calculation.calculation_id,
                        "periods": periods,
                    }
                )

        return ReviewRecord(
            review_id=review_id,
            run_id=run_id,
            status=status,
            deterministic_findings=findings,
            semantic_findings=semantic,
        )
