"""Disposable PostgreSQL fresh-process proof for both new frozen request families."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("FALLBACK_DISPOSABLE_POSTGRES"),
    reason="explicit disposable fallback database",
)


@pytest.mark.parametrize("kind", ["risk_analysis", "valuation_analysis"])
async def test_fresh_process_adoption_and_confirm(database, tmp_path, kind, record_property):  # noqa: F811
    _, sessions = database
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    receipts = {}
    for phase in ("A", "B", "C", "D"):
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "tests.execution_profiles.fallback_process_worker",
            os.environ["TEST_POSTGRESQL_URL"],
            schema,
            str(tmp_path),
            kind,
            phase,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await child.communicate()
        assert child.returncode == 0, output.decode()
        receipts[phase] = json.loads((tmp_path / f"process-{phase}.json").read_text())
    assert len({v["pid"] for v in receipts.values()}) == 4
    a, b = receipts["A"], receipts["B"]
    assert a["run_id"] == b["run_id"]
    for key in (
        "frozen_graph",
        "scenario_snapshot_digest",
        "execution_profile_snapshot_digest",
        "execution_snapshot",
    ):
        assert a["root"][key] == b["root"][key]
    old = next(v for v in a["root"]["attempts"].values() if v["status"] == "FAILED")
    new = b["root"]["attempts"][old["admission"]["task_id"]]
    assert new["status"] == "COMMITTED" and new["generation"] == old["generation"] + 1
    for key in ("task_fingerprint", "graph", "dependency_result_bindings"):
        assert new["admission"][key] == old["admission"][key]
    assert new["admission"]["attempt_reservation_id"] != old["admission"]["attempt_reservation_id"]
    assert b["root"]["attempt_history"][old["admission"]["attempt_reservation_id"]] == old
    assert all(b["root"]["results"][k] == v for k, v in a["root"]["results"].items())
    assert b["records"][: len(a["records"])] == a["records"]
    assert b["upstream_calls"] == 0
    assert b["calls"] == {
        "teamorouter-sol": 0,
        "teamorouter-luna": 0,
        "teamorouter-terra": 1,
        "mimo-direct": 0,
    }
    assert receipts["C"]["snapshot"] == receipts["D"]["snapshot"]
    dest = os.environ.get("FALLBACK_PROOF_RECEIPTS")
    if dest:
        await asyncio.to_thread(Path(dest).mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(
            Path(dest, f"{kind}.json").write_text, json.dumps(receipts, indent=2)
        )
    record_property("fresh_process_proof", json.dumps({k: v["pid"] for k, v in receipts.items()}))


TRANSPORT_WRITER = """
import asyncio,json,sys
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.execution_profiles.fallback_transport_fixture import physical_fixture
async def main():
 engine=create_async_engine(sys.argv[1],connect_args={"server_settings":{"search_path":sys.argv[2]}})
 store=RecoveryEvidenceStore(async_sessionmaker(engine))
 rows=await physical_fixture(
  Path(sys.argv[3]),sys.argv[4],
  terra_failure=None if sys.argv[5]=="success" else "400",store=store)
 print(json.dumps([r.model_dump(mode="json") for r in rows]))
 await engine.dispose()
asyncio.run(main())
"""
TRANSPORT_READER = """
import asyncio,json,sys
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.infrastructure.database.recovery import RecoveryEvidenceStore
async def main():
 engine=create_async_engine(sys.argv[1],connect_args={"server_settings":{"search_path":sys.argv[2]}})
 rows=await RecoveryEvidenceStore(async_sessionmaker(engine)).records()
 print(json.dumps([r.model_dump(mode="json") for r in rows]))
 await engine.dispose()
asyncio.run(main())
"""


@pytest.mark.parametrize("kind", ["risk_analysis", "valuation_analysis"])
@pytest.mark.parametrize("case", ["success", "400"])
async def test_physical_receipts_writer_exit_fresh_reader(
    database, tmp_path, kind, case, record_property  # noqa: F811
):
    from src.application.persistence import SQLAlchemyApplicationRepository
    from src.infrastructure.database.recovery import RecoveryEvidenceStore
    from tests.execution_profiles.fallback_fixture import configured_family

    _, sessions = database
    await configured_family(
        tmp_path,
        kind,
        repository=SQLAlchemyApplicationRepository(sessions),
        store=RecoveryEvidenceStore(sessions),
        sessions=sessions,
    )
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))

    async def process(code):
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            os.environ["TEST_POSTGRESQL_URL"],
            schema,
            str(tmp_path),
            kind,
            case,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await child.communicate()
        assert child.returncode == 0, err.decode()
        return child.pid, json.loads(out)

    writer, written = await process(TRANSPORT_WRITER)
    reader, read = await process(TRANSPORT_READER)
    assert writer != reader and written == read
    completed = [r for r in read if r["kind"] == "ATTEMPT_COMPLETED"]
    assert [r["route"] for r in completed] == ["teamorouter-sol", "teamorouter-terra"]
    assert all(r["transport_evidence"]["proxy_connect_http_status"] == 200 for r in completed)
    assert completed[0]["transport_evidence"]["provider_http_status"] is None
    assert completed[1]["transport_evidence"]["provider_http_status"] == (
        200 if case == "success" else 400
    )
    if case == "400":
        assert (
            completed[1]["safe_failure"]["provider_rejection"]["provider_error_code_numeric"] == 400
        )
    assert "SENTINEL_SECRET" not in json.dumps(read)
    receipt = dict(
        writer_pid=writer,
        reader_pid=reader,
        writer_exited_before_reader=True,
        exact_rows_equal=True,
        rows=read,
    )
    dest = os.environ.get("FALLBACK_PROOF_RECEIPTS")
    if dest:
        await asyncio.to_thread(Path(dest).mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(
            Path(dest, f"transport-{kind}-{case}.json").write_text, json.dumps(receipt, indent=2)
        )
    record_property("transport_fresh_process", json.dumps(dict(writer=writer, reader=reader)))
