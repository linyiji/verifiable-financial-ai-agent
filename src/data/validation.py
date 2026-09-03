from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.data.freshness import FreshnessPolicy, FreshnessStatus
from src.data.normalization import (
    NormalizationError,
    NormalizedValue,
    normalize_date,
    normalize_period,
    normalize_value,
)
from src.data.provider import ProviderRequest
from src.domain.base import JsonObject
from src.domain.enums import EvidenceStatus


class ValidationCode(StrEnum):
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_VALUE = "INVALID_VALUE"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    STALE = "STALE"
    FUTURE_DATED = "FUTURE_DATED"
    DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: ValidationCode
    message: str


@dataclass(frozen=True, slots=True)
class ValidatedRecord:
    raw_index: int
    field: str | None
    period: str | None
    as_of: Any
    normalized: NormalizedValue | None
    status: EvidenceStatus
    issues: tuple[ValidationIssue, ...]


_REQUIRED_FIELDS = ("field", "period", "as_of", "value", "unit")


def validate_record(
    raw_index: int,
    record: JsonObject,
    request: ProviderRequest,
    freshness_policy: FreshnessPolicy,
) -> ValidatedRecord:
    missing = tuple(field for field in _REQUIRED_FIELDS if record.get(field) is None)
    if missing:
        return ValidatedRecord(
            raw_index=raw_index,
            field=None,
            period=None,
            as_of=None,
            normalized=None,
            status=EvidenceStatus.REJECTED,
            issues=(
                ValidationIssue(
                    ValidationCode.MISSING_FIELD,
                    f"missing required fields: {', '.join(missing)}",
                ),
            ),
        )

    try:
        period = normalize_period(record["period"])
        record_as_of = normalize_date(record["as_of"])
        normalized = normalize_value(
            record["field"],
            record["value"],
            record["unit"],
            record.get("currency"),
        )
    except NormalizationError as exc:
        return ValidatedRecord(
            raw_index=raw_index,
            field=str(record.get("field")),
            period=str(record.get("period")),
            as_of=record.get("as_of"),
            normalized=None,
            status=EvidenceStatus.REJECTED,
            issues=(ValidationIssue(ValidationCode.INVALID_VALUE, str(exc)),),
        )

    issues: list[ValidationIssue] = []
    status = EvidenceStatus.ACCEPTED
    if request.expected_period and period != request.expected_period.upper():
        status = EvidenceStatus.CONFLICT
        issues.append(
            ValidationIssue(
                ValidationCode.PERIOD_MISMATCH,
                f"expected {request.expected_period.upper()}, received {period}",
            )
        )

    freshness = freshness_policy.evaluate(record_as_of, request.as_of)
    if freshness is FreshnessStatus.STALE:
        status = EvidenceStatus.REJECTED
        issues.append(ValidationIssue(ValidationCode.STALE, "record exceeds freshness policy"))
    elif freshness is FreshnessStatus.FUTURE:
        status = EvidenceStatus.REJECTED
        issues.append(
            ValidationIssue(ValidationCode.FUTURE_DATED, "record is after requested as_of")
        )

    return ValidatedRecord(
        raw_index=raw_index,
        field=normalized.field,
        period=period,
        as_of=record_as_of,
        normalized=normalized,
        status=status,
        issues=tuple(issues),
    )


def mark_duplicate_conflicts(records: list[ValidatedRecord]) -> list[ValidatedRecord]:
    groups: dict[tuple[object, ...], list[ValidatedRecord]] = {}
    for record in records:
        if record.normalized is None:
            continue
        key = (record.field, record.period, record.as_of)
        groups.setdefault(key, []).append(record)

    conflicting_indices = {
        record.raw_index
        for group in groups.values()
        if len(
            {
                (
                    record.normalized.value,
                    record.normalized.unit,
                    record.normalized.currency,
                )
                for record in group
                if record.normalized
            }
        )
        > 1
        for record in group
    }
    if not conflicting_indices:
        return records

    output: list[ValidatedRecord] = []
    for record in records:
        if record.raw_index not in conflicting_indices or record.status is EvidenceStatus.REJECTED:
            output.append(record)
            continue
        output.append(
            ValidatedRecord(
                raw_index=record.raw_index,
                field=record.field,
                period=record.period,
                as_of=record.as_of,
                normalized=record.normalized,
                status=EvidenceStatus.CONFLICT,
                issues=record.issues
                + (
                    ValidationIssue(
                        ValidationCode.DUPLICATE_CONFLICT,
                        "same canonical key has different values",
                    ),
                ),
            )
        )
    return output
