"""RR1: production owner disposition, full durable equality and exited SQL workers."""

import asyncio
import gzip
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import event, text

from src.application import risk_replan
from src.application.persistence import SQLAlchemyApplicationRepository
from src.domain.node_binding import BindingDenied
from tests.risk_replan.backend_fixture import durable_snapshot
from tests.risk_replan.test_atomic import InjectedFailure, fail_write
from tests.risk_replan.test_bounded_repair import blocked_by, pending_sql
from tests.risk_replan.test_flow import command
from tests.risk_replan.test_postgresql import database, pytestmark  # noqa: F401


async def complete_snapshot(sessions, rid):
    rows = await durable_snapshot(sessions, rid)
    async with sessions() as session:
        rows["runtime_event_counters_explicit"] = [
            dict(row)
            for row in (
                await session.execute(
                    text("SELECT * FROM runtime_event_counters WHERE run_id=:rid ORDER BY run_id"),
                    {"rid": rid},
                )
            ).mappings()
        ]
    value = await SQLAlchemyApplicationRepository(sessions).get_run_fresh(rid)
    result = {
        "rows": rows,
        "payload": SQLAlchemyApplicationRepository._payload(value),
        "run": value.run.model_dump(mode="json"),
    }
    if output := os.environ.get("RR1_PROOF_DIR"):
        root = Path(output)
        await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
        encoded = json.dumps(result, sort_keys=True, default=str).encode()
        await asyncio.to_thread(
            (root / (state_hash(result) + ".json.gz")).write_bytes, gzip.compress(encoded, mtime=0)
        )
    return result


def state_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


@contextmanager
def writes(engine):
    found = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "MERGE"}:
            found.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        yield found
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)


async def setup(sessions, tmp_path, action):
    repo, value, _ = await pending_sql(sessions, tmp_path)
    rid = value.run.run_id
    if action in {"REOPEN", "APPLY", "DENIAL"}:
        await repo.decide_replan(
            rid,
            command(value, {"REOPEN": "DECLINE", "APPLY": "APPROVE", "DENIAL": "CANCEL"}[action]),
            actor="LOCAL_SINGLE_USER",
            key="prepare",
        )
        value = await repo.get_run_fresh(rid)
    body = None if action == "APPLY" else command(value, "REOPEN" if action == "DENIAL" else action)
    return repo, rid, body


async def execute(repo, rid, body, key="rr1"):
    if body is None:
        result = await repo.apply_replan(rid)
        return result.model_dump(mode="json")
    return await repo.decide_replan(rid, body, actor="LOCAL_SINGLE_USER", key=key)


def outcome(result):
    return {k: v for k, v in result.items() if k != "historical_replay"}


WORKER = r"""
import asyncio,json,os,sys
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from tests.risk_replan.test_replay_revision import execute,complete_snapshot,state_hash
from src.application.persistence import SQLAlchemyApplicationRepository
async def main():
    url,schema,rid,body,key=sys.argv[1:]
    engine=create_async_engine(url,connect_args={"server_settings":{"search_path":schema}})
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    statements=[]
    from src.application.risk_replan import _MutationResult
    dispositions=[]
    consume=_MutationResult.consume
    def trace(self,result):
        dispositions.append(self.disposition.value)
        return consume(self,result)
    _MutationResult.consume=trace
    def capture(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().split()[0].upper() in {"INSERT","UPDATE","DELETE","MERGE"}:
            statements.append(statement)
    event.listen(engine.sync_engine,"before_cursor_execute",capture)
    print("READY",flush=True)
    await asyncio.to_thread(sys.stdin.readline)
    result=await execute(SQLAlchemyApplicationRepository(sessions),rid,json.loads(body),key)
    snapshot=await complete_snapshot(sessions,rid)
    print(json.dumps({"pid":os.getpid(),"result":result,"writes":len(statements),"dispositions":dispositions,
                      "hash":state_hash(snapshot)}),flush=True)
    await engine.dispose()
asyncio.run(main())
"""


