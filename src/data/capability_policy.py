"""Finite data capability authority. No learned ranking and no model-granted access."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DataOutcome(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE_ENTITLEMENT = "UNAVAILABLE_ENTITLEMENT"
    UNAVAILABLE_PROVIDER = "UNAVAILABLE_PROVIDER"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    FAILED = "FAILED"


class DataCapabilityPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    capability_id: str
    task_profile: str
    candidates: tuple[str, ...]
    preferred: str
    mode: Literal["SELECT_ONE", "FALLBACK", "FUSE"]
    requirement: Literal["HARD_REQUIRED", "ANY_OF", "SUPPORTING", "ENRICHMENT"]
    max_requests: int = 6


CAPABILITIES = {
    "financial_statements": ("fmp",),
    "market_history": ("fmp",),
    "company_news": ("fmp", "bocha"),
    "earnings_transcript": ("fmp", "bocha"),
    "official_document_search": ("bocha",),
    "web_research": ("bocha",),
    "management_guidance_evidence": ("fmp", "bocha"),
    "company_event_evidence": ("fmp", "bocha"),
}


def data_policy(capability, *, task_profile="research_news_analysis", fuse=False):
    candidates = CAPABILITIES[capability]
    structured = capability in {"financial_statements", "market_history"}
    if structured and fuse:
        raise ValueError("Structured calculation inputs cannot use web fusion")
    return DataCapabilityPolicy(
        capability_id=capability,
        task_profile=task_profile,
        candidates=candidates,
        preferred=candidates[0],
        mode="SELECT_ONE" if len(candidates) == 1 else "FUSE" if fuse else "FALLBACK",
        requirement="HARD_REQUIRED" if structured else "ENRICHMENT",
    )
