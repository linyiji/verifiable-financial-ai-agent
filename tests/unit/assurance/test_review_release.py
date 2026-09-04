from datetime import UTC, date, datetime

from src.assurance.deterministic_review import DeterministicReviewer
from src.assurance.proof_policy import ProofPolicy, ProofRequirement
from src.assurance.release_gate import ReleaseGate
from src.domain.calculation import CalculationRecord
from src.domain.enums import (
    CalculationStatus,
    EvidenceStatus,
    ProofStatus,
    ReviewStatus,
)
from src.domain.evidence import EvidenceRecord
from src.domain.proof import ProofRecord, ProofResult


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
            calc.calculation_id: ProofResult(
                proof_id="PROOF-1", status=ProofStatus.NOT_IMPLEMENTED
            )
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
        status=ProofStatus.VALID,
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
            calc.calculation_id: ProofResult(
                proof_id="PROOF-INVALID", status=ProofStatus.INVALID
            )
        },
    )

    assert missing.reason_codes == ("PROOF_MISSING:CALC-1",)
    assert invalid.reason_codes == ("PROOF_INVALID:CALC-1",)
