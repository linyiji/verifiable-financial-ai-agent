"""Frozen-date admission through production writers, exited readers and Recovery."""

import asyncio
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from src.domain.evidence import EvidenceRecord
from tests.risk_replan.test_postgresql import READER, database  # noqa: F401

# Same pre-persistence synthetic evidence injection and semantic assertion as the
# independent F-64 reproducer. Only follow-on approval is conditional on a proposal:
# lawful admission denial must be observable rather than a harness KeyError.
WRITER = r'''
import asyncio,json,sys,os
from pathlib import Path
from datetime import timedelta
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.application.persistence import SQLAlchemyApplicationRepository
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.risk_replan.test_flow import fixture,command
from tests.risk_replan.test_recovery import resume
async def main():
 engine=create_async_engine(sys.argv[1],connect_args={'server_settings':{'search_path':sys.argv[2]}})
 sessions=async_sessionmaker(engine,expire_on_commit=False);repo=SQLAlchemyApplicationRepository(sessions)
 mode=sys.argv[4]
 service,value,calls,transport=await fixture(Path(sys.argv[3]),repository=repo,
  store=RecoveryEvidenceStore(sessions),sessions=sessions,complete_requirements=True,
  failure_plan={('risk_follow_up','gpt-5.6-sol'):['timeout']} if mode=='recovery' else None)
 original=service.evidence_repository.add
 async def add(record):
  offset={'past':-1,'equal':0,'future':1,'recovery':0}.get(mode,0)
  if mode=='mixed' and record.period=='FY2025':offset=1
  record.as_of=value.run.as_of+timedelta(days=offset)
  return await original(record)
 service.evidence_repository.add=add
 try:
  with transport:value=await service.execute_run(value.run.run_id)
 except ExceptionGroup as exc:
  from src.domain.node_binding import BindingDenied
  assert mode in ('future','mixed')
  assert all(isinstance(e,BindingDenied) and e.code=='STALE_INPUT' for e in exc.exceptions)
  value=await repo.get_run_fresh(value.run.run_id)
 rid=value.run.run_id
 if value.node_binding.replan is not None:
  await repo.decide_replan(rid,command(value,'APPROVE'),actor='LOCAL_SINGLE_USER',key='A')
  await repo.apply_replan(rid)
  with transport:
   if mode=='recovery':await service.execute_run(rid)
   else:await resume(service,rid)
 value=await repo.get_run_fresh(rid)
 print(json.dumps({'pid':os.getpid(),'rid':rid,'as_of':str(value.run.as_of),
  'evidence':[{'id':e.evidence_id,'as_of':str(e.as_of),'status':e.status.value}
   for e in value.artifacts.evidence],
  'calls':calls,'root':value.node_binding.model_dump(mode='json')}))
 await engine.dispose()
asyncio.run(main())
'''

RECOVER = r'''
import asyncio,json,sys,os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.application.persistence import SQLAlchemyApplicationRepository
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.risk_replan.test_flow import fixture
async def main():
 engine=create_async_engine(sys.argv[1],connect_args={'server_settings':{'search_path':sys.argv[2]}})
 sessions=async_sessionmaker(engine,expire_on_commit=False);repo=SQLAlchemyApplicationRepository(sessions)
 service,local,calls,transport=await fixture(Path(sys.argv[3]),repository=repo,
  store=RecoveryEvidenceStore(sessions),sessions=sessions,persist=False)
 # A later mutable request/default is not authority for the persisted Run.
 from datetime import date
 local.run.as_of=local.goal.as_of=date(2099,1,1)
 original=repo.bind_resolved_inputs
 async def bind(admission,*,step_id,materials,payload):
  if (step_id=='agent-context' and admission.task_id.endswith(':risk-follow-up')
      and sys.argv[5]!='valid'):
   from copy import deepcopy
   payload=deepcopy(payload); inputs=payload['context']['inputs']
   if sys.argv[5]=='future':inputs['normalized_evidence'][0]['as_of']='2099-01-01'
   if sys.argv[5]=='scope':inputs['as_of']='2099-01-01'
  return await original(admission,step_id=step_id,materials=materials,payload=payload)
 repo.bind_resolved_inputs=bind
 try:
  with transport:await service.execute_run(sys.argv[4])
 except ExceptionGroup as exc:
  from src.domain.node_binding import BindingDenied
  assert sys.argv[5]!='valid'
  assert all(isinstance(e,BindingDenied) and e.code=='IDENTITY_MISMATCH' for e in exc.exceptions)
 value=await repo.get_run_fresh(sys.argv[4])
 print(json.dumps({'pid':os.getpid(),'as_of':str(value.run.as_of),'calls':calls,
  'root':value.node_binding.model_dump(mode='json')}))
 await engine.dispose()
asyncio.run(main())
'''


