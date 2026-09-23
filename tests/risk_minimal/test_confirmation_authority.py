"""A1 confirmation authority controls, using production Confirm and isolated storage."""

import asyncio
import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import date

import pytest
from sqlalchemy import func, select, text

from src.application.persistence import (
    ResearchRunAggregateRow,
    ResearchRunDraftRow,
    SQLAlchemyApplicationRepository,
)
from src.application.repository import confirmed_risk_authority
from src.application.research_outputs import availability_map, availability_map_for_run
from src.application.service import ResearchApplicationService
from src.domain.execution_profile import ExecutionSnapshot
from src.domain.node_binding import BindingDenied, digest
from src.domain.risk_admission import PROFILE, ConfirmedRiskAuthority
from src.infrastructure.database.phase4_product import (
    Phase4IdempotencyOutcomeRow,
    Phase4SchedulerAdmissionRow,
)
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.phase4_product.contracts import (
    ConfirmResearchRunRequestV1,
    CreateResearchObjectRequestV1,
    PrepareResearchRunRequestV1,
)
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from tests.execution_profiles.test_confirmed_profiles import confirmed
from tests.execution_profiles.test_d01_proof_binding import d01 as terra_d01  # noqa: F401
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401


@pytest.mark.parametrize("d01", [False, True])
async def test_c01_c02_c04_c06_memory_confirm(d01, monkeypatch):
    service, value = await confirmed(preferences={"risk_semantic_profile": PROFILE} if d01 else {})
    receipt = value.confirmed_risk_semantic_binding
    snapshot = ExecutionSnapshot.model_validate(value.node_binding.execution_snapshot)
    assert receipt.risk_semantic_mode == ("D01_V1" if d01 else "LEGACY")
    assert receipt.execution_snapshot_digest == digest(snapshot, "confirmed-execution-snapshot/v1")
    assert receipt.scenario_profile_digest == digest(snapshot.scenario, "scenario-profile/v1")
    assert receipt.confirmation_binding_reference == value.node_binding.reference()
    assert receipt.confirmed_at == value.scheme.confirmed_at.isoformat()

    def forbidden(*args, **kwargs):
        raise AssertionError("current defaults must not resolve on replay")

    monkeypatch.setattr("src.application.execution_profiles.resolve_execution_snapshot", forbidden)
    read = await service.repository.get_run_fresh(value.run.run_id)
    assert read.confirmed_risk_semantic_binding == receipt
    confirmed_risk_authority(read)
    owner = await service.repository.claim_execution(value.run.run_id)
    read = await service.repository.get_run_fresh(value.run.run_id)
    assert read.confirmed_risk_semantic_binding == receipt
    assert read.node_binding.reference() != receipt.confirmation_binding_reference
    assert owner.run_id == receipt.run_id
    confirmed_risk_authority(read)


async def test_c05_requested_preference_cannot_promote_snapshot():
    _, value = await confirmed()
    value.goal.preferences["risk_semantic_profile"] = PROFILE
    with pytest.raises(BindingDenied, match="CONFIRMED_AUTHORITY_MISMATCH"):
        confirmed_risk_authority(value)


@pytest.mark.parametrize(
    "field",
    [
        "run_id",
        "object_id",
        "goal_id",
        "goal_hash",
        "scheme_id",
        "scheme_hash",
        "planned_graph_id",
        "graph_identity",
        "risk_semantic_mode",
        "risk_semantic_contract_version",
        "risk_semantic_contract_digest",
        "scenario_profile_digest",
        "execution_profile_snapshot_digest",
        "execution_snapshot_digest",
        "confirmation_binding_reference",
        "confirmed_at",
        "binding_digest",
    ],
)
async def test_c07_each_receipt_field_tamper(field):
    _, value = await confirmed(preferences={"risk_semantic_profile": PROFILE})
    value.confirmed_risk_semantic_binding = value.confirmed_risk_semantic_binding.model_copy(
        update={field: "tampered"}
    )
    with pytest.raises(BindingDenied):
        confirmed_risk_authority(value)


