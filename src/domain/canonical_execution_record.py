from pydantic import Field

from src.domain.base import JsonObject, TimestampedModel


class CanonicalExecutionRecord(TimestampedModel):
    record_id: str
    run_id: str
    object_snapshot_ref: str | None = None
    goal_ref: str | None = None
    scheme_ref: str | None = None
    planned_graph: JsonObject
    actual_graph: JsonObject
    task_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    calculation_refs: list[str] = Field(default_factory=list)
    metric_refs: list[str] = Field(default_factory=list)
    claim_refs: list[str] = Field(default_factory=list)
    judgment_refs: list[str] = Field(default_factory=list)
    decision_refs: list[str] = Field(default_factory=list)
    agent_output_refs: list[str] = Field(default_factory=list)
    correction_refs: list[str] = Field(default_factory=list)
    replan_refs: list[str] = Field(default_factory=list)
    generated_capability_refs: list[str] = Field(default_factory=list)
    review_refs: list[str] = Field(default_factory=list)
    proof_refs: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
    token_usage: int = Field(default=0, ge=0)
    cost: float = Field(default=0.0, ge=0.0)
    latency_ms: int = Field(default=0, ge=0)
    runtime_outcome: str
