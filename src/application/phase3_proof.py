from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

from src.adapters.risc0 import (
    CanonicalRevenueInputs,
    RiscZeroProofAdapter,
    build_proof_input,
    calculate_revenue_growth,
    write_proof_input,
)
from src.adapters.risc0.models import FORMULA_ID
from src.application.extensions import ProofWorkflowOutcome
from src.domain.calculation import CalculationRecord
from src.domain.enums import ProofRequirement, ProofStatus
from src.domain.proof import (
    ProofArtifactReference,
    ProofInputCommitment,
    ProofPolicyDecision,
    ProofRecord,
    ProofRequest,
    ProofVerificationRecord,
)
from src.domain.runtime_event import RuntimeEventType
from src.observability.instrumentation import RuntimeInstrumentation
from src.runtime.events import RuntimeEventStore


class Phase3RecordRepositoryPort(Protocol):
    async def save(self, entity: Any, *, run_id: str | None = None) -> Any: ...


class RevenueGrowthRiscZeroProofWorkflow:
    """Require, prove, independently verify, and persist revenue-growth lineage."""

    policy_id = "phase3-revenue-growth-must-prove-v1"

    def __init__(
        self,
        *,
        adapter: RiscZeroProofAdapter,
        artifact_dir: str | Path,
        event_store: RuntimeEventStore,
        repository: Phase3RecordRepositoryPort | None = None,
        instrumentation: RuntimeInstrumentation | None = None,
    ) -> None:
        self._adapter = adapter
        requested_artifacts = Path(artifact_dir).expanduser()
        if requested_artifacts == Path(requested_artifacts.anchor):
            raise ValueError("filesystem root cannot be used as proof artifact root")
        if requested_artifacts.is_symlink():
            raise ValueError("proof artifact root must not be a symlink")
        requested_artifacts.mkdir(parents=True, exist_ok=True)
        self._artifact_dir = requested_artifacts.resolve(strict=True)
        if self._artifact_dir == Path(self._artifact_dir.anchor):
            raise ValueError("filesystem root cannot be used as proof artifact root")
        self._event_store = event_store
        self._repository = repository
        self._instrumentation = instrumentation

    async def execute(
        self,
        *,
        run_id: str,
        calculations: list[CalculationRecord],
    ) -> ProofWorkflowOutcome:
        _validate_calculation_set(run_id, calculations)
        requirements: dict[str, ProofRequirement] = {}
        growth = next(item for item in calculations if item.formula_id == FORMULA_ID)
        for calculation in calculations:
            requirement = (
                ProofRequirement.MUST_PROVE
                if calculation.formula_id == FORMULA_ID
                else ProofRequirement.NOT_REQUIRED
            )
            requirements[calculation.calculation_id] = requirement
            decision = ProofPolicyDecision(
                decision_id=f"PPD-{calculation.calculation_id}",
                run_id=run_id,
                calculation_id=calculation.calculation_id,
                formula_id=calculation.formula_id,
                requirement=requirement,
                policy_id=self.policy_id,
                reason=(
                    "Phase 3 requires a real proof for the owned revenue growth formula."
                    if requirement is ProofRequirement.MUST_PROVE
                    else "This calculation is outside the bounded Phase 3 proof policy."
                ),
            )
            await self._save(decision)

        proof_id = f"PROOF-{run_id}-REVENUE-GROWTH"
        await self._event_store.emit(
            run_id=run_id,
            task_id=growth.task_id,
            event_type=RuntimeEventType.PROOF_REQUIRED,
            payload={
                "proof_id": proof_id,
                "calculation_id": growth.calculation_id,
                "formula_id": growth.formula_id,
                "policy_id": self.policy_id,
            },
        )
        try:
            proof_input = _build_input(growth)
            input_path = self._proof_input_path(proof_id)
            write_proof_input(input_path, proof_input)
            input_path.chmod(0o600)
            commitment = ProofInputCommitment(
                commitment_id=f"PIC-{growth.calculation_id}",
                run_id=run_id,
                calculation_id=growth.calculation_id,
                formula_id=growth.formula_id,
                capability_id=growth.capability_id,
                implementation_hash=proof_input.implementation_hash,
                input_evidence_refs=list(proof_input.input_evidence_refs),
                canonical_inputs=proof_input.canonical_inputs.model_dump(mode="json"),
                input_commitment=proof_input.input_commitment,
                expected_output_commitment=proof_input.expected_output_commitment,
            )
            await self._save(commitment)
            await self._event_store.emit(
                run_id=run_id,
                task_id=growth.task_id,
                event_type=RuntimeEventType.PROOF_STARTED,
                payload={
                    "proof_id": proof_id,
                    "backend": "risc0",
                    "input_commitment": proof_input.input_commitment,
                },
            )
            async with self._proof_span(growth, proof_id):
                result = await self._adapter.prove(
                    ProofRequest(
                        proof_id=proof_id,
                        run_id=run_id,
                        calculation_id=growth.calculation_id,
                        program_id=FORMULA_ID,
                        input_commitments=[proof_input.input_commitment],
                        proof_input_ref=str(input_path),
                    )
                )
                if result.status is not ProofStatus.VALID or result.receipt_ref is None:
                    raise RuntimeError(result.detail or "RISC Zero proving failed")
                await self._event_store.emit(
                    run_id=run_id,
                    task_id=growth.task_id,
                    event_type=RuntimeEventType.PROOF_GENERATED,
                    payload={"proof_id": proof_id, "backend": "risc0"},
                )
                if not await self._adapter.verify(result):
                    raise RuntimeError("RISC Zero independent verification failed")
            records = _map_verified_records(
                run_id=run_id,
                calculation=growth,
                proof_id=proof_id,
                input_commitment=proof_input.input_commitment,
                result=result,
                artifact_root=self._artifact_dir,
            )
            proof_record, verification, artifact = records
            await self._save_verified_records(records, run_id=run_id)
            await self._event_store.emit(
                run_id=run_id,
                task_id=growth.task_id,
                event_type=RuntimeEventType.PROOF_VERIFIED,
                payload={
                    "proof_id": proof_id,
                    "image_id": proof_record.image_id,
                    "receipt_hash": proof_record.receipt_hash,
                    "journal_hash": proof_record.journal_hash,
                    "verified": True,
                    "dev_mode": False,
                },
            )
            return ProofWorkflowOutcome(
                requirements=requirements,
                proofs={growth.calculation_id: proof_record},
                runtime_state={
                    "status": ProofStatus.VERIFIED.value,
                    "proof_id": proof_id,
                    "image_id": proof_record.image_id,
                    "verification_id": verification.verification_id,
                    "dev_mode": False,
                },
                limitations=(
                    "The RISC Zero proof verifies program execution over bound inputs; it "
                    "does not prove that provider data is objectively true.",
                ),
            )
        except Exception as exc:
            await self._event_store.emit(
                run_id=run_id,
                task_id=growth.task_id,
                event_type=RuntimeEventType.PROOF_FAILED,
                payload={
                    "proof_id": proof_id,
                    "error_type": type(exc).__name__,
                    "status": ProofStatus.ERROR.value,
                },
            )
            return ProofWorkflowOutcome(
                requirements=requirements,
                proofs={},
                runtime_state={
                    "status": ProofStatus.ERROR.value,
                    "proof_id": proof_id,
                    "error_type": type(exc).__name__,
                },
                limitations=("Required RISC Zero proof did not verify; release is blocked.",),
            )

    def _proof_input_path(self, proof_id: str) -> Path:
        directory = self._artifact_dir / "inputs"
        directory.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(proof_id.encode("utf-8")).hexdigest()
        target = directory / f"{digest}.json"
        if target.exists() or target.is_symlink():
            raise ValueError("proof input target already exists")
        return target

    async def _save(self, entity: Any, *, run_id: str | None = None) -> None:
        if self._repository is not None:
            await self._repository.save(entity, run_id=run_id)

    async def _save_verified_records(
        self,
        records: tuple[ProofRecord, ProofVerificationRecord, ProofArtifactReference],
        *,
        run_id: str,
    ) -> None:
        if self._repository is None:
            return
        save_many = getattr(self._repository, "save_many", None)
        if callable(save_many):
            await save_many(records, run_id=run_id)
            return
        for record in records:
            await self._repository.save(record, run_id=run_id)

    @asynccontextmanager
    async def _proof_span(
        self,
        calculation: CalculationRecord,
        proof_id: str,
    ) -> AsyncIterator[None]:
        if self._instrumentation is None:
            yield
            return
        async with self._instrumentation.tool(
            run_id=calculation.run_id,
            task_id=calculation.task_id,
            attributes={
                "tool_name": "risc0_revenue_growth_prover",
                "proof_id": proof_id,
                "proof_backend": "risc0",
                "formula_id": calculation.formula_id,
            },
        ):
            yield


