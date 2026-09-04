from datetime import datetime

from src.domain.base import JsonObject
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.output._snapshot import ordered_unique, snapshot


class CanonicalExecutionRecordBuilder:
    """Build the immutable-in-practice snapshot used by all output projections."""

    @staticmethod
    def build(
        *,
        record_id: str,
        run_id: str,
        planned_graph: JsonObject,
        actual_graph: JsonObject,
        runtime_outcome: str,
        object_snapshot_ref: str | None = None,
        goal_ref: str | None = None,
        scheme_ref: str | None = None,
        task_refs: list[str] | tuple[str, ...] = (),
        evidence_refs: list[str] | tuple[str, ...] = (),
        calculation_refs: list[str] | tuple[str, ...] = (),
        metric_refs: list[str] | tuple[str, ...] = (),
        claim_refs: list[str] | tuple[str, ...] = (),
        judgment_refs: list[str] | tuple[str, ...] = (),
        decision_refs: list[str] | tuple[str, ...] = (),
        correction_refs: list[str] | tuple[str, ...] = (),
        replan_refs: list[str] | tuple[str, ...] = (),
        generated_capability_refs: list[str] | tuple[str, ...] = (),
        review_refs: list[str] | tuple[str, ...] = (),
        proof_refs: list[str] | tuple[str, ...] = (),
        trace_refs: list[str] | tuple[str, ...] = (),
        token_usage: int = 0,
        cost: float = 0.0,
        latency_ms: int = 0,
        created_at: datetime | None = None,
    ) -> CanonicalExecutionRecord:
        required_identifiers = {
            "record_id": record_id,
            "run_id": run_id,
            "runtime_outcome": runtime_outcome,
        }
        for field_name, value in required_identifiers.items():
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")

        payload: dict[str, object] = {
            "record_id": record_id.strip(),
            "run_id": run_id.strip(),
            "object_snapshot_ref": object_snapshot_ref,
            "goal_ref": goal_ref,
            "scheme_ref": scheme_ref,
            "planned_graph": snapshot(planned_graph),
            "actual_graph": snapshot(actual_graph),
            "task_refs": ordered_unique(task_refs),
            "evidence_refs": ordered_unique(evidence_refs),
            "calculation_refs": ordered_unique(calculation_refs),
            "metric_refs": ordered_unique(metric_refs),
            "claim_refs": ordered_unique(claim_refs),
            "judgment_refs": ordered_unique(judgment_refs),
            "decision_refs": ordered_unique(decision_refs),
            "correction_refs": ordered_unique(correction_refs),
            "replan_refs": ordered_unique(replan_refs),
            "generated_capability_refs": ordered_unique(generated_capability_refs),
            "review_refs": ordered_unique(review_refs),
            "proof_refs": ordered_unique(proof_refs),
            "trace_refs": ordered_unique(trace_refs),
            "token_usage": token_usage,
            "cost": cost,
            "latency_ms": latency_ms,
            "runtime_outcome": runtime_outcome.strip(),
        }
        if created_at is not None:
            payload["created_at"] = created_at

        return CanonicalExecutionRecord.model_validate(payload)
