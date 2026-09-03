from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import NAMESPACE_URL, uuid5

from pydantic import ConfigDict, Field

from src.adapters.llm import (
    LLMMessage,
    LLMProvider,
    LLMProviderError,
    LLMStructuredResponse,
    StructuredOutputError,
)
from src.agentic.planner import ResearchLeadPlanner
from src.agentic.scheme import DeterministicSchemeGenerator
from src.domain.base import DomainModel
from src.domain.decision import StructuredAgentDecision
from src.domain.enums import TaskOrigin, TaskStatus
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.task import PlannedTaskGraph, Task


class _StrictModel(DomainModel):
    model_config = ConfigDict(extra="forbid")


class SchemeProposal(_StrictModel):
    research_scope: list[str] = Field(min_length=1)
    data_requirements: list[str] = Field(min_length=1)
    agent_requirements: list[str] = Field(min_length=1)
    skill_requirements: list[str] = Field(min_length=1)
    calculation_requirements: list[str] = Field(min_length=1)
    assurance_requirements: dict[str, bool]
    report_requirements: list[str] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)


class PlannedTaskProposal(_StrictModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    task_type: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    assigned_agent: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    dependency_keys: list[str] = Field(default_factory=list)


class PlannedGraphProposal(_StrictModel):
    tasks: list[PlannedTaskProposal] = Field(min_length=1)


class LLMExecutionAudit(_StrictModel):
    provider: str
    requested_model: str
    actual_model: str | None
    attempted_models: list[str] = Field(default_factory=list)
    structured_validation: str
    validation_attempts: int = Field(ge=0)
    deterministic_fallback: bool


OutputModel = TypeVar("OutputModel")


@dataclass(frozen=True, slots=True)
class AgenticLLMResult(Generic[OutputModel]):
    output: OutputModel
    decision: StructuredAgentDecision
    audit: LLMExecutionAudit


class TeamoRouterSchemeGenerator:
    generator_id = "teamorouter-scheme-generator-v1"

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_validation_attempts: int = 2,
        fallback: DeterministicSchemeGenerator | None = None,
    ) -> None:
        if max_validation_attempts < 1:
            raise ValueError("max_validation_attempts must be positive")
        self._provider = provider
        self._max_validation_attempts = max_validation_attempts
        self._fallback = fallback or DeterministicSchemeGenerator()
        self.decisions: list[StructuredAgentDecision] = []
        self.last_audit: LLMExecutionAudit | None = None

    async def generate(
        self,
        *,
        research_object: ResearchObject,
        goal: ResearchGoal,
    ) -> ResearchSchemeSnapshot:
        result = await self.generate_with_decision(research_object=research_object, goal=goal)
        return result.output

    async def generate_with_decision(
        self,
        *,
        research_object: ResearchObject,
        goal: ResearchGoal,
    ) -> AgenticLLMResult[ResearchSchemeSnapshot]:
        if goal.research_object_id != research_object.object_id:
            raise ValueError("goal and research object must reference the same object")
        messages = _scheme_messages(research_object, goal)
        last_error: LLMProviderError | ValueError | None = None
        for attempt in range(1, self._max_validation_attempts + 1):
            try:
                response = await self._provider.complete_structured(
                    messages=messages,
                    response_model=SchemeProposal,
                    schema_name="research_scheme_proposal_v1",
                )
                _validate_scheme_proposal(response.output)
                scheme_key = f"{research_object.object_id}:{goal.goal_id}:{goal.as_of}:llm"
                scheme = ResearchSchemeSnapshot(
                    scheme_id=f"SCHEME-{uuid5(NAMESPACE_URL, scheme_key)}",
                    research_object_id=research_object.object_id,
                    goal_id=goal.goal_id,
                    generated_by=self.generator_id,
                    generated_model=response.actual_model,
                    **response.output.model_dump(),
                )
                return self._record_scheme_result(
                    scheme=scheme,
                    goal=goal,
                    response=response,
                    attempt=attempt,
                )
            except (StructuredOutputError, ValueError) as exc:
                last_error = exc
                messages = _with_validation_retry(messages, type(exc).__name__)
            except LLMProviderError as exc:
                last_error = exc
                break
        fallback = await self._fallback.generate(research_object=research_object, goal=goal)
        reason = type(last_error).__name__ if last_error else "UNKNOWN"
        decision = StructuredAgentDecision(
            decision_id=_decision_id(goal.goal_id, "scheme", "deterministic"),
            run_id=f"DRAFT:{goal.goal_id}",
            decision_type="SCHEME_GENERATOR_FALLBACK",
            reason_code=reason,
            summary="LLM scheme was unavailable or invalid; deterministic scheme fallback used.",
            requires_review=False,
        )
        audit = LLMExecutionAudit(
            provider="teamorouter",
            requested_model=_fallback_requested_model(last_error, self._provider),
            actual_model=None,
            attempted_models=_fallback_attempted_models(last_error),
            structured_validation="FALLBACK",
            validation_attempts=self._max_validation_attempts,
            deterministic_fallback=True,
        )
        self.decisions.append(decision)
        self.last_audit = audit
        return AgenticLLMResult(output=fallback, decision=decision, audit=audit)

    def _record_scheme_result(
        self,
        *,
        scheme: ResearchSchemeSnapshot,
        goal: ResearchGoal,
        response: LLMStructuredResponse[SchemeProposal],
        attempt: int,
    ) -> AgenticLLMResult[ResearchSchemeSnapshot]:
        decision = StructuredAgentDecision(
            decision_id=_decision_id(goal.goal_id, "scheme", response.actual_model),
            run_id=f"DRAFT:{goal.goal_id}",
            decision_type="SCHEME_GENERATED",
            reason_code="STRUCTURED_OUTPUT_VALIDATED",
            summary=(
                f"Validated scheme schema from requested model {response.requested_model}; "
                f"actual model {response.actual_model}. No financial values were generated."
            ),
            confidence=1.0,
            requires_review=False,
        )
        audit = _audit(response, attempt)
        self.decisions.append(decision)
        self.last_audit = audit
        return AgenticLLMResult(output=scheme, decision=decision, audit=audit)


