import hashlib
import hmac
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, DecimalException, localcontext
from pathlib import Path

from src.adapters.risc0 import EXPECTED_REVENUE_GROWTH_IMAGE_ID
from src.adapters.risc0.models import (
    CanonicalRevenueInputs,
    build_proof_input,
    calculate_revenue_growth,
)
from src.assurance.independent_financial_review import (
    financial_review_input_snapshot_hash,
)
from src.assurance.proof_policy import ProofRequirement
from src.domain.base import JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.enums import ProofStatus, ReviewStatus
from src.domain.evidence import EvidenceRecord
from src.domain.financial_semantics import MaterialFinancialClaim, ReleasedFinancialMetric
from src.domain.financial_validation import REVENUE_GROWTH_VALIDATION_REASON
from src.domain.proof import (
    ProofArtifactReference,
    ProofInputCommitment,
    ProofRecord,
    ProofResult,
    ProofVerificationRecord,
)
from src.domain.review import ReviewRecord

_STRICT_FINANCIAL_FORMULAS = {
    "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1",
    "sma_close_50_v1",
    "sma_close_200_v1",
    "rsi_close_14_simple_average_v1",
    "macd_line_close_12_26_adjust_false_v1",
    "macd_signal_close_12_26_9_adjust_false_v1",
    "macd_histogram_close_12_26_9_adjust_false_v1",
    "latest_volume_to_average_volume_20_v1",
}


@dataclass(frozen=True, slots=True)
class ReleaseDecision:
    allowed: bool
    reason_codes: tuple[str, ...]


