import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


class NormalizationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NormalizedValue:
    field: str
    value: Decimal | str | bool
    unit: str
    currency: str | None


_SCALES = {
    "THOUSAND": Decimal("1000"),
    "MILLION": Decimal("1000000"),
    "BILLION": Decimal("1000000000"),
}
_SCALED_CURRENCY = re.compile(r"^(?P<currency>[A-Z]{3})_(?P<scale>THOUSAND|MILLION|BILLION)$")


def normalize_field(field: Any) -> str:
    if not isinstance(field, str) or not field.strip():
        raise NormalizationError("field must be a non-empty string")
    snake_candidate = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", field.strip())
    normalized = re.sub(r"[^a-z0-9]+", "_", snake_candidate.lower()).strip("_")
    if not normalized:
        raise NormalizationError("field has no canonical characters")
    return normalized


def normalize_period(period: Any) -> str:
    if not isinstance(period, str) or not period.strip():
        raise NormalizationError("period must be a non-empty string")
    return period.strip().upper()


def normalize_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise NormalizationError("as_of must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise NormalizationError("as_of must be an ISO date") from exc


def normalize_value(field: Any, value: Any, unit: Any, currency: Any = None) -> NormalizedValue:
    canonical_field = normalize_field(field)
    if not isinstance(unit, str) or not unit.strip():
        raise NormalizationError("unit must be a non-empty string")
    canonical_unit = unit.strip().upper()
    canonical_currency = _normalize_currency(currency)

    scaled_currency = _SCALED_CURRENCY.fullmatch(canonical_unit)
    if scaled_currency:
        numeric = _decimal(value)
        unit_currency = scaled_currency.group("currency")
        if canonical_currency is not None and canonical_currency != unit_currency:
            raise NormalizationError("unit currency conflicts with explicit currency")
        return NormalizedValue(
            field=canonical_field,
            value=numeric * _SCALES[scaled_currency.group("scale")],
            unit="CURRENCY",
            currency=unit_currency,
        )

    if canonical_unit == "PERCENT":
        return NormalizedValue(
            field=canonical_field,
            value=_decimal(value) / Decimal("100"),
            unit="RATIO",
            currency=None,
        )

    if canonical_unit == "BASIS_POINTS":
        return NormalizedValue(
            field=canonical_field,
            value=_decimal(value) / Decimal("10000"),
            unit="RATIO",
            currency=None,
        )

    if canonical_unit == "RATIO":
        return NormalizedValue(
            field=canonical_field,
            value=_decimal(value),
            unit="RATIO",
            currency=None,
        )

    if re.fullmatch(r"[A-Z]{3}", canonical_unit):
        if canonical_currency is not None and canonical_currency != canonical_unit:
            raise NormalizationError("unit currency conflicts with explicit currency")
        return NormalizedValue(
            field=canonical_field,
            value=_decimal(value),
            unit="CURRENCY",
            currency=canonical_unit,
        )

    if canonical_unit in {"COUNT", "SHARES"}:
        return NormalizedValue(
            field=canonical_field,
            value=_decimal(value),
            unit=canonical_unit,
            currency=None,
        )

    if canonical_unit in {"TEXT", "SYMBOL"}:
        if not isinstance(value, str) or not value.strip():
            raise NormalizationError(f"{canonical_unit.lower()} value must be a non-empty string")
        text = value.strip()
        if canonical_unit == "SYMBOL":
            text = text.upper()
        return NormalizedValue(
            field=canonical_field,
            value=text,
            unit=canonical_unit,
            currency=None,
        )

    if canonical_unit == "BOOLEAN":
        if not isinstance(value, bool):
            raise NormalizationError("boolean value must be true or false")
        return NormalizedValue(
            field=canonical_field,
            value=value,
            unit="BOOLEAN",
            currency=None,
        )

    raise NormalizationError(f"unsupported unit: {canonical_unit}")


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise NormalizationError("value must be numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise NormalizationError("value must be numeric") from exc
    if not number.is_finite():
        raise NormalizationError("value must be finite")
    return number


def _normalize_currency(currency: Any) -> str | None:
    if currency is None:
        return None
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Za-z]{3}", currency.strip()):
        raise NormalizationError("currency must be a three-letter code")
    return currency.strip().upper()