class TeamoRouterResearchLeadPlanner:
    planner_id = "teamorouter-research-lead-planner-v1"

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_validation_attempts: int = 2,
        fallback: ResearchLeadPlanner | None = None,
    ) -> None:
        if max_validation_attempts < 1:
            raise ValueError("max_validation_attempts must be positive")
        self._provider = provider
        self._max_validation_attempts = max_validation_attempts
        self._fallback = fallback or ResearchLeadPlanner()
        self.decisions: list[StructuredAgentDecision] = []
        self.last_audit: LLMExecutionAudit | None = None

    async def plan(
        self,
        *,
        run_id: str,
        goal: ResearchGoal,
        scheme: ResearchSchemeSnapshot,
    ) -> PlannedTaskGraph:
        result = await self.plan_with_decision(run_id=run_id, goal=goal, scheme=scheme)
        return result.output

    async def plan_with_decision(
        self,
        *,
        run_id: str,
        goal: ResearchGoal,
        scheme: ResearchSchemeSnapshot,
    ) -> AgenticLLMResult[PlannedTaskGraph]:
        _validate_planner_inputs(run_id=run_id, goal=goal, scheme=scheme)
        messages = _planner_messages(run_id, goal, scheme)
        last_error: LLMProviderError | ValueError | None = None
        for attempt in range(1, self._max_validation_attempts + 1):
            try:
                response = await self._provider.complete_structured(
                    messages=messages,
                    response_model=PlannedGraphProposal,
                    schema_name="planned_task_graph_v1",
                )
                graph = _build_validated_graph(run_id, scheme, response.output)
                decision = StructuredAgentDecision(
                    decision_id=_decision_id(run_id, "plan", response.actual_model),
                    run_id=run_id,
                    decision_type="INITIAL_PLAN_GENERATED",
                    reason_code="STRUCTURED_GRAPH_VALIDATED",
                    summary=(
                        f"Validated {len(graph.tasks)}-task graph from requested model "
                        f"{response.requested_model}; actual model {response.actual_model}."
                    ),
                    confidence=1.0,
                    requires_review=False,
                )
                audit = _audit(response, attempt)
                self.decisions.append(decision)
                self.last_audit = audit
                return AgenticLLMResult(output=graph, decision=decision, audit=audit)
            except (StructuredOutputError, ValueError) as exc:
                last_error = exc
                messages = _with_validation_retry(messages, type(exc).__name__)
            except LLMProviderError as exc:
                last_error = exc
                break
        graph = self._fallback.plan(run_id=run_id, goal=goal, scheme=scheme)
        reason = type(last_error).__name__ if last_error else "UNKNOWN"
        decision = StructuredAgentDecision(
            decision_id=_decision_id(run_id, "plan", "deterministic"),
            run_id=run_id,
            decision_type="INITIAL_PLAN_FALLBACK",
            reason_code=reason,
            summary="LLM graph was unavailable or invalid; deterministic Lead plan used.",
            requires_review=False,
        )
        audit = LLMExecutionAudit(
            provider="teamorouter",
            requested_model=_fallback_requested_model(last_error, self._provider),
            actual_model=None,
            attempted_models=_fallback_attempted_models(last_error),
            structured_validation="FALLBACK",
            validation_attempts=self._max_validation_attempts,
            deterministic_fallback=True,
        )
        self.decisions.append(decision)
        self.last_audit = audit
        return AgenticLLMResult(output=graph, decision=decision, audit=audit)


