"""A1R production accounting and isolated PostgreSQL Resume controls."""

import asyncio
import os

import pytest

from src.adapters.finrobot.professional_reporting import (
    ControlledArtifactStore,
    ProfessionalReportPublisher,
)
from src.application.persistence import (
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.application.resume_runtime import current_risk_success
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from src.runtime.scheduler import ResumeLiveness, resume_liveness
from tests.external_failure_resume.runtime_fixture import exhaust, request_for
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401
from tests.report_metrics.runtime_fixture import report_fixture


@pytest.mark.parametrize("elapsed", [59.999, 60, 61])
def test_no_progress_boundary(elapsed):
    now = [0.0]
    scope = ResumeLiveness("run", "cycle", clock=lambda: now[0])
    now[0] = elapsed
    if elapsed >= 60:
        with pytest.raises(TimeoutError, match="NO_PROGRESS"):
            scope.checkpoint()
    else:
        scope.checkpoint()


@pytest.mark.parametrize("elapsed", [299.999, 300, 301])
def test_cumulative_cap_and_noop_progress(elapsed):
    now = [0.0]
    scope = ResumeLiveness("run", "cycle", clock=lambda: now[0])
    for i in range(1, 7):
        now[0] = elapsed if i == 6 else i * 50
        if now[0] >= 300:
            with pytest.raises(TimeoutError, match="HARD_CAP"):
                scope.progress(("commit", i))
            break
        scope.progress(("commit", i))
    assert scope.orchestration == elapsed
    if elapsed < 300:
        before = scope.no_progress
        now[0] += 0.0001
        scope.progress(("commit", 6))
        assert scope.no_progress == pytest.approx(before + 0.0001)


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL")
@pytest.mark.parametrize(
    "fault", ["active", "fallback", "nonactive", "cap", "own_expiry", "resistant"],
)
async def test_production_resume_clock(
    database, tmp_path, monkeypatch, fault, record_property,  # noqa: F811
):
    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, initial, clients, backend, _ = await report_fixture(
        tmp_path, repository=repo, evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions), event_store=PostgresRuntimeEventStore(sessions),
        sessions=sessions,
        preferences={
            "risk_semantic_profile": "risk_semantic_outcome_minimal_v1",
            "report_metric_requirements": {
                "schema_version": "frozen-report-metric-requirements/v1",
                "report_mode": "METRIC_FOCUSED",
                "required_metric_ids": ["revenue_growth_v1"], "period": "FY2026",
            },
        },
    )
    service.report_publisher = ProfessionalReportPublisher(
        ControlledArtifactStore(tmp_path / "reports")
    )
    for client in clients.values():
        client.fail_risk = True
    failed = await exhaust(service, initial)
    request = await request_for(service, failed)
    receipt = await repo.resume_external_failure(request, actor=request.actor)
    for client in clients.values():
        client.fail_risk = False
    scope = await service._resume_liveness_scope(initial.run.run_id)
    real_clock = scope.clock
    offset = [0.0]
    scope.clock = lambda: real_clock() + offset[0]
    injected = []
    release_transport = asyncio.Event()
    transport_returned = asyncio.Event()
    route = "teamorouter-terra" if fault == "fallback" else "teamorouter-sol"
    original = clients[route].complete_structured

    async def client(**kwargs):
        if "risk_analysis" in kwargs["schema_name"] and not injected:
            assert resume_liveness.get() is scope
            assert scope.spans
            injected.append(True)
            if fault == "own_expiry":
                import src.agentic.recovery as recovery_module

                clock = recovery_module.monotonic
                response = await original(**kwargs)
                monkeypatch.setattr(recovery_module, "monotonic", lambda: clock() + 301)
                return response
            if fault == "resistant":
                offset[0] += 151  # frozen provider90 + 61 eligible stalled seconds
                scope.changed.set()
                while not release_transport.is_set():
                    try:
                        await release_transport.wait()
                    except asyncio.CancelledError:
                        pass
                response = await original(**kwargs)
                transport_returned.set()
                return response
            offset[0] += 61
        return await original(**kwargs)

    validate = repo.validate_execution

    async def delay(owner):
        value = await validate(owner)
        if value.node_binding.scheduler_started and not injected:
            assert not scope.spans
            injected.append(True)
            previous = scope.no_progress
            for step in (10, 10, 10, 10, 10, 11):
                offset[0] += step
                unchanged = await repo.get_run_fresh(value.run.run_id)
                from src.application.repository import validate_root

                validate_root(unchanged)
                unchanged.node_binding.reference()
                repo._payload(unchanged)
                scope.advance()
                assert scope.no_progress >= previous + step
                previous = scope.no_progress
        return value

    if fault in {"active", "fallback"}:
        monkeypatch.setattr(clients[route], "complete_structured", client)
        if fault == "fallback":
            clients["teamorouter-sol"].fail_risk = True
            pending = await service.execute_run(initial.run.run_id)
            assert pending.node_binding.lifecycle == "RECOVERY_PENDING"
            assert await service._resume_liveness_scope(initial.run.run_id) is scope
            consumed = scope.orchestration
            offset[0] += 20
        value = await service.execute_run(initial.run.run_id)
        if fault == "fallback":
            assert scope.orchestration >= consumed + 20
        assert value.run.status.value == "RELEASED"
        assert current_risk_success(value)
        assert scope.finished
        assert scope.max_no_progress < 60
    elif fault in {"own_expiry", "resistant"}:
        monkeypatch.setattr(clients[route], "complete_structured", client)
        try:
            with pytest.raises((ExceptionGroup, TimeoutError)):
                await service.execute_run(initial.run.run_id)
        finally:
            release_transport.set()
        value = await repo.get_run_fresh(initial.run.run_id)
        assert value.run.status.value == "FAILED"
        assert not current_risk_success(value)
        if fault == "resistant":
            await asyncio.wait_for(transport_returned.wait(), 2)
            before_late = repo._payload(value)
            await asyncio.sleep(0.02)
            assert repo._payload(await repo.get_run_fresh(initial.run.run_id)) == before_late
        else:
            records = await service.recovery_evidence_store.records(value.run.run_id)
            records = [
                r for r in records if r.scope.operation_id == "risk-resume:" + scope.cycle_id
            ]
            assert any(r.reason_code == "RECOVERY_BUDGET_EXHAUSTED" for r in records)
            assert not any(
                r.kind == "ATTEMPT_COMPLETED" and r.outcome == "PASS" for r in records
            )
    else:
        if fault == "nonactive":
            monkeypatch.setattr(repo, "validate_execution", delay)
        else:
            progress = scope.progress

            def consumed_budget(identity):
                if len(injected) < 6:
                    offset[0] += 50
                    injected.append(identity)
                progress(identity)

            monkeypatch.setattr(scope, "progress", consumed_budget)
        with pytest.raises((TimeoutError, asyncio.CancelledError)):
            await service.execute_run(initial.run.run_id)
        value = await repo.get_run_fresh(initial.run.run_id)
        assert value.run.status.value == "FAILED"
        assert not current_risk_success(value)
        events = await service.event_store.replay(value.run.run_id)
        assert events[-1].type.value == "run.failed"
        assert events[-1].payload["failure_code"] == "RESULT_UNKNOWN"
    assert injected
    assert value.confirmed_risk_semantic_binding == initial.confirmed_risk_semantic_binding
    before_replay = repo._payload(value)
    calls = sum(c.calls for c in clients.values())
    assert await repo.resume_external_failure(request, actor=request.actor) == receipt
    assert repo._payload(await repo.get_run_fresh(value.run.run_id)) == before_replay
    assert sum(c.calls for c in clients.values()) == calls
    record_property("liveness", __import__("json").dumps(dict(
        run_id=scope.run_id, cycle_id=scope.cycle_id, O=scope.orchestration,
        max_N=scope.max_no_progress, trace=scope.trace,
    )))
    await backend.close()


