"""Applied audit lineage survives writer exit and never backfills old events."""

import asyncio
import json
import os
import sys

from sqlalchemy import text

from src.domain.execution_profile import ExecutionSnapshot
from src.domain.node_binding import digest
from src.domain.risk_replan import RiskReplanAudit
from tests.risk_replan.test_postgresql import database, fresh, pytestmark  # noqa: F401

WRITER = r'''
import asyncio,json,sys
from pathlib import Path
from src.domain.node_binding import BindingDenied
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.application.persistence import SQLAlchemyApplicationRepository
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.risk_replan.test_flow import fixture,command
import tests.same_node_recovery.test_durable as fixture_owner
original_aggregate=fixture_owner.aggregate
def unique_aggregate(*args):
    value=original_aggregate(*args)
    def unique(model):
        encoded=model.model_dump_json().replace("WP02", "WP02-"+Path(sys.argv[3]).name)
        return type(model).model_validate_json(encoded)
    value.run=unique(value.run)
    value.goal=unique(value.goal)
    value.scheme=unique(value.scheme)
    value.runtime=type(value.runtime).create(run_id=value.run.run_id,planned_graph=unique(value.runtime.planned_graph))
    value.node_binding=None
    return value
fixture_owner.aggregate=unique_aggregate
async def main():
    engine=create_async_engine(sys.argv[1],connect_args={"server_settings":{"search_path":sys.argv[2]}})
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    repo=SQLAlchemyApplicationRepository(sessions)
    original_draft=repo.add_draft
    async def unique_draft(draft):
        draft.draft_id += "-"+Path(sys.argv[3]).name
        return await original_draft(draft)
    repo.add_draft=unique_draft
    service,value,calls,transport=await fixture(
        Path(sys.argv[3]),repository=repo,
        store=RecoveryEvidenceStore(sessions),sessions=sessions)
    original_evidence=service.evidence_repository.add
    async def unique_evidence(record):
        record.evidence_id += "-"+Path(sys.argv[3]).name
        return await original_evidence(record)
    service.evidence_repository.add=unique_evidence
    rid=value.run.run_id
    with transport:value=await service.execute_run(rid)
    async def denied():
        try: await repo.apply_replan(rid)
        except BindingDenied as exc: assert exc.code == "REPLAN_NOT_AUTHORIZED"
        else: raise AssertionError("unauthorized apply accepted")
    old=command(value,"APPROVE")
    for action in ["DECLINE","REOPEN"]:
        value=await repo.get_run_fresh(rid)
        await repo.decide_replan(rid,command(value,action),actor="LOCAL_SINGLE_USER",key=action)
        await denied()
    stale=await repo.decide_replan(rid,old,actor="LOCAL_SINGLE_USER",key="stale")
    assert stale["outcome"]=="REJECTED"
    await denied()
    value=await repo.get_run_fresh(rid)
    await repo.decide_replan(rid,command(value,"APPROVE"),actor="LOCAL_SINGLE_USER",key="current")
    first=await repo.apply_replan(rid)
    assert await repo.apply_replan(rid)==first
    print(json.dumps({"run_id":rid,"pid":__import__("os").getpid()}))
    await engine.dispose()
asyncio.run(main())
'''


async def test_exited_writer_two_runs_exact_audit(database, tmp_path):  # noqa: F811
    _, sessions = database
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    snapshots = []
    for ordinal in range(2):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", WRITER, os.environ["TEST_POSTGRESQL_URL"], schema,
            str(tmp_path / str(ordinal)), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await process.communicate()
        assert process.returncode == 0, err.decode()
        writer = json.loads(out)
        observed = await fresh(sessions, writer["run_id"])
        assert observed["pid"] != writer["pid"]
        root = observed["root"]
        transition = root["replan"]["transition"]
        events = [e for e in observed["events"] if e["type"] == "replan.applied"]
        assert len(events) == 1
        event = events[0]
        payload = event["payload"]["risk_replan"]
        for field in (
            "transition_id", "old_execution_snapshot_digest", "new_execution_snapshot_digest",
        ):
            assert isinstance(payload[field], str)
            assert payload[field] == transition[field]
        assert payload["run_id"] == transition["run_id"] == event["run_id"] == writer["run_id"]
        assert payload["authorized_diff_digest"] == digest(transition["authorized_diff"])
        assert payload["proposal_id"] == transition["proposal_id"]
        assert payload["proposal_digest"] == transition["proposal_digest"]
        assert payload["decision_id"] == transition["decision_id"]
        assert payload["base_graph"] == transition["base_graph"]
        assert payload["graph"] == transition["new_graph"] == root["frozen_graph"]
        assert payload["old_execution_snapshot_digest"] == ExecutionSnapshot.model_validate(
            transition["old_execution_snapshot"]
        ).execution_profile_snapshot_digest
        assert payload["new_execution_snapshot_digest"] == ExecutionSnapshot.model_validate(
            root["execution_snapshot"]
        ).execution_profile_snapshot_digest
        legacy = {k: v for k, v in payload.items() if k not in {
            "authorized_diff_digest",
            "transition_id", "old_execution_snapshot_digest", "new_execution_snapshot_digest",
        }}
        assert RiskReplanAudit.model_validate(legacy).model_dump(
            mode="json", exclude_unset=True, exclude={"timestamp"}
        ) == {k: v for k, v in legacy.items() if k != "timestamp"}
        assert RiskReplanAudit.model_validate(legacy).transition_id is None
        snapshots.append(observed)
    assert snapshots[0]["root"]["run_id"] != snapshots[1]["root"]["run_id"]
    identities = [item["root"]["replan"]["transition"]["transition_id"] for item in snapshots]
    assert identities[0] != identities[1]
