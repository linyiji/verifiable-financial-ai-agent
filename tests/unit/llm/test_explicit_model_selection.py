"""Offline product identity -> scoped execution -> existing provider and receipt."""

import asyncio
import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from src.adapters.llm.provider import LLMMessage
from src.adapters.llm.routes import configured_incremental_provider, model_selection_options
from src.agentic.composition import build_research_agent_registry
from src.agentic.recovery import AdaptiveRecovery, RecoveryStopped
from src.application.execution import IntegratedTaskExecutor
from src.domain.model_selection import selected_model
from src.domain.recovery import Candidate, RecoveryBudget
from src.domain.research_goal import ResearchGoal
from src.infrastructure.config.settings import Settings
from src.infrastructure.database.recovery import MemoryRecoveryEvidenceStore
from src.phase4_product.contracts import PrepareResearchRunRequestV1
from tests.unit.agentic.test_adaptive_recovery import Output, context, task

TERRA = {"model_selection": {"route_id": "teamorouter-terra"}}


def settings(key="OFFLINE_SENTINEL"):
    return Settings(
        _env_file=None,
        teamorouter_api_key=key,
        mimo_api_key=None,
        mimo_authority_file=None,
        vfa_credential_mode="byok",
    )


def request(preferences):
    return PrepareResearchRunRequestV1(
        research_object_id="OBJ-local",
        research_goal="Offline",
        as_of=date(2026, 9, 17),
        preferences=preferences,
    )


def executor(preferences, registry, config, current_task=None):
    # Exercise the production dispatch selector with a reloaded persisted goal.
    goal = ResearchGoal(
        goal_id="GOAL-local",
        research_object_id="OBJ-local",
        goal_text="Offline",
        as_of=date(2026, 9, 17),
        preferences=request(preferences).preferences,
    )
    invocation = object.__new__(IntegratedTaskExecutor)
    invocation._aggregate = SimpleNamespace(
        goal=ResearchGoal.model_validate_json(goal.model_dump_json()),
        run=SimpleNamespace(run_id=(current_task or task()).run_id),
    )
    invocation._service = SimpleNamespace(
        agent_registry=registry,
        selected_provider_factory=lambda route: configured_incremental_provider(
            config, route_id=route
        ),
    )
    return invocation


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        {},
        "teamorouter-terra",
        {"route_id": "unknown"},
        {"route_id": "gpt-5.6-terra"},
        {"route_id": "teamorouter-terra", "api_key": "forbidden"},
    ],
)
def test_unknown_or_malformed_never_defaults(invalid):
    with pytest.raises(ValidationError):
        request({"model_selection": invalid})


def test_registered_identity_only_and_default():
    assert selected_model(request({}).preferences) is None
    for option in model_selection_options():
        assert (
            selected_model(
                request({"model_selection": {"route_id": option["route_id"]}}).preferences
            ).route_id
            == option["route_id"]
        )
    with pytest.raises(ValidationError):
        selected_model(TERRA).route_id = "teamorouter-sol"


@pytest.mark.asyncio
async def test_concurrent_reloaded_scopes_preserve_settings_and_global_agents():
    config = settings()
    before = config.model_dump()
    default = configured_incremental_provider(config, route_id="teamorouter-sol")
    registry = build_research_agent_registry(default, None)
    original = registry.get("fundamental_analyst")
    a, b = executor(TERRA, registry, config), executor({}, registry, config)

    async def select(invocation):
        await asyncio.sleep(0)
        return invocation._research_agent(task())

    selected, unchanged = await asyncio.gather(select(a), select(b))
    assert unchanged is original
    assert selected is not original
    assert selected._provider.model_name == "gpt-5.6-terra"
    assert selected._provider.route_ids == {"gpt-5.6-terra": "teamorouter-terra"}
    assert selected._provider.task_profile == "fundamental_analysis"
    assert selected._provider._settings.fallback_model == "gpt-5.6-terra"
    assert original._provider is default and default.model_name == "gpt-5.6-sol"
    assert default._settings.fallback_model == "gpt-5.6-luna"
    assert config.model_dump() == before
    assert executor(TERRA, registry, config)._research_agent(task()) is not selected