def _scheme_messages(research_object: ResearchObject, goal: ResearchGoal) -> list[LLMMessage]:
    system = (
        "Create a research method only. Return the strict JSON schema. Never generate financial "
        "numbers, estimates, CalculationRecords, or hidden reasoning. Require accepted evidence "
        "and deterministic code for every calculable financial value."
    )
    user = json.dumps(
        {
            "research_object": research_object.model_dump(mode="json"),
            "goal": goal.model_dump(mode="json"),
        },
        sort_keys=True,
    )
    return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]


def _planner_messages(
    run_id: str,
    goal: ResearchGoal,
    scheme: ResearchSchemeSnapshot,
) -> list[LLMMessage]:
    system = (
        "Build the complete initial task graph before execution. Return strict JSON only. "
        "Dependencies must use task keys, be acyclic, and reference declared tasks. Include every "
        "required skill. Do not generate financial values, calculations, or chain-of-thought."
    )
    user = json.dumps(
        {
            "run_id": run_id,
            "goal": goal.model_dump(mode="json"),
            "confirmed_scheme": scheme.model_dump(mode="json"),
        },
        sort_keys=True,
    )
    return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]


def _with_validation_retry(messages: list[LLMMessage], error_type: str) -> list[LLMMessage]:
    return messages + [
        LLMMessage(
            role="user",
            content=(
                f"The previous structured response failed validation ({error_type}). "
                "Return a corrected object matching the exact schema; do not add explanation."
            ),
        )
    ]


def _validate_scheme_proposal(proposal: SchemeProposal) -> None:
    required_calculations = {
        "deterministic_financial_calculations_only",
        "calculation_records_for_reported_values",
    }
    if not required_calculations.issubset(proposal.calculation_requirements):
        raise ValueError("scheme must preserve deterministic calculation requirements")
    if proposal.assurance_requirements.get("accepted_evidence_only") is not True:
        raise ValueError("scheme must require accepted evidence")
    if proposal.assurance_requirements.get("deterministic_financial_values") is not True:
        raise ValueError("scheme must require deterministic financial values")
    _reject_numeric_values(proposal.model_dump())


