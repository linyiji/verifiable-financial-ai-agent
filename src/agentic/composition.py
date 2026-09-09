"""Single production Specialist registration authority, reusable without provider calls."""

from src.agentic.registry import AgentRegistry
from src.agentic.research_agent import LLMResearchAgent
from src.domain.model_execution import TASK_CANDIDATES


def build_research_agent_registry(provider, artifacts, *, profile_providers=None, recovery=None):
    profile_providers = profile_providers or {}
    registry = AgentRegistry()
    for agent_id, task_types in (
        ("fundamental_analyst", frozenset({"fundamental_analysis"})),
        ("peer_analyst", frozenset({"peer_analysis"})),
        ("research_news_analyst", frozenset({"research_news_analysis"})),
        ("valuation_analyst", frozenset({"valuation_analysis"})),
        ("risk_analyst", frozenset({"risk_analysis", "risk_follow_up"})),
        ("research_lead", frozenset({"report_synthesis"})),
    ):
        if recovery is not None and any(not TASK_CANDIDATES.get(p) for p in task_types):
            raise ValueError("Registered specialist profile has no governed model authority")
        selected = [profile_providers.get(profile, provider) for profile in task_types]
        if any(item is not selected[0] for item in selected):
            raise ValueError("Multi-profile Agent requires one consistent configured provider")
        registry.register(
            LLMResearchAgent(
                agent_id=agent_id,
                supported_task_types=task_types,
                provider=selected[0],
                artifacts=artifacts,
                recovery=recovery,
            )
        )
    return registry
