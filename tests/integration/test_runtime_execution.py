from __future__ import annotations

import asyncio
from time import perf_counter

import pytest

from src.domain.enums import ReplanDecision, RunStatus, TaskOrigin, TaskStatus
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.domain.task import PlannedTaskGraph, ReplanRequest, Task
from src.runtime.checkpoint import InMemoryCheckpointStore, RuntimeCheckpoint
from src.runtime.events import EventSequenceError, InMemoryRuntimeEventStore
from src.runtime.graph import (
    GraphMutationActor,
    GraphMutationPermissionError,
    GraphMutationRole,
    GraphMutationService,
)
from src.runtime.lifecycle import transition_task
from src.runtime.scheduler import (
    DependencyScheduler,
    RetryPolicy,
    TaskExecutionContext,
    TaskExecutionResult,
)
from src.runtime.sse import runtime_event_stream
from src.runtime.state import RuntimeState


def make_task(task_id: str, *, dependencies: list[str] | None = None) -> Task:
    return Task(
        task_id=task_id,
        run_id="RUN-1",
        task_type="runtime_test",
        goal=f"Execute {task_id}",
        assigned_agent="test_specialist",
        skill_id="test_skill_v1",
        dependencies=dependencies or [],
    )


def make_state() -> RuntimeState:
    plan = PlannedTaskGraph(
        graph_id="PLAN-1",
        run_id="RUN-1",
        tasks=[
            make_task("ROOT-A"),
            make_task("ROOT-B"),
            make_task("JOIN", dependencies=["ROOT-A", "ROOT-B"]),
        ],
    )
    return RuntimeState.create(run_id="RUN-1", planned_graph=plan)


def test_capability_wait_and_resume_are_valid_runtime_transitions() -> None:
    task = make_task("CAPABILITY")
    task.status = TaskStatus.RUNNING

    transition_task(task, TaskStatus.WAITING_FOR_CAPABILITY)
    transition_task(task, TaskStatus.READY)
    transition_task(task, TaskStatus.RUNNING)

    assert task.status is TaskStatus.RUNNING


class ParallelProbeExecutor:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.roots_started = 0
        self.both_roots_started = asyncio.Event()

    async def execute(
        self,
        task: Task,
        context: TaskExecutionContext,
    ) -> TaskExecutionResult:
        if task.task_id.startswith("ROOT"):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.roots_started += 1
            if self.roots_started == 2:
                self.both_roots_started.set()
            await asyncio.wait_for(self.both_roots_started.wait(), timeout=0.2)
            await asyncio.sleep(0.1)
            self.active -= 1
        else:
            assert context.attempt == 1
            await asyncio.sleep(0.01)
        return TaskExecutionResult(
            result_ref=f"result://{task.task_id}",
            output_refs=(f"output://{task.task_id}",),
        )


@pytest.mark.asyncio
async def test_scheduler_executes_independent_tasks_in_real_parallel_waves() -> None:
    state = make_state()
    planned_before = state.planned_graph.model_dump()
    events = InMemoryRuntimeEventStore()
    checkpoints = InMemoryCheckpointStore()
    executor = ParallelProbeExecutor()
    scheduler = DependencyScheduler(event_store=events, checkpoint_store=checkpoints)

    started = perf_counter()
    result = await scheduler.execute(state=state, executor=executor)
    elapsed = perf_counter() - started

    assert executor.max_active == 2
    assert elapsed < 0.25, "two 100ms roots must overlap rather than execute serially"
    assert result.run_status is RunStatus.REVIEW
    assert result.task_states == {
        "ROOT-A": TaskStatus.COMPLETED,
        "ROOT-B": TaskStatus.COMPLETED,
        "JOIN": TaskStatus.COMPLETED,
    }
    assert result.task("JOIN").result_ref == "result://JOIN"
    assert result.completed_output_refs["ROOT-A"] == ["output://ROOT-A"]
    assert state.planned_graph.model_dump() == planned_before
    assert all(task.status is TaskStatus.CREATED for task in state.planned_graph.tasks)

    event_log = await events.replay("RUN-1")
    started_sequences = {
        event.task_id: event.sequence
        for event in event_log
        if event.type is RuntimeEventType.TASK_STARTED
    }
    completed_sequences = {
        event.task_id: event.sequence
        for event in event_log
        if event.type is RuntimeEventType.TASK_COMPLETED
    }
    assert started_sequences["ROOT-A"] < completed_sequences["ROOT-B"]
    assert started_sequences["ROOT-B"] < completed_sequences["ROOT-A"]
    assert started_sequences["JOIN"] > completed_sequences["ROOT-A"]
    assert started_sequences["JOIN"] > completed_sequences["ROOT-B"]

    checkpoint = await checkpoints.load_latest("RUN-1")
    assert checkpoint is not None
    assert checkpoint.run_status is RunStatus.REVIEW
    assert checkpoint.actual_graph_version == 1


