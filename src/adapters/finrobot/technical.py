# SPDX-FileCopyrightText: 2024-2026 AI4Finance Foundation
# SPDX-License-Identifier: Apache-2.0

"""Owned, deterministic technical-indicator port inspired by pinned FinRobot.

Upstream provenance:
    AI4Finance Foundation, FinRobot, Apache-2.0
    commit d221910096de87579b02f8f0674652bf1a175f51
    finrobot_equity/core/src/modules/market_data_api.py:get_technical_indicators

This is a clean owned port of the pure formulas only.  It deliberately excludes
the upstream FMP/YFinance fetch, API keys, pandas/numpy dependency, broad error
handling, heuristic labels, and report orchestration.  Formula choices that were
implicit or inconsistent upstream are versioned explicitly here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from typing import Literal
from uuid import uuid4

from pydantic import Field

from src.adapters.finrobot.audit import FINROBOT_PINNED_COMMIT
from src.capabilities.provenance import calculation_source_provenance
from src.domain.base import DomainModel, JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.capability import CapabilityContext, CapabilityDefinition
from src.domain.enums import (
    CalculationStatus,
    CapabilityBackend,
    CorporateActionStatus,
    EvidenceCategory,
    EvidenceStatus,
    TechnicalPriceBasis,
)
from src.domain.evidence import EvidenceRecord
from src.domain.macd_policy import MACD_DECIMAL_CONTEXT_POLICY

UPSTREAM_TECHNICAL_SOURCE = (
    "https://github.com/AI4Finance-Foundation/FinRobot/"
    f"tree/{FINROBOT_PINNED_COMMIT}/"
    "finrobot_equity/core/src/modules/market_data_api.py#get_technical_indicators"
)
OWNED_TECHNICAL_SOURCE = "src.adapters.finrobot.technical"
PORT_VERSION = "1.0.0"


class HistoricalPriceEvidenceError(ValueError):
    pass


class InsufficientHistoryError(HistoricalPriceEvidenceError):
    pass


class ZeroAverageVolumeError(HistoricalPriceEvidenceError):
    pass


@dataclass(frozen=True, slots=True)
class HistoricalPricePoint:
    as_of: date
    close: Decimal
    volume: Decimal
    close_evidence_id: str
    volume_evidence_id: str
    price_unit: str
    currency: str | None
    price_basis: TechnicalPriceBasis
    corporate_action_status: CorporateActionStatus


@dataclass(frozen=True, slots=True)
class MACDValue:
    line: Decimal
    signal: Decimal
    histogram: Decimal


class TechnicalIndicatorJudgment(DomainModel):
    """Versioned interpretation kept separate from deterministic calculations."""

    judgment_id: str
    run_id: str
    task_id: str
    judgment_type: Literal["rsi_state", "macd_state", "moving_average_state"]
    value: Literal["OVERBOUGHT", "OVERSOLD", "BULLISH", "BEARISH", "NEUTRAL"]
    evidence_ids: list[str] = Field(default_factory=list)
    calculation_ids: list[str] = Field(default_factory=list)
    model: str = "finrobot-technical-threshold-policy-v1"
    skill_version: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    requires_review: bool = True


def ordered_accepted_price_points(
    evidence: Sequence[EvidenceRecord],
) -> tuple[HistoricalPricePoint, ...]:
    """Validate and pair an already ordered daily close/volume Evidence stream."""

    if not evidence:
        raise InsufficientHistoryError("historical price evidence is empty")
    seen_ids: set[str] = set()
    grouped: dict[date, dict[str, EvidenceRecord]] = {}
    date_order: list[date] = []
    run_id: str | None = None
    object_id: str | None = None
    previous_date: date | None = None
    for record in evidence:
        if not isinstance(record, EvidenceRecord):
            raise HistoricalPriceEvidenceError(
                "history must contain only normalized EvidenceRecord values"
            )
        if record.evidence_id in seen_ids:
            raise HistoricalPriceEvidenceError("historical evidence ids must be unique")
        seen_ids.add(record.evidence_id)
        if record.status is not EvidenceStatus.ACCEPTED:
            raise HistoricalPriceEvidenceError(f"evidence {record.evidence_id} is not ACCEPTED")
        if record.evidence_category is not EvidenceCategory.MARKET:
            raise HistoricalPriceEvidenceError(
                f"evidence {record.evidence_id} is not MARKET evidence"
            )
        if record.evidence_purpose != "historical_market_context":
            raise HistoricalPriceEvidenceError(
                f"evidence {record.evidence_id} is not historical price evidence"
            )
        if record.period != "DAILY":
            raise HistoricalPriceEvidenceError(
                f"evidence {record.evidence_id} is not DAILY history"
            )
        if record.normalized_field not in {"close", "adjusted_close", "volume"}:
            raise HistoricalPriceEvidenceError(
                f"unsupported historical field: {record.normalized_field}"
            )
        if run_id is None:
            run_id, object_id = record.run_id, record.object_id
        elif record.run_id != run_id or record.object_id != object_id:
            raise HistoricalPriceEvidenceError(
                "historical evidence must belong to one run and one research object"
            )
        if previous_date is not None and record.as_of < previous_date:
            raise HistoricalPriceEvidenceError(
                "historical evidence must be ordered oldest-to-newest"
            )
        if not date_order or date_order[-1] != record.as_of:
            date_order.append(record.as_of)
        previous_date = record.as_of
        fields = grouped.setdefault(record.as_of, {})
        grouped_field = (
            "close" if record.normalized_field == "adjusted_close" else record.normalized_field
        )
        existing = fields.get(grouped_field)
        if existing is not None:
            if record.normalized_field == "adjusted_close":
                fields[grouped_field] = record
                continue
            if existing.normalized_field == "adjusted_close":
                continue
            raise HistoricalPriceEvidenceError(
                f"duplicate {grouped_field} evidence for {record.as_of.isoformat()}"
            )
        fields[grouped_field] = record

    points: list[HistoricalPricePoint] = []
    expected_currency: str | None = None
    expected_price_unit: str | None = None
    for observed_date in date_order:
        fields = grouped[observed_date]
        if set(fields) != {"close", "volume"}:
            raise HistoricalPriceEvidenceError(
                f"close and volume evidence are both required for {observed_date.isoformat()}"
            )
        close = fields["close"]
        volume = fields["volume"]
        if close.unit != "CURRENCY" or not close.currency:
            raise HistoricalPriceEvidenceError("close evidence must use a currency unit")
        if volume.unit not in {"COUNT", "SHARES"} or volume.currency is not None:
            raise HistoricalPriceEvidenceError("volume evidence must use COUNT or SHARES")
        if expected_currency is None:
            expected_currency = close.currency
            expected_price_unit = close.unit
        elif close.currency != expected_currency or close.unit != expected_price_unit:
            raise HistoricalPriceEvidenceError("close evidence currency/unit must be consistent")
        close_value = _finite_decimal(close.normalized_value, field="close")
        volume_value = _finite_decimal(volume.normalized_value, field="volume")
        if close_value <= 0:
            raise HistoricalPriceEvidenceError("close values must be positive")
        if volume_value < 0:
            raise HistoricalPriceEvidenceError("volume values cannot be negative")
        basis = close.technical_price_basis or (
            TechnicalPriceBasis.ADJUSTED_CLOSE
            if close.normalized_field == "adjusted_close"
            else TechnicalPriceBasis.RAW_CLOSE
        )
        action_status = close.corporate_action_status or CorporateActionStatus.UNASSESSED
        if action_status is CorporateActionStatus.UNRESOLVED:
            raise HistoricalPriceEvidenceError(
                "unresolved corporate action blocks technical indicator release"
            )
        points.append(
            HistoricalPricePoint(
                as_of=observed_date,
                close=close_value,
                volume=volume_value,
                close_evidence_id=close.evidence_id,
                volume_evidence_id=volume.evidence_id,
                price_unit=close.unit,
                currency=close.currency,
                price_basis=basis,
                corporate_action_status=action_status,
            )
        )
    return tuple(points)


def simple_moving_average(values: Sequence[Decimal], *, window: int) -> Decimal:
    if window < 1:
        raise ValueError("window must be positive")
    if len(values) < window:
        raise InsufficientHistoryError(f"SMA{window} requires at least {window} values")
    with localcontext() as context:
        context.prec = 50
        return sum(values[-window:], start=Decimal(0)) / Decimal(window)


def relative_strength_index(values: Sequence[Decimal], *, period: int = 14) -> Decimal:
    """Return RSI from the latest ``period`` price changes using simple averages."""

    if period < 1:
        raise ValueError("period must be positive")
    if len(values) < period + 1:
        raise InsufficientHistoryError(f"RSI{period} requires at least {period + 1} closing prices")
    recent = values[-(period + 1) :]
    changes = [
        current - previous for previous, current in zip(recent[:-1], recent[1:], strict=True)
    ]
    gains = [max(change, Decimal(0)) for change in changes]
    losses = [max(-change, Decimal(0)) for change in changes]
    with localcontext() as context:
        context.prec = 50
        average_gain = sum(gains, start=Decimal(0)) / Decimal(period)
        average_loss = sum(losses, start=Decimal(0)) / Decimal(period)
        if average_loss == 0:
            return Decimal(50) if average_gain == 0 else Decimal(100)
        if average_gain == 0:
            return Decimal(0)
        relative_strength = average_gain / average_loss
        return Decimal(100) - (Decimal(100) / (Decimal(1) + relative_strength))


def exponential_moving_average(values: Sequence[Decimal], *, span: int) -> tuple[Decimal, ...]:
    """Recursive EMA with ``adjust=False``, seeded from the first observation."""

    if span < 1:
        raise ValueError("span must be positive")
    if not values:
        raise InsufficientHistoryError("EMA requires at least one value")
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        return _exponential_moving_average(values, span=span)


def _exponential_moving_average(
    values: Sequence[Decimal], *, span: int
) -> tuple[Decimal, ...]:
    """Compute an EMA inside the caller's explicit local Decimal context."""

    alpha = Decimal(2) / Decimal(span + 1)
    output = [values[0]]
    for value in values[1:]:
        output.append(output[-1] + alpha * (value - output[-1]))
    return tuple(output)


