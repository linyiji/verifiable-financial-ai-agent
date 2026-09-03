from typing import Protocol, runtime_checkable

from pydantic import Field

from src.domain.base import JsonObject, TimestampedModel
from src.domain.enums import ProofStatus


class ProofRequest(TimestampedModel):
    proof_id: str
    run_id: str
    calculation_id: str
    program_id: str
    input_commitments: list[str] = Field(default_factory=list)


class ProofResult(TimestampedModel):
    proof_id: str
    status: ProofStatus
    receipt_ref: str | None = None
    verifier_result: JsonObject = Field(default_factory=dict)
    detail: str | None = None


@runtime_checkable
class ProofAdapter(Protocol):
    async def prove(self, request: ProofRequest) -> ProofResult: ...

    async def verify(self, result: ProofResult) -> bool: ...