class FlakyExecutor:
    async def execute(
        self,
        task: Task,
        context: TaskExecutionContext,
    ) -> TaskExecutionResult:
        if context.attempt == 1:
            raise ConnectionError("transient")
        return TaskExecutionResult(result_ref="result://retried")


@pytest.mark.asyncio
async def test_retry_lifecycle_records_attempts_and_monotonic_events() -> None:
    state = RuntimeState.create(
        run_id="RUN-1",
        planned_graph=PlannedTaskGraph(
            graph_id="PLAN-RETRY",
            run_id="RUN-1",
            tasks=[make_task("RETRY")],
        ),
    )
    events = InMemoryRuntimeEventStore()
    scheduler = DependencyScheduler(
        event_store=events,
        checkpoint_store=InMemoryCheckpointStore(),
        retry_policy=RetryPolicy(max_attempts=2),
    )

    await scheduler.execute(state=state, executor=FlakyExecutor())

    assert state.task("RETRY").attempt_count == 2
    assert state.task("RETRY").status is TaskStatus.COMPLETED
    event_log = await events.replay("RUN-1")
    assert [event.sequence for event in event_log] == list(range(1, len(event_log) + 1))
    retry_events = [
        event
        for event in event_log
        if event.type is RuntimeEventType.TASK_PROGRESS
        and event.payload.get("action") == "retry_scheduled"
    ]
    assert len(retry_events) == 1


class FailingExecutor:
    async def execute(
        self,
        task: Task,
        context: TaskExecutionContext,
    ) -> TaskExecutionResult:
        del task, context
        raise RuntimeError("terminal failure")


class CapabilityBuildFailingExecutor:
    def __init__(self, state: RuntimeState) -> None:
        self._state = state

    async def execute(
        self,
        task: Task,
        context: TaskExecutionContext,
    ) -> TaskExecutionResult:
        del context
        managed = self._state.task(task.task_id)
        transition_task(managed, TaskStatus.WAITING_FOR_CAPABILITY)
        transition_task(managed, TaskStatus.CAPABILITY_BUILD_FAILED)
        raise RuntimeError("generated capability build failed")


@pytest.mark.asyncio
async def test_scheduler_handles_capability_build_failure_as_explicit_task_failure() -> None:
    state = RuntimeState.create(
        run_id="RUN-1",
        planned_graph=PlannedTaskGraph(
            graph_id="PLAN-CAPABILITY-FAIL",
            run_id="RUN-1",
            tasks=[make_task("BUILD")],
        ),
    )
    scheduler = DependencyScheduler(
        event_store=InMemoryRuntimeEventStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        retry_policy=RetryPolicy(max_attempts=2),
    )

    with pytest.raises(ExceptionGroup, match="runtime tasks failed"):
        await scheduler.execute(
            state=state,
            executor=CapabilityBuildFailingExecutor(state),
        )

    assert state.run_status is RunStatus.FAILED
    assert state.task("BUILD").status is TaskStatus.CAPABILITY_BUILD_FAILED
    assert state.task("BUILD").attempt_count == 1


