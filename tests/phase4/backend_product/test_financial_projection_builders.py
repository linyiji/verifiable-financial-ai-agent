from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.assurance.independent_financial_review import financial_review_input_snapshot_hash
from src.domain.calculation import CalculationRecord
from src.domain.evidence import EvidenceRecord
from src.domain.financial_semantics import MaterialFinancialClaim, ReleasedFinancialMetric
from src.domain.proof import ProofPolicyDecision
from src.phase4_product.contracts import AvailabilityStatus
from src.phase4_product.projections import (
    ProjectionIntegrityError,
    build_execution_projection,
    build_financial_review,
    build_released_metric,
)

NOW = datetime(2026, 9, 5, 10, tzinfo=UTC)
AS_OF = date(2026, 9, 5)


def _metric() -> dict[str, object]:
    return {
        "metric_id": "METRIC-A",
        "calculation_id": "CALC-A",
        "name": "SMA 50",
        "canonical_value": "123.4500",
        "canonical_unit": "INDEX",
        "display_value": "123.45",
        "display_unit": "points",
        "period": "CURRENT",
        "period_basis": "CURRENT",
        "actuality": "ACTUAL",
        "as_of": AS_OF,
        "currency": None,
        "formula_id": "sma_close_50_v1",
        "capability_id": "sma",
        "evidence_ids": ("EVIDENCE-A", "EVIDENCE-B"),
        "method_metadata": {
            "method": "SMA_CLOSE",
            "parameters": (("window", "50"), ("price", "close")),
            "observation_count": 200,
            "warmup_required": 50,
            "warmup_satisfied": True,
            "first_as_of": date(2026, 1, 1),
            "last_as_of": AS_OF,
            "is_wilder": False,
            "ema_adjust": False,
        },
        "technical_price_basis": "RAW_CLOSE",
        "corporate_action_status": "NONE_DETECTED",
        "corporate_action_guard_refs": ("EVIDENCE-B",),
        "limitations": ("End-of-day prices only",),
    }


def _calculation() -> dict[str, object]:
    return {
        "calculation_id": "CALC-A",
        "run_id": "RUN-A",
        "task_id": "TASK-A",
        "status": "PASS",
        "formula_id": "sma_close_50_v1",
        "capability_id": "sma",
        "capability_version": "1.0.0",
        "input_evidence_ids": ("EVIDENCE-A", "EVIDENCE-B"),
        "input_values_snapshot": {"closes": [120, 121, 123.45]},
        "parameters": {"window": 50},
        "output_value": "123.4500",
        "output_unit": "INDEX",
        "created_at": NOW,
    }


def _evidence() -> tuple[dict[str, object], ...]:
    return (
        {
            "evidence_id": "EVIDENCE-A",
            "run_id": "RUN-A",
            "object_id": "OBJ-A",
            "provider": "market-data",
            "retrieved_at": NOW,
            "period": "CURRENT",
            "period_basis": "CURRENT",
            "actuality": "ACTUAL",
            "as_of": AS_OF,
            "raw_artifact_ref": "artifact://market-data/EVIDENCE-A",
            "normalized_field": "close",
            "normalized_value": "120",
            "unit": "INDEX",
            "snapshot_hash": "sha256:" + "a" * 64,
            "status": "ACCEPTED",
            "created_at": NOW,
        },
        {
            "evidence_id": "EVIDENCE-B",
            "run_id": "RUN-A",
            "object_id": "OBJ-A",
            "provider": "market-data",
            "retrieved_at": NOW,
            "period": "CURRENT",
            "period_basis": "CURRENT",
            "actuality": "ACTUAL",
            "as_of": AS_OF,
            "raw_artifact_ref": "artifact://market-data/EVIDENCE-B",
            "normalized_field": "corporate_action_status",
            "normalized_value": "NONE_DETECTED",
            "unit": "STATUS",
            "snapshot_hash": "sha256:" + "b" * 64,
            "status": "ACCEPTED",
            "created_at": NOW,
        },
    )


def _claim() -> dict[str, object]:
    return {
        "claim_id": "CLAIM-A",
        "run_id": "RUN-A",
        "claim_type": "TECHNICAL_METRIC",
        "statement": "The 50-day simple moving average is 123.45 points.",
        "metric_id": "METRIC-A",
        "value": "123.4500",
        "unit": "INDEX",
        "period": "CURRENT",
        "period_basis": "CURRENT",
        "actuality": "ACTUAL",
        "as_of": AS_OF,
        "currency": None,
        "calculation_refs": ("CALC-A",),
        "evidence_refs": ("EVIDENCE-A", "EVIDENCE-B"),
        "judgment_refs": (),
    }


