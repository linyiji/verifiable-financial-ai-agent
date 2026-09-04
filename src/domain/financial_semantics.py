from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from src.domain.base import DomainModel, JsonObject
from src.domain.enums import (
    CorporateActionStatus,
    FinancialActuality,
    FinancialPeriodBasis,
    FinancialUnit,
    MaterialCalculationDispositionStatus,
    SourceCoverageStatus,
    TechnicalPriceBasis,
)
from src.domain.macd_policy import MACD_DECIMAL_CONTEXT_POLICY

_FY = re.compile(r"^FY(?P<year>\d{4})$")
_QUARTER = re.compile(r"^Q(?P<quarter>[1-4])FY(?P<year>\d{4})$")


def canonical_decimal(value: object) -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError("financial metric value must be numeric")
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("financial metric value must be decimal-compatible") from exc
    if not decimal.is_finite():
        raise ValueError("financial metric value must be finite")
    return format(decimal, "f")


def infer_period_basis(period: str) -> FinancialPeriodBasis:
    normalized = period.strip().upper()
    if _FY.fullmatch(normalized):
        return FinancialPeriodBasis.FY
    if _QUARTER.fullmatch(normalized):
        return FinancialPeriodBasis.QUARTER
    try:
        return FinancialPeriodBasis(normalized)
    except ValueError as exc:
        raise ValueError(f"unsupported financial period: {period}") from exc


def adjacent_financial_periods(prior: str, current: str) -> bool:
    prior_fy = _FY.fullmatch(prior.strip().upper())
    current_fy = _FY.fullmatch(current.strip().upper())
    if prior_fy and current_fy:
        return int(current_fy.group("year")) == int(prior_fy.group("year")) + 1
    prior_quarter = _QUARTER.fullmatch(prior.strip().upper())
    current_quarter = _QUARTER.fullmatch(current.strip().upper())
    if prior_quarter and current_quarter:
        return (
            prior_quarter.group("quarter") == current_quarter.group("quarter")
            and int(current_quarter.group("year")) == int(prior_quarter.group("year")) + 1
        )
    return False


def evidence_unit_class(unit: str, currency: str | None) -> FinancialUnit | None:
    normalized = unit.strip().upper()
    if currency:
        normalized_currency = currency.strip().upper()
        if normalized in {"CURRENCY", normalized_currency} or normalized.startswith(
            f"{normalized_currency}_"
        ):
            return FinancialUnit.CURRENCY
    aliases = {
        "RATIO": FinancialUnit.RATIO,
        "PERCENT": FinancialUnit.PERCENT,
        "COUNT": FinancialUnit.COUNT,
        "SHARES": FinancialUnit.SHARES,
        "INDEX": FinancialUnit.INDEX,
        "INDEX_POINTS": FinancialUnit.INDEX,
        "MULTIPLE": FinancialUnit.MULTIPLE,
    }
    return aliases.get(normalized)


