"""Fresh-process PostgreSQL proof using the production Run transaction owner."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from src.application.persistence import SQLAlchemyApplicationRepository
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401
from tests.risk_replan.test_flow import command, fixture

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL"
)

READER = """
import asyncio,json,sys
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.application.persistence import SQLAlchemyApplicationRepository
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
async def main():
 engine=create_async_engine(sys.argv[1],connect_args={"server_settings":{"search_path":sys.argv[2]}})
 sessions=async_sessionmaker(engine,expire_on_commit=False)
 repo=SQLAlchemyApplicationRepository(sessions)
 value=await repo.get_run_fresh(sys.argv[3])
 result={"pid":__import__('os').getpid(),"projection":await repo.replan_projection(sys.argv[3]),
 "root":value.node_binding.model_dump(mode="json"),
 "events":[e.model_dump(mode="json")
   for e in await PostgresRuntimeEventStore(sessions).replay(sys.argv[3])]}
 print(json.dumps(result))
 await engine.dispose()
asyncio.run(main())
"""


async def fresh(sessions, run_id):
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        READER,
        os.environ["TEST_POSTGRESQL_URL"],
        schema,
        run_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await process.communicate()
    assert process.returncode == 0, err.decode()
    return json.loads(out)


async def test_durable_cycle(database, tmp_path):  # noqa: F811
    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    store = RecoveryEvidenceStore(sessions)
    service, value, calls, transport = await fixture(
        tmp_path, repository=repo, store=store, sessions=sessions
    )
    run_id = value.run.run_id
    receipts = {}
    from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    with transport:
        value = await service.execute_run(run_id)
        receipts["pending"] = await fresh(sessions, run_id)
        for action, label in [
            ("DECLINE", "declined"),
            ("REOPEN", "reopened"),
            ("APPROVE", "approved"),
        ]:
            await repo.decide_replan(
                run_id, command(value, action), actor="LOCAL_SINGLE_USER", key=label
            )
            value = await repo.get_run_fresh(run_id)
            receipts[label] = await fresh(sessions, run_id)
            await consumer_projection(
                (await backend.get_projection(run_id)).model_dump(mode="json")
            )
        await repo.apply_replan(run_id)
        receipts["applied"] = await fresh(sessions, run_id)
        await consumer_projection((await backend.get_projection(run_id)).model_dump(mode="json"))
        from src.application.execution import IntegratedTaskExecutor
        from src.runtime.scheduler import DependencyScheduler

        owner = await repo.claim_execution(run_id)
        value = await repo.get_run_fresh(run_id)
        await DependencyScheduler(
            event_store=service.event_store,
            checkpoint_store=service.checkpoint_store,
            admission_repository=repo,
            execution_owner=owner,
        ).execute(state=value.runtime, executor=IntegratedTaskExecutor(service, value))
        receipts["fulfilled"] = await fresh(sessions, run_id)
        await consumer_projection((await backend.get_projection(run_id)).model_dump(mode="json"))
    assert receipts["declined"]["projection"]["legal_actions"] == ["CANCEL", "REOPEN"]
    assert receipts["reopened"]["projection"]["active_proposal"]["status"] == "PENDING"
    assert receipts["applied"]["root"]["frozen_graph"]["version"] == 2
    assert receipts["fulfilled"]["root"]["replan"]["finalization"]
    assert len({r["pid"] for r in receipts.values()}) == len(receipts)
    assert sum(kind == "valuation_analysis" for kind, model in calls) == 1
    destination = os.environ.get("RISK_REPLAN_PROOF_RECEIPTS")
    if destination:
        await asyncio.to_thread(Path(destination).write_text, json.dumps(receipts, indent=2))


async def test_http_reconnect_and_cancel(database, tmp_path):  # noqa: F811
    from httpx import ASGITransport, AsyncClient

    from apps.api.main import create_app
    from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, calls, transport = await fixture(
        tmp_path, repository=repo, store=RecoveryEvidenceStore(sessions), sessions=sessions
    )
    with transport:
        value = await service.execute_run(value.run.run_id)
    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    app = create_app(service=service)
    app.state.phase4_product_backend = backend
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as client:
        base = "/api/research-runs/" + value.run.run_id
        read = await client.get(base + "/replan")
        assert read.status_code == 200, read.text
        current = read.json()
        projection = await client.get(base + "/projection")
        assert projection.status_code == 200, projection.text
        await consumer_projection(projection.json())
        assert projection.json()["risk_replan"]["binding_revision"] == current["binding_revision"]
        command_body = command(value, "DECLINE")
        command_body.pop("object_id")
        command_body.pop("action")
        command_body["expected_base_graph"] = command_body.pop("expected_graph")
        rejected = await client.post(
            base + "/replans/" + current["active_proposal"]["proposal_id"] + "/reject",
            json=command_body,
            headers={"Idempotency-Key": "decline-http"},
        )
        assert rejected.status_code == 200, rejected.text
        read = await client.get(base + "/replan")
        assert read.json()["legal_actions"] == ["CANCEL", "REOPEN"]
        cancelled = await client.post(
            base + "/cancel",
            json={
                "run_id": value.run.run_id,
                "abandon": True,
                "expected_control_revision": read.json()["control_revision"],
            },
            headers={"Idempotency-Key": "cancel-http"},
        )
        assert cancelled.status_code == 200, cancelled.text
        projection = await client.get(base + "/projection")
        assert projection.status_code == 200, projection.text
        await consumer_projection(projection.json())
        assert projection.json()["run"]["status"] == "CANCELLED"


WORKER = """
import asyncio,json,sys
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.application.persistence import SQLAlchemyApplicationRepository
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.risk_replan.test_flow import fixture
from tests.risk_replan.test_recovery import resume
async def main():
 engine=create_async_engine(sys.argv[1],connect_args={"server_settings":{"search_path":sys.argv[2]}})
 sessions=async_sessionmaker(engine,expire_on_commit=False)
 repo=SQLAlchemyApplicationRepository(sessions)
 service,_,calls,transport=await fixture(Path(sys.argv[4]),repository=repo,
   store=RecoveryEvidenceStore(sessions),sessions=sessions,persist=False)
 before=await repo.get_run_fresh(sys.argv[3])
 with transport:
  if sys.argv[5]=='apply':
   assert sys.argv[3] in await repo.replan_work_run_ids()
   await repo.apply_replan(sys.argv[3])
  else:
   await resume(service,sys.argv[3])
 after=await repo.get_run_fresh(sys.argv[3])
 print(json.dumps({"pid":__import__('os').getpid(),"calls":calls,
   "started_at_preserved":before.run.started_at==after.run.started_at,
   "root":after.node_binding.model_dump(mode="json")}))
 await engine.dispose()
