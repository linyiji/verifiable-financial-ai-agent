"""Backend contract fixtures: lawful Confirm and production owners, offline bytes only."""

import os
from copy import deepcopy
from datetime import date
from functools import partial
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters.finrobot.professional_reporting import (
    ControlledArtifactStore,
    ProfessionalReportPublisher,
)
from src.application.persistence import (
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.application.service import ResearchApplicationService
from src.data.artifacts import LocalRawArtifactStore
from src.data.ingestion import EvidenceIngestionService
from src.domain.node_binding import BindingDenied
from src.infrastructure.database.base import Base
from src.infrastructure.database.recovery import RecoveryEvidenceRow, RecoveryEvidenceStore
from src.runtime.events import InMemoryRuntimeEventStore
from tests.risk_replan.test_flow import fixture

DEFAULT_PROOF_HOST = (
    Path(__file__).resolve().parents[2]
    / "zk/revenue_growth/target/release/revenue-growth-proof-host"
)


async def durable_snapshot(sessions, run_id):
    """Fresh connection: root, projection counters, records, ledger and events."""
    async with sessions() as session:
        result = {}
        for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
            if "run_id" not in table.c:
                continue
            rows = (
                (
                    await session.execute(
                        select(table).where(table.c.run_id == run_id).order_by(*table.primary_key)
                    )
                )
                .mappings()
                .all()
            )
            result[table.name] = [deepcopy(dict(row)) for row in rows]
        return result


async def full_fixture(tmp_path, sessions, monkeypatch, *, sqlite=False):
    repo = SQLAlchemyApplicationRepository(sessions)
    service, _, calls, transport = await fixture(
        tmp_path,
        repository=repo,
        store=RecoveryEvidenceStore(sessions),
        sessions=sessions,
        persist=False,
    )
    # Retain the original four input observations and genuine period correction.
    default = ResearchApplicationService(
        repository=repo, evidence_repository=SessionFactoryEvidenceRepository(sessions)
    )
    service.evidence_collector = default.evidence_collector
    monkeypatch.setattr(
        "src.application.evidence_collection.EvidenceIngestionService",
        partial(EvidenceIngestionService, artifact_store=LocalRawArtifactStore(tmp_path / "raw")),
    )
    service.report_publisher = ProfessionalReportPublisher(
        ControlledArtifactStore(tmp_path / "reports")
    )
    if not sqlite:
        from src.adapters.risc0 import RiscZeroProofAdapter
        from src.application.phase3_proof import RevenueGrowthRiscZeroProofWorkflow
        from src.infrastructure.database.phase3_records import SQLAlchemyPhase3RecordRepository

        proof_root = tmp_path / "proofs"
        host = Path(os.environ.get("TEST_RISC0_HOST_BINARY", str(DEFAULT_PROOF_HOST)))
        # Actual pinned local prover; no fake receipt or weakened host/image pins.
        service.proof_workflow = RevenueGrowthRiscZeroProofWorkflow(
            adapter=RiscZeroProofAdapter(host_binary=host, artifact_dir=proof_root),
            artifact_dir=proof_root,
            event_store=service.event_store,
            repository=SQLAlchemyPhase3RecordRepository(sessions),
        )
    if sqlite:
        service.event_store = InMemoryRuntimeEventStore()
        planner = service.planner

        class SerialPlanner:
            def plan(self, **kwargs):
                graph = planner.plan(**kwargs)
                pending, ordered, seen = list(graph.tasks), [], set()
                while pending:
                    task = next(t for t in pending if set(t.dependencies) <= seen)
                    pending.remove(task)
                    if ordered:
                        task.dependencies = list(
                            dict.fromkeys([*task.dependencies, ordered[-1].task_id])
                        )
                    ordered.append(task)
                    seen.add(task.task_id)
                graph.tasks = ordered
                return graph

        # SQLite has no row locks; serial dependencies are frozen before Confirm.
        service.planner = SerialPlanner()
    obj = await service.create_object(symbol="NVDA", company_name="Synthetic", exchange="LOCAL")
    draft = await service.prepare_run(
        research_object_id=obj.object_id,
        research_goal="Conserve durable full release",
        as_of=date(2026, 9, 4),
        preferences={
            "report_metric_requirements": {
                "schema_version": "frozen-report-metric-requirements/v1",
                "report_mode": "METRIC_FOCUSED",
                "required_metric_ids": ["revenue_growth_v1"],
                "period": "FY2026",
            }
        },
    )
    value = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    assert value.confirmed_risk_semantic_binding is not None
    return service, value, calls, transport, draft


async def assert_sqlite_replan_denied(tmp_path, monkeypatch):
    # Equivalent predicate for create_all in temporary SQLite only. Production
    # metadata is restored by monkeypatch; no migration/capability is changed.
    index = next(
        i for i in RecoveryEvidenceRow.__table__.indexes if i.name == "phase6_recovery_single_entry"
    )
    monkeypatch.setitem(
        index.dialect_options["sqlite"],
        "where",
        text(
            "json_extract(payload, '$.kind')='ATTEMPT_STARTED' AND "
            "json_extract(payload, '$.attempt_number')=1 AND "
            "json_extract(payload, '$.capability_check')=0"
        ),
    )
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'backend-denial.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        service, value, _, transport, _ = await full_fixture(
            tmp_path, sessions, monkeypatch, sqlite=True
        )
        repo, run_id = service.repository, value.run.run_id
        original = repo.commit_node_result
        observed = []
        published = []
        emit = service.event_store.emit

        async def spy(**kwargs):
            published.append(deepcopy(kwargs))
            return await emit(**kwargs)

        monkeypatch.setattr(service.event_store, "emit", spy)

        async def capture(*args, **kwargs):
            task = args[1] if len(args) > 1 else kwargs["task"]
            if task.task_type != "risk_analysis":
                return await original(*args, **kwargs)
            before = await durable_snapshot(sessions, run_id)
            root = await SQLAlchemyApplicationRepository(sessions).get_run_fresh(run_id)
            external_before = deepcopy(published)
            assert root.node_binding.replan is None
            assert root.run.status.value not in {"RELEASED", "FAILED", "CANCELLED"}
            with pytest.raises(BindingDenied) as denial:
                await original(*args, **kwargs)
            assert denial.value.code == "REPLAN_POSTGRESQL_AUTHORITY_REQUIRED"
            assert await durable_snapshot(sessions, run_id) == before
            after = await SQLAlchemyApplicationRepository(sessions).get_run_fresh(run_id)
            assert after.node_binding == root.node_binding
            assert after.run == root.run
            assert after.runtime == root.runtime
            assert after.artifacts.replans == root.artifacts.replans == []
            assert published == external_before
            observed.append(denial.value.code)
            # Subsequent scheduler failure settlement is a separate transaction;
            # BR02-05 above measure only the directly attempted capture boundary.
            raise denial.value

        monkeypatch.setattr(repo, "commit_node_result", capture)
        with transport, pytest.raises((BindingDenied, ExceptionGroup)) as failure:
            await service.execute_run(run_id)
        leaves = [failure.value]
        codes = []
        while leaves:
            leaf = leaves.pop()
            if isinstance(leaf, BaseExceptionGroup):
                leaves.extend(leaf.exceptions)
            else:
                codes.append(getattr(leaf, "code", type(leaf).__name__))
        assert observed == ["REPLAN_POSTGRESQL_AUTHORITY_REQUIRED"]
        assert "REPLAN_POSTGRESQL_AUTHORITY_REQUIRED" in codes
    finally:
        await engine.dispose()