class FinancialSemanticModel(DomainModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        del deep
        payload = self.model_dump(mode="python", round_trip=True)
        if update:
            payload.update(update)
        return type(self).model_validate(payload)


class TechnicalMethodMetadata(FinancialSemanticModel):
    method: str
    parameters: tuple[tuple[str, str], ...] = ()
    observation_count: int | None = Field(default=None, ge=1)
    warmup_required: int | None = Field(default=None, ge=1)
    warmup_satisfied: bool | None = None
    first_as_of: date | None = None
    last_as_of: date | None = None
    is_wilder: bool | None = None
    ema_adjust: bool | None = None
    ema_seed: str | None = None
    fast_span: int | None = Field(default=None, ge=1)
    slow_span: int | None = Field(default=None, ge=1)
    signal_span: int | None = Field(default=None, ge=1)
    decimal_context_policy_id: str | None = None
    decimal_precision: int | None = Field(default=None, ge=1)
    decimal_rounding: str | None = None
    technical_price_basis: TechnicalPriceBasis | None = None

    @field_validator("method")
    @classmethod
    def method_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("technical method must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_macd_policy(self) -> Self:
        if self.method != "MACD_EMA_12_26_9_FIRST_OBSERVATION_SEED":
            return self
        policy = MACD_DECIMAL_CONTEXT_POLICY
        expected = {
            "decimal_context_policy_id": policy.policy_id,
            "decimal_precision": policy.precision,
            "decimal_rounding": policy.rounding,
            "ema_adjust": policy.ema_adjust,
            "ema_seed": policy.ema_seed,
            "fast_span": policy.fast_span,
            "slow_span": policy.slow_span,
            "signal_span": policy.signal_span,
            "warmup_required": policy.warmup_required,
        }
        actual = {key: getattr(self, key) for key in expected}
        if actual != expected:
            raise ValueError(
                "MACD methodology metadata does not match its versioned Decimal policy"
            )
        if self.observation_count is None or self.warmup_satisfied is None:
            raise ValueError("MACD methodology metadata requires observation and warm-up status")
        if self.technical_price_basis is None:
            raise ValueError("MACD methodology metadata requires technical_price_basis")
        return self


class ReleasedFinancialMetric(FinancialSemanticModel):
    """Typed, Decimal-safe financial value at the release boundary."""

    metric_id: str
    calculation_id: str
    name: str
    canonical_value: str
    canonical_unit: FinancialUnit
    display_value: str
    display_unit: str
    period: str
    period_basis: FinancialPeriodBasis
    actuality: FinancialActuality = FinancialActuality.ACTUAL
    as_of: date
    currency: str | None = None
    formula_id: str
    capability_id: str
    evidence_ids: tuple[str, ...]
    method_metadata: TechnicalMethodMetadata | None = None
    technical_price_basis: TechnicalPriceBasis | None = None
    corporate_action_status: CorporateActionStatus | None = None
    corporate_action_guard_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @field_validator("canonical_value")
    @classmethod
    def normalize_canonical_value(cls, value: str) -> str:
        return canonical_decimal(value)

    @field_validator(
        "metric_id",
        "calculation_id",
        "name",
        "display_value",
        "display_unit",
        "period",
        "formula_id",
        "capability_id",
    )
    @classmethod
    def reject_blank_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("released metric text fields must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        if infer_period_basis(self.period) is not self.period_basis:
            raise ValueError("released metric period and period_basis disagree")
        if len(self.evidence_ids) != len(set(self.evidence_ids)) or not self.evidence_ids:
            raise ValueError("released metric evidence_ids must be non-empty and unique")
        if self.canonical_unit is FinancialUnit.CURRENCY and not self.currency:
            raise ValueError("currency metrics require an explicit currency")
        if self.currency is not None and not self.currency.strip():
            raise ValueError("currency must be omitted or non-blank")
        if self.technical_price_basis is TechnicalPriceBasis.RAW_CLOSE:
            if self.corporate_action_status is None:
                raise ValueError("RAW_CLOSE metrics require corporate-action status")
            if self.corporate_action_status is CorporateActionStatus.UNRESOLVED:
                raise ValueError("unresolved corporate action cannot be released")
            if (
                self.corporate_action_status is CorporateActionStatus.UNASSESSED
                and not self.limitations
            ):
                raise ValueError("unassessed RAW_CLOSE metrics require an explicit limitation")
            if (
                self.corporate_action_status
                in {CorporateActionStatus.NONE_DETECTED, CorporateActionStatus.RESOLVED}
                and not self.corporate_action_guard_refs
            ):
                raise ValueError("corporate-action conclusions require evidence references")
        if (
            self.technical_price_basis is TechnicalPriceBasis.ADJUSTED_CLOSE
            and self.corporate_action_status is not CorporateActionStatus.RESOLVED
        ):
            raise ValueError("ADJUSTED_CLOSE metrics require resolved adjustment status")
        if (
            self.technical_price_basis is TechnicalPriceBasis.ADJUSTED_CLOSE
            and not self.corporate_action_guard_refs
        ):
            raise ValueError("ADJUSTED_CLOSE metrics require adjustment evidence refs")
        if self.formula_id.startswith("macd_") and (
            self.method_metadata is None
            or self.method_metadata.technical_price_basis is not self.technical_price_basis
        ):
            raise ValueError("MACD release requires matching versioned methodology metadata")
        return self

    def semantic_payload(self) -> JsonObject:
        return {
            "metric_id": self.metric_id,
            "calculation_id": self.calculation_id,
            "canonical_value": self.canonical_value,
            "canonical_unit": self.canonical_unit.value,
            "period": self.period,
            "period_basis": self.period_basis.value,
            "actuality": self.actuality.value,
            "as_of": self.as_of.isoformat(),
            "currency": self.currency,
            "formula_id": self.formula_id,
            "capability_id": self.capability_id,
            "evidence_ids": list(self.evidence_ids),
            "name": self.name,
            "display_value": self.display_value,
            "display_unit": self.display_unit,
            "method_metadata": (
                self.method_metadata.model_dump(mode="json") if self.method_metadata else None
            ),
            "limitations": list(self.limitations),
            "technical_price_basis": (
                self.technical_price_basis.value if self.technical_price_basis else None
            ),
            "corporate_action_status": (
                self.corporate_action_status.value if self.corporate_action_status else None
            ),
            "corporate_action_guard_refs": list(self.corporate_action_guard_refs),
        }


class MaterialFinancialClaim(FinancialSemanticModel):
    claim_id: str
    run_id: str
    claim_type: str
    statement: str
    metric_id: str
    value: str
    unit: FinancialUnit
    period: str
    period_basis: FinancialPeriodBasis
    actuality: FinancialActuality = FinancialActuality.ACTUAL
    as_of: date
    currency: str | None = None
    calculation_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    judgment_refs: tuple[str, ...] = ()

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        return canonical_decimal(value)

    @model_validator(mode="after")
    def validate_support(self) -> Self:
        if not self.statement.strip() or not self.claim_id.strip() or not self.metric_id.strip():
            raise ValueError("material claim identity and statement must not be blank")
        if infer_period_basis(self.period) is not self.period_basis:
            raise ValueError("material claim period and period_basis disagree")
        if not self.calculation_refs or not self.evidence_refs:
            raise ValueError("material claims require calculation and evidence support")
        if len(self.calculation_refs) != len(set(self.calculation_refs)):
            raise ValueError("material claim calculation_refs must be unique")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("material claim evidence_refs must be unique")
        if self.unit is FinancialUnit.CURRENCY and not self.currency:
            raise ValueError("currency claims require an explicit currency")
        return self


class MaterialCalculationDisposition(FinancialSemanticModel):
    calculation_id: str
    metric_id: str | None = None
    status: MaterialCalculationDispositionStatus
    reason: str | None = None

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        if not self.calculation_id.strip():
            raise ValueError("calculation_id must not be blank")
        if self.metric_id is not None and not self.metric_id.strip():
            raise ValueError("metric_id must be omitted or non-blank")
        if self.reason is not None and not self.reason.strip():
            raise ValueError("reason must be omitted or non-blank")
        if self.status is MaterialCalculationDispositionStatus.REPORTABLE:
            if not self.metric_id or self.reason is not None:
                raise ValueError("REPORTABLE calculations require metric_id and no reason")
        elif not self.reason or self.metric_id is not None:
            raise ValueError("NON_REPORTABLE calculations require reason and no metric_id")
        return self


class SourceCoverage(FinancialSemanticModel):
    status: SourceCoverageStatus
    evidence_ids: tuple[str, ...] = ()
    reason: str | None = None
    limitation: str | None = None

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        if self.status is SourceCoverageStatus.AVAILABLE:
            if not self.evidence_ids or self.reason is not None:
                raise ValueError("AVAILABLE coverage requires evidence and no reason")
        elif not self.reason or not self.limitation:
            raise ValueError("unavailable coverage requires reason and limitation")
        return self


class ResearchSourceCoverage(FinancialSemanticModel):
    news: SourceCoverage
    transcript: SourceCoverage
    limitations: tuple[str, ...] = ()


def metric_semantics_hash(
    metrics: list[ReleasedFinancialMetric] | tuple[ReleasedFinancialMetric, ...],
) -> str:
    payload = [
        metric.semantic_payload() for metric in sorted(metrics, key=lambda item: item.metric_id)
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
