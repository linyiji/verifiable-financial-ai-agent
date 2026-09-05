from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.events import prepare_completed_run_event_stream
from src.domain.enums import RunStatus
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.domain.task import PlannedTaskGraph
from src.infrastructure.database.checkpoints import SQLAlchemyCheckpointStore
from src.infrastructure.database.models import RuntimeCheckpointRow
from src.runtime.checkpoint import RuntimeCheckpoint, RuntimeCheckpointIntegrityError
from src.runtime.events import (
    CursorErrorCode,
    CursorPreflightError,
    EventApplyDisposition,
    EventReconciliationRequired,
    EventRecoveryReason,
    EventSequenceError,
    InMemoryRuntimeEventStore,
    RuntimeEventCursor,
    parse_resume_cursor,
)
from src.runtime.sse import (
    UnsupportedRuntimeEventError,
    preflight_runtime_event_stream,
    runtime_event_stream,
)
from src.runtime.state import RuntimeState


def event(
    sequence: int,
    *,
    run_id: str = "RUN-A",
    event_id: str | None = None,
    event_type: RuntimeEventType = RuntimeEventType.TASK_PROGRESS,
    payload: dict[str, object] | None = None,
) -> RuntimeEvent:
    return RuntimeEvent(
        event_id=event_id or f"EVT-{sequence}",
        run_id=run_id,
        task_id="TASK-A" if event_type is RuntimeEventType.TASK_PROGRESS else None,
        type=event_type,
        sequence=sequence,
        payload=payload or {},
    )


class InjectedDeliveryStore(InMemoryRuntimeEventStore):
    def __init__(self, deliveries: Sequence[RuntimeEvent]) -> None:
        super().__init__()
        self.deliveries = list(deliveries)

    async def wait_for_events(
        self,
        run_id: str,
        *,
        after_sequence: int,
        timeout_seconds: float,
    ) -> list[RuntimeEvent]:
        del run_id, after_sequence, timeout_seconds
        deliveries, self.deliveries = self.deliveries, []
        return [item.model_copy(deep=True) for item in deliveries]


@pytest.mark.parametrize(
    "cursor",
    ["", "01", "+1", "-1", " 1", "1 ", "9223372036854775808", "opaque/id", "事件"],
)
def test_cursor_parser_rejects_noncanonical_values_without_coercion(cursor: str) -> None:
    with pytest.raises(CursorPreflightError) as raised:
        parse_resume_cursor(cursor)

    assert raised.value.code is CursorErrorCode.INVALID_CURSOR
    assert raised.value.status_code == 400
    assert raised.value.recovery == "SNAPSHOT_RELOAD"


def test_cursor_parser_accepts_only_frozen_numeric_and_opaque_families() -> None:
    assert parse_resume_cursor(None) == ("numeric", 0)
    assert parse_resume_cursor("0") == ("numeric", 0)
    assert parse_resume_cursor("9223372036854775807") == (
        "numeric",
        9223372036854775807,
    )
    assert parse_resume_cursor("EVT-a_b.c:1") == ("opaque", "EVT-a_b.c:1")


def test_cursor_parser_rejects_oversized_numeric_input_with_typed_error() -> None:
    with pytest.raises(CursorPreflightError) as exc_info:
        parse_resume_cursor("9" * 5_000)

    assert exc_info.value.code is CursorErrorCode.INVALID_CURSOR
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_cursor_preflight_is_exact_run_and_rejects_unknown_foreign_and_ahead() -> None:
    store = InMemoryRuntimeEventStore()
    first = await store.emit(run_id="RUN-A", event_type=RuntimeEventType.RUN_STARTED)
    second = await store.emit(
        run_id="RUN-A",
        event_type=RuntimeEventType.TASK_PROGRESS,
        task_id="TASK-A",
        payload={"progress": 0.5, "stage": "analysis"},
    )
    foreign = await store.emit(run_id="RUN-B", event_type=RuntimeEventType.RUN_STARTED)

    assert (await store.preflight_cursor("RUN-A", "1")).sequence == first.sequence
    assert (await store.preflight_cursor("RUN-A", second.event_id)).sequence == second.sequence

    for invalid in (foreign.event_id, "EVT-UNKNOWN"):
        with pytest.raises(CursorPreflightError) as raised:
            await store.preflight_cursor("RUN-A", invalid)
        assert raised.value.code is CursorErrorCode.INVALID_CURSOR
        assert raised.value.status_code == 400

    with pytest.raises(CursorPreflightError) as raised:
        await store.preflight_cursor("RUN-A", "3")
    assert raised.value.code is CursorErrorCode.CURSOR_AHEAD
    assert raised.value.status_code == 409


