"""Acceptance tests for exact restart reconstruction.

These tests exercise only the existing durable domain models and the isolated
snapshot validator.  PostgreSQL tables owned by the parent migration are not
assumed here; repository integration belongs in a separate, non-skipped suite
once that migration is available.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from src.domain.enums import ReviewStatus, RunStatus, TaskStatus
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.review import ReviewRecord
from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph, Task
from src.phase4_product.contracts import AvailabilityStatus, ErrorCodeV1
from src.phase4_product.errors import ProductError
from src.phase4_product.reconstruction import (
    PersistedReleaseValidation,
    PersistedRunSnapshot,
    ProjectionWatermark,
    ReconstructedResource,
    _reconstruct_release_validation,
    reconstruct_product_run,
)

NOW = datetime(2026, 9, 5, 10, tzinfo=UTC)


def _snapshot() -> PersistedRunSnapshot:
    research_object = ResearchObject(
        object_id="OBJ-A",
        symbol="ACME",
        company_name="Acme Corp",
        exchange="NASDAQ",
        created_at=NOW,
        updated_at=NOW,
    )
    goal = ResearchGoal(
        goal_id="GOAL-A",
        research_object_id=research_object.object_id,
        goal_text="Evaluate the exact persisted run",
        as_of=date(2026, 9, 5),
        created_at=NOW,
    )
    scheme = ResearchSchemeSnapshot(
        scheme_id="SCHEME-A",
        research_object_id=research_object.object_id,
        goal_id=goal.goal_id,
        research_scope=["fundamentals"],
        generated_by="planner-v1",
        confirmed_at=NOW,
        created_at=NOW,
    )
    task = Task(
        task_id="TASK-A",
        run_id="RUN-A",
        task_type="research",
        goal="Collect exact evidence",
        assigned_agent="research-agent",
        skill_id="research-skill",
        status=TaskStatus.CREATED,
        progress=0.0,
        created_at=NOW,
    )
    planned = PlannedTaskGraph(
        graph_id="PLAN-A",
        run_id="RUN-A",
        version=1,
        tasks=[task.model_copy(deep=True)],
        created_at=NOW,
    )
    actual = ActualRuntimeGraph(
        graph_id="ACTUAL-A",
        run_id="RUN-A",
        version=1,
        tasks=[task.model_copy(deep=True)],
        mutation_history=[],
        created_at=NOW,
    )
    run = ResearchRun(
        run_id="RUN-A",
        research_object_id=research_object.object_id,
        goal_id=goal.goal_id,
        scheme_id=scheme.scheme_id,
        status=RunStatus.DRAFT,
        as_of=goal.as_of,
        planned_graph_id=planned.graph_id,
        actual_graph_id=actual.graph_id,
        created_at=NOW,
    )
    return PersistedRunSnapshot(
        requested_object_id=research_object.object_id,
        requested_run_id=run.run_id,
        projection_revision=7,
        projection_sequence=0,
        research_objects=(research_object,),
        goals=(goal,),
        schemes=(scheme,),
        runs=(run,),
        planned_graphs=(planned,),
        actual_graphs=(actual,),
        tasks=(task,),
    )


def _assert_product_error(
    exc_info: pytest.ExceptionInfo[ProductError],
    code: ErrorCodeV1,
    *,
    reason_code: str | None = None,
) -> None:
    assert exc_info.value.code is code
    if reason_code is not None:
        assert exc_info.value.details == {"reason_code": reason_code}


def test_exact_snapshot_reconstructs_after_process_serialization_round_trip() -> None:
    original = _snapshot()
    restarted = replace(
        original,
        research_objects=tuple(
            ResearchObject.model_validate_json(item.model_dump_json())
            for item in original.research_objects
        ),
        goals=tuple(
            ResearchGoal.model_validate_json(item.model_dump_json()) for item in original.goals
        ),
        schemes=tuple(
            ResearchSchemeSnapshot.model_validate_json(item.model_dump_json())
            for item in original.schemes
        ),
        runs=tuple(
            ResearchRun.model_validate_json(item.model_dump_json()) for item in original.runs
        ),
        planned_graphs=tuple(
            PlannedTaskGraph.model_validate_json(item.model_dump_json())
            for item in original.planned_graphs
        ),
        actual_graphs=tuple(
            ActualRuntimeGraph.model_validate_json(item.model_dump_json())
            for item in original.actual_graphs
        ),
        tasks=tuple(Task.model_validate_json(item.model_dump_json()) for item in original.tasks),
    )

    reconstructed = reconstruct_product_run(restarted)

    assert reconstructed.research_object.object_id == "OBJ-A"
    assert reconstructed.run.run_id == "RUN-A"
    assert reconstructed.goal.goal_id == "GOAL-A"
    assert reconstructed.scheme.scheme_id == "SCHEME-A"
    assert reconstructed.planned_graph.graph_id == "PLAN-A"
    assert reconstructed.actual_graph.value is not None
    assert reconstructed.actual_graph.value.graph_id == "ACTUAL-A"
    assert tuple(task.task_id for task in reconstructed.tasks) == ("TASK-A",)
    assert reconstructed.watermark == ProjectionWatermark(revision=7, sequence=0)
    assert reconstructed.watermark.etag("RUN-A") == '"p4:RUN-A:7:0"'
    assert reconstructed.review.availability.status is AvailabilityStatus.NOT_GENERATED
    assert reconstructed.canonical_record.availability.status is AvailabilityStatus.NOT_GENERATED
    assert reconstructed.released_result.availability.status is AvailabilityStatus.NOT_RELEASED


@pytest.mark.parametrize("missing", ["object", "run"])
def test_missing_exact_root_is_not_found_without_fallback(missing: str) -> None:
    snapshot = _snapshot()
    if missing == "object":
        snapshot = replace(snapshot, research_objects=())
    else:
        snapshot = replace(snapshot, runs=())

    with pytest.raises(ProductError) as exc_info:
        reconstruct_product_run(snapshot)

    _assert_product_error(exc_info, ErrorCodeV1.NOT_FOUND)
    assert exc_info.value.status_code == 404


def test_missing_referenced_child_is_integrity_failure_not_latest_lookup() -> None:
    with pytest.raises(ProductError) as exc_info:
        reconstruct_product_run(replace(_snapshot(), goals=()))

    _assert_product_error(exc_info, ErrorCodeV1.INTEGRITY_FAILURE)
    assert exc_info.value.status_code == 500


def test_foreign_row_is_identity_mismatch_even_when_it_is_the_only_candidate() -> None:
    snapshot = _snapshot()
    foreign = snapshot.runs[0].model_copy(update={"run_id": "RUN-FOREIGN"})

    with pytest.raises(ProductError) as exc_info:
        reconstruct_product_run(replace(snapshot, runs=(foreign,)))

    _assert_product_error(exc_info, ErrorCodeV1.IDENTITY_MISMATCH)
    assert exc_info.value.resource_id == "RUN-A"


def test_multiple_root_rows_are_rejected_without_first_or_latest_fallback() -> None:
    snapshot = _snapshot()
    foreign = snapshot.research_objects[0].model_copy(
        update={"object_id": "OBJ-FOREIGN", "updated_at": NOW.replace(hour=11)}
    )

    with pytest.raises(ProductError) as exc_info:
        reconstruct_product_run(
            replace(snapshot, research_objects=(snapshot.research_objects[0], foreign))
        )

    _assert_product_error(exc_info, ErrorCodeV1.INTEGRITY_FAILURE)


@pytest.mark.parametrize(
    ("changes", "reason_code"),
    [
        ({"projection_revision": None}, "PROJECTION_REVISION_NOT_PERSISTED"),
        ({"projection_sequence": None}, "PROJECTION_SEQUENCE_NOT_ATOMIC"),
    ],
)
def test_missing_atomic_watermark_fails_closed(
    changes: dict[str, object],
    reason_code: str,
) -> None:
    with pytest.raises(ProductError) as exc_info:
        reconstruct_product_run(replace(_snapshot(), **changes))

    _assert_product_error(exc_info, ErrorCodeV1.UNAVAILABLE, reason_code=reason_code)
    assert exc_info.value.status_code == 409


def test_torn_event_tail_is_integrity_failure_not_a_partial_projection() -> None:
    with pytest.raises(ProductError) as exc_info:
        reconstruct_product_run(replace(_snapshot(), projection_sequence=1, events=()))

    _assert_product_error(exc_info, ErrorCodeV1.INTEGRITY_FAILURE)
    assert exc_info.value.status_code == 500


def test_restart_review_fails_closed_without_complete_input_preimage() -> None:
    review = ReviewRecord(
        review_id="REVIEW-A",
        run_id="RUN-A",
        status=ReviewStatus.REVIEW,
        input_snapshot_hash="sha256:" + "a" * 64,
        created_at=NOW,
    )

    reconstructed = reconstruct_product_run(replace(_snapshot(), reviews=(review,)))

    assert reconstructed.review.value is None
    assert reconstructed.review.availability.status is AvailabilityStatus.UNAVAILABLE
    assert reconstructed.review.availability.reason_code == "REVIEW_INPUT_PREIMAGE_NOT_PERSISTED"


def test_restart_release_validation_fails_closed_without_hash_preimages() -> None:
    validation = PersistedReleaseValidation(
        validation_id="VALIDATION-A",
        run_id="RUN-A",
        object_id="OBJ-A",
        decision="ALLOWED",
        reason_codes=(),
        review_id="REVIEW-A",
        canonical_record_id="CER-A",
        released_result_id="RESULT-A",
        release_policy_version="phase4-release-eligibility/v1",
        review_policy_version="phase4-independent-financial-review/v1",
        proof_policy_id="proof-policy-v1",
        proof_policy_hash="sha256:" + "a" * 64,
        material_output_policy_version="phase4-full-material-output/v1",
        material_output_manifest_hash="sha256:" + "b" * 64,
        artifact_policy_version="phase4-html-required-pdf-optional/v1",
        artifact_manifest_hash="sha256:" + "c" * 64,
        review_input_snapshot_hash="sha256:" + "d" * 64,
        closure_hash="sha256:" + "e" * 64,
        evaluated_at=NOW,
        released_at=NOW,
    )
    snapshot = PersistedRunSnapshot(
        requested_object_id="OBJ-A",
        requested_run_id="RUN-A",
        release_validations=(validation,),
    )
    review = ReconstructedResource.available(
        SimpleNamespace(review_id="REVIEW-A", input_snapshot_hash="sha256:" + "d" * 64)
    )
    canonical = ReconstructedResource.available(SimpleNamespace(record_id="CER-A"))
    result = ReconstructedResource.available(
        SimpleNamespace(
            result_id="RESULT-A",
            run_id="RUN-A",
            released_at=NOW,
            released_metrics=(SimpleNamespace(calculation_id="CALC-A"),),
        )
    )
    proof = ReconstructedResource.available(
        SimpleNamespace(
            decisions=(SimpleNamespace(calculation_id="CALC-A", policy_id="proof-policy-v1"),)
        )
    )

    with pytest.raises(ProductError) as exc_info:
        _reconstruct_release_validation(
            snapshot,
            SimpleNamespace(object_id="OBJ-A"),
            SimpleNamespace(run_id="RUN-A", status=RunStatus.RELEASED),
            review,
            proof,
            canonical,
            result,
        )

    _assert_product_error(
        exc_info,
        ErrorCodeV1.UNAVAILABLE,
        reason_code="RELEASE_VALIDATION_PREIMAGE_NOT_PERSISTED",
    )
    assert exc_info.value.status_code == 409
