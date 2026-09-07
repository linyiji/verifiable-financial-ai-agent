"""Single-call graph failure must never turn into deterministic admission."""

from datetime import UTC, datetime

import pytest

from src.agentic.llm_integration import PlannerProviderResearchLeadPlanner
from src.agentic.planning_errors import GraphPlanningFailure
from src.agentic.scheme import DeterministicSchemeGenerator
from tests.unit.llm.test_agentic_llm_integration import FakeProvider, research_inputs, valid_graph


@pytest.mark.parametrize("output", [{}, {"tasks": []}])
async def test_bad_graph_one_call_no_fallback(output):
    obj, goal = research_inputs()
    scheme = await DeterministicSchemeGenerator().generate(research_object=obj, goal=goal)
    scheme.confirmed_at = datetime.now(UTC)
    provider = FakeProvider([output, valid_graph()])
    planner = PlannerProviderResearchLeadPlanner(
        provider, max_validation_attempts=1, fail_closed=True
    )
    with pytest.raises(GraphPlanningFailure):
        await planner.plan(run_id="RUN-STRICT", goal=goal, scheme=scheme)
    assert len(provider.calls) == 1 and not planner.decisions


async def test_valid_graph_one_call_preserves_scheme():
    obj, goal = research_inputs()
    scheme = await DeterministicSchemeGenerator().generate(research_object=obj, goal=goal)
    scheme.confirmed_at = datetime.now(UTC)
    before = scheme.model_dump()
    provider = FakeProvider([valid_graph()])
    planner = PlannerProviderResearchLeadPlanner(
        provider, max_validation_attempts=1, fail_closed=True
    )
    graph = await planner.plan(run_id="RUN-STRICT", goal=goal, scheme=scheme)
    assert graph.run_id == "RUN-STRICT" and len(provider.calls) == 1
    assert scheme.model_dump() == before