@pytest.mark.asyncio
async def test_prepared_resume_replays_strict_suffix_through_terminal_then_closes() -> None:
    store = InMemoryRuntimeEventStore()
    first = await store.emit(run_id="RUN-A", event_type=RuntimeEventType.RUN_STARTED)
    second = await store.emit(
        run_id="RUN-A",
        event_type=RuntimeEventType.TASK_PROGRESS,
        task_id="TASK-A",
        payload={"progress": 0.5, "stage": "analysis"},
    )
    terminal = await store.emit(
        run_id="RUN-A",
        event_type=RuntimeEventType.RUN_FAILED,
        payload={
            "status": "FAILED",
            "failure_stage": "TASK_EXECUTION",
            "failure_code": "SAFE_FAILURE",
        },
    )

    prepared = await prepare_completed_run_event_stream(
        store=store,
        run_id="RUN-A",
        last_event_id=str(first.sequence),
        heartbeat_seconds=0.01,
    )
    frames = [frame async for frame in prepared.body]

    assert [frame.splitlines()[0] for frame in frames] == [
        f"id: {second.sequence}",
        f"id: {terminal.sequence}",
    ]
    assert all(": heartbeat" not in frame for frame in frames)
    assert prepared.preflight.cursor.sequence == first.sequence


@pytest.mark.asyncio
async def test_terminal_at_cursor_returns_terminal_headers_and_zero_frames() -> None:
    store = InMemoryRuntimeEventStore()
    await store.emit(run_id="RUN-A", event_type=RuntimeEventType.RUN_STARTED)
    terminal = await store.emit(
        run_id="RUN-A",
        event_type=RuntimeEventType.RUN_FAILED,
        payload={
            "status": "CANCELLED",
            "failure_stage": "CANCELLATION",
            "failure_code": "RUN_CANCELLED",
        },
    )

    prepared = await prepare_completed_run_event_stream(
        store=store,
        run_id="RUN-A",
        last_event_id=terminal.event_id,
        heartbeat_seconds=0.01,
    )

    assert prepared.preflight.cursor.terminal_at_cursor is True
    assert prepared.preflight.cursor.terminal_outcome == "CANCELLED"
    assert prepared.response_headers["X-Run-Terminal"] == "true"
    assert prepared.response_headers["X-Terminal-Sequence"] == str(terminal.sequence)
    assert [frame async for frame in prepared.body] == []


@pytest.mark.asyncio
async def test_bad_cursor_fails_during_preflight_not_during_body_iteration() -> None:
    store = InMemoryRuntimeEventStore()
    await store.emit(run_id="RUN-A", event_type=RuntimeEventType.RUN_STARTED)

    with pytest.raises(CursorPreflightError) as raised:
        await prepare_completed_run_event_stream(
            store=store,
            run_id="RUN-A",
            last_event_id="99",
        )

    assert raised.value.code is CursorErrorCode.CURSOR_AHEAD


