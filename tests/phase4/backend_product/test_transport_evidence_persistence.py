"""The production writer process must exit before a fresh reader inspects exact facts."""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from src.application.persistence import ResearchRunAggregateRow
from tests.phase4.backend_product.test_failure_receipt_persistence import READER
from tests.phase4.backend_product.test_memory_postgresql import database  # noqa: F401
from tests.phase4.backend_product.test_recovery_persistence import store  # noqa: F401

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRESQL_URL"), reason="local test DB")

WRITER = """
import asyncio,json,sys
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.unit.observability.test_safe_transport_evidence import recovery_fixture
async def write():
    engine=create_async_engine(sys.argv[1],connect_args={"server_settings":{"search_path":sys.argv[2]}})
    store=RecoveryEvidenceStore(async_sessionmaker(engine))
    rows,_,clients,_=await recovery_fixture(sys.argv[3],store=store)
    assert all(c.is_closed for c in clients)
    print(json.dumps([r.model_dump(mode="json") for r in rows]))
    await engine.dispose()
asyncio.run(write())
"""


@pytest.mark.parametrize("case", ["tls_error", "read_timeout", "400"])
async def test_writer_exit_then_fresh_reader(store, case, record_property):  # noqa: F811
    # Synthetic aggregate fixture only; no Research Run orchestration or provider execution.
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
    async with store.sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))

    async def process(source, *args):
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            source,
            os.environ["TEST_POSTGRESQL_URL"],
            schema,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await child.communicate()
        assert child.returncode == 0, stderr.decode()
        return child.pid, json.loads(stdout)

    writer_pid, written = await process(WRITER, case)  # writer has exited before reader launch
    reader_pid, read = await process(READER)
    assert writer_pid != reader_pid
    assert read == written
    row = next(r for r in read if r["kind"] == "ATTEMPT_COMPLETED")
    e = row["transport_evidence"]
    assert e["proxy_connect_http_status"] == 200 and e["client_closed"] is True
    assert e["client_identity"] and e["pool_identity"] and e["attempt_identity"]
    if case == "tls_error":
        assert e["provider_http_status"] is None and e["target_headers_started"] is None
        assert e["trace_cause_exception_module"] == "ssl" and e["errno"] is not None
        assert row["safe_failure"]["dispatch_state"] == "UNKNOWN"
    elif case == "read_timeout":
        assert e["target_body_completed"] is True and e["provider_http_status"] is None
        assert e["exception_class"] == "ReadTimeout" and e["errno"] is not None
    else:
        assert e["target_body_completed"] is True and e["provider_http_status"] == 400
        assert row["safe_failure"]["normalized_failure_class"] == "request_rejected"
    assert "SENTINEL_SECRET" not in json.dumps(read)
    record_property(
        "durable_proof",
        json.dumps(
            {
                "case": case,
                "writer_pid": writer_pid,
                "reader_pid": reader_pid,
                "writer_exited_before_reader": True,
                "exact_rows_equal": read == written,
                "transport_evidence": e,
                "safe_failure": row["safe_failure"],
            }
        ),
    )
