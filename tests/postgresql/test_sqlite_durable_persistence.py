from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.domain.enums import RunStatus, TaskStatus
from src.domain.task import PlannedTaskGraph, Task
from src.infrastructure.database.base import Base
from src.infrastructure.database.checkpoints import (
    SQLAlchemyCheckpointStore,
    restore_runtime_state,
)
from src.runtime.checkpoint import RuntimeCheckpoint
from src.runtime.state import RuntimeState


@pytest.mark.asyncio
async def test_sqlite_keeps_complete_run_record_repositories(tmp_path, monkeypatch) -> None:
    # Positive record/release assertions are conserved on actual PostgreSQL in
    # test_replan_released_record_repository_conservation (BR06/07/11).
    from tests.risk_replan.backend_fixture import assert_sqlite_replan_denied

    await assert_sqlite_replan_denied(tmp_path, monkeypatch)


def _planned_graph() -> PlannedTaskGraph:
    return PlannedTaskGraph(
        graph_id="PLAN-1",
        run_id="RUN-1",
        tasks=[
            Task(
                task_id="TASK-1",
                run_id="RUN-1",
                task_type="test",
                goal="Persist checkpoint",
                assigned_agent="test-agent",
                skill_id="test-skill",
                status=TaskStatus.COMPLETED,
                progress=1.0,
            )
        ],
    )


@pytest.mark.asyncio
async def test_sqlite_checkpoint_latest_and_runtime_restore(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'checkpoints.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = SQLAlchemyCheckpointStore(sessions)
    plan = _planned_graph()
    state = RuntimeState.create(run_id="RUN-1", planned_graph=plan)
    state.actual_graph.tasks[0].status = TaskStatus.COMPLETED
    state.actual_graph.tasks[0].progress = 1.0
    state.run_status = RunStatus.REVIEW
    state.completed_output_refs = {"TASK-1": ["result://task-1"]}
    first_time = datetime(2026, 9, 4, tzinfo=UTC)
    first = RuntimeCheckpoint.capture(checkpoint_id="CP-1", state=state).model_copy(
        update={"created_at": first_time}
    )
    second = first.model_copy(
        deep=True,
        update={
            "checkpoint_id": "CP-2",
            "created_at": first_time + timedelta(seconds=1),
            "cost": 1.25,
        },
    )

    await store.save(first)
    await store.save(second)
    latest = await store.load_latest("RUN-1")

    assert latest is not None and latest.checkpoint_id == "CP-2"
    restored = restore_runtime_state(latest, planned_graph=plan)
    assert restored.run_status is RunStatus.REVIEW
    assert restored.task("TASK-1").status is TaskStatus.COMPLETED
    assert restored.completed_output_refs == {"TASK-1": ["result://task-1"]}
    assert restored.cost == 1.25
    await engine.dispose()
