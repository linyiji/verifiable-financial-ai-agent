import pytest

from src.adapters.llm import routes
from src.agentic.composition import build_research_agent_registry
from src.infrastructure.config.settings import Settings
from tests.phase4.backend_product.test_mimo_foundation import config


def test_explicit_specialist_overrides_preserve_other_profiles(monkeypatch):
    monkeypatch.setattr(routes, "load_mimo_authority", lambda path, **kwargs: config())
    settings = Settings(_env_file=None)
    providers = routes.configured_specialist_providers(settings)
    assert set(providers) == {"peer_analysis", "research_news_analysis"}
    original = object()
    registry = build_research_agent_registry(original, None, profile_providers=providers)
    for actor, profile in (
        ("peer_analyst", "peer_analysis"),
        ("research_news_analyst", "research_news_analysis"),
    ):
        agent = registry.get(actor)
        assert agent._provider is providers[profile]
        assert agent.supported_task_types == {profile}
        assert routes.describe_route(agent._provider).provider_route_id == "mimo-direct"
        assert agent._provider.model_name == "mimo-v2.5"
        assert agent._provider.task_profile == profile
        assert "fixture-only-secret" not in repr(routes.describe_route(agent._provider))
    for actor in ("fundamental_analyst", "valuation_analyst", "risk_analyst", "research_lead"):
        assert registry.get(actor)._provider is original


def test_unknown_profile_rejected():
    settings = Settings(_env_file=None, specialist_provider_routes={"invented": "mimo-direct"})
    with pytest.raises(ValueError, match="Unknown Specialist"):
        routes.configured_specialist_providers(settings)


def test_empty_overrides_do_not_change_provider():
    provider = object()
    registry = build_research_agent_registry(provider, None, profile_providers={})
    assert registry.get("peer_analyst")._provider is provider


def test_conflicting_multi_profile_agent_fails_closed():
    with pytest.raises(ValueError, match="consistent"):
        build_research_agent_registry(object(), None, profile_providers={"risk_analysis": object()})