@pytest.mark.asyncio
async def test_terminal_failure_blocks_transitive_dependents_and_checkpoints() -> None:
    state = RuntimeState.create(
        run_id="RUN-1",
        planned_graph=PlannedTaskGraph(
            graph_id="PLAN-FAIL",
            run_id="RUN-1",
            tasks=[
                make_task("FAIL"),
                make_task("CHILD", dependencies=["FAIL"]),
                make_task("GRANDCHILD", dependencies=["CHILD"]),
            ],
        ),
    )
    checkpoints = InMemoryCheckpointStore()
    scheduler = DependencyScheduler(
        event_store=InMemoryRuntimeEventStore(),
        checkpoint_store=checkpoints,
    )

    with pytest.raises(ExceptionGroup, match="runtime tasks failed"):
        await scheduler.execute(state=state, executor=FailingExecutor())

    assert state.run_status is RunStatus.FAILED
    assert state.task("FAIL").status is TaskStatus.FAILED
    assert state.task("CHILD").status is TaskStatus.BLOCKED
    assert state.task("GRANDCHILD").status is TaskStatus.BLOCKED
    checkpoint = await checkpoints.load_latest("RUN-1")
    assert checkpoint is not None
    assert checkpoint.task_states["GRANDCHILD"] is TaskStatus.BLOCKED


@pytest.mark.asyncio
async def test_event_store_allocates_monotonic_sequences_under_concurrency() -> None:
    store = InMemoryRuntimeEventStore()
    emitted = await asyncio.gather(
        *(store.emit(run_id="RUN-1", event_type=RuntimeEventType.TASK_PROGRESS) for _ in range(50))
    )

    assert sorted(event.sequence for event in emitted) == list(range(1, 51))
    replay = await store.replay("RUN-1", after_sequence=45)
    assert [event.sequence for event in replay] == [46, 47, 48, 49, 50]

    with pytest.raises(EventSequenceError, match="expected sequence 51"):
        await store.append(
            RuntimeEvent(
                event_id="EVT-BAD",
                run_id="RUN-1",
                type=RuntimeEventType.TASK_PROGRESS,
                sequence=52,
            )
        )


@pytest.mark.asyncio
async def test_graph_mutation_requires_approving_lead_and_preserves_plan() -> None:
    state = make_state()
    planned_before = state.planned_graph.model_dump()
    store = InMemoryRuntimeEventStore()
    service = GraphMutationService(store)
    request = ReplanRequest(
        replan_id="REPLAN-1",
        run_id="RUN-1",
        requesting_task_id="ROOT-A",
        requested_by="specialist-1",
        reason_code="MISSING_CONTEXT",
        reason_detail="Add a follow-up",
        proposed_graph_change={"add": ["FOLLOW-UP"]},
        decision=ReplanDecision.APPROVED,
        decided_by="lead-1",
    )
    new_task = make_task("FOLLOW-UP", dependencies=["JOIN"])
    new_task.origin = TaskOrigin.REPLAN

    with pytest.raises(GraphMutationPermissionError, match="Research Lead or Planner"):
        await service.add_tasks(
            state=state,
            request=request,
            tasks=[new_task],
            actor=GraphMutationActor("specialist-1", GraphMutationRole.SPECIALIST),
        )

    graph = await service.add_tasks(
        state=state,
        request=request,
        tasks=[new_task],
        actor=GraphMutationActor("lead-1", GraphMutationRole.RESEARCH_LEAD),
    )

    assert graph.version == 2
    assert graph.tasks[-1].task_id == "FOLLOW-UP"
    assert state.planned_graph.model_dump() == planned_before
    assert all(task.task_id != "FOLLOW-UP" for task in state.planned_graph.tasks)
    assert [event.type for event in await store.replay("RUN-1")] == [
        RuntimeEventType.GRAPH_TASK_ADDED,
        RuntimeEventType.GRAPH_EDGE_ADDED,
        RuntimeEventType.GRAPH_VERSION_CHANGED,
    ]


