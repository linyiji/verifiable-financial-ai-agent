from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from math import isfinite
from typing import Protocol, runtime_checkable
from uuid import uuid4

from src.domain.enums import RunStatus, TaskStatus
from src.domain.node_binding import AdmissionBinding, BindingDenied
from src.domain.output_dependency import LocalOutputFailure
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import Task
from src.runtime.checkpoint import CheckpointStore, RuntimeCheckpoint
from src.runtime.diagnostics import task_failure_diagnostic
from src.runtime.events import RuntimeEventStore
from src.runtime.lifecycle import transition_task
from src.runtime.output_dependencies import resolve_outputs
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
    admission: AdmissionBinding | None = None


@dataclass(frozen=True, slots=True)
class TaskExecutionResult:
    result_ref: str | None = None
    output_refs: tuple[str, ...] = field(default_factory=tuple)
    result_binding_id: str | None = None


@runtime_checkable
class TaskExecutor(Protocol):
    async def execute(
        self,
        task: Task,
        context: TaskExecutionContext,
    ) -> TaskExecutionResult: ...


class DependencyDeadlockError(RuntimeError):
    pass


class RuntimeProcessInterrupted(BaseException):
    """Opt-in process-loss signal; not cancellation or a business task failure."""


class DependencyScheduler:
    """Executes dependency waves concurrently using real ``asyncio`` tasks."""

    def __init__(
        self,
        *,
        event_store: RuntimeEventStore,
        checkpoint_store: CheckpointStore,
        retry_policy: RetryPolicy | None = None,
        attempt_resolver: Callable[[Task, int], Awaitable[int]] | None = None,
        admission_repository=None,
        execution_owner=None,
    ) -> None:
        self._event_store = event_store
        self._checkpoint_store = checkpoint_store
        self._retry_policy = retry_policy or RetryPolicy()
        self._attempt_resolver = attempt_resolver
        self._reported_blocks: set[str] = set()
        self._admission_repository = admission_repository
        self._execution_owner = execution_owner
        self._bound_results = None

    async def execute(
        self,
        *,
        state: RuntimeState,
        executor: TaskExecutor,
        emit_run_started: bool = True,
        on_execution_admitted: Callable[[], None] | None = None,
    ) -> RuntimeState:
        if state.binding_ref is not None:
            if self._admission_repository is None or self._execution_owner is None:
                raise BindingDenied("STATE_REFRESH_REQUIRED", "Scheduler admission port")
            if self._execution_owner.run_id != state.run_id:
                raise BindingDenied("IDENTITY_MISMATCH", "Scheduler Run versus owner")
            await self._admission_repository.begin_scheduler(self._execution_owner)
            # Notify only this invocation, after the existing durable admission commits.
            # This signal cannot skip admission or grant a second Run owner.
            if on_execution_admitted is not None:
                on_execution_admitted()
        self._admit_created_tasks(state)
        state.run_status = RunStatus.RUNNING
        if emit_run_started:
            await self._event_store.emit(
                run_id=state.run_id,
                event_type=RuntimeEventType.RUN_STARTED,
                payload={"actual_graph_version": state.actual_graph.version},
            )

        try:
            while True:
                if resume_liveness.get() is not None:
                    resume_liveness.get().checkpoint()
                if state.binding_ref is not None:
                    fresh = await self._admission_repository.validate_execution(
                        self._execution_owner
                    )
                    state.actual_graph = fresh.runtime.actual_graph.model_copy(deep=True)
                    state.completed_output_refs = dict(fresh.runtime.completed_output_refs)
                    state.binding_ref = fresh.node_binding.reference()
                    from src.application.risk_admission import final_current_results

                    self._bound_results = final_current_results(fresh)
                    from src.application.risk_replan import ReplanSuspended, control

                    replan = control(fresh)
                    if replan is not None and replan.wait_reason not in {
                        "FOLLOW_UP_EXECUTION", "FULFILLED"
                    }:
                        raise ReplanSuspended()
                    self._replan_aggregate = fresh
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
                for blocked in state.actual_graph.tasks:
                    if (
                        blocked.missing_output_dependencies
                        and blocked.task_id not in self._reported_blocks
                    ):
                        await self._event_store.emit(
                            run_id=state.run_id,
                            task_id=blocked.task_id,
                            event_type=RuntimeEventType.TASK_PROGRESS,
                            payload={
                                "progress": blocked.progress,
                                "message_code": "BLOCKED_BY_DEPENDENCY:"
                                + ",".join(blocked.missing_output_dependencies),
                            },
                        )
                        self._reported_blocks.add(blocked.task_id)
                ready = self._promote_ready_tasks(state)
                for task in ready:
                    await self._event_store.emit(
                        run_id=state.run_id,
                        task_id=task.task_id,
                        event_type=RuntimeEventType.TASK_READY,
                    )

                if not ready:
                    from src.runtime.output_dependencies import ExecutionContinuationGate

                    if ExecutionContinuationGate.settled_for_review(state):
                        state.run_status = RunStatus.REVIEW
                        await self._event_store.emit(
                            run_id=state.run_id,
                            event_type=RuntimeEventType.RUN_STATUS_CHANGED,
                            payload={"status": RunStatus.REVIEW.value},
                        )
                        await self._checkpoint(state)
                        return state
                    state.run_status = RunStatus.FAILED
                    if state.binding_ref is None:
                        await self._event_store.emit(
                            run_id=state.run_id,
                            event_type=RuntimeEventType.RUN_FAILED,
                            payload={
                                "status": RunStatus.FAILED.value,
                                "failure_stage": "TASK_EXECUTION",
                                "failure_code": "TASK_EXECUTION_FAILED",
                                "safe_message": (
                                    "No runnable tasks remain because a dependency failed "
                                    "or the graph could not progress."
                                ),
                            },
                        )
                    await self._checkpoint(state)
                    raise DependencyDeadlockError(
                        "no runnable tasks remain; graph is cyclic or a dependency failed"
                    )

                results = await asyncio.gather(
                    *(self._execute_task(state, task, executor) for task in ready),
                    return_exceptions=True,
                )
                if resume_liveness.get() is not None:
                    resume_liveness.get().checkpoint()
                interrupted = next(
                    (item for item in results if isinstance(item, RuntimeProcessInterrupted)), None
                )
                if interrupted is not None:
                    raise interrupted
                if any(isinstance(result, asyncio.CancelledError) for result in results):
                    raise asyncio.CancelledError
                await self._checkpoint(state)
                errors = [
                    result
                    for task, result in zip(ready, results, strict=True)
                    if isinstance(result, BaseException)
                    and (
                        not isinstance(result, LocalOutputFailure)
                        or not any(
                            output.status.value != "COMPLETED"
                            for output in state.task(task.task_id).output_outcomes
                        )
                    )
                ]
                if errors:
                    from src.application.repository import NodeRecoveryPending
                    from src.application.risk_replan import ReplanSuspended

                    if all(isinstance(error, (NodeRecoveryPending, ReplanSuspended))
                           for error in errors) and any(
                               isinstance(error, ReplanSuspended) for error in errors):
                        raise ReplanSuspended()

                    if all(isinstance(error, NodeRecoveryPending) for error in errors):
                        raise ExceptionGroup("node recovery pending", errors)
                    self._block_failed_dependents(state)
                    state.run_status = RunStatus.FAILED
                    generated_capability_failed = any(
                        task.status is TaskStatus.CAPABILITY_BUILD_FAILED
                        for task in state.actual_graph.tasks
                    )
                    if state.binding_ref is None:
                        await self._event_store.emit(
                            run_id=state.run_id,
                            event_type=RuntimeEventType.RUN_FAILED,
                            payload={
                                "status": RunStatus.FAILED.value,
                                "failure_stage": (
                                    "GENERATED_CAPABILITY"
                                    if generated_capability_failed
                                    else "TASK_EXECUTION"
                                ),
                                "failure_code": (
                                    "GENERATED_CAPABILITY_FAILED"
                                    if generated_capability_failed
                                    else "TASK_EXECUTION_FAILED"
                                ),
                            },
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
            if state.binding_ref is None:
                await self._event_store.emit(
                    run_id=state.run_id,
                    event_type=RuntimeEventType.RUN_FAILED,
                    payload={
                        "status": RunStatus.CANCELLED.value,
                        "failure_stage": "CANCELLATION",
                        "failure_code": "RUN_CANCELLED",
                    },
                )
            await self._checkpoint(state)
            raise

    def _admit_created_tasks(self, state: RuntimeState) -> None:
        for task in state.actual_graph.tasks:
            if task.status is TaskStatus.CREATED:
                transition_task(task, TaskStatus.WAITING)

    def _promote_ready_tasks(self, state: RuntimeState) -> list[Task]:
        ready: list[Task] = []
        for task in state.actual_graph.tasks:
            from src.application.risk_replan import child_dependency

            candidate = (child_dependency(self._replan_aggregate, task)
                         if getattr(self, "_replan_aggregate", None) is not None else None)
            if (
                task.status in {TaskStatus.WAITING, TaskStatus.BLOCKED}
                and resolve_outputs(
                    state, task, committed_results=self._bound_results, require_current=True,
                    candidate_dependency=candidate,
                    aggregate=getattr(self, "_replan_aggregate", None)
                )[0]
                == "READY"
            ):
                transition_task(task, TaskStatus.READY)
                ready.append(task)
        return ready

    def _block_failed_dependents(self, state: RuntimeState) -> None:
        changed = True
        while changed:
            changed = False
            for task in state.actual_graph.tasks:
                decision, missing = resolve_outputs(
                    state, task, committed_results=self._bound_results, require_current=True,
                    aggregate=getattr(self, "_replan_aggregate", None)
                )
                if task.status is TaskStatus.WAITING and decision == "BLOCKED":
                    transition_task(task, TaskStatus.BLOCKED)
                    task.missing_output_dependencies = missing
                    changed = True

    async def _execute_task(
        self,
        state: RuntimeState,
        task: Task,
        executor: TaskExecutor,
    ) -> None:
        task_id = task.task_id
        last_error: Exception | None = None
        bound = state.binding_ref is not None
        for retry_number in range(1, (1 if bound else self._retry_policy.max_attempts) + 1):
            # A concurrent graph mutation atomically swaps the Actual Graph copy.
            # Resolve by identity on every state update so in-flight tasks never
            # complete against a detached pre-mutation Task instance.
            task = state.task(task_id)
            attempt = (
                await self._attempt_resolver(task.model_copy(deep=True), retry_number)
                if self._attempt_resolver
                else retry_number
            )
            if attempt < 1:
                raise ValueError("attempt identity must be positive")
            admission = None
            if bound:
                if self._admission_repository is None or self._execution_owner is None:
                    raise BindingDenied("STATE_REFRESH_REQUIRED", "Scheduler admission port")
                if resume_liveness.get() is not None:
                    resume_liveness.get().checkpoint()
                requirements = executor.admission_requirements(task)
                if resume_liveness.get() is not None:
                    resume_liveness.get().checkpoint()
                admission = await self._admission_repository.reserve_node(
                    self._execution_owner, task, requirements
                )
                if resume_liveness.get() is not None:
                    resume_liveness.get().checkpoint()
                dispatched = await self._admission_repository.dispatch_node(admission)
                if resume_liveness.get() is not None:
                    resume_liveness.get().checkpoint()
                attempt = dispatched.node_binding.attempts[task_id].generation
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
                    TaskExecutionContext(run_id=state.run_id, attempt=attempt, admission=admission),
                )
            except asyncio.CancelledError:
                state.task(task_id).status = TaskStatus.CANCELLED
                raise
            except Exception as error:
                from src.application.repository import NodeRecoveryPending
                from src.application.risk_replan import ReplanSuspended

                if isinstance(error, ReplanSuspended):
                    state.task(task_id).status = TaskStatus.WAITING_REPLAN
                    raise

                if isinstance(error, NodeRecoveryPending):
                    state.task(task_id).status = TaskStatus.WAITING
                    raise
                task = state.task(task_id)
                last_error = error
                diagnostic = task_failure_diagnostic(error, task=task, attempt=attempt)
                if task.status is TaskStatus.CAPABILITY_BUILD_FAILED:
                    await self._event_store.emit(
                        run_id=state.run_id,
                        task_id=task.task_id,
                        event_type=RuntimeEventType.TASK_FAILED,
                        payload={
                            "attempt": attempt,
                            "failure_code": "CAPABILITY_BUILD_FAILED",
                            "status": TaskStatus.CAPABILITY_BUILD_FAILED.value,
                            "retry_suppressed": True,
                            "internal_diagnostic": diagnostic,
                        },
                    )
                    raise
                if (
                    not bound
                    and retry_number < self._retry_policy.max_attempts
                    and getattr(error, "retryable", True)
                ):
                    transition_task(task, TaskStatus.READY)
                    await self._event_store.emit(
                        run_id=state.run_id,
                        task_id=task.task_id,
                        event_type=RuntimeEventType.TASK_PROGRESS,
                        payload={
                            # Retained in the durable Phase 3 payload for backward
                            # compatibility. The Phase 4 public event adapter
                            # structurally normalizes this to RETRY_SCHEDULED.
                            "action": "retry_scheduled",
                            "attempt": attempt,
                            "error_code": "TASK_EXECUTION_FAILED",
                            "internal_diagnostic": diagnostic,
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
                    payload={
                        "attempt": attempt,
                        "failure_code": "TASK_EXECUTION_FAILED",
                        "internal_diagnostic": diagnostic,
                    },
                )
                raise
            else:
                if bound:
                    current = await self._admission_repository.validate_execution(
                        self._execution_owner
                    )
                    committed = current.node_binding.current_results.get(task_id)
                    receipt = (current.node_binding.risk_admissions or {}).get(
                        admission.admission_binding_id)
                    if receipt is not None and receipt["decision"] in {
                        "EVIDENCE_INSUFFICIENT", "CONTRACT_REJECTED"
                    }:
                        state.actual_graph = current.runtime.actual_graph.model_copy(deep=True)
                        state.binding_ref = current.node_binding.reference()
                        await self._event_store.emit(
                            run_id=state.run_id, task_id=task_id,
                            event_type=RuntimeEventType.TASK_PROGRESS,
                            payload={"progress": 1.0, "risk_admission": receipt["decision"]})
                        return
                    if result.result_binding_id is None or committed != result.result_binding_id:
                        raise BindingDenied("STATE_REFRESH_REQUIRED", "uncommitted result")
                    state.binding_ref = current.node_binding.reference()
                    state.actual_graph.tasks = [
                        current.runtime.task(task_id).model_copy(deep=True)
                        if item.task_id == task_id
                        else item
                        for item in state.actual_graph.tasks
                    ]
                task = state.task(task_id)
                task.result_ref = result.result_ref
                task.progress = 1.0
                state.completed_output_refs[task.task_id] = list(result.output_refs)
                if task.status is not TaskStatus.COMPLETED:
                    transition_task(task, TaskStatus.COMPLETED)
                paired_completion = (bound and current.node_binding.replan is not None
                    and current.node_binding.replan.get("finalization") is not None
                    and current.node_binding.replan["finalization"]["fulfilling_child_task_id"]
                    == task.task_id)
                if paired_completion:
                    return
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

# Local Resume bookkeeping. None of these values are serialized as authority.

resume_liveness = ContextVar("resume_liveness", default=None)


class ResumeLiveness:
    """One explicit Resume cycle; only committed changes and owned spans count."""

    def __init__(self, run_id, cycle_id, *, clock=None):
        self.run_id, self.cycle_id = run_id, cycle_id
        self.clock = clock or asyncio.get_running_loop().time
        self.sample = self.clock()
        self.orchestration = self.no_progress = 0.0
        self.max_no_progress = 0.0
        self.spans = {}
        self.seen = set()
        self.trace = []
        self.changed = asyncio.Event()
        self.expired = None
        self.settling = self.finished = False
        self.terminal_deadline = None

    def advance(self):
        now = self.clock()
        if now < self.sample:
            raise ValueError("Resume monotonic clock moved backward")
        # Since the previous sample every live span began at or before sample.
        # Its deadline is an exact endpoint even if the timer callback is late.
        end = max((s[0] for s in self.spans.values()), default=self.sample)
        charge = max(0.0, now - max(self.sample, min(now, end)))
        if not self.finished:
            self.orchestration += charge
            self.no_progress += charge
            self.max_no_progress = max(self.max_no_progress, self.no_progress)
        self.sample = now
        return now

    def checkpoint(self):
        self.advance()
        if self.finished:
            return
        if self.expired is None:
            if self.orchestration >= 300:
                self.expired = "RESUME_ORCHESTRATION_HARD_CAP"
            elif not self.settling and self.no_progress >= 60:
                self.expired = "RESUME_NO_PROGRESS_TIMEOUT"
        if self.expired:
            raise TimeoutError(self.expired)

    def progress(self, identity):
        self.checkpoint()
        if self.finished or identity in self.seen:
            return
        self.seen.add(identity)
        self.trace.append(dict(kind="progress", identity=identity, at=self.sample,
                               orchestration=self.orchestration, no_progress=self.no_progress))
        self.no_progress = 0.0
        self.changed.set()

    def start(self, admission, attempt_id, deadline, handle):
        # The executor/recovery owner calls here only after enter + ATTEMPT_STARTED.
        self.checkpoint()
        if (admission.run_id != self.run_id or handle is not asyncio.current_task()
                or handle.done() or not isfinite(deadline) or deadline <= self.sample):
            raise BindingDenied("STATE_REFRESH_REQUIRED", "invalid bounded Resume span")
        cycle = admission.policy_refs.get("external_resume_cycle")
        if cycle is not None and cycle != self.cycle_id:
            raise BindingDenied("RESUME_CYCLE_MISMATCH")
        key = (admission.owner.owner_generation, admission.owner.owner_id, admission.task_id,
               admission.admission_binding_id, admission.attempt_reservation_id, attempt_id)
        self.progress(("active", *key))
        if key in self.spans:
            raise BindingDenied("STATE_REFRESH_REQUIRED", "duplicate active span")
        self.spans[key] = (deadline, handle)
        self.trace.append(dict(kind="active_start", identity=key, at=self.sample,
                               deadline=deadline, orchestration=self.orchestration))
        self.changed.set()
        return key

    def end(self, key):
        self.advance()
        self.spans.pop(key, None)
        self.trace.append(dict(kind="active_end", identity=key, at=self.sample,
                               orchestration=self.orchestration))
        self.changed.set()

    @property
    def deadline(self):
        if self.finished:
            return self.terminal_deadline
        self.advance()
        return self.sample + max(0.0, 300 - self.orchestration)

    def remaining(self):
        if self.finished:
            return max(0.0, self.terminal_deadline - self.clock())
        self.advance()
        return max(0.0, 300 - self.orchestration)

    def require_remaining(self):
        if self.remaining() <= 0:
            raise BindingDenied("RESULT_UNKNOWN", "Resume orchestration budget exhausted")

    def settled(self):
        if self.finished:
            return
        self.advance()
        self.terminal_deadline = self.sample + max(0.0, 300 - self.orchestration)
        self.finished = True
        self.changed.set()

    async def watch(self):
        while not self.finished:
            self.checkpoint()
            self.changed.clear()
            valid = [end for end, handle in self.spans.values()
                     if end > self.sample and not handle.done()]
            delay = (max(valid) - self.sample if valid else
                     min(300 - self.orchestration,
                         300 if self.settling else 60 - self.no_progress))
            try:
                async with asyncio.timeout(max(0.001, delay)):
                    await self.changed.wait()
            except TimeoutError:
                pass


def liveness_progress(run_id, identity):
    scope = resume_liveness.get()
    if scope is not None and scope.run_id == run_id:
        try:
            scope.progress(identity)
        except TimeoutError:
            pass


def liveness_facts(aggregate):
    """Small semantic IDs/statuses, never root hashes, reads or revision bumps."""
    root = aggregate.node_binding
    return frozenset(
        [("lifecycle", root.owner_generation, root.lifecycle, root.scheduler_started)]
        + [("task", t.task_id, t.status.value) for t in aggregate.runtime.actual_graph.tasks]
        + [("attempt", a.admission.attempt_reservation_id, a.status, a.execution_started)
           for a in root.attempts.values()]
        + [("result", key) for key in root.results]
        + [("current", task, result) for task, result in root.current_results.items()]
        + [("admission", key, value["decision"])
           for key, value in (root.risk_admissions or {}).items()]
    )


def liveness_committed(aggregate, before):
    for fact in liveness_facts(aggregate) - before:
        liveness_progress(aggregate.run.run_id, fact)