async def worker(sessions, rid, body, key="rr1"):
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        WORKER,
        os.environ["TEST_POSTGRESQL_URL"],
        schema,
        rid,
        json.dumps(body),
        key,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert (await process.stdout.readline()).decode().strip() == "READY"
    return process


async def finish(process):
    out, err = await process.communicate(b"go\n")
    assert process.returncode == 0, err.decode()
    return json.loads(out)


@pytest.mark.parametrize("action", ["DECLINE", "APPROVE", "REOPEN", "CANCEL", "APPLY", "DENIAL"])
async def test_er01_10_15_16_full_replay(database, tmp_path, monkeypatch, action):  # noqa: F811
    engine, sessions = database
    repo, rid, body = await setup(sessions, tmp_path, action)
    dispositions = []
    consume = risk_replan._MutationResult.consume

    def trace(self, result):
        dispositions.append(self.disposition.value)
        return consume(self, result)

    monkeypatch.setattr(risk_replan._MutationResult, "consume", trace)
    before = await complete_snapshot(sessions, rid)
    # First command commits in an OS worker which exits before replay starts.
    first = await finish(await worker(sessions, rid, body))
    committed = await complete_snapshot(sessions, rid)
    root = committed["payload"]["node_binding"]
    assert root["binding_revision"] == before["payload"]["node_binding"]["binding_revision"] + 1
    assert first["writes"] > 0
    assert first["dispositions"] == ["MUTATED"]
    with (
        writes(engine) as statements,
        fail_write(repo, "_persist_children", False),
        fail_write(repo, "_persist_replan_events", False),
    ):
        replay = await execute(repo, rid, body)
    assert not statements
    assert dispositions == ["NO_OP_REPLAY"]
    assert outcome(replay) == outcome(first["result"])
    assert await complete_snapshot(sessions, rid) == committed
    exited = await finish(await worker(sessions, rid, body))
    assert exited["pid"] != first["pid"] != os.getpid()
    assert exited["writes"] == 0
    assert exited["dispositions"] == ["NO_OP_REPLAY"]
    assert outcome(exited["result"]) == outcome(first["result"])
    assert exited["hash"] == state_hash(committed)
    assert await complete_snapshot(sessions, rid) == committed
    # Old receipts remain read-only after a later terminal decision.
    if action in {"APPROVE", "DECLINE", "REOPEN"}:
        value = await repo.get_run_fresh(rid)
        await repo.decide_replan(
            rid, command(value, "CANCEL"), actor="LOCAL_SINGLE_USER", key="later"
        )
        terminal = await complete_snapshot(sessions, rid)
        historical = await finish(await worker(sessions, rid, body))
        assert historical["writes"] == 0
        assert outcome(historical["result"]) == outcome(first["result"])
        assert historical["hash"] == state_hash(terminal)
    print(
        json.dumps(
            {
                "action": action,
                "first_delta": 1,
                "replay_delta": 0,
                "replay_writes": 0,
                "state_hash": state_hash(committed),
                "first_pid": first["pid"],
                "replay_pid": exited["pid"],
            }
        )
    )


