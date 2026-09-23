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


def risk_input_consistency_guard_v1(*, materials, binding_id, input_digest, policy, scope):
    """Bounded exact comparison of already verified selected retained semantics.

    This function does not select, normalize, admit or mutate EvidenceRecords.
    Its caller owns currentness, producer lineage and raw/material verification.
    """
    import re
    from itertools import combinations

    from src.domain.node_binding import BindingDenied, canonical_value, digest

    if len(materials) > policy["max_materials"]:
        raise BindingDenied("RISK_GUARD_BOUND_EXCEEDED")
    seen = {}
    groups = {}
    exclusions = []
    reasons = set()
    dimensions = (
        "object_id", "normalized_field", "period", "as_of", "period_basis", "actuality",
        "statement_series", "statement_cohort", "unit", "currency",
    )
    for material in materials:
        if material.record_id in seen and seen[material.record_id] != material:
            raise BindingDenied("RISK_MATERIAL_ID_COLLISION", material.record_id)
        seen[material.record_id] = material
    for identity, material in sorted(seen.items()):
        if material.kind != "EVIDENCE":
            continue
        value = canonical_value(material.payload_snapshot)
        if value.get("normalized_field") not in {"revenue", "ebitda"}:
            exclusions.append({"evidence_id": identity,
                               "reason": "UNSUPPORTED_FOR_AUTOMATIC_CONFLICT_RESOLUTION_V1"})
            continue
        period = value.get("period", "")
        valid_period = (re.fullmatch(r"FY[0-9]{4}", period)
                        and value.get("period_basis") == "FY") or (
                            re.fullmatch(r"Q[1-4]FY[0-9]{4}", period)
                            and value.get("period_basis") == "QUARTER")
        number = value.get("normalized_value")
        number = str(number) if type(number) is int else number
        valid_number = isinstance(number, str) and re.fullmatch(
            r"-?(0|[1-9][0-9]*)(\.[0-9]+)?", number
        ) and sum(c.isdigit() for c in number) <= 128 and (
            len(number.split(".")[1]) if "." in number else 0
        ) <= 64
        if not (
            valid_period and valid_number and value.get("unit") == "CURRENCY"
            and re.fullmatch(r"[A-Z]{3}", value.get("currency") or "")
            and value.get("actuality") == "ACTUAL"
            and all(value.get(d) is not None and str(value[d]).strip() for d in dimensions)
            and all(value.get(d) is None for d in (
                "technical_price_basis", "corporate_action_status", "cash_flow_sign_convention"))
            and value.get("cash_flow_normalization_applied") is False
        ):
            reasons.add("STRUCTURED_COMPARISON_UNESTABLISHED")
            exclusions.append({"evidence_id": identity,
                               "reason": "STRUCTURED_COMPARISON_UNESTABLISHED"})
            continue
        canonical = number.rstrip("0").rstrip(".") if "." in number else number
        if canonical in {"-0", "0"}:
            canonical = "0"
        key = tuple(value[d] for d in dimensions)
        groups.setdefault(key, []).append((identity, canonical))
    equal = 0
    conflicts = []
    supported = 0
    for key, members in sorted(groups.items()):
        for left, right in combinations(sorted(members), 2):
            supported += 1
            if supported > policy["max_pairs"]:
                raise BindingDenied("RISK_GUARD_BOUND_EXCEEDED")
            if left[1] == right[1]:
                equal += 1
            else:
                reasons.add("UNRESOLVED_STRUCTURED_CONFLICT")
                conflicts.append({"key": dict(zip(dimensions, key, strict=True)),
                                  "evidence_refs": [left[0], right[0]]})
    if policy["required_comparisons"]:
        # No automatic comparison outside the frozen supported domain is promised.
        reasons.add("REQUIRED_COMPARISON_UNSUPPORTED")
    result = {
        "version": "risk_input_consistency_guard_v1", "scope": scope,
        "resolved_input_binding_id": binding_id, "input_digest": input_digest,
        "policy_digest": digest(policy, "risk-input-consistency-policy/v1"),
        "material_set_digest": digest([seen[k] for k in sorted(seen)], "risk-material-set/v1"),
        "input_consistency": "UNSATISFIED" if reasons else "PASS",
        "reason_codes": sorted(reasons), "supported_pair_count": supported,
        "equal_pair_count": equal, "conflicting_pair_count": len(conflicts),
        "conflicts": conflicts, "coverage_exclusions": exclusions,
    }
    return {**result, "guard_digest": digest(result, "risk-input-consistency-guard/v1")}