def _build_input(calculation: CalculationRecord):
    if calculation.capability_id != "revenue_growth" or calculation.formula_id != FORMULA_ID:
        raise ValueError("RISC Zero workflow only accepts owned revenue growth calculations")
    if len(calculation.input_evidence_ids) != 2:
        raise ValueError("revenue growth proof requires exactly two evidence references")
    implementation_hash = calculation.implementation_hash or calculation.code_hash
    if not implementation_hash:
        raise ValueError("revenue growth calculation has no implementation hash")
    snapshot = calculation.input_values_snapshot
    try:
        prior = Decimal(str(snapshot["prior_revenue"]))
        current = Decimal(str(snapshot["current_revenue"]))
        currency = str(snapshot["currency"])
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("revenue growth calculation snapshot is incomplete") from exc
    if not prior.is_finite() or not current.is_finite():
        raise ValueError("revenue proof inputs must be finite")
    scale = max(0, -prior.as_tuple().exponent, -current.as_tuple().exponent)
    factor = Decimal(10) ** scale
    prior_minor = int(prior * factor)
    current_minor = int(current * factor)
    canonical = CanonicalRevenueInputs(
        prior_revenue_minor=prior_minor,
        current_revenue_minor=current_minor,
        currency=currency,
        scale=scale,
    )
    expected = calculate_revenue_growth(canonical)
    expected_decimal = Decimal(expected.growth_numerator) / Decimal(expected.growth_denominator)
    if expected_decimal != Decimal(str(calculation.output_value)):
        raise ValueError("CalculationRecord output does not match canonical proof inputs")
    return build_proof_input(
        run_id=calculation.run_id,
        calculation_id=calculation.calculation_id,
        implementation_hash=implementation_hash,
        input_evidence_refs=tuple(calculation.input_evidence_ids),
        canonical_inputs=canonical,
    )


