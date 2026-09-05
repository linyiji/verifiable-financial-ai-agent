"""Direct integrity tests for the all-or-nothing Confirm write set."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from src.domain.enums import RunStatus, TaskStatus
from src.domain.research_goal import ResearchGoal
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.domain.task import PlannedTaskGraph, Task
from src.phase4_product.admission import (
    ResearchRunDraftRecordV1,
    build_prepare_draft,
    build_run_admission,
    build_scheduler_admission,
    confirmation_request_hash,
    mark_draft_consumed,
    validate_confirm_request,
)
from src.phase4_product.contracts import (
    ConfirmResearchRunRequestV1,
    GoalProjectionV1,
    PrepareResearchRunRequestV1,
    SchemeProjectionV1,
)
from src.phase4_product.durability import (
    AtomicConfirmCommit,
    DurableIdempotencyOutcomeV1,
)
from src.phase4_product.errors import ProductError
from src.phase4_product.hashing import idempotency_key_digest

NOW = datetime(2026, 9, 5, 9, tzinfo=UTC)
ADMITTED_AT = NOW + timedelta(minutes=1)
IDEMPOTENCY_KEY = "confirm-key-a"


def _confirm_commit() -> AtomicConfirmCommit:
    prepare_request = PrepareResearchRunRequestV1(
        research_object_id="OBJ-A",
        research_goal="Prove one exact durable Confirm write set",
        as_of=date(2026, 9, 5),
        preferences={"currency": "USD"},
    )
    goal_projection = GoalProjectionV1(
        goal_id="GOAL-A",
        research_object_id="OBJ-A",
        goal_text=prepare_request.research_goal,
        as_of=prepare_request.as_of,
        preferences=prepare_request.preferences,
        created_at=NOW,
    )
    scheme_projection = SchemeProjectionV1(
        scheme_id="SCHEME-A",
        research_object_id="OBJ-A",
        goal_id="GOAL-A",
        research_scope=("fundamentals",),
        generated_by="planner-v1",
        created_at=NOW,
    )
    draft = build_prepare_draft(
        prepare_request,
        draft_id="DRAFT-A",
        goal=goal_projection,
        scheme_snapshot=scheme_projection,
        created_at=NOW,
    )
    request = ConfirmResearchRunRequestV1(
        draft_id=draft.draft_id,
        draft_version=draft.draft_version,
        draft_hash=draft.draft_hash,
        research_object_id=draft.object_id,
        confirm_scheme=True,
    )
    validated = validate_confirm_request(draft, request, now=ADMITTED_AT)
    admission = build_run_admission(
        validated,
        admission_id="ADMISSION-A",
        run_id="RUN-A",
        planned_graph_id="GRAPH-A",
        admitted_at=ADMITTED_AT,
    )
    outcome = DurableIdempotencyOutcomeV1(
        outcome_id="OUTCOME-A",
        effective_access_scope_key="LOCAL_SINGLE_USER",
        idempotency_key_digest=idempotency_key_digest(
            IDEMPOTENCY_KEY,
            method="POST",
            route_template="/api/research-runs",
        ),
        method="POST",
        route_template="/api/research-runs",
        confirmation_request_hash=validated.confirmation_request_hash,
        admission=admission,
        created_at=ADMITTED_AT,
    )
    goal = ResearchGoal.model_validate(draft.goal.model_dump(mode="python"))
    scheme = ResearchSchemeSnapshot.model_validate(
        {
            **draft.scheme_snapshot.model_dump(mode="python"),
            "confirmed_at": ADMITTED_AT,
        }
    )
    task = Task(
        task_id="TASK-A",
        run_id="RUN-A",
        task_type="research",
        goal="Collect exact evidence",
        assigned_agent="research-agent",
        skill_id="research-skill",
        status=TaskStatus.CREATED,
        created_at=ADMITTED_AT,
    )
    planned_graph = PlannedTaskGraph(
        graph_id="GRAPH-A",
        run_id="RUN-A",
        tasks=[task],
        created_at=ADMITTED_AT,
    )
    run = ResearchRun(
        run_id="RUN-A",
        research_object_id="OBJ-A",
        goal_id="GOAL-A",
        scheme_id="SCHEME-A",
        status=RunStatus.PLANNING,
        as_of=date(2026, 9, 5),
        planned_graph_id="GRAPH-A",
        created_at=ADMITTED_AT,
    )
    return AtomicConfirmCommit(
        consumed_draft=mark_draft_consumed(
            draft,
            admission=admission,
            consumed_at=ADMITTED_AT,
        ),
        idempotency_outcome=outcome,
        idempotency_key=IDEMPOTENCY_KEY,
        request=request,
        scheduler_admission=build_scheduler_admission(
            admission,
            idempotency_outcome_id=outcome.outcome_id,
            created_at=ADMITTED_AT,
        ),
        goal=goal,
        scheme=scheme,
        run=run,
        planned_graph=planned_graph,
        actual_graph=None,
        tasks=(task,),
        initial_events=(
            RuntimeEvent(
                event_id="EVENT-CREATED-A",
                run_id="RUN-A",
                type=RuntimeEventType.RUN_CREATED,
                sequence=1,
                timestamp=ADMITTED_AT,
                payload={"object_id": "OBJ-A"},
            ),
            RuntimeEvent(
                event_id="EVENT-SCHEME-GENERATED-A",
                run_id="RUN-A",
                type=RuntimeEventType.SCHEME_GENERATED,
                sequence=2,
                timestamp=ADMITTED_AT,
                payload={
                    "scheme_id": "SCHEME-A",
                    "generated_by": "planner-v1",
                    "generated_at": NOW.isoformat(),
                    "generation_stage": "prepare",
                    "retrospective": True,
                },
            ),
            RuntimeEvent(
                event_id="EVENT-SCHEME-CONFIRMED-A",
                run_id="RUN-A",
                type=RuntimeEventType.SCHEME_CONFIRMED,
                sequence=3,
                timestamp=ADMITTED_AT,
                payload={"scheme_id": "SCHEME-A"},
            ),
            RuntimeEvent(
                event_id="EVENT-PLAN-GENERATED-A",
                run_id="RUN-A",
                type=RuntimeEventType.PLAN_GENERATED,
                sequence=4,
                timestamp=ADMITTED_AT,
                payload={"graph_id": "GRAPH-A", "task_count": 1},
            ),
            RuntimeEvent(
                event_id="EVENT-TASK-CREATED-A",
                run_id="RUN-A",
                task_id="TASK-A",
                type=RuntimeEventType.TASK_CREATED,
                sequence=5,
                timestamp=ADMITTED_AT,
                payload={"task_type": "research"},
            ),
        ),
    )


def test_atomic_confirm_commit_binds_request_scope_key_and_write_set() -> None:
    commit = _confirm_commit()

    assert commit.request.draft_id == commit.consumed_draft.draft.draft_id
    assert commit.idempotency_outcome.effective_access_scope_key == "LOCAL_SINGLE_USER"
    assert commit.scheduler_admission.run_id == commit.run.run_id
    assert not hasattr(commit, "idempotency_key")


def test_atomic_confirm_rejects_internally_consistent_unbound_request_hash() -> None:
    commit = _confirm_commit()
    unrelated_hash = "sha256:" + "f" * 64
    admission = commit.idempotency_outcome.admission.model_copy(
        update={"confirmation_request_hash": unrelated_hash}
    )
    outcome = DurableIdempotencyOutcomeV1(
        outcome_id=commit.idempotency_outcome.outcome_id,
        effective_access_scope_key="LOCAL_SINGLE_USER",
        idempotency_key_digest=commit.idempotency_outcome.idempotency_key_digest,
        method="POST",
        route_template="/api/research-runs",
        confirmation_request_hash=unrelated_hash,
        admission=admission,
        created_at=commit.idempotency_outcome.created_at,
    )

    with pytest.raises(ProductError, match="does not bind"):
        replace(
            commit,
            idempotency_outcome=outcome,
            idempotency_key=IDEMPOTENCY_KEY,
        )


def test_atomic_confirm_rejects_a_raw_key_that_does_not_match_stored_digest() -> None:
    with pytest.raises(ProductError, match="key digest"):
        replace(_confirm_commit(), idempotency_key="another-confirm-key")


@pytest.mark.parametrize(
    "event_type",
    [
        RuntimeEventType.RUN_STARTED,
        RuntimeEventType.RUN_COMPLETED,
        RuntimeEventType.RUN_FAILED,
        RuntimeEventType.RELEASE_COMPLETED,
        RuntimeEventType.TASK_COMPLETED,
    ],
)
def test_atomic_confirm_rejects_scheduler_start_and_terminal_initial_events(
    event_type: RuntimeEventType,
) -> None:
    commit = _confirm_commit()
    forbidden = RuntimeEvent(
        event_id=f"EVENT-{event_type.name}",
        run_id="RUN-A",
        type=event_type,
        sequence=6,
        timestamp=ADMITTED_AT,
    )

    with pytest.raises(ProductError, match="outside the frozen setup phase"):
        replace(
            commit,
            initial_events=(*commit.initial_events, forbidden),
            idempotency_key=IDEMPOTENCY_KEY,
        )


def test_atomic_confirm_rejects_goal_or_scheme_drift_from_prepared_draft() -> None:
    commit = _confirm_commit()
    changed_goal = commit.goal.model_copy(update={"goal_text": "different goal"})

    with pytest.raises(ProductError, match="immutable prepared draft"):
        replace(
            commit,
            goal=changed_goal,
            idempotency_key=IDEMPOTENCY_KEY,
        )


@pytest.mark.parametrize(
    "run_update",
    [
        {"goal_id": "GOAL-B"},
        {"scheme_id": "SCHEME-B"},
        {"as_of": date(2026, 9, 4)},
    ],
)
def test_atomic_confirm_rejects_run_goal_scheme_or_as_of_drift(
    run_update: dict[str, object],
) -> None:
    commit = _confirm_commit()

    with pytest.raises(ProductError, match="closure|identities"):
        replace(
            commit,
            run=commit.run.model_copy(update=run_update),
            idempotency_key=IDEMPOTENCY_KEY,
        )


def test_atomic_confirm_rejects_tampered_draft_even_when_all_copies_agree() -> None:
    commit = _confirm_commit()
    bad_hash = "sha256:" + "e" * 64
    tampered_draft = commit.consumed_draft.draft.model_copy(update={"draft_hash": bad_hash})
    consumed = ResearchRunDraftRecordV1(
        draft=tampered_draft,
        consumed_at=commit.consumed_draft.consumed_at,
        consumed_admission_id=commit.consumed_draft.consumed_admission_id,
        consumed_run_id=commit.consumed_draft.consumed_run_id,
    )
    request = commit.request.model_copy(update={"draft_hash": bad_hash})
    request_hash = confirmation_request_hash(request)
    admission = commit.idempotency_outcome.admission.model_copy(
        update={
            "draft_hash": bad_hash,
            "confirmation_request_hash": request_hash,
        }
    )
    outcome = DurableIdempotencyOutcomeV1(
        outcome_id=commit.idempotency_outcome.outcome_id,
        effective_access_scope_key="LOCAL_SINGLE_USER",
        idempotency_key_digest=commit.idempotency_outcome.idempotency_key_digest,
        method="POST",
        route_template="/api/research-runs",
        confirmation_request_hash=request_hash,
        admission=admission,
        created_at=commit.idempotency_outcome.created_at,
    )

    with pytest.raises(ProductError, match="immutable hash check"):
        replace(
            commit,
            consumed_draft=consumed,
            request=request,
            idempotency_outcome=outcome,
            idempotency_key=IDEMPOTENCY_KEY,
        )


def test_atomic_confirm_rejects_prestarted_pending_scheduler_row() -> None:
    commit = _confirm_commit()
    scheduler = commit.scheduler_admission.model_copy(
        update={
            "start_committed_at": ADMITTED_AT,
            "run_started_event_id": "EVENT-START-A",
            "run_started_sequence": 99,
        }
    )

    with pytest.raises(ProductError, match="pristine PENDING"):
        replace(
            commit,
            scheduler_admission=scheduler,
            idempotency_key=IDEMPOTENCY_KEY,
        )


@pytest.mark.parametrize(
    "run_update",
    [
        {"started_at": ADMITTED_AT},
        {"completed_at": ADMITTED_AT},
        {"started_at": ADMITTED_AT, "completed_at": ADMITTED_AT},
    ],
)
def test_atomic_confirm_rejects_run_with_runtime_timestamps(
    run_update: dict[str, object],
) -> None:
    commit = _confirm_commit()

    with pytest.raises(ProductError, match="pristine frozen PLANNING"):
        replace(
            commit,
            run=commit.run.model_copy(update=run_update),
            idempotency_key=IDEMPOTENCY_KEY,
        )


def test_atomic_confirm_rejects_cross_run_task_hidden_under_same_id() -> None:
    commit = _confirm_commit()
    foreign_task = commit.planned_graph.tasks[0].model_copy(update={"run_id": "RUN-B"})
    graph = commit.planned_graph.model_copy(update={"tasks": [foreign_task]})

    with pytest.raises(ProductError, match="Task rows disagree"):
        replace(
            commit,
            planned_graph=graph,
            idempotency_key=IDEMPOTENCY_KEY,
        )


@pytest.mark.parametrize(
    ("event_index", "payload"),
    [
        (0, {"object_id": "OBJ-B"}),
        (4, {"task_type": "wrong"}),
    ],
)
def test_atomic_confirm_rejects_setup_event_payload_substitution(
    event_index: int,
    payload: dict[str, object],
) -> None:
    commit = _confirm_commit()
    events = list(commit.initial_events)
    events[event_index] = events[event_index].model_copy(update={"payload": payload})

    with pytest.raises(ProductError, match="payload does not bind|does not bind one CREATED"):
        replace(
            commit,
            initial_events=tuple(events),
            idempotency_key=IDEMPOTENCY_KEY,
        )


def test_atomic_confirm_rejects_incomplete_setup_event_inventory() -> None:
    commit = _confirm_commit()

    with pytest.raises(ProductError, match="inventory/order is incomplete"):
        replace(
            commit,
            initial_events=commit.initial_events[:-1],
            idempotency_key=IDEMPOTENCY_KEY,
        )