async def test_union_deadlines_partial_balance_and_duplicate_progress():
    # Actual Confirm/reserve/enter creates the token used by the accounting unit
    # control. Provider integration is independently covered above.
    from src.domain.node_binding import canonical_value, task_semantics
    from tests.execution_profiles.test_confirmed_profiles import confirmed

    service, value = await confirmed()
    owner = await service.repository.claim_execution(value.run.run_id)
    task = value.runtime.actual_graph.tasks[0]
    admission = await service.repository.reserve_node(owner, task, {
        "task": task_semantics(task), "scheme": canonical_value(value.scheme),
    })
    await service.repository.dispatch_node(admission)
    await service.repository.enter_node_execution(admission)
    now = [0.0]
    scope = ResumeLiveness(value.run.run_id, "unit-accounting", clock=lambda: now[0])
    now[0] = 40
    a = scope.start(admission, "unit-a", 100, asyncio.current_task())
    now[0] = 80
    b = scope.start(admission, "unit-b", 120, asyncio.current_task())
    now[0] = 100
    scope.end(a)
    now[0] = 130
    scope.end(b)
    assert scope.orchestration == 50  # union [40,120], not sum of spans
    assert scope.no_progress == 10
    scope.progress(("commit", 1))
    now[0] = 150
    scope.progress(("commit", 1))
    assert scope.no_progress == 20
    assert scope.orchestration == 70
    for invalid in (float("inf"), float("nan"), 0, -1, 149):
        with pytest.raises(Exception, match="invalid bounded Resume span"):
            scope.start(admission, "invalid", invalid, asyncio.current_task())
    now[0] = 191
    with pytest.raises(TimeoutError, match="NO_PROGRESS"):
        scope.progress(("late_commit", 2))
    assert scope.no_progress == 61


