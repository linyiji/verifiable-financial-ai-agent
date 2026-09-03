from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Protocol, runtime_checkable

from pydantic import Field

from src.domain.base import JsonObject, TimestampedModel
from src.domain.enums import RunStatus, TaskStatus
from src.runtime.state import RuntimeState


class RuntimeCheckpoint(TimestampedModel):
    checkpoint_id: str
    run_id: str
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
        return cls(
            checkpoint_id=checkpoint_id,
            run_id=state.run_id,
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


@runtime_checkable
class CheckpointStore(Protocol):
    async def save(self, checkpoint: RuntimeCheckpoint) -> None: ...

    async def load_latest(self, run_id: str) -> RuntimeCheckpoint | None: ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._checkpoints: dict[str, list[RuntimeCheckpoint]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def save(self, checkpoint: RuntimeCheckpoint) -> None:
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
            return self._checkpoints[run_id][-1].model_copy(deep=True)
