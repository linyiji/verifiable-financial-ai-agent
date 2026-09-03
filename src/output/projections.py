from pydantic import Field

from src.domain.base import DomainModel, JsonObject
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.output._snapshot import snapshot


class FinancialReviewView(DomainModel):
    """Financial lineage view (claim/decision -> evidence -> review -> proof)."""

    canonical_record_id: str
    run_id: str
    decision_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    calculation_refs: list[str] = Field(default_factory=list)
    review_refs: list[str] = Field(default_factory=list)
    proof_refs: list[str] = Field(default_factory=list)
    runtime_outcome: str


class ExecutionDetails(DomainModel):
    """Machine-oriented view of graph execution and operational lineage."""

    canonical_record_id: str
    run_id: str
    planned_graph: JsonObject
    actual_graph: JsonObject
    task_refs: list[str] = Field(default_factory=list)
    generated_capability_refs: list[str] = Field(default_factory=list)
    correction_refs: list[str] = Field(default_factory=list)
    replan_refs: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
    token_usage: int = Field(ge=0)
    cost: float = Field(ge=0.0)
    latency_ms: int = Field(ge=0)
    runtime_outcome: str


class CanonicalRecordProjections(DomainModel):
    """B/C views emitted together from exactly one record instance."""

    canonical_record_id: str
    financial_review: FinancialReviewView
    execution_details: ExecutionDetails


def build_financial_review_view(record: CanonicalExecutionRecord) -> FinancialReviewView:
    return FinancialReviewView(
        canonical_record_id=record.record_id,
        run_id=record.run_id,
        decision_refs=snapshot(record.decision_refs),
        evidence_refs=snapshot(record.evidence_refs),
        calculation_refs=snapshot(record.calculation_refs),
        review_refs=snapshot(record.review_refs),
        proof_refs=snapshot(record.proof_refs),
        runtime_outcome=record.runtime_outcome,
    )


def build_execution_details(record: CanonicalExecutionRecord) -> ExecutionDetails:
    return ExecutionDetails(
        canonical_record_id=record.record_id,
        run_id=record.run_id,
        planned_graph=snapshot(record.planned_graph),
        actual_graph=snapshot(record.actual_graph),
        task_refs=snapshot(record.task_refs),
        generated_capability_refs=snapshot(record.generated_capability_refs),
        correction_refs=snapshot(record.correction_refs),
        replan_refs=snapshot(record.replan_refs),
        trace_refs=snapshot(record.trace_refs),
        token_usage=record.token_usage,
        cost=record.cost,
        latency_ms=record.latency_ms,
        runtime_outcome=record.runtime_outcome,
    )


def build_canonical_record_projections(
    record: CanonicalExecutionRecord,
) -> CanonicalRecordProjections:
    financial_review = build_financial_review_view(record)
    execution_details = build_execution_details(record)
    if financial_review.canonical_record_id != execution_details.canonical_record_id:
        raise AssertionError("B/C projections must share one canonical execution record")
    return CanonicalRecordProjections(
        canonical_record_id=record.record_id,
        financial_review=financial_review,
        execution_details=execution_details,
    )
