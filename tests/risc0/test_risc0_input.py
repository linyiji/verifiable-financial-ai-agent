from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.adapters.risc0 import (
    CanonicalRevenueInputs,
    RiscZeroAdapterError,
    RiscZeroProofAdapter,
    build_proof_input,
    calculate_revenue_growth,
    load_proof_input,
)
from src.domain.proof import ProofAdapter, ProofRequest

FIXTURE = Path(__file__).parents[1] / "fixtures" / "risc0_revenue_growth_input.json"


def test_fixture_binds_complete_proof_context() -> None:
    proof_input = load_proof_input(FIXTURE)
    assert proof_input.run_id == "RUN-RISC0-NVDA-001"
    assert proof_input.calculation_id == "CALC-REVENUE-GROWTH-001"
    assert proof_input.formula_id == "revenue_growth_v1"
    assert proof_input.capability_id == "revenue_growth"
    assert proof_input.implementation_hash.startswith("sha256:")
    assert len(proof_input.input_evidence_refs) == 2
    assert proof_input.input_commitment.startswith("sha256:")
    assert proof_input.expected_output_commitment.startswith("sha256:")


def test_revenue_growth_uses_exact_reduced_rational_arithmetic() -> None:
    result = calculate_revenue_growth(
        CanonicalRevenueInputs(
            prior_revenue_minor=60_922,
            current_revenue_minor=130_497,
            currency="USD",
            scale=0,
        )
    )
    assert result.growth_numerator == 69_575
    assert result.growth_denominator == 60_922


def test_tampered_revenue_invalidates_commitment() -> None:
    original = load_proof_input(FIXTURE)
    tampered = original.model_dump(mode="json")
    tampered["canonical_inputs"]["current_revenue_minor"] += 1
    with pytest.raises(ValidationError, match="commitment mismatch"):
        original.__class__.model_validate(tampered)


def test_build_proof_input_is_deterministic() -> None:
    first = load_proof_input(FIXTURE)
    rebuilt = build_proof_input(
        run_id=first.run_id,
        calculation_id=first.calculation_id,
        implementation_hash=first.implementation_hash,
        input_evidence_refs=first.input_evidence_refs,
        canonical_inputs=first.canonical_inputs,
    )
    assert rebuilt == first


@pytest.mark.asyncio
async def test_adapter_rejects_dev_mode_even_before_host_invocation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RISC0_DEV_MODE", "1")
    adapter = RiscZeroProofAdapter(host_binary=sys.executable, artifact_dir=tmp_path)
    with pytest.raises(RiscZeroAdapterError, match="forbidden"):
        await adapter.prove(
            ProofRequest(
                proof_id="PROOF-DEV",
                run_id="RUN-RISC0-NVDA-001",
                calculation_id="CALC-REVENUE-GROWTH-001",
                program_id="revenue_growth_v1",
                input_commitments=["sha256:unused"],
                proof_input_ref=str(FIXTURE),
            )
        )


def test_adapter_satisfies_frozen_proof_protocol(tmp_path: Path) -> None:
    adapter = RiscZeroProofAdapter(host_binary=sys.executable, artifact_dir=tmp_path)
    assert isinstance(adapter, ProofAdapter)