async def test_c07_rehashed_foreign_identity_and_stale_reference():
    _, value = await confirmed(preferences={"risk_semantic_profile": PROFILE})
    receipt = value.confirmed_risk_semantic_binding
    raw = receipt.model_dump(exclude={"binding_digest"})
    raw["goal_id"] = "foreign"
    value.confirmed_risk_semantic_binding = type(receipt)(
        **raw, binding_digest=digest(raw, receipt.schema_version)
    )
    with pytest.raises(BindingDenied, match="CONFIRMED_AUTHORITY_MISMATCH"):
        confirmed_risk_authority(value)
    value.confirmed_risk_semantic_binding = receipt
    value.node_binding.binding_revision += 1
    with pytest.raises(BindingDenied, match="current binding reference"):
        confirmed_risk_authority(value)


async def test_c08_missing_root_denies_both_entrypoints():
    _, value = await confirmed(preferences={"risk_semantic_profile": PROFILE})
    snapshot = ExecutionSnapshot.model_validate(value.node_binding.execution_snapshot)
    payload = SQLAlchemyApplicationRepository._payload(value)
    payload["node_binding"] = None
    with pytest.raises(BindingDenied, match="AUTHORITY_MISSING"):
        SQLAlchemyApplicationRepository._to_aggregate(payload, 2)
    value.node_binding = None
    for call in (
        lambda: availability_map_for_run(value),
        lambda: availability_map(value),
        lambda: availability_map(value, execution_snapshot=snapshot),
    ):
        with pytest.raises(BindingDenied, match="AUTHORITY_MISSING"):
            call()


async def test_c09_explicit_legacy_rootless_parity():
    _, value = await confirmed()
    baseline = availability_map(value)
    value.node_binding = None
    assert confirmed_risk_authority(value) == ConfirmedRiskAuthority.CONFIRMED_LEGACY
    assert availability_map(value) == availability_map_for_run(value) == baseline


@pytest.mark.parametrize("d01", [False, True])
async def test_c10_c11_c12_explicit_codec_boundary(d01):
    _, value = await confirmed(preferences={"risk_semantic_profile": PROFILE} if d01 else {})
    payload = SQLAlchemyApplicationRepository._payload(value)
    for removed in [
        ("confirmed_risk_semantic_binding",),
        ("confirmed_risk_semantic_binding", "aggregate_schema_version"),
    ]:
        broken = deepcopy(payload)
        for field in removed:
            broken.pop(field)
        with pytest.raises(BindingDenied, match="CONFIRMED_AUTHORITY_CORRUPT"):
            SQLAlchemyApplicationRepository._to_aggregate(broken, 2)
    with pytest.raises(TypeError):
        SQLAlchemyApplicationRepository._to_aggregate(payload)
    with pytest.raises(BindingDenied):
        SQLAlchemyApplicationRepository._to_aggregate(payload, 1)
    historical = deepcopy(payload)
    historical.pop("aggregate_schema_version")
    historical.pop("confirmed_risk_semantic_binding")
    before = deepcopy(historical)
    read = SQLAlchemyApplicationRepository._to_aggregate(historical, 1)
    assert read.confirmed_risk_semantic_binding is None
    assert confirmed_risk_authority(read) == ConfirmedRiskAuthority.HISTORICAL_PRE_BINDING
    assert SQLAlchemyApplicationRepository._payload(read) == before
    assert historical == before