def _policy() -> dict[str, object]:
    return {
        "decision_id": "DECISION-A",
        "run_id": "RUN-A",
        "calculation_id": "CALC-A",
        "formula_id": "sma_close_50_v1",
        "requirement": "NOT_REQUIRED",
        "policy_id": "proof-policy-v1",
        "reason": "Formula does not require proof under policy v1.",
        "created_at": NOW,
    }


def _build_metric(**updates: object):
    values = {
        "expected_object_id": "OBJ-A",
        "expected_run_id": "RUN-A",
        "metric": _metric(),
        "claims": (_claim(),),
        "calculation": _calculation(),
        "evidence": _evidence(),
        "proof_policy_decisions": (_policy(),),
    }
    values.update(updates)
    return build_released_metric(**values)


def test_released_metric_preserves_every_financial_and_method_field() -> None:
    projection = _build_metric()

    assert projection.model_dump(mode="json") == {
        "run_id": "RUN-A",
        "metric_id": "METRIC-A",
        "name": "SMA 50",
        "canonical_value": "123.4500",
        "canonical_unit": "INDEX",
        "display_value": "123.45",
        "display_unit": "points",
        "period": "CURRENT",
        "period_basis": "CURRENT",
        "actuality": "ACTUAL",
        "as_of": "2026-09-05",
        "currency": None,
        "formula_id": "sma_close_50_v1",
        "capability_id": "sma",
        "calculation_id": "CALC-A",
        "evidence_refs": ["EVIDENCE-A", "EVIDENCE-B"],
        "claim_refs": ["CLAIM-A"],
        "proof": {
            "policy_id": "proof-policy-v1",
            "requirement": "NOT_REQUIRED",
            "status": "NOT_REQUIRED",
            "proof_refs": [],
        },
        "method_metadata": {
            "method": "SMA_CLOSE",
            "parameters": [
                {"name": "window", "value": "50"},
                {"name": "price", "value": "close"},
            ],
            "observation_count": 200,
            "warmup_required": 50,
            "warmup_satisfied": True,
            "first_as_of": "2026-01-01",
            "last_as_of": "2026-09-05",
            "is_wilder": False,
            "ema_adjust": False,
        },
        "technical_price_basis": "RAW_CLOSE",
        "corporate_action_status": "NONE_DETECTED",
        "corporate_action_guard_refs": ["EVIDENCE-B"],
        "limitations": ["End-of-day prices only"],
    }


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("run_id", "RUN-B", "Calculation closure"),
        ("output_value", "123.46", "value differs"),
        ("output_unit", "PERCENT", "unit differs"),
    ],
)
def test_released_metric_rejects_calculation_substitution(
    field: str,
    bad_value: object,
    message: str,
) -> None:
    calculation = {**_calculation(), field: bad_value}
    with pytest.raises(ProjectionIntegrityError, match=message):
        _build_metric(calculation=calculation)


@pytest.mark.parametrize("field", ["run_id", "object_id", "status"])
def test_released_metric_rejects_foreign_or_unaccepted_evidence(field: str) -> None:
    first, second = _evidence()
    bad = {
        **first,
        field: {"run_id": "RUN-B", "object_id": "OBJ-B", "status": "REJECTED"}[field],
    }
    with pytest.raises(ProjectionIntegrityError, match="Evidence closure"):
        _build_metric(evidence=(bad, second))


def test_released_metric_rejects_missing_or_contaminating_records_without_fallback() -> None:
    with pytest.raises(ProjectionIntegrityError, match="Evidence input"):
        _build_metric(evidence=(_evidence()[0],))
    with pytest.raises(ProjectionIntegrityError, match="exactly one durable"):
        _build_metric(proof_policy_decisions=())
    with pytest.raises(ProjectionIntegrityError, match="Claim belongs to another Run"):
        _build_metric(claims=({**_claim(), "run_id": "RUN-B"},))


def _run(status: str = "RUNNING") -> dict[str, object]:
    return {
        "run_id": "RUN-A",
        "research_object_id": "OBJ-A",
        "status": status,
        "as_of": AS_OF,
    }


def _review_inputs() -> dict[str, tuple[object, ...]]:
    return {
        "evidence_records": tuple(EvidenceRecord.model_validate(item) for item in _evidence()),
        "calculation_records": (CalculationRecord.model_validate(_calculation()),),
        "metric_records": (ReleasedFinancialMetric.model_validate(_metric()),),
        "claim_records": (MaterialFinancialClaim.model_validate(_claim()),),
        "judgment_records": (),
        "proof_policy_decisions": (ProofPolicyDecision.model_validate(_policy()),),
    }


