"""Actual append-only writer plus a separate interpreter reading the committed rows."""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime

import pytest

from src.application.persistence import ResearchRunAggregateRow
from tests.phase4.backend_product.test_memory_postgresql import database  # noqa: F401
from tests.phase4.backend_product.test_recovery_persistence import store  # noqa: F401
from tests.unit.agentic.test_failure_attempt_receipt import CASES, exercise

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="local DB required"
)

READER = """
import asyncio, json, sys
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.infrastructure.database.recovery import RecoveryEvidenceStore
async def read():
    engine = create_async_engine(
        sys.argv[1], connect_args={"server_settings": {"search_path": sys.argv[2]}})
    rows = await RecoveryEvidenceStore(async_sessionmaker(engine)).records("RUN-local")
    print(json.dumps([r.model_dump(mode="json") for r in rows]))
    await engine.dispose()
asyncio.run(read())
"""


@pytest.mark.asyncio
@pytest.mark.parametrize("case,fallback", [(c, False) for c in CASES] + [("400", True)])
async def test_committed_failure_survives_fresh_process(store, case, fallback):  # noqa: F811
    async with store.sessions() as session, session.begin():
        session.add(
            ResearchRunAggregateRow(
                run_id="RUN-local",
                object_id="OBJ-A",
                status="RUNNING",
                payload={},
                updated_at=datetime.now(UTC),
            )
        )
    rows, target, _, _ = await exercise(case, store=store, fallback=fallback)
    engine = store.sessions.kw["bind"]
    async with engine.connect() as conn:
        from sqlalchemy import text

        schema = await conn.scalar(text("SELECT current_schema()"))
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        READER,
        os.environ["TEST_POSTGRESQL_URL"],
        schema,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode()
    fresh = json.loads(stdout)
    assert fresh == [r.model_dump(mode="json") for r in rows]
    retained = next(r for r in fresh if r["record_id"] == target.record_id)
    assert retained["safe_failure"] == target.safe_failure.model_dump(mode="json")
    assert retained["safe_failure"]["dispatch_state"] in {"UNKNOWN", "NOT_DISPATCHED", "DISPATCHED"}
