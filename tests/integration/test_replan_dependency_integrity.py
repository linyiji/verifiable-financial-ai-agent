from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from src.domain.enums import ReplanDecision, TaskStatus
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.domain.task import PlannedTaskGraph, ReplanRequest, Task
from src.runtime.checkpoint import RuntimeCheckpoint
from src.runtime.events import InMemoryRuntimeEventStore
from src.runtime.graph import (
    GraphMutationActor,
    GraphMutationRole,
    GraphMutationService,
    GraphMutationValidationError,
)
from src.runtime.state import RuntimeState, RuntimeStateError


def _task(task_id: str, dependencies: list[str] | None = None) -> Task:
    return Task(
        task_id=task_id,
        run_id="RUN-1",
        task_type="test",
        goal=task_id,
        assigned_agent="test-agent",
        skill_id="test-skill",
        dependencies=dependencies or [],
    )


def _state() -> RuntimeState:
    return RuntimeState.create(
        run_id="RUN-1",
        planned_graph=PlannedTaskGraph(
            graph_id="PLAN-1",
            run_id="RUN-1",
            tasks=[
                _task("RISK"),
                _task("SYNTHESIS", ["RISK"]),
            ],
        ),
    )


def _request() -> ReplanRequest:
    return ReplanRequest(
        replan_id="REPLAN-1",
        run_id="RUN-1",
        requesting_task_id="RISK",
        requested_by="risk-agent",
        reason_code="MATERIAL_RISK_FOLLOW_UP",
        reason_detail="Add a bounded follow-up",
        proposed_graph_change={"operation": "insert_task_between"},
        decision=ReplanDecision.APPROVED,
        decided_by="lead-1",
    )


def _actor() -> GraphMutationActor:
    return GraphMutationActor("lead-1", GraphMutationRole.RESEARCH_LEAD)


@pytest.mark.asyncio
async def test_insert_between_is_one_versioned_audited_atomic_mutation() -> None:
    state = _state()
    events = InMemoryRuntimeEventStore()
    follow_up = _task("FOLLOW-UP")

    await GraphMutationService(events).insert_node_between(
        state=state,
        request=_request(),
        task=follow_up,
        predecessor_task_id="RISK",
        successor_task_id="SYNTHESIS",
        actor=_actor(),
    )

    assert state.actual_graph.version == 2
    assert state.task("FOLLOW-UP").dependencies == ["RISK"]
    assert state.task("SYNTHESIS").dependencies == ["FOLLOW-UP"]
    assert state.planned_graph.tasks[-1].dependencies == ["RISK"]
    assert state.actual_graph.mutation_history[-1]["version_before"] == 1
    assert state.actual_graph.mutation_history[-1]["version_after"] == 2
    graph_events = await events.replay("RUN-1")
    assert [event.type for event in graph_events] == [
        RuntimeEventType.GRAPH_TASK_ADDED,
        RuntimeEventType.GRAPH_EDGE_ADDED,
        RuntimeEventType.GRAPH_EDGE_REMOVED,
        RuntimeEventType.GRAPH_EDGE_ADDED,
        RuntimeEventType.GRAPH_VERSION_CHANGED,
    ]
    assert [
        (event.payload["source_task_id"], event.payload["target_task_id"])
        for event in graph_events
        if event.type in {RuntimeEventType.GRAPH_EDGE_ADDED, RuntimeEventType.GRAPH_EDGE_REMOVED}
    ] == [
        ("RISK", "FOLLOW-UP"),
        ("RISK", "SYNTHESIS"),
        ("FOLLOW-UP", "SYNTHESIS"),
    ]


@pytest.mark.asyncio
async def test_invalid_cycle_rolls_back_graph_version_and_emits_no_audit() -> None:
    state = _state()
    original = state.actual_graph.model_dump()
    events = InMemoryRuntimeEventStore()

    with pytest.raises(GraphMutationValidationError, match="dependency cycle"):
        await GraphMutationService(events).add_edge(
            state=state,
            request=_request(),
            source_task_id="SYNTHESIS",
            target_task_id="RISK",
            actor=_actor(),
        )

    assert state.actual_graph.model_dump() == original
    assert await events.replay("RUN-1") == []


