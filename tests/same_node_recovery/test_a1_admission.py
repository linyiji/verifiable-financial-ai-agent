"""Current evidence must authorize a durable retry before reservation."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from src.application.execution import IntegratedTaskExecutor
from src.application.persistence import SQLAlchemyApplicationRepository
from src.domain.node_binding import BindingDenied
from src.domain.recovery import RecoveryEvidence
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401
from tests.same_node_recovery.test_durable import configured

pytestmark = pytest.mark.skipif(
    not os.environ.get("SAME_NODE_DISPOSABLE_POSTGRES"),
    reason="Disposable PostgreSQL required",
)


async def pending_case(tmp_path, sessions):
    store = RecoveryEvidenceStore(sessions)
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, _, _ = await configured(
        tmp_path, repository=repo, store=store, sessions=sessions,
    )
    pending = await service.execute_run(value.run.run_id)
    target = pending.runtime.actual_graph.tasks[1]
    prior = pending.node_binding.attempts[target.task_id]
    records = await store.records(value.run.run_id, target.task_id)
    terminal = RecoveryEvidence(
        record_id="REC-" + str(uuid4()), scope=records[-1].scope,
        node_reservation_id=prior.admission.attempt_reservation_id,
        kind="TERMINAL", outcome="FAIL", reason_code="NONRECOVERABLE",
        timestamp=datetime.now(UTC).isoformat(),
    )
    return service, pending, target, store, terminal


@pytest.mark.parametrize("case", [
    "recoverable", "terminal", "fresh_startup", "other_operation",
    "other_task", "other_lineage", "succeeded", "budget",
])
async def test_current_admission(database, tmp_path, monkeypatch, case):  # noqa: F811
    _, sessions = database
    service, pending, target, store, terminal = await pending_case(tmp_path, sessions)
    run_id = pending.run.run_id
    if case == "succeeded":
        await service.execute_run(run_id)
    if case == "budget":
        async with service.repository._binding_transaction(run_id) as current:
            prior = current.node_binding.attempts[target.task_id]
            current.node_binding.attempts[target.task_id] = prior.model_copy(
                update={"generation": 3},
            )
    if case in {"terminal", "fresh_startup", "other_operation", "other_task", "other_lineage"}:
        if case == "other_operation":
            terminal = terminal.model_copy(update={
                "scope": terminal.scope.model_copy(update={"operation_id": "unrelated"}),
            })
        if case == "other_task":
            terminal = terminal.model_copy(update={
                "scope": terminal.scope.model_copy(update={"task_id": run_id + ":other"}),
            })
        if case == "other_lineage":
            terminal = terminal.model_copy(update={"node_reservation_id": str(uuid4())})
        await store.append(terminal)
    fresh = SQLAlchemyApplicationRepository(sessions)
    before = await fresh.get_run_fresh(run_id)
    entries = []
    original = fresh.enter_node_execution

    async def entered(admission):
        entries.append(admission)
        return await original(admission)

    monkeypatch.setattr(fresh, "enter_node_execution", entered)
    fresh_service, _, _, clients = await configured(
        tmp_path, repository=fresh, store=RecoveryEvidenceStore(sessions),
        sessions=sessions, persist=False,
    )
    denied = case in {"terminal", "fresh_startup", "succeeded", "budget"}
    if denied:
        with pytest.raises(BindingDenied):
            if case == "fresh_startup":
                await fresh_service.execute_run(run_id)
            else:
                owner = await fresh.claim_execution(run_id)
                req = IntegratedTaskExecutor(service, before).admission_requirements(target)
                await fresh.reserve_node(owner, target, req)
        after = await fresh.get_run_fresh(run_id)
        assert after.node_binding == before.node_binding
        assert not entries
        assert all(client.calls == 0 for client in clients.values())
    else:
        owner = await fresh.claim_execution(run_id)
        req = IntegratedTaskExecutor(service, before).admission_requirements(target)
        await fresh.reserve_node(owner, target, req)
        after = await fresh.get_run_fresh(run_id)
        assert after.node_binding.attempts[target.task_id].generation == 2
    if case in {"terminal", "fresh_startup"}:
        assert terminal in await store.records(run_id, target.task_id)
        assert after.node_binding.attempts[target.task_id].status == "FAILED"
        assert after.node_binding.lifecycle == "RECOVERY_PENDING"


async def wait_for_blocked_writer(sessions):
    async with asyncio.timeout(5):
        while True:
            async with sessions() as session:
                blocked = await session.scalar(text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname=current_database() "
                    "AND cardinality(pg_blocking_pids(pid)) > 0"
                ))
            if blocked:
                return
            await asyncio.sleep(0.01)


async def test_evidence_append_cannot_cross_reservation(database, tmp_path, monkeypatch):  # noqa: F811
    _, sessions = database
    service, pending, target, store, terminal = await pending_case(tmp_path, sessions)
    fresh = SQLAlchemyApplicationRepository(sessions)
    owner = await fresh.claim_execution(pending.run.run_id)
    req = IntegratedTaskExecutor(service, pending).admission_requirements(target)
    checked, release = asyncio.Event(), asyncio.Event()
    original = fresh._validate_current_recovery_evidence

    async def paused(prior):
        await original(prior)
        checked.set()
        await release.wait()

    monkeypatch.setattr(fresh, "_validate_current_recovery_evidence", paused)
    reservation = asyncio.create_task(fresh.reserve_node(owner, target, req))
    await asyncio.wait_for(checked.wait(), 5)
    append = asyncio.create_task(store.append(terminal))
    try:
        await wait_for_blocked_writer(sessions)
        assert not append.done()
        assert terminal not in await store.records(pending.run.run_id, target.task_id)
    finally:
        release.set()
    await asyncio.wait_for(reservation, 5)
    await asyncio.wait_for(append, 5)
    assert terminal in await store.records(pending.run.run_id, target.task_id)


async def test_evidence_committed_before_reserve_is_denied(database, tmp_path):  # noqa: F811
    _, sessions = database
    service, pending, target, store, terminal = await pending_case(tmp_path, sessions)
    fresh = SQLAlchemyApplicationRepository(sessions)
    owner = await fresh.claim_execution(pending.run.run_id)
    req = IntegratedTaskExecutor(service, pending).admission_requirements(target)
    # Evidence arrives after claim, so reserve must independently re-read it.
    await store.append(terminal)
    before = await fresh.get_run_fresh(pending.run.run_id)
    with pytest.raises(BindingDenied, match="RECOVERY_EVIDENCE_MISMATCH"):
        await fresh.reserve_node(owner, target, req)
    after = await fresh.get_run_fresh(pending.run.run_id)
    assert after.node_binding == before.node_binding
    assert after.node_binding.attempts[target.task_id].generation == 1


async def test_uncommitted_terminal_append_fences_reservation(database, tmp_path):  # noqa: F811
    from contextlib import asynccontextmanager

    _, sessions = database
    service, pending, target, store, terminal = await pending_case(tmp_path, sessions)
    fresh = SQLAlchemyApplicationRepository(sessions)
    owner = await fresh.claim_execution(pending.run.run_id)
    req = IntegratedTaskExecutor(service, pending).admission_requirements(target)
    published, release = asyncio.Event(), asyncio.Event()

    class HeldSession:
        def __init__(self, session):
            self.session = session

        def __getattr__(self, name):
            return getattr(self.session, name)

        @asynccontextmanager
        async def begin(self):
            async with self.session.begin():
                yield
                await self.session.flush()
                published.set()
                await release.wait()

    @asynccontextmanager
    async def held_sessions():
        async with sessions() as session:
            yield HeldSession(session)

    # Pause the real append after INSERT and before COMMIT, retaining its row lock.
    store.sessions = held_sessions
    append = asyncio.create_task(store.append(terminal))
    await asyncio.wait_for(published.wait(), 5)
    reservation = asyncio.create_task(fresh.reserve_node(owner, target, req))
    try:
        await wait_for_blocked_writer(sessions)
        assert not reservation.done()
    finally:
        release.set()
    await asyncio.wait_for(append, 5)
    with pytest.raises(BindingDenied, match="RECOVERY_EVIDENCE_MISMATCH"):
        await asyncio.wait_for(reservation, 5)
    after = await fresh.get_run_fresh(pending.run.run_id)
    assert after.node_binding.attempts[target.task_id].generation == 1
    assert after.node_binding.attempts[target.task_id].status == "FAILED"
    assert not after.node_binding.attempt_history
