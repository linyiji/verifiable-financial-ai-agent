"""Control-plane roundtrip against disposable migrated PostgreSQL."""

import os

import pytest

from src.application.persistence import (
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from src.phase4_product.external_resume import AuthorizeExternalResume, decide, read
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from tests.external_failure_resume.runtime_fixture import legal_fixture
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="PostgreSQL required"
)


async def test_control_projection_roundtrip(database, tmp_path):  # noqa: F811
    _, sessions = database
    service, value, clients = await legal_fixture(
        tmp_path,
        repository=SQLAlchemyApplicationRepository(sessions),
        evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions),
        event_store=PostgresRuntimeEventStore(sessions),
    )
    from tests.external_failure_resume.control_process import (
        production_exhaust,
        retain_blocking_review,
    )

    retain_blocking_review(service)
    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    await production_exhaust(service, value)
    view = await read(backend, value.run.run_id)
    projection = await backend.get_projection(value.run.run_id)
    assert projection.external_failure_resume == view
    command = AuthorizeExternalResume(
        **view["legal_actions"][0]["expectations"], idempotency_key="pg-one", authorize_resume=True
    )
    result = await decide(backend, value.run.run_id, command, "pg-one")
    assert result["outcome"] == "AUTHORIZED"
    projection = await backend.get_projection(value.run.run_id)
    assert projection.external_failure_resume["state"] == "EXTERNAL_RESUME_PENDING"
    clients["teamorouter-sol"].fail_risk = False
    await service.execute_run(value.run.run_id, emit_run_started=False)
    projection = await backend.get_projection(value.run.run_id)
    assert projection.external_failure_resume["authoritative_risk_result"]


@pytest.mark.parametrize("worker", ["worker-success", "worker-exhaust"])
async def test_fresh_process_control_plane(database, tmp_path, worker, record_property):  # noqa: F811
    import asyncio
    import json
    import sys

    from sqlalchemy import text

    _, sessions = database
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    results = []

    async def child(mode, run_id="new"):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "tests.external_failure_resume.control_process",
            mode,
            schema,
            str(tmp_path),
            run_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await process.communicate()
        assert process.returncode == 0, err.decode()
        result = json.loads(out)
        results.append(result)
        return result

    writer = await child("writer")
    run_id = writer["run_id"]
    fresh = await child("read", run_id)
    assert len(fresh["view"]["legal_actions"]) == 1
    authorized = await child("authorize", run_id)
    assert authorized["status"] == 200
    replay = await child("duplicate", run_id)
    assert replay["response"]["receipt"] == authorized["response"]["receipt"]
    assert replay["response"]["outcome"] == "IDEMPOTENT"
    stale = await child("stale", run_id)
    assert stale["status"] == 409
    scheduler = await child("scheduler", run_id)
    assert scheduler["pending"] == [run_id]
    executed = await child(worker, run_id)
    final = await child("read", run_id)
    assert len({r["pid"] for r in results}) == len(results)
    after_completion = await child("duplicate", run_id)
    assert after_completion["response"]["receipt"] == authorized["response"]["receipt"]
    assert after_completion["view"] == final["view"]
    assert sum(a["type"] == "external_failure.cycle_claimed" for a in final["view"]["audit"]) == 1
    assert final["graph"] == writer["graph"]
    assert final["snapshot"] == writer["snapshot"]
    assert all(
        final["current_results"][key] == value for key, value in writer["current_results"].items()
    )
    assert (
        sum(a["type"] == "external_failure.resume_authorized" for a in final["view"]["audit"]) == 1
    )
    assert executed["calls"]["teamorouter-luna"] == executed["calls"]["mimo-direct"] == 0
    if worker == "worker-success":
        assert final["view"]["authoritative_risk_result"]
        assert any("synthesis" in key for key in final["current_results"])
    else:
        assert final["view"]["lifecycle"] == "EXTERNAL_FAILURE_PAUSED"
        assert len(final["view"]["legal_actions"]) == 1
        assert len(final["view"]["failed_cycles"]) == 2
        assert executed["calls"]["teamorouter-sol"] == executed["calls"]["teamorouter-terra"] == 1
    assert any("event: external_failure.resume_authorized" in f for f in authorized["frames"])
    assert authorized["reconnect_frames"] == authorized["frames"][-2:]
    evidence = tmp_path / "cross-process.json"
    evidence.write_text(json.dumps(results))
    record_property("process_proof", str(evidence))
    # Production browser DTO and reducer, in another OS process, consume the
    # atomic snapshots and duplicate/replayed SSE event envelopes.
    node = await asyncio.create_subprocess_exec(
        "node",
        "--experimental-strip-types",
        "--loader",
        "file://"
        + str(__import__("pathlib").Path("apps/web/scripts/typescript-test-loader.mjs").resolve()),
        "apps/web/scripts/external-resume-proof.mjs",
        str(evidence),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await node.communicate()
    assert node.returncode == 0, err.decode()
    record_property("frontend_proof", out.decode())
