"""Bounded I-01/F-53 SQL proofs with legal barriers and exited-process readers."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.persistence import SQLAlchemyApplicationRepository
from src.domain.node_binding import BindingDenied
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType, normalize_runtime_event_v1
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from src.runtime.events import EventReconciliationRequired, EventSequenceError, RuntimeEventCursor
from src.runtime.sse import preflight_runtime_event_stream, runtime_event_stream
from tests.risk_replan.test_atomic import InjectedFailure, fail_write, snapshot
from tests.risk_replan.test_flow import command, fixture
from tests.risk_replan.test_postgresql import database, fresh, pytestmark  # noqa: F401
from tests.risk_replan.test_recovery import resume


async def pending_sql(sessions, tmp_path):
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, calls, transport = await fixture(
        tmp_path, repository=repo, store=RecoveryEvidenceStore(sessions), sessions=sessions
    )
    with transport:
        value = await service.execute_run(value.run.run_id)
    return repo, value, service


def business(value):
    """Exclude only permitted audit bookkeeping, never business/control identity."""
    assert value.runtime.binding_ref == value.node_binding.reference()
    payload = SQLAlchemyApplicationRepository._payload(value)
    root = payload["node_binding"]
    root.pop("binding_revision")
    root["replan"].pop("receipts")
    root["replan"].pop("audit")
    payload["runtime"]["binding_ref"].pop("binding_revision")
    payload["runtime"]["binding_ref"].pop("binding_hash")
    return payload


async def blocked_by(sessions, holder):
    # Bounded read-only observation, not retries of a product operation.
    for _ in range(200):
        async with sessions() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT pid, pg_blocking_pids(pid) FROM pg_stat_activity "
                        "WHERE :holder = ANY(pg_blocking_pids(pid))"
                    ),
                    {"holder": holder},
                )
            ).all()
        if rows:
            print("observed wait", holder, [tuple(row) for row in rows])
            return
    raise AssertionError("expected legal same-Run lock wait not observed")


@pytest.mark.parametrize("first", ["root", "event"])
@pytest.mark.parametrize("writer", ["emit", "append", "cache"])
async def test_legal_lock_orders(database, tmp_path, monkeypatch, first, writer):  # noqa: F811
    _, sessions = database
    repo, value, _ = await pending_sql(sessions, tmp_path)
    rid = value.run.run_id
    original_lock = PostgresRuntimeEventStore._lock_run_event_writes
    original_persist = repo._persist_replan_events
    held, release = asyncio.Event(), asyncio.Event()
    holder = []

    async def lock(session, run_id):
        await original_lock(session, run_id)
        if asyncio.current_task().get_name() == "event-writer" and first == "event":
            holder.append(await session.scalar(text("SELECT pg_backend_pid()")))
            held.set()
            await release.wait()

    async def persist(session, *args):
        if first == "root":
            holder.append(await session.scalar(text("SELECT pg_backend_pid()")))
            held.set()
            await release.wait()
        return await original_persist(session, *args)

    monkeypatch.setattr(PostgresRuntimeEventStore, "_lock_run_event_writes", staticmethod(lock))
    monkeypatch.setattr(repo, "_persist_replan_events", persist)
    store = PostgresRuntimeEventStore(sessions)
    initial = await store.replay(rid)

    # An explicitly sequenced append is legal when its expected sequence is
    # current. The root-first case samples only after that transaction commits.
    async def event_writer():
        if writer == "emit":
            return await store.emit(
                run_id=rid,
                event_type=RuntimeEventType.RUN_STATUS_CHANGED,
                payload={"status": "WAITING_REPLAN"},
            )
        if writer == "cache":
            return await SQLAlchemyApplicationRepository(sessions).save_runtime_events(initial)

    async def root_writer():
        return await repo.decide_replan(
            rid, command(value, "DECLINE"), actor="LOCAL_SINGLE_USER", key="ordered-decline"
        )

    # For append/root-first, hold at the actual append helper and compute the
    # sequence from the known two-event Decline transaction (no allocator change).
    if writer == "append":

        async def event_writer():
            event = RuntimeEvent(
                event_id="EVT-append-order",
                run_id=rid,
                type=RuntimeEventType.RUN_STATUS_CHANGED,
                sequence=initial[-1].sequence + (3 if first == "root" else 1),
                payload={"status": "WAITING_REPLAN"},
            )
            await store.append(event)

    functions = {"root": root_writer, "event": event_writer}
    tasks = []
    try:
        async with asyncio.timeout(15):
            tasks.append(asyncio.create_task(functions[first](), name=first + "-writer"))
            await held.wait()
            second = "event" if first == "root" else "root"
            tasks.append(asyncio.create_task(functions[second](), name=second + "-writer"))
            await blocked_by(sessions, holder[0])
            release.set()
            await asyncio.gather(*tasks)
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    read = await fresh(sessions, rid)
    assert read["projection"]["legal_actions"] == ["CANCEL", "REOPEN"]
    assert len([e for e in read["events"] if e["type"] == "replan.rejected"]) == 1
    assert [e["sequence"] for e in read["events"]] == list(range(1, len(read["events"]) + 1))
    assert read["root"]["current_results"] == value.node_binding.current_results


@pytest.mark.parametrize("first", ["CANCEL", "REOPEN"])
async def test_cancel_reopen_legal_orders(database, tmp_path, monkeypatch, first):  # noqa: F811
    _, sessions = database
    repo, value, _ = await pending_sql(sessions, tmp_path)
    rid = value.run.run_id
    await repo.decide_replan(rid, command(value, "DECLINE"), actor="LOCAL_SINGLE_USER", key="D")
    value = await repo.get_run_fresh(rid)
    before = value.node_binding.frozen_graph
    commands = {action: command(value, action) for action in ("CANCEL", "REOPEN")}
    held, release = asyncio.Event(), asyncio.Event()
    persist = repo._persist_replan_events
    holder = []

    async def pause(session, *args):
        holder.append(await session.scalar(text("SELECT pg_backend_pid()")))
        held.set()
        await release.wait()
        return await persist(session, *args)

    monkeypatch.setattr(repo, "_persist_replan_events", pause)
    first_task = asyncio.create_task(
        repo.decide_replan(rid, commands[first], actor="LOCAL_SINGLE_USER", key=first)
    )
    second_task = None
    try:
        async with asyncio.timeout(15):
            await held.wait()
            second = "REOPEN" if first == "CANCEL" else "CANCEL"
            second_task = asyncio.create_task(
                SQLAlchemyApplicationRepository(sessions).decide_replan(
                    rid, commands[second], actor="LOCAL_SINGLE_USER", key=second
                )
            )
            await blocked_by(sessions, holder[0])
            release.set()
            outcomes = await asyncio.gather(first_task, second_task)
    finally:
        release.set()
    assert [r["outcome"] for r in outcomes] == ["COMMITTED", "REJECTED"]
    if first == "REOPEN":
        current = await repo.get_run_fresh(rid)
        await SQLAlchemyApplicationRepository(sessions).decide_replan(
            rid, command(current, "CANCEL"), actor="LOCAL_SINGLE_USER", key="fresh-cancel"
        )
        current = await repo.get_run_fresh(rid)
        assert (
            await SQLAlchemyApplicationRepository(sessions).decide_replan(
                rid, command(current, "REOPEN"), actor="LOCAL_SINGLE_USER", key="terminal"
            )
        )["code"] == "REPLAN_TERMINAL_RUN"
    final = await fresh(sessions, rid)
    assert final["projection"]["status"] == "CANCELLED"
    assert final["projection"]["legal_actions"] == []
    assert final["root"]["frozen_graph"] == before.model_dump(mode="json")
    assert final["root"]["current_results"] == value.node_binding.current_results


@pytest.mark.parametrize("after", [False, True])
async def test_denial_transaction_rollback(database, tmp_path, after):  # noqa: F811
    _, sessions = database
    repo, value, _ = await pending_sql(sessions, tmp_path)
    rid = value.run.run_id
    await repo.decide_replan(rid, command(value, "CANCEL"), actor="LOCAL_SINGLE_USER", key="C")
    value = await repo.get_run_fresh(rid)
    body = command(value, "REOPEN")
    before = await snapshot(sessions, rid)
    with fail_write(repo, "_persist_replan_events", after), pytest.raises(InjectedFailure):
        await repo.decide_replan(rid, body, actor="LOCAL_SINGLE_USER", key="denial")
    assert await snapshot(sessions, rid) == before
    receipt = await repo.decide_replan(rid, body, actor="LOCAL_SINGLE_USER", key="denial")
    assert receipt["outcome"] == "REJECTED"
    committed = await snapshot(sessions, rid)
    with fail_write(repo, "_persist_children", True), pytest.raises(InjectedFailure):
        await repo.decide_replan(rid, body, actor="LOCAL_SINGLE_USER", key="alias")
    assert await snapshot(sessions, rid) == committed
    assert business(await repo.get_run_fresh(rid)) == business(value)


async def worker():
    mode, url, schema, directory, *ids = sys.argv[1:]
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyApplicationRepository(sessions)
    if mode in {"denial", "carry"}:
        failure = {("valuation_analysis", "gpt-5.6-sol"): ["timeout"]} if mode == "carry" else None
        service, value, calls, transport = await fixture(
            Path(directory),
            repository=repo,
            store=RecoveryEvidenceStore(sessions),
            sessions=sessions,
            failure_plan=failure,
        )
        rid = value.run.run_id
        with transport:
            value = await service.execute_run(rid)
        if mode == "carry":
            before = value.node_binding.model_dump(mode="json")
            await repo.decide_replan(
                rid, command(value, "APPROVE"), actor="LOCAL_SINGLE_USER", key="A"
            )
            await repo.apply_replan(rid)
            print(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "rid": rid,
                        "before": before,
                        "root": (await repo.get_run_fresh(rid)).node_binding.model_dump(
                            mode="json"
                        ),
                        "calls": calls,
                    }
                )
            )
        else:
            await repo.decide_replan(
                rid, command(value, "CANCEL"), actor="LOCAL_SINGLE_USER", key="C"
            )
            value = await repo.get_run_fresh(rid)
            body = command(value, "REOPEN")
            receipt = await repo.decide_replan(rid, body, actor="LOCAL_SINGLE_USER", key="deny")
            # A caller error after repository return cannot undo its committed audit.
            try:
                raise InjectedFailure("caller after commit")
            except InjectedFailure:
                pass
            assert business(await repo.get_run_fresh(rid)) == business(value)
            print(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "rid": rid,
                        "receipt": receipt,
                        "body": body,
                        "business": business(value),
                    }
                )
            )
    else:
        rid = ids[0]
        before = await repo.get_run_fresh(rid)
        service, _, calls, transport = await fixture(
            Path(directory),
            repository=repo,
            store=RecoveryEvidenceStore(sessions),
            sessions=sessions,
            persist=False,
        )
        assert rid in await repo.replan_work_run_ids()
        with transport:
            await resume(service, rid)
        after = await repo.get_run_fresh(rid)
        rows = await service.recovery_evidence_store.records(rid, rid + ":valuation")
        print(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "rid": rid,
                    "calls": calls,
                    "started_at_preserved": before.run.started_at == after.run.started_at,
                    "root": after.node_binding.model_dump(mode="json"),
                    "records": [row.model_dump(mode="json") for row in rows],
                }
            )
        )
    await engine.dispose()


async def exited_worker(sessions, tmp_path, mode, *ids):
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import asyncio; from tests.risk_replan.test_bounded_repair import worker; "
        "asyncio.run(worker())",
        mode,
        os.environ["TEST_POSTGRESQL_URL"],
        schema,
        str(tmp_path),
        *ids,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await process.communicate()
    assert process.returncode == 0, err.decode()
    return json.loads(out)


async def test_exited_carry_worker_completes(database, tmp_path):  # noqa: F811
    _, sessions = database
    writer = await exited_worker(sessions, tmp_path, "carry")
    rid = writer["rid"]
    completed = await exited_worker(sessions, tmp_path, "resume", rid)
    read = await fresh(sessions, rid)
    assert len({writer["pid"], completed["pid"], read["pid"], os.getpid()}) == 4
    assert completed["started_at_preserved"]
    assert completed["root"] == read["root"]
    root = read["root"]
    prior = writer["before"]["attempts"][rid + ":valuation"]
    assert root["attempt_history"][prior["admission"]["attempt_reservation_id"]] == prior
    assert root["attempts"][rid + ":valuation"]["status"] == "COMMITTED"
    assert root["attempts"][rid + ":valuation"]["generation"] == 2
    assert root["frozen_graph"] == writer["root"]["frozen_graph"]
    assert root["execution_snapshot"] == writer["root"]["execution_snapshot"]
    for task, result in writer["before"]["current_results"].items():
        assert root["current_results"][task] == result
    assert root["replan"]["finalization"]
    assert all(
        rid + suffix in root["current_results"]
        for suffix in (":risk", ":risk-follow-up", ":synthesis")
    )
    assert [
        model
        for task, model in writer["calls"] + completed["calls"]
        if task == "valuation_analysis"
    ] == ["gpt-5.6-sol", "gpt-5.6-terra"]
    assert len([r for r in completed["records"] if r["kind"] == "ATTEMPT_STARTED"]) == 2
    events = read["events"]
    paired = [
        e["sequence"]
        for e in events
        if e["type"] == "task.completed"
        and e["task_id"] in {rid + ":risk", rid + ":risk-follow-up"}
    ]
    synthesis = [
        e["sequence"]
        for e in events
        if e["type"] == "task.completed" and e["task_id"] == rid + ":synthesis"
    ]
    assert len(paired) == 2 and len(synthesis) == 1 and max(paired) < synthesis[0]
    destination = os.environ.get("RISK_REPLAN_PROOF_RECEIPTS")
    if destination:
        Path(destination).with_name("bounded-carry-processes.json").write_text(
            json.dumps({"writer": writer, "completed": completed, "reader": read}, indent=2)
        )


async def test_exited_denial_idempotency_and_consumers(database, tmp_path):  # noqa: F811
    _, sessions = database
    writer = await exited_worker(sessions, tmp_path, "denial")
    rid, body = writer["rid"], writer["body"]
    read = await fresh(sessions, rid)
    assert writer["pid"] != read["pid"] != os.getpid()
    repo = SQLAlchemyApplicationRepository(sessions)
    before = await repo.get_run_fresh(rid)
    assert business(before) == writer["business"]
    for key in ("deny", "deny", "equivalent-new-key"):
        receipt = await repo.decide_replan(rid, body, actor="LOCAL_SINGLE_USER", key=key)
        assert receipt["historical_replay"]
        assert {k: v for k, v in receipt.items() if k != "historical_replay"} == {
            k: v for k, v in writer["receipt"].items() if k != "historical_replay"
        }
    changed = {**body, "expected_decision_revision": body["expected_decision_revision"] + 1}
    with pytest.raises(BindingDenied, match="IDEMPOTENCY"):
        await repo.decide_replan(rid, changed, actor="LOCAL_SINGLE_USER", key="deny")
    for field in ("run_id", "object_id", "proposal_id"):
        with pytest.raises(BindingDenied, match="ACCESS"):
            await repo.decide_replan(
                rid, {**body, field: "foreign"}, actor="LOCAL_SINGLE_USER", key=field
            )
    with pytest.raises(BindingDenied, match="ACCESS"):
        await repo.decide_replan(rid, body, actor="foreign", key="actor")
    assert (
        len(
            [
                e
                for e in (await fresh(sessions, rid))["events"]
                if e["type"] == "replan.reopen_stale_rejected"
            ]
        )
        == 1
    )
    distinct = await repo.decide_replan(rid, changed, actor="LOCAL_SINGLE_USER", key="distinct")
    assert distinct["audit_event_id"] != writer["receipt"]["audit_event_id"]
    after = await fresh(sessions, rid)
    assert business(await repo.get_run_fresh(rid)) == writer["business"]
    denials = [e for e in after["events"] if e["type"] == "replan.reopen_stale_rejected"]
    assert len(denials) == 2
    for e, receipt in zip(denials, [writer["receipt"], distinct], strict=True):
        audit = e["payload"]["risk_replan"]
        assert audit["command_key_digest"] == receipt["command_key_digest"]
        assert audit["request_hash"] == receipt["request_hash"]
        assert audit["decision_revision"] == receipt["decision_revision"]
        assert audit["run_id"] == receipt["run_id"] == rid
        assert audit["terminal_status"] == "CANCELLED"
        assert e["event_id"] == receipt["audit_event_id"]
    store = PostgresRuntimeEventStore(sessions)
    events = await store.replay(rid)
    assert (await store.preflight_cursor(rid, str(events[-1].sequence))).terminal_at_cursor
    for method in ("emit", "append"):
        with pytest.raises(EventSequenceError, match="terminal"):
            if method == "emit":
                await store.emit(
                    run_id=rid,
                    event_type=RuntimeEventType.TASK_COMPLETED,
                    task_id=rid + ":risk",
                    payload={"attempt": 1},
                )
            else:
                await store.append(
                    RuntimeEvent(
                        event_id="EVT-forbidden",
                        run_id=rid,
                        type=RuntimeEventType.RUN_STARTED,
                        sequence=events[-1].sequence + 1,
                    )
                )
    # Real SSE preflight/batch reducer must accept the terminal+denial history.
    admitted = await preflight_runtime_event_stream(store=store, run_id=rid, last_event_id=None)
    frames = [
        frame async for frame in runtime_event_stream(store=store, run_id=rid, preflight=admitted)
    ]
    assert frames and "run.failed" in frames[-1]
    cursor = RuntimeEventCursor(run_id=rid)
    for event in events:
        cursor.accept(event)
    invalid = events[-1].model_copy(
        deep=True, update={"event_id": "EVT-invalid", "sequence": events[-1].sequence + 1}
    )
    invalid.payload["risk_replan"].update(event_id="EVT-invalid", terminal_status="RELEASED")
    with pytest.raises(EventReconciliationRequired):
        cursor.accept(invalid)
    await check_typescript_and_schema(events, invalid)
    destination = os.environ.get("RISK_REPLAN_PROOF_RECEIPTS")
    if destination:
        Path(destination).with_name("bounded-denial-processes.json").write_text(
            json.dumps({"writer": writer, "reader": after}, indent=2)
        )


async def check_typescript_and_schema(events, invalid):
    from src.domain.risk_replan import RiskReplanAudit

    schema = json.loads(
        await asyncio.to_thread(Path("contracts/events/runtime_event.schema.json").read_text)
    )
    assert schema["$defs"]["RiskReplanAudit"] == {
        key: value for key, value in RiskReplanAudit.model_json_schema().items() if key != "$defs"
    }
    normalized = [normalize_runtime_event_v1(e).model_dump(mode="json") for e in events]
    for event in normalized:
        if "risk_replan" in event["payload"]:
            RiskReplanAudit.model_validate(event["payload"]["risk_replan"])
    module = (
        await asyncio.to_thread(Path("apps/web/src/runtime/RuntimeTransport.ts").resolve)
    ).as_uri()
    script = f"""
      import {{RuntimeEventIngestionGuard}} from {json.dumps(module)};
      let input=''; for await (const chunk of process.stdin) input += chunk;
      const {{events, invalid}} = JSON.parse(input);
      const guard = new RuntimeEventIngestionGuard({{runId: events[0].run_id, initialSequence: 0,
        authoritativeTaskIds: new Set(events.map(e=>e.task_id).filter(Boolean))}});
      for (const event of events) guard.ingest(event);
      if (guard.ingest(events.at(-1)).kind !== 'DUPLICATE') throw Error('audit replay');
      try {{guard.ingest(invalid); throw Error('accepted invalid denial');}}
      catch (e) {{if (e.reason !== 'EVENT_AFTER_TERMINAL') throw e;}}
    """
    process = await asyncio.create_subprocess_exec(
        "node",
        "--experimental-transform-types",
        "--input-type=module",
        "-e",
        script,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await process.communicate(
        json.dumps(
            {
                "events": normalized,
                "invalid": normalize_runtime_event_v1(invalid).model_dump(mode="json"),
            }
        ).encode()
    )
    assert process.returncode == 0, err.decode()


async def test_other_run_progresses_while_root_locked(database, tmp_path):  # noqa: F811
    from uuid import uuid4

    from src.application.models import RunAggregate
    from src.runtime.state import RuntimeState
    from tests.wp02.confirmation_fixture import confirm_template
    from tests.wp02.test_node_binding import aggregate

    _, sessions = database
    _, first, service = await pending_sql(sessions, tmp_path)
    source = aggregate(("evidence_collection",))
    identity = "OTHER-" + uuid4().hex

    def renamed(value):
        return type(value).model_validate(
            json.loads(value.model_dump_json().replace("WP02", identity))
        )

    plan = renamed(source.runtime.planned_graph)
    template = RunAggregate(
        run=renamed(source.run), goal=renamed(source.goal), scheme=renamed(source.scheme),
        runtime=RuntimeState.create(run_id=plan.run_id, planned_graph=plan),
    )
    value = await confirm_template(service, template, symbol="OTHER")
    store = PostgresRuntimeEventStore(sessions)
    before = await store.replay(first.run.run_id)
    other_before = await store.replay(value.run.run_id)
    async with sessions() as holder, holder.begin():
        await PostgresRuntimeEventStore._lock_run_event_writes(holder, first.run.run_id)
        async with asyncio.timeout(10):
            event = await store.emit(
                run_id=value.run.run_id,
                event_type=RuntimeEventType.RUN_CREATED,
                payload={"object_id": value.run.research_object_id},
            )
        assert event.sequence == len(other_before) + 1 and event.run_id != first.run.run_id
        assert await store.replay(first.run.run_id) == before
    assert (await store.replay(value.run.run_id)) == [*other_before, event]
