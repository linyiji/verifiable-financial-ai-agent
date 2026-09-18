"""Safe provider rejection survives the existing writer and a fresh interpreter."""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from src.application.persistence import ResearchRunAggregateRow
from tests.phase4.backend_product.test_failure_receipt_persistence import READER
from tests.phase4.backend_product.test_memory_postgresql import database  # noqa: F401
from tests.phase4.backend_product.test_recovery_persistence import store  # noqa: F401
from tests.unit.llm.test_provider_rejection_metadata import (
    CASES,
    MODELS,
    NUMERIC_CASES,
    exercise_rejection,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL required"
)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("model", MODELS)
async def test_rejection_metadata_fresh_reader(store, case, model):  # noqa: F811
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
    rows, row, _ = await exercise_rejection(case, model, store)
    async with store.sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        READER,
        os.environ["TEST_POSTGRESQL_URL"],
        schema,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    assert proc.returncode == 0, stderr.decode()
    fresh = json.loads(stdout)
    assert fresh == [r.model_dump(mode="json") for r in rows]
    durable = next(r for r in fresh if r["record_id"] == row.record_id)
    assert durable["safe_failure"] == row.safe_failure.model_dump(mode="json")
    assert (
        durable["safe_failure"]["provider_rejection"]["provider_rejection_detail_parse_status"]
        != "UNKNOWN"
    )

    if case in NUMERIC_CASES:
        numeric = durable["safe_failure"]["provider_rejection"]["provider_error_code_numeric"]
        assert numeric == NUMERIC_CASES[case][0]
        assert type(numeric) is int
        assert durable["safe_failure"]["provider_rejection"]["provider_error_code"] is None

    if destination := os.environ.get("REJECTION_METADATA_PROOF_DIR"):
        await asyncio.to_thread(Path(destination).mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(
            Path(destination, f"{model}-{case}.json").write_text,
            json.dumps(
                {
                    "writer_pid": os.getpid(),
                    "fresh_reader_pid": proc.pid,
                    "writer_record": row.model_dump(mode="json"),
                    "fresh_reader_record": durable,
                    "all_records_equal": True,
                },
                indent=2,
            )
        )
