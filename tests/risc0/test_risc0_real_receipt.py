from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.adapters.risc0 import (
    CanonicalRevenueGrowthResult,
    CanonicalRevenueInputs,
    RiscZeroProofAdapter,
    build_proof_input,
    load_proof_input,
    write_proof_input,
)
from src.adapters.risc0.models import input_commitment, output_commitment
from src.domain.enums import ProofStatus
from src.domain.financial_validation import REVENUE_GROWTH_VALIDATION_REASON
from src.domain.proof import ProofRequest, ProofResult

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "risc0_revenue_growth_input.json"
DEFAULT_HOST = ROOT / "zk" / "revenue_growth" / "target" / "release" / ("revenue-growth-proof-host")


@dataclass(frozen=True)
class RealProof:
    adapter: RiscZeroProofAdapter
    result: ProofResult
    input_path: Path
    receipt_path: Path
    host_binary: Path


@pytest.fixture(scope="module")
def real_proof(tmp_path_factory: pytest.TempPathFactory) -> RealProof:
    if "RISC0_DEV_MODE" in os.environ:
        pytest.fail("RISC0_DEV_MODE must be absent for real proof tests")
    host_binary = Path(os.environ.get("RISC0_PROOF_HOST_BINARY", DEFAULT_HOST))
    if not host_binary.is_file():
        pytest.skip(f"pre-built RISC Zero host is unavailable: {host_binary}")
    temp_dir = tmp_path_factory.mktemp("risc0-real")
    input_path = temp_dir / "proof-input.json"
    input_path.write_bytes(FIXTURE.read_bytes())
    proof_input = load_proof_input(input_path)
    adapter = RiscZeroProofAdapter(
        host_binary=host_binary,
        artifact_dir=temp_dir,
        timeout_seconds=1_800,
    )
    result = asyncio.run(
        adapter.prove(
            ProofRequest(
                proof_id="PROOF-RISC0-REAL-001",
                run_id=proof_input.run_id,
                calculation_id=proof_input.calculation_id,
                program_id=proof_input.formula_id,
                input_commitments=[proof_input.input_commitment],
                proof_input_ref=str(input_path),
            )
        )
    )
    assert result.status is ProofStatus.VALID, result.detail
    assert result.receipt_ref is not None
    return RealProof(
        adapter=adapter,
        result=result,
        input_path=input_path,
        receipt_path=Path(result.receipt_ref),
        host_binary=host_binary,
    )


def test_real_receipt_passes_independent_verification(real_proof: RealProof) -> None:
    assert asyncio.run(real_proof.adapter.verify(real_proof.result)) is True
    assert real_proof.result.status is ProofStatus.VERIFIED
    assert real_proof.result.verifier_result["verified"] is True
    assert real_proof.receipt_path.stat().st_size > 1_000
    assert real_proof.receipt_path.stat().st_mode & 0o777 == 0o600
    assert real_proof.result.verifier_result["proving_duration_ms"] > 0
    assert real_proof.result.verifier_result["dev_mode"] is False
    assert real_proof.result.verifier_result["image_id"]


def test_tampered_revenue_is_rejected(real_proof: RealProof) -> None:
    original = load_proof_input(real_proof.input_path)
    tampered_path = real_proof.input_path.parent / "tampered-revenue.json"
    tampered = build_proof_input(
        run_id=original.run_id,
        calculation_id=original.calculation_id,
        implementation_hash=original.implementation_hash,
        input_evidence_refs=original.input_evidence_refs,
        canonical_inputs=CanonicalRevenueInputs(
            prior_revenue_minor=original.canonical_inputs.prior_revenue_minor,
            current_revenue_minor=original.canonical_inputs.current_revenue_minor + 1,
            currency=original.canonical_inputs.currency,
            scale=original.canonical_inputs.scale,
        ),
    )
    write_proof_input(tampered_path, tampered)
    forged_context = real_proof.result.model_copy(
        update={
            "verifier_result": {
                **real_proof.result.verifier_result,
                "proof_input_ref": str(tampered_path),
            }
        }
    )
    assert asyncio.run(real_proof.adapter.verify(forged_context)) is False


