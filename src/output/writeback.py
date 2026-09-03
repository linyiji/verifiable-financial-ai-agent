from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from src.domain.base import TimestampedModel
from src.output._snapshot import snapshot


class ValueType(StrEnum):
    FACT = "FACT"
    CALCULATION = "CALCULATION"
    FORECAST = "FORECAST"
    JUDGMENT = "JUDGMENT"


class WritebackTarget(StrEnum):
    CANONICAL_STATE = "CANONICAL_STATE"
    VERSIONED_METRIC = "VERSIONED_METRIC"
    VERSIONED_FORECAST = "VERSIONED_FORECAST"
    VERSIONED_JUDGMENT = "VERSIONED_JUDGMENT"


EXPECTED_TARGET = {
    ValueType.FACT: WritebackTarget.CANONICAL_STATE,
    ValueType.CALCULATION: WritebackTarget.VERSIONED_METRIC,
    ValueType.FORECAST: WritebackTarget.VERSIONED_FORECAST,
    ValueType.JUDGMENT: WritebackTarget.VERSIONED_JUDGMENT,
}


class ObjectWritebackItem(TimestampedModel):
    metric_code: str
    period: str
    as_of: date
    definition_version: str
    value: Any
    unit: str
    currency: str | None = None
    value_type: ValueType
    writeback_target: WritebackTarget
    source_evidence_ids: list[str] = Field(default_factory=list)
    calculation_id: str | None = None
    assumption_set_id: str | None = None
    judgment_ref: str | None = None

    @model_validator(mode="after")
    def validate_lineage_and_target(self) -> "ObjectWritebackItem":
        expected_target = EXPECTED_TARGET[self.value_type]
        if self.writeback_target is not expected_target:
            raise ValueError(
                f"{self.value_type.value} must write to {expected_target.value}, "
                f"not {self.writeback_target.value}"
            )
        if self.value_type is ValueType.FACT and not self.source_evidence_ids:
            raise ValueError("FACT writeback requires accepted source evidence references")
        if self.value_type is ValueType.CALCULATION and self.calculation_id is None:
            raise ValueError("CALCULATION writeback requires calculation_id")
        if self.value_type is ValueType.FORECAST and self.assumption_set_id is None:
            raise ValueError("FORECAST writeback requires assumption_set_id")
        if self.value_type is ValueType.JUDGMENT and self.judgment_ref is None:
            raise ValueError("JUDGMENT writeback requires a versioned judgment_ref")
        return self


class ObjectWritebackProposal(TimestampedModel):
    proposal_id: str
    object_id: str
    run_id: str
    items: list[ObjectWritebackItem] = Field(min_length=1)


class ObjectWritebackProposalBuilder:
    @staticmethod
    def build(
        *,
        proposal_id: str,
        object_id: str,
        run_id: str,
        items: list[ObjectWritebackItem] | tuple[ObjectWritebackItem, ...],
    ) -> ObjectWritebackProposal:
        identifiers = {
            "proposal_id": proposal_id,
            "object_id": object_id,
            "run_id": run_id,
        }
        for field_name, value in identifiers.items():
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")
        return ObjectWritebackProposal(
            proposal_id=proposal_id.strip(),
            object_id=object_id.strip(),
            run_id=run_id.strip(),
            items=snapshot(list(items)),
        )
