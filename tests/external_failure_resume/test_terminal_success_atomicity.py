"""S1 integration on lawful offline report preparation and production PostgreSQL."""

# Reuse the hash-verified RMR22 legal proposal and per-test disposable database.
import asyncio
import os
from copy import deepcopy

import pytest
from sqlalchemy import event

from src.adapters.finrobot.professional_reporting import (
    ControlledArtifactStore,
    ProfessionalReportPublisher,
)
from src.application.persistence import (
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.application.service import ResearchApplicationService
from src.domain.node_binding import BindingDenied
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.external_failure_resume.test_terminal_success_bounds import (
    budget,
    read,
    settle,
    snapshot,
)
from tests.external_failure_resume.test_terminal_success_bounds import (
    case as case,
)
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401
from tests.report_metrics.runtime_fixture import report_fixture

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL"
)


@pytest.mark.parametrize("delivery_loss", [False, True])
async def test_u01_production_service_atomic_success(
    database,  # noqa: F811
    tmp_path,
    monkeypatch,
    delivery_loss,
):  # noqa: F811
    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, initial, clients, backend, _ = await report_fixture(
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
    captured = {}
    original = repo.finalize_success

    async def capture(owner, proposed, **kwargs):
        from types import SimpleNamespace

        captured.update(
            owner=owner,
            proposed=deepcopy(proposed),
            kwargs=kwargs,
            before=await snapshot({"p": SimpleNamespace(sessions=sessions), "owner": owner}),
        )
        result = await original(owner, proposed, **kwargs)
        if delivery_loss:
            raise TimeoutError("S1 post-commit delivery loss")
        return result

    async def forbidden(*args, **kwargs):
        pytest.fail("split settlement or failure owner called")

    monkeypatch.setattr(repo, "finalize_success", capture)
    monkeypatch.setattr(repo, "close_execution", forbidden)
    monkeypatch.setattr(repo, "finalize_failure", forbidden)
    monkeypatch.setattr(service, "_emit_release_completion", forbidden)
    if delivery_loss:
        with pytest.raises(TimeoutError, match="post-commit delivery loss"):
            await service.execute_run(initial.run.run_id)
        value = await repo.get_run_fresh(initial.run.run_id)
    else:
        value = await service.execute_run(initial.run.run_id)
    assert value.run.status.value == "RELEASED"
    assert value.node_binding.lifecycle == "CLOSED"
    assert value.artifacts.review.status.value == "PASS"
    assert len(value.artifacts.released_result.released_metrics) == 1
    assert value.confirmed_risk_semantic_binding == initial.confirmed_risk_semantic_binding
    events = await service.event_store.replay(value.run.run_id)
    assert [e.type.value for e in events[-2:]] == ["release.completed", "run.completed"]
    assert events[-1].timestamp == value.run.completed_at
    assert (
        value.node_binding.binding_revision
        == captured["proposed"].node_binding.binding_revision + 1
    )
    from types import SimpleNamespace

    c = {"p": SimpleNamespace(sessions=sessions), "owner": captured["owner"]}
    committed_snapshot = await snapshot(c)
    calls = sum(c.calls for c in clients.values())
    monkeypatch.setattr(repo, "claim_execution", forbidden)
    monkeypatch.setattr(service, "_assure_and_release", forbidden)
    replay = await service.execute_run(value.run.run_id)
    assert repo._payload(replay) == repo._payload(value)
    await backend._publish_latest_projection_watermark(
        value.run.run_id,
        expected_binding_ref=value.node_binding.reference(),
        settlement_budget=captured["kwargs"]["budget"],
    )
    assert sum(c.calls for c in clients.values()) == calls
    assert await service.event_store.replay(value.run.run_id) == events
    assert await snapshot(c) == committed_snapshot
    if os.environ.get("S1_PROOF_DIR"):
        import gzip
        import json
        from pathlib import Path

        root = Path(os.environ["S1_PROOF_DIR"])
        prefix = "service-loss" if delivery_loss else "service-ack"
        for label, data in (
            ("before", captured["before"]),
            ("after", committed_snapshot),
            ("replayed", await snapshot(c)),
        ):
            (root / (prefix + "-" + label + ".json.gz")).write_bytes(
                gzip.compress(json.dumps(data, sort_keys=True).encode()),
            )
        (root / (prefix + "-command.json")).write_text(
            json.dumps(
                {
                    "owner": captured["owner"].model_dump(mode="json"),
                    "proposed": repo._payload(captured["proposed"]),
                    "released_at": captured["kwargs"]["released_at"].isoformat(),
                    "events": [e.model_dump(mode="json") for e in events[-2:]],
                    "receipt_unchanged": value.confirmed_risk_semantic_binding
                    == initial.confirmed_risk_semantic_binding,
                },
                indent=2,
            )
        )


@pytest.mark.parametrize("fault", ["before", "fence", "first_event", "children", "commit"])
async def test_u02_u05_exact_rollback(case, monkeypatch, fault):  # noqa: F811
    c = case
    before = await snapshot(c)
    repo = c["repo"]
    method = {
        "before": "_success_transaction",
        "fence": "_persist_success_events",
        "children": "_persist_children",
        "commit": "_commit_success",
    }.get(fault)
    hook = None
    if fault == "first_event":

        def hook(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO runtime_events"):
                raise RuntimeError("S1 after first terminal event allocation")

        event.listen(c["p"].engine.sync_engine, "after_cursor_execute", hook)
    else:
        original = getattr(repo, method)

        async def fail(*args, **kwargs):
            if fault == "before" and kwargs.get("readback"):
                return await original(*args, **kwargs)
            if fault == "children":
                await original(*args, **kwargs)
                await args[0].flush()
            raise RuntimeError("S1 before commit fault:" + fault)

        monkeypatch.setattr(repo, method, fail)
    try:
        with pytest.raises(BindingDenied, match="RESULT_UNKNOWN"):
            await settle(c)
    finally:
        if hook is not None:
            event.remove(c["p"].engine.sync_engine, "after_cursor_execute", hook)
    assert await snapshot(c) == before


async def test_u06_atomic_visibility(case, monkeypatch):  # noqa: F811
    c = case
    before = await snapshot(c)
    ready, release = asyncio.Event(), asyncio.Event()
    original = c["repo"]._commit_success

    async def hold(session):
        ready.set()
        await release.wait()
        await original(session)

    monkeypatch.setattr(c["repo"], "_commit_success", hold)
    task = asyncio.create_task(settle(c))
    try:
        await asyncio.wait_for(ready.wait(), 30)
        assert await snapshot(c) == before
    finally:
        release.set()
    value, events = await task
    assert value.node_binding.lifecycle == "CLOSED"
    assert [e.type.value for e in events] == ["release.completed", "run.completed"]
    assert (await read(c))[1] == events


async def test_u08_u12_replay_identity_and_fencing(case, monkeypatch):  # noqa: F811
    c = case
    value, events = await settle(c)
    before = await snapshot(c)
    repos = [SQLAlchemyApplicationRepository(c["p"].sessions) for _ in range(2)]
    results = await asyncio.gather(*(settle(c, repo=r) for r in repos))
    assert all(r[1] == events for r in results)
    for field in ("released_at", "owner", "proposed"):
        changed = dict(c)
        if field == "released_at":
            from datetime import timedelta

            changed[field] += timedelta(microseconds=1)
        elif field == "owner":
            changed[field] = c[field].model_copy(
                update={"owner_generation": c[field].owner_generation + 1}
            )
        else:
            changed[field] = deepcopy(c[field])
            changed[field].run.completed_at = changed[field].run.completed_at.replace(year=2025)
        with pytest.raises(BindingDenied):
            await settle(changed)
        assert await snapshot(c) == before
    with pytest.raises(BindingDenied, match="STALE_WRITE_REJECTED"):
        await c["repo"].save_run(c["proposed"])
    service = ResearchApplicationService(repository=repos[0], report_publisher=c["report_store"])

    async def forbidden(*args, **kwargs):
        pytest.fail("replay acquired authority or prepared new result")

    monkeypatch.setattr(repos[0], "claim_execution", forbidden)
    monkeypatch.setattr(service, "_assure_and_release", forbidden)
    replay = await service.execute_run(value.run.run_id)
    assert c["repo"]._payload(replay) == c["repo"]._payload(value)
    with pytest.raises(BindingDenied, match="STALE_WRITE_REJECTED"):
        await service.execute_run(
            value.run.run_id,
            execution_owner=c["owner"].model_copy(update={"owner_id": "foreign-owner"}),
        )
    assert await snapshot(c) == before


@pytest.mark.parametrize("code", ["RESULT_UNKNOWN", "IDENTITY_MISMATCH"])
async def test_u13_replay_denial_never_failure(case, monkeypatch, code):  # noqa: F811
    c = case
    service = ResearchApplicationService(repository=c["repo"], report_publisher=c["report_store"])
    before = await snapshot(c)

    async def denied(*args, **kwargs):
        raise BindingDenied(code, "S1 deterministic readback fault")

    async def forbidden(*args, **kwargs):
        pytest.fail("unknown/integrity result invoked a failure writer")

    monkeypatch.setattr(c["repo"], "read_terminal_success", denied)
    monkeypatch.setattr(c["repo"], "finalize_failure", forbidden)
    monkeypatch.setattr(c["repo"], "claim_execution", forbidden)
    with pytest.raises(BindingDenied, match=code):
        await service.execute_run(c["owner"].run_id)
    assert await snapshot(c) == before


async def test_u14_consumed_context_blocks_before_claim(case, monkeypatch):  # noqa: F811
    c = case
    service = ResearchApplicationService(repository=c["repo"], report_publisher=c["report_store"])
    before = await snapshot(c)

    async def forbidden(*args, **kwargs):
        pytest.fail("exhausted context began new work")

    monkeypatch.setattr(c["repo"], "claim_execution", forbidden)
    monkeypatch.setattr(c["repo"], "finalize_failure", forbidden)
    with pytest.raises(BindingDenied, match="RESULT_UNKNOWN"):
        await service.execute_run(c["owner"].run_id, settlement_budget=budget(-1))
    assert await snapshot(c) == before


@pytest.mark.parametrize("minimal", [False, True])
async def test_u16_u17_legal_resume_releases(database, tmp_path, monkeypatch, minimal):  # noqa: F811
    from src.application.resume_runtime import current_risk_success
    from tests.external_failure_resume.runtime_fixture import exhaust, request_for

    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    preferences = {
        "report_metric_requirements": {
            "schema_version": "frozen-report-metric-requirements/v1",
            "report_mode": "METRIC_FOCUSED",
            "required_metric_ids": ["revenue_growth_v1"],
            "period": "FY2026",
        }
    }
    if minimal:
        preferences["risk_semantic_profile"] = "risk_semantic_outcome_minimal_v1"
    service, initial, clients, backend, _ = await report_fixture(
        tmp_path,
        repository=repo,
        evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions),
        event_store=PostgresRuntimeEventStore(sessions),
        sessions=sessions,
        preferences=preferences,
    )
    service.report_publisher = ProfessionalReportPublisher(
        ControlledArtifactStore(tmp_path / "reports")
    )
    for client in clients.values():
        client.fail_risk = True
    failed = await exhaust(service, initial)
    request = await request_for(service, failed)
    await repo.resume_external_failure(request, actor=request.actor)
    for client in clients.values():
        client.fail_risk = False
    value = await service.execute_run(initial.run.run_id)
    assert value.run.status.value == "RELEASED"
    assert current_risk_success(value)
    assert value.confirmed_risk_semantic_binding == initial.confirmed_risk_semantic_binding
    events = await service.event_store.replay(value.run.run_id)
    assert events[-1].type.value == "run.completed"
    assert value.node_binding.lifecycle == "CLOSED"
    fresh_service = ResearchApplicationService(
        repository=repo, report_publisher=service.report_publisher,
        event_store=service.event_store,
    )
    assert await fresh_service._resume_liveness_scope(value.run.run_id) is None
    before_replay = repo._payload(value)

    async def forbidden_reexecution(*args, **kwargs):
        pytest.fail("terminal Resume replay must not claim or prepare new work")

    with monkeypatch.context() as replay_patch:
        replay_patch.setattr(repo, "claim_execution", forbidden_reexecution)
        replay_patch.setattr(fresh_service, "_assure_and_release", forbidden_reexecution)
        replayed = await fresh_service.execute_run(value.run.run_id)
    assert repo._payload(replayed) == before_replay
    assert not getattr(fresh_service, "_resume_liveness_scopes", {})
    await backend._publish_latest_projection_watermark(
        value.run.run_id,
        expected_binding_ref=value.node_binding.reference(),
    )


async def test_u07_process_exit_committed_service_replay(case):  # noqa: F811
    import json
    import sys

    c = case
    code = """import asyncio,os,sys,json
from pathlib import Path
from src.infrastructure.database.composition import create_postgresql_persistence
from src.infrastructure.config.settings import DatabaseSettings
from src.application.persistence import TerminalSettlementBudget
from src.application.service import ResearchApplicationService
from src.adapters.finrobot.professional_reporting import ControlledArtifactStore
from src.domain.node_binding import OwnerToken
async def main():
 p=create_postgresql_persistence(DatabaseSettings(url=sys.argv[1]))
 repo=p.application_repository
 store=ControlledArtifactStore(Path(sys.argv[3]))
 if sys.argv[4]=="commit":
  base=Path(sys.argv[5]); data=json.loads((base/"legal_proposal.json").read_text())
  proposed=repo._to_aggregate(data,data.get("aggregate_schema_version",1))
  owner=OwnerToken.model_validate_json((base/"execution_owner.json").read_text())
  from datetime import datetime,UTC
  original=repo._commit_success
  async def crash(session):
   await original(session)
   os._exit(73)
  repo._commit_success=crash
  await repo.finalize_success(owner,proposed,released_at=datetime.now(UTC),
   budget=TerminalSettlementBudget(asyncio.get_running_loop().time()+300),report_store=store)
 else:
  async def forbidden(*a,**kw):raise AssertionError("replay attempted execution")
  repo.claim_execution=forbidden
  service=ResearchApplicationService(repository=repo,report_publisher=store)
  service._assure_and_release=forbidden
  result=await service.execute_run(sys.argv[2])
  print(json.dumps(repo._payload(result)))
  await p.close()
asyncio.run(main())"""

    async def child(mode):
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            c["url"].replace("postgresql://", "postgresql+asyncpg://"),
            c["owner"].run_id,
            str(c["report_store"].root),
            mode,
            str(c["base"]),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode, out, err

    rc, _, err = await child("commit")
    assert rc == 73, err.decode()
    before = await snapshot(c)
    rc, out, err = await child("read")
    assert rc == 0, err.decode()
    value, _ = await read(c)
    assert json.loads(out) == c["repo"]._payload(value)
    assert await snapshot(c) == before


async def test_u13_backend_delivery_failure_is_nonmutating(case, monkeypatch):  # noqa: F811
    from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

    c = case
    value, _ = await settle(c)
    before = await snapshot(c)
    service = ResearchApplicationService(
        repository=c["repo"],
        report_publisher=c["report_store"],
        event_store=PostgresRuntimeEventStore(c["p"].sessions),
    )
    backend = PostgreSQLPhase4ProductBackend(sessions=c["p"].sessions, service=service)

    async def failed(*args, **kwargs):
        raise TimeoutError("S1 derived projection delivery")

    async def forbidden(*args, **kwargs):
        pytest.fail("postcommit delivery invoked failure/claim")

    monkeypatch.setattr(backend, "_publish_latest_projection_watermark", failed)
    monkeypatch.setattr(c["repo"], "claim_execution", forbidden)
    monkeypatch.setattr(c["repo"], "finalize_failure", forbidden)
    with pytest.raises(TimeoutError, match="derived projection"):
        await backend._execute_started_run(value.run.run_id)
    assert await snapshot(c) == before


async def test_u14_preterminal_timeout_keeps_failure_owner(case, monkeypatch):  # noqa: F811
    from src.runtime.scheduler import DependencyScheduler

    c = case
    service = ResearchApplicationService(
        repository=c["repo"],
        report_publisher=c["report_store"],
        event_store=PostgresRuntimeEventStore(c["p"].sessions),
    )

    async def expired(self, **kwargs):
        kwargs["on_execution_admitted"]()
        raise TimeoutError("S1 admitted preterminal timeout")

    monkeypatch.setattr(DependencyScheduler, "execute", expired)
    with pytest.raises(TimeoutError, match="admitted preterminal"):
        await service.execute_run(c["owner"].run_id, execution_owner=c["owner"])
    fresh = await c["repo"].get_run_fresh(c["owner"].run_id)
    assert fresh.run.status.value == "FAILED"
    assert fresh.node_binding.owner_generation == c["owner"].owner_generation + 1
    events = await service.event_store.replay(c["owner"].run_id)
    assert events[-1].type.value == "run.failed"
    assert events[-1].timestamp == fresh.run.completed_at
    assert not any(e.type.value in {"release.completed", "run.completed"} for e in events)


@pytest.mark.skipif(not os.environ.get("S1_OWNED_PGDATA"), reason="explicit owned restart required")
async def test_u18_disposable_restart_exact_readback(restart_case):  # noqa: F811
    import sys

    c = restart_case
    pgdata = os.environ["S1_OWNED_PGDATA"]
    pgctl = os.environ["S1_OWNED_PGCTL"]
    assert pgdata.endswith("/work/s1-pg")
    value, events = await settle(c)
    before = await snapshot(c)
    await c["p"].engine.dispose()
    proc = await asyncio.create_subprocess_exec(
        pgctl,
        "-D",
        pgdata,
        "-l",
        os.path.join(os.path.dirname(pgdata), "s1-restart-server.log"),
        "restart",
        "-m",
        "fast",
        "-w",
        cwd=os.path.dirname(os.path.dirname(pgdata)),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(proc.communicate(), 45)
    assert proc.returncode == 0, (out + err).decode()
    replay = await read(c)
    assert c["repo"]._payload(replay[0]) == c["repo"]._payload(value)
    assert replay[1] == events
    assert await snapshot(c) == before
    # A distinct interpreter after restart uses service replay with no publisher loop.
    code = """import asyncio,sys,json
from pathlib import Path
from src.infrastructure.database.composition import create_postgresql_persistence
from src.infrastructure.config.settings import DatabaseSettings
from src.application.service import ResearchApplicationService
from src.adapters.finrobot.professional_reporting import ControlledArtifactStore
async def main():
 p=create_postgresql_persistence(DatabaseSettings(url=sys.argv[1]))
 s=ResearchApplicationService(repository=p.application_repository,
  report_publisher=ControlledArtifactStore(Path(sys.argv[3])))
 r=await s.execute_run(sys.argv[2])
 print(json.dumps(p.application_repository._payload(r)))
 await p.close()
asyncio.run(main())"""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        code,
        c["url"].replace("postgresql://", "postgresql+asyncpg://"),
        value.run.run_id,
        str(c["report_store"].root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    assert proc.returncode == 0, err.decode()
    import json

    assert json.loads(out) == c["repo"]._payload(value)
    assert await snapshot(c) == before


@pytest.fixture
async def restart_case():
    # Separate ownership: cluster restart intentionally closes every connection.
    # Unlike ordinary case fixtures, reopen the admin connection for cleanup.
    import json
    from pathlib import Path
    from uuid import uuid4

    import asyncpg

    from src.domain.node_binding import OwnerToken
    from src.infrastructure.config.settings import DatabaseSettings
    from src.infrastructure.database.composition import create_postgresql_persistence

    base = Path(os.environ["D1_RMC1_FIXTURE"])
    name = "s1_restart_" + uuid4().hex
    url = os.environ["D1_TEST_ADMIN_URL"].rsplit("/", 1)[0] + "/" + name
    template = os.environ["D1_TEST_TEMPLATE"]
    assert template.replace("_", "").isalnum()
    admin = await asyncpg.connect(os.environ["D1_TEST_ADMIN_URL"])
    await admin.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
    await admin.close()
    p = create_postgresql_persistence(
        DatabaseSettings(
            url=url.replace("postgresql://", "postgresql+asyncpg://"),
        )
    )
    try:
        from datetime import UTC, datetime

        data = json.loads((base / "legal_proposal.json").read_text())
        proposed = p.application_repository._to_aggregate(
            data, data.get("aggregate_schema_version", 1)
        )
        yield dict(
            p=p,
            repo=p.application_repository,
            owner=OwnerToken.model_validate_json((base / "execution_owner.json").read_text()),
            proposed=proposed,
            released_at=datetime.now(UTC),
            url=url,
            report_store=ControlledArtifactStore(base / "product" / "report"),
        )
    finally:
        await p.close()
        admin = await asyncpg.connect(os.environ["D1_TEST_ADMIN_URL"])
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


async def test_u11_changed_receipt_result_and_graph_denied(case):  # noqa: F811
    from datetime import datetime, timedelta

    c = case
    await settle(c)
    before = await snapshot(c)
    for field in ("receipt", "result", "canonical", "graph", "revision"):
        proposed = deepcopy(c["proposed"])
        if field == "receipt":
            receipt = proposed.confirmed_risk_semantic_binding
            proposed.confirmed_risk_semantic_binding = receipt.model_copy(
                update={
                    "confirmed_at": (
                        datetime.fromisoformat(receipt.confirmed_at) + timedelta(microseconds=1)
                    ).isoformat()
                },
            )
        elif field == "result":
            proposed.artifacts.released_result = proposed.artifacts.released_result.model_copy(
                update={"result_id": "RESULT-FOREIGN"},
            )
        elif field == "canonical":
            proposed.artifacts.canonical_record = proposed.artifacts.canonical_record.model_copy(
                update={"record_id": "RECORD-FOREIGN"},
            )
        elif field == "graph":
            proposed.runtime.actual_graph.graph_id = "GRAPH-FOREIGN"
        else:
            proposed.node_binding.binding_revision += 1
            proposed.runtime.binding_ref = proposed.node_binding.reference()
        with pytest.raises(BindingDenied):
            await settle({**c, "proposed": proposed})
        assert await snapshot(c) == before


async def test_u18_immediate_product_projection(case):  # noqa: F811
    from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

    c = case
    value, events = await settle(c)
    before = await snapshot(c)
    service = ResearchApplicationService(
        repository=SQLAlchemyApplicationRepository(c["p"].sessions),
        report_publisher=c["report_store"],
        event_store=PostgresRuntimeEventStore(c["p"].sessions),
    )
    backend = PostgreSQLPhase4ProductBackend(sessions=c["p"].sessions, service=service)
    projection = await backend._build_projection(value.run.run_id, persist=False)
    assert projection.projection_sequence == events[-1].sequence
    assert await snapshot(c) == before


async def test_u10_backend_replay_precedes_claim_and_shares_budget(case, monkeypatch):  # noqa: F811
    from sqlalchemy import select

    from src.infrastructure.database.phase4_product import Phase4SchedulerAdmissionRow
    from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

    c = case
    value, _ = await settle(c)
    before = await snapshot(c)
    service = ResearchApplicationService(
        repository=c["repo"],
        report_publisher=c["report_store"],
        event_store=PostgresRuntimeEventStore(c["p"].sessions),
    )
    backend = PostgreSQLPhase4ProductBackend(sessions=c["p"].sessions, service=service)

    async def forbidden(*args, **kwargs):
        pytest.fail("backend replay attempted owner claim")

    monkeypatch.setattr(c["repo"], "claim_execution", forbidden)
    monkeypatch.setattr(SQLAlchemyApplicationRepository, "claim_execution_in_session", forbidden)
    async with c["p"].sessions() as session:
        admission = await session.scalar(select(Phase4SchedulerAdmissionRow))
        admission_id = admission.admission_id
    await backend._start_admitted_run(admission_id)
    assert await snapshot(c) == before
    calls = []
    original = c["repo"].read_terminal_success

    async def observe(*args, **kwargs):
        calls.append(kwargs["budget"])
        return await original(*args, **kwargs)

    monkeypatch.setattr(c["repo"], "read_terminal_success", observe)
    context = budget(90)
    await backend._create_execution_task(value.run.run_id, None, context)
    assert calls and all(b is context for b in calls)
    assert await snapshot(c) == before
    attempts = 0

    async def pending():
        nonlocal attempts
        attempts += 1
        if attempts > 1:
            raise asyncio.CancelledError
        return [value.run.run_id]

    monkeypatch.setattr(c["repo"], "external_resume_pending_run_ids", pending)
    with pytest.raises(asyncio.CancelledError):
        await backend._scheduler_loop()
    assert await snapshot(c) == before
