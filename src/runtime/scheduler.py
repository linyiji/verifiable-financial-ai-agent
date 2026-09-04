from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import uuid4

from src.domain.enums import RunStatus, TaskStatus
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import Task
from src.runtime.checkpoint import CheckpointStore, RuntimeCheckpoint
from src.runtime.events import RuntimeEventStore
from src.runtime.lifecycle import transition_task
from src.runtime.state import RuntimeState


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds cannot be negative")


@dataclass(frozen=True, slots=True)
class TaskExecutionContext:
    run_id: str
    attempt: int


@dataclass(frozen=True, slots=True)
class TaskExecutionResult:
    result_ref: str | None = None
    output_refs: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class TaskExecutor(Protocol):
    async def execute(
        self,
        task: Task,
        context: TaskExecutionContext,
    ) -> TaskExecutionResult: ...


class DependencyDeadlockError(RuntimeError):
    pass


class DependencyScheduler:
    """Executes dependency waves concurrently using real ``asyncio`` tasks."""

    def __init__(
        self,
        *,
        event_store: RuntimeEventStore,
        checkpoint_store: CheckpointStore,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._event_store = event_store
        self._checkpoint_store = checkpoint_store
        self._retry_policy = retry_policy or RetryPolicy()

    async def execute(self, *, state: RuntimeState, executor: TaskExecutor) -> RuntimeState:
        self._admit_created_tasks(state)
        state.run_status = RunStatus.RUNNING
        await self._event_store.emit(
            run_id=state.run_id,
            event_type=RuntimeEventType.RUN_STARTED,
            payload={"actual_graph_version": state.actual_graph.version},
        )

        try:
            while True:
                # Approved graph mutations may add CREATED tasks while a wave is running.
                self._admit_created_tasks(state)
                if all(task.status is TaskStatus.COMPLETED for task in state.actual_graph.tasks):
                    state.run_status = RunStatus.REVIEW
                    await self._event_store.emit(
                        run_id=state.run_id,
                        event_type=RuntimeEventType.RUN_STATUS_CHANGED,
                        payload={"status": RunStatus.REVIEW.value},
                    )
                    await self._checkpoint(state)
                    return state

                self._block_failed_dependents(state)
                ready = self._promote_ready_tasks(state)
                for task in ready:
                    await self._event_store.emit(
                        run_id=state.run_id,
                        task_id=task.task_id,
                        event_type=RuntimeEventType.TASK_READY,
                    )

                if not ready:
                    state.run_status = RunStatus.FAILED
                    await self._event_store.emit(
                        run_id=state.run_id,
                        event_type=RuntimeEventType.RUN_FAILED,
                        payload={"reason": "dependency_deadlock_or_failed_dependency"},
                    )
                    await self._checkpoint(state)
                    raise DependencyDeadlockError(
                        "no runnable tasks remain; graph is cyclic or a dependency failed"
                    )

                results = await asyncio.gather(
                    *(self._execute_task(state, task, executor) for task in ready),
                    return_exceptions=True,
                )
                await self._checkpoint(state)
                errors = [result for result in results if isinstance(result, BaseException)]
                if errors:
                    self._block_failed_dependents(state)
                    state.run_status = RunStatus.FAILED
                    await self._event_store.emit(
                        run_id=state.run_id,
                        event_type=RuntimeEventType.RUN_FAILED,
                        payload={"failed_task_count": len(errors)},
                    )
                    await self._checkpoint(state)
                    raise ExceptionGroup("one or more runtime tasks failed", errors)
        except asyncio.CancelledError:
            state.run_status = RunStatus.CANCELLED
            for task in state.actual_graph.tasks:
                if task.status not in {
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CAPABILITY_BUILD_FAILED,
                    TaskStatus.CANCELLED,
                }:
                    task.status = TaskStatus.CANCELLED
            await self._checkpoint(state)
            raise

    def _admit_created_tasks(self, state: RuntimeState) -> None:
        for task in state.actual_graph.tasks:
            if task.status is TaskStatus.CREATED:
                transition_task(task, TaskStatus.WAITING)

    def _promote_ready_tasks(self, state: RuntimeState) -> list[Task]:
        completed = {
            task.task_id for task in state.actual_graph.tasks if task.status is TaskStatus.COMPLETED
        }
        ready: list[Task] = []
        for task in state.actual_graph.tasks:
            if task.status in {TaskStatus.WAITING, TaskStatus.BLOCKED} and set(
                task.dependencies
            ).issubset(completed):
                transition_task(task, TaskStatus.READY)
                ready.append(task)
        return ready

    def _block_failed_dependents(self, state: RuntimeState) -> None:
        failed = {
            task.task_id
            for task in state.actual_graph.tasks
            if task.status
            in {
                TaskStatus.FAILED,
                TaskStatus.CAPABILITY_BUILD_FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.BLOCKED,
            }
        }
        changed = True
        while changed:
            changed = False
            for task in state.actual_graph.tasks:
                if task.status is TaskStatus.WAITING and failed.intersection(task.dependencies):
                    transition_task(task, TaskStatus.BLOCKED)
                    failed.add(task.task_id)
                    changed = True

    async def _execute_task(
        self,
        state: RuntimeState,
        task: Task,
        executor: TaskExecutor,
    ) -> None:
        task_id = task.task_id
        last_error: Exception | None = None
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            # A concurrent graph mutation atomically swaps the Actual Graph copy.
            # Resolve by identity on every state update so in-flight tasks never
            # complete against a detached pre-mutation Task instance.
            task = state.task(task_id)
            if task.status is not TaskStatus.READY:
                transition_task(task, TaskStatus.READY)
            transition_task(task, TaskStatus.RUNNING)
            task.attempt_count = attempt
            await self._event_store.emit(
                run_id=state.run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.TASK_STARTED,
                payload={"attempt": attempt},
            )
            try:
                result = await executor.execute(
                    task.model_copy(deep=True),
                    TaskExecutionContext(run_id=state.run_id, attempt=attempt),
                )
            except asyncio.CancelledError:
                state.task(task_id).status = TaskStatus.CANCELLED
                raise
            except Exception as error:
                task = state.task(task_id)
                last_error = error
                if attempt < self._retry_policy.max_attempts:
                    transition_task(task, TaskStatus.READY)
                    await self._event_store.emit(
                        run_id=state.run_id,
                        task_id=task.task_id,
                        event_type=RuntimeEventType.TASK_PROGRESS,
                        payload={
                            "action": "retry_scheduled",
                            "attempt": attempt,
                            "error_type": type(error).__name__,
                        },
                    )
                    if self._retry_policy.backoff_seconds:
                        await asyncio.sleep(self._retry_policy.backoff_seconds)
                    continue
                transition_task(task, TaskStatus.FAILED)
                await self._event_store.emit(
                    run_id=state.run_id,
                    task_id=task.task_id,
                    event_type=RuntimeEventType.TASK_FAILED,
                    payload={"attempt": attempt, "error_type": type(error).__name__},
                )
                raise
            else:
                task = state.task(task_id)
                task.result_ref = result.result_ref
                task.progress = 1.0
                state.completed_output_refs[task.task_id] = list(result.output_refs)
                transition_task(task, TaskStatus.COMPLETED)
                await self._event_store.emit(
                    run_id=state.run_id,
                    task_id=task.task_id,
                    event_type=RuntimeEventType.TASK_COMPLETED,
                    payload={"attempt": attempt, "result_ref": result.result_ref},
                )
                return
        if last_error is not None:  # pragma: no cover - defensive; loop always returns/raises
            raise last_error

    async def _checkpoint(self, state: RuntimeState) -> None:
        await self._checkpoint_store.save(
            RuntimeCheckpoint.capture(checkpoint_id=f"CHK-{uuid4()}", state=state)
        )
