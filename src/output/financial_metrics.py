from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, NamedTuple

from src.domain.base import JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.enums import (
    CorporateActionStatus,
    FinancialPeriodBasis,
    FinancialUnit,
    MaterialCalculationDispositionStatus,
    SourceCoverageStatus,
    TechnicalPriceBasis,
)
from src.domain.evidence import EvidenceRecord
from src.domain.financial_semantics import (
    MaterialCalculationDisposition,
    MaterialFinancialClaim,
    ReleasedFinancialMetric,
    ResearchSourceCoverage,
    SourceCoverage,
    TechnicalMethodMetadata,
    canonical_decimal,
)
from src.domain.macd_policy import MACD_DECIMAL_CONTEXT_POLICY

MATERIAL_FORMULAS = (
    "revenue_growth_v1",
    "ebitda_margin_v1",
    "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1",
    "sma_close_50_v1",
    "sma_close_200_v1",
    "rsi_close_14_simple_average_v1",
    "macd_line_close_12_26_adjust_false_v1",
    "macd_signal_close_12_26_9_adjust_false_v1",
    "macd_histogram_close_12_26_9_adjust_false_v1",
    "latest_volume_to_average_volume_20_v1",
)


class _FormulaSpec(NamedTuple):
    metric_code: str
    name: str
    unit: FinancialUnit
    display_unit: str


_FORMULAS = {
    "revenue_growth_v1": _FormulaSpec("revenue_growth", "Revenue Growth", FinancialUnit.RATIO, "%"),
    "ebitda_margin_v1": _FormulaSpec("ebitda_margin", "EBITDA Margin", FinancialUnit.RATIO, "%"),
    "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1": _FormulaSpec(
        "free_cash_flow_margin", "Free Cash Flow Margin", FinancialUnit.RATIO, "%"
    ),
    "sma_close_50_v1": _FormulaSpec(
        "sma_50", "50-Day Simple Moving Average", FinancialUnit.CURRENCY, "currency"
    ),
    "sma_close_200_v1": _FormulaSpec(
        "sma_200", "200-Day Simple Moving Average", FinancialUnit.CURRENCY, "currency"
    ),
    "rsi_close_14_simple_average_v1": _FormulaSpec(
        "rsi_14_simple", "RSI 14 (Simple Average, not Wilder)", FinancialUnit.INDEX, "index points"
    ),
    "macd_line_close_12_26_adjust_false_v1": _FormulaSpec(
        "macd_line", "MACD Line 12/26 EMA", FinancialUnit.CURRENCY, "currency"
    ),
    "macd_signal_close_12_26_9_adjust_false_v1": _FormulaSpec(
        "macd_signal", "MACD Signal 9 EMA", FinancialUnit.CURRENCY, "currency"
    ),
    "macd_histogram_close_12_26_9_adjust_false_v1": _FormulaSpec(
        "macd_histogram", "MACD Histogram", FinancialUnit.CURRENCY, "currency"
    ),
    "latest_volume_to_average_volume_20_v1": _FormulaSpec(
        "volume_ratio_20", "Volume Ratio 20", FinancialUnit.RATIO, "x"
    ),
}


