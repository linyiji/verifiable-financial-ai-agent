from datetime import UTC, date, datetime

from src.assurance.deterministic_review import DeterministicReviewer
from src.assurance.independent_financial_review import financial_review_input_snapshot_hash
from src.assurance.proof_policy import ProofPolicy, ProofRequirement
from src.assurance.release_gate import ReleaseGate
from src.domain.calculation import CalculationRecord
from src.domain.enums import (
    CalculationStatus,
    EvidenceStatus,
    FinancialActuality,
    FinancialPeriodBasis,
    FinancialUnit,
    ProofStatus,
    ReviewStatus,
)
from src.domain.evidence import EvidenceRecord
from src.domain.financial_semantics import MaterialFinancialClaim, ReleasedFinancialMetric
from src.domain.proof import ProofRecord, ProofResult
from src.domain.review import ReviewCheck, ReviewRecord


def evidence(evidence_id: str, period: str, status: EvidenceStatus) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="RUN-1",
        object_id="OBJ-1",
        provider="fixture",
        retrieved_at=datetime.now(UTC),
        period=period,
        as_of=date(2026, 1, 1),
        raw_artifact_ref="fixture://raw",
        normalized_field="revenue",
        normalized_value=100,
        unit="USD",
        snapshot_hash=f"sha256:{evidence_id}",
        status=status,
    )


def calculation(*, formula_id: str = "revenue_growth_v1") -> CalculationRecord:
    return CalculationRecord(
        calculation_id="CALC-1",
        run_id="RUN-1",
        task_id="TASK-A",
        capability_id="revenue_growth",
        capability_version="1.0.0",
        formula_id=formula_id,
        input_evidence_ids=["E-1", "E-2"],
        output_value="0.25",
        output_unit="ratio",
        status=CalculationStatus.PASS,
    )


def test_review_passes_only_accepted_linked_inputs() -> None:
    review = DeterministicReviewer().review(
        review_id="REV-1",
        run_id="RUN-1",
        evidence=[
            evidence("E-1", "FY2025", EvidenceStatus.ACCEPTED),
            evidence("E-2", "FY2026", EvidenceStatus.ACCEPTED),
        ],
        calculations=[calculation()],
    )
    assert review.status is ReviewStatus.PASS


def test_review_blocks_unaccepted_or_missing_evidence() -> None:
    review = DeterministicReviewer().review(
        review_id="REV-1",
        run_id="RUN-1",
        evidence=[evidence("E-1", "FY2025", EvidenceStatus.REJECTED)],
        calculations=[calculation()],
    )
    assert review.status is ReviewStatus.BLOCK
    assert {finding["code"] for finding in review.deterministic_findings} == {
        "EVIDENCE_NOT_ACCEPTED",
        "EVIDENCE_REFERENCE_MISSING",
    }


def test_semantic_finding_requires_review_without_hard_block() -> None:
    review = DeterministicReviewer().review(
        review_id="REV-1",
        run_id="RUN-1",
        evidence=[
            evidence("E-1", "FY2025", EvidenceStatus.ACCEPTED),
            evidence("E-2", "FY2026", EvidenceStatus.ACCEPTED),
        ],
        calculations=[calculation()],
        semantic_findings=[{"code": "CLAIM_STRENGTH_REVIEW"}],
    )
    assert review.status is ReviewStatus.REVIEW


