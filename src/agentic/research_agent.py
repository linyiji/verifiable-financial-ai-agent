from __future__ import annotations

import json
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from src.adapters.llm import LLMMessage, LLMProvider, LLMProviderError
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.agentic.specialist import SpecialistExecutionContext, SpecialistResult
from src.domain.agent_output import (
    ResearchAgentOutputRecord,
    ResearchAgentStructuredOutput,
    RiskResearchAgentStructuredOutput,
    StandardResearchAgentStructuredOutput,
)
from src.domain.decision import StructuredAgentDecision
from src.domain.task import ReplanRequest


class ResearchAgentInvocationError(RuntimeError):
    """A safe task failure carrying the durable failed-invocation record."""

    retryable = False

    def __init__(self, record: ResearchAgentOutputRecord) -> None:
        super().__init__("research Agent provider execution failed")
        self.record = record


class LLMResearchAgent:
    """Provider-backed specialist/Lead boundary with strict structured output."""

    def __init__(
        self,
        *,
        agent_id: str,
        supported_task_types: frozenset[str],
        provider: LLMProvider,
        artifacts: ResearchAgentOutputArtifactStore,
        recovery=None,
    ) -> None:
        if not agent_id.strip() or not supported_task_types:
            raise ValueError("research Agent identity and task types are required")
        self.agent_id = agent_id
        self.supported_task_types = supported_task_types
        self._provider = provider
        self._artifacts = artifacts
        self._recovery = recovery

    async def execute(self, context: SpecialistExecutionContext) -> SpecialistResult:
        task = context.task
        if task.assigned_agent != self.agent_id:
            raise ValueError("research Agent was dispatched under another actor identity")
        if task.task_type not in self.supported_task_types:
            raise ValueError("research Agent does not support the dispatched task type")
        input_refs = _input_refs(context)
        response_model: type[ResearchAgentStructuredOutput] = (
            RiskResearchAgentStructuredOutput
            if task.task_type == "risk_analysis"
            else StandardResearchAgentStructuredOutput
        )
        started = perf_counter()
        try:
            request = dict(
                messages=_messages(context),
                response_model=response_model,
                schema_name=f"{task.task_type}_research_output_v1",
                workload_type="RESEARCH_AGENT_EXECUTION",
            )
            response = (
                await self._recovery.execute(context, self._provider, **request)
                if self._recovery is not None
                else await self._provider.complete_structured(**request)
            )
        except LLMProviderError as exc:
            duration_ms = max(0, round((perf_counter() - started) * 1000))
            record = self._artifacts.retain_failure(
                task=task,
                provider_name=self._provider.provider_name,
                requested_model=self._provider.model_name,
                error=exc,
                duration_ms=duration_ms,
                input_refs=input_refs,
            )
            raise ResearchAgentInvocationError(record) from exc

        duration_ms = max(0, round((perf_counter() - started) * 1000))
        record = self._artifacts.retain_success(
            task=task,
            response=response,
            duration_ms=duration_ms,
            input_refs=input_refs,
        )
        decision = StructuredAgentDecision(
            decision_id=(
                f"DEC-{uuid5(NAMESPACE_URL, f'{task.run_id}:{task.task_id}:{record.output_id}')}"
            ),
            run_id=task.run_id,
            task_id=task.task_id,
            decision_type="RESEARCH_OUTPUT_ACCEPTED",
            reason_code="STRICT_STRUCTURED_OUTPUT_VALIDATED",
            summary="Validated and retained the assigned research Agent output.",
            evidence_ids=list(context.accepted_evidence_ids),
            selected_skill=task.skill_id,
            requires_review=True,
        )
        replan_request = (
            ReplanRequest(
                replan_id=f"REPLAN-{task.run_id}-RISK",
                run_id=task.run_id,
                requesting_task_id=task.task_id,
                requested_by=task.assigned_agent,
                reason_code="MATERIAL_RISK_FOLLOW_UP",
                reason_detail=(
                    "The Risk Analyst requested one bounded follow-up from its retained "
                    "structured output."
                ),
                proposed_graph_change={
                    "operation": "add_child_task",
                    "add_child_task_type": "risk_follow_up",
                },
            )
            if task.task_type == "risk_analysis" and response.output.requires_follow_up
            else None
        )
        return SpecialistResult(
            output={
                **response.output.model_dump(mode="json"),
                "agent_output_id": record.output_id,
            },
            decision=decision,
            replan_request=replan_request,
            agent_output=record,
        )


def _messages(context: SpecialistExecutionContext) -> list[LLMMessage]:
    task = context.task
    follow_up_instruction = (
        "Set requires_follow_up true only when one bounded risk follow-up is materially "
        "necessary; otherwise set it false."
        if task.task_type == "risk_analysis"
        else "Set requires_follow_up to false."
    )
    system = (
        "Act only as the assigned financial research role. Return one object matching the "
        "strict JSON schema. Use only the normalized evidence, deterministic outputs, and "
        "upstream Agent outputs supplied in the input. Do not calculate or estimate financial "
        "values; deterministic CalculationRecords are authoritative for numbers. Do not invent "
        "missing evidence, peers, news, valuation results, or citations. State unavailable "
        "information as a limitation. Write concise Chinese-first business conclusions. Never "
        "return prompts, provider payloads, chain-of-thought, private reasoning, or an explanation "
        f"outside the schema. {follow_up_instruction}"
    )
    inputs = context.inputs
    evidence_identity = {"accepted_evidence_ids": context.accepted_evidence_ids}
    if task.task_type == "risk_follow_up" and "risk_follow_up" in inputs:
        # The typed child context already contains the evidence identity set.
        # Keep complete input_refs on the durable AgentOutput, not duplicated
        # a second time in the model request.
        inputs = {key: value for key, value in inputs.items() if key != "input_refs"}
        evidence_identity = {}
    user = json.dumps(
        {
            "run_id": task.run_id,
            "task_id": task.task_id,
            "actor": task.assigned_agent,
            "task_type": task.task_type,
            "task_goal": task.goal,
            **evidence_identity,
            "authoritative_inputs": inputs,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]


def _input_refs(context: SpecialistExecutionContext) -> list[str]:
    raw = context.inputs.get("input_refs", [])
    if not isinstance(raw, list) or any(not isinstance(value, str) for value in raw):
        raise ValueError("research Agent input refs must be a string list")
    return list(dict.fromkeys([context.task.task_id, *raw]))
