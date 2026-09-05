from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.enums import RunStatus, TaskStatus
from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph, Task


class RuntimeStateError(ValueError):
    """Raised when runtime state cannot be constructed or updated safely."""


@dataclass(slots=True)
class RuntimeState:
    """Mutable execution state with separate planned and actual graph snapshots.

    ``create`` deep-copies the approved plan twice. Runtime operations only mutate
    ``actual_graph``; the planned copy remains the audit record of the approved route.
    """

    run_id: str
    planned_graph: PlannedTaskGraph
    actual_graph: ActualRuntimeGraph
    run_status: RunStatus = RunStatus.PLANNING
    completed_output_refs: dict[str, list[str]] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    workspace_refs: list[str] = field(default_factory=list)
    review_state: dict[str, Any] = field(default_factory=dict)
    proof_state: dict[str, Any] = field(default_factory=dict)
    cost: float = 0.0

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        planned_graph: PlannedTaskGraph,
        actual_graph_id: str | None = None,
    ) -> RuntimeState:
        if planned_graph.run_id != run_id:
            raise RuntimeStateError("planned graph belongs to a different run")

        foreign_tasks = sorted(
            task.task_id for task in planned_graph.tasks if task.run_id != run_id
        )
        if foreign_tasks:
            raise RuntimeStateError(
                f"planned graph contains tasks from a different run: {foreign_tasks}"
            )

        remaining = {task.task_id for task in planned_graph.tasks}
        dependencies = {task.task_id: set(task.dependencies) for task in planned_graph.tasks}
        while remaining:
            ready = {
                task_id
                for task_id in remaining
                if not dependencies[task_id].intersection(remaining)
            }
            if not ready:
                raise RuntimeStateError("planned graph contains a dependency cycle")
            remaining.difference_update(ready)

        planned_snapshot = planned_graph.model_copy(deep=True)
        actual = ActualRuntimeGraph(
            graph_id=actual_graph_id or f"{planned_graph.graph_id}-actual",
            run_id=run_id,
            version=1,
            tasks=[task.model_copy(deep=True) for task in planned_graph.tasks],
        )
        return cls(run_id=run_id, planned_graph=planned_snapshot, actual_graph=actual)

    def task(self, task_id: str) -> Task:
        for task in self.actual_graph.tasks:
            if task.task_id == task_id:
                return task
        raise KeyError(f"unknown runtime task: {task_id}")

    @property
    def task_states(self) -> dict[str, TaskStatus]:
        return {task.task_id: task.status for task in self.actual_graph.tasks}

    def planned_snapshot(self) -> PlannedTaskGraph:
        """Return a defensive copy suitable for audit comparison."""

        return self.planned_graph.model_copy(deep=True)
