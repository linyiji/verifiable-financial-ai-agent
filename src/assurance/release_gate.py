from dataclasses import dataclass

from src.assurance.proof_policy import ProofRequirement
from src.domain.enums import ProofStatus, ReviewStatus
from src.domain.proof import ProofResult
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
        proofs: dict[str, ProofResult],
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
            elif proof.status is not ProofStatus.VERIFIED:
                reasons.append(f"PROOF_{proof.status.value}:{calculation_id}")

        return ReleaseDecision(allowed=not reasons, reason_codes=tuple(reasons))

