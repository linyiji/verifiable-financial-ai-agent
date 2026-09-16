from __future__ import annotations

import asyncio
import copy
import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from acceptance.phase4.vs01.harness.backend import validate_run_collection
from apps.api.main import create_app
from src.application.errors import ApplicationError
from src.application.execution import IntegratedTaskExecutor
from src.application.persistence import ResearchRunAggregateRow, RuntimeEventRow, TaskRow
from src.domain.enums import ReplanDecision, RunStatus
from src.domain.node_binding import BindingDenied
from src.domain.runtime_event import RuntimeEventType, normalize_runtime_event_v1
from src.domain.task import ReplanRequest, Task
from src.infrastructure.config.settings import get_settings
from src.infrastructure.database.phase4_product import (
    Phase4ActualGraphRow,
    Phase4IdempotencyOutcomeRow,
    Phase4PlannedGraphRow,
    Phase4SchedulerAdmissionRow,
)
from src.phase4_product.contracts import AvailabilityStatus, AvailabilityV1
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from src.phase4_product.projections import (
    ProjectionIntegrityError,
    RunCollectionSource,
    project_run_collection_item,
)
from src.runtime.events import InMemoryRuntimeEventStore
from src.runtime.scheduler import DependencyScheduler

pytestmark = pytest.mark.skipif(
    "TEST_POSTGRESQL_URL" not in os.environ,
    reason="TEST_POSTGRESQL_URL is required for the focused PostgreSQL proof",
)


@pytest.fixture(autouse=True)
def configured_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_POSTGRESQL_URL"])
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _confirm_write_counts(backend, run_id: str) -> dict[str, int | bool]:
    async with backend.sessions() as session:
        planned = await session.scalar(
            select(Phase4PlannedGraphRow).where(Phase4PlannedGraphRow.run_id == run_id)
        )
        persisted_task_ids = set(
            (await session.scalars(select(TaskRow.task_id).where(TaskRow.run_id == run_id))).all()
        )
        planned_task_ids = (
            {item["task_id"] for item in planned.payload["tasks"]} if planned is not None else set()
        )

        async def count(model, *criteria) -> int:
            statement = select(func.count()).select_from(model)
            if criteria:
                statement = statement.where(*criteria)
            return int((await session.scalar(statement)) or 0)

        return {
            "runs": await count(ResearchRunAggregateRow, ResearchRunAggregateRow.run_id == run_id),
            "planned_graphs": await count(
                Phase4PlannedGraphRow, Phase4PlannedGraphRow.run_id == run_id
            ),
            "actual_graphs": await count(
                Phase4ActualGraphRow, Phase4ActualGraphRow.run_id == run_id
            ),
            "tasks": await count(TaskRow, TaskRow.run_id == run_id),
            "events": await count(RuntimeEventRow, RuntimeEventRow.run_id == run_id),
            "confirm_outcomes": await count(
                Phase4IdempotencyOutcomeRow,
                Phase4IdempotencyOutcomeRow.run_id == run_id,
                Phase4IdempotencyOutcomeRow.kind == "CONFIRM",
            ),
            "scheduler_admissions": await count(
                Phase4SchedulerAdmissionRow, Phase4SchedulerAdmissionRow.run_id == run_id
            ),
            "planned_task_set_closes": planned_task_ids == persisted_task_ids,
        }


async def _business_write_totals(backend) -> dict[str, int]:
    async with backend.sessions() as session:

        async def count(model, *criteria) -> int:
            statement = select(func.count()).select_from(model)
            if criteria:
                statement = statement.where(*criteria)
            return int((await session.scalar(statement)) or 0)

        async def run_set_count(model) -> int:
            return int((await session.scalar(select(func.count(func.distinct(model.run_id))))) or 0)

        scheduler_admissions = await count(Phase4SchedulerAdmissionRow)
        return {
            "runs": await count(ResearchRunAggregateRow),
            "planned_graphs": await count(Phase4PlannedGraphRow),
            "actual_graphs": await count(Phase4ActualGraphRow),
            "task_sets": await run_set_count(TaskRow),
            "initial_event_sets": await run_set_count(RuntimeEventRow),
            "confirm_outcomes": await count(
                Phase4IdempotencyOutcomeRow,
                Phase4IdempotencyOutcomeRow.kind == "CONFIRM",
            ),
            "scheduler_admissions": scheduler_admissions,
            "outbox_records": scheduler_admissions,
        }


def _confirm_body(draft: dict[str, object], object_id: str) -> dict[str, object]:
    return {
        "draft_id": draft["draft_id"],
        "draft_version": draft["draft_version"],
        "draft_hash": draft["draft_hash"],
        "research_object_id": object_id,
        "confirm_scheme": True,
    }


