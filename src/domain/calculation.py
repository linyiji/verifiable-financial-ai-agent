from typing import Any

from pydantic import Field

from src.domain.base import JsonObject, TimestampedModel
from src.domain.enums import CalculationStatus, ReviewStatus


class CalculationRecord(TimestampedModel):
    calculation_id: str
    run_id: str
    task_id: str
    capability_id: str
    capability_version: str
    formula_id: str
    input_evidence_ids: list[str]
    input_values_snapshot: JsonObject = Field(default_factory=dict)
    parameters: JsonObject = Field(default_factory=dict)
    output_value: Any
    output_unit: str
    status: CalculationStatus
    review_status: ReviewStatus | None = None
    implementation_hash: str | None = None
    # Deprecated Phase 1/2 name retained for persisted-record compatibility.
    code_hash: str | None = None
    source_ref: str | None = None
    runtime_version: str | None = None
    review_record_id: str | None = None
    canonical_record_id: str | None = None
    proof_ref: str | None = None
