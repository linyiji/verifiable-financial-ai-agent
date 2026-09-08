"""Production registry/client/builder composition; all HTTP is fake."""

import json
import os
from datetime import date

import httpx
import pytest

from src.agentic.recovery import RecoveryStopped
from src.agentic.recovery_composition import build_adaptive_recovery
from src.application.persistence import SQLAlchemyApplicationRepository
from src.application.service import ResearchApplicationService
from src.capabilities.generated.contract import GeneratedCapabilityRequestV1
from src.capabilities.generated.governed_builder import GovernedCodeBuilder
from src.capabilities.generated.spec import expected_spec
from src.domain.recovery import Health, RecoveryBudget
from src.infrastructure.config.settings import Settings
from src.infrastructure.database.base import Base
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401
from tests.unit.generated.test_code_builder import build_request

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="PostgreSQL required"
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route,actual,accepted",
    [
        ("teamorouter-sol", "gpt-5.6-sol", True),
        ("teamorouter-luna", "gpt-5.6-terra", False),
        ("teamorouter-terra", "gpt-5.6-terra", True),
        ("teamorouter-terra", "gpt-5.6-luna", False),
    ],
)
async def test_actual_builder_route_matrix(database, tmp_path, route, actual, accepted):  # noqa: F811
    sessions, recovery, repository, request = await composition(database, tmp_path)
    recovery.budget = RecoveryBudget(max_total_attempts_per_task=1)
    calls = []
    owned = GeneratedCapabilityRequestV1.from_build_request(request)

    def respond(http):
        body = json.loads(http.content)
        calls.append(body["model"])
        return httpx.Response(
            200,
            json={
                "model": actual,
                "choices": [
                    {
                        "message": {
                            "content": expected_spec(owned).model_dump_json(),
                        }
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        for provider in recovery.clients.values():
            provider._client = client
        builder = GovernedCodeBuilder(recovery, repository, initial_route=route)
        if accepted:
            result = await builder.generate(request)
            assert result.actual_model == actual
        else:
            with pytest.raises(RecoveryStopped):
                await builder.generate(request)
        assert len(calls) == 1
        records = await recovery.store.records(request.gap.run_id)
        completed = [r for r in records if r.kind == "ATTEMPT_COMPLETED"]
        assert len(completed) == 1
        assert completed[0].requested_model == calls[0]
        assert completed[0].actual_model == actual
        assert completed[0].outcome == ("PASS" if accepted else "FAIL")
        assert bool(completed[0].candidate_hash) == accepted
        if accepted:
            assert completed[0].candidate_hash == result.implementation_hash
            # Same real task may later enter Specialist recovery, without rewriting
            # the builder ledger or bypassing duplicate generation protection.
            from uuid import uuid4

            start = next(r for r in records if r.kind == "ATTEMPT_STARTED")
            await recovery.store.append(
                start.model_copy(
                    update={
                        "record_id": "REC-" + str(uuid4()),
                        "attempt_id": "ATT-" + str(uuid4()),
                        "scope": start.scope.model_copy(update={"operation_id": "specialist"}),
                    }
                )
            )
        with pytest.raises(RecoveryStopped):
            await builder.generate(request)
        assert len(calls) == 1  # persisted operation cannot reset budget


async def composition(database_fixture, tmp_path):
    _, sessions = database_fixture
    async with sessions.kw["bind"].begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    settings = Settings(
        _env_file=None,
        teamorouter_api_key="OFFLINE_SENTINEL",
        mimo_api_key=None,
        mimo_authority_file=None,
        artifact_root=str(tmp_path),
        vfa_credential_mode="byok",
    )
    recovery = await build_adaptive_recovery(settings, sessions)
    repository = SQLAlchemyApplicationRepository(sessions)
    service = ResearchApplicationService(repository=repository)
    obj = await service.create_object(symbol="NVDA", company_name="NVIDIA", exchange="NASDAQ")
    draft = await service.prepare_run(
        research_object_id=obj.object_id,
        research_goal="Offline builder",
        as_of=date(2026, 9, 8),
        preferences={},
    )
    aggregate = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    task = next(
        t for t in aggregate.runtime.actual_graph.tasks if t.task_type == "fundamental_analysis"
    )
    request = build_request()
    request = request.model_copy(
        update={
            "gap": request.gap.model_copy(
                update={
                    "run_id": task.run_id,
                    "task_id": task.task_id,
                    "requested_by": task.assigned_agent,
                }
            ),
            "approval": request.approval.model_copy(
                update={"run_id": task.run_id, "task_id": task.task_id}
            ),
        }
    )
    return sessions, recovery, repository, request


@pytest.mark.asyncio
async def test_governed_generation_timeout_then_explicit_terra(database, tmp_path):  # noqa: F811
    _, recovery, repository, request = await composition(database, tmp_path)
    # Independent observed route health excludes Luna, no hardcoded builder ranking.
    recovery.initial_health["teamorouter-luna"] = Health.UNAVAILABLE
    owned = GeneratedCapabilityRequestV1.from_build_request(request)
    calls = []

    def respond(http):
        model = json.loads(http.content)["model"]
        calls.append(model)
        if model == "gpt-5.6-sol":
            raise httpx.ReadTimeout("offline timeout")
        return httpx.Response(
            200,
            json={
                "model": model,
                "choices": [
                    {
                        "message": {
                            "content": expected_spec(owned).model_dump_json(),
                        }
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        for provider in recovery.clients.values():
            provider._client = client
        result = await GovernedCodeBuilder(recovery, repository).generate(request)
    assert result.actual_model == "gpt-5.6-terra"
    assert calls == ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-terra"]
    records = await recovery.store.records(request.gap.run_id)
    assert len([r for r in records if r.kind == "DECISION" and r.outcome == "ALLOW"]) == 2
    checks = [r for r in records if r.kind == "ATTEMPT_COMPLETED" and r.capability_check]
    assert len(checks) == 1 and checks[0].candidate_hash


@pytest.mark.asyncio
async def test_generated_route_authority_denial_makes_no_http_call(database, tmp_path):  # noqa: F811
    _, recovery, repository, request = await composition(database, tmp_path)
    route = "teamorouter-terra"
    recovery.detector.routes[route] = recovery.detector.routes[route].model_copy(
        update={"authority_exists": False}
    )
    with pytest.raises(RecoveryStopped):
        await GovernedCodeBuilder(recovery, repository, initial_route=route).generate(request)
    records = await recovery.store.records(request.gap.run_id)
    assert len(records) == 1
    assert records[0].kind == "TERMINAL" and records[0].reason_code == "POLICY_DENIED"


@pytest.mark.asyncio
async def test_generated_budget_exhausted_never_attempts_terra(database, tmp_path):  # noqa: F811
    _, recovery, repository, request = await composition(database, tmp_path)
    recovery.budget = RecoveryBudget(max_total_attempts_per_task=1)
    calls = []

    def fail(http):
        calls.append(json.loads(http.content)["model"])
        raise httpx.ReadTimeout("offline timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        for provider in recovery.clients.values():
            provider._client = client
        with pytest.raises(RecoveryStopped):
            await GovernedCodeBuilder(recovery, repository).generate(request)
    assert calls == ["gpt-5.6-sol"]
    records = await recovery.store.records(request.gap.run_id)
    assert records[-1].reason_code == "RECOVERY_BUDGET_EXHAUSTED"


@pytest.mark.asyncio
async def test_luna_alias_is_rejected_before_separate_terra_decision(database, tmp_path):  # noqa: F811
    _, recovery, repository, request = await composition(database, tmp_path)
    recovery.initial_health["teamorouter-sol"] = Health.UNAVAILABLE
    owned = GeneratedCapabilityRequestV1.from_build_request(request)
    calls = []

    def respond(http):
        calls.append(json.loads(http.content)["model"])
        return httpx.Response(
            200,
            json={
                "model": "gpt-5.6-terra",
                "choices": [
                    {
                        "message": {
                            "content": expected_spec(owned).model_dump_json(),
                        }
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        for provider in recovery.clients.values():
            provider._client = client
        result = await GovernedCodeBuilder(
            recovery, repository, initial_route="teamorouter-luna"
        ).generate(request)
    assert result.actual_model == "gpt-5.6-terra"
    assert calls == ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-terra"]
    records = await recovery.store.records(request.gap.run_id)
    completed = [r for r in records if r.kind == "ATTEMPT_COMPLETED"]
    assert (
        completed[0].outcome == "FAIL" and completed[0].failure_class == "MODEL_IDENTITY_MISMATCH"
    )
    assert completed[0].candidate_hash is None
    assert any(
        r.kind == "DECISION" and r.route == "teamorouter-terra" and r.outcome == "ALLOW"
        for r in records
    )
