from datetime import date
from decimal import Decimal

from src.data.freshness import FreshnessPolicy
from src.data.normalization import normalize_value
from src.data.provider import ProviderRequest
from src.data.validation import ValidationCode, mark_duplicate_conflicts, validate_record
from src.domain.enums import EvidenceStatus


def test_percentage_and_basis_points_normalize_to_ratios() -> None:
    percent = normalize_value("gross margin", 65, "PERCENT")
    basis_points = normalize_value("spread", 125, "BASIS_POINTS")

    assert percent.field == "gross_margin"
    assert percent.value == Decimal("0.65")
    assert percent.unit == "RATIO"
    assert basis_points.value == Decimal("0.0125")


def test_camel_case_provider_field_normalizes_to_snake_case() -> None:
    normalized = normalize_value("grossProfit", 10, "USD")

    assert normalized.field == "gross_profit"


def test_different_values_for_same_canonical_key_are_conflicts() -> None:
    request = ProviderRequest(
        symbol="NVDA",
        dataset="annual_financials",
        as_of=date(2026, 9, 3),
        expected_period="FY2026",
    )
    common = {
        "field": "revenue",
        "period": "FY2026",
        "as_of": "2026-01-25",
        "unit": "USD_BILLION",
    }
    validated = [
        validate_record(
            index,
            {**common, "value": value},
            request,
            FreshnessPolicy(max_age_days=550),
        )
        for index, value in enumerate((215.9, 216.0))
    ]

    resolved = mark_duplicate_conflicts(validated)

    assert all(item.status is EvidenceStatus.CONFLICT for item in resolved)
    assert all(
        ValidationCode.DUPLICATE_CONFLICT in {issue.code for issue in item.issues}
        for item in resolved
    )


def test_different_currencies_for_same_canonical_key_are_conflicts() -> None:
    request = ProviderRequest(
        symbol="NVDA",
        dataset="annual_financials",
        as_of=date(2026, 9, 3),
        expected_period="FY2026",
    )
    validated = [
        validate_record(
            index,
            {
                "field": "revenue",
                "period": "FY2026",
                "as_of": "2026-01-25",
                "unit": currency,
                "value": 100,
            },
            request,
            FreshnessPolicy(max_age_days=550),
        )
        for index, currency in enumerate(("USD", "EUR"))
    ]

    resolved = mark_duplicate_conflicts(validated)

    assert all(item.status is EvidenceStatus.CONFLICT for item in resolved)
