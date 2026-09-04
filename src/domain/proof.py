from typing import Protocol, runtime_checkable

from pydantic import Field

from src.domain.base import JsonObject, TimestampedModel
from src.domain.enums import ProofRequirement, ProofStatus


class ProofPolicyDecision(TimestampedModel):
    decision_id: str
    run_id: str
    calculation_id: str
    formula_id: str
    requirement: ProofRequirement
    policy_id: str
    reason: str


class ProofInputCommitment(TimestampedModel):
    commitment_id: str
    run_id: str
    calculation_id: str
    formula_id: str
    capability_id: str
    implementation_hash: str
    input_evidence_refs: list[str] = Field(default_factory=list)
    canonical_inputs: JsonObject
    input_commitment: str
    expected_output_commitment: str


class ProofArtifactReference(TimestampedModel):
    artifact_id: str
    proof_id: str
    artifact_type: str
    artifact_ref: str
    content_hash: str
    size_bytes: int = Field(ge=0)


class ProofRecord(TimestampedModel):
    proof_id: str
    run_id: str
    calculation_id: str
    backend: str
    program_id: str
    image_id: str
    implementation_hash: str
    input_commitment: str
    receipt_artifact_ref: str | None = None
    receipt_hash: str | None = None
    journal_hash: str | None = None
    status: ProofStatus = ProofStatus.REQUIRED_PENDING
    proving_duration_ms: int | None = Field(default=None, ge=0)


class ProofVerificationRecord(TimestampedModel):
    verification_id: str
    proof_id: str
    verifier: str
    image_id: str
    receipt_hash: str
    journal_hash: str
    status: ProofStatus
    verified: bool
    detail: str | None = None


class ProofRequest(TimestampedModel):
    proof_id: str
    run_id: str
    calculation_id: str
    program_id: str
    input_commitments: list[str] = Field(default_factory=list)
    proof_input_ref: str | None = None


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
