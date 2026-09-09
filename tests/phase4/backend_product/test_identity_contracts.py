from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.phase4_product.contracts import (
    ArtifactSummaryV1,
    AtomicRunProjectionV1,
    AvailabilityStatus,
    AvailabilityV1,
    ExecutionSummaryV1,
    GoalProjectionV1,
    GraphProjectionV1,
    ObjectIdentityV1,
    ProofSummaryV1,
    ResearchRunDetailV1,
    ResearchRunDraftV1,
    ResultSummaryV1,
    ReviewSummaryV1,
    RunAdmissionV1,
    RunLifecycleV1,
    RunProgressV1,
    SchemeProjectionV1,
    TaskProjectionV1,
    TerminalStateV1,
)

NOW = datetime(2026, 9, 5, 8, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def _goal(*, object_id: str = "OBJ-A", goal_id: str = "GOAL-A") -> GoalProjectionV1:
    return GoalProjectionV1(
        goal_id=goal_id,
        research_object_id=object_id,
        goal_text="Evaluate the exact company",
        as_of=date(2026, 9, 5),
        created_at=NOW,
    )


def _scheme(
    *,
    object_id: str = "OBJ-A",
    goal_id: str = "GOAL-A",
    scheme_id: str = "SCHEME-A",
    confirmed: bool = True,
) -> SchemeProjectionV1:
    return SchemeProjectionV1(
        scheme_id=scheme_id,
        research_object_id=object_id,
        goal_id=goal_id,
        generated_by="planner-v1",
        created_at=NOW,
        confirmed_at=NOW if confirmed else None,
    )


def _task(*, run_id: str = "RUN-A") -> TaskProjectionV1:
    return TaskProjectionV1(
        task_id=f"{run_id}:TASK-1",
        run_id=run_id,
        task_type="fundamental_analysis",
        goal="Analyze fundamentals",
        assigned_agent="fundamental_analyst",
        skill_id="fundamental_analysis_v1",
        origin="PLAN",
        status="RUNNING",
        progress=0.25,
        attempt_count=1,
        created_at=NOW,
    )


def _projection_payload() -> dict[str, object]:
    pending_review = ReviewSummaryV1(
        availability=AvailabilityV1.unavailable(
            AvailabilityStatus.PENDING,
            "REVIEW_PENDING",
        )
    )
    not_generated = AvailabilityV1.unavailable(
        AvailabilityStatus.NOT_GENERATED,
        "NOT_GENERATED",
    )
    progress = RunProgressV1(completed_tasks=0, total_tasks=1, fraction=0.25)
    task = _task()
    return {
        "projection_revision": 7,
        "projection_sequence": 11,
        "generated_at": NOW,
        "object": ObjectIdentityV1(
            object_id="OBJ-A",
            symbol="NVDA",
            company_name="NVIDIA Corporation",
            exchange="NASDAQ",
        ),
        "run": ResearchRunDetailV1(
            run_id="RUN-A",
            research_object_id="OBJ-A",
            goal_id="GOAL-A",
            scheme_id="SCHEME-A",
            status="RUNNING",
            stage="RESEARCH",
            as_of=date(2026, 9, 5),
            planned_graph_id="GRAPH-A",
            actual_graph_id="GRAPH-ACTUAL-A",
            execution_target="SERVER_SANDBOX",
            created_at=NOW,
            updated_at=NOW,
            started_at=NOW,
            completed_at=None,
            terminal=False,
            projection_revision=7,
            projection_sequence=11,
        ),
        "goal": _goal(),
        "confirmed_scheme": _scheme(),
        "planned_graph": GraphProjectionV1(
            graph_id="GRAPH-A",
            run_id="RUN-A",
            version=1,
            tasks=(task,),
        ),
        "actual_graph": GraphProjectionV1(
            graph_id="GRAPH-ACTUAL-A",
            run_id="RUN-A",
            version=2,
            tasks=(task,),
        ),
        "graph_version": 2,
        "tasks": (task,),
        "path_changes": (),
        "activity": (),
        "lifecycle": RunLifecycleV1(
            status="RUNNING",
            stage="RESEARCH",
            progress=progress,
            terminal=False,
            terminal_outcome=None,
            safe_failure=None,
        ),
        "review": pending_review,
        "result": ResultSummaryV1(availability=not_generated),
        "artifacts": ArtifactSummaryV1(availability=not_generated),
        "proof": ProofSummaryV1(
            availability=AvailabilityV1.unavailable(
                AvailabilityStatus.NOT_GENERATED,
                "PROOF_POLICY_UNKNOWN",
            ),
            policy="UNKNOWN",
            status=None,
        ),
        "execution": ExecutionSummaryV1(availability=not_generated),
        "terminal": TerminalStateV1(
            is_terminal=False,
            outcome=None,
            event_id=None,
            sequence=None,
        ),
    }


def test_atomic_projection_accepts_one_exact_object_goal_scheme_run_tuple() -> None:
    projection = AtomicRunProjectionV1.model_validate(_projection_payload())
    assert (
        projection.object.object_id,
        projection.run.run_id,
        projection.goal.goal_id,
        projection.confirmed_scheme.scheme_id,
    ) == ("OBJ-A", "RUN-A", "GOAL-A", "SCHEME-A")


def test_atomic_projection_summaries_serialize_exact_per_kind_wire_shapes() -> None:
    payload = AtomicRunProjectionV1.model_validate(_projection_payload()).model_dump(mode="json")
    assert set(payload["review"]) == {"availability", "review_id", "status"}
    assert set(payload["result"]) == {
        "availability",
        "released_result_id",
        "canonical_record_id",
        "released_at",
    }
    assert set(payload["artifacts"]) == {"availability", "report_id", "representation_ids"}
    assert set(payload["execution"]) == {"availability", "canonical_record_id"}


@pytest.mark.parametrize(
    ("model", "payload", "expected_fields"),
    [
        (
            ReviewSummaryV1,
            {
                "availability": AvailabilityV1.available(),
                "review_id": "REVIEW-A",
                "status": "PASS",
            },
            {"availability", "review_id", "status"},
        ),
        (
            ResultSummaryV1,
            {
                "availability": AvailabilityV1.available(),
                "released_result_id": "RESULT-A",
                "canonical_record_id": "CANONICAL-A",
                "released_at": NOW,
            },
            {"availability", "released_result_id", "canonical_record_id", "released_at"},
        ),
        (
            ArtifactSummaryV1,
            {
                "availability": AvailabilityV1.available(),
                "report_id": "REPORT-A",
                "representation_ids": ("REPRESENTATION-A",),
            },
            {"availability", "report_id", "representation_ids"},
        ),
        (
            ExecutionSummaryV1,
            {
                "availability": AvailabilityV1.available(),
                "canonical_record_id": "CANONICAL-A",
            },
            {"availability", "canonical_record_id"},
        ),
    ],
)
def test_atomic_projection_summary_accepts_each_exact_available_shape(
    model: type[object], payload: dict[str, object], expected_fields: set[str]
) -> None:
    summary = model.model_validate(payload)  # type: ignore[attr-defined]
    assert set(summary.model_dump(mode="json")) == expected_fields  # type: ignore[attr-defined]


def test_atomic_projection_summary_rejects_obsolete_generic_eight_field_superset() -> None:
    with pytest.raises(ValidationError):
        ReviewSummaryV1.model_validate(
            {
                "availability": AvailabilityV1.available(),
                "review_id": "REVIEW-A",
                "status": "PASS",
                "released_result_id": "RESULT-A",
                "canonical_record_id": "CANONICAL-A",
                "released_at": NOW,
                "report_id": "REPORT-A",
                "representation_ids": ("REPRESENTATION-A",),
            }
        )


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            ReviewSummaryV1,
            {"availability": AvailabilityV1.available(), "review_id": "REVIEW-A"},
        ),
        (
            ResultSummaryV1,
            {
                "availability": AvailabilityV1.available(),
                "released_result_id": "RESULT-A",
                "canonical_record_id": None,
                "released_at": None,
            },
        ),
        (
            ArtifactSummaryV1,
            {
                "availability": AvailabilityV1.available(),
                "report_id": "REPORT-A",
                "representation_ids": (),
            },
        ),
        (
            ExecutionSummaryV1,
            {"availability": AvailabilityV1.available(), "canonical_record_id": None},
        ),
        (
            ReviewSummaryV1,
            {
                "availability": AvailabilityV1.unavailable(
                    AvailabilityStatus.PENDING, "REVIEW_PENDING"
                ),
                "review_id": None,
                "status": None,
                "released_result_id": None,
            },
        ),
    ],
)
def test_atomic_projection_summary_rejects_missing_owned_or_cross_kind_fields(
    model: type[object], payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            ReviewSummaryV1,
            {
                "availability": AvailabilityV1.unavailable(
                    AvailabilityStatus.PENDING, "REVIEW_PENDING"
                ),
                "review_id": "REVIEW-A",
                "status": "PASS",
            },
        ),
        (
            ResultSummaryV1,
            {
                "availability": AvailabilityV1.unavailable(
                    AvailabilityStatus.PENDING, "RESULT_PENDING"
                ),
                "released_result_id": "RESULT-A",
                "canonical_record_id": "CANONICAL-A",
                "released_at": NOW,
            },
        ),
        (
            ArtifactSummaryV1,
            {
                "availability": AvailabilityV1.unavailable(
                    AvailabilityStatus.PENDING, "ARTIFACT_PENDING"
                ),
                "report_id": "REPORT-A",
                "representation_ids": ("REPRESENTATION-A",),
            },
        ),
        (
            ExecutionSummaryV1,
            {
                "availability": AvailabilityV1.unavailable(
                    AvailabilityStatus.PENDING, "EXECUTION_PENDING"
                ),
                "canonical_record_id": "CANONICAL-A",
            },
        ),
    ],
)
def test_atomic_projection_summary_rejects_availability_identity_mismatch(
    model: type[object], payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        (
            "object",
            ObjectIdentityV1(
                object_id="OBJ-B",
                symbol="AMD",
                company_name="Advanced Micro Devices",
                exchange="NASDAQ",
            ),
            "run and object identity disagree",
        ),
        ("goal", _goal(goal_id="GOAL-B"), "goal identity does not close"),
        ("confirmed_scheme", _scheme(scheme_id="SCHEME-B"), "confirmed scheme identity"),
        (
            "confirmed_scheme",
            _scheme(confirmed=False),
            "confirmed scheme identity",
        ),
        (
            "planned_graph",
            GraphProjectionV1(
                graph_id="GRAPH-B",
                run_id="RUN-B",
                version=1,
                tasks=(_task(run_id="RUN-B"),),
            ),
            "graph belongs to another run",
        ),
        ("tasks", (_task(run_id="RUN-B"),), "task belongs to another run"),
    ],
)
def test_atomic_projection_rejects_cross_object_run_goal_scheme_substitution(
    field: str,
    replacement: object,
    message: str,
) -> None:
    payload = _projection_payload()
    payload[field] = replacement
    with pytest.raises(ValidationError, match=message):
        AtomicRunProjectionV1.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [("projection_revision", 8), ("projection_sequence", 12)],
)
def test_atomic_projection_rejects_torn_revision_or_event_watermark(
    field: str,
    value: int,
) -> None:
    payload = _projection_payload()
    payload[field] = value
    with pytest.raises(ValidationError, match="torn"):
        AtomicRunProjectionV1.model_validate(payload)


