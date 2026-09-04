from dataclasses import dataclass

from src.assurance.proof_policy import ProofRequirement
from src.domain.enums import ProofStatus, ReviewStatus
from src.domain.proof import ProofRecord, ProofResult
from src.domain.review import ReviewRecord


@dataclass(frozen=True, slots=True)
class ReleaseDecision:
    allowed: bool
    reason_codes: tuple[str, ...]


class ReleaseGate:
    def evaluate(
        self,
        *,
        review: ReviewRecord,
        proof_requirements: dict[str, ProofRequirement],
        proofs: dict[str, ProofRecord | ProofResult],
    ) -> ReleaseDecision:
        reasons: list[str] = []
        if review.status is not ReviewStatus.PASS:
            reasons.append(f"REVIEW_{review.status.value}")

        for calculation_id, requirement in proof_requirements.items():
            if requirement is not ProofRequirement.MUST_PROVE:
                continue
            proof = proofs.get(calculation_id)
            if proof is None:
                reasons.append(f"PROOF_MISSING:{calculation_id}")
            elif isinstance(proof, ProofRecord) and (
                proof.status is not ProofStatus.VERIFIED
                or proof.run_id != review.run_id
                or proof.calculation_id != calculation_id
                or not proof.image_id
                or not proof.implementation_hash
                or not proof.input_commitment
                or not proof.receipt_artifact_ref
                or not proof.receipt_hash
                or not proof.journal_hash
            ):
                reasons.append(f"PROOF_IDENTITY_OR_VERIFICATION_INVALID:{calculation_id}")
            elif isinstance(proof, ProofResult) and (
                proof.status is not ProofStatus.VERIFIED
                or not proof.receipt_ref
                or proof.verifier_result.get("verified") is not True
            ):
                reasons.append(f"PROOF_{proof.status.value}:{calculation_id}")

        return ReleaseDecision(allowed=not reasons, reason_codes=tuple(reasons))
