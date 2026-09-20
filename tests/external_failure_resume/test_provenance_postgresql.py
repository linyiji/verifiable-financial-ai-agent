"""Writer exits before a separate reader loads migrated PostgreSQL evidence."""

import asyncio
import json
import os
import sys

import pytest
from sqlalchemy import text

from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL required"
)

PROCESS = '''
import asyncio,json,os,sys
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.data.persistence import SQLAlchemyEvidenceRepository
from src.domain.evidence import EvidenceRecord
from tests.external_failure_resume.test_provenance import ingest
async def main():
 engine=create_async_engine(sys.argv[1],connect_args={"server_settings":{"search_path":sys.argv[2]}})
 sessions=async_sessionmaker(engine,expire_on_commit=False)
 async with sessions() as session:
  repo=SQLAlchemyEvidenceRepository(session)
  if sys.argv[3]=="write":
   from datetime import date
   from src.application.persistence import SQLAlchemyApplicationRepository
   from src.application.service import ResearchApplicationService
   service=ResearchApplicationService(
    repository=SQLAlchemyApplicationRepository(sessions),
    run_id_factory=lambda: "RUN-PROVENANCE")
   obj=await service.create_object(symbol="NVDA",company_name="Synthetic",exchange="LOCAL")
   draft=await service.prepare_run(research_object_id=obj.object_id,
    research_goal="Synthetic provenance persistence test",as_of=date(2026,9,3),preferences={})
   await service.confirm_run(draft_id=draft.draft_id,confirm_scheme=True)
   result=await ingest(repo)
   legacy=result.records[0].model_dump(mode="json")
   legacy.pop("validation_provenance")
   legacy["evidence_id"]="LEGACY-NULL"
   await repo.add(EvidenceRecord.model_validate(legacy))
   await session.commit()
  records=await repo.list_by_run("RUN-PROVENANCE")
  print(json.dumps({"pid":os.getpid(),"records":sorted(
   [r.model_dump(mode="json") for r in records],key=lambda r:r["evidence_id"])}))
 await engine.dispose()
asyncio.run(main())
'''


async def test_ingestion_writer_exit_fresh_reader_and_legacy_null(
    database, record_property,  # noqa: F811
):
    _, sessions = database
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
        columns = await session.execute(text(
            "SELECT is_nullable,column_default FROM information_schema.columns "
            "WHERE table_schema=:schema AND table_name='evidence_records' "
            "AND column_name='validation_provenance'"
        ), {"schema": schema})
        assert columns.one() == ("YES", None)
        indexes = await session.execute(text(
            "SELECT indexname FROM pg_indexes WHERE schemaname=:schema"
        ), {"schema": schema})
        assert "phase6_recovery_single_entry" in {row[0] for row in indexes}
        triggers = await session.execute(text(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE trigger_schema=:schema"
        ), {"schema": schema})
        assert "runtime_events_allocate_sequence" in {row[0] for row in triggers}

    async def process(mode):
        child = await asyncio.create_subprocess_exec(
            sys.executable, "-c", PROCESS, os.environ["TEST_POSTGRESQL_URL"], schema, mode,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await child.communicate()
        assert child.returncode == 0, err.decode()
        return json.loads(out)

    written = await process("write")
    read = await process("read")
    assert written["pid"] != read["pid"]
    assert read["records"] == written["records"]
    assert len(read["records"]) == 5
    assert "validation_provenance" not in read["records"][-1]
    for record in read["records"][:-1]:
        assert record["validation_provenance"]["freshness"]["max_age_days"] == 800
    record_property("fresh_process_provenance", json.dumps({
        "writer_pid": written["pid"], "reader_pid": read["pid"],
        "writer_exited_before_reader": True, "records_equal": True, "schema": schema,
    }))