async def prepare_backend(sessions, d01, tmp_path):
    from src.agentic.composition import build_research_agent_registry
    from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
    from tests.unit.agentic.test_adaptive_recovery import Client

    service = ResearchApplicationService(
        agent_registry=build_research_agent_registry(
            Client("teamorouter", "gpt-5.6-sol"),
            ResearchAgentOutputArtifactStore(tmp_path / "agents"),
        ),
        repository=SQLAlchemyApplicationRepository(sessions),
        event_store=PostgresRuntimeEventStore(sessions),
    )
    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    obj = await backend.create_object(
        CreateResearchObjectRequestV1(
            symbol="A1", company_name="Synthetic A1", exchange="LOCAL", currency="USD"
        ),
        idempotency_key="a1-object",
        request_id=None,
    )
    draft = await backend.prepare_run(
        PrepareResearchRunRequestV1(
            research_object_id=obj.object.object_id,
            research_goal="Company fundamental research",
            as_of=date(2026, 9, 17),
            preferences={"risk_semantic_profile": PROFILE} if d01 else {},
        ),
        idempotency_key="a1-prepare",
        request_id=None,
    )
    request = ConfirmResearchRunRequestV1(
        draft_id=draft.draft_id,
        draft_version=draft.draft_version,
        draft_hash=draft.draft_hash,
        research_object_id=draft.object_id,
        confirm_scheme=True,
    )
    return backend, request


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL")
@pytest.mark.parametrize("d01", [False, True])
async def test_c01_c02_c03_product_confirm_fresh_process(database, d01, monkeypatch, tmp_path):  # noqa: F811
    _, sessions = database
    backend, request = await prepare_backend(sessions, d01, tmp_path)
    result = await backend.confirm_run(request, idempotency_key="a1-confirm", request_id=None)
    run_id = result.admission.run_id
    read = await backend.service.repository.get_run_fresh(run_id)
    receipt = read.confirmed_risk_semantic_binding.model_dump(mode="json")
    assert receipt["risk_semantic_mode"] == ("D01_V1" if d01 else "LEGACY")
    async with sessions() as session:
        schema = await session.scalar(text("select current_schema()"))
        row = await session.get(ResearchRunAggregateRow, run_id)
        assert row.aggregate_schema_version == row.payload["aggregate_schema_version"] == 2
    script = """
import asyncio,json,os,sys
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.application.persistence import SQLAlchemyApplicationRepository
async def main():
 e=create_async_engine(os.environ["TEST_POSTGRESQL_URL"],connect_args={"server_settings":{"search_path":sys.argv[1]}})
 r=await SQLAlchemyApplicationRepository(async_sessionmaker(e)).get_run_fresh(sys.argv[2])
 print(json.dumps(r.confirmed_risk_semantic_binding.model_dump(mode="json"),sort_keys=True))
 await e.dispose()
asyncio.run(main())
"""
    output = await asyncio.to_thread(
        subprocess.check_output, [sys.executable, "-c", script, schema, run_id], text=True
    )
    assert json.loads(output) == receipt

    def forbidden(*args, **kwargs):
        raise AssertionError("idempotent replay must not resolve or plan")

    monkeypatch.setattr("src.application.execution_profiles.resolve_execution_snapshot", forbidden)
    monkeypatch.setattr(backend.service.planner, "plan", forbidden)
    replay = await backend.confirm_run(request, idempotency_key="a1-confirm", request_id=None)
    assert replay.admission == result.admission
    assert (
        await backend.service.repository.get_run_fresh(run_id)
    ).confirmed_risk_semantic_binding == read.confirmed_risk_semantic_binding


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL")
@pytest.mark.parametrize("fault", ["receipt", "after_insert", "before_commit", "response_loss"])
async def test_c13_product_atomicity(database, monkeypatch, fault, tmp_path):  # noqa: F811
    from src.application.persistence import ResearchSchemeSnapshotRow, RuntimeEventRow, TaskRow
    from src.infrastructure.database import phase4_product as owner

    _, sessions = database
    backend, request = await prepare_backend(sessions, True, tmp_path)
    if fault == "receipt":
        original = owner._aggregate_payload

        def fail(commit):
            original(commit)
            raise RuntimeError("A1 injected receipt failure")

        monkeypatch.setattr(owner, "_aggregate_payload", fail)
    elif fault == "after_insert":
        original = owner.SQLAlchemyPhase4AdmissionRepository.insert_confirm_commit

        async def fail(self, commit):
            await original(self, commit)
            await self.session.flush()
            raise RuntimeError("A1 injected after insert")

        monkeypatch.setattr(
            owner.SQLAlchemyPhase4AdmissionRepository, "insert_confirm_commit", fail
        )
    else:
        original = owner.PostgreSQLProductUnitOfWork.commit

        async def fail(self):
            if fault == "response_loss":
                await original(self)
            raise RuntimeError("A1 injected commit boundary")

        monkeypatch.setattr(owner.PostgreSQLProductUnitOfWork, "commit", fail)
    with pytest.raises(RuntimeError, match="A1 injected"):
        await backend.confirm_run(request, idempotency_key="a1-confirm", request_id=None)
    async with sessions() as session:
        for model in (ResearchRunAggregateRow, Phase4SchedulerAdmissionRow):
            count = await session.scalar(select(func.count()).select_from(model))
            assert count == int(fault == "response_loss")
        count = await session.scalar(
            select(func.count())
            .select_from(Phase4IdempotencyOutcomeRow)
            .where(Phase4IdempotencyOutcomeRow.kind == "CONFIRM")
        )
        assert count == int(fault == "response_loss")
        draft = await session.get(ResearchRunDraftRow, request.draft_id)
        assert (draft.consumed_at is not None) == (fault == "response_loss")
        scheme = await session.get(
            ResearchSchemeSnapshotRow, draft.payload["scheme_snapshot"]["scheme_id"]
        )
        assert scheme.confirmed == (fault == "response_loss")
        for model in (
            owner.Phase4PlannedGraphRow,
            owner.Phase4ActualGraphRow,
            TaskRow,
            RuntimeEventRow,
        ):
            count = await session.scalar(select(func.count()).select_from(model))
            assert (count > 0) == (fault == "response_loss")
    before_replay = None
    if fault == "response_loss":
        async with sessions() as session:
            before_replay = deepcopy(
                (await session.scalar(select(ResearchRunAggregateRow))).payload
            )
    monkeypatch.undo()
    if fault == "response_loss":

        def forbidden(*args, **kwargs):
            raise AssertionError("response-loss replay must not recreate confirmation")

        monkeypatch.setattr(backend.service.planner, "plan", forbidden)
        monkeypatch.setattr(
            "src.application.execution_profiles.resolve_execution_snapshot", forbidden
        )
    result = await backend.confirm_run(request, idempotency_key="a1-confirm", request_id=None)
    read = await backend.service.repository.get_run_fresh(result.admission.run_id)
    assert confirmed_risk_authority(read) == ConfirmedRiskAuthority.CONFIRMED_D01_V1
    if before_replay is not None:
        assert SQLAlchemyApplicationRepository._payload(read) == before_replay