def test_event_cursor_is_idempotent_only_for_exact_canonical_duplicate() -> None:
    cursor = RuntimeEventCursor(run_id="RUN-A")
    accepted = event(1)

    assert cursor.accept(accepted) is EventApplyDisposition.APPLIED
    assert cursor.accept(accepted.model_copy(deep=True)) is EventApplyDisposition.DUPLICATE_IGNORED

    with pytest.raises(EventReconciliationRequired) as raised:
        cursor.accept(accepted.model_copy(update={"payload": {"progress": 0.5}}))
    assert raised.value.reason is EventRecoveryReason.CONFLICTING_DUPLICATE
    assert cursor.committed_sequence == 1


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        (event(2, run_id="RUN-B"), EventRecoveryReason.WRONG_RUN),
        (event(3), EventRecoveryReason.SEQUENCE_GAP),
    ],
)
def test_event_cursor_quarantines_foreign_and_gapped_events_without_advancing(
    candidate: RuntimeEvent,
    reason: EventRecoveryReason,
) -> None:
    cursor = RuntimeEventCursor(run_id="RUN-A", committed_sequence=1)

    with pytest.raises(EventReconciliationRequired) as raised:
        cursor.accept(candidate)

    assert raised.value.reason is reason
    assert cursor.committed_sequence == 1


def test_event_cursor_quarantines_stale_unseen_and_post_terminal_events() -> None:
    stale_cursor = RuntimeEventCursor(run_id="RUN-A", committed_sequence=2)
    with pytest.raises(EventReconciliationRequired) as stale:
        stale_cursor.accept(event(1))
    assert stale.value.reason is EventRecoveryReason.STALE_EVENT
    assert stale_cursor.committed_sequence == 2

    terminal_cursor = RuntimeEventCursor(run_id="RUN-A")
    terminal_cursor.accept(event(1, event_type=RuntimeEventType.RUN_COMPLETED))
    with pytest.raises(EventReconciliationRequired) as post_terminal:
        terminal_cursor.accept(event(2))
    assert post_terminal.value.reason is EventRecoveryReason.POST_TERMINAL_EVENT
    assert terminal_cursor.committed_sequence == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("delivered", "reason"),
    [
        (event(2), EventRecoveryReason.SEQUENCE_GAP),
        (event(1, run_id="RUN-B"), EventRecoveryReason.WRONG_RUN),
    ],
)
async def test_stream_quarantines_invalid_delivery_before_emitting_a_frame(
    delivered: RuntimeEvent,
    reason: EventRecoveryReason,
) -> None:
    store = InjectedDeliveryStore([delivered])
    admitted = await preflight_runtime_event_stream(store=store, run_id="RUN-A")
    stream = runtime_event_stream(
        store=store,
        run_id="RUN-A",
        heartbeat_seconds=0.01,
        preflight=admitted,
    )

    with pytest.raises(EventReconciliationRequired) as raised:
        await anext(stream)

    assert raised.value.reason is reason
    assert raised.value.committed_sequence == 0


@pytest.mark.asyncio
async def test_stream_quarantines_unsupported_batch_without_emitting_valid_prefix() -> None:
    store = InjectedDeliveryStore(
        [
            event(1, payload={"progress": 0.5, "stage": "analysis"}),
            event(2, event_type=RuntimeEventType.SCHEME_GENERATION_STARTED),
        ]
    )
    admitted = await preflight_runtime_event_stream(store=store, run_id="RUN-A")
    stream = runtime_event_stream(
        store=store,
        run_id="RUN-A",
        heartbeat_seconds=0.01,
        preflight=admitted,
    )

    with pytest.raises(UnsupportedRuntimeEventError) as raised:
        await anext(stream)

    assert raised.value.run_id == "RUN-A"
    assert raised.value.sequence == 2