@pytest.mark.parametrize("action", ["DECLINE", "APPROVE", "REOPEN", "CANCEL", "APPLY", "DENIAL"])
@pytest.mark.parametrize("rollback", [False, True])
async def test_er11_process_duplicates(database, tmp_path, monkeypatch, action, rollback):  # noqa: F811
    _, sessions = database
    repo, rid, body = await setup(sessions, tmp_path, action)
    before = await complete_snapshot(sessions, rid)
    held, release = asyncio.Event(), asyncio.Event()
    holder = []
    original = repo._persist_replan_events

    async def pause(session, *args):
        holder.append(await session.scalar(text("SELECT pg_backend_pid()")))
        held.set()
        await release.wait()
        if rollback:
            raise InjectedFailure("first writer rollback")
        return await original(session, *args)

    monkeypatch.setattr(repo, "_persist_replan_events", pause)
    processes = [await worker(sessions, rid, body) for _ in range(2)]
    first = asyncio.create_task(execute(repo, rid, body))
    followers = []
    try:
        async with asyncio.timeout(30):
            await held.wait()
            followers = [asyncio.create_task(finish(p)) for p in processes]
            await blocked_by(sessions, holder[0])
            release.set()
            if rollback:
                with pytest.raises(InjectedFailure):
                    await first
            else:
                await first
            results = await asyncio.gather(*followers)
    finally:
        release.set()
        for p in processes:
            if p.returncode is None:
                p.kill()
                await p.wait()
        if not first.done():
            first.cancel()
        await asyncio.gather(first, *followers, return_exceptions=True)
    after = await complete_snapshot(sessions, rid)
    assert after["payload"]["node_binding"]["binding_revision"] == (
        before["payload"]["node_binding"]["binding_revision"] + 1
    )
    assert outcome(results[0]["result"]) == outcome(results[1]["result"])
    assert sum(r["writes"] > 0 for r in results) == int(rollback)
    # Already-committed duplicate workers both perform no DML and return equal full state.
    replay = await asyncio.gather(
        *(finish(p) for p in [await worker(sessions, rid, body) for _ in range(2)])
    )
    assert all(r["writes"] == 0 and r["hash"] == state_hash(after) for r in replay)
    assert await complete_snapshot(sessions, rid) == after
    print(
        json.dumps(
            {
                "action": action,
                "rollback": rollback,
                "delta": 1,
                "worker_pids": [r["pid"] for r in results],
                "state_hash": state_hash(after),
            }
        )
    )


async def test_er12_alias_denials_and_fail_closed(database, tmp_path, monkeypatch):  # noqa: F811
    engine, sessions = database
    repo, rid, body = await setup(sessions, tmp_path, "DECLINE")
    await execute(repo, rid, body)
    before = await complete_snapshot(sessions, rid)
    with fail_write(repo, "_persist_children", True), pytest.raises(InjectedFailure):
        await execute(repo, rid, body, "alias")
    assert await complete_snapshot(sessions, rid) == before
    await execute(repo, rid, body, "alias")
    alias = await complete_snapshot(sessions, rid)
    assert (
        alias["payload"]["node_binding"]["binding_revision"]
        == before["payload"]["node_binding"]["binding_revision"] + 1
    )
    assert alias["rows"]["runtime_events"] == before["rows"]["runtime_events"]
    with writes(engine) as statements:
        await execute(repo, rid, body, "alias")
        for altered in (
            {**body, "expected_decision_revision": 100},
            {**body, "expected_proposal_digest": "changed"},
            {**body, "expected_graph": {}},
            {**body, "reject_replan": False},
            {**body, "run_id": "OTHER"},
            {**body, "object_id": "OTHER"},
            {**body, "proposal_id": "OTHER"},
        ):
            with pytest.raises(BindingDenied):
                await execute(repo, rid, altered)
        with pytest.raises(BindingDenied):
            await repo.decide_replan(rid, body, actor="OTHER", key="rr1")
    assert not statements
    assert await complete_snapshot(sessions, rid) == alias
    # A helper returning success without owner classification must abort its writes.
    original = risk_replan.decide

    def unclassified(aggregate, body, *, actor, key, _mutation):
        return original(aggregate, body, actor=actor, key=key)

    monkeypatch.setattr(risk_replan, "decide", unclassified)
    with pytest.raises(RuntimeError, match="REPLAN_MUTATION_DISPOSITION_REQUIRED"):
        await execute(repo, rid, body, "unclassified-alias")
    assert await complete_snapshot(sessions, rid) == alias


