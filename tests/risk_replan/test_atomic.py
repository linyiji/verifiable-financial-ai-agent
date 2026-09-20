"""Failure injection at production SQL transaction write boundaries, no DB bypass."""

import asyncio
from contextlib import contextmanager

import pytest

from src.application.persistence import SQLAlchemyApplicationRepository
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.risk_replan.test_flow import command, fixture
from tests.risk_replan.test_postgresql import database, fresh, pytestmark  # noqa: F401
from tests.risk_replan.test_recovery import resume


class InjectedFailure(RuntimeError):
    pass


@contextmanager
def fail_write(repo, method, after):
    original = getattr(repo, method)

    async def failure(*args, **kwargs):
        if after:
            await original(*args, **kwargs)
        raise InjectedFailure(method)

    setattr(repo, method, failure)
    try:
        yield
    finally:
        setattr(repo, method, original)


async def snapshot(sessions, run_id):
    value = await fresh(sessions, run_id)
    value.pop("pid")
    return value


@pytest.mark.parametrize("action", ["DECLINE", "REOPEN", "APPROVE", "CANCEL", "APPLY"])
@pytest.mark.parametrize(
    "method,after",
    [
        ("_persist_replan_events", False),
        ("_persist_replan_events", True),
        ("_persist_children", False),
        ("_persist_children", True),
    ],
)
async def test_atomic_decision_and_graph(database, tmp_path, action, method, after):  # noqa: F811
    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, calls, transport = await fixture(
        tmp_path, repository=repo, store=RecoveryEvidenceStore(sessions), sessions=sessions
    )
    run_id = value.run.run_id
    with transport:
        value = await service.execute_run(run_id)
    if action in {"REOPEN", "APPLY"}:
        await repo.decide_replan(
            run_id,
            command(value, "DECLINE" if action == "REOPEN" else "APPROVE"),
            actor="LOCAL_SINGLE_USER",
            key="prepare",
        )
        value = await repo.get_run_fresh(run_id)
    body = None if action == "APPLY" else command(value, action)

    async def execute():
        if body is None:
            return await repo.apply_replan(run_id)
        return await repo.decide_replan(run_id, body, actor="LOCAL_SINGLE_USER", key="fault-replay")

    before = await snapshot(sessions, run_id)
    with fail_write(repo, method, after), pytest.raises(InjectedFailure):
        await execute()
    assert await snapshot(sessions, run_id) == before
    first = await execute()
    committed = await snapshot(sessions, run_id)
    second = await execute()
    replay = await snapshot(sessions, run_id)
    assert committed["events"] == replay["events"]
    assert committed["root"]["replan"]["audit"] == replay["root"]["replan"]["audit"]
    if body is None:
        assert first == second
    else:
        assert first["decision_id"] == second["decision_id"]


@pytest.mark.parametrize("target", ["capture", "pair"])
@pytest.mark.parametrize(
    "method,after",
    [
        ("_persist_replan_events", False),
        ("_persist_replan_events", True),
        ("_persist_children", False),
        ("_persist_children", True),
    ],
)
async def test_atomic_capture_and_paired_completion(database, tmp_path, target, method, after):  # noqa: F811
    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    gate = asyncio.Event()
    if target == "pair":
        gate.set()
    service, value, calls, transport = await fixture(
        tmp_path,
        repository=repo,
        store=RecoveryEvidenceStore(sessions),
        sessions=sessions,
        valuation_gate=gate,
    )
    run_id = value.run.run_id
    if target == "pair":
        with transport:
            value = await service.execute_run(run_id)
        await repo.decide_replan(
            run_id, command(value, "APPROVE"), actor="LOCAL_SINGLE_USER", key="A"
        )
        await repo.apply_replan(run_id)
    original = repo.commit_node_result
    tested = []

    async def commit(*args, **kwargs):
        task_id = args[1].task_id if len(args) > 1 else kwargs["task"].task_id
        wanted = run_id + (":risk" if target == "capture" else ":risk-follow-up")
        if task_id != wanted or tested:
            return await original(*args, **kwargs)
        tested.append(task_id)
        before = await snapshot(sessions, run_id)
        with fail_write(repo, method, after), pytest.raises(InjectedFailure):
            await original(*args, **kwargs)
        assert await snapshot(sessions, run_id) == before
        result = await original(*args, **kwargs)
        committed = await snapshot(sessions, run_id)
        replay = await original(*args, **kwargs)
        assert replay == result
        assert (await snapshot(sessions, run_id))["events"] == committed["events"]
        if target == "pair":
            completed = [
                e
                for e in committed["events"]
                if e["type"] == "task.completed" and e["task_id"] in {run_id + ":risk", wanted}
            ]
            assert len(completed) == 2
            assert committed["root"]["replan"]["finalization"] is not None
        else:
            assert run_id + ":risk" not in committed["root"]["current_results"]
        gate.set()
        return result

    repo.commit_node_result = commit
    with transport:
        if target == "capture":
            await service.execute_run(run_id)
        else:
            await resume(service, run_id)
    assert tested