async def test_committed_truth_ends_watchdog_without_renewing_db_budget():
    now = [0.0]
    scope = ResumeLiveness("run", "cycle", clock=lambda: now[0])
    now[0] = 50
    scope.progress(("commit", 1))
    scope.settling = True
    now[0] = 150
    scope.checkpoint()
    assert scope.orchestration == 150
    scope.settled()
    deadline = scope.deadline
    now[0] = 250
    scope.checkpoint()
    assert scope.remaining() == 50
    scope.settled()
    assert scope.deadline == deadline == 300
    now[0] = 301
    scope.checkpoint()  # terminal fact cannot be overwritten by liveness
    assert scope.remaining() == 0


async def test_commit_rollback_noop_and_cross_run_progress(tmp_path):
    from src.domain.node_binding import canonical_value, task_semantics
    from src.runtime.scheduler import liveness_progress
    from tests.wp02.test_node_binding import wired

    service, value, _, _ = await wired(tmp_path)
    now = [0.0]
    scope = ResumeLiveness(value.run.run_id, "commit-controls", clock=lambda: now[0])
    token = resume_liveness.set(scope)
    try:
        now[0] = 10
        with pytest.raises(RuntimeError, match="rollback"):
            async with service.repository._binding_transaction(value.run.run_id) as candidate:
                candidate.node_binding.lifecycle = "CLOSED"
                raise RuntimeError("rollback")
        scope.advance()
        assert scope.no_progress == 10 and not scope.seen
        async with service.repository._binding_transaction(value.run.run_id):
            pass
        assert scope.no_progress == 10 and not scope.seen
        liveness_progress("foreign-run", ("result", "foreign"))
        assert scope.no_progress == 10 and not scope.seen
        owner = await service.repository.claim_execution(value.run.run_id)
        assert scope.no_progress == 0
        now[0] = 20
        task = value.runtime.actual_graph.tasks[0]
        admission = await service.repository.reserve_node(owner, task, {
            "task": task_semantics(task), "scheme": canonical_value(value.scheme),
        })
        assert scope.no_progress == 0
        before = len(scope.seen)
        now[0] = 30
        await service.repository.get_run_fresh(value.run.run_id)
        scope.advance()
        assert scope.no_progress == 10 and len(scope.seen) == before
        await service.repository.dispatch_node(admission)
        assert scope.no_progress == 0
        now[0] = 40
        await service.repository.enter_node_execution(admission)
        assert scope.no_progress == 0
        identities = [row["identity"] for row in scope.trace if row["kind"] == "progress"]
        assert any(x[0] == "attempt" and x[-1] is True for x in identities)
        # Duplicate callbacks and revision-only updates cannot renew N or O.
        now[0] = 50
        for identity in identities:
            liveness_progress(value.run.run_id, identity)
        async with service.repository._binding_transaction(value.run.run_id):
            pass
        assert scope.no_progress == 10 and scope.orchestration == 50
    finally:
        resume_liveness.reset(token)


