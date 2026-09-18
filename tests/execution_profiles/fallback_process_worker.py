"""Independent local-only writer/resumer/Confirm reader; no real provider clients."""

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.execution_profiles import frozen_profile
from src.application.persistence import SQLAlchemyApplicationRepository
from src.application.repository import validate_root
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from src.phase4_product.contracts import ConfirmResearchRunRequestV1, PrepareResearchRunRequestV1
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from tests.execution_profiles.fallback_fixture import configured_family


async def main():
    url, schema, directory, kind, phase = sys.argv[1:]
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        assert (
            await session.scalar(text("SELECT current_database()")) == "vefin_fallback_disposable"
        )
        assert engine.url.host == "127.0.0.1"
    repository = SQLAlchemyApplicationRepository(sessions)
    store = RecoveryEvidenceStore(sessions)
    service, fixture, collector, clients = await configured_family(
        Path(directory),
        kind,
        repository=repository,
        store=store,
        sessions=sessions,
        persist=phase == "A",
    )
    if phase in {"A", "B"}:
        before = await repository.get_run_fresh(fixture.run.run_id)
        result = await service.execute_run(fixture.run.run_id)
        root = result.node_binding
        target = result.runtime.actual_graph.tasks[1]
        validate_root(result)
        receipt = dict(
            pid=os.getpid(),
            phase=phase,
            run_id=result.run.run_id,
            root=root.model_dump(mode="json"),
            before_root=before.node_binding.model_dump(mode="json"),
            calls={k: c.calls for k, c in clients.items()},
            upstream_calls=collector.calls,
            records=[r.model_dump(mode="json") for r in await store.records(result.run.run_id)],
            profile=frozen_profile(result, target).model_dump(mode="json"),
        )
        if phase == "A":
            assert root.lifecycle == "RECOVERY_PENDING" and collector.calls == 1
        else:
            assert len(root.current_results) == 2 and collector.calls == 0
            assert clients["teamorouter-sol"].calls == 0
            assert clients["teamorouter-terra"].calls == 1
    elif phase == "C":
        obj = await service.create_object(symbol="BETA", company_name="Synthetic", exchange="LOCAL")
        backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
        draft = await backend.prepare_run(
            PrepareResearchRunRequestV1(
                research_object_id=obj.object_id,
                research_goal="Fundamental research",
                as_of=date(2026, 9, 17),
                preferences={},
            ),
            idempotency_key="local-prepare",
            request_id=None,
        )
        request = ConfirmResearchRunRequestV1(
            draft_id=draft.draft_id,
            draft_version=draft.draft_version,
            draft_hash=draft.draft_hash,
            research_object_id=obj.object_id,
            confirm_scheme=True,
        )
        confirmed = await backend.confirm_run(
            request, idempotency_key="local-confirm", request_id=None
        )
        replay = await backend.confirm_run(
            request, idempotency_key="local-confirm", request_id=None
        )
        assert replay.admission.run_id == confirmed.admission.run_id
        result = await repository.get_run_fresh(confirmed.admission.run_id)
        validate_root(result)
        receipt = dict(
            pid=os.getpid(),
            run_id=result.run.run_id,
            snapshot=result.node_binding.execution_snapshot,
            replay_run_id=replay.admission.run_id,
        )
        for t in result.runtime.actual_graph.tasks:
            p = frozen_profile(result, t)
            if t.task_type in {"risk_analysis", "valuation_analysis"}:
                assert p.profile_version == "2" and p.recovery_fallback_routes == (
                    "teamorouter-terra",
                )
            else:
                assert p.allowed_model_routes == p.owner_policy.candidates
        assert sum(c.calls for c in clients.values()) == 0
    else:
        saved = json.loads(await asyncio.to_thread(Path(directory, "process-C.json").read_text))
        result = await repository.get_run_fresh(saved["run_id"])
        validate_root(result)
        assert result.node_binding.execution_snapshot == saved["snapshot"]
        receipt = dict(
            pid=os.getpid(),
            snapshot=result.node_binding.execution_snapshot,
            run_id=result.run.run_id,
        )
    await asyncio.to_thread(
        Path(directory, f"process-{phase}.json").write_text, json.dumps(receipt, indent=2)
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
