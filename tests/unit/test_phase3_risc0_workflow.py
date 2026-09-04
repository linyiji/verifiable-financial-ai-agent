from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.phase3_proof import RevenueGrowthRiscZeroProofWorkflow
from src.domain.calculation import CalculationRecord
from src.domain.enums import CalculationStatus, ProofRequirement, ProofStatus
from src.domain.proof import (
    ProofArtifactReference,
    ProofInputCommitment,
    ProofPolicyDecision,
    ProofRecord,
    ProofResult,
    ProofVerificationRecord,
)
from src.runtime.events import InMemoryRuntimeEventStore


class RecordingRepository:
    def __init__(self) -> None:
        self.records: list[object] = []

    async def save(self, entity, *, run_id=None):
        del run_id
        self.records.append(entity)
        return entity


class FakeRiscZeroAdapter:
    def __init__(self, receipt: Path, *, valid: bool = True) -> None:
        self.receipt = receipt
        self.valid = valid
        self.requests = []

    async def prove(self, request):
        self.requests.append(request)
        if not self.valid:
            return ProofResult(
                proof_id=request.proof_id,
                status=ProofStatus.ERROR,
                detail="controlled failure",
            )
        self.receipt.parent.mkdir(parents=True, exist_ok=True)
        self.receipt.write_bytes(b"real-receipt-placeholder")
        digest = f"sha256:{hashlib.sha256(self.receipt.read_bytes()).hexdigest()}"
        return ProofResult(
            proof_id=request.proof_id,
            status=ProofStatus.VALID,
            receipt_ref=str(self.receipt),
            verifier_result={
                "receipt_hash": digest,
                "proof_input_ref": request.proof_input_ref,
                "proving_duration_ms": 12,
            },
        )

    async def verify(self, result):
        result.status = ProofStatus.VERIFIED
        result.verifier_result = {
            **result.verifier_result,
            "image_id": "image-1",
            "journal_hash": "sha256:journal",
            "dev_mode": False,
            "verified": True,
        }
        return True


def _growth() -> CalculationRecord:
    return CalculationRecord(
        calculation_id="CALC-GROWTH",
        run_id="RUN-1",
        task_id="TASK-1",
        capability_id="revenue_growth",
        capability_version="1.0.0",
        formula_id="revenue_growth_v1",
        input_evidence_ids=["E-PRIOR", "E-CURRENT"],
        input_values_snapshot={
            "prior_revenue": "60922",
            "current_revenue": "130497",
            "currency": "USD",
        },
        output_value=Decimal(69575) / Decimal(60922),
        output_unit="ratio",
        status=CalculationStatus.PASS,
        code_hash="sha256:implementation",
        source_ref="src.capabilities.financial.growth:RevenueGrowthCapability",
        runtime_version="Python 3.11.test",
    )


@pytest.mark.asyncio
async def test_workflow_maps_verified_receipt_to_durable_records(tmp_path: Path) -> None:
    events = InMemoryRuntimeEventStore()
    repository = RecordingRepository()
    adapter = FakeRiscZeroAdapter(tmp_path / "receipts" / "proof.receipt")
    workflow = RevenueGrowthRiscZeroProofWorkflow(
        adapter=adapter,  # type: ignore[arg-type]
        artifact_dir=tmp_path,
        event_store=events,
        repository=repository,
    )

    outcome = await workflow.execute(run_id="RUN-1", calculations=[_growth()])

    assert outcome.requirements == {"CALC-GROWTH": ProofRequirement.MUST_PROVE}
    proof = outcome.proofs["CALC-GROWTH"]
    assert isinstance(proof, ProofRecord)
    assert proof.status is ProofStatus.VALID
    assert proof.receipt_hash and proof.journal_hash
    assert outcome.runtime_state["dev_mode"] is False
    assert len(adapter.requests) == 1
    assert adapter.requests[0].input_commitments[0] == proof.input_commitment
    record_types = {type(record) for record in repository.records}
    assert record_types == {
        ProofPolicyDecision,
        ProofInputCommitment,
        ProofRecord,
        ProofVerificationRecord,
        ProofArtifactReference,
    }
    event_types = [event.type.value for event in await events.replay("RUN-1")]
    assert event_types == [
        "proof.required",
        "proof.started",
        "proof.generated",
        "proof.verified",
    ]


@pytest.mark.asyncio
async def test_workflow_returns_missing_proof_on_prover_error(tmp_path: Path) -> None:
    events = InMemoryRuntimeEventStore()
    workflow = RevenueGrowthRiscZeroProofWorkflow(
        adapter=FakeRiscZeroAdapter(  # type: ignore[arg-type]
            tmp_path / "receipts" / "proof.receipt",
            valid=False,
        ),
        artifact_dir=tmp_path,
        event_store=events,
    )

    outcome = await workflow.execute(run_id="RUN-1", calculations=[_growth()])

    assert outcome.proofs == {}
    assert outcome.runtime_state["status"] == ProofStatus.ERROR.value
    assert (await events.replay("RUN-1"))[-1].type.value == "proof.failed"