@pytest.mark.parametrize("reserved", [False, True])
async def test_pending_apply_preserves_normal_exit(database, tmp_path, monkeypatch, reserved):  # noqa: F811
    from src.infrastructure.database.recovery import RecoveryEvidenceStore
    from tests.risk_replan.test_flow import fixture
    from tests.wp02.confirmation_fixture import confirm_template

    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    gate = asyncio.Event()
    service, draft, _, transport = await fixture(
        tmp_path,
        repository=repo,
        store=RecoveryEvidenceStore(sessions),
        sessions=sessions,
        valuation_gate=gate,
        persist=False,
    )
    # Template tasks are frozen by real Confirm before any execution authority exists.
    if reserved:
        for graph in (draft.runtime.planned_graph, draft.runtime.actual_graph):
            original = next(t for t in graph.tasks if t.task_type == "valuation_analysis")
            graph.tasks.append(
                original.model_copy(update={"task_id": draft.run.run_id + ":parallel"})
            )
    value = await confirm_template(service, draft, symbol="PENDING")
    rid = value.run.run_id
    captured, dispatched, reservation = asyncio.Event(), asyncio.Event(), asyncio.Event()
    commit, dispatch = repo.commit_node_result, repo.dispatch_node

    async def capture(*args, **kwargs):
        result = await commit(*args, **kwargs)
        task = args[1] if len(args) > 1 else kwargs["task"]
        if task.task_type == "risk_analysis":
            captured.set()
        return result

    async def hold(admission):
        if admission.task_id.endswith(":parallel"):
            reservation.set()
            await gate.wait()
        result = await dispatch(admission)
        if admission.task_id.endswith(":valuation"):
            dispatched.set()
        return result

    monkeypatch.setattr(repo, "commit_node_result", capture)
    monkeypatch.setattr(repo, "dispatch_node", hold)
    with transport:
        running = asyncio.create_task(service.execute_run(rid))
        try:
            async with asyncio.timeout(30):
                await captured.wait()
                await dispatched.wait()
                if reserved:
                    await reservation.wait()
                current = await repo.get_run_fresh(rid)
                await repo.decide_replan(
                    rid, command(current, "APPROVE"), actor="LOCAL_SINGLE_USER", key="pending"
                )
                before = await repo.get_run_fresh(rid)
                assert before.node_binding.attempts[rid + ":valuation"].status == "DISPATCHED"
                if reserved:
                    assert before.node_binding.attempts[rid + ":parallel"].status == "RESERVED"
                assert await repo.apply_replan(rid) is None
                after = await repo.get_run_fresh(rid)
                assert (
                    after.node_binding.binding_revision == before.node_binding.binding_revision + 1
                )
                assert after.node_binding.replan["transition"] is None
                assert after.node_binding.frozen_graph == before.node_binding.frozen_graph
                if reserved:
                    assert rid + ":parallel" not in after.node_binding.attempts
                    admission = before.node_binding.attempts[rid + ":parallel"].admission
                    assert admission.attempt_reservation_id in after.node_binding.attempt_history
                print(json.dumps({"pending": True, "reserved_retired": reserved, "delta": 1}))
        finally:
            running.cancel()
            gate.set()
            await asyncio.gather(running, return_exceptions=True)


