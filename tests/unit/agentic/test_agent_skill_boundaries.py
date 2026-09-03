import pytest

from src.agentic.registry import (
    AgentRegistry,
    DuplicateRegistrationError,
    RegistrationNotFoundError,
    SkillRegistry,
)
from src.agentic.skill import Skill, SkillContext, SkillDefinition, SkillResult
from src.agentic.specialist import (
    SpecialistAgent,
    SpecialistExecutionContext,
    SpecialistResult,
)
from src.domain.base import JsonObject
from src.domain.decision import StructuredAgentDecision
from src.domain.enums import ReplanDecision
from src.domain.task import ReplanRequest, Task


class StubAgent:
    agent_id = "fundamental_analyst"
    supported_task_types = frozenset({"fundamental_analysis"})

    async def execute(self, context: SpecialistExecutionContext) -> SpecialistResult:
        return SpecialistResult(
            output={"artifact_ref": "ART-1"},
            decision=_decision(context.task.run_id, context.task.task_id),
        )


class StubSkill:
    definition = SkillDefinition(
        skill_id="fundamental_analysis_v1",
        version="1.0.0",
        name="Fundamental analysis",
        allowed_capability_ids=["financial_statements_v1"],
    )

    async def execute(self, inputs: JsonObject, context: SkillContext) -> SkillResult:
        return SkillResult(
            output={"artifact_ref": inputs.get("artifact_ref")},
            decision=_decision(context.run_id, context.task_id),
        )


def _decision(run_id: str = "RUN-1", task_id: str = "TASK-1") -> StructuredAgentDecision:
    return StructuredAgentDecision(
        decision_id="DECISION-1",
        run_id=run_id,
        task_id=task_id,
        decision_type="SKILL_SELECTION",
        reason_code="SCHEME_REQUIREMENT",
        summary="Selected the registered skill required by the confirmed scheme.",
        selected_skill="fundamental_analysis_v1",
    )


def _task() -> Task:
    return Task(
        task_id="TASK-1",
        run_id="RUN-1",
        task_type="fundamental_analysis",
        goal="Analyze fundamentals",
        assigned_agent="fundamental_analyst",
        skill_id="fundamental_analysis_v1",
    )


def test_specialist_and_skill_protocols_and_registries() -> None:
    agent = StubAgent()
    skill = StubSkill()
    agents = AgentRegistry()
    skills = SkillRegistry()

    assert isinstance(agent, SpecialistAgent)
    assert isinstance(skill, Skill)

    agents.register(agent)
    skills.register(skill)

    assert agents.get(agent.agent_id) is agent
    assert agents.for_task_type("fundamental_analysis") == (agent,)
    assert agents.for_task_type("valuation_analysis") == ()
    assert skills.get(skill.definition.skill_id) is skill
    assert agents.registered_ids() == ("fundamental_analyst",)
    assert skills.registered_ids() == ("fundamental_analysis_v1",)


def test_registries_reject_duplicates_and_unknown_ids() -> None:
    agents = AgentRegistry()
    skills = SkillRegistry()
    agents.register(StubAgent())
    skills.register(StubSkill())

    with pytest.raises(DuplicateRegistrationError, match="agent already registered"):
        agents.register(StubAgent())
    with pytest.raises(DuplicateRegistrationError, match="skill already registered"):
        skills.register(StubSkill())
    with pytest.raises(RegistrationNotFoundError, match="agent not registered"):
        agents.get("missing")
    with pytest.raises(RegistrationNotFoundError, match="skill not registered"):
        skills.get("missing")


def test_specialist_context_has_no_graph_mutation_surface() -> None:
    assert set(SpecialistExecutionContext.model_fields) == {
        "task",
        "accepted_evidence_ids",
        "inputs",
    }
    assert "graph" not in SpecialistExecutionContext.model_fields


def test_specialist_result_validates_replan_request_scope() -> None:
    request = ReplanRequest(
        replan_id="REPLAN-1",
        run_id="RUN-1",
        requesting_task_id="TASK-OTHER",
        requested_by="fundamental_analyst",
        reason_code="MISSING_DEPENDENCY",
        reason_detail="A required evidence category is not available.",
        proposed_graph_change={"add_task_type": "evidence_collection"},
    )

    with pytest.raises(ValueError, match="same task"):
        SpecialistResult(decision=_decision(), replan_request=request)


@pytest.mark.parametrize(
    ("request_update", "message"),
    [
        ({"decision": ReplanDecision.APPROVED}, "only submit pending"),
        ({"decided_by": "fundamental_analyst"}, "cannot decide"),
        ({"created_task_ids": ["TASK-NEW"]}, "cannot create graph tasks"),
    ],
)
def test_specialist_cannot_smuggle_graph_decision_or_mutation(
    request_update: JsonObject,
    message: str,
) -> None:
    request = ReplanRequest(
        replan_id="REPLAN-1",
        run_id="RUN-1",
        requesting_task_id="TASK-1",
        requested_by="fundamental_analyst",
        reason_code="MISSING_DEPENDENCY",
        reason_detail="A required evidence category is not available.",
        proposed_graph_change={"add_task_type": "evidence_collection"},
    ).model_copy(update=request_update)

    with pytest.raises(ValueError, match=message):
        SpecialistResult(decision=_decision(), replan_request=request)


@pytest.mark.asyncio
async def test_specialist_output_is_structured_and_does_not_mutate_task() -> None:
    task = _task()
    result = await StubAgent().execute(SpecialistExecutionContext(task=task))

    assert result.output == {"artifact_ref": "ART-1"}
    assert result.decision.summary
    assert task.status.value == "CREATED"
