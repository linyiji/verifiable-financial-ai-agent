from __future__ import annotations

import json

import pytest

from src.adapters.llm import (
    LLMFailureClassification,
    LLMMessage,
    LLMRequestError,
    LLMStructuredResponse,
)
from src.agentic.research_agent import LLMResearchAgent, ResearchAgentInvocationError
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.agentic.specialist import SpecialistExecutionContext
from src.domain.agent_output import StandardResearchAgentStructuredOutput
from src.domain.task import Task


class SuccessfulProvider:
    provider_name = "test-provider"
    model_name = "test-model"

    async def complete_structured(
        self,
        *,
        messages: list[LLMMessage],
        response_model: type,
        schema_name: str,
        force_fallback: bool = False,
        workload_type: str | None = None,
    ) -> LLMStructuredResponse:
        del schema_name, force_fallback
        assert workload_type == "RESEARCH_AGENT_EXECUTION"
        assert "accepted_evidence_ids" in json.loads(messages[-1].content)
        return LLMStructuredResponse(
            output=response_model.model_validate(
                {
                    "summary": "基本面分析已基于规范化证据完成。",
                    "key_findings": ["收入与 EBITDA 仅引用确定性计算结果。"],
                    "risks": [],
                    "limitations": ["不在当前任务内生成估值。"],
                    "requires_follow_up": False,
                }
            ),
            provider=self.provider_name,
            requested_model=self.model_name,
            actual_model=self.model_name,
            attempted_models=(self.model_name,),
            request_id="REQ-safe",
            input_tokens=123,
            output_tokens=45,
        )


class FailingProvider(SuccessfulProvider):
    async def complete_structured(self, **kwargs) -> LLMStructuredResponse:
        del kwargs
        raise LLMRequestError(
            "provider body contained never-persist-this-secret",
            requested_model=self.model_name,
            attempted_models=(self.model_name,),
            failure_classification=LLMFailureClassification.REQUEST_REJECTED,
            provider=self.provider_name,
            model=self.model_name,
            workload_type="RESEARCH_AGENT_EXECUTION",
        )


def task() -> Task:
    return Task(
        task_id="RUN-1:fundamentals",
        run_id="RUN-1",
        task_type="fundamental_analysis",
        goal="Analyze fundamentals",
        assigned_agent="fundamental_analyst",
        skill_id="fundamental_analysis_v1",
    )


@pytest.mark.asyncio
async def test_research_agent_retains_strict_safe_exact_task_output(tmp_path) -> None:
    store = ResearchAgentOutputArtifactStore(
        tmp_path / "outputs",
        forbidden_values=("never-persist-this-secret",),
    )
    agent = LLMResearchAgent(
        agent_id="fundamental_analyst",
        supported_task_types=frozenset({"fundamental_analysis"}),
        provider=SuccessfulProvider(),
        artifacts=store,
    )

    result = await agent.execute(
        SpecialistExecutionContext(
            task=task(),
            accepted_evidence_ids=["EVIDENCE-1"],
            inputs={"input_refs": ["GOAL-1", "EVIDENCE-1"]},
        )
    )

    record = result.agent_output
    assert record is not None
    assert (record.run_id, record.task_id, record.actor) == (
        "RUN-1",
        "RUN-1:fundamentals",
        "fundamental_analyst",
    )
    assert record.status == "SUCCESS"
    assert (record.provider, record.requested_model, record.actual_model) == (
        "test-provider",
        "test-model",
        "test-model",
    )
    assert (record.input_tokens, record.output_tokens) == (123, 45)
    assert record.input_refs == ["RUN-1:fundamentals", "GOAL-1", "EVIDENCE-1"]
    artifact = json.loads(store.read_verified(record))
    assert artifact["structured_output"]["summary"] == record.structured_output.summary
    serialized = json.dumps(artifact).lower()
    assert "prompt" not in serialized
    assert "reasoning" not in serialized
    assert "chain-of-thought" not in serialized
    assert "never-persist-this-secret" not in serialized


@pytest.mark.asyncio
async def test_research_agent_failure_retains_only_safe_failure_metadata(tmp_path) -> None:
    store = ResearchAgentOutputArtifactStore(
        tmp_path / "outputs",
        forbidden_values=("never-persist-this-secret",),
    )
    agent = LLMResearchAgent(
        agent_id="fundamental_analyst",
        supported_task_types=frozenset({"fundamental_analysis"}),
        provider=FailingProvider(),
        artifacts=store,
    )

    with pytest.raises(ResearchAgentInvocationError) as captured:
        await agent.execute(
            SpecialistExecutionContext(task=task(), inputs={"input_refs": ["GOAL-1"]})
        )

    record = captured.value.record
    assert record.status == "FAILED"
    assert record.structured_output is None
    assert record.failure_code == "request_rejected"
    artifact = store.read_verified(record)
    assert b"never-persist-this-secret" not in artifact
    assert b"provider body" not in artifact


def test_standard_research_output_rejects_follow_up_and_unbounded_surface() -> None:
    payload = {
        "summary": "safe",
        "key_findings": ["finding"],
        "risks": [],
        "limitations": [],
        "requires_follow_up": True,
    }
    with pytest.raises(ValueError):
        StandardResearchAgentStructuredOutput.model_validate(payload)
    payload["requires_follow_up"] = False
    payload["raw_provider_response"] = {"secret": "no"}
    with pytest.raises(ValueError):
        StandardResearchAgentStructuredOutput.model_validate(payload)


def test_standard_research_output_schema_requires_every_strict_property() -> None:
    schema = StandardResearchAgentStructuredOutput.model_json_schema()

    assert set(schema["required"]) == set(schema["properties"])
    assert all(
        "default" not in property_schema
        for property_schema in schema["properties"].values()
    )
