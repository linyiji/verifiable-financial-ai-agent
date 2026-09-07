"""Single production Specialist registration authority, reusable without provider calls."""

from src.agentic.registry import AgentRegistry
from src.agentic.research_agent import LLMResearchAgent


def build_research_agent_registry(provider, artifacts):
    registry = AgentRegistry()
    for agent_id, task_types in (
        ("fundamental_analyst", frozenset({"fundamental_analysis"})),
        ("peer_analyst", frozenset({"peer_analysis"})),
        ("research_news_analyst", frozenset({"research_news_analysis"})),
        ("valuation_analyst", frozenset({"valuation_analysis"})),
        ("risk_analyst", frozenset({"risk_analysis", "risk_follow_up"})),
        ("research_lead", frozenset({"report_synthesis"})),
    ):
        registry.register(
            LLMResearchAgent(
                agent_id=agent_id,
                supported_task_types=task_types,
                provider=provider,
                artifacts=artifacts,
            )
        )
    return registry
