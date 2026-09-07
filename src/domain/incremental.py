"""Bounded immutable planning references, never current-run evidence or approval."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IncrementalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision: Literal["REUSE", "REFRESH", "REVALIDATE", "PREVENT", "UNKNOWN"]
    source_run_id: str = Field(min_length=1)
    source_identity: str = Field(min_length=1)
    category: Literal["VIEW_CONTEXT", "VERIFIED_METRIC", "VERIFIED_CLAIM", "RESOLVED_ISSUE"]
    statement: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=2000)
    authority: Literal["phase5b-exact-memory-policy/v1"] = "phase5b-exact-memory-policy/v1"


class IncrementalResearchContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    research_object_id: str = Field(min_length=1)
    base_run_id: str = Field(min_length=1)
    base_research_view_version: str = Field(min_length=1)
    base_version_number: int = Field(ge=1)
    base_as_of: date
    target_as_of: date
    prior_summary: str | None = Field(default=None, max_length=4000, exclude_if=lambda v: v is None)
    decisions: tuple[IncrementalDecision, ...] = Field(max_length=32)

    @model_validator(mode="after")
    def closure(self):
        if self.target_as_of < self.base_as_of:
            raise ValueError("incremental target precedes base as-of")
        keys = [d.source_identity for d in self.decisions]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate incremental decision")
        allowed = {
            "VIEW_CONTEXT": {"REUSE", "UNKNOWN"},
            "VERIFIED_METRIC": {"REFRESH", "REVALIDATE", "UNKNOWN"},
            "VERIFIED_CLAIM": {"REFRESH", "REVALIDATE", "UNKNOWN"},
            "RESOLVED_ISSUE": {"PREVENT", "UNKNOWN"},
        }
        for decision in self.decisions:
            if decision.source_run_id != self.base_run_id:
                raise ValueError("foreign incremental source")
            if decision.decision not in allowed[decision.category]:
                raise ValueError("unsupported reuse or transferred approval")
            if (
                decision.category == "VIEW_CONTEXT"
                and decision.source_identity != self.base_research_view_version
            ):
                raise ValueError("foreign view reference")
        return self