async def test_c05_resolution_mismatch_rolls_back_memory(monkeypatch):
    from src.application import execution_profiles

    resolver = execution_profiles.resolve_execution_snapshot

    def omit_resolved_contract(scheme, goal, tasks, service=None):
        snapshot = resolver(scheme, goal, tasks, service)
        scenario = snapshot.scenario.model_copy(update={"risk_semantic_contract": None})
        return ExecutionSnapshot.freeze(scenario, snapshot.nodes)

    monkeypatch.setattr(execution_profiles, "resolve_execution_snapshot", omit_resolved_contract)
    service = ResearchApplicationService()
    obj = await service.create_object(symbol="MISMATCH", company_name="Synthetic", exchange="LOCAL")
    draft = await service.prepare_run(
        research_object_id=obj.object_id,
        research_goal="Company fundamental research",
        as_of=date(2026, 9, 17),
        preferences={"risk_semantic_profile": PROFILE},
    )
    with pytest.raises(BindingDenied, match="requested/resolved"):
        await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    assert await service.repository.list_runs_for_object(obj.object_id) == []


async def test_c10_in_memory_downgrade_is_not_historical():
    service, value = await confirmed()
    value.aggregate_schema_version = 1
    value.confirmed_risk_semantic_binding = None
    with pytest.raises(BindingDenied, match="CONFIRMED_AUTHORITY_CORRUPT"):
        confirmed_risk_authority(value)
    with pytest.raises(BindingDenied):
        await service.repository.save_run(value)


async def test_c09_exact_head_lightweight_dictionary_parity():
    import types

    from src.application.models import CompletedRunArtifacts
    from src.domain.agent_output import ResearchAgentOutputRecord

    source = await asyncio.to_thread(
        subprocess.check_output,
        [
            "git",
            "show",
            "8e611c3432b8ac6ecd6181f544e4bfdc2dcaf990:src/application/research_outputs.py",
        ],
        text=True,
    )
    baseline = types.ModuleType("a1_head_projection")
    exec(compile(source, "HEAD:src/application/research_outputs.py", "exec"), baseline.__dict__)
    _, value = await confirmed()
    legacy = types.SimpleNamespace(runtime=value.runtime, artifacts=CompletedRunArtifacts())
    assert availability_map(legacy) == baseline.availability_map(legacy)
    risk = next(t for t in value.runtime.actual_graph.tasks if t.task_type == "risk_analysis")
    # Populate real validated artifact values using the existing production model.
    fields = ResearchAgentOutputRecord.model_fields
    assert "status" in fields and risk.run_id == value.run.run_id
    value.node_binding = None
    assert availability_map_for_run(value) == baseline.availability_map(value)