def test_confirm_persists_canonical_output_contracts_before_scheduler_start(monkeypatch) -> None:
    async def hold_scheduler(self):
        await asyncio.Event().wait()

    async def assert_canonical_rows(backend, run_id):
        async with backend.sessions() as session:
            planned = await session.scalar(
                select(Phase4PlannedGraphRow).where(Phase4PlannedGraphRow.run_id == run_id)
            )
            actual = await session.scalar(
                select(Phase4ActualGraphRow).where(Phase4ActualGraphRow.run_id == run_id)
            )
            rows = (await session.scalars(select(TaskRow).where(TaskRow.run_id == run_id))).all()
            expected = [
                Task.model_validate(t).model_dump(mode="json") for t in planned.payload["tasks"]
            ]
            observed = [
                Task.model_validate(t).model_dump(mode="json") for t in actual.payload["tasks"]
            ]
            assert len(expected) == len(observed) == len(rows) == 7
            assert observed == expected
            assert {row.task_id for row in rows} == {t["task_id"] for t in expected}
            by_id = {
                row.task_id: Task.model_validate(row.payload).model_dump(mode="json")
                for row in rows
            }
            assert [by_id[t["task_id"]] for t in expected] == expected
            assert all(t["run_id"] == run_id for t in expected)
            assert all(row.run_id == run_id for row in rows)
            for kind in ("valuation_analysis", "risk_analysis", "report_synthesis"):
                contract = next(
                    t["output_requirements"] for t in expected if t["task_type"] == kind
                )
                assert contract["hard_required"] == [
                    f"{run_id}:fundamentals/revenue_growth", f"{run_id}:fundamentals/ebitda_margin"
                ]
                assert contract["supporting"]

    monkeypatch.setattr(PostgreSQLPhase4ProductBackend, "_scheduler_loop", hold_scheduler)
    with TestClient(create_app()) as client:
        object_id = _create_object(client, symbol="AMD", key="canonical-object")
        draft = _prepare(client, object_id=object_id, key="canonical-prepare", goal="financial")
        response = client.post(
            "/api/research-runs",
            headers={
                "X-Phase4-Contract-Version": "phase4-core/v1",
                "Idempotency-Key": "canonical-confirm",
            },
            json=_confirm_body(draft, object_id),
        )
        assert response.status_code == 201, response.text
        run_id = response.json()["admission"]["run_id"]
        backend = client.app.state.phase4_product_backend
        client.portal.call(assert_canonical_rows, backend, run_id)
        counts = client.portal.call(_confirm_write_counts, backend, run_id)
        assert counts["runs"] == counts["confirm_outcomes"] == counts["scheduler_admissions"] == 1


def _validate_history_collection(body: dict[str, object], *, object_id: str) -> tuple[str, ...]:
    assert body["schema_version"] == "phase4-run-history-collection/v1"
    items = body["items"]
    assert isinstance(items, list)
    assert all(item["availability"] == "AVAILABLE" for item in items)
    return validate_run_collection(
        {
            "schema_version": "phase4-run-collection/v1",
            "items": [item["run"] for item in items],
            "next_cursor": body["next_cursor"],
        },
        expected_object_id=object_id,
    )