def test_proof_policy_and_release_gate_control_plane() -> None:
    calc = calculation()
    strict_policy = ProofPolicy(require_material_calculations=True)
    requirement = strict_policy.requirement_for(calc)
    assert requirement is ProofRequirement.MUST_PROVE

    review = DeterministicReviewer().review(
        review_id="REV-1",
        run_id="RUN-1",
        evidence=[
            evidence("E-1", "FY2025", EvidenceStatus.ACCEPTED),
            evidence("E-2", "FY2026", EvidenceStatus.ACCEPTED),
        ],
        calculations=[calc],
    )
    blocked = ReleaseGate().evaluate(
        review=review,
        proof_requirements={calc.calculation_id: requirement},
        proofs={
            calc.calculation_id: ProofResult(proof_id="PROOF-1", status=ProofStatus.NOT_IMPLEMENTED)
        },
    )
    assert blocked.allowed is False
    assert "PROOF_NOT_IMPLEMENTED:CALC-1" in blocked.reason_codes

    allowed = ReleaseGate().evaluate(
        review=review,
        proof_requirements={calc.calculation_id: ProofRequirement.NOT_REQUIRED},
        proofs={},
    )
    assert allowed.allowed is True

    real_proof = ProofRecord(
        proof_id="PROOF-REAL-1",
        run_id=calc.run_id,
        calculation_id=calc.calculation_id,
        backend="risc0",
        program_id=calc.formula_id,
        image_id="IMAGE-1",
        implementation_hash="sha256:implementation",
        input_commitment="sha256:input",
        receipt_artifact_ref="artifact://proofs/receipt.bin",
        receipt_hash="sha256:receipt",
        journal_hash="sha256:journal",
        status=ProofStatus.VERIFIED,
    )
    proven = ReleaseGate().evaluate(
        review=review,
        proof_requirements={calc.calculation_id: ProofRequirement.MUST_PROVE},
        proofs={calc.calculation_id: real_proof},
    )
    assert proven.allowed is True


def test_must_prove_rejects_missing_and_invalid_real_proof() -> None:
    calc = calculation()
    review = DeterministicReviewer().review(
        review_id="REV-1",
        run_id="RUN-1",
        evidence=[
            evidence("E-1", "FY2025", EvidenceStatus.ACCEPTED),
            evidence("E-2", "FY2026", EvidenceStatus.ACCEPTED),
        ],
        calculations=[calc],
    )
    missing = ReleaseGate().evaluate(
        review=review,
        proof_requirements={calc.calculation_id: ProofRequirement.MUST_PROVE},
        proofs={},
    )
    invalid = ReleaseGate().evaluate(
        review=review,
        proof_requirements={calc.calculation_id: ProofRequirement.MUST_PROVE},
        proofs={
            calc.calculation_id: ProofResult(proof_id="PROOF-INVALID", status=ProofStatus.INVALID)
        },
    )

    assert missing.reason_codes == ("PROOF_MISSING:CALC-1",)
    assert invalid.reason_codes == ("PROOF_INVALID:CALC-1",)


def test_must_prove_rejects_unverified_result_and_mismatched_record() -> None:
    calc = calculation()
    review = DeterministicReviewer().review(
        review_id="REV-1",
        run_id="RUN-1",
        evidence=[
            evidence("E-1", "FY2025", EvidenceStatus.ACCEPTED),
            evidence("E-2", "FY2026", EvidenceStatus.ACCEPTED),
        ],
        calculations=[calc],
    )
    unverified = ReleaseGate().evaluate(
        review=review,
        proof_requirements={calc.calculation_id: ProofRequirement.MUST_PROVE},
        proofs={
            calc.calculation_id: ProofResult(
                proof_id="PROOF-RAW",
                status=ProofStatus.VALID,
                receipt_ref="artifact://proofs/raw.receipt",
                verifier_result={"verified": False},
            )
        },
    )
    mismatched = ReleaseGate().evaluate(
        review=review,
        proof_requirements={calc.calculation_id: ProofRequirement.MUST_PROVE},
        proofs={
            calc.calculation_id: ProofRecord(
                proof_id="PROOF-WRONG",
                run_id="OTHER-RUN",
                calculation_id="OTHER-CALC",
                backend="risc0",
                program_id="revenue_growth_v1",
                image_id="IMAGE-1",
                implementation_hash="sha256:implementation",
                input_commitment="sha256:input",
                receipt_artifact_ref="artifact://proofs/receipt.bin",
                receipt_hash="sha256:receipt",
                journal_hash="sha256:journal",
                status=ProofStatus.VALID,
            )
        },
    )

    assert unverified.allowed is False
    assert unverified.reason_codes == ("PROOF_VALID:CALC-1",)
    assert mismatched.allowed is False
    assert mismatched.reason_codes == ("PROOF_IDENTITY_OR_VERIFICATION_INVALID:CALC-1",)