async def process(source, schema, tmp_path, *args):
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", source, os.environ["TEST_POSTGRESQL_URL"], schema,
        str(tmp_path), *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    assert proc.returncode == 0, err.decode()
    return json.loads(out)


async def fresh(sessions, run_id):
    async with sessions() as session:
        schema = await session.scalar(text("select current_schema()"))
    source = READER.replace('sys.argv[3]', 'sys.argv[4]').replace(
        '"root":value.node_binding',
        '"as_of":value.run.as_of.isoformat(),"root":value.node_binding',
    )
    return await process(source, schema, Path.cwd(), run_id)


def receipt(name, value):
    destination = os.environ.get("RISK_REPLAN_PROOF_RECEIPTS")
    if destination:
        path = Path(destination)
        path.with_name(path.stem + "-" + name + ".json").write_text(json.dumps(value, indent=2))


@pytest.mark.parametrize("mode", ["past", "equal", "future", "mixed"])
async def test_exited_temporal_boundary(database, tmp_path, mode):  # noqa: F811
    _, sessions = database
    async with sessions() as session:
        schema = await session.scalar(text("select current_schema()"))
    writer = await process(WRITER, schema, tmp_path, mode)
    reader = await fresh(sessions, writer["rid"])
    # The closed root codec omits an absent optional Replan extension.
    reader["root"].setdefault("replan", None)
    assert writer["pid"] != reader["pid"] != os.getpid()
    receipt(mode, {"writer": writer, "reader": reader})
    assert reader["as_of"] == writer["as_of"] == "2026-09-14"
    if mode in {"future", "mixed"}:
        # Unchanged independent semantic assertion, followed by stronger checks.
        assert (not any(e['as_of'] > writer['as_of'] for e in writer['evidence'])
                or reader['root']['replan'] is None), (
            'F-64: future-as_of evidence accepted through durable proposal/apply/child finalization'
        )
        assert any(e["as_of"] > writer["as_of"] for e in writer["evidence"])
        if mode == "mixed":
            assert any(e["as_of"] <= writer["as_of"] for e in writer["evidence"])
        assert reader["root"]["frozen_graph"]["version"] == 1
        assert not any(k in {"risk_analysis", "risk_follow_up", "report_synthesis"}
                       for k, _ in writer["calls"])
        for suffix in (":risk", ":risk-follow-up", ":synthesis"):
            assert writer["rid"] + suffix not in reader["root"]["current_results"]
        assert "STALE_INPUT" in json.dumps(reader)
    else:
        assert reader["root"]["frozen_graph"]["version"] == 2
        assert reader["root"]["replan"]["finalization"]
        for suffix in (":risk", ":risk-follow-up", ":synthesis"):
            assert writer["rid"] + suffix in reader["root"]["current_results"]
        assert sum(k == "risk_follow_up" for k, _ in writer["calls"]) == 1
        for bound in reader["root"]["resolved_inputs"].values():
            if bound["step_id"] == "agent-context":
                inputs = bound["payload_snapshot"]["context"]["inputs"]
                assert inputs["as_of"] == writer["as_of"]
                assert all(e["as_of"] <= writer["as_of"] for e in inputs["normalized_evidence"])


