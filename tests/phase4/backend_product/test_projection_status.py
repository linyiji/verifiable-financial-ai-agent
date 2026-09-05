from __future__ import annotations

import math

import pytest

from src.phase4_product.projections import (
    ProjectionIntegrityError,
    calculate_run_progress,
    project_run_status,
    project_task_status,
)


@pytest.mark.parametrize(
    ("raw", "stage", "terminal", "outcome"),
    [
        ("DRAFT", "PREPARE", False, None),
        ("SCHEME_GENERATING", "PREPARE", False, None),
        ("AWAITING_CONFIRMATION", "CONFIRM", False, None),
        ("PLANNING", "PLANNING", False, None),
        ("RUNNING", "RESEARCH", False, None),
        ("REVIEW", "REVIEW", False, None),
        ("PROVING", "PROVING", False, None),
        ("RELEASED", "COMPLETE", True, "SUCCESS"),
        ("FAILED", "FAILED", True, "FAILURE"),
        ("CANCELLED", "CANCELLED", True, "CANCELLED"),
    ],
)
def test_run_status_projection_is_total_and_preserves_backend_status(
    raw: str,
    stage: str,
    terminal: bool,
    outcome: str | None,
) -> None:
    projection = project_run_status(raw)
    observed = (
        projection.status,
        projection.stage,
        projection.terminal,
        projection.terminal_outcome,
    )
    assert observed == (raw, stage, terminal, outcome)


@pytest.mark.parametrize(
    ("raw", "stage", "terminal"),
    [
        ("CREATED", "QUEUED", False),
        ("WAITING", "QUEUED", False),
        ("READY", "READY", False),
        ("RUNNING", "ACTIVE", False),
        ("WAITING_FOR_CAPABILITY", "WAITING_SUPPORT", False),
        ("SELF_CORRECTING", "CORRECTING", False),
        ("BLOCKED", "BLOCKED", False),
        ("REVIEW", "REVIEW", False),
        ("COMPLETED", "COMPLETE", True),
        ("FAILED", "FAILED", True),
        ("CAPABILITY_BUILD_FAILED", "FAILED", True),
        ("CANCELLED", "CANCELLED", True),
    ],
)
def test_task_status_projection_is_total_and_preserves_backend_status(
    raw: str,
    stage: str,
    terminal: bool,
) -> None:
    projection = project_task_status(raw)
    assert (projection.status, projection.stage, projection.terminal) == (raw, stage, terminal)


@pytest.mark.parametrize("unknown", ["", "ACTIVE", "PASS_WITH_UNCERTAINTY", "UNKNOWN"])
def test_unknown_status_fails_closed_without_guessing(unknown: str) -> None:
    with pytest.raises(ProjectionIntegrityError):
        project_run_status(unknown)
    with pytest.raises(ProjectionIntegrityError):
        project_task_status(unknown)


def test_progress_is_unweighted_actual_task_mean_with_backend_counts() -> None:
    tasks = [
        {"status": "COMPLETED", "progress": 1.0},
        {"status": "RUNNING", "progress": 0.25},
        {"status": "READY", "progress": 0.0},
    ]
    progress = calculate_run_progress(tasks, run_status="RUNNING")

    assert progress.method == "ACTUAL_TASK_MEAN_V1"
    assert progress.completed_tasks == 1
    assert progress.total_tasks == 3
    assert progress.fraction == pytest.approx(1.25 / 3)
    assert "percent" not in progress.model_dump(mode="json")


def test_progress_is_zero_for_a_run_with_no_actual_tasks() -> None:
    progress = calculate_run_progress([], run_status="PLANNING")
    assert (progress.completed_tasks, progress.total_tasks, progress.fraction) == (0, 0, 0.0)


def test_released_progress_requires_release_closure_and_is_exactly_one() -> None:
    tasks = [{"status": "RUNNING", "progress": 0.4}]
    with pytest.raises(ProjectionIntegrityError, match="release closure"):
        calculate_run_progress(tasks, run_status="RELEASED")

    released = calculate_run_progress(
        tasks,
        run_status="RELEASED",
        release_closure_valid=True,
    )
    assert released.fraction == 1.0


@pytest.mark.parametrize("run_status", ["FAILED", "CANCELLED"])
def test_unsuccessful_terminal_run_is_one_only_when_every_task_is_terminal(
    run_status: str,
) -> None:
    terminal = calculate_run_progress(
        [
            {"status": "FAILED", "progress": 0.3},
            {"status": "CANCELLED", "progress": 0.6},
        ],
        run_status=run_status,
    )
    unfinished = calculate_run_progress(
        [
            {"status": "FAILED", "progress": 0.3},
            {"status": "RUNNING", "progress": 0.6},
        ],
        run_status=run_status,
    )

    assert terminal.fraction == 1.0
    assert unfinished.fraction == pytest.approx(0.45)


def test_adding_an_actual_task_may_honestly_lower_progress() -> None:
    before = calculate_run_progress(
        [{"status": "RUNNING", "progress": 0.8}],
        run_status="RUNNING",
    )
    after = calculate_run_progress(
        [
            {"status": "RUNNING", "progress": 0.8},
            {"status": "CREATED", "progress": 0.0},
        ],
        run_status="RUNNING",
    )
    assert after.fraction < before.fraction


@pytest.mark.parametrize("bad_progress", [-0.01, 1.01, math.nan, math.inf, "half"])
def test_invalid_task_progress_fails_closed(bad_progress: object) -> None:
    with pytest.raises(ProjectionIntegrityError):
        calculate_run_progress(
            [{"status": "RUNNING", "progress": bad_progress}],
            run_status="RUNNING",
        )