@pytest.mark.asyncio
async def test_public_edge_operations_each_commit_one_validated_version() -> None:
    state = _state()
    events = InMemoryRuntimeEventStore()
    service = GraphMutationService(events)

    await service.add_node(
        state=state,
        request=_request(),
        task=_task("ALTERNATE"),
        actor=_actor(),
    )
    assert state.actual_graph.version == 2
    await service.replace_dependency(
        state=state,
        request=_request(),
        target_task_id="SYNTHESIS",
        old_dependency_id="RISK",
        new_dependency_id="ALTERNATE",
        actor=_actor(),
    )
    assert state.actual_graph.version == 3
    assert state.task("SYNTHESIS").dependencies == ["ALTERNATE"]
    await service.remove_edge(
        state=state,
        request=_request(),
        source_task_id="ALTERNATE",
        target_task_id="SYNTHESIS",
        actor=_actor(),
    )
    assert state.actual_graph.version == 4
    await service.add_edge(
        state=state,
        request=_request(),
        source_task_id="RISK",
        target_task_id="SYNTHESIS",
        actor=_actor(),
    )
    assert state.actual_graph.version == 5
    assert state.task("SYNTHESIS").dependencies == ["RISK"]
    assert (
        sum(
            event.type is RuntimeEventType.GRAPH_VERSION_CHANGED
            for event in await events.replay("RUN-1")
        )
        == 4
    )


class _FailingAuditStore(InMemoryRuntimeEventStore):
    async def emit(
        self,
        *,
        run_id: str,
        event_type: RuntimeEventType,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> RuntimeEvent:
        del run_id, event_type, task_id, payload, timestamp
        raise RuntimeError("audit unavailable")


@pytest.mark.asyncio
async def test_audit_failure_restores_original_graph_reference() -> None:
    state = _state()
    original = state.actual_graph

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await GraphMutationService(_FailingAuditStore()).add_node(
            state=state,
            request=_request(),
            task=_task("FOLLOW-UP"),
            actor=_actor(),
        )

    assert state.actual_graph is original
    assert state.actual_graph.version == 1
    assert {task.task_id for task in state.actual_graph.tasks} == {"RISK", "SYNTHESIS"}


def test_dependency_change_invalidates_and_recomputes_ready_state() -> None:
    state = _state()
    service = GraphMutationService(InMemoryRuntimeEventStore())
    state.task("RISK").status = TaskStatus.COMPLETED
    state.task("SYNTHESIS").status = TaskStatus.READY
    state.task("SYNTHESIS").dependencies = ["FOLLOW-UP"]
    follow_up = _task("FOLLOW-UP")
    follow_up.status = TaskStatus.WAITING
    state.actual_graph.tasks.append(follow_up)

    assert service.invalidate_ready_state(state) == ["SYNTHESIS"]
    assert state.task("SYNTHESIS").status is TaskStatus.WAITING
    assert [task.task_id for task in service.recompute_ready_tasks(state)] == ["FOLLOW-UP"]
    state.task("FOLLOW-UP").status = TaskStatus.COMPLETED
    assert [task.task_id for task in service.recompute_ready_tasks(state)] == ["SYNTHESIS"]


@pytest.mark.asyncio
async def test_checkpoint_restore_preserves_mutated_dependencies_and_version() -> None:
    state = _state()
    await GraphMutationService(InMemoryRuntimeEventStore()).insert_node_between(
        state=state,
        request=_request(),
        task=_task("FOLLOW-UP"),
        predecessor_task_id="RISK",
        successor_task_id="SYNTHESIS",
        actor=_actor(),
    )
    checkpoint = RuntimeCheckpoint.capture(checkpoint_id="CHECKPOINT-1", state=state)
    restored = checkpoint.restore(planned_graph=state.planned_snapshot())

    assert restored.actual_graph.version == 2
    assert restored.task("FOLLOW-UP").dependencies == ["RISK"]
    assert restored.task("SYNTHESIS").dependencies == ["FOLLOW-UP"]
    assert restored.planned_graph.tasks[-1].dependencies == ["RISK"]

    tampered = checkpoint.model_copy(update={"actual_graph_version": 99})
    with pytest.raises(RuntimeStateError, match="version"):
        tampered.restore(planned_graph=state.planned_snapshot())
