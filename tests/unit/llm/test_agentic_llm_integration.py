from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.adapters.llm import (
    LLMMessage,
    LLMProviderUnavailableError,
    LLMStructuredResponse,
)
from src.agentic.llm_integration import (
    PlannedGraphProposal,
    SchemeProposal,
    TeamoRouterResearchLeadPlanner,
    TeamoRouterSchemeGenerator,
)
from src.agentic.scheme import DeterministicSchemeGenerator
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject


class FakeProvider:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[type, list[LLMMessage]]] = []

    async def complete_structured(
        self,
        *,
        messages: list[LLMMessage],
        response_model: type,
        schema_name: str,
        force_fallback: bool = False,
    ):
        del schema_name, force_fallback
        self.calls.append((response_model, messages))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return LLMStructuredResponse(
            output=response_model.model_validate(output),
            provider="teamorouter",
            requested_model="gpt-5.6-sol",
            actual_model="gpt-5.6-sol",
            attempted_models=("gpt-5.6-sol",),
        )


def research_inputs() -> tuple[ResearchObject, ResearchGoal]:
    research_object = ResearchObject(
        object_id="OBJ-NVDA",
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
    )
    goal = ResearchGoal(
        goal_id="GOAL-1",
        research_object_id=research_object.object_id,
        goal_text="Evaluate fundamentals and risks",
        as_of=date(2026, 9, 4),
    )
    return research_object, goal


def valid_scheme() -> dict:
    return {
        "research_scope": ["verified_financial_evidence", "fundamental_analysis"],
        "data_requirements": ["accepted_company_financial_evidence"],
        "agent_requirements": ["fundamental_analyst", "research_lead"],
        "skill_requirements": [
            "evidence_collection_v1",
            "fundamental_analysis_v1",
            "peer_analysis_v1",
            "research_news_analysis_v1",
            "valuation_analysis_v1",
            "risk_analysis_v1",
            "report_synthesis_v1",
        ],
        "calculation_requirements": [
            "deterministic_financial_calculations_only",
            "calculation_records_for_reported_values",
        ],
        "assurance_requirements": {
            "accepted_evidence_only": True,
            "deterministic_financial_values": True,
            "review_required": True,
        },
        "report_requirements": ["financial_report"],
        "limitations": ["No financial values are authored by this scheme."],
    }


def valid_graph() -> dict:
    return {
        "tasks": [
            {
                "key": "evidence",
                "task_type": "evidence_collection",
                "goal": "Collect and validate required evidence",
                "assigned_agent": "research_news_analyst",
                "skill_id": "evidence_collection_v1",
                "dependency_keys": [],
            },
            {
                "key": "fundamentals",
                "task_type": "fundamental_analysis",
                "goal": "Interpret deterministic fundamental calculations",
                "assigned_agent": "fundamental_analyst",
                "skill_id": "fundamental_analysis_v1",
                "dependency_keys": ["evidence"],
            },
            {
                "key": "peers",
                "task_type": "peer_analysis",
                "goal": "Analyze peers from accepted evidence",
                "assigned_agent": "peer_analyst",
                "skill_id": "peer_analysis_v1",
                "dependency_keys": ["evidence"],
            },
            {
                "key": "research-news",
                "task_type": "research_news_analysis",
                "goal": "Analyze research and news evidence",
                "assigned_agent": "research_news_analyst",
                "skill_id": "research_news_analysis_v1",
                "dependency_keys": ["evidence"],
            },
            {
                "key": "valuation",
                "task_type": "valuation_analysis",
                "goal": "Interpret deterministic valuation outputs",
                "assigned_agent": "valuation_analyst",
                "skill_id": "valuation_analysis_v1",
                "dependency_keys": ["fundamentals", "peers"],
            },
            {
                "key": "risk",
                "task_type": "risk_analysis",
                "goal": "Assess risks from accepted evidence",
                "assigned_agent": "risk_analyst",
                "skill_id": "risk_analysis_v1",
                "dependency_keys": ["fundamentals", "research-news"],
            },
            {
                "key": "synthesis",
                "task_type": "report_synthesis",
                "goal": "Synthesize review-ready outputs",
                "assigned_agent": "research_lead",
                "skill_id": "report_synthesis_v1",
                "dependency_keys": ["valuation", "risk"],
            },
        ]
    }


