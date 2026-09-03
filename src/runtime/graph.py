from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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


class GraphMutationService:
    """Applies approved replans without ever changing the planned graph."""

    _AUTHORIZED_ROLES = frozenset(
        {GraphMutationRole.RESEARCH_LEAD, GraphMutationRole.PLANNER}
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
        self._validate(state=state, request=request, tasks=tasks, actor=actor)

        previous_version = state.actual_graph.version
        task_copies = [task.model_copy(deep=True) for task in tasks]
        state.actual_graph.tasks.extend(task_copies)
        state.actual_graph.version += 1
        state.actual_graph.mutation_history.append(
            {
                "replan_id": request.replan_id,
                "approved_by": actor.actor_id,
                "version_before": previous_version,
                "version_after": state.actual_graph.version,
                "created_task_ids": [task.task_id for task in task_copies],
            }
        )

        for task in task_copies:
            await self._event_store.emit(
                run_id=state.run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.GRAPH_TASK_ADDED,
                payload={
                    "replan_id": request.replan_id,
                    "graph_version": state.actual_graph.version,
                },
            )
        await self._event_store.emit(
            run_id=state.run_id,
            event_type=RuntimeEventType.GRAPH_VERSION_CHANGED,
            payload={
                "replan_id": request.replan_id,
                "version_before": previous_version,
                "version_after": state.actual_graph.version,
            },
        )
        return state.actual_graph.model_copy(deep=True)

    def _validate(
        self,
        *,
        state: RuntimeState,
        request: ReplanRequest,
        tasks: list[Task],
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
        if request.requesting_task_id not in {
            task.task_id for task in state.actual_graph.tasks
        }:
            raise GraphMutationValidationError("replan requesting task is not in the actual graph")
        if not tasks:
            raise GraphMutationValidationError("graph mutation must add at least one task")

        existing_ids = {task.task_id for task in state.actual_graph.tasks}
        added_ids = {task.task_id for task in tasks}
        if len(added_ids) != len(tasks) or existing_ids & added_ids:
            raise GraphMutationValidationError("graph mutation contains duplicate task ids")
        if any(task.run_id != state.run_id for task in tasks):
            raise GraphMutationValidationError("new task belongs to a different run")
        if any(task.status is not TaskStatus.CREATED for task in tasks):
            raise GraphMutationValidationError("new graph tasks must start in CREATED status")

        known_ids = existing_ids | added_ids
        unknown = {
            dependency
            for task in tasks
            for dependency in task.dependencies
            if dependency not in known_ids
        }
        if unknown:
            raise GraphMutationValidationError(f"unknown task dependencies: {sorted(unknown)}")
