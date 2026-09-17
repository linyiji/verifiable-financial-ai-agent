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


def selected_research_agent(registry, task, selection, provider_factory):
    """Compose a fresh invocation; shared Agents and credentials remain unchanged."""
    agent = registry.get(task.assigned_agent)
    if selection is None:
        return agent
    if selection.route_id not in TASK_CANDIDATES.get(task.task_type, ()):
        raise ValueError("Initial provider is outside governed recovery authority")
    if type(agent) is not LLMResearchAgent or task.task_type not in agent.supported_task_types:
        raise ValueError("Explicit model selection requires supported research Agent composition")
    if provider_factory is None:
        raise ValueError("Explicit model selection provider configuration is unavailable")
    provider = provider_factory(selection.route_id)
    provider.task_profile = task.task_type
    return LLMResearchAgent(
        agent_id=agent.agent_id,
        supported_task_types=agent.supported_task_types,
        provider=provider,
        artifacts=agent._artifacts,
        recovery=agent._recovery,
    )
