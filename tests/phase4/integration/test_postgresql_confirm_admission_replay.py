from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from acceptance.phase4.vs01.harness.backend import validate_run_collection
from apps.api.main import create_app
from src.application.persistence import ResearchRunAggregateRow, RuntimeEventRow, TaskRow
from src.domain.runtime_event import RuntimeEventType
from src.infrastructure.config.settings import get_settings
from src.infrastructure.database.phase4_product import (
    Phase4ActualGraphRow,
    Phase4IdempotencyOutcomeRow,
    Phase4PlannedGraphRow,
    Phase4SchedulerAdmissionRow,
)

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


def _confirm_body(draft: dict[str, object], object_id: str) -> dict[str, object]:
    return {
        "draft_id": draft["draft_id"],
        "draft_version": draft["draft_version"],
        "draft_hash": draft["draft_hash"],
        "research_object_id": object_id,
        "confirm_scheme": True,
    }


def test_confirm_admission_replay_and_immediate_run_collection_are_exactly_once() -> None:
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    confirm_headers = {**headers, "Idempotency-Key": "be004-confirm"}
    app = create_app()
    with TestClient(app) as client:
        created = client.post(
            "/api/objects",
            headers={**headers, "Idempotency-Key": "be004-object"},
            json={
                "symbol": "NVDA",
                "company_name": "NVIDIA Corporation",
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
        assert [item["run_id"] for item in immediate_runs.json()["items"]] == [run_id]

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


async def _hold_started_run(_run_id: str) -> None:
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


def test_terminal_scheduler_event_and_run_watermark_are_http_atomic_across_restart() -> None:
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    confirm_headers = {**headers, "Idempotency-Key": "be004-terminal-confirm"}
    app = create_app()
    with TestClient(app) as client:
        backend = app.state.phase4_product_backend
        backend._execute_started_run = _hold_started_run
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

        client.portal.call(_emit_scheduler_failure, backend, run_id)
        object_runs = client.get(f"/api/objects/{object_id}/runs", headers=headers)
        assert object_runs.status_code == 200, object_runs.text
        assert validate_run_collection(object_runs.json(), expected_object_id=object_id) == (
            run_id,
        )
        item = object_runs.json()["items"][0]
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

    reopened = create_app()
    with TestClient(reopened) as client:
        restart_replay = client.post("/api/research-runs", headers=confirm_headers, json=body)
        assert restart_replay.status_code == 200, restart_replay.text
        assert restart_replay.json()["admission"] == admission
        object_runs = client.get(f"/api/objects/{object_id}/runs", headers=headers)
        assert object_runs.status_code == 200, object_runs.text
        assert validate_run_collection(object_runs.json(), expected_object_id=object_id) == (
            run_id,
        )