def moving_average_convergence_divergence(
    values: Sequence[Decimal],
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MACDValue:
    if not 0 < fast < slow:
        raise ValueError("MACD spans must satisfy 0 < fast < slow")
    if signal < 1:
        raise ValueError("MACD signal span must be positive")
    warmup = slow + signal - 1
    if len(values) < warmup:
        raise InsufficientHistoryError(
            f"MACD requires at least {warmup} closing prices for signal warm-up"
        )
    policy = MACD_DECIMAL_CONTEXT_POLICY
    with localcontext(policy.decimal_context()):
        fast_ema = _exponential_moving_average(values, span=fast)
        slow_ema = _exponential_moving_average(values, span=slow)
        lines = tuple(
            fast_value - slow_value
            for fast_value, slow_value in zip(fast_ema, slow_ema, strict=True)
        )
        signal_values = _exponential_moving_average(lines, span=signal)
        line = lines[-1]
        signal_value = signal_values[-1]
        histogram = line - signal_value
    return MACDValue(line=line, signal=signal_value, histogram=histogram)


def latest_volume_ratio(values: Sequence[Decimal], *, window: int = 20) -> Decimal:
    if window < 1:
        raise ValueError("window must be positive")
    if len(values) < window:
        raise InsufficientHistoryError(
            f"volume ratio {window} requires at least {window} volume values"
        )
    with localcontext() as context:
        context.prec = 50
        average = sum(values[-window:], start=Decimal(0)) / Decimal(window)
        if average == 0:
            raise ZeroAverageVolumeError("average volume must not be zero")
        return values[-1] / average


class SMA50Capability:
    definition = CapabilityDefinition(
        capability_id="technical_sma_50",
        version=PORT_VERSION,
        name="50-Day Simple Moving Average",
        category="technical_indicator",
        backend=CapabilityBackend.NATIVE,
        input_schema={"history": "ordered ACCEPTED daily close/volume EvidenceRecord[]"},
        output_schema={"calculation": "CalculationRecord"},
        deterministic=True,
        implementation_ref=f"{OWNED_TECHNICAL_SOURCE}:SMA50Capability",
        owner="vfas-finrobot-owned-port",
    )

    async def execute(self, inputs: JsonObject, context: CapabilityContext) -> CalculationRecord:
        points = _points_from_inputs(inputs, context)
        window = 50
        value = simple_moving_average([point.close for point in points], window=window)
        return _calculation(
            inputs=inputs,
            context=context,
            definition=self.definition,
            formula_id="sma_close_50_v1",
            evidence_ids=[point.close_evidence_id for point in points[-window:]],
            input_snapshot={
                "window": window,
                "observation_count": window,
                "first_as_of": points[-window].as_of.isoformat(),
                "last_as_of": points[-1].as_of.isoformat(),
                **_technical_input_metadata(points),
            },
            output=value,
            unit=_price_output_unit(points),
        )


class SMA200Capability:
    definition = CapabilityDefinition(
        capability_id="technical_sma_200",
        version=PORT_VERSION,
        name="200-Day Simple Moving Average",
        category="technical_indicator",
        backend=CapabilityBackend.NATIVE,
        input_schema={"history": "ordered ACCEPTED daily close/volume EvidenceRecord[]"},
        output_schema={"calculation": "CalculationRecord"},
        deterministic=True,
        implementation_ref=f"{OWNED_TECHNICAL_SOURCE}:SMA200Capability",
        owner="vfas-finrobot-owned-port",
    )

    async def execute(self, inputs: JsonObject, context: CapabilityContext) -> CalculationRecord:
        points = _points_from_inputs(inputs, context)
        window = 200
        value = simple_moving_average([point.close for point in points], window=window)
        return _calculation(
            inputs=inputs,
            context=context,
            definition=self.definition,
            formula_id="sma_close_200_v1",
            evidence_ids=[point.close_evidence_id for point in points[-window:]],
            input_snapshot={
                "window": window,
                "observation_count": window,
                "first_as_of": points[-window].as_of.isoformat(),
                "last_as_of": points[-1].as_of.isoformat(),
                **_technical_input_metadata(points),
            },
            output=value,
            unit=_price_output_unit(points),
        )


class RSI14Capability:
    definition = CapabilityDefinition(
        capability_id="technical_rsi_14",
        version=PORT_VERSION,
        name="14-Period Relative Strength Index",
        category="technical_indicator",
        backend=CapabilityBackend.NATIVE,
        input_schema={"history": "ordered ACCEPTED daily close/volume EvidenceRecord[]"},
        output_schema={"calculation": "CalculationRecord"},
        deterministic=True,
        implementation_ref=f"{OWNED_TECHNICAL_SOURCE}:RSI14Capability",
        owner="vfas-finrobot-owned-port",
    )

    async def execute(self, inputs: JsonObject, context: CapabilityContext) -> CalculationRecord:
        points = _points_from_inputs(inputs, context)
        period = 14
        value = relative_strength_index([point.close for point in points], period=period)
        relevant = points[-(period + 1) :]
        return _calculation(
            inputs=inputs,
            context=context,
            definition=self.definition,
            formula_id="rsi_close_14_simple_average_v1",
            evidence_ids=[point.close_evidence_id for point in relevant],
            input_snapshot={
                "period": period,
                "price_change_count": period,
                "zero_gain_and_loss_policy": "50_index_points",
                "first_as_of": relevant[0].as_of.isoformat(),
                "last_as_of": relevant[-1].as_of.isoformat(),
                "rsi_method": "simple_average_not_wilder",
                **_technical_input_metadata(relevant),
            },
            output=value,
            unit="INDEX_POINTS",
        )


class MACD12269Capability:
    definition = CapabilityDefinition(
        capability_id="technical_macd_12_26_9",
        version=PORT_VERSION,
        name="MACD 12/26/9",
        category="technical_indicator",
        backend=CapabilityBackend.NATIVE,
        input_schema={"history": "ordered ACCEPTED daily close/volume EvidenceRecord[]"},
        output_schema={"calculations": "CalculationRecord[3]"},
        deterministic=True,
        implementation_ref=f"{OWNED_TECHNICAL_SOURCE}:MACD12269Capability",
        owner="vfas-finrobot-owned-port",
    )

    async def execute(
        self, inputs: JsonObject, context: CapabilityContext
    ) -> tuple[CalculationRecord, CalculationRecord, CalculationRecord]:
        points = _points_from_inputs(inputs, context)
        values = [point.close for point in points]
        policy = MACD_DECIMAL_CONTEXT_POLICY
        result = moving_average_convergence_divergence(
            values,
            fast=policy.fast_span,
            slow=policy.slow_span,
            signal=policy.signal_span,
        )
        evidence_ids = [point.close_evidence_id for point in points]
        base_id = _calculation_id(inputs)
        common = {
            "context": context,
            "definition": self.definition,
            "evidence_ids": evidence_ids,
            "input_snapshot": {
                "decimal_context_policy_id": policy.policy_id,
                "decimal_precision": policy.precision,
                "decimal_rounding": policy.rounding,
                "fast_span": policy.fast_span,
                "slow_span": policy.slow_span,
                "signal_span": policy.signal_span,
                "ema_adjust": policy.ema_adjust,
                "ema_seed": policy.ema_seed,
                "observation_count": len(points),
                "first_as_of": points[0].as_of.isoformat(),
                "last_as_of": points[-1].as_of.isoformat(),
                "warmup_required": policy.warmup_required,
                "warmup_satisfied": len(points) >= policy.warmup_required,
                **_technical_input_metadata(points),
            },
            "unit": _price_output_unit(points),
        }
        return (
            _calculation(
                inputs={"calculation_id": f"{base_id}:line"},
                formula_id="macd_line_close_12_26_adjust_false_v1",
                output=result.line,
                **common,
            ),
            _calculation(
                inputs={"calculation_id": f"{base_id}:signal"},
                formula_id="macd_signal_close_12_26_9_adjust_false_v1",
                output=result.signal,
                **common,
            ),
            _calculation(
                inputs={"calculation_id": f"{base_id}:histogram"},
                formula_id="macd_histogram_close_12_26_9_adjust_false_v1",
                output=result.histogram,
                **common,
            ),
        )


class VolumeRatio20Capability:
    definition = CapabilityDefinition(
        capability_id="technical_volume_ratio_20",
        version=PORT_VERSION,
        name="Latest Volume to 20-Day Average Volume Ratio",
        category="technical_indicator",
        backend=CapabilityBackend.NATIVE,
        input_schema={"history": "ordered ACCEPTED daily close/volume EvidenceRecord[]"},
        output_schema={"calculation": "CalculationRecord"},
        deterministic=True,
        implementation_ref=f"{OWNED_TECHNICAL_SOURCE}:VolumeRatio20Capability",
        owner="vfas-finrobot-owned-port",
    )

    async def execute(self, inputs: JsonObject, context: CapabilityContext) -> CalculationRecord:
        points = _points_from_inputs(inputs, context)
        window = 20
        value = latest_volume_ratio([point.volume for point in points], window=window)
        return _calculation(
            inputs=inputs,
            context=context,
            definition=self.definition,
            formula_id="latest_volume_to_average_volume_20_v1",
            evidence_ids=[point.volume_evidence_id for point in points[-window:]],
            input_snapshot={
                "window": window,
                "average_includes_latest_observation": True,
                "first_as_of": points[-window].as_of.isoformat(),
                "last_as_of": points[-1].as_of.isoformat(),
                **_technical_input_metadata(points[-window:]),
            },
            output=value,
            unit="RATIO",
        )


class TechnicalIndicatorJudgmentService:
    """Apply versioned interpretation policy without changing numeric records."""

    policy_version = "finrobot-technical-threshold-policy-v1"

    def rsi(
        self,
        calculation: CalculationRecord,
        *,
        skill_version: str,
    ) -> TechnicalIndicatorJudgment:
        if calculation.formula_id != "rsi_close_14_simple_average_v1":
            raise ValueError("RSI judgment requires an RSI14 CalculationRecord")
        value = _finite_decimal(calculation.output_value, field="RSI")
        label: Literal["OVERBOUGHT", "OVERSOLD", "BULLISH", "BEARISH", "NEUTRAL"]
        if value > 70:
            label = "OVERBOUGHT"
        elif value < 30:
            label = "OVERSOLD"
        elif value > 55:
            label = "BULLISH"
        elif value < 45:
            label = "BEARISH"
        else:
            label = "NEUTRAL"
        return _judgment(
            calculation,
            judgment_type="rsi_state",
            value=label,
            skill_version=skill_version,
            limitation="Threshold label is an interpretation, not a market fact or calculation.",
        )

    def macd(
        self,
        line: CalculationRecord,
        signal: CalculationRecord,
        *,
        skill_version: str,
    ) -> TechnicalIndicatorJudgment:
        if not line.formula_id.startswith("macd_line_") or not signal.formula_id.startswith(
            "macd_signal_"
        ):
            raise ValueError("MACD judgment requires line and signal CalculationRecords")
        if line.run_id != signal.run_id or line.task_id != signal.task_id:
            raise ValueError("MACD calculations must belong to the same task")
        if line.input_values_snapshot.get("warmup_satisfied") is not True:
            raise ValueError("MACD judgment requires a completed 12/26/9 warm-up window")
        line_value = _finite_decimal(line.output_value, field="MACD line")
        signal_value = _finite_decimal(signal.output_value, field="MACD signal")
        label: Literal["BULLISH", "BEARISH", "NEUTRAL"]
        if line_value > signal_value:
            label = "BULLISH"
        elif line_value < signal_value:
            label = "BEARISH"
        else:
            label = "NEUTRAL"
        return TechnicalIndicatorJudgment(
            judgment_id=f"JUDG-{uuid4()}",
            run_id=line.run_id,
            task_id=line.task_id,
            judgment_type="macd_state",
            value=label,
            evidence_ids=list(
                dict.fromkeys([*line.input_evidence_ids, *signal.input_evidence_ids])
            ),
            calculation_ids=[line.calculation_id, signal.calculation_id],
            model=self.policy_version,
            skill_version=skill_version,
            limitations=["Crossover label is an interpretation, not a market fact or calculation."],
            requires_review=True,
        )


def _points_from_inputs(
    inputs: JsonObject,
    context: CapabilityContext,
) -> tuple[HistoricalPricePoint, ...]:
    history = inputs.get("history")
    if not isinstance(history, (list, tuple)):
        raise HistoricalPriceEvidenceError("history must be an ordered EvidenceRecord sequence")
    points = ordered_accepted_price_points(history)
    if any(
        record.run_id != context.run_id for record in history if isinstance(record, EvidenceRecord)
    ):
        raise HistoricalPriceEvidenceError("history does not belong to CapabilityContext run")
    allowed = set(context.accepted_evidence_ids)
    evidence_ids = {
        evidence_id
        for point in points
        for evidence_id in (point.close_evidence_id, point.volume_evidence_id)
    }
    if not evidence_ids.issubset(allowed):
        raise HistoricalPriceEvidenceError(
            "history contains evidence outside CapabilityContext accepted_evidence_ids"
        )
    return points


def _calculation(
    *,
    inputs: JsonObject,
    context: CapabilityContext,
    definition: CapabilityDefinition,
    formula_id: str,
    evidence_ids: list[str],
    input_snapshot: JsonObject,
    output: Decimal,
    unit: str,
) -> CalculationRecord:
    provenance = calculation_source_provenance(
        __file__,
        source_ref=(
            f"{definition.implementation_ref}; upstream={UPSTREAM_TECHNICAL_SOURCE}; "
            "license=Apache-2.0"
        ),
    )
    return CalculationRecord(
        calculation_id=_calculation_id(inputs),
        run_id=context.run_id,
        task_id=context.task_id,
        capability_id=definition.capability_id,
        capability_version=definition.version,
        formula_id=formula_id,
        input_evidence_ids=evidence_ids,
        input_values_snapshot=input_snapshot,
        output_value=output,
        output_unit=unit,
        status=CalculationStatus.PASS,
        implementation_hash=provenance.code_hash,
        code_hash=provenance.code_hash,
        source_ref=provenance.source_ref,
        runtime_version=provenance.runtime_version,
    )


def _calculation_id(inputs: JsonObject) -> str:
    value = inputs.get("calculation_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("calculation_id must be a non-empty string")
    return value


def _price_output_unit(points: Sequence[HistoricalPricePoint]) -> str:
    return points[-1].currency or points[-1].price_unit


def _technical_input_metadata(points: Sequence[HistoricalPricePoint]) -> JsonObject:
    bases = {point.price_basis for point in points}
    statuses = {point.corporate_action_status for point in points}
    if len(bases) != 1 or len(statuses) != 1:
        raise HistoricalPriceEvidenceError(
            "technical lookback must use one price basis and corporate-action status"
        )
    return {
        "technical_price_basis": next(iter(bases)).value,
        "corporate_action_status": next(iter(statuses)).value,
    }


def _finite_decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise HistoricalPriceEvidenceError(f"{field} value must be numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise HistoricalPriceEvidenceError(f"{field} value must be numeric") from exc
    if not number.is_finite():
        raise HistoricalPriceEvidenceError(f"{field} value must be finite")
    return number


def _judgment(
    calculation: CalculationRecord,
    *,
    judgment_type: Literal["rsi_state", "macd_state", "moving_average_state"],
    value: Literal["OVERBOUGHT", "OVERSOLD", "BULLISH", "BEARISH", "NEUTRAL"],
    skill_version: str,
    limitation: str,
) -> TechnicalIndicatorJudgment:
    return TechnicalIndicatorJudgment(
        judgment_id=f"JUDG-{uuid4()}",
        run_id=calculation.run_id,
        task_id=calculation.task_id,
        judgment_type=judgment_type,
        value=value,
        evidence_ids=list(calculation.input_evidence_ids),
        calculation_ids=[calculation.calculation_id],
        model=TechnicalIndicatorJudgmentService.policy_version,
        skill_version=skill_version,
        limitations=[limitation],
        requires_review=True,
    )
