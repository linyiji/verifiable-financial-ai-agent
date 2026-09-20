"""Complete offline child Confirm configuration; constructs clients without sending requests."""

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.teamorouter import TeamoRouterClient
from src.domain.owner_policy import ADAPTIVE_TRANSPORT_POLICY
from src.domain.recovery import Candidate
from src.infrastructure.config.settings import Settings


def configure_child(service):
    agent = service.agent_registry.get("risk_analyst")
    settings = Settings(_env_file=None, teamorouter_api_key="LOCAL_SENTINEL")
    for route, model in [
        ("teamorouter-sol", "gpt-5.6-sol"),
        ("teamorouter-terra", "gpt-5.6-terra"),
    ]:
        client = TeamoRouterClient(
            settings.llm.model_copy(update={"primary_model": model, "fallback_model": model}),
            execution_policy=ProviderExecutionPolicyV1(**ADAPTIVE_TRANSPORT_POLICY),
        )
        client.route_ids = {model: route}
        agent._recovery.clients[route] = client
        agent._recovery.detector.routes[route] = Candidate(
            route=route, provider="teamorouter", model=model, authority_exists=True
        )
        if route == "teamorouter-sol":
            agent._provider = client
