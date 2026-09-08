"""Independent financial-semantic review over immutable calculation inputs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, DecimalException, localcontext
from typing import Any

from src.domain.base import JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.enums import (
    CalculationStatus,
    CashFlowSignConvention,
    CorporateActionStatus,
    EvidenceCategory,
    EvidenceStatus,
    FinancialActuality,
    FinancialPeriodBasis,
    FinancialUnit,
    ProofRequirement,
    ReviewStatus,
    TechnicalPriceBasis,
)
from src.domain.evidence import EvidenceRecord
from src.domain.financial_branch import BranchRequirement, BranchStatus, FinancialBranchResult
from src.domain.financial_semantics import (
    MaterialFinancialClaim,
    ReleasedFinancialMetric,
    adjacent_financial_periods,
    canonical_decimal,
    evidence_unit_class,
)
from src.domain.financial_validation import REVENUE_GROWTH_VALIDATION_REASON
from src.domain.macd_policy import MACD_DECIMAL_CONTEXT_POLICY
from src.domain.review import ReviewCheck, ReviewRecord
from src.observability.performance import observe
from src.output.financial_metrics import MATERIAL_FORMULAS

_METRIC_SPECS: dict[str, tuple[str, FinancialUnit, str]] = {
    "revenue_growth_v1": ("Revenue Growth", FinancialUnit.RATIO, "%"),
    "ebitda_margin_v1": ("EBITDA Margin", FinancialUnit.RATIO, "%"),
    "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1": (
        "Free Cash Flow Margin",
        FinancialUnit.RATIO,
        "%",
    ),
    "sma_close_50_v1": (
        "50-Day Simple Moving Average",
        FinancialUnit.CURRENCY,
        "currency",
    ),
    "sma_close_200_v1": (
        "200-Day Simple Moving Average",
        FinancialUnit.CURRENCY,
        "currency",
    ),
    "rsi_close_14_simple_average_v1": (
        "RSI 14 (Simple Average, not Wilder)",
        FinancialUnit.INDEX,
        "index points",
    ),
    "macd_line_close_12_26_adjust_false_v1": (
        "MACD Line 12/26 EMA",
        FinancialUnit.CURRENCY,
        "currency",
    ),
    "macd_signal_close_12_26_9_adjust_false_v1": (
        "MACD Signal 9 EMA",
        FinancialUnit.CURRENCY,
        "currency",
    ),
    "macd_histogram_close_12_26_9_adjust_false_v1": (
        "MACD Histogram",
        FinancialUnit.CURRENCY,
        "currency",
    ),
    "latest_volume_to_average_volume_20_v1": (
        "Volume Ratio 20",
        FinancialUnit.RATIO,
        "x",
    ),
}


class IndependentFinancialReviewer:
    """Recompute every material metric without invoking production capabilities."""

    reviewer_id = "independent-financial-review-v2"

    @observe("review.compute", run="run_id")
    def review(
        self,
        *,
        review_id: str,
        run_id: str,
        run_as_of: date,
        evidence: Sequence[EvidenceRecord],
        calculations: Sequence[CalculationRecord],
        metrics: Sequence[ReleasedFinancialMetric],
        claims: Sequence[MaterialFinancialClaim],
        judgments: Sequence[JsonObject],
        proof_requirements: Mapping[str, ProofRequirement],
        branch_results: Sequence[FinancialBranchResult] = (),
        requirement_context: JsonObject | None = None,
    ) -> ReviewRecord:
        checks: list[ReviewCheck] = []
        evidence_by_id = _unique(evidence, "evidence_id", "evidence")
        calculation_by_id = _unique(calculations, "calculation_id", "calculation")
        metric_by_calculation = _unique(metrics, "calculation_id", "metric calculation")
        claim_by_metric = _unique(claims, "metric_id", "claim metric")
        formulas = [item.formula_id for item in calculations]
        expected_formulas = set(MATERIAL_FORMULAS)
        if requirement_context is not None:
            from src.domain.financial_branch import BRANCH_FORMULAS

            explicit = set(requirement_context["required_calculations"])
            valid = (
                requirement_context["branches"]
                == [b.model_dump(mode="json") for b in branch_results]
                and len(branch_results) == len(BRANCH_FORMULAS)
                and {b.calculation_type for b in branch_results} == set(BRANCH_FORMULAS)
            )
            for branch in branch_results:
                required = (
                    branch.calculation_type in explicit
                    or branch.calculation_type == "free_cash_flow_margin"
                )
                valid = valid and (branch.requirement is BranchRequirement.REQUIRED) == required
                if (
                    not required
                    and branch.status
                    in {BranchStatus.INSUFFICIENT_DATA, BranchStatus.BLOCKED_BY_RUNTIME}
                    and branch.reason_code
                ):
                    expected_formulas.difference_update(BRANCH_FORMULAS[branch.calculation_type])
            valid = valid and explicit.issubset({c.capability_id for c in calculations})
            _check(
                checks,
                "FIN_SCHEME_REQUIREMENT_CLOSURE",
                valid,
                refs=[b.branch_id for b in branch_results],
                expected={"status": "PASS"},
                actual={"status": "PASS" if valid else "BLOCK"},
            )
        for branch in branch_results:
            owned = [
                item.calculation_id
                for item in calculations
                if item.capability_id == branch.calculation_type
            ]
            eligible = branch.status is BranchStatus.COMPLETED
            _check(
                checks,
                "FIN_BRANCH_CALCULATION_AVAILABILITY",
                branch.run_id == run_id
                and set(owned) == set(branch.calculation_ids)
                and (eligible or not owned),
                refs=[branch.branch_id, *owned],
                expected={"status": "PASS"},
                actual={"status": branch.status.value},
            )
            if branch.requirement is BranchRequirement.REQUIRED:
                _check(
                    checks,
                    "FIN_REQUIRED_BRANCH_AVAILABILITY",
                    eligible,
                    refs=[branch.branch_id],
                    expected={"status": "COMPLETED"},
                    actual={"status": branch.status.value},
                )

        _check(
            checks,
            "FIN_MATERIAL_FORMULA_CLOSURE",
            len(formulas) == len(set(formulas)) and set(formulas) == expected_formulas,
            refs=[item.calculation_id for item in calculations],
            expected={"formula_ids": sorted(expected_formulas)},
            actual={"formula_ids": sorted(formulas)},
        )
        _check(
            checks,
            "FIN_TYPED_RELEASE_CARDINALITY",
            len(calculations) == len(metrics) == len(claims) == len(expected_formulas),
            expected={"count": len(expected_formulas)},
            actual={
                "calculations": len(calculations),
                "metrics": len(metrics),
                "claims": len(claims),
            },
        )

        for calculation in calculations:
            inputs = [
                evidence_by_id[evidence_id]
                for evidence_id in calculation.input_evidence_ids
                if evidence_id in evidence_by_id
            ]
            identity_ok = (
                calculation.run_id == run_id
                and calculation.status is CalculationStatus.PASS
                and _calculation_identity_matches(calculation)
                and len(inputs) == len(calculation.input_evidence_ids)
                and len(inputs) == len({item.evidence_id for item in inputs})
                and all(
                    item.run_id == run_id
                    and item.status is EvidenceStatus.ACCEPTED
                    and item.as_of <= run_as_of
                    for item in inputs
                )
            )
            _check(
                checks,
                "FIN_CALCULATION_IDENTITY",
                identity_ok,
                refs=[calculation.calculation_id, *calculation.input_evidence_ids],
                expected={"run_id": run_id, "status": "PASS"},
                actual={
                    "run_id": calculation.run_id,
                    "status": calculation.status.value,
                    "input_count": len(calculation.input_evidence_ids),
                    "resolved_input_count": len(inputs),
                    "implementation_hash": calculation.implementation_hash,
                },
                detail=calculation.formula_id,
            )
            if not identity_ok:
                continue
            try:
                _validate_formula_semantics(calculation.formula_id, inputs)
                expected_value = _recompute(calculation.formula_id, inputs)
                actual_value = _decimal(calculation.output_value)
                recompute_ok = expected_value == actual_value
                recompute_detail = None
            except (ArithmeticError, DecimalException, KeyError, TypeError, ValueError) as exc:
                expected_value = None
                actual_value = None
                recompute_ok = False
                recompute_detail = str(exc)
            _check(
                checks,
                "FIN_CALCULATION_RECOMPUTATION",
                recompute_ok,
                refs=[calculation.calculation_id, *calculation.input_evidence_ids],
                expected={
                    "formula_id": calculation.formula_id,
                    "value": (
                        canonical_decimal(expected_value) if expected_value is not None else None
                    ),
                    "tolerance": "0",
                },
                actual={
                    "value": (canonical_decimal(actual_value) if actual_value is not None else None)
                },
                detail=recompute_detail,
            )
            metric = metric_by_calculation.get(calculation.calculation_id)
            try:
                snapshot_ok = _snapshot_matches(calculation, inputs)
            except (
                ArithmeticError,
                DecimalException,
                IndexError,
                KeyError,
                TypeError,
                ValueError,
            ):
                snapshot_ok = False
            _check(
                checks,
                "FIN_CALCULATION_INPUT_SNAPSHOT",
                snapshot_ok,
                refs=[calculation.calculation_id, *calculation.input_evidence_ids],
                expected={"bound_to_evidence": True},
                actual={"bound_to_evidence": snapshot_ok},
            )
            try:
                metric_ok = metric is not None and _metric_matches(
                    calculation,
                    metric,
                    inputs,
                )
            except (ArithmeticError, DecimalException, KeyError, TypeError, ValueError):
                metric_ok = False
            _check(
                checks,
                "FIN_METRIC_BINDING",
                metric_ok,
                refs=[
                    calculation.calculation_id,
                    *([metric.metric_id] if metric is not None else []),
                ],
                expected={"formula_id": calculation.formula_id},
                actual={
                    "formula_id": metric.formula_id if metric is not None else None,
                    "value": metric.canonical_value if metric is not None else None,
                },
            )
            claim = claim_by_metric.get(metric.metric_id) if metric is not None else None
            claim_ok = (
                metric is not None
                and claim is not None
                and _claim_matches(
                    run_id,
                    calculation,
                    metric,
                    claim,
                )
            )
            _check(
                checks,
                "FIN_CLAIM_SUPPORT",
                claim_ok,
                refs=[
                    calculation.calculation_id,
                    *([claim.claim_id] if claim is not None else []),
                ],
                expected={"metric_id": metric.metric_id if metric is not None else None},
                actual={"metric_id": claim.metric_id if claim is not None else None},
            )

        calculation_ids = set(calculation_by_id)
        evidence_ids = set(evidence_by_id)
        judgment_ids: list[str] = []
        judgment_types: set[str] = set()
        judgment_ok = True
        for judgment in judgments:
            judgment_id = judgment.get("judgment_id")
            if not isinstance(judgment_id, str) or not judgment_id:
                judgment_ok = False
                continue
            judgment_ids.append(judgment_id)
            judgment_type = judgment.get("judgment_type")
            if not isinstance(judgment_type, str):
                judgment_ok = False
                continue
            judgment_types.add(judgment_type)
            if judgment.get("run_id") != run_id:
                judgment_ok = False
            judgment_calculation_ids = _string_list(judgment.get("calculation_ids"))
            judgment_evidence_ids = _string_list(judgment.get("evidence_ids"))
            if not judgment_calculation_ids or not set(judgment_calculation_ids).issubset(
                calculation_ids
            ):
                judgment_ok = False
            if not judgment_evidence_ids or not set(judgment_evidence_ids).issubset(evidence_ids):
                judgment_ok = False
            if (
                judgment.get("requires_review") is not True
                or judgment.get("model") != "finrobot-technical-threshold-policy-v1"
                or not judgment.get("skill_version")
                or not judgment.get("limitations")
            ):
                judgment_ok = False
            if judgment_type == "rsi_state":
                referenced = [
                    calculation_by_id[item]
                    for item in judgment_calculation_ids
                    if item in calculation_by_id
                ]
                if len(referenced) != 1 or referenced[0].formula_id != (
                    "rsi_close_14_simple_average_v1"
                ):
                    judgment_ok = False
                elif judgment.get("value") != _safe_rsi_label(referenced[0].output_value):
                    judgment_ok = False
                elif set(judgment_evidence_ids) != set(referenced[0].input_evidence_ids):
                    judgment_ok = False
            elif judgment_type == "macd_state":
                referenced = [
                    calculation_by_id[item]
                    for item in judgment_calculation_ids
                    if item in calculation_by_id
                ]
                by_formula = {item.formula_id: item for item in referenced}
                line = by_formula.get("macd_line_close_12_26_adjust_false_v1")
                signal = by_formula.get("macd_signal_close_12_26_9_adjust_false_v1")
                if line is None or signal is None or len(referenced) != 2:
                    judgment_ok = False
                elif judgment.get("value") != _safe_macd_label(
                    line.output_value,
                    signal.output_value,
                ):
                    judgment_ok = False
                elif set(judgment_evidence_ids) != {
                    evidence_id for item in referenced for evidence_id in item.input_evidence_ids
                }:
                    judgment_ok = False
            else:
                judgment_ok = False
        claim_judgment_refs = {
            judgment_id for claim in claims for judgment_id in claim.judgment_refs
        }
        judgment_ok = judgment_ok and claim_judgment_refs.issubset(set(judgment_ids))
        for claim in claims:
            metric = next(
                (item for item in metrics if item.metric_id == claim.metric_id),
                None,
            )
            if metric is None:
                judgment_ok = False
                continue
            formula_id = metric.formula_id
            exact_supporting_judgments = {
                str(judgment["judgment_id"])
                for judgment in judgments
                if metric.calculation_id in _string_list(judgment.get("calculation_ids"))
                and isinstance(judgment.get("judgment_id"), str)
            }
            if set(claim.judgment_refs) != exact_supporting_judgments:
                judgment_ok = False
            expected_type = (
                "rsi_state"
                if formula_id == "rsi_close_14_simple_average_v1"
                else "macd_state"
                if formula_id
                in {
                    "macd_line_close_12_26_adjust_false_v1",
                    "macd_signal_close_12_26_9_adjust_false_v1",
                }
                else None
            )
            if expected_type is not None and not any(
                judgment.get("judgment_id") in claim.judgment_refs
                and judgment.get("judgment_type") == expected_type
                for judgment in judgments
            ):
                judgment_ok = False
        expected_judgments = {"rsi_state", "macd_state"}
        if requirement_context is not None:
            expected_judgments = set()
            if "rsi_close_14_simple_average_v1" in expected_formulas:
                expected_judgments.add("rsi_state")
            if "macd_line_close_12_26_adjust_false_v1" in expected_formulas:
                expected_judgments.add("macd_state")
        _check(
            checks,
            "FIN_JUDGMENT_SUPPORT",
            judgment_ok
            and judgment_types == expected_judgments
            and len(judgment_ids) == len(set(judgment_ids)) == len(expected_judgments),
            refs=judgment_ids,
            expected={"run_id": run_id, "unique": True},
            actual={"count": len(judgment_ids), "unique_count": len(set(judgment_ids))},
        )

        required = sorted(
            calculation_id
            for calculation_id, requirement in proof_requirements.items()
            if requirement is ProofRequirement.MUST_PROVE
        )
        _check(
            checks,
            "FIN_PROOF_REQUIREMENT_CLOSURE",
            set(proof_requirements) == calculation_ids
            and len(required) == 1
            and calculation_by_id[required[0]].formula_id == "revenue_growth_v1",
            refs=required,
            expected={"must_prove_formula": "revenue_growth_v1"},
            actual={"required_calculation_ids": required},
        )

        snapshot_hash = financial_review_input_snapshot_hash(
            run_id=run_id,
            run_as_of=run_as_of,
            evidence=evidence,
            calculations=calculations,
            metrics=metrics,
            claims=claims,
            judgments=judgments,
            proof_requirements=proof_requirements,
            requirement_context=requirement_context,
        )
        status = (
            ReviewStatus.PASS
            if checks and all(item.status is ReviewStatus.PASS for item in checks)
            else ReviewStatus.BLOCK
        )
        return ReviewRecord(
            review_id=review_id,
            run_id=run_id,
            status=status,
            deterministic_findings=[
                {"code": item.code, "detail": item.detail}
                for item in checks
                if item.status is ReviewStatus.BLOCK
            ],
            reviewed_evidence_refs=sorted(evidence_ids),
            reviewed_calculation_refs=sorted(calculation_ids),
            reviewed_metric_refs=sorted(item.metric_id for item in metrics),
            reviewed_claim_refs=sorted(item.claim_id for item in claims),
            reviewed_judgment_refs=sorted(judgment_ids),
            required_proof_calculation_refs=required,
            checks=checks,
            input_snapshot_hash=snapshot_hash,
            requirement_context=requirement_context,
            reviewer=self.reviewer_id,
        )


def financial_review_input_snapshot_hash(
    *,
    run_id: str,
    run_as_of: date,
    evidence: Sequence[EvidenceRecord],
    calculations: Sequence[CalculationRecord],
    metrics: Sequence[ReleasedFinancialMetric],
    claims: Sequence[MaterialFinancialClaim],
    judgments: Sequence[JsonObject],
    proof_requirements: Mapping[str, ProofRequirement],
    requirement_context: JsonObject | None = None,
) -> str:
    """Hash the exact immutable inputs independently reviewed before proof/release."""

    payload = {
        "run_id": run_id,
        "run_as_of": run_as_of.isoformat(),
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "calculations": [_reviewed_calculation_payload(item) for item in calculations],
        "metrics": [item.model_dump(mode="json") for item in metrics],
        "claims": [item.model_dump(mode="json") for item in claims],
        "judgments": list(judgments),
        "proof_requirements": {
            key: value.value for key, value in sorted(proof_requirements.items())
        },
    }
    if requirement_context is not None:
        payload["requirement_context"] = requirement_context
    encoded = json.dumps(
        payload,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _check(
    checks: list[ReviewCheck],
    code: str,
    passed: bool,
    *,
    refs: Sequence[str] = (),
    expected: JsonObject | None = None,
    actual: JsonObject | None = None,
    detail: str | None = None,
) -> None:
    checks.append(
        ReviewCheck(
            code=code,
            status=ReviewStatus.PASS if passed else ReviewStatus.BLOCK,
            subject_refs=list(refs),
            expected=expected or {},
            actual=actual or {},
            detail=detail,
        )
    )


def _reviewed_calculation_payload(calculation: CalculationRecord) -> JsonObject:
    payload = calculation.model_dump(mode="json")
    for field in ("review_record_id", "canonical_record_id", "proof_ref"):
        payload[field] = None
    return payload


def _unique(values: Sequence[Any], field: str, label: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in values:
        identifier = getattr(item, field)
        if identifier in result:
            raise ValueError(f"duplicate {label} id: {identifier}")
        result[identifier] = item
    return result


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("financial value must be numeric")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("financial value must be finite")
    return number


def _values(inputs: Sequence[EvidenceRecord], field: str) -> list[Decimal]:
    return [_decimal(item.normalized_value) for item in inputs if item.normalized_field == field]


def _calculation_identity_matches(calculation: CalculationRecord) -> bool:
    if (
        not calculation.implementation_hash
        or calculation.code_hash != calculation.implementation_hash
        or not calculation.source_ref
        or not calculation.runtime_version
    ):
        return False
    native_sources = {
        "revenue_growth_v1": "src.capabilities.financial.growth",
        "ebitda_margin_v1": "src.capabilities.financial.profitability",
    }
    source_prefix = native_sources.get(calculation.formula_id)
    if source_prefix is not None:
        return calculation.source_ref.startswith(source_prefix)
    if calculation.formula_id == ("operating_cash_flow_plus_signed_capex_divided_by_revenue_v1"):
        return (
            calculation.capability_id == "free_cash_flow_margin"
            and calculation.source_ref.startswith("generated://")
            and calculation.parameters.get("generated_source_hash")
            == calculation.implementation_hash
            and bool(calculation.parameters.get("generated_tests_hash"))
            and bool(calculation.parameters.get("live_input_commitment"))
        )
    return calculation.capability_id.startswith("technical_") and calculation.source_ref.startswith(
        "src.adapters.finrobot.technical"
    )


def _snapshot_matches(
    calculation: CalculationRecord,
    inputs: Sequence[EvidenceRecord],
) -> bool:
    snapshot = calculation.input_values_snapshot
    by_field = {item.normalized_field: item for item in inputs}
    formula_id = calculation.formula_id
    if formula_id == "revenue_growth_v1":
        if len(inputs) != 2:
            return False
        prior, current = inputs
        return (
            _same_decimal(snapshot.get("prior_revenue"), prior.normalized_value)
            and _same_decimal(snapshot.get("current_revenue"), current.normalized_value)
            and snapshot.get("currency") == current.currency
            and snapshot.get("prior_period") == prior.period
            and snapshot.get("current_period") == current.period
            and snapshot.get("period_basis") == current.period_basis.value
            and snapshot.get("actuality") == current.actuality.value
            and snapshot.get("statement_series") == current.statement_series
        )
    if formula_id == "ebitda_margin_v1":
        ebitda = by_field.get("ebitda")
        revenue = by_field.get("revenue")
        return bool(
            ebitda
            and revenue
            and _same_decimal(snapshot.get("ebitda"), ebitda.normalized_value)
            and _same_decimal(snapshot.get("revenue"), revenue.normalized_value)
            and snapshot.get("currency") == revenue.currency
            and snapshot.get("period") == revenue.period
            and snapshot.get("period_basis") == revenue.period_basis.value
            and snapshot.get("actuality") == revenue.actuality.value
            and snapshot.get("statement_cohort") == revenue.statement_cohort
        )
    if formula_id == "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1":
        required = {"operating_cash_flow", "capital_expenditure", "revenue"}
        if set(by_field) != required:
            return False
        if not all(
            _same_decimal(snapshot.get(field), by_field[field].normalized_value)
            for field in required
        ):
            return False
        parameters = calculation.parameters
        expected_value = canonical_decimal(_recompute(formula_id, inputs))
        oracle = parameters.get("owned_oracle_result")
        runtime = parameters.get("runtime_result")
        return (
            parameters.get("validation_scope") == "LIVE_RUNTIME"
            and parameters.get("financial_validation_result") == "PASS"
            and parameters.get("capital_expenditure_sign_convention")
            == CashFlowSignConvention.OUTFLOW_NEGATIVE.value
            and parameters.get("statement_cohort") == by_field["revenue"].statement_cohort
            and parameters.get("period") == by_field["revenue"].period
            and parameters.get("period_basis") == by_field["revenue"].period_basis.value
            and parameters.get("actuality") == by_field["revenue"].actuality.value
            and parameters.get("as_of") == by_field["revenue"].as_of.isoformat()
            and parameters.get("currency") == by_field["revenue"].currency
            and isinstance(oracle, dict)
            and isinstance(runtime, dict)
            and _same_decimal(oracle.get("value"), expected_value)
            and _same_decimal(runtime.get("value"), expected_value)
            and oracle.get("unit") == "RATIO"
            and runtime.get("unit") == "RATIO"
        )
    first = inputs[0]
    last = inputs[-1]
    bases = {
        item.technical_price_basis
        or (
            TechnicalPriceBasis.ADJUSTED_CLOSE
            if item.normalized_field == "adjusted_close"
            else TechnicalPriceBasis.RAW_CLOSE
        )
        for item in inputs
        if item.normalized_field in {"close", "adjusted_close"}
    }
    actions = {
        item.corporate_action_status or CorporateActionStatus.UNASSESSED
        for item in inputs
        if item.normalized_field in {"close", "adjusted_close"}
    }
    common = (
        snapshot.get("first_as_of") == first.as_of.isoformat()
        and snapshot.get("last_as_of") == last.as_of.isoformat()
    )
    if bases:
        common = (
            common
            and len(bases) == 1
            and snapshot.get("technical_price_basis") == next(iter(bases)).value
            and len(actions) == 1
            and snapshot.get("corporate_action_status") == next(iter(actions)).value
        )
    if formula_id == "sma_close_50_v1":
        return common and snapshot.get("window") == 50 and snapshot.get("observation_count") == 50
    if formula_id == "sma_close_200_v1":
        return common and snapshot.get("window") == 200 and snapshot.get("observation_count") == 200
    if formula_id == "rsi_close_14_simple_average_v1":
        return (
            common
            and snapshot.get("period") == 14
            and snapshot.get("price_change_count") == 14
            and snapshot.get("zero_gain_and_loss_policy") == "50_index_points"
            and snapshot.get("rsi_method") == "simple_average_not_wilder"
        )
    if formula_id.startswith("macd_"):
        policy = MACD_DECIMAL_CONTEXT_POLICY
        return (
            common
            and snapshot.get("decimal_context_policy_id") == policy.policy_id
            and snapshot.get("decimal_precision") == policy.precision
            and snapshot.get("decimal_rounding") == policy.rounding
            and snapshot.get("fast_span") == policy.fast_span
            and snapshot.get("slow_span") == policy.slow_span
            and snapshot.get("signal_span") == policy.signal_span
            and snapshot.get("ema_adjust") is policy.ema_adjust
            and snapshot.get("ema_seed") == policy.ema_seed
            and snapshot.get("observation_count") == len(inputs)
            and snapshot.get("warmup_required") == policy.warmup_required
            and snapshot.get("warmup_satisfied") is True
        )
    return (
        common
        and snapshot.get("window") == 20
        and snapshot.get("average_includes_latest_observation") is True
    )


def _metric_matches(
    calculation: CalculationRecord,
    metric: ReleasedFinancialMetric,
    inputs: Sequence[EvidenceRecord],
) -> bool:
    name, unit, display_unit_kind = _METRIC_SPECS[calculation.formula_id]
    technical = calculation.formula_id not in MATERIAL_FORMULAS[:3]
    anchor = max(inputs, key=lambda item: (item.as_of, item.evidence_id))
    period = "DAILY" if technical else anchor.period
    period_basis = FinancialPeriodBasis.DAILY if technical else anchor.period_basis
    currencies = {item.currency for item in inputs if item.currency}
    currency = next(iter(currencies), None) if len(currencies) <= 1 else None
    expected_display = _display(calculation.output_value, display_unit_kind)
    expected_display_unit = currency if display_unit_kind == "currency" else display_unit_kind
    output_unit_ok = calculation.output_unit.upper() == (
        currency if unit is FinancialUnit.CURRENCY else _calculation_output_unit(unit)
    )
    if metric.method_metadata is not None:
        method_ok = _method_metadata_matches(calculation, metric, inputs)
    else:
        method_ok = not technical
    if not technical:
        method_ok = method_ok and (
            metric.technical_price_basis is None
            and metric.corporate_action_status is None
            and not metric.corporate_action_guard_refs
        )
    basis_ok = True
    if technical and any(item.normalized_field in {"close", "adjusted_close"} for item in inputs):
        bases = {
            item.technical_price_basis
            or (
                TechnicalPriceBasis.ADJUSTED_CLOSE
                if item.normalized_field == "adjusted_close"
                else TechnicalPriceBasis.RAW_CLOSE
            )
            for item in inputs
        }
        actions = {
            item.corporate_action_status or CorporateActionStatus.UNASSESSED for item in inputs
        }
        expected_basis = next(iter(bases))
        expected_action = next(iter(actions))
        basis_ok = (
            len(bases) == 1
            and len(actions) == 1
            and metric.technical_price_basis is expected_basis
            and metric.corporate_action_status is expected_action
            and (
                expected_action is CorporateActionStatus.UNASSESSED
                and expected_basis is TechnicalPriceBasis.RAW_CLOSE
                and bool(metric.limitations)
                or expected_action
                in {CorporateActionStatus.NONE_DETECTED, CorporateActionStatus.RESOLVED}
                and set(metric.corporate_action_guard_refs) == {item.evidence_id for item in inputs}
            )
        )
    return (
        output_unit_ok
        and metric.calculation_id == calculation.calculation_id
        and metric.name == name
        and metric.formula_id == calculation.formula_id
        and metric.capability_id == calculation.capability_id
        and metric.canonical_value == canonical_decimal(calculation.output_value)
        and metric.canonical_unit is unit
        and metric.display_value == expected_display
        and metric.display_unit == expected_display_unit
        and metric.period == period
        and metric.period_basis is period_basis
        and metric.actuality is anchor.actuality
        and metric.as_of == anchor.as_of
        and metric.currency == currency
        and metric.evidence_ids == tuple(calculation.input_evidence_ids)
        and method_ok
        and basis_ok
    )


def _claim_matches(
    run_id: str,
    calculation: CalculationRecord,
    metric: ReleasedFinancialMetric,
    claim: MaterialFinancialClaim,
) -> bool:
    expected_statement = (
        f"Revenue {'increased' if Decimal(metric.canonical_value) >= 0 else 'decreased'} "
        f"{metric.display_value}{metric.display_unit} YoY for {metric.period}."
        if calculation.formula_id == "revenue_growth_v1"
        else (
            f"{metric.name} was {metric.display_value}{metric.display_unit} for "
            f"{metric.period} as of {metric.as_of.isoformat()}."
        )
    )
    return (
        claim.run_id == run_id
        and claim.claim_type == "MATERIAL_FINANCIAL_METRIC"
        and claim.statement == expected_statement
        and claim.metric_id == metric.metric_id
        and claim.value == metric.canonical_value
        and claim.unit is metric.canonical_unit
        and claim.period == metric.period
        and claim.period_basis is metric.period_basis
        and claim.actuality is metric.actuality
        and claim.as_of == metric.as_of
        and claim.currency == metric.currency
        and claim.calculation_refs == (calculation.calculation_id,)
        and claim.evidence_refs == tuple(calculation.input_evidence_ids)
    )


def _method_metadata_matches(
    calculation: CalculationRecord,
    metric: ReleasedFinancialMetric,
    inputs: Sequence[EvidenceRecord],
) -> bool:
    method = metric.method_metadata
    if method is None:
        return False
    formula_id = calculation.formula_id
    expected: tuple[str, int, int]
    if formula_id == "rsi_close_14_simple_average_v1":
        expected = ("RSI_SIMPLE_AVERAGE_NOT_WILDER", 15, 15)
        extra = method.is_wilder is False and method.parameters == (("period", "14"),)
    elif formula_id.startswith("macd_"):
        policy = MACD_DECIMAL_CONTEXT_POLICY
        expected = (
            "MACD_EMA_12_26_9_FIRST_OBSERVATION_SEED",
            len(inputs),
            policy.warmup_required,
        )
        price_bases = {
            item.technical_price_basis
            or (
                TechnicalPriceBasis.ADJUSTED_CLOSE
                if item.normalized_field == "adjusted_close"
                else TechnicalPriceBasis.RAW_CLOSE
            )
            for item in inputs
        }
        extra = (
            len(price_bases) == 1
            and method.decimal_context_policy_id == policy.policy_id
            and method.decimal_precision == policy.precision
            and method.decimal_rounding == policy.rounding
            and method.ema_adjust is policy.ema_adjust
            and method.ema_seed == policy.ema_seed
            and method.fast_span == policy.fast_span
            and method.slow_span == policy.slow_span
            and method.signal_span == policy.signal_span
            and method.technical_price_basis is next(iter(price_bases))
            and method.parameters
            == (
                ("fast", str(policy.fast_span)),
                ("slow", str(policy.slow_span)),
                ("signal", str(policy.signal_span)),
            )
        )
    elif formula_id == "latest_volume_to_average_volume_20_v1":
        expected = ("VOLUME_RATIO", 20, 20)
        extra = method.parameters == (("window", "20"),)
    elif formula_id == "sma_close_50_v1":
        expected = ("SIMPLE_MOVING_AVERAGE", 50, 50)
        extra = method.parameters == (("window", "50"),)
    else:
        expected = ("SIMPLE_MOVING_AVERAGE", 200, 200)
        extra = method.parameters == (("window", "200"),)
    return (
        method.method == expected[0]
        and method.observation_count == expected[1]
        and method.warmup_required == expected[2]
        and method.warmup_satisfied is True
        and method.first_as_of == inputs[0].as_of
        and method.last_as_of == inputs[-1].as_of
        and extra
    )


def _same_decimal(first: object, second: object) -> bool:
    try:
        return _decimal(first) == _decimal(second)
    except (DecimalException, TypeError, ValueError):
        return False


def _display(value: object, display_unit: str) -> str:
    number = _decimal(value)
    if display_unit == "%":
        number *= Decimal(100)
    return format(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _calculation_output_unit(unit: FinancialUnit) -> str:
    if unit is FinancialUnit.INDEX:
        return "INDEX_POINTS"
    return unit.value


def _rsi_label(value: Decimal) -> str:
    if value > 70:
        return "OVERBOUGHT"
    if value < 30:
        return "OVERSOLD"
    if value > 55:
        return "BULLISH"
    if value < 45:
        return "BEARISH"
    return "NEUTRAL"


def _macd_label(line: Decimal, signal: Decimal) -> str:
    if line > signal:
        return "BULLISH"
    if line < signal:
        return "BEARISH"
    return "NEUTRAL"


def _safe_rsi_label(value: object) -> str | None:
    try:
        return _rsi_label(_decimal(value))
    except (DecimalException, TypeError, ValueError):
        return None


def _safe_macd_label(line: object, signal: object) -> str | None:
    try:
        return _macd_label(_decimal(line), _decimal(signal))
    except (DecimalException, TypeError, ValueError):
        return None


def _validate_formula_semantics(
    formula_id: str,
    inputs: Sequence[EvidenceRecord],
) -> None:
    if formula_id == "revenue_growth_v1":
        if len(inputs) != 2 or any(item.normalized_field != "revenue" for item in inputs):
            raise ValueError("revenue growth requires two revenue inputs")
        prior, current = inputs
        if _decimal(prior.normalized_value) <= 0:
            raise ValueError(REVENUE_GROWTH_VALIDATION_REASON)
        if (
            any(
                item.evidence_category is not EvidenceCategory.FINANCIAL_STATEMENT
                for item in inputs
            )
            or prior.object_id != current.object_id
            or prior.period_basis is not FinancialPeriodBasis.FY
            or current.period_basis is not FinancialPeriodBasis.FY
            or not adjacent_financial_periods(prior.period, current.period)
            or prior.actuality is not current.actuality
            or prior.actuality is FinancialActuality.UNKNOWN
            or not prior.statement_series
            or prior.statement_series != current.statement_series
            or not prior.currency
            or prior.currency != current.currency
            or evidence_unit_class(prior.unit, prior.currency) is not FinancialUnit.CURRENCY
            or evidence_unit_class(current.unit, current.currency) is not FinancialUnit.CURRENCY
        ):
            raise ValueError("revenue growth period/series/currency semantics mismatch")
        return
    if formula_id == "ebitda_margin_v1":
        if len(inputs) != 2 or {item.normalized_field for item in inputs} != {
            "ebitda",
            "revenue",
        }:
            raise ValueError("EBITDA margin input set mismatch")
        first, second = inputs
        if (
            any(
                item.evidence_category is not EvidenceCategory.FINANCIAL_STATEMENT
                for item in inputs
            )
            or first.object_id != second.object_id
            or first.period != second.period
            or first.period_basis is not second.period_basis
            or first.period_basis is not FinancialPeriodBasis.FY
            or first.actuality is not second.actuality
            or first.actuality is FinancialActuality.UNKNOWN
            or first.as_of != second.as_of
            or not first.statement_cohort
            or first.statement_cohort != second.statement_cohort
            or not first.currency
            or first.currency != second.currency
            or evidence_unit_class(first.unit, first.currency) is not FinancialUnit.CURRENCY
            or evidence_unit_class(second.unit, second.currency) is not FinancialUnit.CURRENCY
        ):
            raise ValueError("EBITDA margin cohort semantics mismatch")
        return
    if formula_id == "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1":
        fields = {item.normalized_field: item for item in inputs}
        if len(inputs) != 3 or set(fields) != {
            "operating_cash_flow",
            "capital_expenditure",
            "revenue",
        }:
            raise ValueError("FCF margin input set mismatch")
        capex = fields["capital_expenditure"]
        reference = fields["revenue"]
        if (
            any(
                item.evidence_category is not EvidenceCategory.FINANCIAL_STATEMENT
                for item in inputs
            )
            or capex.cash_flow_sign_convention is not CashFlowSignConvention.OUTFLOW_NEGATIVE
            or _decimal(capex.normalized_value) > 0
            or reference.period_basis is not FinancialPeriodBasis.FY
            or reference.actuality is FinancialActuality.UNKNOWN
            or not reference.statement_cohort
            or not reference.currency
            or any(
                item.object_id != reference.object_id
                or item.period != reference.period
                or item.period_basis is not reference.period_basis
                or item.actuality is not reference.actuality
                or item.as_of != reference.as_of
                or item.statement_cohort != reference.statement_cohort
                or item.currency != reference.currency
                or evidence_unit_class(item.unit, item.currency) is not FinancialUnit.CURRENCY
                for item in fields.values()
            )
        ):
            raise ValueError("FCF margin signed-capex/cohort semantics mismatch")
        return
    counts = {
        "sma_close_50_v1": 50,
        "sma_close_200_v1": 200,
        "rsi_close_14_simple_average_v1": 15,
        "macd_line_close_12_26_adjust_false_v1": 34,
        "macd_signal_close_12_26_9_adjust_false_v1": 34,
        "macd_histogram_close_12_26_9_adjust_false_v1": 34,
        "latest_volume_to_average_volume_20_v1": 20,
    }
    minimum = counts.get(formula_id)
    if minimum is None:
        raise ValueError("unsupported material formula")
    if len(inputs) < minimum:
        raise ValueError(f"technical formula requires at least {minimum} observations")
    exact_count_formulas = {
        "sma_close_50_v1",
        "sma_close_200_v1",
        "rsi_close_14_simple_average_v1",
    }
    if formula_id in exact_count_formulas and len(inputs) != minimum:
        raise ValueError("technical formula input count is not exact")
    if formula_id == "latest_volume_to_average_volume_20_v1" and len(inputs) != 20:
        raise ValueError("volume ratio requires exactly 20 observations")
    if len({item.as_of for item in inputs}) != len(inputs) or any(
        current.as_of <= previous.as_of
        for previous, current in zip(inputs, inputs[1:], strict=False)
    ):
        raise ValueError("technical evidence dates must be unique and ordered")
    if len({item.object_id for item in inputs}) != 1 or any(
        item.evidence_category is not EvidenceCategory.MARKET
        or item.evidence_purpose != "historical_market_context"
        or item.period != "DAILY"
        or item.period_basis is not FinancialPeriodBasis.DAILY
        for item in inputs
    ):
        raise ValueError("technical evidence series identity is invalid")
    is_volume = formula_id == "latest_volume_to_average_volume_20_v1"
    if is_volume:
        if any(
            item.normalized_field != "volume"
            or item.unit not in {"COUNT", "SHARES"}
            or item.currency is not None
            or _decimal(item.normalized_value) < 0
            for item in inputs
        ):
            raise ValueError("volume evidence field/unit is invalid")
        return
    if any(
        item.normalized_field not in {"close", "adjusted_close"}
        or item.unit != "CURRENCY"
        or not item.currency
        or _decimal(item.normalized_value) <= 0
        for item in inputs
    ):
        raise ValueError("price evidence field/unit is invalid")
    bases = {
        item.technical_price_basis
        or (
            TechnicalPriceBasis.ADJUSTED_CLOSE
            if item.normalized_field == "adjusted_close"
            else TechnicalPriceBasis.RAW_CLOSE
        )
        for item in inputs
    }
    actions = {item.corporate_action_status or CorporateActionStatus.UNASSESSED for item in inputs}
    if (
        len(bases) != 1
        or len(actions) != 1
        or CorporateActionStatus.UNRESOLVED in actions
        or len({item.currency for item in inputs}) != 1
        or len({item.normalized_field for item in inputs}) != 1
    ):
        raise ValueError("price basis/corporate-action/currency series mismatch")
    basis = next(iter(bases))
    field = inputs[0].normalized_field
    if (field == "adjusted_close") is not (basis is TechnicalPriceBasis.ADJUSTED_CLOSE):
        raise ValueError("normalized price field does not match declared basis")


def _recompute(formula_id: str, inputs: Sequence[EvidenceRecord]) -> Decimal:
    if formula_id == "revenue_growth_v1":
        with localcontext() as context:
            context.prec = 28
            prior, current = (_decimal(item.normalized_value) for item in inputs)
            if prior <= 0:
                raise ValueError(REVENUE_GROWTH_VALIDATION_REASON)
            return (current - prior) / prior
    if formula_id == "ebitda_margin_v1":
        with localcontext() as context:
            context.prec = 28
            by_field = {item.normalized_field: _decimal(item.normalized_value) for item in inputs}
            return by_field["ebitda"] / by_field["revenue"]
    if formula_id == "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1":
        with localcontext() as context:
            context.prec = 28
            by_field = {item.normalized_field: _decimal(item.normalized_value) for item in inputs}
            return (by_field["operating_cash_flow"] + by_field["capital_expenditure"]) / by_field[
                "revenue"
            ]
    closes = _values(inputs, "adjusted_close") or _values(inputs, "close")
    if formula_id.startswith("macd_"):
        policy = MACD_DECIMAL_CONTEXT_POLICY
        with localcontext(policy.decimal_context()):
            fast = _ema(closes, policy.fast_span)
            slow = _ema(closes, policy.slow_span)
            line_values = [a - b for a, b in zip(fast, slow, strict=True)]
            signal_values = _ema(line_values, policy.signal_span)
            if formula_id == "macd_line_close_12_26_adjust_false_v1":
                return line_values[-1]
            if formula_id == "macd_signal_close_12_26_9_adjust_false_v1":
                return signal_values[-1]
            return line_values[-1] - signal_values[-1]
    with localcontext() as context:
        context.prec = 50
        if formula_id == "sma_close_50_v1":
            return sum(closes[-50:], Decimal(0)) / Decimal(50)
        if formula_id == "sma_close_200_v1":
            return sum(closes[-200:], Decimal(0)) / Decimal(200)
        if formula_id == "rsi_close_14_simple_average_v1":
            changes = [
                current - previous
                for previous, current in zip(closes[-15:-1], closes[-14:], strict=True)
            ]
            gains = [max(item, Decimal(0)) for item in changes]
            losses = [max(-item, Decimal(0)) for item in changes]
            average_gain = sum(gains, Decimal(0)) / Decimal(14)
            average_loss = sum(losses, Decimal(0)) / Decimal(14)
            if average_loss == 0:
                return Decimal(50) if average_gain == 0 else Decimal(100)
            if average_gain == 0:
                return Decimal(0)
            strength = average_gain / average_loss
            return Decimal(100) - Decimal(100) / (Decimal(1) + strength)
        if formula_id == "latest_volume_to_average_volume_20_v1":
            volume = _values(inputs, "volume")[-20:]
            average = sum(volume, Decimal(0)) / Decimal(20)
            if average == 0:
                raise ValueError("average volume is zero")
            return volume[-1] / average
    raise ValueError(f"unsupported material formula: {formula_id}")


def _ema(values: Sequence[Decimal], span: int) -> list[Decimal]:
    if not values:
        raise ValueError("EMA inputs are empty")
    alpha = Decimal(2) / Decimal(span + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(result[-1] + alpha * (value - result[-1]))
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