async def test_c14_terra_explicit_version_replay(monkeypatch):
    from src.application import execution_profiles as profiles

    service, value = await confirmed(preferences={"risk_semantic_profile": PROFILE})
    before = SQLAlchemyApplicationRepository._payload(value)
    monkeypatch.setattr(profiles, "accepted_terra_proof", lambda *args, **kwargs: None)
    restored = SQLAlchemyApplicationRepository._to_aggregate(deepcopy(before), 2)
    assert SQLAlchemyApplicationRepository._payload(restored) == before
    for task in restored.runtime.actual_graph.tasks:
        assert profiles.frozen_profile(restored, task) == profiles.frozen_profile(value, task)


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL")
async def test_c11_c12_migration_preserves_synthetic_old_bytes(database):  # noqa: F811
    import importlib.util
    from pathlib import Path
    from uuid import uuid4

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.exc import IntegrityError

    engine, _ = database
    _, value = await confirmed()
    old = SQLAlchemyApplicationRepository._payload(value)
    old.pop("aggregate_schema_version")
    old.pop("confirmed_risk_semantic_binding")
    raw = json.dumps(old, separators=(",", ":"), ensure_ascii=False)
    schema = "a1_old_" + uuid4().hex
    path = Path("alembic/versions/20260921_0018_confirmed_risk_authority.py")
    spec = importlib.util.spec_from_file_location("a1_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def migrate(conn):
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()

    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        await conn.execute(
            text("CREATE TABLE research_runs(run_id TEXT PRIMARY KEY, payload JSON)")
        )
        await conn.execute(
            text("INSERT INTO research_runs VALUES ('synthetic-old',CAST(:p AS JSON))"), {"p": raw}
        )
        await conn.run_sync(migrate)
        row = (
            await conn.execute(
                text("SELECT payload::text, aggregate_schema_version FROM research_runs")
            )
        ).one()
        assert row[0] == raw and row[1] == 1
        decoded = SQLAlchemyApplicationRepository._to_aggregate(json.loads(row[0]), row[1])
        assert decoded.confirmed_risk_semantic_binding is None
        for version in (None, 0, 3):
            with pytest.raises(IntegrityError):
                async with conn.begin_nested():
                    await conn.execute(
                        text(
                            "INSERT INTO research_runs(run_id,payload,aggregate_schema_version) "
                            "VALUES ('invalid','{}',:version)"
                        ),
                        {"version": version},
                    )
        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL")
async def test_c07_lawful_replan_preserves_initial_receipt(database, tmp_path):  # noqa: F811
    from src.application.execution import IntegratedTaskExecutor
    from src.domain.research_scheme import ResearchSchemeSnapshot
    from src.domain.task import PlannedTaskGraph
    from src.infrastructure.database.recovery import RecoveryEvidenceStore
    from src.runtime.scheduler import DependencyScheduler
    from tests.risk_replan.test_flow import command
    from tests.risk_replan.test_flow import fixture as replan_transport

    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, template, calls, transport = await replan_transport(
        tmp_path,
        repository=repo,
        store=RecoveryEvidenceStore(sessions),
        sessions=sessions,
        complete_requirements=True,
        minimal_risk=True,
        persist=False,
    )

    class SyntheticScheme:
        async def generate(self, *, research_object, goal):
            raw = template.scheme.model_dump(mode="json")
            raw.update(
                scheme_id="SCHEME-A1-REPLAN",
                goal_id=goal.goal_id,
                research_object_id=research_object.object_id,
                confirmed_at=None,
            )
            return ResearchSchemeSnapshot.model_validate(raw)

    class SyntheticPlanner:
        def plan(self, *, run_id, goal, scheme):
            raw = json.loads(
                json.dumps(template.runtime.planned_graph.model_dump(mode="json")).replace(
                    template.run.run_id, run_id
                )
            )
            raw["graph_id"] = "PLAN-" + run_id
            return PlannedTaskGraph.model_validate(raw)

    service.scheme_generator = SyntheticScheme()
    service.planner = SyntheticPlanner()
    obj = await service.create_object(symbol="REPLAN", company_name="Synthetic", exchange="LOCAL")
    draft = await service.prepare_run(
        research_object_id=obj.object_id,
        research_goal="Synthetic lawful Risk Replan",
        as_of=template.goal.as_of,
        preferences={"risk_semantic_profile": PROFILE},
    )
    value = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    receipt = value.confirmed_risk_semantic_binding
    run_id = value.run.run_id
    with transport:
        value = await service.execute_run(run_id)
        assert value.node_binding.replan is not None
        await repo.decide_replan(
            run_id, command(value, "APPROVE"), actor="LOCAL_SINGLE_USER", key="a1-replan"
        )
        await repo.apply_replan(run_id)
        value = await repo.get_run_fresh(run_id)
        assert value.confirmed_risk_semantic_binding == receipt
        confirmed_risk_authority(value)
        original = deepcopy(value.node_binding.replan)
        value.node_binding.replan["transition"]["old_graph_snapshot"]["graph_id"] = "foreign"
        value.runtime.binding_ref = value.node_binding.reference()
        with pytest.raises(BindingDenied):
            confirmed_risk_authority(value)
        value.node_binding.replan = original
        owner = await repo.claim_execution(run_id)
        value = await repo.get_run_fresh(run_id)
        await DependencyScheduler(
            event_store=service.event_store,
            checkpoint_store=service.checkpoint_store,
            admission_repository=repo,
            execution_owner=owner,
        ).execute(state=value.runtime, executor=IntegratedTaskExecutor(service, value))
    value = await repo.get_run_fresh(run_id)
    assert value.confirmed_risk_semantic_binding == receipt
    confirmed_risk_authority(value)
    assert next(iter(value.node_binding.risk_admissions.values()))["decision"] == "FINAL_SUCCESS"
    assert sum(kind == "report_synthesis" for kind, _ in calls) == 1


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL")
async def test_c13_alternate_confirm_add_run_atomicity(database, tmp_path, monkeypatch):  # noqa: F811
    _, sessions = database
    backend, _ = await prepare_backend(sessions, True, tmp_path)
    service = backend.service
    obj = await service.create_object(
        symbol="ALTERNATE", company_name="Synthetic", exchange="LOCAL"
    )
    draft = await service.prepare_run(
        research_object_id=obj.object_id,
        research_goal="Company fundamental research",
        as_of=date(2026, 9, 17),
        preferences={"risk_semantic_profile": PROFILE},
    )
    persist = service.repository._persist_children

    async def failed(session, aggregate):
        await persist(session, aggregate)
        await session.flush()
        raise RuntimeError("A1 alternate Confirm rollback")

    monkeypatch.setattr(service.repository, "_persist_children", failed)
    with pytest.raises(RuntimeError, match="alternate Confirm rollback"):
        await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ResearchRunAggregateRow)) == 0
    monkeypatch.setattr(service.repository, "_persist_children", persist)
    value = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    fresh = await SQLAlchemyApplicationRepository(sessions).get_run_fresh(value.run.run_id)
    assert fresh.confirmed_risk_semantic_binding == value.confirmed_risk_semantic_binding


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL")
async def test_c09_production_legacy_complete_dictionary_head_parity(database, tmp_path):  # noqa: F811
    import types

    from src.application.execution import IntegratedTaskExecutor
    from src.runtime.scheduler import DependencyScheduler
    from tests.risk_minimal.test_production import fixture

    _, sessions = database
    service, value, _ = await fixture(tmp_path, sessions, legacy=True)
    owner = await service.repository.claim_execution(value.run.run_id)
    value = await service.repository.get_run_fresh(value.run.run_id)
    await DependencyScheduler(
        event_store=service.event_store,
        checkpoint_store=service.checkpoint_store,
        admission_repository=service.repository,
        execution_owner=owner,
    ).execute(state=value.runtime, executor=IntegratedTaskExecutor(service, value))
    value = await service.repository.get_run_fresh(value.run.run_id)
    source = await asyncio.to_thread(
        subprocess.check_output,
        [
            "git",
            "show",
            "8e611c3432b8ac6ecd6181f544e4bfdc2dcaf990:src/application/research_outputs.py",
        ],
        text=True,
    )
    baseline = types.ModuleType("a1_head_full_projection")
    exec(compile(source, "HEAD:src/application/research_outputs.py", "exec"), baseline.__dict__)
    assert value.artifacts.agent_outputs
    lightweight = types.SimpleNamespace(runtime=value.runtime, artifacts=value.artifacts)
    baseline_view = types.SimpleNamespace(
        runtime=value.runtime, artifacts=value.artifacts, node_binding=None
    )
    for task in [None, *value.runtime.actual_graph.tasks]:
        expected = baseline.availability_map(baseline_view, task)
        assert availability_map(lightweight, task) == expected
        assert availability_map(value, task) == expected
    value.node_binding = None
    assert availability_map_for_run(value) == baseline.availability_map(baseline_view)
    with pytest.raises(BindingDenied):
        availability_map_for_run(lightweight)