def test_prepared_draft_rejects_cross_object_or_goal_scheme() -> None:
    valid = {
        "draft_id": "DRAFT-A",
        "draft_version": 1,
        "planned_graph_availability": AvailabilityV1.unavailable(
            AvailabilityStatus.NOT_GENERATED,
            "PLAN_CREATED_ON_CONFIRM",
        ),
        "object_id": "OBJ-A",
        "goal": _goal(),
        "scheme_snapshot": _scheme(confirmed=False),
        "prepare_request_hash": HASH_A,
        "draft_hash": HASH_B,
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=30),
    }
    assert ResearchRunDraftV1.model_validate(valid).object_id == "OBJ-A"

    for field, replacement in (
        ("goal", _goal(object_id="OBJ-B")),
        ("scheme_snapshot", _scheme(object_id="OBJ-B", confirmed=False)),
        ("scheme_snapshot", _scheme(goal_id="GOAL-B", confirmed=False)),
    ):
        payload = {**valid, field: replacement}
        with pytest.raises(ValidationError, match="belongs to another"):
            ResearchRunDraftV1.model_validate(payload)


def test_admission_refs_cannot_point_at_a_latest_or_first_run() -> None:
    values = {
        "admission_id": "ADMISSION-A",
        "run_id": "RUN-A",
        "object_id": "OBJ-A",
        "draft_id": "DRAFT-A",
        "draft_version": 1,
        "draft_hash": HASH_A,
        "goal_id": "GOAL-A",
        "scheme_id": "SCHEME-A",
        "planned_graph_id": "GRAPH-A",
        "confirmation_request_hash": HASH_B,
        "admitted_at": NOW,
        "projection_ref": "/api/research-runs/RUN-A/projection",
        "events_ref": "/api/research-runs/RUN-A/events",
    }
    assert RunAdmissionV1.model_validate(values).run_id == "RUN-A"

    for field, fallback_ref in (
        ("projection_ref", "/api/research-runs/latest/projection"),
        ("events_ref", "/api/research-runs/RUN-B/events"),
    ):
        with pytest.raises(ValidationError, match="admitted run"):
            RunAdmissionV1.model_validate({**values, field: fallback_ref})