asyncio.run(main())
"""


async def test_fresh_worker_apply_and_child_recovery(database, tmp_path):  # noqa: F811
    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, calls, transport = await fixture(
        tmp_path,
        repository=repo,
        store=RecoveryEvidenceStore(sessions),
        sessions=sessions,
        failure_plan={("risk_follow_up", "gpt-5.6-sol"): ["timeout"]},
    )
    run_id = value.run.run_id
    with transport:
        value = await service.execute_run(run_id)
    await repo.decide_replan(run_id, command(value, "APPROVE"), actor="LOCAL_SINGLE_USER", key="A")
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))

    async def worker(phase):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            WORKER,
            os.environ["TEST_POSTGRESQL_URL"],
            schema,
            run_id,
            str(tmp_path),
            phase,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await process.communicate()
        assert process.returncode == 0, err.decode()
        return json.loads(out)

    applied = await worker("apply")
    with transport:
        value = await service.execute_run(run_id)
    assert value.node_binding.lifecycle == "RECOVERY_PENDING"
    prior = value.node_binding.attempts[run_id + ":risk-follow-up"]
    completed = await worker("resume")
    assert applied["pid"] != completed["pid"] != os.getpid()
    assert completed["started_at_preserved"]
    assert [model for kind, model in completed["calls"] if kind == "risk_follow_up"] == [
        "gpt-5.6-terra"
    ]
    assert not any(kind == "valuation_analysis" for kind, model in completed["calls"])
    assert completed["root"]["replan"]["finalization"]
    assert completed["root"]["attempt_history"][prior.admission.attempt_reservation_id] == (
        prior.model_dump(mode="json")
    )
    destination = os.environ.get("RISK_REPLAN_PROOF_RECEIPTS")
    if destination:
        Path(destination).with_name("fresh-worker.json").write_text(
            json.dumps({"applied": applied, "completed": completed}, indent=2)
        )


@pytest.mark.parametrize("actions", [("APPROVE", "DECLINE"), ("REOPEN", "CANCEL")])
async def test_sql_decision_races_fresh_receipts(database, tmp_path, actions):  # noqa: F811
    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, calls, transport = await fixture(
        tmp_path, repository=repo, store=RecoveryEvidenceStore(sessions), sessions=sessions
    )
    with transport:
        value = await service.execute_run(value.run.run_id)
    run_id = value.run.run_id
    if actions[0] == "REOPEN":
        await repo.decide_replan(
            run_id, command(value, "DECLINE"), actor="LOCAL_SINGLE_USER", key="D"
        )
        value = await repo.get_run_fresh(run_id)
    commands = [command(value, action) for action in actions]
    results = await asyncio.gather(
        *[
            SQLAlchemyApplicationRepository(sessions).decide_replan(
                run_id, body, actor="LOCAL_SINGLE_USER", key=body["action"]
            )
            for body in commands
        ],
        return_exceptions=True,
    )
    committed = [r for r in results if isinstance(r, dict) and r["outcome"] == "COMMITTED"]
    assert len(committed) == 1
    receipt = await fresh(sessions, run_id)
    assert receipt["root"]["frozen_graph"]["version"] == 1
    assert len(receipt["root"]["current_results"]) == 3
    for body, result in zip(commands, results, strict=True):
        if isinstance(result, dict):
            replay = await SQLAlchemyApplicationRepository(sessions).decide_replan(
                run_id, body, actor="LOCAL_SINGLE_USER", key=body["action"]
            )
            assert {k: v for k, v in replay.items() if k != "historical_replay"} == {
                k: v for k, v in result.items() if k != "historical_replay"
            }
    assert len(calls) == 3


async def test_orphan_unknown_survives_decline_and_reopen_without_dispatch(database, tmp_path):  # noqa: F811
    from src.application.risk_replan import control

    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, calls, transport = await fixture(
        tmp_path, repository=repo, store=RecoveryEvidenceStore(sessions), sessions=sessions
    )
    with transport:
        value = await service.execute_run(value.run.run_id)
    run_id = value.run.run_id
    task_id = run_id + ":valuation"
    # Failure injection through the production aggregate transaction owner: emulate
    # a worker whose dispatch outcome cannot be reconciled, never direct DB writes.
    async with repo._binding_transaction(run_id) as current:
        current.node_binding.attempts[task_id] = current.node_binding.attempts[task_id].model_copy(
            update={"status": "RESULT_UNKNOWN"}
        )
        current.node_binding.current_results.pop(task_id)
    for action in ("DECLINE", "REOPEN"):
        value = await repo.get_run_fresh(run_id)
        await repo.decide_replan(
            run_id, command(value, action), actor="LOCAL_SINGLE_USER", key=action
        )
        read = await fresh(sessions, run_id)
        assert read["root"]["attempts"][task_id]["status"] == "RESULT_UNKNOWN"
        assert not read["root"]["replan"]["resume_eligible"]
        assert run_id not in await repo.replan_work_run_ids()
    value = await repo.get_run_fresh(run_id)
    await repo.decide_replan(run_id, command(value, "APPROVE"), actor="LOCAL_SINGLE_USER", key="A")
    assert await repo.apply_replan(run_id) is None
    current = await repo.get_run_fresh(run_id)
    assert control(current).transition is None and len(calls) == 3


async def consumer_projection(value):
    module = (await asyncio.to_thread(Path("apps/web/src/types/domain.ts").resolve)).as_uri()
    events_module = (
        await asyncio.to_thread(Path("apps/web/src/runtime/RuntimeTransport.ts").resolve)
    ).as_uri()
    script = f"""
      import {{decodeRunProjection}} from {json.dumps(module)};
      import {{decodeRuntimeEventV1}} from {json.dumps(events_module)};
      let input = ''; for await (const chunk of process.stdin) input += chunk;
      const wire = JSON.parse(input);
      const decoded = decodeRunProjection(wire, wire.run.run_id, wire.object.object_id);
      if (!decoded.riskReplan) throw Error('Missing Replan projection');
      for (const item of wire.activity) {{
        if (item.payload?.risk_replan) {{
          const audit = item.payload.risk_replan;
          decodeRuntimeEventV1({{
            event_contract_version: 'phase4-runtime-event/v1', payload_schema_version: 1,
            event_id: audit.event_id, run_id: audit.run_id, task_id: item.task_id,
            type: audit.type, timestamp: audit.timestamp, sequence: item.sequence,
            payload: {{risk_replan: audit}}, graph_version: null,
            effect: 'REFRESH_PROJECTION', projection_refresh_required: true
          }}, {{expectedRunId: wire.run.run_id}});
        }}
      }}
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
    out, err = await process.communicate(json.dumps(value).encode())
    assert process.returncode == 0, err.decode()
