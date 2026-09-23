"""Future failure construction uses the production root/event transaction."""
import asyncio
import os
from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from src.application.persistence import (
    ResearchRunAggregateRow,
    RuntimeEventRow,
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
    TerminalSettlementBudget,
)
from src.application.resume_runtime import require_terminal_event
from src.application.terminal_failure import failure_command
from src.domain.node_binding import BindingDenied
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from tests.external_failure_resume.runtime_fixture import legal_fixture
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL required",
)


@pytest.mark.parametrize("fault", ["event", "children", "closure"])
async def test_failure_atomic_rollback_retry_and_mismatch(
    database, tmp_path, monkeypatch, fault,  # noqa: F811
):
    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    store = PostgresRuntimeEventStore(sessions)
    service, initial, _ = await legal_fixture(
        tmp_path, repository=repo, evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions), event_store=store,
    )
    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    run_id = initial.run.run_id
    captured = {}
    finalize = repo.finalize_failure

    async def capture(owner, proposed, **kwargs):
        captured.update(owner=owner, proposed=deepcopy(proposed), kwargs=kwargs)
        return await finalize(owner, proposed, **kwargs)

    monkeypatch.setattr(repo, "finalize_failure", capture)
    method = {"event": "_persist_terminal_failure", "children": "_persist_children",
              "closure": "_close_execution_state"}[fault]
    original = getattr(repo, method)

    async def fail(*args, **kwargs):
        await original(*args, **kwargs)
        if captured:
            raise RuntimeError("injected terminal rollback")

    monkeypatch.setattr(repo, method, fail)
    for _ in range(2):
        try:
            await service.execute_run(run_id)
        except RuntimeError as exc:
            assert str(exc) == "injected terminal rollback"
        if captured:
            break
    assert captured
    value = await repo.get_run_fresh(run_id)
    assert value.run.status.value != "FAILED"
    assert value.run.completed_at is None
    assert not any(e.type.value == "run.failed" for e in await store.replay(run_id))
    monkeypatch.setattr(repo, method, original)
    owner, proposed, kwargs = captured["owner"], captured["proposed"], captured["kwargs"]
    if fault == "event":
        command = failure_command(owner, proposed, kwargs["unknown"], kwargs["payload"])
        async with sessions() as session:
            row = await session.get(ResearchRunAggregateRow, run_id)
            command["search_path"] = await session.scalar(text("SELECT current_schema()"))
            command["baseline"] = {
                "payload": deepcopy(row.payload), "status": row.status,
                "projection_revision": row.projection_revision,
                "projection_sequence": row.projection_sequence,
                "last_event_sequence": max(
                    (event.sequence for event in await store.replay(run_id)), default=0,
                ),
            }
        assert await repo._read_failure_outcome(
            owner, command,
            TerminalSettlementBudget(asyncio.get_running_loop().time() + 30),
        ) is None
    # Two independent repository instances compete with exactly the same command.
    events = await asyncio.gather(*(
        SQLAlchemyApplicationRepository(sessions).finalize_failure(owner, proposed, **kwargs)
        for _ in range(2)
    ))
    assert events[0] == events[1]
    terminal = events[0]
    value = await repo.get_run_fresh(run_id)
    require_terminal_event(value, terminal)
    all_events = await store.replay(run_id)
    assert all_events[-2].type.value == "task.failed"
    assert all_events[-1] == terminal
    assert terminal.timestamp == value.run.completed_at
    assert len([e for e in all_events if e.type.value == "run.failed"]) == 1
    assert (await service.event_store.replay(run_id)) == all_events

    async def snapshot():
        async with sessions() as session:
            row = await session.get(ResearchRunAggregateRow, run_id)
            raw = list(await session.scalars(select(RuntimeEventRow).where(
                RuntimeEventRow.run_id == run_id,
            ).order_by(RuntimeEventRow.sequence)))
            assert row.projection_sequence == terminal.sequence
            return deepcopy((row.payload, row.projection_revision, [e.payload for e in raw]))

    before = await snapshot()
    for mismatch in ("payload", "revision", "timestamp"):
        changed = deepcopy(proposed)
        arguments = dict(kwargs, payload=deepcopy(kwargs["payload"]))
        if mismatch == "payload":
            arguments["payload"]["failure_code"] = "WRONG"
        elif mismatch == "revision":
            changed.node_binding.binding_revision += 1
        else:
            changed.run.completed_at += timedelta(seconds=1)
        with pytest.raises(BindingDenied, match="IDENTITY_MISMATCH"):
            await repo.finalize_failure(owner, changed, **arguments)
    assert await snapshot() == before
    # Persist corruption only inside a transaction which is always rolled back.
    # Exercise the production event decoder rather than a duplicate test validator.
    for mismatch in ("payload", "hash", "revision"):
        async with sessions() as session, session.begin():
            row = await session.get(RuntimeEventRow, terminal.event_id)
            payload = deepcopy(row.payload)
            if mismatch == "payload":
                payload["payload"]["failure_code"] = "WRONG"
            elif mismatch == "hash":
                payload["payload"]["terminal_failure"]["payload_digest"] = "WRONG"
            else:
                payload["payload"]["terminal_failure"]["binding_ref"]["binding_revision"] += 1
            row.payload = payload
            with pytest.raises(BindingDenied, match="IDENTITY_MISMATCH"):
                store._decode_row(run_id, row)
            await session.rollback()
    assert await snapshot() == before
    await backend.close()


async def test_success_terminal_publication_is_unchanged(database, tmp_path):  # noqa: F811
    """Synthetic release facts exercise success owners, not financial Release policy."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from src.domain.enums import RunStatus

    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    store = PostgresRuntimeEventStore(sessions)
    service, initial, _ = await legal_fixture(
        tmp_path, repository=repo, evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions), event_store=store,
    )
    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    owner = await repo.claim_execution(initial.run.run_id)
    current = await repo.validate_execution(owner)
    timestamp = datetime.now(UTC)
    service._apply_terminal_lifecycle(current, status=RunStatus.RELEASED, terminal_at=timestamp)
    await repo.save_run(current)
    committed = await repo.close_execution(owner)
    await service._emit_release_completion(SimpleNamespace(
        run=committed.run, artifacts=SimpleNamespace(
            canonical_record=SimpleNamespace(record_id="synthetic-success-record"),
            released_result=SimpleNamespace(result_id="synthetic-success-result"),
        ),
    ))
    fresh = await SQLAlchemyApplicationRepository(sessions).get_run_fresh(initial.run.run_id)
    events = await service.event_store.replay(initial.run.run_id)
    assert [e.type.value for e in events[-2:]] == ["release.completed", "run.completed"]
    assert events[-1].payload == {"status": "RELEASED"}
    assert events[-1].timestamp == fresh.run.completed_at == timestamp
    assert fresh.node_binding.lifecycle == "CLOSED"
    assert not any(e.type.value == "run.failed" for e in events)
    await backend.close()
