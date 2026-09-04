from src.domain.enums import ProofStatus
from src.domain.proof import ProofRequest, ProofResult


class PendingProofAdapter:
    async def prove(self, request: ProofRequest) -> ProofResult:
        return ProofResult(
            proof_id=request.proof_id,
            status=ProofStatus.NOT_IMPLEMENTED,
            detail="RISC Zero integration is intentionally NOT_IMPLEMENTED in Phase 1",
        )

    async def verify(self, result: ProofResult) -> bool:
        return result.status is ProofStatus.VERIFIED
