from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from src.domain.base import TimestampedModel


class PeerCandidate(TimestampedModel):
    candidate_symbol: str = Field(min_length=1)
    source_evidence_ids: list[str] = Field(default_factory=list)
    industry: str | None = None
    sector: str | None = None
    market_cap: Decimal | None = None
    data_available: bool = False
    metric_comparable: bool = False


class PeerSelectionDecision(TimestampedModel):
    candidate_symbol: str = Field(min_length=1)
    selected: bool
    reason_summary: str = Field(min_length=1)
    selection_source: str = Field(min_length=1)
    source_evidence_ids: list[str] = Field(default_factory=list)