class MutatingExecutor:
    def __init__(self, state: RuntimeState, mutation_service: GraphMutationService) -> None:
        self.state = state
        self.mutation_service = mutation_service
        self.executed: list[str] = []

    async def execute(
        self,
        task: Task,
        context: TaskExecutionContext,
    ) -> TaskExecutionResult:
        del context
        self.executed.append(task.task_id)
        if task.task_id == "ROOT":
            follow_up = make_task("DYNAMIC", dependencies=["ROOT"])
            follow_up.origin = TaskOrigin.REPLAN
            await self.mutation_service.add_tasks(
                state=self.state,
                request=ReplanRequest(
                    replan_id="REPLAN-DYNAMIC",
                    run_id="RUN-1",
                    requesting_task_id="ROOT",
                    requested_by="specialist-1",
                    reason_code="MISSING_CONTEXT",
                    reason_detail="Add dynamic follow-up",
                    proposed_graph_change={"add": ["DYNAMIC"]},
                    decision=ReplanDecision.APPROVED,
                    decided_by="lead-1",
                ),
                tasks=[follow_up],
                actor=GraphMutationActor("lead-1", GraphMutationRole.RESEARCH_LEAD),
            )
        return TaskExecutionResult(result_ref=f"result://{task.task_id}")


@pytest.mark.asyncio
async def test_scheduler_admits_approved_tasks_added_during_execution() -> None:
    state = RuntimeState.create(
        run_id="RUN-1",
        planned_graph=PlannedTaskGraph(
            graph_id="PLAN-DYNAMIC",
            run_id="RUN-1",
            tasks=[make_task("ROOT")],
        ),
    )
    events = InMemoryRuntimeEventStore()
    executor = MutatingExecutor(state, GraphMutationService(events))
    scheduler = DependencyScheduler(
        event_store=events,
        checkpoint_store=InMemoryCheckpointStore(),
    )

    await scheduler.execute(state=state, executor=executor)

    assert executor.executed == ["ROOT", "DYNAMIC"]
    assert state.actual_graph.version == 2
    assert state.task("DYNAMIC").status is TaskStatus.COMPLETED
    assert [task.task_id for task in state.planned_graph.tasks] == ["ROOT"]


@pytest.mark.asyncio
async def test_checkpoint_and_event_replay_are_defensive_copies() -> None:
    state = make_state()
    state.completed_output_refs["ROOT-A"] = ["output://a"]
    checkpoint_store = InMemoryCheckpointStore()
    checkpoint = RuntimeCheckpoint.capture(checkpoint_id="CHK-1", state=state)
    await checkpoint_store.save(checkpoint)

    first = await checkpoint_store.load_latest("RUN-1")
    assert first is not None
    first.completed_output_refs["ROOT-A"].append("tampered")
    second = await checkpoint_store.load_latest("RUN-1")
    assert second is not None
    assert second.completed_output_refs["ROOT-A"] == ["output://a"]

    event_store = InMemoryRuntimeEventStore()
    event = await event_store.emit(
        run_id="RUN-1",
        event_type=RuntimeEventType.RUN_STARTED,
        payload={"nested": {"safe": True}},
    )
    event.payload["nested"] = {"safe": False}
    replay = await event_store.replay("RUN-1")
    assert replay[0].payload == {"nested": {"safe": True}}


@pytest.mark.asyncio
async def test_sse_replays_by_sequence_and_emits_heartbeat_when_idle() -> None:
    store = InMemoryRuntimeEventStore()
    first = await store.emit(run_id="RUN-1", event_type=RuntimeEventType.RUN_STARTED)
    await store.emit(run_id="RUN-1", event_type=RuntimeEventType.TASK_READY, task_id="A")
    third = await store.emit(run_id="RUN-1", event_type=RuntimeEventType.TASK_STARTED, task_id="A")

    stream = runtime_event_stream(
        store=store,
        run_id="RUN-1",
        last_event_id=str(first.sequence),
        heartbeat_seconds=0.01,
    )
    replay_two = await anext(stream)
    replay_three = await anext(stream)
    heartbeat = await anext(stream)
    await stream.aclose()

    assert replay_two.startswith("id: 2\nevent: task.ready\n")
    assert replay_three.startswith(f"id: {third.sequence}\nevent: task.started\n")
    assert heartbeat == ": heartbeat\n\n"

    assert await store.resolve_resume_sequence("RUN-1", third.event_id) == 3