class ReleaseGate:
    def evaluate(
        self,
        *,
        review: ReviewRecord,
        proof_requirements: dict[str, ProofRequirement],
        proofs: dict[str, ProofRecord | ProofResult],
        calculations: dict[str, CalculationRecord] | None = None,
        evidence: Sequence[EvidenceRecord] | None = None,
        metrics: Sequence[ReleasedFinancialMetric] | None = None,
        claims: Sequence[MaterialFinancialClaim] | None = None,
        judgments: Sequence[JsonObject] | None = None,
        run_as_of: date | None = None,
        input_commitments: dict[str, ProofInputCommitment] | None = None,
        verifications: dict[str, ProofVerificationRecord] | None = None,
        artifacts: dict[str, ProofArtifactReference] | None = None,
        requirement_context: JsonObject | None = None,
    ) -> ReleaseDecision:
        reasons: list[str] = []
        if review.requirement_context != requirement_context:
            reasons.append("REVIEW_REQUIREMENT_CONTEXT_MISMATCH")
        if review.status is not ReviewStatus.PASS:
            reasons.append(f"REVIEW_{review.status.value}")

        required_ids = {
            calculation_id
            for calculation_id, requirement in proof_requirements.items()
            if requirement is ProofRequirement.MUST_PROVE
        }
        extended_financial_calculations = bool(calculations) and any(
            item.formula_id in _STRICT_FINANCIAL_FORMULAS for item in calculations.values()
        )
        strict_lineage = (
            review.reviewer == "independent-financial-review-v2"
            or any(check.code.startswith("FIN_") for check in review.checks)
            or bool(review.reviewed_metric_refs)
            or bool(review.reviewed_claim_refs)
            or bool(review.required_proof_calculation_refs)
            or extended_financial_calculations
        )
        if strict_lineage and review.reviewer != "independent-financial-review-v2":
            reasons.append("STRICT_REVIEW_IDENTITY_INVALID")
        if strict_lineage:
            complete_review_inputs = (
                calculations is not None
                and evidence is not None
                and metrics is not None
                and claims is not None
                and judgments is not None
                and run_as_of is not None
            )
            if not complete_review_inputs:
                reasons.append("REVIEW_INPUT_SNAPSHOT_MISSING")
            else:
                assert calculations is not None
                assert evidence is not None
                assert metrics is not None
                assert claims is not None
                assert judgments is not None
                assert run_as_of is not None
                try:
                    snapshot_hash = financial_review_input_snapshot_hash(
                        run_id=review.run_id,
                        run_as_of=run_as_of,
                        evidence=evidence,
                        calculations=list(calculations.values()),
                        metrics=metrics,
                        claims=claims,
                        judgments=judgments,
                        proof_requirements=proof_requirements,
                        requirement_context=requirement_context,
                    )
                except (AttributeError, TypeError, ValueError):
                    snapshot_hash = None
                if (
                    snapshot_hash is None
                    or review.input_snapshot_hash is None
                    or not hmac.compare_digest(snapshot_hash, review.input_snapshot_hash)
                    or set(calculations) != set(review.reviewed_calculation_refs)
                    or {item.evidence_id for item in evidence} != set(review.reviewed_evidence_refs)
                    or {item.metric_id for item in metrics} != set(review.reviewed_metric_refs)
                    or {item.claim_id for item in claims} != set(review.reviewed_claim_refs)
                    or {
                        str(item.get("judgment_id"))
                        for item in judgments
                        if isinstance(item.get("judgment_id"), str)
                    }
                    != set(review.reviewed_judgment_refs)
                ):
                    reasons.append("REVIEW_INPUT_SNAPSHOT_MISMATCH")
        if strict_lineage and "RISC0_DEV_MODE" in os.environ:
            reasons.append("RISC0_DEV_MODE_FORBIDDEN")
        if strict_lineage and set(review.required_proof_calculation_refs) != required_ids:
            reasons.append("REVIEW_PROOF_REQUIREMENT_MISMATCH")
        if calculations is not None:
            for calculation in calculations.values():
                if calculation.formula_id != "revenue_growth_v1":
                    continue
                try:
                    prior_revenue = Decimal(str(calculation.input_values_snapshot["prior_revenue"]))
                    prior_is_positive = prior_revenue.is_finite() and prior_revenue > 0
                except (DecimalException, KeyError, TypeError, ValueError):
                    prior_is_positive = False
                if not prior_is_positive:
                    reasons.append(REVENUE_GROWTH_VALIDATION_REASON)
        if strict_lineage:
            for label, records in (
                ("PROOF", proofs),
                ("COMMITMENT", input_commitments or {}),
                ("VERIFICATION", verifications or {}),
                ("ARTIFACT", artifacts or {}),
            ):
                if set(records) != required_ids:
                    reasons.append(f"{label}_SET_MISMATCH")

        for calculation_id, requirement in proof_requirements.items():
            if requirement is not ProofRequirement.MUST_PROVE:
                continue
            proof = proofs.get(calculation_id)
            if proof is None:
                reasons.append(f"PROOF_MISSING:{calculation_id}")
                continue
            if isinstance(proof, ProofResult):
                reasons.append(f"PROOF_{proof.status.value}:{calculation_id}")
                continue
            invalid = (
                proof.status is not ProofStatus.VERIFIED
                or proof.run_id != review.run_id
                or proof.calculation_id != calculation_id
                or not proof.image_id
                or not proof.implementation_hash
                or not proof.input_commitment
                or not proof.receipt_artifact_ref
                or not proof.receipt_hash
                or not proof.journal_hash
                or (
                    strict_lineage
                    and (
                        proof.backend != "risc0"
                        or proof.image_id != EXPECTED_REVENUE_GROWTH_IMAGE_ID
                    )
                )
            )
            calculation = calculations.get(calculation_id) if calculations is not None else None
            if calculations is not None and strict_lineage:
                invalid = invalid or (
                    calculation is None
                    or calculation.run_id != review.run_id
                    or calculation.implementation_hash != proof.implementation_hash
                    or proof.program_id != calculation.formula_id
                )
            commitment = (
                input_commitments.get(calculation_id) if input_commitments is not None else None
            )
            if input_commitments is not None:
                expected_commitment = (
                    _expected_revenue_growth_commitment(calculation)
                    if calculation is not None
                    else None
                )
                invalid = invalid or (
                    commitment is None
                    or commitment.run_id != review.run_id
                    or commitment.calculation_id != calculation_id
                    or commitment.implementation_hash != proof.implementation_hash
                    or commitment.input_commitment != proof.input_commitment
                    or (
                        strict_lineage
                        and (
                            calculation is None
                            or commitment.formula_id != calculation.formula_id
                            or commitment.capability_id != calculation.capability_id
                            or commitment.input_evidence_refs != calculation.input_evidence_ids
                            or not commitment.expected_output_commitment
                            or expected_commitment is None
                            or commitment.canonical_inputs
                            != expected_commitment.canonical_inputs.model_dump(mode="json")
                            or commitment.input_commitment != expected_commitment.input_commitment
                            or commitment.expected_output_commitment
                            != expected_commitment.expected_output_commitment
                        )
                    )
                )
            elif strict_lineage:
                invalid = True
            verification = verifications.get(calculation_id) if verifications is not None else None
            if verifications is not None:
                invalid = invalid or (
                    verification is None
                    or verification.proof_id != proof.proof_id
                    or verification.status is not ProofStatus.VERIFIED
                    or verification.verified is not True
                    or verification.image_id != proof.image_id
                    or verification.receipt_hash != proof.receipt_hash
                    or verification.journal_hash != proof.journal_hash
                    or (
                        strict_lineage
                        and verification.verifier != "risc0-independent-host-verifier"
                    )
                )
            elif strict_lineage:
                invalid = True
            artifact = artifacts.get(calculation_id) if artifacts is not None else None
            if artifacts is not None:
                invalid = invalid or (
                    artifact is None
                    or artifact.proof_id != proof.proof_id
                    or artifact.artifact_ref != proof.receipt_artifact_ref
                    or artifact.content_hash != proof.receipt_hash
                    or artifact.size_bytes <= 0
                    or (
                        strict_lineage and artifact.artifact_type != "application/vnd.risc0.receipt"
                    )
                )
                if artifact is not None and strict_lineage:
                    receipt = Path(artifact.artifact_ref)
                    invalid = invalid or not receipt.is_file()
                    if receipt.is_file():
                        content = receipt.read_bytes()
                        invalid = invalid or (
                            artifact.size_bytes != len(content)
                            or artifact.content_hash
                            != f"sha256:{hashlib.sha256(content).hexdigest()}"
                        )
            elif strict_lineage:
                invalid = True
            if invalid:
                reasons.append(f"PROOF_IDENTITY_OR_VERIFICATION_INVALID:{calculation_id}")

        return ReleaseDecision(allowed=not reasons, reason_codes=tuple(reasons))