@pytest.mark.asyncio
async def test_invalid_terminal_payload_fails_before_stream_is_prepared() -> None:
    store = InMemoryRuntimeEventStore()
    terminal = await store.emit(
        run_id="RUN-A",
        event_type=RuntimeEventType.RUN_FAILED,
        payload={"status": "FAILED", "failure_code": "SAFE_FAILURE"},
    )

    with pytest.raises(UnsupportedRuntimeEventError) as raised:
        await prepare_completed_run_event_stream(
            store=store,
            run_id="RUN-A",
            last_event_id=terminal.event_id,
        )

    assert raised.value.sequence == terminal.sequence


@pytest.mark.asyncio
async def test_store_rejects_business_events_after_terminal() -> None:
    store = InMemoryRuntimeEventStore()
    await store.emit(
        run_id="RUN-A",
        event_type=RuntimeEventType.RUN_FAILED,
        payload={"status": "FAILED", "failure_code": "SAFE_FAILURE"},
    )

    with pytest.raises(EventSequenceError, match="already terminal"):
        await store.emit(run_id="RUN-A", event_type=RuntimeEventType.TASK_PROGRESS)


def checkpoint_fixture() -> tuple[PlannedTaskGraph, RuntimeCheckpoint]:
    planned_graph = PlannedTaskGraph(
        graph_id="PLAN-A",
        run_id="RUN-A",
        tasks=[],
    )
    state = RuntimeState.create(
        run_id="RUN-A",
        planned_graph=planned_graph,
        actual_graph_id="ACTUAL-A",
    )
    return planned_graph, RuntimeCheckpoint.capture(
        checkpoint_id="CHECKPOINT-A",
        state=state,
    )


def test_checkpoint_capture_and_restore_bind_both_exact_graph_identities() -> None:
    planned_graph, checkpoint = checkpoint_fixture()

    restored = checkpoint.restore(planned_graph=planned_graph)

    assert checkpoint.planned_graph_id == "PLAN-A"
    assert checkpoint.actual_graph_id == "ACTUAL-A"
    assert restored.planned_graph.graph_id == checkpoint.planned_graph_id
    assert restored.actual_graph.graph_id == checkpoint.actual_graph_id


def test_checkpoint_restore_rejects_same_run_wrong_planned_graph_identity() -> None:
    planned_graph, checkpoint = checkpoint_fixture()
    wrong_planned_graph = planned_graph.model_copy(update={"graph_id": "PLAN-B"})

    with pytest.raises(RuntimeCheckpointIntegrityError, match="planned graph identities"):
        checkpoint.restore(planned_graph=wrong_planned_graph)


def test_checkpoint_restore_rejects_same_run_wrong_actual_graph_identity() -> None:
    planned_graph, checkpoint = checkpoint_fixture()
    wrong_checkpoint = checkpoint.model_copy(update={"actual_graph_id": "ACTUAL-B"})

    with pytest.raises(RuntimeCheckpointIntegrityError, match="actual graph identity"):
        wrong_checkpoint.restore(planned_graph=planned_graph)


@pytest.mark.asyncio
async def test_checkpoint_load_rejects_cross_run_payload_before_restore(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'checkpoint.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(RuntimeCheckpointRow.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    foreign = RuntimeCheckpoint(
        checkpoint_id="CHECKPOINT-A",
        run_id="RUN-B",
        planned_graph_id="PLAN-B",
        actual_graph_id="GRAPH-B",
        run_status=RunStatus.RUNNING,
        task_states={},
        actual_graph_version=1,
        actual_graph={
            "graph_id": "GRAPH-B",
            "run_id": "RUN-B",
            "version": 1,
            "tasks": [],
            "mutation_history": [],
        },
    )
    async with sessions() as session:
        session.add(
            RuntimeCheckpointRow(
                checkpoint_id=foreign.checkpoint_id,
                run_id="RUN-A",
                created_at=foreign.created_at,
                payload=foreign.model_dump(mode="json"),
            )
        )
        await session.commit()

    with pytest.raises(RuntimeCheckpointIntegrityError, match="exact Run row"):
        await SQLAlchemyCheckpointStore(sessions).load_latest("RUN-A")

    await engine.dispose()