async def test_cross_run_disposition_isolation(database, tmp_path):  # noqa: F811
    _, sessions = database
    repo, first_id, first_body = await setup(sessions, tmp_path / "first", "DECLINE")
    from pydantic import BaseModel

    from src.infrastructure.database.recovery import RecoveryEvidenceStore
    from tests.risk_replan.test_flow import fixture
    from tests.wp02.confirmation_fixture import confirm_template

    service, template, _, transport = await fixture(
        tmp_path / "second",
        repository=repo,
        store=RecoveryEvidenceStore(sessions),
        sessions=sessions,
        persist=False,
    )
    # Give the second planner template distinct identities before lawful Confirm.
    assert template.confirmed_risk_semantic_binding is None
    for name, value in list(vars(template).items()):
        if isinstance(value, BaseModel):
            setattr(
                template,
                name,
                type(value).model_validate_json(
                    value.model_dump_json().replace("WP02", "RR1-OTHER")
                ),
            )
    for name in ("planned_graph", "actual_graph"):
        graph = getattr(template.runtime, name)
        setattr(
            template.runtime,
            name,
            type(graph).model_validate_json(graph.model_dump_json().replace("WP02", "RR1-OTHER")),
        )
    add = service.evidence_repository.add

    async def distinct_source_id(record):
        record.evidence_id = "OTHER-" + record.evidence_id
        return await add(record)

    service.evidence_repository.add = distinct_source_id
    second = await confirm_template(service, template)
    with transport:
        second = await service.execute_run(second.run.run_id)
    second_id, second_body = second.run.run_id, command(second, "APPROVE")
    await execute(repo, first_id, first_body)
    before = await complete_snapshot(sessions, first_id)
    second_before = await complete_snapshot(sessions, second_id)
    waiting = None
    try:
        async with sessions() as session, session.begin():
            await session.execute(
                text("SELECT run_id FROM research_runs WHERE run_id=:rid FOR UPDATE"),
                {"rid": first_id},
            )
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            waiting = asyncio.create_task(execute(repo, first_id, first_body))
            await blocked_by(sessions, pid)
            async with asyncio.timeout(15):
                await execute(repo, second_id, second_body)
                await execute(repo, second_id, second_body)
        await waiting
    finally:
        if waiting is not None and not waiting.done():
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)
    assert await complete_snapshot(sessions, first_id) == before
    second = await complete_snapshot(sessions, second_id)
    assert second["payload"]["node_binding"]["binding_revision"] == (
        second_before["payload"]["node_binding"]["binding_revision"] + 1
    )


@pytest.mark.parametrize("boundary", ["_persist_success_events", "_persist_children"])
async def test_er17_success_owner_rollback_revision(database, tmp_path, monkeypatch, boundary):  # noqa: F811
    from src.adapters.finrobot.professional_reporting import (
        ControlledArtifactStore,
        ProfessionalReportPublisher,
    )
    from src.application.persistence import SessionFactoryEvidenceRepository
    from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
    from src.infrastructure.database.recovery import RecoveryEvidenceStore
    from tests.report_metrics.runtime_fixture import report_fixture

    engine, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, initial, _, backend, _ = await report_fixture(
        tmp_path,
        repository=repo,
        evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions),
        event_store=PostgresRuntimeEventStore(sessions),
        sessions=sessions,
    )
    service.report_publisher = ProfessionalReportPublisher(
        ControlledArtifactStore(tmp_path / "reports")
    )
    original = repo.finalize_success
    observed = []

    async def verify(owner, proposed, **kwargs):
        before = await complete_snapshot(sessions, owner.run_id)
        with fail_write(repo, boundary, True), pytest.raises(BindingDenied, match="RESULT_UNKNOWN"):
            await original(owner, proposed, **kwargs)
        assert await complete_snapshot(sessions, owner.run_id) == before
        first = await original(owner, proposed, **kwargs)
        committed = await complete_snapshot(sessions, owner.run_id)
        assert committed["payload"]["node_binding"]["binding_revision"] == (
            before["payload"]["node_binding"]["binding_revision"] + 1
        )
        with writes(engine) as statements:
            replay = await original(owner, proposed, **kwargs)
        assert repo._payload(replay[0]) == repo._payload(first[0])
        assert replay[1:] == first[1:]
        assert not statements
        assert await complete_snapshot(sessions, owner.run_id) == committed
        observed.append(boundary)
        return first

    monkeypatch.setattr(repo, "finalize_success", verify)
    result = await service.execute_run(initial.run.run_id)
    assert result.run.status.value == "RELEASED"
    assert observed == [boundary]
    await backend.close()
