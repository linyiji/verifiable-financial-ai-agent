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
    "market_price": FreshnessPolicy(max_age_days=2),
    "news": FreshnessPolicy(max_age_days=7),
    "peer_multiples": FreshnessPolicy(max_age_days=30),
}


def policy_for(dataset: str) -> FreshnessPolicy:
    return DEFAULT_FRESHNESS_POLICIES.get(dataset, FreshnessPolicy(max_age_days=365))