def _review_input_hash() -> str:
    inputs = _review_inputs()
    decisions = inputs["proof_policy_decisions"]
    return financial_review_input_snapshot_hash(
        run_id="RUN-A",
        run_as_of=AS_OF,
        evidence=inputs["evidence_records"],  # type: ignore[arg-type]
        calculations=inputs["calculation_records"],  # type: ignore[arg-type]
        metrics=inputs["metric_records"],  # type: ignore[arg-type]
        claims=inputs["claim_records"],  # type: ignore[arg-type]
        judgments=inputs["judgment_records"],  # type: ignore[arg-type]
        proof_requirements={
            decision.calculation_id: decision.requirement  # type: ignore[attr-defined]
            for decision in decisions
        },
    )


def _review() -> dict[str, object]:
    return {
        "review_id": "REVIEW-A",
        "run_id": "RUN-A",
        "status": "PASS",
        "reviewer": "independent-financial-review-v2",
        "input_snapshot_hash": _review_input_hash(),
        "reviewed_evidence_refs": ("EVIDENCE-A", "EVIDENCE-B"),
        "reviewed_calculation_refs": ("CALC-A",),
        "reviewed_metric_refs": ("METRIC-A",),
        "reviewed_claim_refs": ("CLAIM-A",),
        "reviewed_judgment_refs": (),
        "required_proof_calculation_refs": (),
        "checks": (
            {
                "check_id": "CHECK-B",
                "check_code": "FORMULA_MATCH",
                "status": "PASS",
                "subjects": (
                    {
                        "subject_type": "CALCULATION",
                        "subject_id": "CALC-A",
                        "run_id": "RUN-A",
                    },
                ),
                "expected": {"formula_id": "sma_close_50_v1"},
                "actual": {"formula_id": "sma_close_50_v1"},
                "detail": "Formula identity matches.",
                "exception_state": "NONE",
                "correction_refs": (),
                "created_at": NOW.replace(minute=2),
                "resolved_at": None,
            },
            {
                "check_id": "CHECK-A",
                "check_code": "RUN_CLOSED",
                "status": "PASS",
                "subjects": ({"subject_type": "RUN", "subject_id": "RUN-A", "run_id": "RUN-A"},),
                "expected": {"status": "RUNNING"},
                "actual": {"status": "RUNNING"},
                "detail": None,
                "exception_state": "NONE",
                "correction_refs": (),
                "created_at": NOW.replace(minute=1),
                "resolved_at": None,
            },
        ),
    }


def _build_review(**updates: object):
    values = {
        "expected_object_id": "OBJ-A",
        "expected_run_id": "RUN-A",
        "projection_revision": 4,
        "projection_sequence": 9,
        "run": _run(),
        "review": _review(),
        **_review_inputs(),
    }
    values.update(updates)
    return build_financial_review(**values)


def test_review_projects_exact_status_vocabulary_and_stable_check_order() -> None:
    projection = _build_review()

    assert projection.status == "PASS"
    assert [item.check_id for item in projection.checks] == ["CHECK-A", "CHECK-B"]
    assert projection.reviewed_calculation_refs == ("CALC-A",)
    assert projection.availability.status is AvailabilityStatus.AVAILABLE


def test_absent_review_has_explicit_pending_or_terminal_not_generated_state() -> None:
    live = _build_review(review=None)
    assert (live.status, live.availability.status, live.availability.reason_code) == (
        None,
        AvailabilityStatus.PENDING,
        "REVIEW_PENDING",
    )

    failed = _build_review(run=_run("FAILED"), review=None)
    assert (failed.status, failed.availability.status, failed.availability.reason_code) == (
        None,
        AvailabilityStatus.NOT_GENERATED,
        "REVIEW_NOT_GENERATED",
    )

    with pytest.raises(ProjectionIntegrityError, match="cannot lack"):
        _build_review(run=_run("RELEASED"), review=None)


def test_review_rejects_legacy_status_foreign_subject_and_secret_payload() -> None:
    legacy = {**_review(), "status": "PASS_WITH_UNCERTAINTY"}
    with pytest.raises(ProjectionIntegrityError, match="status disagrees"):
        _build_review(review=legacy)

    foreign = _review()
    foreign["checks"] = (
        {
            **foreign["checks"][0],  # type: ignore[index]
            "subjects": ({"subject_type": "RUN", "subject_id": "RUN-B", "run_id": "RUN-B"},),
        },
    )
    with pytest.raises(ProjectionIntegrityError, match="same-Run"):
        _build_review(review=foreign)

    unsafe = _review()
    unsafe["checks"] = (
        {**unsafe["checks"][0], "actual": {"api_key": "secret"}},  # type: ignore[index]
    )
    with pytest.raises(ProjectionIntegrityError, match="api_key"):
        _build_review(review=unsafe)