def test_tampered_prior_revenue_is_rejected(real_proof: RealProof) -> None:
    original = load_proof_input(real_proof.input_path)
    tampered_path = real_proof.input_path.parent / "tampered-prior-revenue.json"
    tampered = build_proof_input(
        run_id=original.run_id,
        calculation_id=original.calculation_id,
        implementation_hash=original.implementation_hash,
        input_evidence_refs=original.input_evidence_refs,
        canonical_inputs=CanonicalRevenueInputs(
            prior_revenue_minor=original.canonical_inputs.prior_revenue_minor + 1,
            current_revenue_minor=original.canonical_inputs.current_revenue_minor,
            currency=original.canonical_inputs.currency,
            scale=original.canonical_inputs.scale,
        ),
    )
    write_proof_input(tampered_path, tampered)
    forged_context = real_proof.result.model_copy(
        update={
            "verifier_result": {
                **real_proof.result.verifier_result,
                "proof_input_ref": str(tampered_path),
            }
        }
    )
    assert asyncio.run(real_proof.adapter.verify(forged_context)) is False


@pytest.mark.parametrize("prior", [0, -1])
def test_real_host_rejects_nonpositive_prior_with_stable_reason(
    real_proof: RealProof, prior: int
) -> None:
    payload = json.loads(real_proof.input_path.read_text(encoding="utf-8"))
    payload["canonical_inputs"]["prior_revenue_minor"] = prior
    invalid_path = real_proof.input_path.parent / f"nonpositive-{prior}.json"
    invalid_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    receipt_path = real_proof.input_path.parent / f"nonpositive-{prior}.receipt"

    completed = subprocess.run(
        [
            str(real_proof.host_binary),
            "prove",
            "--input",
            str(invalid_path),
            "--receipt",
            str(receipt_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert REVENUE_GROWTH_VALIDATION_REASON in completed.stderr
    assert not receipt_path.exists()


def test_tampered_expected_result_is_rejected(real_proof: RealProof) -> None:
    original = load_proof_input(real_proof.input_path)
    fake_result = CanonicalRevenueGrowthResult(
        growth_numerator=1,
        growth_denominator=2,
        unit="ratio",
    )
    tampered = original.model_copy(
        update={"expected_output_commitment": output_commitment(original.formula_id, fake_result)}
    )
    tampered = tampered.model_copy(update={"input_commitment": input_commitment(tampered)})
    tampered_path = real_proof.input_path.parent / "tampered-result.json"
    tampered_path.write_text(
        json.dumps(tampered.model_dump(mode="json"), sort_keys=True), encoding="utf-8"
    )
    forged_context = real_proof.result.model_copy(
        update={
            "verifier_result": {
                **real_proof.result.verifier_result,
                "proof_input_ref": str(tampered_path),
            }
        }
    )
    assert asyncio.run(real_proof.adapter.verify(forged_context)) is False


def test_wrong_program_image_is_rejected(real_proof: RealProof) -> None:
    completed = subprocess.run(
        [
            str(real_proof.host_binary),
            "verify",
            "--input",
            str(real_proof.input_path),
            "--receipt",
            str(real_proof.receipt_path),
            "--expected-image-id",
            "0" * 64,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "cryptographic verification" in completed.stderr.lower()


def test_corrupted_receipt_is_rejected(real_proof: RealProof) -> None:
    corrupted_path = real_proof.input_path.parent / "corrupted.receipt"
    encoded = bytearray(real_proof.receipt_path.read_bytes())
    encoded[len(encoded) // 2] ^= 0x01
    corrupted_path.write_bytes(encoded)
    corrupted = real_proof.result.model_copy(update={"receipt_ref": str(corrupted_path)})
    assert asyncio.run(real_proof.adapter.verify(corrupted)) is False