@pytest.mark.parametrize("mode", ["valid", "future", "scope"])
async def test_exited_recovery_frozen_scope(database, tmp_path, mode):  # noqa: F811
    _, sessions = database
    async with sessions() as session:
        schema = await session.scalar(text("select current_schema()"))
    writer = await process(WRITER, schema, tmp_path, "recovery")
    before = await fresh(sessions, writer["rid"])
    assert before["root"]["lifecycle"] == "RECOVERY_PENDING"
    assert before["root"]["replan"]["finalization"] is None
    recovered = await process(RECOVER, schema, tmp_path, writer["rid"], mode)
    reader = await fresh(sessions, writer["rid"])
    receipt("recovery-" + mode, {"writer": writer, "before": before,
                                "recovered": recovered, "reader": reader})
    assert len({writer["pid"], before["pid"], recovered["pid"], reader["pid"], os.getpid()}) == 5
    assert reader["as_of"] == before["as_of"] == recovered["as_of"] == writer["as_of"]
    assert reader["as_of"] == "2026-09-14"
    assert reader["root"]["frozen_graph"]["version"] == 2
    if mode == "valid":
        assert reader["root"]["replan"]["finalization"]
        assert [m for k, m in recovered["calls"] if k == "risk_follow_up"] == ["gpt-5.6-terra"]
    else:
        assert reader["root"]["replan"]["finalization"] is None
        assert recovered["calls"] == []
        assert writer["rid"] + ":risk" not in reader["root"]["current_results"]
        assert writer["rid"] + ":risk-follow-up" not in reader["root"]["current_results"]
        assert "IDENTITY_MISMATCH" in json.dumps(reader)


@pytest.mark.parametrize(
    "change", ["missing", "unknown", "later_scope", "wrong_object", "wrong_run"]
)
async def test_context_identity_admission(tmp_path, change):
    from tests.risk_replan.test_flow import fixture

    service, value, calls, transport = await fixture(tmp_path)
    original = service.repository.bind_resolved_inputs

    async def bind(admission, *, step_id, materials, payload):
        if step_id == "agent-context" and admission.task_id.endswith(":risk"):
            payload = deepcopy(payload)
            inputs = payload["context"]["inputs"]
            if change == "missing":
                inputs["normalized_evidence"][0].pop("as_of")
            elif change == "unknown":
                inputs["normalized_evidence"][0]["as_of"] = "UNKNOWN"
            elif change == "later_scope":
                inputs["as_of"] = "2099-01-01"
            elif change == "wrong_object":
                inputs["research_object_id"] = "WRONG"
            else:
                payload["context"]["task"]["run_id"] = "WRONG"
        return await original(admission, step_id=step_id, materials=materials, payload=payload)

    service.repository.bind_resolved_inputs = bind
    from src.domain.node_binding import BindingDenied

    with transport, pytest.raises(ExceptionGroup) as caught:
        await service.execute_run(value.run.run_id)
    assert all(isinstance(e, BindingDenied) and e.code == "IDENTITY_MISMATCH"
               for e in caught.value.exceptions)
    result = await service.repository.get_run_fresh(value.run.run_id)
    assert result.node_binding.replan is None
    assert not any(k in {"risk_analysis", "risk_follow_up", "report_synthesis"} for k, _ in calls)


@pytest.mark.parametrize("value", [None, "UNKNOWN"])
async def test_evidence_unknown_date_is_not_valid(tmp_path, value):
    from tests.risk_replan.test_controls import pending

    _, aggregate, _, _ = await pending(tmp_path)
    data = aggregate.artifacts.evidence[0].model_dump(mode="json")
    data["as_of"] = value
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate(data)
    data.pop("as_of")
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate(data)
