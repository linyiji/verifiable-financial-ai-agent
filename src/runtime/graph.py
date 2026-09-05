from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from src.domain.enums import ReplanDecision, TaskStatus
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import ActualRuntimeGraph, ReplanRequest, Task
from src.runtime.events import RuntimeEventStore
from src.runtime.state import RuntimeState


class GraphMutationPermissionError(PermissionError):
    pass


class GraphMutationValidationError(ValueError):
    pass


class GraphMutationRole(StrEnum):
    RESEARCH_LEAD = "RESEARCH_LEAD"
    PLANNER = "PLANNER"
    SPECIALIST = "SPECIALIST"


@dataclass(frozen=True, slots=True)
class GraphMutationActor:
    actor_id: str
    role: GraphMutationRole


@dataclass(frozen=True, slots=True)
class _Operation:
    kind: Literal["add_node", "add_edge", "remove_edge"]
    task: Task | None = None
    source_task_id: str | None = None
    target_task_id: str | None = None


class GraphMutationService:
    """Apply Lead-approved graph changes atomically to Actual Graph only."""

    _AUTHORIZED_ROLES = frozenset({GraphMutationRole.RESEARCH_LEAD, GraphMutationRole.PLANNER})
    _DEPENDENCY_IMMUTABLE_STATUSES = frozenset(
        {
            TaskStatus.RUNNING,
            TaskStatus.REVIEW,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    )

    def __init__(self, event_store: RuntimeEventStore) -> None:
        self._event_store = event_store

    async def add_tasks(
        self,
        *,
        state: RuntimeState,
        request: ReplanRequest,
        tasks: list[Task],
        actor: GraphMutationActor,
    ) -> ActualRuntimeGraph:
        if not tasks:
            raise GraphMutationValidationError("graph mutation must add at least one task")
        return await self._apply_atomic(
            state=state,
            request=request,
            actor=actor,
            operations=[_Operation(kind="add_node", task=task) for task in tasks],
        )

    async def add_node(
        self,
        *,
        state: RuntimeState,
        request: ReplanRequest,
        task: Task,
        actor: GraphMutationActor,
    ) -> ActualRuntimeGraph:
        return await self.add_tasks(
            state=state,
            request=request,
            tasks=[task],
            actor=actor,
        )

    async def add_edge(
        self,
        *,
        state: RuntimeState,
        request: ReplanRequest,
        source_task_id: str,
        target_task_id: str,
        actor: GraphMutationActor,
    ) -> ActualRuntimeGraph:
        return await self._apply_atomic(
            state=state,
            request=request,
            actor=actor,
            operations=[
                _Operation(
                    kind="add_edge",
                    source_task_id=source_task_id,
                    target_task_id=target_task_id,
                )
            ],
        )

    async def remove_edge(
        self,
        *,
        state: RuntimeState,
        request: ReplanRequest,
        source_task_id: str,
        target_task_id: str,
        actor: GraphMutationActor,
    ) -> ActualRuntimeGraph:
        return await self._apply_atomic(
            state=state,
            request=request,
            actor=actor,
            operations=[
                _Operation(
                    kind="remove_edge",
                    source_task_id=source_task_id,
                    target_task_id=target_task_id,
                )
            ],
        )

    async def replace_dependency(
        self,
        *,
        state: RuntimeState,
        request: ReplanRequest,
        target_task_id: str,
        old_dependency_id: str,
        new_dependency_id: str,
        actor: GraphMutationActor,
    ) -> ActualRuntimeGraph:
        return await self._apply_atomic(
            state=state,
            request=request,
            actor=actor,
            operations=[
                _Operation(
                    kind="remove_edge",
                    source_task_id=old_dependency_id,
                    target_task_id=target_task_id,
                ),
                _Operation(
                    kind="add_edge",
                    source_task_id=new_dependency_id,
                    target_task_id=target_task_id,
                ),
            ],
        )

    async def insert_node_between(
        self,
        *,
        state: RuntimeState,
        request: ReplanRequest,
        task: Task,
        predecessor_task_id: str,
        successor_task_id: str,
        actor: GraphMutationActor,
    ) -> ActualRuntimeGraph:
        """Atomically replace predecessor→successor with predecessor→node→successor."""

        if task.dependencies:
            raise GraphMutationValidationError(
                "inserted task dependencies must be empty; edges are declared by the insertion"
            )
        return await self._apply_atomic(
            state=state,
            request=request,
            actor=actor,
            operations=[
                _Operation(kind="add_node", task=task),
                _Operation(
                    kind="add_edge",
                    source_task_id=predecessor_task_id,
                    target_task_id=task.task_id,
                ),
                _Operation(
                    kind="remove_edge",
                    source_task_id=predecessor_task_id,
                    target_task_id=successor_task_id,
                ),
                _Operation(
                    kind="add_edge",
                    source_task_id=task.task_id,
                    target_task_id=successor_task_id,
                ),
            ],
        )

    def invalidate_ready_state(self, state: RuntimeState) -> list[str]:
        completed = {
            task.task_id for task in state.actual_graph.tasks if task.status is TaskStatus.COMPLETED
        }
        invalidated: list[str] = []
        for task in state.actual_graph.tasks:
            if task.status is TaskStatus.READY and not set(task.dependencies).issubset(completed):
                task.status = TaskStatus.WAITING
                invalidated.append(task.task_id)
        return invalidated

    def recompute_ready_tasks(self, state: RuntimeState) -> list[Task]:
        self.invalidate_ready_state(state)
        completed = {
            task.task_id for task in state.actual_graph.tasks if task.status is TaskStatus.COMPLETED
        }
        ready: list[Task] = []
        for task in state.actual_graph.tasks:
            if task.status in {TaskStatus.WAITING, TaskStatus.BLOCKED} and set(
                task.dependencies
            ).issubset(completed):
                task.status = TaskStatus.READY
                ready.append(task)
        return ready

    async def _apply_atomic(
        self,
        *,
        state: RuntimeState,
        request: ReplanRequest,
        actor: GraphMutationActor,
        operations: list[_Operation],
    ) -> ActualRuntimeGraph:
        self._validate_authority(state=state, request=request, actor=actor)
        original = state.actual_graph
        staged = original.model_copy(deep=True)
        audit_operations: list[dict[str, str]] = []
        for operation in operations:
            self._apply_operation(staged, operation, audit_operations)
        self._validate_graph(staged)

        previous_version = original.version
        staged.version = previous_version + 1
        staged.mutation_history.append(
            {
                "replan_id": request.replan_id,
                "approved_by": actor.actor_id,
                "version_before": previous_version,
                "version_after": staged.version,
                "operations": audit_operations,
                "created_task_ids": [
                    operation.task.task_id
                    for operation in operations
                    if operation.kind == "add_node" and operation.task is not None
                ],
            }
        )
        state.actual_graph = staged
        self.invalidate_ready_state(state)
        try:
            await self._emit_audit_events(
                state=state,
                request=request,
                previous_version=previous_version,
                operations=operations,
            )
        except Exception:
            state.actual_graph = original
            raise
        return state.actual_graph.model_copy(deep=True)

    def _validate_authority(
        self,
        *,
        state: RuntimeState,
        request: ReplanRequest,
        actor: GraphMutationActor,
    ) -> None:
        if actor.role not in self._AUTHORIZED_ROLES:
            raise GraphMutationPermissionError("only Research Lead or Planner may mutate the graph")
        if request.decision is not ReplanDecision.APPROVED:
            raise GraphMutationPermissionError("graph mutation requires an approved replan")
        if not request.decided_by or request.decided_by != actor.actor_id:
            raise GraphMutationPermissionError(
                "mutation actor must be the approving Lead or Planner"
            )
        if request.run_id != state.run_id:
            raise GraphMutationValidationError("replan belongs to a different run")
        if request.requesting_task_id not in {task.task_id for task in state.actual_graph.tasks}:
            raise GraphMutationValidationError("replan requesting task is not in the actual graph")

    def _apply_operation(
        self,
        graph: ActualRuntimeGraph,
        operation: _Operation,
        audit: list[dict[str, str]],
    ) -> None:
        if operation.kind == "add_node":
            assert operation.task is not None
            task = operation.task.model_copy(deep=True)
            if task.run_id != graph.run_id:
                raise GraphMutationValidationError("new task belongs to a different run")
            if task.status is not TaskStatus.CREATED:
                raise GraphMutationValidationError("new graph tasks must start in CREATED status")
            if any(existing.task_id == task.task_id for existing in graph.tasks):
                raise GraphMutationValidationError("graph mutation contains duplicate task ids")
            graph.tasks.append(task)
            audit.append({"operation": "add_node", "task_id": task.task_id})
            return

        source = operation.source_task_id
        target = operation.target_task_id
        assert source is not None and target is not None
        task_ids = {task.task_id for task in graph.tasks}
        unknown = {task_id for task_id in (source, target) if task_id not in task_ids}
        if unknown:
            raise GraphMutationValidationError(f"unknown graph task ids: {sorted(unknown)}")
        target_task = next(task for task in graph.tasks if task.task_id == target)
        if target_task.status in self._DEPENDENCY_IMMUTABLE_STATUSES:
            raise GraphMutationValidationError(
                f"cannot mutate dependencies of {target_task.status.value} task: {target}"
            )
        if operation.kind == "add_edge":
            if source in target_task.dependencies:
                raise GraphMutationValidationError(f"graph edge already exists: {source}->{target}")
            target_task.dependencies.append(source)
        else:
            if source not in target_task.dependencies:
                raise GraphMutationValidationError(f"graph edge does not exist: {source}->{target}")
            target_task.dependencies.remove(source)
        audit.append(
            {
                "operation": operation.kind,
                "source_task_id": source,
                "target_task_id": target,
            }
        )

    def _validate_graph(self, graph: ActualRuntimeGraph) -> None:
        ids = [task.task_id for task in graph.tasks]
        if len(ids) != len(set(ids)):
            raise GraphMutationValidationError("task ids must be unique")
        known = set(ids)
        unknown = {
            dependency
            for task in graph.tasks
            for dependency in task.dependencies
            if dependency not in known
        }
        if unknown:
            raise GraphMutationValidationError(f"unknown task dependencies: {sorted(unknown)}")
        if any(task.task_id in task.dependencies for task in graph.tasks):
            raise GraphMutationValidationError("self-referential graph edge is not allowed")
        remaining = set(ids)
        dependencies = {task.task_id: set(task.dependencies) for task in graph.tasks}
        while remaining:
            ready = {task_id for task_id in remaining if not dependencies[task_id] & remaining}
            if not ready:
                raise GraphMutationValidationError("graph mutation would create a dependency cycle")
            remaining -= ready

    async def _emit_audit_events(
        self,
        *,
        state: RuntimeState,
        request: ReplanRequest,
        previous_version: int,
        operations: list[_Operation],
    ) -> None:
        for operation in operations:
            if operation.kind == "add_node":
                assert operation.task is not None
                await self._event_store.emit(
                    run_id=state.run_id,
                    task_id=operation.task.task_id,
                    event_type=RuntimeEventType.GRAPH_TASK_ADDED,
                    payload={
                        "replan_id": request.replan_id,
                        "graph_version": state.actual_graph.version,
                    },
                )
                for dependency in operation.task.dependencies:
                    await self._emit_edge_event(
                        state=state,
                        request=request,
                        event_type=RuntimeEventType.GRAPH_EDGE_ADDED,
                        source_task_id=dependency,
                        target_task_id=operation.task.task_id,
                    )
                continue
            await self._emit_edge_event(
                state=state,
                request=request,
                event_type=(
                    RuntimeEventType.GRAPH_EDGE_ADDED
                    if operation.kind == "add_edge"
                    else RuntimeEventType.GRAPH_EDGE_REMOVED
                ),
                source_task_id=operation.source_task_id,
                target_task_id=operation.target_task_id,
            )
        # The final version event is its own durable snapshot boundary.  Yield a
        # bounded observation window after the preceding sparse graph delta.
        await asyncio.sleep(10.0)
        await self._event_store.emit(
            run_id=state.run_id,
            event_type=RuntimeEventType.GRAPH_VERSION_CHANGED,
            payload={
                "replan_id": request.replan_id,
                "version_before": previous_version,
                "version_after": state.actual_graph.version,
            },
        )

    async def _emit_edge_event(
        self,
        *,
        state: RuntimeState,
        request: ReplanRequest,
        event_type: RuntimeEventType,
        source_task_id: str | None,
        target_task_id: str | None,
    ) -> None:
        assert source_task_id is not None and target_task_id is not None
        await self._event_store.emit(
            run_id=state.run_id,
            task_id=target_task_id,
            event_type=event_type,
            payload={
                "replan_id": request.replan_id,
                "graph_version": state.actual_graph.version,
                "source_task_id": source_task_id,
                "target_task_id": target_task_id,
            },
        )
