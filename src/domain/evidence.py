from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.base import TimestampedModel
from src.domain.enums import (
    CashFlowSignConvention,
    CorporateActionStatus,
    EvidenceCategory,
    EvidenceStatus,
    FinancialActuality,
    FinancialPeriodBasis,
    TechnicalPriceBasis,
)
from src.domain.financial_semantics import infer_period_basis


class DocumentAuthority(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    discovery_provider: Literal["bocha"]
    original_url: str
    authority: Literal["PRIMARY", "OFFICIAL"]
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_scope: Literal["ORIGINAL_DOCUMENT", "TRANSCRIPT_DISCOVERY_ONLY"]
    period_verified: Literal[False] = False


class EvidenceValidationRequest(BaseModel):
    """Exact request seen by the supported normalized-record validator."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    as_of: date
    expected_period: str | None = None
    fields: tuple[str, ...] = ()
    limit: int = Field(default=20, strict=True, ge=1, le=500)


class EvidenceValidationFreshness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rule_version: Literal["record-as-of-max-age/v1"] = "record-as-of-max-age/v1"
    max_age_days: int = Field(strict=True, ge=0)


class EvidenceValidationProvenance(BaseModel):
    """Bounded ingestion facts; acceptance and permission remain existing authorities."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["evidence-validation/v1"] = "evidence-validation/v1"
    validator_version: Literal["normalized-record-validation/v1"] = (
        "normalized-record-validation/v1"
    )
    request: EvidenceValidationRequest
    freshness: EvidenceValidationFreshness
    mapped_record_index: int = Field(strict=True, ge=0)


class EvidenceRecord(TimestampedModel):
    validation_provenance: EvidenceValidationProvenance | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    document_authority: DocumentAuthority | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    evidence_id: str
    run_id: str
    object_id: str
    provider: str
    source_locator: str | None = None
    producer_task_id: str | None = None
    source_endpoint: str | None = None
    evidence_purpose: str | None = None
    evidence_category: EvidenceCategory = EvidenceCategory.OTHER
    retrieved_at: datetime
    observed_at: datetime | None = None
    provider_timestamp: datetime | None = None
    period: str
    period_basis: FinancialPeriodBasis | None = None
    actuality: FinancialActuality = FinancialActuality.UNKNOWN
    statement_series: str | None = None
    statement_cohort: str | None = None
    technical_price_basis: TechnicalPriceBasis | None = None
    corporate_action_status: CorporateActionStatus | None = None
    cash_flow_sign_convention: CashFlowSignConvention | None = None
    cash_flow_normalization_applied: bool = False
    as_of: date
    raw_artifact_ref: str
    normalized_field: str
    normalized_value: Any
    unit: str
    currency: str | None = None
    snapshot_hash: str
    status: EvidenceStatus

    def model_post_init(self, __context: Any) -> None:
        del __context
        if self.period_basis is None:
            try:
                self.period_basis = infer_period_basis(self.period)
            except ValueError:
                # Non-financial text/symbol evidence can retain an untyped provider period.
                self.period_basis = None
        is_financial_statement = self.evidence_category is EvidenceCategory.FINANCIAL_STATEMENT or (
            self.normalized_field
            in {"revenue", "ebitda", "operating_cash_flow", "capital_expenditure"}
            and self.period_basis in {FinancialPeriodBasis.FY, FinancialPeriodBasis.QUARTER}
        )
        if is_financial_statement and self.provider == "fixture":
            if self.actuality is FinancialActuality.UNKNOWN and self.provider == "fixture":
                self.actuality = FinancialActuality.ACTUAL
            actuality = self.actuality.value
            if self.statement_series is None:
                self.statement_series = (
                    f"{self.provider}:{self.object_id}:{self.currency or 'NONE'}:"
                    f"{self.period_basis.value if self.period_basis else 'UNKNOWN'}:{actuality}"
                )
            if self.statement_cohort is None:
                self.statement_cohort = (
                    f"{self.statement_series}:{self.period}:{self.as_of.isoformat()}"
                )
        if (
            self.normalized_field == "capital_expenditure"
            and self.provider == "fixture"
            and self.cash_flow_sign_convention is None
        ):
            try:
                if Decimal(str(self.normalized_value)) <= 0:
                    self.cash_flow_sign_convention = CashFlowSignConvention.OUTFLOW_NEGATIVE
            except (InvalidOperation, TypeError, ValueError):
                pass


class AcceptedEvidenceBundle(TimestampedModel):
    run_id: str
    records: list[EvidenceRecord]
