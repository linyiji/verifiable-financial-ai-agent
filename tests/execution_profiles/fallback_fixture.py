"""Local synthetic provider ports through production Confirm and durable execution."""

from src.application.repository import initialize_binding
from src.domain.recovery import Candidate
from tests.same_node_recovery.test_durable import LocalClient, configured


async def configured_family(tmp_path, kind, *, persist=True, **kwargs):
    service, value, collector, clients = await configured(tmp_path, persist=False, **kwargs)
    terra = LocalClient("teamorouter", "gpt-5.6-terra")
    clients["teamorouter-terra"] = terra
    # All default research agents share the explicitly supplied Recovery fixture.
    from src.application.execution_profiles import configured_agent, recovery_for

    for graph in (value.runtime.actual_graph, value.runtime.planned_graph):
        task = graph.tasks[1]
        task.task_type = kind
        task.assigned_agent = {
            "risk_analysis": "risk_analyst",
            "valuation_analysis": "valuation_analyst",
        }[kind]
        task.skill_id = f"{kind}_v1"
    agent = configured_agent(service, value.runtime.actual_graph.tasks[1], None)
    recovery = recovery_for(agent)
    recovery.clients["teamorouter-terra"] = terra
    recovery.detector.routes["teamorouter-terra"] = Candidate(
        route="teamorouter-terra",
        provider="teamorouter",
        model="gpt-5.6-terra",
        authority_exists=True,
    )
    value.node_binding = None
    initialize_binding(value, service=service)
    if persist:
        from tests.wp02.confirmation_fixture import confirm_template

        value = await confirm_template(service, value, symbol=kwargs.get("symbol", "ALPHA"))
    return service, value, collector, clients