def test_review_rejects_stale_hash_and_self_authored_subject_refs() -> None:
    stale = {**_review(), "input_snapshot_hash": "sha256:" + "f" * 64}
    with pytest.raises(ProjectionIntegrityError, match="does not bind"):
        _build_review(review=stale)

    substituted = _review()
    substituted["reviewed_calculation_refs"] = ("CALC-B",)
    substituted["checks"] = (
        {
            **substituted["checks"][0],  # type: ignore[index]
            "subjects": (
                {
                    "subject_type": "CALCULATION",
                    "subject_id": "CALC-B",
                    "run_id": "RUN-A",
                },
            ),
        },
    )
    with pytest.raises(ProjectionIntegrityError, match="exact retained input set"):
        _build_review(review=substituted)


def _task() -> dict[str, object]:
    return {
        "task_id": "TASK-A",
        "run_id": "RUN-A",
        "parent_task_id": None,
        "task_type": "calculation",
        "goal": "Calculate exact metric",
        "assigned_agent": "calc-agent",
        "skill_id": "sma",
        "dependencies": (),
        "origin": "PLAN",
        "reason_code": None,
        "status": "COMPLETED",
        "progress": 1.0,
        "attempt_count": 1,
        "task_input_evidence_ids": ("EVIDENCE-A", "EVIDENCE-B"),
        "task_output_evidence_ids": (),
        "evidence_acquisition_status": "COMPLETED",
        "evidence_source_coverage": {},
        "created_at": NOW,
    }


def _canonical() -> dict[str, object]:
    graph = {"graph_id": "PLAN-A", "run_id": "RUN-A", "version": 1, "tasks": (_task(),)}
    return {
        "record_id": "CER-A",
        "run_id": "RUN-A",
        "object_snapshot_ref": "OBJ-A",
        "planned_graph": graph,
        "actual_graph": {**graph, "graph_id": "ACTUAL-A"},
        "task_refs": ("TASK-A",),
        "evidence_refs": ("EVIDENCE-A", "EVIDENCE-B"),
        "calculation_refs": ("CALC-A",),
        "metric_refs": ("METRIC-A",),
        "claim_refs": ("CLAIM-A",),
        "judgment_refs": (),
        "decision_refs": (),
        "correction_refs": (),
        "replan_refs": (),
        "generated_capability_refs": (),
        "review_refs": ("REVIEW-A",),
        "proof_refs": (),
        "trace_refs": ("TRACE-A",),
        "token_usage": 321,
        "cost": 1.25,
        "latency_ms": 456,
        "runtime_outcome": "RELEASED",
    }


def test_execution_projection_preserves_exact_graph_refs_and_resource_usage() -> None:
    projection = build_execution_projection(
        expected_object_id="OBJ-A",
        expected_run_id="RUN-A",
        projection_revision=4,
        projection_sequence=9,
        canonical_record=_canonical(),
        released_result={
            "result_id": "RESULT-A",
            "run_id": "RUN-A",
            "canonical_record_id": "CER-A",
        },
    )

    assert projection.canonical_record_id == "CER-A"
    assert projection.released_result_id == "RESULT-A"
    assert projection.task_refs == ("TASK-A",)
    assert projection.token_usage == 321
    assert projection.cost == 1.25
    assert projection.latency_ms == 456
    assert projection.planned_graph["graph_id"] == "PLAN-A"
    assert projection.actual_graph["graph_id"] == "ACTUAL-A"


def test_execution_projection_rejects_cross_run_and_torn_task_graph() -> None:
    with pytest.raises(ProjectionIntegrityError, match="Run/Object closure"):
        build_execution_projection(
            expected_object_id="OBJ-A",
            expected_run_id="RUN-A",
            projection_revision=4,
            projection_sequence=9,
            canonical_record={**_canonical(), "run_id": "RUN-B"},
        )

    canonical = _canonical()
    canonical["task_refs"] = ("TASK-FOREIGN",)
    with pytest.raises(ProjectionIntegrityError, match="task refs"):
        build_execution_projection(
            expected_object_id="OBJ-A",
            expected_run_id="RUN-A",
            projection_revision=4,
            projection_sequence=9,
            canonical_record=canonical,
        )
