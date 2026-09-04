# SPDX-FileCopyrightText: 2024-2026 AI4Finance Foundation
# SPDX-License-Identifier: Apache-2.0

"""Deterministic peer-metric transformation port from pinned FinRobot.

Upstream provenance:
    AI4Finance Foundation, FinRobot, Apache-2.0
    commit d221910096de87579b02f8f0674652bf1a175f51
    finrobot_equity/core/src/modules/market_data_api.py:combine_peer_financial_data

The upstream function combines provider retrieval and pandas pivoting.  This
owned port keeps only the pure period-alignment, pivot, matrix, and aggregation
behavior.  It deliberately has no provider client, peer-discovery logic,
selection policy, projection, or missing-value fill.  Its inputs are already
selected canonical metrics or ACCEPTED peer Evidence joined to an existing
``PeerSelectionDecision``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from src.adapters.finrobot.audit import FINROBOT_PINNED_COMMIT
from src.capabilities.provenance import calculation_source_provenance
from src.domain.base import DomainModel, JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.capability import CapabilityContext, CapabilityDefinition
from src.domain.enums import (
    CalculationStatus,
    CapabilityBackend,
    EvidenceCategory,
    EvidenceStatus,
)
from src.domain.evidence import EvidenceRecord
from src.domain.peer import PeerSelectionDecision

UPSTREAM_PEER_SOURCE = (
    "https://github.com/AI4Finance-Foundation/FinRobot/"
    f"tree/{FINROBOT_PINNED_COMMIT}/"
    "finrobot_equity/core/src/modules/market_data_api.py#combine_peer_financial_data"
)
OWNED_PEER_SOURCE = "src.adapters.finrobot.peer_port"
PORT_VERSION = "1.0.0"


class PeerMetricInputError(ValueError):
    """Raised when peer metric lineage or dimensionality is not usable."""


class PeerPeriodAlignmentError(PeerMetricInputError):
    """Raised when no complete historical period can be aligned without filling."""


class PeerAggregateMethod(StrEnum):
    MEAN = "MEAN"
    MEDIAN = "MEDIAN"
    MIN = "MIN"
    MAX = "MAX"


class SelectedComparableMetric(DomainModel):
    """One canonical metric for a comparable selected outside this module.

    ``selected`` is a literal guard, not a selection result.  The Evidence
    constructor additionally requires a positive existing selection decision.
    This module therefore cannot promote a rejected candidate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    run_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    period: str = Field(min_length=1)
    as_of: date
    value: Decimal
    unit: str = Field(min_length=1)
    currency: str | None = None
    source_evidence_ids: tuple[str, ...] = Field(min_length=1)
    selected: Literal[True] = True
    selection_source: str = Field(min_length=1)

    @field_validator("symbol")
    @classmethod
    def canonical_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("symbol must not be blank")
        return symbol

    @field_validator("metric", "period", "unit", "selection_source")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("canonical metric text fields must not be blank")
        return normalized

    @field_validator("value", mode="before")
    @classmethod
    def finite_value(cls, value: object) -> Decimal:
        return _finite_decimal(value)

    @field_validator("source_evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not evidence_id.strip() for evidence_id in value):
            raise ValueError("source evidence ids must not be blank")
        if len(set(value)) != len(value):
            raise ValueError("source evidence ids must be unique")
        return value

    @model_validator(mode="after")
    def currency_is_explicit(self) -> SelectedComparableMetric:
        if self.currency is not None and not self.currency.strip():
            raise ValueError("currency must be None or a non-blank code")
        return self

    @classmethod
    def from_accepted_evidence(
        cls,
        *,
        symbol: str,
        evidence: EvidenceRecord,
        selection: PeerSelectionDecision,
    ) -> SelectedComparableMetric:
        """Join canonical peer Evidence to an already-approved comparable."""

        canonical_symbol = symbol.strip().upper()
        if evidence.status is not EvidenceStatus.ACCEPTED:
            raise PeerMetricInputError("peer metric Evidence must be ACCEPTED")
        if evidence.evidence_category is not EvidenceCategory.PEER:
            raise PeerMetricInputError("peer metric Evidence must use the PEER category")
        if not selection.selected:
            raise PeerMetricInputError(
                f"peer {selection.candidate_symbol} was not selected by PeerSelectionPolicy"
            )
        if selection.candidate_symbol.strip().upper() != canonical_symbol:
            raise PeerMetricInputError("peer metric symbol does not match selection decision")
        evidence_ids = tuple(dict.fromkeys((evidence.evidence_id, *selection.source_evidence_ids)))
        return cls(
            run_id=evidence.run_id,
            symbol=canonical_symbol,
            metric=evidence.normalized_field,
            period=evidence.period,
            as_of=evidence.as_of,
            value=_finite_decimal(evidence.normalized_value),
            unit=evidence.unit,
            currency=evidence.currency,
            source_evidence_ids=evidence_ids,
            selected=True,
            selection_source=selection.selection_source,
        )


class PeerPeriodAlignmentDTO(DomainModel):
    """Complete historical periods retained without forecasting or filling."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    run_id: str
    symbols: tuple[str, ...]
    metrics: tuple[str, ...]
    included_periods: tuple[str, ...]
    excluded_periods: tuple[str, ...]
    observations: tuple[SelectedComparableMetric, ...]

    @model_validator(mode="after")
    def complete_shape(self) -> PeerPeriodAlignmentDTO:
        if not self.symbols or not self.metrics or not self.included_periods:
            raise ValueError("alignment dimensions must not be empty")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("alignment symbols must be unique")
        if len(set(self.metrics)) != len(self.metrics):
            raise ValueError("alignment metrics must be unique")
        if set(self.included_periods) & set(self.excluded_periods):
            raise ValueError("included and excluded periods must not overlap")
        expected = {
            (symbol, metric, period)
            for symbol in self.symbols
            for metric in self.metrics
            for period in self.included_periods
        }
        actual = {(item.symbol, item.metric, item.period) for item in self.observations}
        if actual != expected or len(self.observations) != len(expected):
            raise ValueError("alignment observations must form a complete unique matrix")
        if any(item.run_id != self.run_id for item in self.observations):
            raise ValueError("alignment observations must belong to its run")
        return self


class PeerMetricMatrixCell(DomainModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    metric: str = Field(min_length=1)
    period: str = Field(min_length=1)
    as_of: date
    value: Decimal
    unit: str = Field(min_length=1)
    currency: str | None = None
    source_evidence_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("value", mode="before")
    @classmethod
    def finite_value(cls, value: object) -> Decimal:
        return _finite_decimal(value)

    @field_validator("source_evidence_ids")
    @classmethod
    def valid_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not evidence_id.strip() for evidence_id in value):
            raise ValueError("peer matrix Evidence ids must not be blank")
        if len(set(value)) != len(value):
            raise ValueError("peer matrix Evidence ids must be unique")
        return value


class PeerMetricMatrixRow(DomainModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    symbol: str
    cells: tuple[PeerMetricMatrixCell, ...]


class PeerMetricMatrixDTO(DomainModel):
    """Stable row/column peer matrix produced by a pure pivot."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    run_id: str
    symbols: tuple[str, ...]
    metrics: tuple[str, ...]
    periods: tuple[str, ...]
    excluded_periods: tuple[str, ...]
    rows: tuple[PeerMetricMatrixRow, ...]
    source_evidence_ids: tuple[str, ...]
    selection_sources: tuple[str, ...]
    upstream_commit: str = FINROBOT_PINNED_COMMIT

    @model_validator(mode="after")
    def validate_matrix(self) -> PeerMetricMatrixDTO:
        if self.upstream_commit != FINROBOT_PINNED_COMMIT:
            raise ValueError("peer matrix upstream commit does not match the approved pin")
        if not self.symbols or not self.metrics or not self.periods:
            raise ValueError("peer matrix dimensions must not be empty")
        if self.symbols != tuple(sorted(set(self.symbols))):
            raise ValueError("peer matrix symbols must be unique and sorted")
        if self.metrics != tuple(sorted(set(self.metrics))):
            raise ValueError("peer matrix metrics must be unique and sorted")
        if len(set(self.periods)) != len(self.periods):
            raise ValueError("peer matrix periods must be unique")
        if tuple(row.symbol for row in self.rows) != self.symbols:
            raise ValueError("peer matrix rows must match its selected symbols")
        expected_columns = {(metric, period) for period in self.periods for metric in self.metrics}
        for row in self.rows:
            actual_columns = {(cell.metric, cell.period) for cell in row.cells}
            if actual_columns != expected_columns or len(row.cells) != len(expected_columns):
                raise ValueError("each peer row must contain one cell per matrix column")
        cell_evidence_ids = tuple(
            dict.fromkeys(
                evidence_id
                for row in self.rows
                for cell in row.cells
                for evidence_id in cell.source_evidence_ids
            )
        )
        if cell_evidence_ids != self.source_evidence_ids:
            raise ValueError("peer matrix Evidence lineage must exactly match its cells")
        if self.selection_sources != tuple(sorted(set(self.selection_sources))) or any(
            not source.strip() for source in self.selection_sources
        ):
            raise ValueError("peer matrix selection sources must be explicit")
        return self

    def cell(self, *, symbol: str, metric: str, period: str) -> PeerMetricMatrixCell:
        canonical_symbol = symbol.strip().upper()
        for row in self.rows:
            if row.symbol != canonical_symbol:
                continue
            for cell in row.cells:
                if cell.metric == metric and cell.period == period:
                    return cell
        raise KeyError((canonical_symbol, metric, period))


def align_peer_periods(
    observations: Sequence[SelectedComparableMetric],
    *,
    required_metrics: Iterable[str] | None = None,
) -> PeerPeriodAlignmentDTO:
    """Retain only periods complete for every selected symbol and metric.

    Missing periods are reported in ``excluded_periods``.  No value is carried
    forward, interpolated, forecast, or synthesized.
    """

    items = _validated_observations(observations)
    symbols = tuple(sorted({item.symbol for item in items}))
    available_metrics = {item.metric for item in items}
    metrics = _normalized_required_metrics(required_metrics, available_metrics)
    by_key = {(item.symbol, item.metric, item.period): item for item in items}
    all_periods = {item.period for item in items if item.metric in metrics}
    ordered_periods = tuple(sorted(all_periods, key=lambda value: _period_key(value, items)))
    included = tuple(
        period
        for period in ordered_periods
        if all((symbol, metric, period) in by_key for symbol in symbols for metric in metrics)
    )
    excluded = tuple(period for period in ordered_periods if period not in included)
    if not included:
        raise PeerPeriodAlignmentError(
            "no complete peer period exists; missing values are not filled or projected"
        )
    retained = tuple(
        sorted(
            (item for item in items if item.metric in metrics and item.period in included),
            key=lambda item: (
                item.symbol,
                included.index(item.period),
                metrics.index(item.metric),
            ),
        )
    )
    return PeerPeriodAlignmentDTO(
        run_id=items[0].run_id,
        symbols=symbols,
        metrics=metrics,
        included_periods=included,
        excluded_periods=excluded,
        observations=retained,
    )


def pivot_peer_metrics(alignment: PeerPeriodAlignmentDTO) -> PeerMetricMatrixDTO:
    """Pivot aligned long-form canonical metrics into a deterministic matrix."""

    by_key = {(item.symbol, item.metric, item.period): item for item in alignment.observations}
    rows: list[PeerMetricMatrixRow] = []
    for symbol in alignment.symbols:
        cells: list[PeerMetricMatrixCell] = []
        for period in alignment.included_periods:
            for metric in alignment.metrics:
                item = by_key[(symbol, metric, period)]
                cells.append(
                    PeerMetricMatrixCell(
                        metric=metric,
                        period=period,
                        as_of=item.as_of,
                        value=item.value,
                        unit=item.unit,
                        currency=item.currency,
                        source_evidence_ids=item.source_evidence_ids,
                    )
                )
        rows.append(PeerMetricMatrixRow(symbol=symbol, cells=tuple(cells)))
    evidence_ids = tuple(
        dict.fromkeys(
            evidence_id
            for item in alignment.observations
            for evidence_id in item.source_evidence_ids
        )
    )
    return PeerMetricMatrixDTO(
        run_id=alignment.run_id,
        symbols=alignment.symbols,
        metrics=alignment.metrics,
        periods=alignment.included_periods,
        excluded_periods=alignment.excluded_periods,
        rows=tuple(rows),
        source_evidence_ids=evidence_ids,
        selection_sources=tuple(sorted({item.selection_source for item in alignment.observations})),
    )


def build_peer_metric_matrix(
    observations: Sequence[SelectedComparableMetric],
    *,
    required_metrics: Iterable[str] | None = None,
) -> PeerMetricMatrixDTO:
    """Align and pivot selected peer metrics without choosing any peer."""

    return pivot_peer_metrics(align_peer_periods(observations, required_metrics=required_metrics))


class PeerMetricAggregationCapability:
    """Aggregate an already-selected, aligned peer matrix into CalculationRecords."""

    definition = CapabilityDefinition(
        capability_id="finrobot_peer_metric_aggregation",
        version=PORT_VERSION,
        name="FinRobot Peer Metric Aggregation Port",
        category="peer_calculation",
        backend=CapabilityBackend.NATIVE,
        input_schema={
            "matrix": "PeerMetricMatrixDTO",
            "methods": "PeerAggregateMethod[]",
            "calculation_id_prefix": "string",
        },
        output_schema={"calculations": "CalculationRecord[]"},
        deterministic=True,
        proof_eligible=True,
        implementation_ref=f"{OWNED_PEER_SOURCE}:PeerMetricAggregationCapability",
        owner="vfas-finrobot-owned-port",
    )

    async def execute(
        self,
        inputs: JsonObject,
        context: CapabilityContext,
    ) -> tuple[CalculationRecord, ...]:
        matrix = inputs.get("matrix")
        if not isinstance(matrix, PeerMetricMatrixDTO):
            raise PeerMetricInputError("matrix must be a PeerMetricMatrixDTO")
        if matrix.run_id != context.run_id:
            raise PeerMetricInputError("peer matrix does not belong to CapabilityContext run")
        if not set(matrix.source_evidence_ids).issubset(context.accepted_evidence_ids):
            raise PeerMetricInputError(
                "peer matrix contains evidence outside CapabilityContext accepted_evidence_ids"
            )
        methods = _aggregate_methods(inputs.get("methods"))
        prefix = inputs.get("calculation_id_prefix")
        if not isinstance(prefix, str) or not prefix.strip():
            raise PeerMetricInputError("calculation_id_prefix must be a non-empty string")

        provenance = calculation_source_provenance(
            __file__,
            source_ref=(
                f"{self.definition.implementation_ref}; upstream={UPSTREAM_PEER_SOURCE}; "
                "license=Apache-2.0; behavior=pivot-and-aggregation-only"
            ),
        )
        calculations: list[CalculationRecord] = []
        for period in matrix.periods:
            for metric in matrix.metrics:
                cells = tuple(
                    matrix.cell(symbol=symbol, metric=metric, period=period)
                    for symbol in matrix.symbols
                )
                _require_compatible_dimensions(cells, metric=metric, period=period)
                for method in methods:
                    output = _aggregate(tuple(cell.value for cell in cells), method)
                    evidence_ids = list(
                        dict.fromkeys(
                            evidence_id
                            for cell in cells
                            for evidence_id in cell.source_evidence_ids
                        )
                    )
                    calculations.append(
                        CalculationRecord(
                            calculation_id=(
                                f"{prefix.strip()}:{method.value.lower()}:{metric}:{period}"
                            ),
                            run_id=context.run_id,
                            task_id=context.task_id,
                            capability_id=self.definition.capability_id,
                            capability_version=self.definition.version,
                            formula_id=f"peer_{method.value.lower()}_v1",
                            input_evidence_ids=evidence_ids,
                            input_values_snapshot={
                                "peer_values": {
                                    symbol: str(cell.value)
                                    for symbol, cell in zip(matrix.symbols, cells, strict=True)
                                }
                            },
                            parameters={
                                "method": method.value,
                                "metric": metric,
                                "period": period,
                                "peer_symbols": list(matrix.symbols),
                                "peer_count": len(cells),
                                "currency": cells[0].currency,
                                "excluded_periods": list(matrix.excluded_periods),
                                "missing_value_policy": "EXCLUDE_INCOMPLETE_PERIOD_NO_FILL",
                                "projection_policy": "PROHIBITED",
                            },
                            output_value=output,
                            output_unit=(
                                cells[0].currency
                                if cells[0].unit == "CURRENCY" and cells[0].currency
                                else cells[0].unit
                            ),
                            status=CalculationStatus.PASS,
                            implementation_hash=provenance.code_hash,
                            code_hash=provenance.code_hash,
                            source_ref=provenance.source_ref,
                            runtime_version=provenance.runtime_version,
                        )
                    )
        return tuple(calculations)


def _validated_observations(
    observations: Sequence[SelectedComparableMetric],
) -> tuple[SelectedComparableMetric, ...]:
    if not isinstance(observations, (list, tuple)) or not observations:
        raise PeerMetricInputError("selected peer metric observations are required")
    if any(not isinstance(item, SelectedComparableMetric) for item in observations):
        raise PeerMetricInputError("observations must contain only SelectedComparableMetric values")
    items = tuple(observations)
    run_ids = {item.run_id for item in items}
    if len(run_ids) != 1:
        raise PeerMetricInputError("peer metrics must belong to one run")
    keys = [(item.symbol, item.metric, item.period) for item in items]
    if len(set(keys)) != len(keys):
        raise PeerMetricInputError("duplicate peer metric cell")
    return items


def _normalized_required_metrics(
    required_metrics: Iterable[str] | None,
    available_metrics: set[str],
) -> tuple[str, ...]:
    if required_metrics is None:
        return tuple(sorted(available_metrics))
    if isinstance(required_metrics, str):
        raise PeerMetricInputError("required_metrics must be an iterable of metric names")
    normalized = tuple(dict.fromkeys(metric.strip() for metric in required_metrics))
    if not normalized or any(not metric for metric in normalized):
        raise PeerMetricInputError("required_metrics must contain non-blank metric names")
    missing = set(normalized) - available_metrics
    if missing:
        raise PeerMetricInputError(
            f"required peer metrics are unavailable: {', '.join(sorted(missing))}"
        )
    return tuple(sorted(normalized))


def _period_key(
    period: str,
    observations: Sequence[SelectedComparableMetric],
) -> tuple[date, str]:
    dates = [item.as_of for item in observations if item.period == period]
    return (max(dates), period)


def _aggregate_methods(value: object) -> tuple[PeerAggregateMethod, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise PeerMetricInputError("methods must be a non-empty list or tuple")
    try:
        methods = tuple(
            item if isinstance(item, PeerAggregateMethod) else PeerAggregateMethod(str(item))
            for item in value
        )
    except ValueError as exc:
        raise PeerMetricInputError("unsupported peer aggregation method") from exc
    if len(set(methods)) != len(methods):
        raise PeerMetricInputError("aggregation methods must be unique")
    return methods


def _require_compatible_dimensions(
    cells: Sequence[PeerMetricMatrixCell],
    *,
    metric: str,
    period: str,
) -> None:
    dimensions = {(cell.unit, cell.currency) for cell in cells}
    if len(dimensions) != 1:
        raise PeerMetricInputError(
            f"peer values for {metric}/{period} do not share one unit and currency"
        )


def _aggregate(values: tuple[Decimal, ...], method: PeerAggregateMethod) -> Decimal:
    if not values:
        raise PeerMetricInputError("cannot aggregate an empty peer set")
    ordered = tuple(sorted(values))
    with localcontext() as context:
        context.prec = 50
        if method is PeerAggregateMethod.MEAN:
            return sum(values, start=Decimal(0)) / Decimal(len(values))
        if method is PeerAggregateMethod.MEDIAN:
            middle = len(ordered) // 2
            if len(ordered) % 2:
                return ordered[middle]
            return (ordered[middle - 1] + ordered[middle]) / Decimal(2)
        if method is PeerAggregateMethod.MIN:
            return ordered[0]
        return ordered[-1]


def _finite_decimal(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise PeerMetricInputError("peer metric value must be numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PeerMetricInputError("peer metric value must be numeric") from exc
    if not number.is_finite():
        raise PeerMetricInputError("peer metric value must be finite")
    return number
