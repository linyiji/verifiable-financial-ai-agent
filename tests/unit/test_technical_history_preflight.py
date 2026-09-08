import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.persistence import RuntimeEventRow, SQLAlchemyApplicationRepository
from src.application.phase3_financial import (
    _ordered_historical_evidence,
)
from src.domain.enums import TaskStatus
from src.infrastructure.database.base import Base
from src.phase4_product.projections import project_event
from src.runtime.checkpoint import InMemoryCheckpointStore
from src.runtime.diagnostics import InsufficientTechnicalHistoryError, task_failure_diagnostic
from src.runtime.events import InMemoryRuntimeEventStore
from src.runtime.scheduler import DependencyScheduler, RetryPolicy
from src.runtime.sse import encode_sse_event
from tests.unit.test_phase3_financial_extension import _evidence, _state, _task


def short_evidence():
    records = _evidence()
    dates = sorted({e.as_of for e in records if e.period == "DAILY"})[-20:]
    return [e for e in records if e.period != "DAILY" or e.as_of in dates]


@pytest.mark.asyncio
async def test_explicit_required_history_failure_records_private_diagnostic(tmp_path):
    task = _task()
    state = _state(task)
    state.task(task.task_id).status = TaskStatus.READY
    events = InMemoryRuntimeEventStore()

    class Executor:
        async def execute(self, task, context):
            return _ordered_historical_evidence(short_evidence())

    scheduler = DependencyScheduler(
        event_store=events,
        checkpoint_store=InMemoryCheckpointStore(),
        retry_policy=RetryPolicy(max_attempts=3),
    )
    with pytest.raises(InsufficientTechnicalHistoryError):
        await scheduler._execute_task(state, task, Executor())
    emitted = await events.replay(task.run_id)
    assert [e.type.value for e in emitted] == ["task.started", "task.failed"]
    failed = emitted[-1]
    diagnostic = failed.payload["internal_diagnostic"]
    assert diagnostic["available_paired_observations"] == 20
    assert diagnostic["runtime_seam"] == "TECHNICAL_HISTORY_PREFLIGHT"
    assert diagnostic["capability_id"] == "technical_sma_200"
    assert diagnostic["attempt"] == 1
    assert state.task(task.task_id).status is TaskStatus.FAILED
    public = project_event(failed, expected_run_id=task.run_id, known_task_ids=[task.task_id])
    assert "internal_diagnostic" not in public.model_dump_json()
    assert "owned_frames" not in public.model_dump_json()
    assert "internal_diagnostic" not in encode_sse_event(failed)
    assert "owned_frames" not in encode_sse_event(failed)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'diagnostic.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await SQLAlchemyApplicationRepository(sessions).save_runtime_events(emitted)
    async with sessions() as session:
        stored = await session.get(RuntimeEventRow, failed.event_id)
        assert stored.payload["payload"]["internal_diagnostic"] == diagnostic
    await engine.dispose()


def test_history_requires_pairs_not_just_two_hundred_dates():
    records = [e for e in _evidence() if e.period != "DAILY" or e.normalized_field == "close"]
    with pytest.raises(InsufficientTechnicalHistoryError) as failure:
        _ordered_historical_evidence(records)
    assert failure.value.paired_observations == 0


@pytest.mark.parametrize(
    "kind", [ValueError, RuntimeError, type("secret_custom_type", (Exception,), {})]
)
def test_exception_arguments_and_custom_names_never_become_diagnostics(kind):
    secret = "Authorization: Bearer private-token private-prompt hidden-reasoning"
    try:
        raise kind(secret)
    except Exception as error:
        result = task_failure_diagnostic(error, task=_task(), attempt=2)
    encoded = json.dumps(result)
    assert secret not in encoded
    assert "secret_custom_type" not in encoded
    assert "private-token" not in encoded
    assert len(result["owned_frames"]) <= 8
