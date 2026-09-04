from __future__ import annotations

import hashlib
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
    write_proof_input,
)
from src.adapters.risc0.release_manifest import (
    REVENUE_GROWTH_RELEASE_PROGRAM,
    load_and_verify_release_manifest,
)
from src.domain.enums import ProofStatus
from src.domain.financial_validation import REVENUE_GROWTH_VALIDATION_REASON
from src.domain.proof import ProofAdapter, ProofRequest

FIXTURE = Path(__file__).parents[1] / "fixtures" / "risc0_revenue_growth_input.json"
ROOT = Path(__file__).parents[2]
PYTHON_HOST = Path(sys.executable).resolve()
PYTHON_HOST_DIGEST = f"sha256:{hashlib.sha256(PYTHON_HOST.read_bytes()).hexdigest()}"


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


def test_release_manifest_binds_reviewed_formula_and_precondition() -> None:
    manifest = load_and_verify_release_manifest(ROOT)
    assert manifest["program"] == REVENUE_GROWTH_RELEASE_PROGRAM


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


@pytest.mark.parametrize("prior", [0, -60_922])
def test_revenue_growth_rejects_nonpositive_prior_with_stable_reason(prior: int) -> None:
    with pytest.raises(ValidationError, match=REVENUE_GROWTH_VALIDATION_REASON):
        CanonicalRevenueInputs(
            prior_revenue_minor=prior,
            current_revenue_minor=130_497,
            currency="USD",
            scale=0,
        )

    bypassed = CanonicalRevenueInputs.model_construct(
        prior_revenue_minor=prior,
        current_revenue_minor=130_497,
        currency="USD",
        scale=0,
    )
    with pytest.raises(ValueError, match=REVENUE_GROWTH_VALIDATION_REASON):
        calculate_revenue_growth(bypassed)


@pytest.mark.parametrize("field", ["prior_revenue_minor", "current_revenue_minor"])
def test_tampered_revenue_invalidates_commitment(field: str) -> None:
    original = load_proof_input(FIXTURE)
    tampered = original.model_dump(mode="json")
    tampered["canonical_inputs"][field] += 1
    with pytest.raises(ValidationError, match="commitment mismatch"):
        original.__class__.model_validate(tampered)


def test_tampered_expected_result_invalidates_commitment() -> None:
    original = load_proof_input(FIXTURE)
    tampered = original.model_dump(mode="json")
    tampered["expected_output_commitment"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="expected output commitment mismatch"):
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
    adapter = RiscZeroProofAdapter(host_binary=PYTHON_HOST, artifact_dir=tmp_path)
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
    adapter = RiscZeroProofAdapter(host_binary=PYTHON_HOST, artifact_dir=tmp_path)
    assert isinstance(adapter, ProofAdapter)


@pytest.mark.asyncio
async def test_adapter_rejects_unpinned_host_binary(tmp_path: Path) -> None:
    adapter = RiscZeroProofAdapter(host_binary=PYTHON_HOST, artifact_dir=tmp_path)
    proof_input = load_proof_input(FIXTURE)

    with pytest.raises(RiscZeroAdapterError, match="digest does not match release pin"):
        await adapter.prove(
            ProofRequest(
                proof_id="PROOF-UNPINNED",
                run_id=proof_input.run_id,
                calculation_id=proof_input.calculation_id,
                program_id=proof_input.formula_id,
                input_commitments=[proof_input.input_commitment],
                proof_input_ref=str(FIXTURE),
            )
        )


@pytest.mark.asyncio
async def test_adapter_rejects_input_outside_controlled_root(tmp_path: Path) -> None:
    adapter = RiscZeroProofAdapter(
        host_binary=PYTHON_HOST,
        artifact_dir=tmp_path,
        expected_host_sha256=PYTHON_HOST_DIGEST,
    )
    proof_input = load_proof_input(FIXTURE)

    result = await adapter.prove(
        ProofRequest(
            proof_id="PROOF-ESCAPE",
            run_id=proof_input.run_id,
            calculation_id=proof_input.calculation_id,
            program_id=proof_input.formula_id,
            input_commitments=[proof_input.input_commitment],
            proof_input_ref=str(FIXTURE),
        )
    )

    assert result.status is ProofStatus.ERROR
    assert "escapes the controlled artifact root" in (result.detail or "")


def test_proof_input_write_is_exclusive(tmp_path: Path) -> None:
    target = tmp_path / "input.json"
    proof_input = load_proof_input(FIXTURE)
    write_proof_input(target, proof_input)

    with pytest.raises(FileExistsError):
        write_proof_input(target, proof_input)

    assert load_proof_input(target) == proof_input


def test_adapter_rejects_filesystem_root_as_artifact_directory() -> None:
    with pytest.raises(ValueError, match="filesystem root"):
        RiscZeroProofAdapter(host_binary=Path(sys.executable).resolve(), artifact_dir=Path("/"))
