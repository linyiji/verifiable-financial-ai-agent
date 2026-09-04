from __future__ import annotations

from datetime import date

import pytest

from src.application.errors import ApplicationError
from src.application.extensions import ProofWorkflowOutcome
from src.application.service import ResearchApplicationService
from src.domain.enums import ProofRequirement, ProofStatus, RunStatus
from src.domain.proof import ProofRecord


class RevenueGrowthProofWorkflow:
    def __init__(self, *, provide_valid_proof: bool) -> None:
        self.provide_valid_proof = provide_valid_proof

    async def execute(self, *, run_id, calculations):
        growth = next(item for item in calculations if item.formula_id == "revenue_growth_v1")
        requirements = {
            item.calculation_id: (
                ProofRequirement.MUST_PROVE
                if item.calculation_id == growth.calculation_id
                else ProofRequirement.NOT_REQUIRED
            )
            for item in calculations
        }
        proofs = {}
        if self.provide_valid_proof:
            proofs[growth.calculation_id] = ProofRecord(
                proof_id=f"PROOF-{run_id}-REVENUE-GROWTH",
                run_id=run_id,
                calculation_id=growth.calculation_id,
                backend="risc0",
                program_id="risc0-revenue-growth-v1",
                image_id="sha256:image",
                implementation_hash=growth.implementation_hash or "sha256:implementation",
                input_commitment="sha256:input",
                receipt_artifact_ref="artifact://proofs/receipt.bin",
                receipt_hash="sha256:receipt",
                journal_hash="sha256:journal",
                status=ProofStatus.VERIFIED,
                proving_duration_ms=1,
            )
        return ProofWorkflowOutcome(
            requirements=requirements,
            proofs=proofs,
            runtime_state={
                "status": (
                    ProofStatus.VERIFIED.value if proofs else ProofStatus.REQUIRED_PENDING.value
                )
            },
        )


async def _prepared_service(workflow: RevenueGrowthProofWorkflow):
    service = ResearchApplicationService(proof_workflow=workflow)
    research_object = await service.create_object(
        symbol="NVDA",
        company_name="NVIDIA",
        exchange="NASDAQ",
    )
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Verify proof workflow release semantics",
        as_of=date(2026, 9, 4),
        preferences={},
    )
    aggregate = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    return service, aggregate


@pytest.mark.asyncio
async def test_valid_required_proof_is_referenced_by_canonical_record() -> None:
    service, aggregate = await _prepared_service(
        RevenueGrowthProofWorkflow(provide_valid_proof=True)
    )

    completed = await service.execute_run(aggregate.run.run_id)

    assert completed.run.status is RunStatus.RELEASED
    assert completed.artifacts.canonical_record is not None
    assert completed.artifacts.canonical_record.proof_refs == [
        f"PROOF-{aggregate.run.run_id}-REVENUE-GROWTH"
    ]
    assert completed.runtime.proof_state["status"] == ProofStatus.VERIFIED.value


@pytest.mark.asyncio
async def test_missing_required_proof_blocks_release() -> None:
    service, aggregate = await _prepared_service(
        RevenueGrowthProofWorkflow(provide_valid_proof=False)
    )

    with pytest.raises(ApplicationError, match="assurance requirements"):
        await service.execute_run(aggregate.run.run_id)

    assert aggregate.run.status is not RunStatus.RELEASED
    assert aggregate.artifacts.canonical_record is None