def _map_verified_records(
    *,
    run_id: str,
    calculation: CalculationRecord,
    proof_id: str,
    input_commitment: str,
    result,
    artifact_root: Path,
) -> tuple[ProofRecord, ProofVerificationRecord, ProofArtifactReference]:
    values = result.verifier_result
    receipt = Path(str(result.receipt_ref)).expanduser().resolve(strict=True)
    try:
        receipt.relative_to(artifact_root)
    except ValueError as exc:
        raise ValueError("receipt escaped the controlled proof artifact root") from exc
    image_id = _required_text(values, "image_id")
    receipt_hash = _required_text(values, "receipt_hash")
    journal_hash = _required_text(values, "journal_hash")
    actual_receipt_hash = f"sha256:{hashlib.sha256(receipt.read_bytes()).hexdigest()}"
    if receipt_hash != actual_receipt_hash:
        raise ValueError("receipt changed after independent verification")
    if values.get("dev_mode") is not False or values.get("verified") is not True:
        raise ValueError("verified proof metadata does not attest formal mode")
    proof = ProofRecord(
        proof_id=proof_id,
        run_id=run_id,
        calculation_id=calculation.calculation_id,
        backend="risc0",
        program_id=FORMULA_ID,
        image_id=image_id,
        implementation_hash=calculation.implementation_hash or calculation.code_hash or "",
        input_commitment=input_commitment,
        receipt_artifact_ref=str(receipt),
        receipt_hash=receipt_hash,
        journal_hash=journal_hash,
        status=ProofStatus.VERIFIED,
        proving_duration_ms=int(values.get("proving_duration_ms") or 0),
    )
    verification = ProofVerificationRecord(
        verification_id=f"PV-{proof_id}",
        proof_id=proof_id,
        verifier="risc0-independent-host-verifier",
        image_id=image_id,
        receipt_hash=receipt_hash,
        journal_hash=journal_hash,
        status=ProofStatus.VERIFIED,
        verified=True,
        detail="Receipt::verify passed for the compiled revenue growth image.",
    )
    artifact = ProofArtifactReference(
        artifact_id=f"PA-{proof_id}",
        proof_id=proof_id,
        artifact_type="application/vnd.risc0.receipt",
        artifact_ref=str(receipt),
        content_hash=receipt_hash,
        size_bytes=receipt.stat().st_size,
    )
    return proof, verification, artifact


def _required_text(values: dict[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"verified proof metadata is missing {key}")
    return value


def _validate_calculation_set(
    run_id: str,
    calculations: list[CalculationRecord],
) -> None:
    if not calculations:
        raise ValueError("proof workflow requires completed calculations")
    if any(calculation.run_id != run_id for calculation in calculations):
        raise ValueError("all proof-policy calculations must belong to the requested run")
    identifiers = [calculation.calculation_id for calculation in calculations]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("proof-policy calculation ids must be unique")
    growth = [calculation for calculation in calculations if calculation.formula_id == FORMULA_ID]
    if len(growth) != 1:
        raise ValueError("Phase 3 proof policy requires exactly one revenue_growth_v1 calculation")
