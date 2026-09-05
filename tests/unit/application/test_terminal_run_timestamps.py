from __future__ import annotations

from datetime import date

import pytest

from src.application.service import ResearchApplicationService
from src.domain.enums import RunStatus
from src.domain.runtime_event import RuntimeEventType
from src.runtime.scheduler import DependencyScheduler


async def _confirmed_service() -> tuple[ResearchApplicationService, str]:
    service = ResearchApplicationService()
    research_object = await service.create_object(
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
    )
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Verify terminal timestamp semantics",
        as_of=date(2026, 9, 5),
        preferences={},
    )
    aggregate = await service.confirm_run(
        draft_id=draft.draft_id,
        confirm_scheme=True,
    )
    return service, aggregate.run.run_id


@pytest.mark.asyncio
async def test_new_nonterminal_run_has_no_completion_timestamp() -> None:
    service, run_id = await _confirmed_service()

    aggregate = await service.get_run(run_id)

    assert aggregate.run.status is RunStatus.PLANNING
    assert aggregate.run.started_at is None
    assert aggregate.run.completed_at is None
    assert aggregate.run.created_at <= aggregate.run.updated_at


@pytest.mark.asyncio
async def test_success_terminal_timestamp_matches_final_runtime_event() -> None:
    service, run_id = await _confirmed_service()

    aggregate = await service.execute_run(run_id)
    events = await service.event_store.replay(run_id)
    terminal_event = events[-1]
    release_event = events[-2]

    assert aggregate.run.status is RunStatus.RELEASED
    assert release_event.type is RuntimeEventType.RELEASE_COMPLETED
    assert terminal_event.type is RuntimeEventType.RUN_COMPLETED
    assert release_event.timestamp <= terminal_event.timestamp
    assert aggregate.run.completed_at == terminal_event.timestamp
    assert aggregate.run.started_at is not None
    assert aggregate.run.started_at <= terminal_event.timestamp <= aggregate.run.updated_at


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", [RunStatus.FAILED, RunStatus.CANCELLED])
async def test_existing_failure_event_remains_authoritative_for_terminal_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: RunStatus,
) -> None:
    service, run_id = await _confirmed_service()

    async def fail_after_terminal_event(
        scheduler: DependencyScheduler,
        *,
        state,
        executor,
        emit_run_started: bool = True,
    ):
        del executor, emit_run_started
        state.run_status = terminal_status
        await scheduler._event_store.emit(
            run_id=state.run_id,
            event_type=RuntimeEventType.RUN_FAILED,
            payload={
                "status": terminal_status.value,
                "failure_stage": (
                    "CANCELLATION" if terminal_status is RunStatus.CANCELLED else "TASK_EXECUTION"
                ),
                "failure_code": (
                    "RUN_CANCELLED"
                    if terminal_status is RunStatus.CANCELLED
                    else "TASK_EXECUTION_FAILED"
                ),
            },
        )
        raise RuntimeError("controlled terminal failure")

    monkeypatch.setattr(DependencyScheduler, "execute", fail_after_terminal_event)

    with pytest.raises(RuntimeError, match="controlled terminal failure"):
        await service.execute_run(run_id)

    aggregate = await service.get_run(run_id)
    events = await service.event_store.replay(run_id)
    terminal_event = events[-1]
    assert terminal_event.type is RuntimeEventType.RUN_FAILED
    assert terminal_event.payload["status"] == terminal_status.value
    assert aggregate.run.status is terminal_status
    assert aggregate.run.completed_at == terminal_event.timestamp
    assert aggregate.run.started_at is not None
    assert aggregate.run.started_at <= terminal_event.timestamp <= aggregate.run.updated_at


@pytest.mark.asyncio
async def test_post_scheduler_failure_uses_one_timestamp_for_event_and_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, run_id = await _confirmed_service()

    async def fail_without_terminal_event(
        scheduler: DependencyScheduler,
        *,
        state,
        executor,
        emit_run_started: bool = True,
    ):
        del scheduler, state, executor, emit_run_started
        raise RuntimeError("controlled post-scheduler failure")

    monkeypatch.setattr(DependencyScheduler, "execute", fail_without_terminal_event)

    with pytest.raises(RuntimeError, match="controlled post-scheduler failure"):
        await service.execute_run(run_id)

    aggregate = await service.get_run(run_id)
    terminal_event = (await service.event_store.replay(run_id))[-1]
    assert terminal_event.type is RuntimeEventType.RUN_FAILED
    assert terminal_event.payload == {
        "status": "FAILED",
        "failure_stage": "POST_SCHEDULER",
        "failure_code": "POST_SCHEDULER_FAILED",
        "safe_message": "The Run could not complete its release checks.",
    }
    assert aggregate.run.status is RunStatus.FAILED
    assert aggregate.run.completed_at == terminal_event.timestamp
    assert aggregate.run.started_at is not None
    assert aggregate.run.started_at <= terminal_event.timestamp <= aggregate.run.updated_at
