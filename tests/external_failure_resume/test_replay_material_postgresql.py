"""Committed Resume receipts survive material loss, process exit and HTTP retries."""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text

from src.application.persistence import (
    ResearchRunAggregateRow,
    RuntimeEventRow,
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.domain.node_binding import BindingDenied
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from src.phase4_product.api import create_phase4_product_router, install_phase4_error_handlers
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from tests.external_failure_resume.runtime_fixture import exhaust, legal_fixture, request_for
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="PostgreSQL required"
)


async def test_committed_replay_material_loss(database, tmp_path):  # noqa: F811
    _, sessions = database
    service, value, clients = await legal_fixture(
        tmp_path,
        repository=SQLAlchemyApplicationRepository(sessions),
        evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions),
        event_store=PostgresRuntimeEventStore(sessions),
    )
    failed = await exhaust(service, value)
    request = (await request_for(service, failed)).model_copy(
        update={"actor": "LOCAL_SINGLE_USER"}
    )
    command_file = tmp_path / "request.json"
    command_file.write_text(request.model_dump_json())
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))

    async def child():
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "tests.external_failure_resume.test_replay_material_postgresql",
            schema, str(command_file), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await process.communicate()
        assert process.returncode == 0, err.decode()
        return json.loads(out)

    material = next(
        r for result in failed.node_binding.results.values()
        for r in result.output_records if r.kind == "AGENT_OUTPUT"
    )
    path = Path(material.location)
    assert path.is_relative_to(tmp_path)
    withheld = path.with_suffix(".withheld")
    await asyncio.to_thread(path.rename, withheld)
    try:
        # A never-committed grant must still verify retained inputs.
        with pytest.raises(BindingDenied, match="MISSING_INPUT"):
            await service.repository.resume_external_failure(request, actor=request.actor)
    finally:
        await asyncio.to_thread(withheld.rename, path)
    writer = await child()  # Production authorization commits, then its process exits.
    receipt = writer["receipt"]

    async def snapshot():
        async with sessions() as session:
            row = await session.get(ResearchRunAggregateRow, request.run_id)
            events = list(await session.scalars(select(RuntimeEventRow).where(
                RuntimeEventRow.run_id == request.run_id
            ).order_by(RuntimeEventRow.sequence)))
            return json.dumps([
                row.payload, row.projection_revision, row.projection_sequence,
                [e.payload for e in events],
            ], sort_keys=True)

    before = await snapshot()
    calls = {k: c.calls for k, c in clients.items()}
    await asyncio.to_thread(path.rename, withheld)
    try:
        reader = await child()
        assert reader["pid"] != writer["pid"]
        assert reader["receipt"] == receipt
        replays = await asyncio.gather(*[
            SQLAlchemyApplicationRepository(sessions).resume_external_failure(
                request, actor=request.actor
            ) for _ in range(8)
        ])
        assert all(r.model_dump(mode="json") == receipt for r in replays)
        changed = request.model_copy(update={"expected_owner_generation": 999})
        with pytest.raises(BindingDenied, match="RESUME_IDEMPOTENCY_CONFLICT"):
            await service.repository.resume_external_failure(changed, actor=request.actor)
        unknown = request.model_copy(update={"idempotency_key": "unknown"})
        with pytest.raises(BindingDenied, match="MISSING_INPUT"):
            await service.repository.resume_external_failure(unknown, actor=request.actor)
        with pytest.raises(BindingDenied, match="RESUME_ACTOR_MISMATCH"):
            await service.repository.resume_external_failure(request, actor="OTHER")
        wrong_run = request.model_copy(update={"run_id": "RUN-NOT-THIS-RUN"})
        with pytest.raises(BindingDenied, match="STATE_REFRESH_REQUIRED"):
            await service.repository.resume_external_failure(wrong_run, actor=request.actor)
        app = FastAPI()
        app.state.phase4_product_backend = PostgreSQLPhase4ProductBackend(
            sessions=sessions, service=service
        )
        app.state.research_service = service
        app.include_router(create_phase4_product_router())
        install_phase4_error_handlers(app)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://local"
        ) as client:
            payload = dict(request.model_dump(mode="json"), authorize_resume=True)
            url = f"/api/research-runs/{request.run_id}/external-resume"
            for _ in range(2):
                response = await client.post(
                    url, json=payload, headers={"Idempotency-Key": request.idempotency_key}
                )
                assert response.status_code == 200, response.text
                assert response.json()["receipt"] == receipt
                assert response.json()["outcome"] == "IDEMPOTENT"
                assert response.json()["projection"] is None
            invalid = dict(payload, command="ApproveReplan")
            response = await client.post(
                url, json=invalid, headers={"Idempotency-Key": request.idempotency_key}
            )
            assert response.status_code == 422
    finally:
        await asyncio.to_thread(withheld.rename, path)
    restored = await child()
    assert restored["receipt"] == receipt
    assert await snapshot() == before  # Includes all budgets, cycles, revisions and events.
    assert calls == {k: c.calls for k, c in clients.items()}


async def _child():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.domain.external_failure_resume import ResumeExternalFailure

    engine = create_async_engine(
        os.environ["TEST_POSTGRESQL_URL"],
        connect_args={"server_settings": {"search_path": sys.argv[1]}},
    )
    try:
        request = ResumeExternalFailure.model_validate_json(
            await asyncio.to_thread(Path(sys.argv[2]).read_text)
        )
        receipt = await SQLAlchemyApplicationRepository(async_sessionmaker(
            engine, expire_on_commit=False
        )).resume_external_failure(request, actor=request.actor)
        print(json.dumps({"pid": os.getpid(), "receipt": receipt.model_dump(mode="json")}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_child())