def build_material_financial_release(
    *,
    run_id: str,
    evidence: Sequence[EvidenceRecord],
    calculations: Sequence[CalculationRecord],
    judgments: Sequence[JsonObject],
    unavailable_formulas: frozenset[str] = frozenset(),
) -> tuple[
    tuple[ReleasedFinancialMetric, ...],
    tuple[MaterialFinancialClaim, ...],
    tuple[MaterialCalculationDisposition, ...],
]:
    by_formula: dict[str, CalculationRecord] = {}
    for calculation in calculations:
        if calculation.formula_id not in _FORMULAS:
            continue
        if calculation.formula_id in by_formula:
            raise ValueError(f"duplicate material formula: {calculation.formula_id}")
        by_formula[calculation.formula_id] = calculation
    missing = set(MATERIAL_FORMULAS) - by_formula.keys()
    extra = by_formula.keys() - set(MATERIAL_FORMULAS)
    if missing != unavailable_formulas or extra:
        raise ValueError(
            f"material calculation set mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    evidence_by_id = {record.evidence_id: record for record in evidence}
    metrics: list[ReleasedFinancialMetric] = []
    claims: list[MaterialFinancialClaim] = []
    dispositions: list[MaterialCalculationDisposition] = []
    for formula_id in MATERIAL_FORMULAS:
        if formula_id in unavailable_formulas:
            continue
        calculation = by_formula[formula_id]
        if calculation.run_id != run_id or not calculation.implementation_hash:
            raise ValueError("material calculation lacks run or implementation identity")
        inputs = _material_inputs(calculation, evidence_by_id)
        metric = _metric(calculation, inputs)
        judgment_refs = tuple(
            str(item["judgment_id"])
            for item in judgments
            if calculation.calculation_id in item.get("calculation_ids", [])
            and isinstance(item.get("judgment_id"), str)
        )
        claim = MaterialFinancialClaim(
            claim_id=f"CLAIM-{calculation.calculation_id}",
            run_id=run_id,
            claim_type="MATERIAL_FINANCIAL_METRIC",
            statement=_claim_statement(metric),
            metric_id=metric.metric_id,
            value=metric.canonical_value,
            unit=metric.canonical_unit,
            period=metric.period,
            period_basis=metric.period_basis,
            actuality=metric.actuality,
            as_of=metric.as_of,
            currency=metric.currency,
            calculation_refs=(calculation.calculation_id,),
            evidence_refs=metric.evidence_ids,
            judgment_refs=judgment_refs,
        )
        metrics.append(metric)
        claims.append(claim)
        dispositions.append(
            MaterialCalculationDisposition(
                calculation_id=calculation.calculation_id,
                metric_id=metric.metric_id,
                status=MaterialCalculationDispositionStatus.REPORTABLE,
            )
        )
    return tuple(metrics), tuple(claims), tuple(dispositions)


def build_research_source_coverage(result: Mapping[str, Any]) -> ResearchSourceCoverage:
    raw = result.get("source_coverage")
    mapping = raw if isinstance(raw, Mapping) else {}
    return ResearchSourceCoverage(
        news=_source_coverage("news", mapping.get("news")),
        transcript=_source_coverage("transcript", mapping.get("transcript")),
        limitations=tuple(
            item
            for item in (
                _coverage_limitation("news", mapping.get("news")),
                _coverage_limitation("transcript", mapping.get("transcript")),
            )
            if item is not None
        ),
    )


def _source_coverage(source: str, value: Any) -> SourceCoverage:
    details = value if isinstance(value, Mapping) else {}
    try:
        status = SourceCoverageStatus(str(details.get("status", "EMPTY")))
    except ValueError:
        status = SourceCoverageStatus.ERROR
    evidence_ids = tuple(
        item for item in details.get("accepted_evidence_ids", []) if isinstance(item, str) and item
    )
    if status is SourceCoverageStatus.AVAILABLE and not evidence_ids:
        status = SourceCoverageStatus.EMPTY
    if status is SourceCoverageStatus.AVAILABLE:
        return SourceCoverage(status=status, evidence_ids=evidence_ids)
    reason = str(details.get("error_code") or f"{source.upper()}_{status.value}")
    limitation = f"{source.title()} unavailable: {reason}."
    return SourceCoverage(
        status=status,
        evidence_ids=(),
        reason=reason,
        limitation=limitation,
    )


def _coverage_limitation(source: str, value: Any) -> str | None:
    coverage = _source_coverage(source, value)
    return coverage.limitation


def _material_inputs(
    calculation: CalculationRecord,
    evidence_by_id: Mapping[str, EvidenceRecord],
) -> tuple[EvidenceRecord, ...]:
    try:
        inputs = tuple(
            evidence_by_id[evidence_id] for evidence_id in calculation.input_evidence_ids
        )
    except KeyError as exc:
        raise ValueError("material calculation references missing evidence") from exc
    if not inputs or any(record.run_id != calculation.run_id for record in inputs):
        raise ValueError("material calculation evidence belongs to another run")
    return inputs


def _metric(
    calculation: CalculationRecord,
    inputs: tuple[EvidenceRecord, ...],
) -> ReleasedFinancialMetric:
    spec = _FORMULAS[calculation.formula_id]
    technical = calculation.formula_id not in MATERIAL_FORMULAS[:3]
    anchor = max(inputs, key=lambda item: (item.as_of, item.evidence_id))
    if technical:
        period = "DAILY"
        period_basis = FinancialPeriodBasis.DAILY
    else:
        period = anchor.period
        if anchor.period_basis is None:
            raise ValueError("material statement calculation lacks period basis")
        period_basis = anchor.period_basis
    currency_values = {item.currency for item in inputs if item.currency}
    if len(currency_values) > 1:
        raise ValueError("material calculation has inconsistent currency")
    currency = next(iter(currency_values), None)
    if spec.unit is FinancialUnit.CURRENCY and currency is None:
        raise ValueError("currency material metric lacks currency")
    canonical = canonical_decimal(calculation.output_value)
    display = _display_value(canonical, spec)
    method = _method_metadata(calculation, inputs) if technical else None
    price_inputs = [item for item in inputs if item.normalized_field in {"close", "adjusted_close"}]
    price_basis = None
    action_status = None
    action_guard_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    if price_inputs:
        bases = {
            item.technical_price_basis
            or (
                TechnicalPriceBasis.ADJUSTED_CLOSE
                if item.normalized_field == "adjusted_close"
                else TechnicalPriceBasis.RAW_CLOSE
            )
            for item in price_inputs
        }
        statuses = {
            item.corporate_action_status or CorporateActionStatus.UNASSESSED
            for item in price_inputs
        }
        if len(bases) != 1 or len(statuses) != 1:
            raise ValueError("technical metric inputs must use one basis and action status")
        price_basis = next(iter(bases))
        action_status = next(iter(statuses))
        if action_status is CorporateActionStatus.UNRESOLVED:
            raise ValueError("unresolved corporate action blocks technical metric release")
        if action_status in {
            CorporateActionStatus.NONE_DETECTED,
            CorporateActionStatus.RESOLVED,
        }:
            action_guard_refs = tuple(item.evidence_id for item in price_inputs)
        if (
            price_basis is TechnicalPriceBasis.RAW_CLOSE
            and action_status is CorporateActionStatus.UNASSESSED
        ):
            limitations = (
                "Technical indicator uses RAW_CLOSE; corporate-action adjustment was not "
                "available for the accepted lookback window.",
            )
    return ReleasedFinancialMetric(
        metric_id=f"METRIC-{calculation.calculation_id}",
        calculation_id=calculation.calculation_id,
        name=spec.name,
        canonical_value=canonical,
        canonical_unit=spec.unit,
        display_value=display,
        display_unit=currency if spec.display_unit == "currency" else spec.display_unit,
        period=period,
        period_basis=period_basis,
        actuality=anchor.actuality,
        as_of=anchor.as_of,
        currency=currency,
        formula_id=calculation.formula_id,
        capability_id=calculation.capability_id,
        evidence_ids=tuple(calculation.input_evidence_ids),
        method_metadata=method,
        technical_price_basis=price_basis,
        corporate_action_status=action_status,
        corporate_action_guard_refs=action_guard_refs,
        limitations=limitations,
    )


def _display_value(value: str, spec: _FormulaSpec) -> str:
    decimal = Decimal(value)
    if spec.display_unit == "%":
        decimal *= Decimal(100)
    return format(decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _method_metadata(
    calculation: CalculationRecord,
    inputs: tuple[EvidenceRecord, ...],
) -> TechnicalMethodMetadata:
    snapshot = calculation.input_values_snapshot
    first = min(item.as_of for item in inputs)
    last = max(item.as_of for item in inputs)
    count = int(snapshot.get("observation_count") or len({item.as_of for item in inputs}))
    if calculation.formula_id == "rsi_close_14_simple_average_v1":
        return TechnicalMethodMetadata(
            method="RSI_SIMPLE_AVERAGE_NOT_WILDER",
            parameters=(("period", "14"),),
            observation_count=count,
            warmup_required=15,
            warmup_satisfied=count >= 15,
            first_as_of=first,
            last_as_of=last,
            is_wilder=False,
        )
    if calculation.formula_id.startswith("macd_"):
        policy = MACD_DECIMAL_CONTEXT_POLICY
        price_bases = {
            item.technical_price_basis
            or (
                TechnicalPriceBasis.ADJUSTED_CLOSE
                if item.normalized_field == "adjusted_close"
                else TechnicalPriceBasis.RAW_CLOSE
            )
            for item in inputs
        }
        if len(price_bases) != 1:
            raise ValueError("MACD methodology requires one technical price basis")
        return TechnicalMethodMetadata(
            method="MACD_EMA_12_26_9_FIRST_OBSERVATION_SEED",
            parameters=(
                ("fast", str(policy.fast_span)),
                ("slow", str(policy.slow_span)),
                ("signal", str(policy.signal_span)),
            ),
            observation_count=count,
            warmup_required=policy.warmup_required,
            warmup_satisfied=count >= policy.warmup_required,
            first_as_of=first,
            last_as_of=last,
            ema_adjust=policy.ema_adjust,
            ema_seed=policy.ema_seed,
            fast_span=policy.fast_span,
            slow_span=policy.slow_span,
            signal_span=policy.signal_span,
            decimal_context_policy_id=policy.policy_id,
            decimal_precision=policy.precision,
            decimal_rounding=policy.rounding,
            technical_price_basis=next(iter(price_bases)),
        )
    window = int(snapshot.get("window") or 1)
    return TechnicalMethodMetadata(
        method=(
            "SIMPLE_MOVING_AVERAGE" if calculation.formula_id.startswith("sma_") else "VOLUME_RATIO"
        ),
        parameters=(("window", str(window)),),
        observation_count=count,
        warmup_required=window,
        warmup_satisfied=count >= window,
        first_as_of=first,
        last_as_of=last,
    )


def _claim_statement(metric: ReleasedFinancialMetric) -> str:
    display = f"{metric.display_value}{metric.display_unit}"
    if metric.capability_id == "revenue_growth":
        direction = "increased" if Decimal(metric.canonical_value) >= 0 else "decreased"
        return f"Revenue {direction} {display} YoY for {metric.period}."
    return f"{metric.name} was {display} for {metric.period} as of {metric.as_of.isoformat()}."
