"""Disposable PostgreSQL proofs for the production AtomicConfirmCommit path."""

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from src.application.persistence import ResearchRunAggregateRow, SQLAlchemyApplicationRepository
from src.application.repository import validate_root
from src.application.service import ResearchApplicationService
from src.infrastructure.database.phase4_product import SQLAlchemyPhase4AdmissionRepository
from src.phase4_product.contracts import ConfirmResearchRunRequestV1, PrepareResearchRunRequestV1
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("PROFILE_BINDING_DISPOSABLE_DATABASE"),
    reason="Explicit disposable profile test database required",
)


async def prepared(db):
    _, sessions = db
    async with sessions() as session:
        directory = (await session.execute(text("SHOW data_directory"))).scalar_one()
        assert "execute-the-user-s-complete-authoritative/work/postgres-profile/data" in directory
        assert (
            await session.execute(text("SELECT current_database()"))
        ).scalar_one() == "vefin_profile_disposable"
    repository = SQLAlchemyApplicationRepository(sessions)
    from src.agentic.composition import build_research_agent_registry
    from tests.unit.agentic.test_adaptive_recovery import Client

    registry = build_research_agent_registry(Client("teamorouter", "gpt-5.6-sol"), None)
    service = ResearchApplicationService(repository=repository, agent_registry=registry)
    obj = await service.create_object(
        symbol="ALPHA", company_name="Offline company", exchange="LOCAL"
    )
    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    draft = await backend.prepare_run(
        PrepareResearchRunRequestV1(
            research_object_id=obj.object_id,
            research_goal="Fundamental research",
            as_of=date(2026, 9, 17),
            preferences={},
        ),
        idempotency_key="prepare",
        request_id=None,
    )
    request = ConfirmResearchRunRequestV1(
        draft_id=draft.draft_id,
        draft_version=draft.draft_version,
        draft_hash=draft.draft_hash,
        research_object_id=obj.object_id,
        confirm_scheme=True,
    )
    return backend, request


