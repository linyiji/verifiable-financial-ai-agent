"""P4-BE-001 / P4-BC-001 pure Run collection contract gates."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from src.phase4_product.contracts import AvailabilityStatus, AvailabilityV1, ErrorCodeV1
from src.phase4_product.errors import ProductError
from src.phase4_product.projections import (
    ProjectionIntegrityError,
    RunCollectionSource,
    build_run_collection,
    project_run_collection_item,
)

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)
CURSOR_KEY = b"phase4-run-collection-test-signing-key-v1"


def _source(
    run_id: str,
    *,
    updated_at: datetime,
    object_id: str = "OBJ-A",
    status: str = "RUNNING",
    task_progress: float = 0.25,
) -> RunCollectionSource:
    terminal = status in {"RELEASED", "FAILED", "CANCELLED"}
    if status == "RELEASED":
        task_status = "COMPLETED"
        task_progress = 1.0
        availability = AvailabilityV1.available()
        release_closure_valid = True
        event_type = "run.completed"
        event_payload: dict[str, object] = {"status": "RELEASED"}
    elif status in {"FAILED", "CANCELLED"}:
        task_status = status
        availability = AvailabilityV1.unavailable(
            AvailabilityStatus.FAILED,
            "RUN_TERMINAL_WITHOUT_RELEASE",
        )
        release_closure_valid = False
        event_type = "run.failed"
        event_payload = {
            "status": status,
            "failure_stage": "EXECUTION",
            "failure_code": "RUN_TERMINAL_WITHOUT_RELEASE",
            "safe_message": "The run ended without a released result",
        }
    else:
        task_status = "RUNNING"
        availability = AvailabilityV1.unavailable(
            AvailabilityStatus.PENDING,
            "RUN_NONTERMINAL",
        )
        release_closure_valid = False
        event_type = "task.progress"
        event_payload = {
            "progress": task_progress,
            "progress_scale": "RATIO",
            "message_code": "TASK_PROGRESS",
        }

    task_id = f"TASK-{run_id}"
    graph_id = f"GRAPH-{run_id}"
    task = {
        "task_id": task_id,
        "run_id": run_id,
        "parent_task_id": None,
        "task_type": "research",
        "goal": "Collect exact retained inputs",
        "assigned_agent": "research-agent",
        "skill_id": "research-skill",
        "dependencies": (),
        "origin": "PLANNED",
        "reason_code": None,
        "status": task_status,
        "progress": task_progress,
        "attempt_count": 1,
        "task_input_evidence_ids": (),
        "task_output_evidence_ids": (),
        "evidence_acquisition_status": None,
        "evidence_source_coverage": {},
        "created_at": updated_at - timedelta(minutes=3),
    }
    run = {
        "run_id": run_id,
        "research_object_id": object_id,
        "goal_id": f"GOAL-{run_id}",
        "scheme_id": f"SCHEME-{run_id}",
        "status": status,
        "as_of": date(2026, 9, 5),
        "planned_graph_id": f"PLAN-{run_id}",
        "actual_graph_id": graph_id,
        "execution_target": "LOCAL",
        "created_at": updated_at - timedelta(minutes=4),
        "updated_at": updated_at,
        "started_at": updated_at - timedelta(minutes=3),
        "completed_at": updated_at - timedelta(seconds=1) if terminal else None,
    }
    research_object = {
        "object_id": object_id,
        "symbol": "ACME" if object_id == "OBJ-A" else "BETA",
        "company_name": "Acme Corp" if object_id == "OBJ-A" else "Beta Corp",
        "object_type": "public_company",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "currency": "USD",
        "identity_version": 1,
    }
    event = {
        "event_id": f"EVT-{run_id}",
        "run_id": run_id,
        "type": event_type,
        "sequence": 9,
        "timestamp": updated_at - timedelta(seconds=1),
        "task_id": None if terminal else task_id,
        "payload": event_payload,
    }
    return RunCollectionSource(
        run=run,
        research_object=research_object,
        actual_graph={
            "graph_id": graph_id,
            "run_id": run_id,
            "version": 2,
            "tasks": (task,),
        },
        latest_event=event,
        projection_revision=4,
        projection_sequence=9,
        result_availability=availability,
        release_closure_valid=release_closure_valid,
    )


def _corpus() -> list[RunCollectionSource]:
    return [
        _source("RUN-A2", updated_at=NOW, object_id="OBJ-A"),
        _source("RUN-B1", updated_at=NOW + timedelta(minutes=1), object_id="OBJ-B"),
        _source("RUN-A4", updated_at=NOW - timedelta(minutes=2), status="FAILED"),
        _source("RUN-A3", updated_at=NOW - timedelta(minutes=1), status="RELEASED"),
        _source("RUN-A1", updated_at=NOW, object_id="OBJ-A"),
        _source("RUN-B2", updated_at=NOW - timedelta(minutes=3), object_id="OBJ-B"),
    ]


def test_item_uses_exact_safe_projection_primitives() -> None:
    item = project_run_collection_item(_source("RUN-A", updated_at=NOW, task_progress=0.375))

    assert item.run_id == "RUN-A"
    assert item.object.model_dump() == {
        "object_id": "OBJ-A",
        "symbol": "ACME",
        "company_name": "Acme Corp",
    }
    assert (item.status, item.stage, item.terminal) == ("RUNNING", "RESEARCH", False)
    assert item.progress.model_dump() == {
        "method": "ACTUAL_TASK_MEAN_V1",
        "completed_tasks": 0,
        "total_tasks": 1,
        "fraction": 0.375,
    }
    assert item.graph_version == 2
    assert item.activity is not None
    assert (item.activity.event_id, item.activity.sequence) == ("EVT-RUN-A", 9)
    assert set(item.activity.model_dump(mode="json")) == {
        "event_id",
        "type",
        "sequence",
        "timestamp",
        "task_id",
        "message_code",
    }
    assert item.result_availability.status is AvailabilityStatus.PENDING


def test_collection_stably_orders_and_pages_by_updated_at_then_run_id_desc() -> None:
    corpus = _corpus()
    expected = ["RUN-B1", "RUN-A2", "RUN-A1", "RUN-A3", "RUN-A4", "RUN-B2"]
    observed: list[str] = []
    cursor: str | None = None

    while True:
        page = build_run_collection(
            sources=corpus,
            cursor_signing_key=CURSOR_KEY,
            limit=2,
            cursor=cursor,
        )
        observed.extend(item.run_id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert observed == expected
    assert len(observed) == len(set(observed))


def test_cursor_replays_identical_suffix_after_process_restart_and_input_reorder() -> None:
    corpus = _corpus()
    first = build_run_collection(
        sources=corpus,
        cursor_signing_key=CURSOR_KEY,
        limit=2,
    )
    assert first.next_cursor is not None

    resumed = build_run_collection(
        sources=list(reversed(corpus)),
        cursor_signing_key=bytes(CURSOR_KEY),
        limit=100,
        cursor=first.next_cursor,
    )
    assert [item.run_id for item in resumed.items] == [
        "RUN-A1",
        "RUN-A3",
        "RUN-A4",
        "RUN-B2",
    ]


def test_combined_filters_are_exact_and_status_values_are_or_members() -> None:
    page = build_run_collection(
        sources=_corpus(),
        cursor_signing_key=CURSOR_KEY,
        object_id="OBJ-A",
        statuses=("FAILED", "RUNNING"),
        result_availability=AvailabilityStatus.PENDING,
    )
    assert [item.run_id for item in page.items] == ["RUN-A2", "RUN-A1"]


def test_cursor_accepts_equivalent_normalized_status_filter_set() -> None:
    corpus = _corpus()
    first = build_run_collection(
        sources=corpus,
        cursor_signing_key=CURSOR_KEY,
        limit=1,
        object_id="OBJ-A",
        statuses=("FAILED", "RUNNING", "FAILED"),
    )
    assert first.next_cursor is not None

    resumed = build_run_collection(
        sources=corpus,
        cursor_signing_key=CURSOR_KEY,
        object_id="OBJ-A",
        statuses=("RUNNING", "FAILED"),
        cursor=first.next_cursor,
    )
    assert [item.run_id for item in resumed.items] == ["RUN-A1", "RUN-A4"]


@pytest.mark.parametrize(
    "changed_filters",
    [
        {"object_id": "OBJ-B"},
        {"statuses": ("FAILED",)},
        {"result_availability": AvailabilityStatus.AVAILABLE},
    ],
)
def test_cursor_is_bound_to_every_normalized_filter(
    changed_filters: dict[str, object],
) -> None:
    first = build_run_collection(
        sources=_corpus(),
        cursor_signing_key=CURSOR_KEY,
        limit=1,
    )
    assert first.next_cursor is not None

    with pytest.raises(ProductError) as raised:
        build_run_collection(
            sources=_corpus(),
            cursor_signing_key=CURSOR_KEY,
            cursor=first.next_cursor,
            **changed_filters,  # type: ignore[arg-type]
        )
    assert raised.value.code is ErrorCodeV1.INVALID_CURSOR
    assert raised.value.status_code == 400
    assert raised.value.envelope().error.recovery == "SNAPSHOT_RELOAD"


def test_tampered_cursor_fails_with_frozen_invalid_cursor_error() -> None:
    first = build_run_collection(sources=_corpus(), cursor_signing_key=CURSOR_KEY, limit=1)
    assert first.next_cursor is not None
    replacement = "0" if first.next_cursor[-1] != "0" else "1"
    tampered = first.next_cursor[:-1] + replacement

    with pytest.raises(ProductError) as raised:
        build_run_collection(
            sources=_corpus(),
            cursor_signing_key=CURSOR_KEY,
            cursor=tampered,
        )
    assert raised.value.code is ErrorCodeV1.INVALID_CURSOR


@pytest.mark.parametrize(
    "cursor",
    ["", "offset=2", " p4rc1.invalid.invalid", "p4rc2.payload.signature", "x" * 2049],
)
def test_malformed_cursor_never_falls_back_to_first_page(cursor: str) -> None:
    with pytest.raises(ProductError) as raised:
        build_run_collection(
            sources=_corpus(),
            cursor_signing_key=CURSOR_KEY,
            cursor=cursor,
        )
    assert raised.value.code is ErrorCodeV1.INVALID_CURSOR


def test_cursor_with_missing_ordering_tuple_is_expired_not_offset_fallback() -> None:
    corpus = _corpus()
    first = build_run_collection(
        sources=corpus,
        cursor_signing_key=CURSOR_KEY,
        limit=1,
    )
    assert first.next_cursor is not None

    without_marker = [source for source in corpus if source.run["run_id"] != "RUN-B1"]  # type: ignore[index]
    with pytest.raises(ProductError) as raised:
        build_run_collection(
            sources=without_marker,
            cursor_signing_key=CURSOR_KEY,
            cursor=first.next_cursor,
        )
    assert raised.value.code is ErrorCodeV1.INVALID_CURSOR


@pytest.mark.parametrize("limit", [0, 101, -1, True])
def test_limit_is_caller_controlled_but_strictly_bounded(limit: object) -> None:
    with pytest.raises(ProjectionIntegrityError):
        build_run_collection(
            sources=_corpus(),
            cursor_signing_key=CURSOR_KEY,
            limit=limit,  # type: ignore[arg-type]
        )


def test_empty_collection_has_no_cursor() -> None:
    page = build_run_collection(sources=(), cursor_signing_key=CURSOR_KEY)
    assert page.items == ()
    assert page.next_cursor is None


def test_duplicate_run_identity_fails_before_returning_a_partial_page() -> None:
    duplicate = _source("RUN-DUP", updated_at=NOW)
    moved = _source("RUN-DUP", updated_at=NOW - timedelta(minutes=1))
    with pytest.raises(ProjectionIntegrityError, match="duplicate Run"):
        build_run_collection(
            sources=(duplicate, moved),
            cursor_signing_key=CURSOR_KEY,
        )


def test_cross_object_run_relation_fails_closed() -> None:
    source = _source("RUN-CROSS", updated_at=NOW)
    contaminated = replace(
        source,
        research_object={**source.research_object, "object_id": "OBJ-B"},  # type: ignore[arg-type]
    )
    with pytest.raises(ProjectionIntegrityError, match="ownership closure"):
        project_run_collection_item(contaminated)


def test_unknown_status_and_unsafe_latest_event_fail_closed() -> None:
    source = _source("RUN-BAD", updated_at=NOW)
    unknown = replace(
        source,
        run={**source.run, "status": "ACTIVE"},  # type: ignore[arg-type]
    )
    with pytest.raises(ProjectionIntegrityError, match="unsupported Run status"):
        project_run_collection_item(unknown)

    unsafe_event = {
        **source.latest_event,  # type: ignore[arg-type]
        "payload": {
            "progress": 0.5,
            "progress_scale": "RATIO",
            "message_code": "TASK_PROGRESS",
            "raw_provider_payload": "secret",
        },
    }
    with pytest.raises(ProjectionIntegrityError, match="protected key"):
        project_run_collection_item(replace(source, latest_event=unsafe_event))


def test_watermark_graph_and_result_lifecycle_mismatches_fail_closed() -> None:
    source = _source("RUN-MISMATCH", updated_at=NOW)
    with pytest.raises(ProjectionIntegrityError, match="watermark"):
        project_run_collection_item(replace(source, projection_sequence=10))
    with pytest.raises(ProjectionIntegrityError, match="actual graph"):
        project_run_collection_item(replace(source, actual_graph=None))
    with pytest.raises(ProjectionIntegrityError, match="cannot expose an available result"):
        project_run_collection_item(replace(source, result_availability=AvailabilityV1.available()))


def test_cursor_signing_configuration_must_be_integrity_protecting() -> None:
    with pytest.raises(ProjectionIntegrityError, match="at least 32 bytes"):
        build_run_collection(sources=(), cursor_signing_key=b"short")


@pytest.mark.parametrize(
    ("status", "event_type", "event_status"),
    [
        ("RUNNING", "run.completed", "RELEASED"),
        ("RUNNING", "run.failed", "FAILED"),
        ("RELEASED", "task.progress", None),
        ("FAILED", "run.completed", "RELEASED"),
    ],
)
def test_latest_event_must_agree_with_terminal_lifecycle(
    status: str,
    event_type: str,
    event_status: str | None,
) -> None:
    source = _source("RUN-TERMINAL-EVENT", updated_at=NOW, status=status)
    payload: dict[str, object]
    task_id: str | None
    if event_type == "task.progress":
        payload = {
            "progress": 1.0,
            "progress_scale": "RATIO",
            "message_code": "TASK_PROGRESS",
        }
        task_id = "TASK-RUN-TERMINAL-EVENT"
    elif event_type == "run.failed":
        payload = {
            "status": event_status,
            "failure_stage": "EXECUTION",
            "failure_code": "RUN_TERMINAL_WITHOUT_RELEASE",
            "safe_message": "The run ended without a released result",
        }
        task_id = None
    else:
        payload = {"status": event_status}
        task_id = None
    latest_event = {
        **source.latest_event,  # type: ignore[arg-type]
        "type": event_type,
        "task_id": task_id,
        "payload": payload,
    }

    with pytest.raises(ProjectionIntegrityError, match="terminal"):
        project_run_collection_item(replace(source, latest_event=latest_event))


def test_malformed_cursor_wins_over_corrupt_source_projection() -> None:
    source = _source("RUN-CORRUPT", updated_at=NOW)
    corrupt = replace(
        source,
        run={**source.run, "status": "UNKNOWN"},  # type: ignore[arg-type]
    )

    with pytest.raises(ProductError) as raised:
        build_run_collection(
            sources=(corrupt,),
            cursor_signing_key=CURSOR_KEY,
            cursor="malformed-cursor",
        )
    assert raised.value.code is ErrorCodeV1.INVALID_CURSOR


def test_excluded_corrupt_sources_are_not_projected() -> None:
    included = _source("RUN-INCLUDED", updated_at=NOW, object_id="OBJ-A")
    foreign = _source("RUN-FOREIGN", updated_at=NOW, object_id="OBJ-B")
    foreign_corrupt = replace(
        foreign,
        run={**foreign.run, "status": "UNKNOWN"},  # type: ignore[arg-type]
    )
    status_excluded = _source(
        "RUN-STATUS-EXCLUDED",
        updated_at=NOW,
        object_id="OBJ-A",
        status="FAILED",
    )
    status_excluded_corrupt = replace(status_excluded, actual_graph=None)
    availability_excluded = _source(
        "RUN-AVAILABILITY-EXCLUDED",
        updated_at=NOW,
        object_id="OBJ-A",
    )
    availability_excluded_corrupt = replace(
        availability_excluded,
        actual_graph=None,
        result_availability=AvailabilityV1.unavailable(
            AvailabilityStatus.FAILED,
            "RESULT_ATTEMPT_FAILED",
        ),
    )

    page = build_run_collection(
        sources=(
            foreign_corrupt,
            status_excluded_corrupt,
            availability_excluded_corrupt,
            included,
        ),
        cursor_signing_key=CURSOR_KEY,
        object_id="OBJ-A",
        statuses=("RUNNING",),
        result_availability=AvailabilityStatus.PENDING,
    )

    assert [item.run_id for item in page.items] == ["RUN-INCLUDED"]


@pytest.mark.parametrize(
    ("run_changes", "event_changes", "error"),
    [
        ({"started_at": NOW + timedelta(seconds=1)}, {}, "started_at exceeds"),
        ({}, {"timestamp": NOW - timedelta(hours=1)}, "activity precedes"),
        ({"completed_at": NOW - timedelta(seconds=1)}, {}, "terminal status"),
    ],
)
def test_collection_rejects_inconsistent_lifecycle_timestamps(
    run_changes: dict[str, object],
    event_changes: dict[str, object],
    error: str,
) -> None:
    source = _source("RUN-TIME", updated_at=NOW)
    run = {**source.run, **run_changes}  # type: ignore[arg-type]
    latest_event = {**source.latest_event, **event_changes}  # type: ignore[arg-type]

    with pytest.raises(ProjectionIntegrityError, match=error):
        project_run_collection_item(replace(source, run=run, latest_event=latest_event))


@pytest.mark.parametrize("event_status", [None, "UNKNOWN", "FAILED", "REVIEW"])
def test_latest_status_change_must_match_current_nonterminal_run(
    event_status: str | None,
) -> None:
    source = _source("RUN-STATUS-CHANGE", updated_at=NOW)
    payload = {} if event_status is None else {"status": event_status}
    latest_event = {
        **source.latest_event,  # type: ignore[arg-type]
        "type": "run.status_changed",
        "task_id": None,
        "payload": payload,
    }

    with pytest.raises(ProjectionIntegrityError, match="status"):
        project_run_collection_item(replace(source, latest_event=latest_event))