def _create_object(client: TestClient, *, symbol: str, key: str) -> str:
    response = client.post(
        "/api/objects",
        headers={
            "X-Phase4-Contract-Version": "phase4-core/v1",
            "Idempotency-Key": key,
        },
        json={
            "symbol": symbol,
            "company_name": f"{symbol} Corporation",
            "exchange": "NASDAQ",
            "currency": "USD",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["object"]["object_id"]


def _prepare(
    client: TestClient,
    *,
    object_id: str,
    key: str,
    goal: str,
) -> dict[str, object]:
    response = client.post(
        "/api/research-runs/prepare",
        headers={
            "X-Phase4-Contract-Version": "phase4-core/v1",
            "Idempotency-Key": key,
        },
        json={
            "research_object_id": object_id,
            "research_goal": goal,
            "as_of": "2026-09-05",
            "preferences": {},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _wait_until_started(client: TestClient, run_id: str) -> None:
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/api/research-runs/{run_id}", headers=headers)
        assert response.status_code == 200, response.text
        if response.json()["status"] == "RUNNING":
            return
        time.sleep(0.01)
    raise AssertionError("scheduler did not start the admitted Run")


@pytest.mark.parametrize("symbol", ["AMD", "MSFT"])
def test_default_composition_preserves_bound_fundamentals(monkeypatch, symbol) -> None:
    original_start = PostgreSQLPhase4ProductBackend.start

    async def checked_start(self):
        assert self.service.calculation_extensions == []
        await original_start(self)

    async def hold_scheduler(self):
        await asyncio.Event().wait()

    monkeypatch.setattr(PostgreSQLPhase4ProductBackend, "start", checked_start)
    monkeypatch.setattr(PostgreSQLPhase4ProductBackend, "_scheduler_loop", hold_scheduler)
    with TestClient(create_app()) as client:
        object_id = _create_object(client, symbol=symbol, key="composition-object")
        draft = _prepare(client, object_id=object_id, key="composition-prepare", goal="financial")
        response = client.post(
            "/api/research-runs",
            headers={
                "X-Phase4-Contract-Version": "phase4-core/v1",
                "Idempotency-Key": "composition-confirm",
            },
            json=_confirm_body(draft, object_id),
        )
        assert response.status_code == 201, response.text
        run_id = response.json()["admission"]["run_id"]
        service = client.app.state.research_service
        aggregate = client.portal.call(service.repository.get_run_fresh, run_id)
        before = copy.deepcopy(aggregate.__dict__)
        executor = IntegratedTaskExecutor(service, aggregate)
        task = next(
            task for task in aggregate.runtime.actual_graph.tasks
            if task.task_type == "fundamental_analysis"
        )
        assert aggregate.run.research_object_id == object_id
        assert task.run_id == run_id
        assert executor._handler_for(task).__name__ == "_execute_fundamental_analysis"
        assert executor.admission_requirements(task)["resolved_handler"] == (
            "_execute_fundamental_analysis"
        )
        assert aggregate.__dict__ == before
        service.calculation_extensions.append(object())
        with pytest.raises(BindingDenied, match="UNSUPPORTED_NEW_BOUND_HANDLER"):
            executor.admission_requirements(task)
        assert aggregate.__dict__ == before


def _concurrent_confirm(
    client: TestClient,
    *,
    requests: tuple[tuple[dict[str, str], dict[str, object]], ...],
):
    barrier = Barrier(len(requests) + 1)

    def send(headers: dict[str, str], body: dict[str, object]):
        barrier.wait(timeout=15)
        return client.post("/api/research-runs", headers=headers, json=body)

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        futures = [pool.submit(send, headers, body) for headers, body in requests]
        barrier.wait(timeout=15)
        return [future.result(timeout=30) for future in futures]


def test_confirm_admission_replay_and_immediate_run_collection_are_exactly_once() -> None:
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    confirm_headers = {**headers, "Idempotency-Key": "be004-confirm"}
    app = create_app()
    with TestClient(app) as client:
        app.state.phase4_product_backend._execute_started_run = _hold_started_run
        created = client.post(
            "/api/objects",
            headers={**headers, "Idempotency-Key": "be004-object"},
            json={
                "symbol": "QCOM",
                "company_name": "Qualcomm Incorporated",
                "exchange": "NASDAQ",
                "currency": "USD",
            },
        )
        assert created.status_code == 201, created.text
        object_id = created.json()["object"]["object_id"]
        prepared = client.post(
            "/api/research-runs/prepare",
            headers={**headers, "Idempotency-Key": "be004-prepare"},
            json={
                "research_object_id": object_id,
                "research_goal": "Produce a verifiable full-company research report.",
                "as_of": "2026-09-05",
                "preferences": {},
            },
        )
        assert prepared.status_code == 201, prepared.text
        draft = prepared.json()
        body = _confirm_body(draft, object_id)

        confirmed = client.post("/api/research-runs", headers=confirm_headers, json=body)
        assert confirmed.status_code == 201, confirmed.text
        admission = confirmed.json()["admission"]
        run_id = admission["run_id"]

        immediate_runs = client.get(f"/api/objects/{object_id}/runs", headers=headers)
        assert immediate_runs.status_code == 200, immediate_runs.text
        assert [item["run"]["run_id"] for item in immediate_runs.json()["items"]] == [run_id]

        replayed = client.post("/api/research-runs", headers=confirm_headers, json=body)
        assert replayed.status_code == 200, replayed.text
        assert replayed.json()["admission"] == admission
        assert replayed.json()["response_meta"]["idempotency_replayed"] is True

        changed_body = {**body, "research_object_id": f"{object_id}-changed"}
        changed_hash = client.post("/api/research-runs", headers=confirm_headers, json=changed_body)
        assert changed_hash.status_code == 409, changed_hash.text
        assert changed_hash.json()["error"]["details"]["reason_code"] == (
            "IDEMPOTENCY_REQUEST_MISMATCH"
        )

        consumed_draft = client.post(
            "/api/research-runs",
            headers={**headers, "Idempotency-Key": "be004-confirm-consumed"},
            json=body,
        )
        assert consumed_draft.status_code == 409, consumed_draft.text
        assert consumed_draft.json()["error"]["details"]["reason_code"] == "DRAFT_CONSUMED"

        counts = client.portal.call(
            _confirm_write_counts,
            app.state.phase4_product_backend,
            run_id,
        )
        assert counts["runs"] == 1
        assert counts["planned_graphs"] == 1
        assert counts["actual_graphs"] == 1
        assert counts["tasks"] > 0
        assert counts["events"] >= 4 + counts["tasks"]
        assert counts["confirm_outcomes"] == 1
        assert counts["scheduler_admissions"] == 1
        assert counts["planned_task_set_closes"] is True

    reopened = create_app()
    with TestClient(reopened) as client:
        restart_replay = client.post("/api/research-runs", headers=confirm_headers, json=body)
        assert restart_replay.status_code == 200, restart_replay.text
        assert restart_replay.json()["admission"] == admission
        assert restart_replay.json()["response_meta"]["idempotency_replayed"] is True

        restart_counts = client.portal.call(
            _confirm_write_counts, reopened.state.phase4_product_backend, run_id
        )
        for name in (
            "runs",
            "planned_graphs",
            "actual_graphs",
            "tasks",
            "confirm_outcomes",
            "scheduler_admissions",
        ):
            assert restart_counts[name] == counts[name]
        _wait_until_started(client, run_id)
        client.portal.call(_emit_scheduler_failure, reopened.state.phase4_product_backend, run_id)


async def _hold_started_run(run_id: str, *, execution_owner=None) -> None:
    await asyncio.Event().wait()


async def _emit_scheduler_failure(backend, run_id: str) -> None:
    await backend.service.event_store.emit(
        run_id=run_id,
        event_type=RuntimeEventType.RUN_FAILED,
        payload={
            "status": "FAILED",
            "failure_stage": "TASK_EXECUTION",
            "failure_code": "TASK_EXECUTION_FAILED",
        },
    )


class _TerminalFailureHarness:
    """Resume the admitted production invocation with a controlled preflight fault."""

    def __init__(self, backend):
        self.backend = backend
        self.pending = asyncio.Queue()

    async def execute(self, run_id: str, *, execution_owner=None) -> None:
        loop = asyncio.get_running_loop()
        resume, finished = loop.create_future(), loop.create_future()
        self.pending.put_nowait((run_id, resume, finished))
        scenario = await resume

        def fail_preflight(executor, task):
            raise ApplicationError("TASK_EXECUTION_FAILED", "Controlled terminal fixture fault")

        async def fail_task(executor, task):
            if scenario == "cancellation":
                raise asyncio.CancelledError
            raise ApplicationError("TASK_EXECUTION_FAILED", "Controlled task execution fault")

        original_emit = self.backend.service.event_store.emit

        async def observe_committed_terminal(**kwargs):
            if kwargs["event_type"] is RuntimeEventType.RUN_FAILED:
                committed = await self.backend.service.repository.get_run_fresh(run_id)
                assert committed.run.status is committed.runtime.run_status is RunStatus.FAILED
                assert committed.run.completed_at is not None
                assert kwargs["timestamp"] == committed.run.completed_at
                assert committed.run.updated_at == committed.run.completed_at
                assert committed.node_binding.lifecycle == "RESULT_UNKNOWN"
                assert committed.node_binding.owner_generation == (
                    execution_owner.owner_generation + 1
                )
                business_facts = self.backend.service.repository._payload(committed)
                event = await original_emit(**kwargs)
                published = await self.backend.service.repository.get_run_fresh(run_id)
                assert self.backend.service.repository._payload(published) == business_facts
                return event
            return await original_emit(**kwargs)

        try:
            assert execution_owner is not None
            with pytest.MonkeyPatch.context() as patch:
                if scenario == "preflight":
                    patch.setattr(IntegratedTaskExecutor, "admission_requirements", fail_preflight)
                else:
                    # Use the supported native bound-handler composition for task admission.
                    patch.setattr(self.backend.service, "calculation_extensions", [])
                    patch.setattr(IntegratedTaskExecutor, "_execute_instrumented_task", fail_task)
                patch.setattr(self.backend.service.event_store, "emit", observe_committed_terminal)
                expected = {
                    "preflight": ApplicationError,
                    "task": ExceptionGroup,
                    "cancellation": asyncio.CancelledError,
                }[scenario]
                with pytest.raises(expected) as failure:
                    await self.backend.service.execute_run(
                        run_id, emit_run_started=False, execution_owner=execution_owner
                    )
                if scenario == "preflight":
                    assert failure.value.code == "TASK_EXECUTION_FAILED"
            finished.set_result(execution_owner)
        except BaseException as exc:
            finished.set_exception(exc)

    async def fail(self, run_id: str, scenario: str = "preflight"):
        admitted_run, resume, finished = await self.pending.get()
        assert admitted_run == run_id
        before = await self.backend.service.repository.get_run_fresh(run_id)
        assert before.run.status is RunStatus.RUNNING
        assert before.node_binding.lifecycle == "ACTIVE"
        resume.set_result(scenario)
        owner = await finished
        snapshot = await _assert_durable_terminal(self.backend, run_id)
        assert snapshot["owner_generation"] == owner.owner_generation + 1
        with pytest.raises(BindingDenied) as stale:
            await self.backend.service.repository.validate_execution(owner)
        assert stale.value.code == "STALE_WRITE_REJECTED"
        with pytest.raises(BindingDenied):
            await self.backend.service.execute_run(
                run_id, emit_run_started=False, execution_owner=owner
            )
        assert await _assert_durable_terminal(self.backend, run_id) == snapshot
        async with self.backend._confirm_uow_factory() as uow:
            assert await uow.admission.get_active_run_id_for_update(
                self.backend._run_admission_scope
            ) is None
        return snapshot


async def _assert_durable_terminal(backend, run_id: str):
    """Read committed rows independently of the service's aggregate cache."""
    async with backend.sessions() as session:
        row = await session.get(ResearchRunAggregateRow, run_id)
        assert row.status == row.payload["run"]["status"] == "FAILED"
        assert row.payload["runtime"]["run_status"] == "FAILED"
        assert row.payload["run"]["started_at"] is not None
        assert row.payload["run"]["completed_at"] is not None
        root = row.payload["node_binding"]
        assert root["lifecycle"] == "RESULT_UNKNOWN"
        events = list((await session.scalars(
            select(RuntimeEventRow).where(RuntimeEventRow.run_id == run_id)
            .order_by(RuntimeEventRow.sequence)
        )).all())
        failed = [event for event in events if event.payload["type"] == "run.failed"]
        assert len(failed) == 1
        assert failed[0].payload["timestamp"] == row.payload["run"]["completed_at"]
        assert row.payload["run"]["updated_at"] == row.payload["run"]["completed_at"]
        assert [event.sequence for event in events] == list(range(1, len(events) + 1))
        assert failed[0].sequence == events[-1].sequence == row.projection_sequence
        snapshot = {
            "run": row.payload["run"],
            "owner_generation": root["owner_generation"],
            "projection_sequence": row.projection_sequence,
            "terminal_event": failed[0].payload,
            "events": [event.payload for event in events],
        }
    replay = await backend.service.event_store.replay(run_id)
    assert [event.model_dump(mode="json") for event in replay] == snapshot["events"]
    resumed = await backend.service.event_store.replay(run_id, after_sequence=1)
    assert [event.model_dump(mode="json") for event in resumed] == snapshot["events"][1:]
    assert [event.model_dump(mode="json") for event in replay
            if event.type is RuntimeEventType.RUN_FAILED] == [snapshot["terminal_event"]]
    await _assert_terminal_reader_contract(backend, run_id, replay[-1])
    return snapshot


async def _assert_terminal_reader_contract(backend, run_id, terminal_event):
    aggregate = await backend.service.repository.get_run_fresh(run_id)
    research_object = await backend.service.get_object(aggregate.run.research_object_id)
    source = RunCollectionSource(
        run=aggregate.run,
        research_object=research_object,
        actual_graph=aggregate.runtime.actual_graph,
        latest_event=normalize_runtime_event_v1(terminal_event),
        projection_revision=1,
        projection_sequence=terminal_event.sequence,
        result_availability=AvailabilityV1.unavailable(
            AvailabilityStatus.FAILED, "RUN_TERMINAL_WITHOUT_RELEASE"
        ),
    )
    assert project_run_collection_item(source).status == "FAILED"
    # A later occurrence is still invalid. Only a detached reader input is changed.
    newer_event = terminal_event.model_copy(update={"timestamp": datetime.now(UTC)})
    assert newer_event.timestamp > aggregate.run.updated_at
    with pytest.raises(ProjectionIntegrityError, match="newer than durable updated_at"):
        project_run_collection_item(replace(
            source, latest_event=normalize_runtime_event_v1(newer_event)
        ))

    # CANCELLED has no durable bound route today. Exercise its existing lifecycle
    # and reader contract on a detached value, without saving or publishing it.
    cancelled = copy.deepcopy(aggregate)
    terminal_at = datetime.now(UTC)
    backend.service._apply_terminal_lifecycle(
        cancelled, status=RunStatus.CANCELLED, terminal_at=terminal_at
    )
    events = InMemoryRuntimeEventStore()
    event = await events.emit(
        run_id=run_id,
        event_type=RuntimeEventType.RUN_FAILED,
        payload={
            "status": "CANCELLED",
            "failure_stage": "CANCELLATION",
            "failure_code": "RUN_CANCELLED",
        },
        timestamp=terminal_at,
    )
    assert cancelled.run.completed_at == cancelled.run.updated_at == event.timestamp
    item = project_run_collection_item(replace(
        source, run=cancelled.run, latest_event=normalize_runtime_event_v1(event),
        projection_sequence=event.sequence,
    ))
    assert item.status == "CANCELLED"
    assert item.result_availability.status is AvailabilityStatus.FAILED


async def _emit_pending_replan(backend, run_id: str, task_id: str, replan_id: str):
    return await backend.service.event_store.emit(
        run_id=run_id,
        task_id=task_id,
        event_type=RuntimeEventType.REPLAN_REQUESTED,
        payload={"replan_id": replan_id, "decision": ReplanDecision.PENDING.value},
    )


async def _replay_after(backend, run_id: str, sequence: int):
    return await backend.service.event_store.replay(run_id, after_sequence=sequence)


def test_terminal_scheduler_event_and_run_watermark_are_http_atomic_across_restart() -> None:
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    confirm_headers = {**headers, "Idempotency-Key": "be004-terminal-confirm"}
    app = create_app()
    with TestClient(app) as client:
        backend = app.state.phase4_product_backend
        terminal = _TerminalFailureHarness(backend)
        backend._execute_started_run = terminal.execute
        created = client.post(
            "/api/objects",
            headers={**headers, "Idempotency-Key": "be004-terminal-object"},
            json={
                "symbol": "AAPL",
                "company_name": "Apple Inc.",
                "exchange": "NASDAQ",
                "currency": "USD",
            },
        )
        assert created.status_code == 201, created.text
        object_id = created.json()["object"]["object_id"]
        prepared = client.post(
            "/api/research-runs/prepare",
            headers={**headers, "Idempotency-Key": "be004-terminal-prepare"},
            json={
                "research_object_id": object_id,
                "research_goal": "Produce a verifiable full-company research report.",
                "as_of": "2026-09-05",
                "preferences": {},
            },
        )
        assert prepared.status_code == 201, prepared.text
        body = _confirm_body(prepared.json(), object_id)
        confirmed = client.post("/api/research-runs", headers=confirm_headers, json=body)
        assert confirmed.status_code == 201, confirmed.text
        admission = confirmed.json()["admission"]
        run_id = admission["run_id"]

        for _ in range(100):
            run = client.get(f"/api/research-runs/{run_id}", headers=headers)
            assert run.status_code == 200, run.text
            if run.json()["status"] == "RUNNING":
                break
        assert run.json()["status"] == "RUNNING"

        replayed = client.post("/api/research-runs", headers=confirm_headers, json=body)
        assert replayed.status_code == 200, replayed.text
        assert replayed.json()["admission"] == admission

        terminal_snapshot = client.portal.call(terminal.fail, run_id)
        object_runs = client.get(f"/api/objects/{object_id}/runs", headers=headers)
        assert object_runs.status_code == 200, object_runs.text
        assert _validate_history_collection(object_runs.json(), object_id=object_id) == (
            run_id,
        )
        item = object_runs.json()["items"][0]["run"]
        global_runs = client.get("/api/research-runs", headers=headers)
        assert global_runs.status_code == 200, global_runs.text
        assert next(entry for entry in global_runs.json()["items"]
                    if entry["run"]["run_id"] == run_id) == object_runs.json()["items"][0]
        assert (item["status"], item["stage"], item["terminal"]) == (
            "FAILED",
            "FAILED",
            True,
        )
        assert item["activity"]["type"] == "run.failed"
        assert item["result_availability"] == {
            "status": "FAILED",
            "reason_code": "RUN_TERMINAL_WITHOUT_RELEASE",
            "retryable": False,
        }
        projection = client.get(f"/api/research-runs/{run_id}/projection", headers=headers)
        assert projection.status_code == 200, projection.text
        assert projection.json()["projection_sequence"] == terminal_snapshot["projection_sequence"]
        assert projection.json()["lifecycle"]["safe_failure"] == {
            "status": "FAILED",
            "failure_stage": "TASK_EXECUTION",
            "failure_code": "TASK_EXECUTION_FAILED",
            "safe_message": None,
        }

    reopened = create_app()
    with TestClient(reopened) as client:
        assert client.portal.call(
            _assert_durable_terminal, reopened.state.phase4_product_backend, run_id
        ) == terminal_snapshot
        restart_replay = client.post("/api/research-runs", headers=confirm_headers, json=body)
        assert restart_replay.status_code == 200, restart_replay.text
        assert restart_replay.json()["admission"] == admission
        object_runs = client.get(f"/api/objects/{object_id}/runs", headers=headers)
        assert object_runs.status_code == 200, object_runs.text
        assert _validate_history_collection(object_runs.json(), object_id=object_id) == (
            run_id,
        )
        projection = client.get(f"/api/research-runs/{run_id}/projection", headers=headers)
        assert projection.status_code == 200, projection.text
        assert projection.json()["lifecycle"]["safe_failure"]["safe_message"] is None
        assert projection.json()["projection_sequence"] == terminal_snapshot["projection_sequence"]
        assert object_runs.json()["items"][0]["run"] == item


def test_production_execution_preserves_scheduler_start_during_event_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    event_staged = Event()
    allow_watermark = asyncio.Event()

    async def publish_one_task_event_then_hold(
        scheduler,
        *,
        state,
        executor,
        emit_run_started: bool = True,
        on_execution_admitted=None,
    ) -> None:
        del executor, emit_run_started, on_execution_admitted
        state.run_status = RunStatus.RUNNING
        task = state.actual_graph.tasks[0]
        await scheduler._event_store.emit(
            run_id=state.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.TASK_READY,
        )
        await asyncio.Event().wait()

    monkeypatch.setattr(DependencyScheduler, "execute", publish_one_task_event_then_hold)
    app = create_app()
    with TestClient(app) as client:
        backend = app.state.phase4_product_backend
        repository = backend.service.repository
        original_publish = repository.save_run_with_projection_watermark
        blocked_once = False

        async def publish_after_barrier(
            aggregate, *, projection_sequence: int, expected_binding_ref=None
        ) -> None:
            nonlocal blocked_once
            if not blocked_once:
                blocked_once = True
                event_staged.set()
                await allow_watermark.wait()
            await original_publish(
                aggregate,
                projection_sequence=projection_sequence,
                expected_binding_ref=expected_binding_ref,
            )

        repository.save_run_with_projection_watermark = publish_after_barrier
        object_id = _create_object(client, symbol="ORCL", key="start-owner-object")
        draft = _prepare(
            client,
            object_id=object_id,
            key="start-owner-prepare",
            goal="Verify one authoritative scheduler start timestamp.",
        )
        confirmed = client.post(
            "/api/research-runs",
            headers={**headers, "Idempotency-Key": "start-owner-confirm"},
            json=_confirm_body(draft, object_id),
        )
        assert confirmed.status_code == 201, confirmed.text
        run_id = confirmed.json()["admission"]["run_id"]
        assert event_staged.wait(timeout=10), "event was not staged before publication"

        object_runs = client.get(f"/api/objects/{object_id}/runs", headers=headers)
        assert object_runs.status_code == 200, object_runs.text
        assert _validate_history_collection(object_runs.json(), object_id=object_id) == (
            run_id,
        )
        item = object_runs.json()["items"][0]["run"]
        assert item["activity"]["type"] == "run.started"
        assert item["started_at"] == item["activity"]["timestamp"]
        client.portal.call(allow_watermark.set)


def test_replan_requested_projection_and_replay_publish_at_one_public_watermark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import uuid4

    from src.domain.node_binding import BindingDenied, GraphIdentity
    from src.infrastructure.database.phase4_product import SQLAlchemyPhase4ProjectionRepository
    from src.runtime.graph import GraphMutationActor, GraphMutationRole, GraphMutationService

    def durable_projection(response):
        value = response.json()
        # Response-generation time is not a persisted projection fact.
        assert value.pop("generated_at")
        return value

    headers = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    publication_entered = Event()
    allow_start = asyncio.Event()
    allow_publication = asyncio.Event()
    original_scheduler = PostgreSQLPhase4ProductBackend._scheduler_loop

    async def scheduler_after_baseline(self):
        await allow_start.wait()
        await original_scheduler(self)

    monkeypatch.setattr(PostgreSQLPhase4ProductBackend, "_scheduler_loop", scheduler_after_baseline)
    monkeypatch.setattr(PostgreSQLPhase4ProductBackend, "_execute_started_run", _hold_execution)
    app = create_app()
    with TestClient(app) as client:
        backend = app.state.phase4_product_backend
        object_id = _create_object(client, symbol="INTC", key="replan-watermark-object")
        draft = _prepare(
            client,
            object_id=object_id,
            key="replan-watermark-prepare",
            goal="Verify fixed-graph policy and atomic supported-event publication.",
        )
        confirmed = client.post(
            "/api/research-runs",
            headers={**headers, "Idempotency-Key": "replan-watermark-confirm"},
            json=_confirm_body(draft, object_id),
        )
        assert confirmed.status_code == 201, confirmed.text
        run_id = confirmed.json()["admission"]["run_id"]
        repository = backend.service.repository
        initial = client.portal.call(repository.get_run_fresh, run_id)
        assert initial is not None and initial.node_binding is not None
        fixed_graph = GraphIdentity.of(initial.runtime.actual_graph)
        assert initial.node_binding.frozen_graph == fixed_graph
        initial_graph = initial.runtime.actual_graph.model_dump(mode="json")
        assert initial.artifacts.replans == []

        baseline = client.get(f"/api/research-runs/{run_id}/projection", headers=headers)
        assert baseline.status_code == 200, baseline.text
        baseline_projection = durable_projection(baseline)
        baseline_sequence = baseline_projection["projection_sequence"]
        baseline_revision = baseline_projection["projection_revision"]
        assert baseline_projection["path_changes"] == []

        # Observe the real scheduler's transaction after staging, before commit.
        # No Replan event is manufactured: this bound path does not emit one.
        original_publish = SQLAlchemyPhase4ProjectionRepository.publish

        async def publish_after_barrier(self, write_set):
            watermark = await original_publish(self, write_set)
            publication_entered.set()
            await allow_publication.wait()
            return watermark

        monkeypatch.setattr(
            SQLAlchemyPhase4ProjectionRepository, "publish", publish_after_barrier
        )
        client.portal.call(allow_start.set)
        assert publication_entered.wait(timeout=10), "scheduler publication was not staged"

        def read_projections():
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = [
                    future.result(timeout=10)
                    for future in (
                        pool.submit(
                            client.get, f"/api/research-runs/{run_id}/projection", headers=headers
                        ),
                        pool.submit(
                            client.get, f"/api/research-runs/{run_id}/projection", headers=headers
                        ),
                    )
                ]
            assert all(response.status_code == 200 for response in responses)
            return [durable_projection(response) for response in responses]

        try:
            before = read_projections()
            assert all(value == baseline_projection for value in before)
            assert client.portal.call(_replay_after, backend, run_id, baseline_sequence) == []
        finally:
            client.portal.call(allow_publication.set)
        _wait_until_started(client, run_id)
        monkeypatch.setattr(SQLAlchemyPhase4ProjectionRepository, "publish", original_publish)

        after = read_projections()
        assert after[0] == after[1]
        expected_projection = after[0]
        assert expected_projection["projection_sequence"] == baseline_sequence + 1
        assert expected_projection["projection_revision"] == baseline_revision + 1
        assert expected_projection["graph_version"] == baseline_projection["graph_version"]
        assert expected_projection["run"]["run_id"] == run_id
        assert expected_projection["run"]["status"] == "RUNNING"
        assert expected_projection["path_changes"] == []
        replay = client.portal.call(_replay_after, backend, run_id, baseline_sequence)
        assert [(event.type, event.sequence) for event in replay] == [
            (RuntimeEventType.RUN_STARTED, expected_projection["projection_sequence"])
        ]
        expected_events = [event.model_dump(mode="json") for event in replay]

        async def assert_fixed_graph_and_deny_mutation():
            current = await repository.get_run_fresh(run_id)
            assert current is not None and current.node_binding is not None
            assert current.run.status is RunStatus.RUNNING
            assert current.node_binding.lifecycle == "ACTIVE"
            assert current.node_binding.frozen_graph == fixed_graph
            assert GraphIdentity.of(current.runtime.actual_graph) == fixed_graph
            assert current.runtime.actual_graph.model_dump(mode="json") == initial_graph
            assert current.artifacts.replans == []
            task = current.runtime.actual_graph.tasks[0]
            mutation = GraphMutationService(backend.service.event_store, repository=repository)
            # An attempted request is only an input value, never appended or saved.
            # Even a Lead-approved request cannot mutate a bound fixed graph.
            for role in (GraphMutationRole.RESEARCH_LEAD, GraphMutationRole.PLANNER):
                actor = GraphMutationActor(actor_id=role.value, role=role)
                request = ReplanRequest(
                    replan_id=f"REPLAN-{uuid4()}",
                    run_id=run_id,
                    requesting_task_id=task.task_id,
                    requested_by=task.assigned_agent,
                    reason_code="FIXED_GRAPH_FOLLOW_UP",
                    reason_detail="Attempt a follow-up through the graph mutation authority.",
                    proposed_graph_change={"operation": "add_task"},
                    decision=ReplanDecision.APPROVED,
                    decided_by=actor.actor_id,
                )
                child = task.model_copy(update={"task_id": f"{run_id}:{uuid4()}"}, deep=True)
                with pytest.raises(BindingDenied) as denied:
                    await mutation.add_node(
                        state=current.runtime, request=request, task=child, actor=actor
                    )
                assert denied.value.code == "POLICY_DENIED"
                assert denied.value.subject == "fixed initial graph mutation excluded"
                assert current.runtime.actual_graph.model_dump(mode="json") == initial_graph
                assert current.artifacts.replans == []
            fresh = await repository.get_run_fresh(run_id)
            assert fresh.node_binding.frozen_graph == fixed_graph
            assert fresh.runtime.actual_graph.model_dump(mode="json") == initial_graph
            assert fresh.artifacts.replans == []

        client.portal.call(assert_fixed_graph_and_deny_mutation)
        assert all(value == expected_projection for value in read_projections())
        all_events = client.portal.call(_replay_after, backend, run_id, 0)
        assert all(event.type is not RuntimeEventType.REPLAN_REQUESTED for event in all_events)
        assert [event.model_dump(mode="json") for event in all_events if
                event.sequence > baseline_sequence] == expected_events

    reopened = create_app()
    with TestClient(reopened) as client:
        backend = reopened.state.phase4_product_backend
        projection = client.get(f"/api/research-runs/{run_id}/projection", headers=headers)
        assert projection.status_code == 200, projection.text
        assert durable_projection(projection) == expected_projection
        fresh = client.portal.call(backend.service.repository.get_run_fresh, run_id)
        assert fresh.node_binding.frozen_graph == fixed_graph
        assert GraphIdentity.of(fresh.runtime.actual_graph) == fixed_graph
        assert fresh.runtime.actual_graph.model_dump(mode="json") == initial_graph
        assert fresh.artifacts.replans == []
        replay = client.portal.call(_replay_after, backend, run_id, 0)
        assert [event.model_dump(mode="json") for event in replay] == [
            event.model_dump(mode="json") for event in all_events
        ]


async def _hold_execution(self, run_id: str, *, execution_owner=None) -> None:
    await asyncio.Event().wait()


@pytest.mark.parametrize(
    ("request_count", "symbol"),
    ((2, "AMD"), (4, "GOOG")),
)
def test_concurrent_identical_confirm_has_one_creator_and_only_durable_replays(
    request_count: int,
    symbol: str,
) -> None:
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    app = create_app()
    with TestClient(app) as client:
        backend = app.state.phase4_product_backend
        backend._execute_started_run = _hold_started_run
        object_id = _create_object(client, symbol=symbol, key=f"{symbol}-object")
        draft = _prepare(
            client,
            object_id=object_id,
            key=f"{symbol}-prepare",
            goal=f"Produce a verifiable research report for {symbol}.",
        )
        body = _confirm_body(draft, object_id)
        confirm_headers = {**headers, "Idempotency-Key": f"{symbol}-confirm"}
        responses = _concurrent_confirm(
            client,
            requests=tuple((confirm_headers, body) for _ in range(request_count)),
        )

        assert sorted(response.status_code for response in responses) == [
            *([200] * (request_count - 1)),
            201,
        ]
        admissions = [response.json()["admission"] for response in responses]
        assert all(admission == admissions[0] for admission in admissions)
        assert sorted(
            response.json()["response_meta"]["idempotency_replayed"] for response in responses
        ) == [False, *([True] * (request_count - 1))]
        run_id = admissions[0]["run_id"]
        counts = client.portal.call(_confirm_write_counts, backend, run_id)
        assert counts["runs"] == 1
        assert counts["planned_graphs"] == 1
        assert counts["actual_graphs"] == 1
        assert counts["tasks"] > 0
        assert counts["events"] in {4 + counts["tasks"], 5 + counts["tasks"]}
        assert counts["confirm_outcomes"] == 1
        assert counts["scheduler_admissions"] == 1
        assert counts["planned_task_set_closes"] is True

        _wait_until_started(client, run_id)
        client.portal.call(_emit_scheduler_failure, backend, run_id)


def test_active_run_rejects_new_confirm_without_mutation_and_terminal_releases_slot() -> None:
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    app = create_app()
    with TestClient(app) as client:
        backend = app.state.phase4_product_backend
        terminal = _TerminalFailureHarness(backend)
        backend._execute_started_run = terminal.execute
        object_id = _create_object(client, symbol="META", key="meta-object")
        draft_a = _prepare(
            client,
            object_id=object_id,
            key="meta-prepare-a",
            goal="Produce the first verifiable META research report.",
        )
        draft_b = _prepare(
            client,
            object_id=object_id,
            key="meta-prepare-b",
            goal="Produce the second verifiable META research report.",
        )
        first = client.post(
            "/api/research-runs",
            headers={**headers, "Idempotency-Key": "meta-confirm-a"},
            json=_confirm_body(draft_a, object_id),
        )
        assert first.status_code == 201, first.text
        run_a = first.json()["admission"]["run_id"]
        before = client.portal.call(_business_write_totals, backend)

        rejected = client.post(
            "/api/research-runs",
            headers={**headers, "Idempotency-Key": "meta-confirm-b"},
            json=_confirm_body(draft_b, object_id),
        )
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["error"]["code"] == "CONFLICT"
        assert rejected.json()["error"]["details"] == {"reason_code": "RUN_ALREADY_ACTIVE"}
        assert rejected.json()["error"]["resource"] == {
            "type": "research_run",
            "id": run_a,
        }
        assert client.portal.call(_business_write_totals, backend) == before

        _wait_until_started(client, run_a)
        snapshot_a = client.portal.call(terminal.fail, run_a, "task")
        admitted_b = client.post(
            "/api/research-runs",
            headers={**headers, "Idempotency-Key": "meta-confirm-b"},
            json=_confirm_body(draft_b, object_id),
        )
        assert admitted_b.status_code == 201, admitted_b.text
        run_b = admitted_b.json()["admission"]["run_id"]
        assert run_b != run_a
        _wait_until_started(client, run_b)
        snapshot_b = client.portal.call(terminal.fail, run_b, "cancellation")

    with TestClient(create_app()) as client:
        backend = client.app.state.phase4_product_backend
        assert client.portal.call(_assert_durable_terminal, backend, run_a) == snapshot_a
        assert client.portal.call(_assert_durable_terminal, backend, run_b) == snapshot_b
        history = client.get(f"/api/objects/{object_id}/runs", headers=headers)
        assert history.status_code == 200, history.text
        assert set(_validate_history_collection(history.json(), object_id=object_id)) == {
            run_a, run_b,
        }


def test_concurrent_different_confirms_admit_exactly_one_active_run() -> None:
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    app = create_app()
    with TestClient(app) as client:
        backend = app.state.phase4_product_backend
        backend._execute_started_run = _hold_started_run
        object_id = _create_object(client, symbol="INTC", key="intc-object")
        draft_a = _prepare(
            client,
            object_id=object_id,
            key="intc-prepare-a",
            goal="Produce the first verifiable INTC research report.",
        )
        draft_b = _prepare(
            client,
            object_id=object_id,
            key="intc-prepare-b",
            goal="Produce the second verifiable INTC research report.",
        )
        before = client.portal.call(_business_write_totals, backend)
        responses = _concurrent_confirm(
            client,
            requests=(
                (
                    {**headers, "Idempotency-Key": "intc-confirm-a"},
                    _confirm_body(draft_a, object_id),
                ),
                (
                    {**headers, "Idempotency-Key": "intc-confirm-b"},
                    _confirm_body(draft_b, object_id),
                ),
            ),
        )
        assert sorted(response.status_code for response in responses) == [201, 409]
        winner = next(response for response in responses if response.status_code == 201)
        rejected = next(response for response in responses if response.status_code == 409)
        run_id = winner.json()["admission"]["run_id"]
        assert rejected.json()["error"]["details"] == {"reason_code": "RUN_ALREADY_ACTIVE"}
        assert rejected.json()["error"]["resource"]["id"] == run_id
        after = client.portal.call(_business_write_totals, backend)
        assert {name: after[name] - before[name] for name in after} == {name: 1 for name in after}

        _wait_until_started(client, run_id)
        client.portal.call(_emit_scheduler_failure, backend, run_id)
