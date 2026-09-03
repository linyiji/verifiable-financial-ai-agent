from datetime import UTC, date, datetime

import pytest

from src.agentic.planner import ResearchLeadPlanner
from src.agentic.scheme import DeterministicSchemeGenerator, SchemeGenerator
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject


def _object() -> ResearchObject:
    return ResearchObject(
        object_id="OBJ-NVDA",
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
    )


def _goal(object_id: str = "OBJ-NVDA") -> ResearchGoal:
    return ResearchGoal(
        goal_id="GOAL-1",
        research_object_id=object_id,
        goal_text="Prepare a comprehensive evidence-backed equity research report",
        as_of=date(2026, 9, 3),
    )


@pytest.mark.asyncio
async def test_deterministic_scheme_generator_satisfies_interface_and_is_stable() -> None:
    generator = DeterministicSchemeGenerator()

    assert isinstance(generator, SchemeGenerator)
    first = await generator.generate(research_object=_object(), goal=_goal())
    second = await generator.generate(research_object=_object(), goal=_goal())

    assert first.scheme_id == second.scheme_id
    assert first.model_dump(exclude={"created_at"}) == second.model_dump(exclude={"created_at"})
    assert first.generated_model is None
    assert first.assurance_requirements["accepted_evidence_only"] is True
    assert first.calculation_requirements == [
        "deterministic_financial_calculations_only",
        "calculation_records_for_reported_values",
    ]


@pytest.mark.asyncio
async def test_scheme_generator_rejects_mismatched_object() -> None:
    with pytest.raises(ValueError, match="same object"):
        await DeterministicSchemeGenerator().generate(
            research_object=_object(),
            goal=_goal(object_id="OBJ-OTHER"),
        )


@pytest.mark.asyncio
async def test_research_lead_plans_complete_initial_graph_before_execution() -> None:
    goal = _goal()
    scheme = await DeterministicSchemeGenerator().generate(
        research_object=_object(),
        goal=goal,
    )
    scheme.confirmed_at = datetime(2026, 9, 3, tzinfo=UTC)

    graph = ResearchLeadPlanner().plan(run_id="RUN-1", goal=goal, scheme=scheme)

    assert graph.graph_id == "RUN-1:planned:v1"
    assert graph.version == 1
    assert [task.task_type for task in graph.tasks] == [
        "evidence_collection",
        "fundamental_analysis",
        "peer_analysis",
        "research_news_analysis",
        "valuation_analysis",
        "risk_analysis",
        "report_synthesis",
    ]
    assert all(task.run_id == "RUN-1" for task in graph.tasks)
    assert all(task.status.value == "CREATED" for task in graph.tasks)
    assert all(task.origin.value == "PLAN" for task in graph.tasks)

    tasks = {task.task_type: task for task in graph.tasks}
    assert tasks["evidence_collection"].dependencies == []
    assert set(tasks["valuation_analysis"].dependencies) == {
        "RUN-1:evidence",
        "RUN-1:fundamentals",
        "RUN-1:peers",
    }
    assert set(tasks["report_synthesis"].dependencies) == {
        "RUN-1:fundamentals",
        "RUN-1:peers",
        "RUN-1:research-news",
        "RUN-1:valuation",
        "RUN-1:risk",
    }


@pytest.mark.asyncio
async def test_planner_requires_confirmed_scheme() -> None:
    goal = _goal()
    scheme = await DeterministicSchemeGenerator().generate(
        research_object=_object(),
        goal=goal,
    )

    with pytest.raises(ValueError, match="confirmed"):
        ResearchLeadPlanner().plan(run_id="RUN-1", goal=goal, scheme=scheme)


@pytest.mark.asyncio
async def test_planner_fails_closed_when_confirmed_scheme_needs_unsupported_skill() -> None:
    goal = _goal()
    scheme = await DeterministicSchemeGenerator().generate(
        research_object=_object(),
        goal=goal,
    )
    scheme.confirmed_at = datetime(2026, 9, 3, tzinfo=UTC)
    scheme.skill_requirements.append("unsupported_custom_skill_v1")

    with pytest.raises(ValueError, match="unsupported skill requirements"):
        ResearchLeadPlanner().plan(run_id="RUN-1", goal=goal, scheme=scheme)