async def test_c14_original_terra_replay_assertions_with_versioned_codec(terra_d01, monkeypatch):  # noqa: F811
    from src.application import execution_profiles as profiles
    from tests.execution_profiles.test_d01_proof_binding import matches

    service, value, _, expected_profile, context, _, _, _ = terra_d01
    before = json.dumps(
        SQLAlchemyApplicationRepository._payload(value), sort_keys=True, default=str
    )
    monkeypatch.setattr(profiles, "accepted_terra_proof", lambda *args, **kwargs: None)
    restored = SQLAlchemyApplicationRepository._to_aggregate(
        json.loads(json.dumps(SQLAlchemyApplicationRepository._payload(value))), 2
    )
    assert profiles.validate_runtime_profile(service, restored, context.task) == expected_profile
    assert matches(terra_d01, profile=profiles.frozen_profile(restored, context.task))
    assert (
        json.dumps(SQLAlchemyApplicationRepository._payload(value), sort_keys=True, default=str)
        == before
    )


async def test_c07_foreign_durable_run_identity():
    _, value = await confirmed(preferences={"risk_semantic_profile": PROFILE})
    row = SQLAlchemyApplicationRepository._row(value)
    row.run_id = "foreign-storage-key"
    with pytest.raises(BindingDenied, match="durable Run identity"):
        SQLAlchemyApplicationRepository._from_row(row)