async def test_cases_02_03_postgresql_commit_restart_fresh_lookup(database, tmp_path):  # noqa: F811
    backend, request = await prepared(database)
    response = await backend.confirm_run(request, idempotency_key="confirm", request_id=None)
    run_id = response.admission.run_id
    value = await backend.service.repository.get_run_fresh(run_id)
    validate_root(value)
    expected = [
        value.node_binding.scenario_snapshot_digest,
        value.node_binding.execution_profile_snapshot_digest,
    ]
    replay = await backend.confirm_run(request, idempotency_key="confirm", request_id=None)
    assert replay.admission.run_id == run_id
    engine, _ = database
    schema = engine.url.query.get("search_path")
    async with backend.sessions() as session:
        schema = (await session.execute(text("SELECT current_schema()"))).scalar_one()
    script = """import asyncio,json,sys
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.application.persistence import SQLAlchemyApplicationRepository as R
from src.application.repository import validate_root
from src.application.execution_profiles import frozen_profile
async def main():
 e=create_async_engine(sys.argv[1],connect_args={"server_settings":{"search_path":sys.argv[2]}})
 r=R(async_sessionmaker(e,expire_on_commit=False))
 v=await r.get_run_fresh(sys.argv[3]); validate_root(v)
 for t in v.runtime.actual_graph.tasks: frozen_profile(v,t)
 print(json.dumps([v.node_binding.scenario_snapshot_digest,v.node_binding.execution_profile_snapshot_digest]))
 await e.dispose()
asyncio.run(main())"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        os.environ["TEST_POSTGRESQL_URL"],
        schema,
        run_id,
        stdout=asyncio.subprocess.PIPE,
    )
    output, _ = await process.communicate()
    assert process.returncode == 0 and json.loads(output) == expected
    destination = os.environ.get("PROFILE_BINDING_RECEIPT_DIR")
    if destination:
        target = Path(destination)
        await asyncio.to_thread(target.mkdir, parents=True, exist_ok=True)
        (target / "postgres-committed-binding.json").write_text(
            json.dumps(SQLAlchemyApplicationRepository._payload(value), indent=2)
        )
        (target / "postgres-fresh-process.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "expected_digests": expected,
                    "fresh_process_digests": json.loads(output),
                    "returncode": process.returncode,
                    "idempotency_replay_run_id": replay.admission.run_id,
                },
                indent=2,
            )
        )


async def test_confirm_profile_failure_rolls_back_entire_write_set(database, monkeypatch):  # noqa: F811
    backend, request = await prepared(database)
    original = SQLAlchemyPhase4AdmissionRepository.insert_confirm_commit

    async def fail_after_writes(self, commit):
        assert commit.execution_snapshot is not None
        await original(self, commit)
        await self.session.flush()
        raise RuntimeError("Injected after full Confirm write set")

    monkeypatch.setattr(
        SQLAlchemyPhase4AdmissionRepository, "insert_confirm_commit", fail_after_writes
    )
    with pytest.raises(RuntimeError, match="Injected"):
        await backend.confirm_run(request, idempotency_key="confirm", request_id=None)
    from src.application.persistence import (
        ResearchRunDraftRow,
        ResearchSchemeSnapshotRow,
        RuntimeEventRow,
        TaskRow,
    )
    from src.infrastructure.database.phase4_product import (
        Phase4ActualGraphRow,
        Phase4PlannedGraphRow,
        Phase4SchedulerAdmissionRow,
    )

    async with backend.sessions() as session:
        counts = {
            model.__name__: await session.scalar(select(func.count()).select_from(model))
            for model in (
                ResearchRunAggregateRow,
                TaskRow,
                RuntimeEventRow,
                Phase4ActualGraphRow,
                Phase4PlannedGraphRow,
                Phase4SchedulerAdmissionRow,
            )
        }
        counts["confirmed_schemes"] = await session.scalar(
            select(func.count())
            .select_from(ResearchSchemeSnapshotRow)
            .where(ResearchSchemeSnapshotRow.confirmed.is_(True))
        )
        counts["consumed_drafts"] = await session.scalar(
            select(func.count())
            .select_from(ResearchRunDraftRow)
            .where(ResearchRunDraftRow.consumed_at.is_not(None))
        )
    assert all(count == 0 for count in counts.values())
    destination = os.environ.get("PROFILE_BINDING_RECEIPT_DIR")
    if destination:
        target = Path(destination)
        await asyncio.to_thread(target.mkdir, parents=True, exist_ok=True)
        (target / "postgres-rollback.json").write_text(json.dumps(counts, indent=2))
    monkeypatch.setattr(SQLAlchemyPhase4AdmissionRepository, "insert_confirm_commit", original)
    response = await backend.confirm_run(request, idempotency_key="confirm", request_id=None)
    value = await backend.service.repository.get_run_fresh(response.admission.run_id)
    validate_root(value)


async def test_explicit_allowed_terra_node_persists_selection(database):  # noqa: F811
    from src.agentic.planner import ResearchLeadPlanner
    from src.agentic.scheme import DeterministicSchemeGenerator
    from tests.unit.agentic.test_adaptive_recovery import Client

    backend, _ = await prepared(database)

    class FocusScheme(DeterministicSchemeGenerator):
        async def generate(self, **kwargs):
            scheme = await super().generate(**kwargs)
            return scheme.model_copy(
                update={"skill_requirements": ["evidence_collection_v1", "fundamental_analysis_v1"]}
            )

    class FocusPlanner(ResearchLeadPlanner):
        def plan(self, **kwargs):
            graph = super().plan(**kwargs)
            return graph.model_copy(
                update={
                    "tasks": [
                        t
                        for t in graph.tasks
                        if t.task_type in {"evidence_collection", "fundamental_analysis"}
                    ]
                }
            )

    backend.service.scheme_generator = FocusScheme()
    backend.service.planner = FocusPlanner()
    backend.service.selected_provider_factory = lambda route: Client("teamorouter", "gpt-5.6-terra")
    draft = await backend.prepare_run(
        PrepareResearchRunRequestV1(
            research_object_id="OBJ-ALPHA",
            research_goal="Focused fundamental analysis",
            as_of=date(2026, 9, 17),
            preferences={"model_selection": {"route_id": "teamorouter-terra"}},
        ),
        idempotency_key="focused",
        request_id=None,
    )
    response = await backend.confirm_run(
        ConfirmResearchRunRequestV1(
            draft_id=draft.draft_id,
            draft_version=draft.draft_version,
            draft_hash=draft.draft_hash,
            research_object_id="OBJ-ALPHA",
            confirm_scheme=True,
        ),
        idempotency_key="terra",
        request_id=None,
    )
    value = await SQLAlchemyApplicationRepository(backend.sessions).get_run_fresh(
        response.admission.run_id
    )
    from src.application.execution_profiles import frozen_profile, validate_runtime_profile

    task = next(
        t for t in value.runtime.actual_graph.tasks if t.task_type == "fundamental_analysis"
    )
    profile = frozen_profile(value, task)
    assert profile.requested_route == profile.resolved_route == "teamorouter-terra"
    assert profile.selection_origin == "USER_EXPLICIT"
    assert profile.recovery_fallback_routes == ()
    validate_runtime_profile(backend.service, value, task)