async def test_unmatched_events_do_not_grant_active_exemption():
    from src.runtime.events import InMemoryRuntimeEventStore, RuntimeEventType

    now = [0.0]
    scope = ResumeLiveness("run", "cycle", clock=lambda: now[0])
    store = InMemoryRuntimeEventStore()
    token = resume_liveness.set(scope)
    try:
        now[0] = 30
        await store.emit(run_id="run", event_type=RuntimeEventType.TASK_PROGRESS,
                         payload={"heartbeat": True, "state": "RUNNING",
                                  "kind": "ATTEMPT_STARTED"})
        scope.advance()
        assert scope.no_progress == 30 and not scope.spans
        now[0] = 61
        with pytest.raises(TimeoutError, match="NO_PROGRESS"):
            scope.checkpoint()
    finally:
        resume_liveness.reset(token)


async def test_real_resume_preflight_gap_and_same_cycle_clock(tmp_path, monkeypatch):
    from tests.external_failure_resume.runtime_fixture import legal_fixture

    service, initial, clients = await legal_fixture(tmp_path)
    failed = await exhaust(service, initial)
    request = await request_for(service, failed)
    await service.repository.resume_external_failure(request, actor=request.actor)
    scope = await service._resume_liveness_scope(initial.run.run_id)
    real = scope.clock
    offset = [0.0]
    scope.clock = lambda: real() + offset[0]
    offset[0] += 20
    assert await service._resume_liveness_scope(initial.run.run_id) is scope
    assert scope.orchestration >= 20
    repo = service.repository
    before = SQLAlchemyApplicationRepository._payload(await repo.get_run_fresh(initial.run.run_id))
    calls = sum(c.calls for c in clients.values())
    get = repo.get_run_fresh
    claims = []

    async def late_read(run_id):
        value = await get(run_id)
        offset[0] += 61
        return value

    async def forbidden_claim(*args, **kwargs):
        claims.append(True)
        pytest.fail("expired preflight must not claim or dispatch")

    monkeypatch.setattr(repo, "get_run_fresh", late_read)
    monkeypatch.setattr(repo, "claim_execution", forbidden_claim)
    with pytest.raises(TimeoutError, match="NO_PROGRESS"):
        await service.execute_run(initial.run.run_id)
    assert not claims
    assert SQLAlchemyApplicationRepository._payload(await get(initial.run.run_id)) == before
    assert sum(c.calls for c in clients.values()) == calls
    assert scope.expired == "RESUME_NO_PROGRESS_TIMEOUT"


@pytest.mark.asyncio
async def test_expired_reservation_return_cannot_dispatch(tmp_path, monkeypatch):
    from tests.external_failure_resume.runtime_fixture import legal_fixture

    service, initial, clients = await legal_fixture(tmp_path)
    failed = await exhaust(service, initial)
    request = await request_for(service, failed)
    await service.repository.resume_external_failure(request, actor=request.actor)
    for c in clients.values():
        c.fail_risk = False
    scope = await service._resume_liveness_scope(initial.run.run_id)
    real = scope.clock
    offset = [0.0]
    scope.clock = lambda: real() + offset[0]
    reserve = service.repository.reserve_node
    dispatch = service.repository.dispatch_node
    dispatched = []

    async def late(*args, **kwargs):
        value = await reserve(*args, **kwargs)
        offset[0] += 61
        return value

    async def spy(*args, **kwargs):
        dispatched.append(True)
        return await dispatch(*args, **kwargs)

    monkeypatch.setattr(service.repository, "reserve_node", late)
    monkeypatch.setattr(service.repository, "dispatch_node", spy)
    with pytest.raises((TimeoutError, ExceptionGroup)):
        await service.execute_run(initial.run.run_id)
    assert not dispatched, "expired reservation return dispatched new work"
    fresh = await service.repository.get_run_fresh(initial.run.run_id)
    assert fresh.run.status.value == "FAILED"
    assert (
        fresh.confirmed_risk_semantic_binding == initial.confirmed_risk_semantic_binding
    )
