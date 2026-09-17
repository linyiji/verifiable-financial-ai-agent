"""Create page -> HTTP Prepare -> durable Confirm -> scoped composer, offline only."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.adapters.llm.routes import configured_incremental_provider, model_selection_options
from src.agentic.composition import build_research_agent_registry
from src.application.execution import IntegratedTaskExecutor
from src.application.persistence import ResearchObjectRow, SQLAlchemyApplicationRepository
from src.application.service import ResearchApplicationService
from src.domain.research_object import ResearchObject
from src.infrastructure.database.base import Base
from src.phase4_product.api import (
    CONTRACT_HEADER,
    create_phase4_product_router,
    install_phase4_error_handlers,
)
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401
from tests.unit.llm.test_explicit_model_selection import settings

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="Local DB required"
)


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", [0, 1])
async def test_page_prepare_confirm_reload_scoped_invocation(database, choice):  # noqa: F811
    engine, sessions = database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    obj = ResearchObject(
        object_id="OBJ-local", symbol="NVDA", company_name="Offline", exchange="NASDAQ"
    )
    async with sessions() as session, session.begin():
        session.add(
            ResearchObjectRow(
                object_id=obj.object_id,
                created_at=obj.created_at,
                payload=obj.model_dump(mode="json"),
            )
        )
    config = settings()
    default = configured_incremental_provider(config, route_id="teamorouter-sol")
    registry = build_research_agent_registry(default, None)
    repository = SQLAlchemyApplicationRepository(sessions)
    service = ResearchApplicationService(
        repository=repository,
        agent_registry=registry,
        selected_provider_factory=lambda route: configured_incremental_provider(
            config, route_id=route
        ),
    )
    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    app = FastAPI()
    app.state.phase4_product_backend = backend
    install_phase4_error_handlers(app)
    app.include_router(create_phase4_product_router())
    headers = {CONTRACT_HEADER: "phase4-core/v1"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://offline") as client:
        options = await client.get("/api/model-selection-options", headers=headers)
        assert options.status_code == 200 and options.json() == model_selection_options()
        result = subprocess.run(  # noqa: ASYNC221 - bounded local component/request integration
            ["node", "scripts/model-selection.test.mjs"],
            cwd=Path("apps/web"),
            input=json.dumps(options.json()),
            text=True,
            capture_output=True,
            check=True,
        )
        bodies = json.loads(result.stdout)
        run_ids = []
        for i, body in [(choice, bodies[choice])]:
            prepared = await client.post(
                "/api/research-runs/prepare",
                json=body,
                headers={**headers, "Idempotency-Key": f"prepare-{i}"},
            )
            assert prepared.status_code == 201, prepared.text
            draft = prepared.json()
            assert draft["goal"]["preferences"] == body["preferences"]
            confirmed = await client.post(
                "/api/research-runs",
                json={
                    "draft_id": draft["draft_id"],
                    "draft_version": draft["draft_version"],
                    "draft_hash": draft["draft_hash"],
                    "research_object_id": "OBJ-local",
                    "confirm_scheme": True,
                },
                headers={**headers, "Idempotency-Key": f"confirm-{i}"},
            )
            if i:
                # The full graph contains Terra-denied peer/news tasks. V5 moves
                # this existing authorization failure to atomic Confirm.
                assert confirmed.status_code == 409, confirmed.text
                assert confirmed.json()["error"]["details"]["reason_code"] == "MODEL_NOT_AUTHORIZED"
                from sqlalchemy import func, select

                from src.application.persistence import ResearchRunAggregateRow

                async with sessions() as session:
                    assert await session.scalar(
                        select(func.count()).select_from(ResearchRunAggregateRow)
                    ) == 0
                continue
            assert confirmed.status_code == 201, confirmed.text
            run_ids.append((i, confirmed.json()["admission"]["run_id"]))
        # Reload committed configuration without starting a scheduler or provider.
        reloaded = SQLAlchemyApplicationRepository(sessions)
        for i, run_id in run_ids:
            aggregate = await reloaded.get_run(run_id)
            assert aggregate.goal.preferences == bodies[i]["preferences"]
            task = next(
                t
                for t in aggregate.runtime.actual_graph.tasks
                if t.task_type == "fundamental_analysis"
            )
            agent = IntegratedTaskExecutor(service, aggregate)._research_agent(task)
            assert agent._provider.model_name == ("gpt-5.6-terra" if i else "gpt-5.6-sol")
        invalid = {**bodies[0], "preferences": {"model_selection": {"route_id": "unknown"}}}
        rejected = await client.post(
            "/api/research-runs/prepare",
            json=invalid,
            headers={**headers, "Idempotency-Key": "unknown"},
        )
        assert rejected.status_code == 422
        assert registry.get("fundamental_analyst")._provider is default
