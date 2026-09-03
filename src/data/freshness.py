from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class FreshnessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    FUTURE = "FUTURE"


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    max_age_days: int

    def evaluate(self, record_as_of: date, requested_as_of: date) -> FreshnessStatus:
        age = (requested_as_of - record_as_of).days
        if age < 0:
            return FreshnessStatus.FUTURE
        if age > self.max_age_days:
            return FreshnessStatus.STALE
        return FreshnessStatus.FRESH


DEFAULT_FRESHNESS_POLICIES: dict[str, FreshnessPolicy] = {
    "company_profile": FreshnessPolicy(max_age_days=365),
    "annual_financials": FreshnessPolicy(max_age_days=550),
    "quarterly_financials": FreshnessPolicy(max_age_days=150),
    "income": FreshnessPolicy(max_age_days=550),
    "income_statement": FreshnessPolicy(max_age_days=550),
    "balance_sheet": FreshnessPolicy(max_age_days=550),
    "balance": FreshnessPolicy(max_age_days=550),
    "cash_flow": FreshnessPolicy(max_age_days=550),
    "cashflow": FreshnessPolicy(max_age_days=550),
    "market_price": FreshnessPolicy(max_age_days=2),
    "quote": FreshnessPolicy(max_age_days=2),
    "historical_prices": FreshnessPolicy(max_age_days=30),
    "historical": FreshnessPolicy(max_age_days=30),
    "news": FreshnessPolicy(max_age_days=7),
    "peer_multiples": FreshnessPolicy(max_age_days=30),
    "peers": FreshnessPolicy(max_age_days=30),
    "analyst_recommendations": FreshnessPolicy(max_age_days=120),
    "analyst": FreshnessPolicy(max_age_days=120),
    "transcript": FreshnessPolicy(max_age_days=550),
}


def policy_for(dataset: str) -> FreshnessPolicy:
    return DEFAULT_FRESHNESS_POLICIES.get(dataset, FreshnessPolicy(max_age_days=365))
