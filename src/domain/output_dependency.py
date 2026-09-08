"""Owned output availability and one sufficiency policy, independent of Task status."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from src.domain.base import DomainModel


class OutputStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNAVAILABLE_ENTITLEMENT = "UNAVAILABLE_ENTITLEMENT"
    UNAVAILABLE_PROVIDER = "UNAVAILABLE_PROVIDER"
    BLOCKED_BY_RUNTIME = "BLOCKED_BY_RUNTIME"
    BLOCKED_BY_DEPENDENCY = "BLOCKED_BY_DEPENDENCY"
    FAILED = "FAILED"


class OutputOutcome(DomainModel):
    output_id: str = Field(min_length=1)
    status: OutputStatus
    refs: list[str] = Field(default_factory=list)
    reason_code: str | None = None

    @model_validator(mode="after")
    def completed_output_has_refs(self):
        if self.status is OutputStatus.COMPLETED and not self.refs:
            raise ValueError("Completed output must identify retained authoritative records")
        return self


class OutputRequirements(DomainModel):
    hard_required: list[str] = Field(default_factory=list)
    any_of: list[list[str]] = Field(default_factory=list)
    supporting: list[str] = Field(default_factory=list)
    enrichment: list[str] = Field(default_factory=list)


class Sufficiency(DomainModel):
    status: Literal["SUFFICIENT", "PARTIAL_BUT_SUFFICIENT", "INSUFFICIENT"]
    missing_required: list[str] = Field(default_factory=list)
    unavailable_optional: list[str] = Field(default_factory=list)


def evidence_sufficiency(requirements: OutputRequirements, available: set[str]) -> Sufficiency:
    missing = [key for key in requirements.hard_required if key not in available]
    for group in requirements.any_of:
        if not group or not available.intersection(group):
            missing.append("ANY_OF(" + "|".join(group) + ")")
    optional = [
        key for key in (*requirements.supporting, *requirements.enrichment) if key not in available
    ]
    return Sufficiency(
        status="INSUFFICIENT"
        if missing
        else "PARTIAL_BUT_SUFFICIENT"
        if optional
        else "SUFFICIENT",
        missing_required=missing,
        unavailable_optional=optional,
    )


class LocalOutputFailure(RuntimeError):
    """An explicitly recorded local failure; never used for unknown integrity errors."""

    retryable = False