def test_strict_release_gate_binds_every_review_input_snapshot() -> None:
    run_as_of = date(2026, 9, 4)
    record = evidence("E-1", "FY2026", EvidenceStatus.ACCEPTED).model_copy(
        update={
            "normalized_field": "revenue",
            "normalized_value": "100",
            "period_basis": FinancialPeriodBasis.FY,
            "actuality": FinancialActuality.ACTUAL,
            "statement_series": "SERIES-1",
            "statement_cohort": "COHORT-1",
            "currency": "USD",
        }
    )
    calc = CalculationRecord(
        calculation_id="CALC-FCF",
        run_id="RUN-1",
        task_id="TASK-A",
        capability_id="free_cash_flow_margin",
        capability_version="1.0.0-generated",
        formula_id="operating_cash_flow_plus_signed_capex_divided_by_revenue_v1",
        input_evidence_ids=[record.evidence_id],
        output_value="0.5",
        output_unit="ratio",
        status=CalculationStatus.PASS,
        implementation_hash="sha256:implementation",
        code_hash="sha256:implementation",
        source_ref="generated://fcf",
        runtime_version="Python 3.11",
    )
    metric = ReleasedFinancialMetric(
        metric_id="METRIC-FCF",
        calculation_id=calc.calculation_id,
        name="Free Cash Flow Margin",
        canonical_value="0.5",
        canonical_unit=FinancialUnit.RATIO,
        display_value="50.00",
        display_unit="%",
        period="FY2026",
        period_basis=FinancialPeriodBasis.FY,
        actuality=FinancialActuality.ACTUAL,
        as_of=record.as_of,
        currency="USD",
        formula_id=calc.formula_id,
        capability_id=calc.capability_id,
        evidence_ids=(record.evidence_id,),
    )
    claim = MaterialFinancialClaim(
        claim_id="CLAIM-FCF",
        run_id="RUN-1",
        claim_type="MATERIAL_FINANCIAL_METRIC",
        statement="FCF margin was 50.00% for FY2026.",
        metric_id=metric.metric_id,
        value=metric.canonical_value,
        unit=metric.canonical_unit,
        period=metric.period,
        period_basis=metric.period_basis,
        actuality=metric.actuality,
        as_of=metric.as_of,
        currency=metric.currency,
        calculation_refs=(calc.calculation_id,),
        evidence_refs=metric.evidence_ids,
    )
    requirements = {calc.calculation_id: ProofRequirement.NOT_REQUIRED}
    snapshot_hash = financial_review_input_snapshot_hash(
        run_id="RUN-1",
        run_as_of=run_as_of,
        evidence=[record],
        calculations=[calc],
        metrics=[metric],
        claims=[claim],
        judgments=[],
        proof_requirements=requirements,
    )
    review = ReviewRecord(
        review_id="REVIEW-STRICT",
        run_id="RUN-1",
        status=ReviewStatus.PASS,
        reviewed_evidence_refs=[record.evidence_id],
        reviewed_calculation_refs=[calc.calculation_id],
        reviewed_metric_refs=[metric.metric_id],
        reviewed_claim_refs=[claim.claim_id],
        checks=[ReviewCheck(code="FIN_TEST", status=ReviewStatus.PASS)],
        input_snapshot_hash=snapshot_hash,
        reviewer="independent-financial-review-v2",
    )

    def evaluate(calculation: CalculationRecord) -> object:
        return ReleaseGate().evaluate(
            review=review,
            proof_requirements=requirements,
            proofs={},
            calculations={calculation.calculation_id: calculation},
            evidence=[record],
            metrics=[metric],
            claims=[claim],
            judgments=[],
            run_as_of=run_as_of,
            input_commitments={},
            verifications={},
            artifacts={},
        )

    assert evaluate(calc).allowed is True
    tampered = evaluate(calc.model_copy(update={"output_value": "999"}))
    assert tampered.allowed is False
    assert "REVIEW_INPUT_SNAPSHOT_MISMATCH" in tampered.reason_codes