def _expected_revenue_growth_commitment(calculation: CalculationRecord):
    if calculation.formula_id != "revenue_growth_v1" or not calculation.implementation_hash:
        return None
    snapshot = calculation.input_values_snapshot
    try:
        prior = Decimal(str(snapshot["prior_revenue"]))
        current = Decimal(str(snapshot["current_revenue"]))
        currency = str(snapshot["currency"])
    except (ArithmeticError, DecimalException, KeyError, TypeError, ValueError):
        return None
    if len(calculation.input_evidence_ids) != 2 or not prior.is_finite() or not current.is_finite():
        return None
    try:
        scale = max(0, -prior.as_tuple().exponent, -current.as_tuple().exponent)
        factor = Decimal(10) ** scale
        canonical = CanonicalRevenueInputs(
            prior_revenue_minor=int(prior * factor),
            current_revenue_minor=int(current * factor),
            currency=currency,
            scale=scale,
        )
        result = calculate_revenue_growth(canonical)
        with localcontext() as context:
            context.prec = 28
            expected_value = Decimal(result.growth_numerator) / Decimal(result.growth_denominator)
        actual_value = Decimal(str(calculation.output_value))
        if not actual_value.is_finite() or actual_value != expected_value:
            return None
    except (ArithmeticError, DecimalException, TypeError, ValueError):
        return None
    return build_proof_input(
        run_id=calculation.run_id,
        calculation_id=calculation.calculation_id,
        implementation_hash=calculation.implementation_hash,
        input_evidence_refs=tuple(calculation.input_evidence_ids),
        canonical_inputs=canonical,
    )
