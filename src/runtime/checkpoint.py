from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Protocol, runtime_checkable

from pydantic import Field

from src.domain.base import JsonObject, TimestampedModel
from src.domain.enums import RunStatus, TaskStatus
from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph
from src.runtime.state import RuntimeState, RuntimeStateError


class RuntimeCheckpointIntegrityError(RuntimeStateError):
    """Raised before a malformed or cross-Run checkpoint can replace runtime state."""


class RuntimeCheckpoint(TimestampedModel):
    checkpoint_id: str
    run_id: str
    planned_graph_id: str = Field(min_length=1)
    actual_graph_id: str = Field(min_length=1)
    run_status: RunStatus
    task_states: dict[str, TaskStatus]
    actual_graph_version: int = Field(ge=1)
    actual_graph: JsonObject
    completed_output_refs: dict[str, list[str]] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    workspace_refs: list[str] = Field(default_factory=list)
    review_state: JsonObject = Field(default_factory=dict)
    proof_state: JsonObject = Field(default_factory=dict)
    cost: float = Field(default=0.0, ge=0.0)

    @classmethod
    def capture(cls, *, checkpoint_id: str, state: RuntimeState) -> RuntimeCheckpoint:
        _validate_runtime_state_identity(state)
        return cls(
            checkpoint_id=checkpoint_id,
            run_id=state.run_id,
            planned_graph_id=state.planned_graph.graph_id,
            actual_graph_id=state.actual_graph.graph_id,
            run_status=state.run_status,
            task_states=state.task_states,
            actual_graph_version=state.actual_graph.version,
            actual_graph=state.actual_graph.model_dump(mode="json"),
            completed_output_refs={
                task_id: list(refs) for task_id, refs in state.completed_output_refs.items()
            },
            evidence_refs=list(state.evidence_refs),
            workspace_refs=list(state.workspace_refs),
            review_state=dict(state.review_state),
            proof_state=dict(state.proof_state),
            cost=state.cost,
        )

    def restore(self, *, planned_graph: PlannedTaskGraph) -> RuntimeState:
        """Restore the mutable runtime while retaining the approved plan snapshot."""

        if planned_graph.run_id != self.run_id:
            raise RuntimeCheckpointIntegrityError(
                "checkpoint and planned graph belong to different runs"
            )
        if planned_graph.graph_id != self.planned_graph_id:
            raise RuntimeCheckpointIntegrityError(
                "checkpoint and planned graph identities do not match"
            )
        foreign_planned_tasks = sorted(
            task.task_id for task in planned_graph.tasks if task.run_id != self.run_id
        )
        if foreign_planned_tasks:
            raise RuntimeCheckpointIntegrityError(
                "planned graph contains tasks from a different run"
            )
        actual_graph = self.validate_payload_identity()
        return RuntimeState(
            run_id=self.run_id,
            planned_graph=planned_graph.model_copy(deep=True),
            actual_graph=actual_graph,
            run_status=self.run_status,
            completed_output_refs={
                task_id: list(refs) for task_id, refs in self.completed_output_refs.items()
            },
            evidence_refs=list(self.evidence_refs),
            workspace_refs=list(self.workspace_refs),
            review_state=dict(self.review_state),
            proof_state=dict(self.proof_state),
            cost=self.cost,
        )

    def validate_payload_identity(self) -> ActualRuntimeGraph:
        """Validate the self-contained actual-graph closure before using a checkpoint."""

        try:
            actual_graph = ActualRuntimeGraph.model_validate(self.actual_graph)
        except (TypeError, ValueError) as exc:
            raise RuntimeCheckpointIntegrityError(
                "checkpoint actual graph payload is malformed"
            ) from exc
        if actual_graph.run_id != self.run_id:
            raise RuntimeCheckpointIntegrityError(
                "checkpoint actual graph belongs to a different run"
            )
        if actual_graph.graph_id != self.actual_graph_id:
            raise RuntimeCheckpointIntegrityError(
                "checkpoint actual graph identity does not match its payload"
            )
        if actual_graph.version != self.actual_graph_version:
            raise RuntimeCheckpointIntegrityError(
                "checkpoint graph version does not match its payload"
            )
        foreign_actual_tasks = sorted(
            task.task_id for task in actual_graph.tasks if task.run_id != self.run_id
        )
        if foreign_actual_tasks:
            raise RuntimeCheckpointIntegrityError(
                "checkpoint actual graph contains tasks from a different run"
            )
        actual_task_states = {task.task_id: task.status for task in actual_graph.tasks}
        if actual_task_states != self.task_states:
            raise RuntimeCheckpointIntegrityError(
                "checkpoint task states do not match its graph payload"
            )
        return actual_graph


@runtime_checkable
class CheckpointStore(Protocol):
    async def save(self, checkpoint: RuntimeCheckpoint) -> None: ...

    async def load_latest(self, run_id: str) -> RuntimeCheckpoint | None: ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._checkpoints: dict[str, list[RuntimeCheckpoint]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def save(self, checkpoint: RuntimeCheckpoint) -> None:
        checkpoint.validate_payload_identity()
        async with self._lock:
            if any(
                existing.checkpoint_id == checkpoint.checkpoint_id
                for existing in self._checkpoints[checkpoint.run_id]
            ):
                raise ValueError(f"duplicate checkpoint id: {checkpoint.checkpoint_id}")
            self._checkpoints[checkpoint.run_id].append(checkpoint.model_copy(deep=True))

    async def load_latest(self, run_id: str) -> RuntimeCheckpoint | None:
        async with self._lock:
            if not self._checkpoints[run_id]:
                return None
            checkpoint = self._checkpoints[run_id][-1].model_copy(deep=True)
            if checkpoint.run_id != run_id:
                raise RuntimeCheckpointIntegrityError(
                    "stored checkpoint belongs to a different run"
                )
            checkpoint.validate_payload_identity()
            return checkpoint


def _validate_runtime_state_identity(state: RuntimeState) -> None:
    if state.planned_graph.run_id != state.run_id:
        raise RuntimeCheckpointIntegrityError(
            "runtime state and planned graph belong to different runs"
        )
    if state.actual_graph.run_id != state.run_id:
        raise RuntimeCheckpointIntegrityError(
            "runtime state and actual graph belong to different runs"
        )
    foreign_planned_tasks = sorted(
        task.task_id for task in state.planned_graph.tasks if task.run_id != state.run_id
    )
    if foreign_planned_tasks:
        raise RuntimeCheckpointIntegrityError("planned graph contains tasks from a different run")
    foreign_actual_tasks = sorted(
        task.task_id for task in state.actual_graph.tasks if task.run_id != state.run_id
    )
    if foreign_actual_tasks:
        raise RuntimeCheckpointIntegrityError("actual graph contains tasks from a different run")
