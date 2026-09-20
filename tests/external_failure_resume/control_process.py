from src.adapters.fmp import FMPProvider
from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.agentic.composition import build_research_agent_registry
from src.agentic.recovery import AdaptiveRecovery
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.application.evidence_collection import LiveFMPEvidenceCollector
from src.application.service import ResearchApplicationService
from src.data.artifacts import LocalRawArtifactStore
from src.data.repository import InMemoryEvidenceRepository
from src.domain.owner_policy import ADAPTIVE_TRANSPORT_POLICY
from src.domain.recovery import Candidate
from src.infrastructure.config.settings import Settings
from src.infrastructure.database.recovery import MemoryRecoveryEvidenceStore
from tests.external_failure_resume.runtime_fixture import RiskFailure, Transport


async def fresh_service(root, *, repository=None, evidence=None, store=None, event_store=None):
    evidence = evidence or InMemoryEvidenceRepository()
    store = store or MemoryRecoveryEvidenceStore()
    clients = {
        f"teamorouter-{name}": RiskFailure("teamorouter", f"gpt-5.6-{name}")
        for name in ("sol", "terra", "luna")
    }
    clients["mimo-direct"] = RiskFailure("mimo", "mimo-v2.5")
    for c in clients.values():
        c.execution_policy = ProviderExecutionPolicyV1(**ADAPTIVE_TRANSPORT_POLICY)
        c._settings = Settings(_env_file=None, teamorouter_api_key="LOCAL_SENTINEL").llm.model_copy(
            update={"primary_model": c.model_name, "fallback_model": c.model_name}
        )
    recovery = AdaptiveRecovery(
        {
            k: Candidate(
                route=k, provider=v.provider_name, model=v.model_name, authority_exists=True
            )
            for k, v in clients.items()
        },
        clients,
        store,
    )
    service = ResearchApplicationService(
        repository=repository,
        event_store=event_store,
        evidence_repository=evidence,
        recovery_evidence_store=store,
        evidence_collector=LiveFMPEvidenceCollector(
            provider=FMPProvider(Transport()),
            repository=evidence,
            artifact_store=LocalRawArtifactStore(root / "raw"),
        ),
        agent_registry=build_research_agent_registry(
            clients["teamorouter-sol"],
            ResearchAgentOutputArtifactStore(root / "agents"),
            recovery=recovery,
        ),
    )
    return service, clients


async def production_exhaust(service, value):
    """Match product scheduler delivery: only initial execution emits run.started."""
    for step in range(2):
        try:
            await service.execute_run(value.run.run_id, emit_run_started=(step == 0))
        except ExceptionGroup:
            pass
        value = await service.repository.get_run_fresh(value.run.run_id)
        if value.node_binding.lifecycle != "RECOVERY_PENDING":
            break
    assert value.run.status.value == "FAILED"
    return value


def retain_blocking_review(service):
    """Use the real independent reviewer on the deliberately limited fixture.

    Missing full financial claims block release. Resume/Synthesis remains the
    proof target; no synthetic PASS or production assurance bypass is introduced.
    """
    original = service._review_for_release

    async def review(aggregate, strict, *args):
        return await original(aggregate, True, *args)

    service._review_for_release = review


async def main():
    import json
    import os
    import sys
    from pathlib import Path

    import httpx
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from starlette.requests import Request

    from apps.api.routes import stream_events
    from src.application.persistence import (
        SessionFactoryEvidenceRepository,
        SQLAlchemyApplicationRepository,
    )
    from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
    from src.infrastructure.database.recovery import RecoveryEvidenceStore
    from src.phase4_product.api import create_phase4_product_router, install_phase4_error_handlers
    from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
    from tests.external_failure_resume.runtime_fixture import legal_fixture

    mode, schema, root, run_id = sys.argv[1:]
    engine = create_async_engine(
        os.environ["TEST_POSTGRESQL_URL"], connect_args={"server_settings": {"search_path": schema}}
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owners = dict(
        repository=SQLAlchemyApplicationRepository(sessions),
        evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions),
        event_store=PostgresRuntimeEventStore(sessions),
    )
    if mode == "writer":
        service, value, clients = await legal_fixture(Path(root), **owners)
        run_id = value.run.run_id
    else:
        service, clients = await fresh_service(Path(root), **owners)
    retain_blocking_review(service)
    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    if mode == "writer":
        await production_exhaust(service, value)
    app = FastAPI()
    app.state.phase4_product_backend = backend
    app.state.research_service = service
    app.include_router(create_phase4_product_router())
    install_phase4_error_handlers(app)
    result = dict(pid=os.getpid(), run_id=run_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local"
    ) as client:
        url = f"/api/research-runs/{run_id}/external-resume"
        if mode in {"authorize", "duplicate", "stale"}:
            file = Path(root) / "command.json"
            if mode == "authorize":
                state = (await client.get(url)).json()
                command = dict(
                    state["legal_actions"][0]["expectations"],
                    authorize_resume=True,
                    idempotency_key="cross-process-one",
                )
                file.write_text(json.dumps(command))
            else:
                command = json.loads(file.read_text())
            if mode == "stale":
                command["idempotency_key"] = "stale-new-key"
            response = await client.post(
                url, json=command, headers={"Idempotency-Key": command["idempotency_key"]}
            )
            result.update(status=response.status_code, response=response.json())
        if mode == "scheduler":
            result["pending"] = await service.repository.external_resume_pending_run_ids()
        if mode in {"worker-success", "worker-exhaust"}:
            clients["teamorouter-sol"].fail_risk = mode != "worker-success"
            for _ in range(2):
                try:
                    await service.execute_run(run_id, emit_run_started=False)
                except ExceptionGroup:
                    current = await service.repository.get_run_fresh(run_id)
                    if (
                        mode != "worker-exhaust"
                        or current.node_binding.lifecycle != "EXTERNAL_FAILURE_PAUSED"
                    ):
                        raise
                current = await service.repository.get_run_fresh(run_id)
                if current.node_binding.lifecycle != "RECOVERY_PENDING":
                    break
            result["calls"] = {key: c.calls for key, c in clients.items()}
        response = await client.get(url)
        assert response.status_code == 200, response.text
        result["view"] = response.json()
        projection = await backend.get_projection(run_id)
        result["projection"] = projection.model_dump(mode="json")
        current = await service.repository.get_run_fresh(run_id)
        result["current_results"] = current.node_binding.current_results
        result["graph"] = current.node_binding.frozen_graph.model_dump(mode="json")
        result["snapshot"] = current.node_binding.execution_snapshot
        events = await service.event_store.replay(run_id)
        from src.phase4_product.reconstruction import ProjectionWatermark, _validate_events

        _validate_events(
            current.run,
            tuple(current.runtime.actual_graph.tasks),
            tuple(events),
            ProjectionWatermark(projection.projection_revision, projection.projection_sequence),
        )
        result["backend_event_reconstruction"] = "PASS"

        async def routed_frames(cursor=None):
            request = Request({"type": "http", "app": app, "headers": []})
            response = await stream_events(run_id, request, last_event_id=cursor)
            frames = []
            target = len(events) - (int(cursor) if cursor else 0)
            async for frame in response.body_iterator:
                frames.append(frame)
                if len(frames) >= target:
                    break
            await response.body_iterator.aclose()
            return frames, dict(response.headers)

        result["frames"], result["sse_headers"] = await routed_frames()
        if events:
            result["reconnect_frames"], _ = await routed_frames(
                str(max(0, events[-1].sequence - 2))
            )
    print(json.dumps(result, default=str))
    await engine.dispose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
