from __future__ import annotations

import os
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from src.infrastructure.config.settings import get_settings
from src.phase4_product.reconstruction import reconstruct_product_run

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


async def _read_exact_snapshot(backend, object_id: str, run_id: str):
    async with backend.uow_factory() as uow:
        return await uow.projection.read_exact_run_snapshot(
            object_id=object_id, run_id=run_id
        )


def test_root_composition_persists_reopens_and_resumes_exact_run() -> None:
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    app = create_app()
    with TestClient(app) as client:
        created = client.post(
            "/api/objects",
            headers={**headers, "Idempotency-Key": "r1-object"},
            json={
                "symbol": "MSFT",
                "company_name": "Microsoft Corporation",
                "exchange": "NASDAQ",
                "currency": "USD",
            },
        )
        assert created.status_code == 201, created.text
        object_id = created.json()["object"]["object_id"]
        prepared = client.post(
            "/api/research-runs/prepare",
            headers={**headers, "Idempotency-Key": "r1-prepare"},
            json={
                "research_object_id": object_id,
                "research_goal": "Produce a verifiable full-company research report.",
                "as_of": "2026-09-05",
                "preferences": {},
            },
        )
        assert prepared.status_code == 201, prepared.text
        draft = prepared.json()
        confirmed = client.post(
            "/api/research-runs",
            headers={**headers, "Idempotency-Key": "r1-confirm"},
            json={
                "draft_id": draft["draft_id"],
                "draft_version": draft["draft_version"],
                "draft_hash": draft["draft_hash"],
                "research_object_id": object_id,
                "confirm_scheme": True,
            },
        )
        assert confirmed.status_code == 201, confirmed.text
        run_id = confirmed.json()["admission"]["run_id"]

        for _ in range(100):
            run_response = client.get(f"/api/research-runs/{run_id}", headers=headers)
            assert run_response.status_code == 200, run_response.text
            if run_response.json()["status"] == "RUNNING":
                break
            time.sleep(0.02)
        assert run_response.json()["status"] == "RUNNING"
        projection_response = client.get(
            f"/api/research-runs/{run_id}/projection", headers=headers
        )
        assert projection_response.status_code == 200, projection_response.text
        projection = projection_response.json()
        assert projection["run"]["run_id"] == run_id
        assert projection["projection_revision"] == run_response.json()["projection_revision"]
        assert projection["projection_sequence"] == run_response.json()["projection_sequence"]

        backend = app.state.phase4_product_backend
        preflight = client.portal.call(
            backend.service.event_store.preflight_cursor,
            run_id,
            str(projection["projection_sequence"]),
        )
        assert preflight.sequence == projection["projection_sequence"]
        assert preflight.tail_sequence == projection["projection_sequence"]
        snapshot = client.portal.call(
            _read_exact_snapshot,
            backend,
            object_id,
            run_id,
        )
        reconstructed = reconstruct_product_run(snapshot)
        assert reconstructed.run.run_id == run_id
        assert reconstructed.research_object.object_id == object_id
        assert reconstructed.watermark.sequence == projection["projection_sequence"]

    reopened = create_app()
    with TestClient(reopened) as client:
        same_run = client.get(f"/api/research-runs/{run_id}", headers=headers)
        assert same_run.status_code == 200, same_run.text
        assert same_run.json()["run_id"] == run_id
        assert same_run.json()["research_object_id"] == object_id
        same_projection = client.get(
            f"/api/research-runs/{run_id}/projection", headers=headers
        )
        assert same_projection.status_code == 200, same_projection.text
        assert same_projection.json()["projection_sequence"] >= projection["projection_sequence"]
