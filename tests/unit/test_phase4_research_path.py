from __future__ import annotations

import asyncio

import pytest

from src.domain.enums import RunStatus, TaskStatus
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import PlannedTaskGraph, Task
from src.runtime.checkpoint import InMemoryCheckpointStore
from src.runtime.events import InMemoryRuntimeEventStore
from src.runtime.lifecycle import TaskProjectionStage, project_task_lifecycle
from src.runtime.scheduler import DependencyScheduler, TaskExecutionContext, TaskExecutionResult
from src.runtime.state import RuntimeState, RuntimeStateError


def _task(task_id: str, *, run_id: str = "RUN-1", dependencies: list[str] | None = None) -> Task:
    return Task(
        task_id=task_id,
        run_id=run_id,
        task_type="research",
        goal=f"Research {task_id}",
        assigned_agent="research-agent",
        skill_id="research-skill",
        dependencies=dependencies or [],
    )


def _state(*tasks: Task) -> RuntimeState:
    return RuntimeState.create(
        run_id="RUN-1",
        planned_graph=PlannedTaskGraph(
            graph_id="GRAPH-1",
            run_id="RUN-1",
            tasks=list(tasks),
        ),
    )


@pytest.mark.parametrize(
    ("status", "stage", "terminal"),
    [
        (TaskStatus.CREATED, TaskProjectionStage.QUEUED, False),
        (TaskStatus.WAITING, TaskProjectionStage.QUEUED, False),
        (TaskStatus.READY, TaskProjectionStage.READY, False),
        (TaskStatus.RUNNING, TaskProjectionStage.ACTIVE, False),
        (TaskStatus.WAITING_FOR_CAPABILITY, TaskProjectionStage.WAITING_SUPPORT, False),
        (TaskStatus.SELF_CORRECTING, TaskProjectionStage.CORRECTING, False),
        (TaskStatus.BLOCKED, TaskProjectionStage.BLOCKED, False),
        (TaskStatus.REVIEW, TaskProjectionStage.REVIEW, False),
        (TaskStatus.COMPLETED, TaskProjectionStage.COMPLETE, True),
        (TaskStatus.FAILED, TaskProjectionStage.FAILED, True),
        (TaskStatus.CAPABILITY_BUILD_FAILED, TaskProjectionStage.FAILED, True),
        (TaskStatus.CANCELLED, TaskProjectionStage.CANCELLED, True),
    ],
)
def test_task_lifecycle_projection_is_total_and_preserves_raw_status(
    status: TaskStatus,
    stage: TaskProjectionStage,
    terminal: bool,
) -> None:
    projection = project_task_lifecycle(status)

    assert projection.status is status
    assert projection.stage is stage
    assert projection.terminal is terminal


def test_runtime_state_rejects_cross_run_tasks() -> None:
    graph = PlannedTaskGraph(
        graph_id="GRAPH-1",
        run_id="RUN-1",
        tasks=[_task("TASK-FOREIGN", run_id="RUN-2")],
    )

    with pytest.raises(RuntimeStateError, match="different run"):
        RuntimeState.create(run_id="RUN-1", planned_graph=graph)


def test_runtime_state_rejects_cyclic_planned_graph() -> None:
    graph = PlannedTaskGraph(
        graph_id="GRAPH-1",
        run_id="RUN-1",
        tasks=[
            _task("TASK-A", dependencies=["TASK-B"]),
            _task("TASK-B", dependencies=["TASK-A"]),
        ],
    )

    with pytest.raises(RuntimeStateError, match="dependency cycle"):
        RuntimeState.create(run_id="RUN-1", planned_graph=graph)


class _BlockingExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def execute(
        self,
        task: Task,
        context: TaskExecutionContext,
    ) -> TaskExecutionResult:
        del task, context
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_scheduler_cancellation_emits_authoritative_cancelled_terminal_event() -> None:
    events = InMemoryRuntimeEventStore()
    checkpoints = InMemoryCheckpointStore()
    state = _state(_task("TASK-1"))
    executor = _BlockingExecutor()
    execution = asyncio.create_task(
        DependencyScheduler(event_store=events, checkpoint_store=checkpoints).execute(
            state=state,
            executor=executor,
        )
    )

    await executor.started.wait()
    execution.cancel()
    with pytest.raises(asyncio.CancelledError):
        await execution

    terminal_events = [
        event
        for event in await events.replay(state.run_id)
        if event.type in {RuntimeEventType.RUN_COMPLETED, RuntimeEventType.RUN_FAILED}
    ]
    assert state.run_status is RunStatus.CANCELLED
    assert state.task("TASK-1").status is TaskStatus.CANCELLED
    assert len(terminal_events) == 1
    assert terminal_events[0].type is RuntimeEventType.RUN_FAILED
    assert terminal_events[0].payload == {
        "status": "CANCELLED",
        "failure_stage": "CANCELLATION",
        "failure_code": "RUN_CANCELLED",
    }


class _FailingExecutor:
    async def execute(
        self,
        task: Task,
        context: TaskExecutionContext,
    ) -> TaskExecutionResult:
        del task, context
        raise RuntimeError("secret provider diagnostic")


@pytest.mark.asyncio
async def test_scheduler_failure_uses_safe_terminal_and_task_codes() -> None:
    events = InMemoryRuntimeEventStore()
    state = _state(_task("TASK-1"))

    with pytest.raises(ExceptionGroup):
        await DependencyScheduler(
            event_store=events,
            checkpoint_store=InMemoryCheckpointStore(),
        ).execute(state=state, executor=_FailingExecutor())

    emitted = await events.replay(state.run_id)
    task_failure = next(event for event in emitted if event.type is RuntimeEventType.TASK_FAILED)
    run_failure = next(event for event in emitted if event.type is RuntimeEventType.RUN_FAILED)
    assert task_failure.payload == {
        "attempt": 1,
        "failure_code": "TASK_EXECUTION_FAILED",
    }
    assert run_failure.payload == {
        "status": "FAILED",
        "failure_stage": "TASK_EXECUTION",
        "failure_code": "TASK_EXECUTION_FAILED",
    }
    assert "secret provider diagnostic" not in repr([event.payload for event in emitted])
