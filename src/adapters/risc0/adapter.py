from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from src.adapters.risc0.models import (
    FORMULA_ID,
    calculate_revenue_growth,
    load_proof_input,
    write_proof_input,
)
from src.domain.enums import ProofStatus
from src.domain.proof import ProofRequest, ProofResult


class RiscZeroAdapterError(RuntimeError):
    pass


class RiscZeroProofAdapter:
    """RISC Zero boundary that invokes one pinned, pre-built host executable."""

    def __init__(
        self,
        *,
        host_binary: str | Path,
        artifact_dir: str | Path,
        timeout_seconds: float = 900.0,
    ) -> None:
        self._host_binary = Path(host_binary).expanduser().resolve()
        self._artifact_dir = Path(artifact_dir).expanduser().resolve()
        self._timeout_seconds = timeout_seconds

    async def prove(self, request: ProofRequest) -> ProofResult:
        self._assert_secure_runtime()
        try:
            _, proof_input = self._validate_request(request)
            self._artifact_dir.mkdir(parents=True, exist_ok=True)
            safe_proof_id = hashlib.sha256(request.proof_id.encode("utf-8")).hexdigest()
            proof_input_path = self._artifact_dir / f"{safe_proof_id}.input.json"
            receipt_path = self._artifact_dir / f"{safe_proof_id}.receipt"
            write_proof_input(proof_input_path, proof_input)
            proof_input_path.chmod(0o600)
            output = await self._run_host(
                "prove",
                "--input",
                str(proof_input_path),
                "--receipt",
                str(receipt_path),
            )
            self._validate_host_output(
                output,
                status="GENERATED",
                proof_input=proof_input,
                receipt_path=receipt_path,
            )
            receipt_path.chmod(0o600)
        except RiscZeroAdapterError as error:
            return ProofResult(
                proof_id=request.proof_id,
                status=ProofStatus.ERROR,
                detail=str(error),
            )

        return ProofResult(
            proof_id=request.proof_id,
            status=ProofStatus.VALID,
            receipt_ref=str(receipt_path),
            verifier_result={
                **output,
                "proof_input_ref": str(proof_input_path),
                "verified": False,
            },
            detail="Real RISC Zero receipt generated; independent verification is required.",
        )

    async def verify(self, result: ProofResult) -> bool:
        self._assert_secure_runtime()
        if result.status not in {ProofStatus.VALID, ProofStatus.VERIFIED}:
            return False
        if result.receipt_ref is None:
            return False
        proof_input_ref = result.verifier_result.get("proof_input_ref")
        if not isinstance(proof_input_ref, str):
            return False
        try:
            proof_input_path, receipt_path = self._resolve_result_paths(
                proof_input_ref, result.receipt_ref
            )
            proof_input = load_proof_input(proof_input_path)
            output = await self._run_host(
                "verify",
                "--input",
                str(proof_input_path),
                "--receipt",
                str(receipt_path),
            )
            self._validate_host_output(
                output,
                status="VERIFIED",
                proof_input=proof_input,
                receipt_path=receipt_path,
            )
            original_hash = result.verifier_result.get("receipt_hash")
            verified = (
                original_hash == output["receipt_hash"] and output.get("dev_mode") is False
            )
            if verified:
                proving_duration_ms = result.verifier_result.get("proving_duration_ms")
                result.status = ProofStatus.VERIFIED
                result.verifier_result = {
                    **output,
                    "proof_input_ref": str(proof_input_path),
                    "proving_duration_ms": proving_duration_ms,
                    "verified": True,
                }
                result.detail = "Receipt independently verified against the compiled image."
            return verified
        except (OSError, ValueError, RiscZeroAdapterError):
            return False

    @staticmethod
    def _resolve_result_paths(proof_input_ref: str, receipt_ref: str) -> tuple[Path, Path]:
        return (
            Path(proof_input_ref).expanduser().resolve(),
            Path(receipt_ref).expanduser().resolve(),
        )

    def _assert_secure_runtime(self) -> None:
        if "RISC0_DEV_MODE" in os.environ:
            raise RiscZeroAdapterError("RISC0_DEV_MODE is forbidden for formal proof operations")
        if not self._host_binary.is_file() or not os.access(self._host_binary, os.X_OK):
            raise RiscZeroAdapterError(
                f"RISC Zero host binary is not executable: {self._host_binary}"
            )

    def _validate_request(self, request: ProofRequest) -> tuple[Path, Any]:
        if request.program_id != FORMULA_ID:
            raise RiscZeroAdapterError(f"unsupported proof program: {request.program_id}")
        if request.proof_input_ref is None:
            raise RiscZeroAdapterError("proof_input_ref is required")
        path = Path(request.proof_input_ref).expanduser().resolve()
        try:
            proof_input = load_proof_input(path)
        except (OSError, ValueError) as error:
            raise RiscZeroAdapterError(f"invalid proof input: {error}") from error
        if proof_input.run_id != request.run_id:
            raise RiscZeroAdapterError("run id does not match proof input")
        if proof_input.calculation_id != request.calculation_id:
            raise RiscZeroAdapterError("calculation id does not match proof input")
        if request.input_commitments != [proof_input.input_commitment]:
            raise RiscZeroAdapterError("request input commitment does not match proof input")
        return path, proof_input

    async def _run_host(self, *arguments: str) -> dict[str, Any]:
        child_env = os.environ.copy()
        child_env.pop("RISC0_DEV_MODE", None)
        try:
            process = await asyncio.create_subprocess_exec(
                str(self._host_binary),
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=child_env,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
        except TimeoutError as error:
            process.kill()
            await process.communicate()
            raise RiscZeroAdapterError("RISC Zero host timed out") from error
        except OSError as error:
            raise RiscZeroAdapterError(f"failed to execute RISC Zero host: {error}") from error
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise RiscZeroAdapterError(f"RISC Zero host rejected operation: {detail[:500]}")
        try:
            decoded = json.loads(stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RiscZeroAdapterError("RISC Zero host returned invalid JSON") from error
        if not isinstance(decoded, dict):
            raise RiscZeroAdapterError("RISC Zero host response must be an object")
        return decoded

    @staticmethod
    def _validate_host_output(
        output: dict[str, Any], *, status: str, proof_input: Any, receipt_path: Path
    ) -> None:
        if output.get("status") != status:
            raise RiscZeroAdapterError("unexpected host proof status")
        if output.get("backend") != "risc0" or output.get("program_id") != FORMULA_ID:
            raise RiscZeroAdapterError("host program identity mismatch")
        if output.get("dev_mode") is not False:
            raise RiscZeroAdapterError("host did not attest dev mode is disabled")
        if output.get("input_commitment") != proof_input.input_commitment:
            raise RiscZeroAdapterError("host input commitment mismatch")
        if output.get("expected_output_commitment") != proof_input.expected_output_commitment:
            raise RiscZeroAdapterError("host output commitment mismatch")
        expected_result = calculate_revenue_growth(proof_input.canonical_inputs).model_dump(
            mode="json"
        )
        if output.get("canonical_result") != expected_result:
            raise RiscZeroAdapterError("host canonical result mismatch")
        if output.get("receipt_path") != str(receipt_path):
            raise RiscZeroAdapterError("host receipt path mismatch")
        if not isinstance(output.get("image_id"), str) or not output["image_id"]:
            raise RiscZeroAdapterError("host image id is missing")
        if not receipt_path.is_file():
            raise RiscZeroAdapterError("host did not create a receipt")
        actual_receipt_hash = f"sha256:{hashlib.sha256(receipt_path.read_bytes()).hexdigest()}"
        if output.get("receipt_hash") != actual_receipt_hash:
            raise RiscZeroAdapterError("receipt artifact hash mismatch")