def _reject_numeric_values(value: object) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        raise ValueError("LLM scheme must not contain financial numeric values")
    if isinstance(value, list):
        for item in value:
            _reject_numeric_values(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            _reject_numeric_values(item)
        return
    raise ValueError(f"unsupported scheme value type: {type(value).__name__}")


def _validate_planner_inputs(
    *, run_id: str, goal: ResearchGoal, scheme: ResearchSchemeSnapshot
) -> None:
    if not run_id:
        raise ValueError("run_id is required")
    if scheme.confirmed_at is None:
        raise ValueError("the research scheme must be confirmed before planning")
    if scheme.goal_id != goal.goal_id or scheme.research_object_id != goal.research_object_id:
        raise ValueError("scheme and goal identifiers must match")


def _build_validated_graph(
    run_id: str,
    scheme: ResearchSchemeSnapshot,
    proposal: PlannedGraphProposal,
) -> PlannedTaskGraph:
    keys = [task.key for task in proposal.tasks]
    if len(keys) != len(set(keys)):
        raise ValueError("planned task keys must be unique")
    known = set(keys)
    unknown = {
        dependency
        for task in proposal.tasks
        for dependency in task.dependency_keys
        if dependency not in known
    }
    if unknown:
        raise ValueError(f"unknown task dependencies: {sorted(unknown)}")
    _ensure_acyclic(proposal)
    supplied_skills = {task.skill_id for task in proposal.tasks}
    missing_skills = set(scheme.skill_requirements) - supplied_skills
    if missing_skills:
        raise ValueError(f"planned graph omits required skills: {sorted(missing_skills)}")
    ids = {key: f"{run_id}:{key}" for key in keys}
    tasks = [
        Task(
            task_id=ids[item.key],
            run_id=run_id,
            task_type=item.task_type,
            goal=item.goal,
            assigned_agent=item.assigned_agent,
            skill_id=item.skill_id,
            dependencies=[ids[key] for key in item.dependency_keys],
            origin=TaskOrigin.PLAN,
            status=TaskStatus.CREATED,
        )
        for item in proposal.tasks
    ]
    return PlannedTaskGraph(
        graph_id=f"{run_id}:planned:llm:v1",
        run_id=run_id,
        tasks=tasks,
    )


def _ensure_acyclic(proposal: PlannedGraphProposal) -> None:
    dependencies = {task.key: set(task.dependency_keys) for task in proposal.tasks}
    remaining = set(dependencies)
    while remaining:
        ready = {key for key in remaining if not (dependencies[key] & remaining)}
        if not ready:
            raise ValueError("planned graph must be acyclic")
        remaining -= ready


def _audit(response: LLMStructuredResponse[DomainModel], attempt: int) -> LLMExecutionAudit:
    return LLMExecutionAudit(
        provider=response.provider,
        requested_model=response.requested_model,
        actual_model=response.actual_model,
        attempted_models=list(response.attempted_models),
        structured_validation="PASS",
        validation_attempts=attempt,
        deterministic_fallback=False,
    )


def _decision_id(scope: str, kind: str, model: str) -> str:
    return f"DEC-{uuid5(NAMESPACE_URL, f'{scope}:{kind}:{model}')}"


def _requested_model(provider: LLMProvider) -> str:
    settings = getattr(provider, "_settings", None)
    value = getattr(settings, "primary_model", None)
    return value if isinstance(value, str) and value else "configured-primary"


def _fallback_requested_model(
    error: LLMProviderError | ValueError | None,
    provider: LLMProvider,
) -> str:
    value = getattr(error, "requested_model", None)
    return value if isinstance(value, str) and value else _requested_model(provider)


def _fallback_attempted_models(error: LLMProviderError | ValueError | None) -> list[str]:
    values = getattr(error, "attempted_models", ())
    return [value for value in values if isinstance(value, str)]