@pytest.mark.asyncio
async def test_llm_scheme_validates_and_records_decision_without_financial_numbers() -> None:
    research_object, goal = research_inputs()
    provider = FakeProvider([valid_scheme()])
    generator = TeamoRouterSchemeGenerator(provider)

    result = await generator.generate_with_decision(
        research_object=research_object,
        goal=goal,
    )

    assert isinstance(provider.calls[0][0].model_validate(valid_scheme()), SchemeProposal)
    assert result.output.generated_model == "gpt-5.6-sol"
    assert result.audit.structured_validation == "PASS"
    assert result.audit.deterministic_fallback is False
    assert result.decision.reason_code == "STRUCTURED_OUTPUT_VALIDATED"
    serialized = str(result.decision.model_dump()).lower()
    assert "chain-of-thought" not in serialized
    assert "calculationrecord" not in str(result.output.model_dump()).lower()


@pytest.mark.asyncio
async def test_scheme_semantic_validation_retries_same_route_then_passes() -> None:
    research_object, goal = research_inputs()
    invalid = valid_scheme()
    invalid["calculation_requirements"] = ["let_the_llm_calculate"]
    provider = FakeProvider([invalid, valid_scheme()])

    result = await TeamoRouterSchemeGenerator(provider).generate_with_decision(
        research_object=research_object,
        goal=goal,
    )

    assert len(provider.calls) == 2
    assert result.audit.validation_attempts == 2
    assert result.audit.actual_model == "gpt-5.6-sol"


@pytest.mark.asyncio
async def test_provider_outage_preserves_deterministic_scheme_fallback() -> None:
    research_object, goal = research_inputs()
    provider = FakeProvider(
        [
            LLMProviderUnavailableError(
                "offline",
                requested_model="gpt-5.6-sol",
                attempted_models=("gpt-5.6-sol", "gpt-5.6-luna"),
            )
        ]
    )

    result = await TeamoRouterSchemeGenerator(provider).generate_with_decision(
        research_object=research_object,
        goal=goal,
    )

    assert result.audit.deterministic_fallback is True
    assert result.audit.requested_model == "gpt-5.6-sol"
    assert result.audit.attempted_models == ["gpt-5.6-sol", "gpt-5.6-luna"]
    assert result.output.generated_by == "deterministic-scheme-generator-v1"
    assert result.decision.decision_type == "SCHEME_GENERATOR_FALLBACK"


@pytest.mark.asyncio
async def test_llm_planner_builds_valid_acyclic_graph_and_audit_decision() -> None:
    research_object, goal = research_inputs()
    scheme = await DeterministicSchemeGenerator().generate(
        research_object=research_object, goal=goal
    )
    scheme.confirmed_at = datetime.now(UTC)
    provider = FakeProvider([valid_graph()])

    result = await TeamoRouterResearchLeadPlanner(provider).plan_with_decision(
        run_id="RUN-1", goal=goal, scheme=scheme
    )

    assert isinstance(provider.calls[0][0].model_validate(valid_graph()), PlannedGraphProposal)
    assert len(result.output.tasks) == 7
    assert result.output.graph_id == "RUN-1:planned:llm:v1"
    assert result.audit.structured_validation == "PASS"
    assert result.decision.reason_code == "STRUCTURED_GRAPH_VALIDATED"
    known = {task.task_id for task in result.output.tasks}
    assert all(set(task.dependencies) <= known for task in result.output.tasks)


@pytest.mark.asyncio
async def test_invalid_graph_retries_then_uses_deterministic_lead_plan() -> None:
    research_object, goal = research_inputs()
    scheme = await DeterministicSchemeGenerator().generate(
        research_object=research_object, goal=goal
    )
    scheme.confirmed_at = datetime.now(UTC)
    cyclic = valid_graph()
    cyclic["tasks"][0]["dependency_keys"] = ["synthesis"]
    provider = FakeProvider([cyclic, cyclic])

    result = await TeamoRouterResearchLeadPlanner(provider).plan_with_decision(
        run_id="RUN-2", goal=goal, scheme=scheme
    )

    assert len(provider.calls) == 2
    assert result.audit.deterministic_fallback is True
    assert result.output.graph_id == "RUN-2:planned:v1"
    assert result.decision.decision_type == "INITIAL_PLAN_FALLBACK"