async def test_c03_c10_closed_receipt_and_canonical_order():
    from src.domain.risk_admission import ConfirmedRiskSemanticBindingV1

    _, value = await confirmed(preferences={"risk_semantic_profile": PROFILE})
    receipt = value.confirmed_risk_semantic_binding
    raw = receipt.model_dump(mode="json")
    reverse = dict(reversed(list(raw.items())))
    assert ConfirmedRiskSemanticBindingV1.model_validate(reverse) == receipt
    for key in raw:
        broken = dict(raw)
        del broken[key]
        with pytest.raises(ValueError):
            ConfirmedRiskSemanticBindingV1.model_validate(broken)
    with pytest.raises(ValueError):
        ConfirmedRiskSemanticBindingV1.model_validate({**raw, "unrecognized": True})
    for bad in (True, None, 0, 3, "2"):
        payload = SQLAlchemyApplicationRepository._payload(value)
        payload["aggregate_schema_version"] = bad
        with pytest.raises(BindingDenied, match="CONFIRMED_AUTHORITY_CORRUPT"):
            SQLAlchemyApplicationRepository._to_aggregate(payload, 2)


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL")
async def test_c14_d01_resume_keeps_confirmation_receipt(database, tmp_path):  # noqa: F811
    from src.application.execution import IntegratedTaskExecutor
    from src.application.persistence import SessionFactoryEvidenceRepository
    from src.application.resume_runtime import current_risk_success
    from src.infrastructure.database.recovery import RecoveryEvidenceStore
    from src.runtime.scheduler import DependencyScheduler
    from tests.external_failure_resume.runtime_fixture import exhaust, legal_fixture, request_for

    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, clients = await legal_fixture(
        tmp_path,
        repository=repo,
        evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions),
        event_store=PostgresRuntimeEventStore(sessions),
        minimal=True,
    )
    confirmation = value.confirmed_risk_semantic_binding
    failed = await exhaust(service, value)
    request = await request_for(service, failed)
    await repo.resume_external_failure(request, actor=request.actor)
    for client in clients.values():
        client.fail_risk = False
    owner = await repo.claim_execution(value.run.run_id)
    pending = await repo.get_run_fresh(value.run.run_id)
    await DependencyScheduler(
        event_store=service.event_store,
        checkpoint_store=service.checkpoint_store,
        admission_repository=repo,
        execution_owner=owner,
    ).execute(state=pending.runtime, executor=IntegratedTaskExecutor(service, pending))
    fresh = await repo.get_run_fresh(value.run.run_id)
    assert current_risk_success(fresh)
    assert fresh.confirmed_risk_semantic_binding == confirmation
    assert next(iter(fresh.node_binding.risk_admissions.values()))["scope"]["cycle"] != "INITIAL"
    fresh.node_binding.risk_admissions = None
    with pytest.raises(BindingDenied, match="CONFIRMED_AUTHORITY_MISMATCH"):
        current_risk_success(fresh)
