from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.phase4_product.contracts import (
    AvailabilityStatus,
    AvailabilityV1,
    FinancialReviewCheckProjectionV1,
    FinancialReviewProjectionV1,
    MetricProofProjectionV1,
    ReleasedFinancialMetricProjectionV1,
    RepresentationClaimAnchorV1,
    ReviewCorrectionRefV1,
)

NOW = datetime(2026, 9, 5, tzinfo=UTC)
HASH = "sha256:" + "a" * 64


def _subject() -> dict[str, str]:
    return {"subject_type": "RUN", "subject_id": "RUN-A", "run_id": "RUN-A"}


def test_resolved_pass_check_is_forbidden() -> None:
    correction = ReviewCorrectionRefV1(
        correction_id="CORRECTION-A",
        run_id="RUN-A",
        task_id="TASK-A",
        status="RESOLVED",
        resolved_at=NOW,
    )
    with pytest.raises(ValidationError, match="corrected REVIEW/BLOCK"):
        FinancialReviewCheckProjectionV1(
            check_id="CHECK-A",
            check_code="EXACT_INPUT",
            status="PASS",
            subjects=(_subject(),),
            expected={},
            actual={},
            exception_state="RESOLVED",
            correction_refs=(correction,),
            created_at=NOW,
            resolved_at=NOW,
        )


def test_absent_review_requires_every_array_empty() -> None:
    with pytest.raises(ValidationError, match="empty arrays"):
        FinancialReviewProjectionV1(
            projection_revision=1,
            projection_sequence=0,
            object_id="OBJ-A",
            run_id="RUN-A",
            canonical_record_id=None,
            released_result_id=None,
            review_id=None,
            status=None,
            reviewer=None,
            input_snapshot_hash=None,
            reviewed_claim_refs=("CLAIM-A",),
            availability=AvailabilityV1.unavailable(AvailabilityStatus.PENDING, "REVIEW_PENDING"),
        )


def test_unknown_proof_and_financial_applicability_enums_fail_closed() -> None:
    with pytest.raises(ValidationError):
        MetricProofProjectionV1(
            policy_id="POLICY-A",
            requirement="MUST_PROVE",
            status="VALID",
        )

    metric = {
        "run_id": "RUN-A",
        "metric_id": "METRIC-A",
        "name": "SMA",
        "canonical_value": "10",
        "canonical_unit": "CURRENCY",
        "display_value": "10.00",
        "display_unit": "USD",
        "period": "CURRENT",
        "period_basis": "CURRENT",
        "actuality": "ACTUAL",
        "as_of": "2026-09-05",
        "currency": "USD",
        "formula_id": "sma_close_50_v1",
        "capability_id": "sma",
        "calculation_id": "CALC-A",
        "evidence_refs": ("EVIDENCE-A",),
        "claim_refs": ("CLAIM-A",),
        "proof": {
            "policy_id": "POLICY-A",
            "requirement": "NOT_REQUIRED",
            "status": "NOT_REQUIRED",
        },
        "technical_price_basis": "GUESS",
        "corporate_action_status": "MAYBE",
    }
    with pytest.raises(ValidationError):
        ReleasedFinancialMetricProjectionV1.model_validate(metric)


def test_unavailable_representation_anchor_cannot_retain_artifact_id() -> None:
    with pytest.raises(ValidationError, match="exactly when"):
        RepresentationClaimAnchorV1(
            anchor_id=None,
            anchor_kind="REPORT_CLAIM",
            object_id="OBJ-A",
            run_id="RUN-A",
            claim_id="CLAIM-A",
            metric_id="METRIC-A",
            report_id="RESULT-A",
            released_result_id="RESULT-A",
            canonical_record_id="CER-A",
            format="PDF",
            artifact_id="ARTIFACT-PDF-A",
            availability=AvailabilityV1.unavailable(
                AvailabilityStatus.NOT_GENERATED,
                "PDF_NOT_GENERATED_BY_POLICY",
            ),
        )