@pytest.mark.parametrize(
    "profile,actor",
    [("peer_analysis", "peer_analyst"), ("research_news_analysis", "research_news_analyst")],
)
def test_current_policy_rejects_before_composition(profile, actor):
    config = settings()
    registry = build_research_agent_registry(None, None)
    t = task().model_copy(update={"task_type": profile, "assigned_agent": actor})
    with pytest.raises(ValueError, match="outside governed"):
        executor(TERRA, registry, config)._research_agent(t)


def test_missing_credentials_fail_no_fallback():
    config = settings(None)
    registry = build_research_agent_registry(None, None)
    with pytest.raises(ValueError, match="API key is not configured"):
        executor(TERRA, registry, config)._research_agent(task())


@pytest.mark.asyncio
async def test_selected_terra_transport_failure_uses_generic_receipt():
    config = settings()
    registry = build_research_agent_registry(None, None)
    invocation = executor(TERRA, registry, config)
    provider = invocation._research_agent(task())._provider
    store = MemoryRecoveryEvidenceStore()
    recovery = AdaptiveRecovery(
        {
            "teamorouter-terra": Candidate(
                route="teamorouter-terra",
                provider=provider.provider_name,
                model=provider.model_name,
                authority_exists=True,
            )
        },
        {"teamorouter-terra": provider},
        store,
        budget=RecoveryBudget(max_total_attempts_per_task=1),
    )
    calls = []

    async def fail(req):
        calls.append(json.loads(req.content)["model"])
        await req.extensions["trace"]("http11.send_request_headers.started", {})
        return httpx.Response(503, json={"error": "offline"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as http:
        provider._client = http
        with pytest.raises(RecoveryStopped):
            await recovery.execute(
                context(),
                provider,
                messages=[LLMMessage(role="user", content="test")],
                response_model=Output,
                schema_name="answer",
            )
    rows = await store.records()
    row = next(r for r in rows if r.kind == "ATTEMPT_COMPLETED")
    assert calls == ["gpt-5.6-terra"]
    assert invocation._aggregate.goal.preferences == TERRA
    assert row.provider == "teamorouter" and row.requested_model == "gpt-5.6-terra"
    assert row.execution_policy["preferred_model"] == "gpt-5.6-terra"
    assert row.model == "gpt-5.6-terra" and row.actual_model is None
    assert row.safe_failure.http_status == 503
    assert row.safe_failure.dispatch_state == "DISPATCHED"
    assert row.latency_ms >= 0 and row.failure_class is not None
    assert row.safe_failure.retryable is True


@pytest.mark.asyncio
async def test_concurrent_agent_invocations_keep_requested_and_observed_models(tmp_path):
    from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore

    config = settings()
    default = configured_incremental_provider(config, route_id="teamorouter-sol")
    registry = build_research_agent_registry(default, ResearchAgentOutputArtifactStore(tmp_path))
    a = task().model_copy(update={"run_id": "RUN-A", "task_id": "RUN-A:fundamentals"})
    b = task().model_copy(update={"run_id": "RUN-B", "task_id": "RUN-B:fundamentals"})
    selected = executor(TERRA, registry, config, a)._research_agent(a)
    unchanged = executor({}, registry, config, b)._research_agent(b)
    calls = []

    async def respond(req):
        model = json.loads(req.content)["model"]
        calls.append(model)
        await asyncio.sleep(0)
        return httpx.Response(
            200,
            json={
                "model": model,
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Offline",
                                    "key_findings": ["Bound input"],
                                    "risks": [],
                                    "limitations": [],
                                    "requires_follow_up": False,
                                }
                            )
                        }
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        selected._provider._client = http
        default._client = http
        first, second = await asyncio.gather(
            selected.execute(context(a)), unchanged.execute(context(b))
        )
    assert sorted(calls) == ["gpt-5.6-sol", "gpt-5.6-terra"]
    assert first.agent_output.requested_model == first.agent_output.actual_model == "gpt-5.6-terra"
    assert second.agent_output.requested_model == second.agent_output.actual_model == "gpt-5.6-sol"
    assert registry.get("fundamental_analyst") is unchanged
    assert default.model_name == "gpt-5.6-sol"
