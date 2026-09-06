from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters.llm import LLMMessage, LLMStructuredResponse
from src.agentic import AgentRegistry
from src.agentic.research_agent import LLMResearchAgent
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.application.persistence import (
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.application.service import ResearchApplicationService
from src.domain.enums import RunStatus, TaskStatus
from src.infrastructure.database.base import Base


class RecordingProvider:
    provider_name = "test-provider"
    model_name = "test-model"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def complete_structured(
        self,
        *,
        messages: list[LLMMessage],
        response_model: type,
        schema_name: str,
        force_fallback: bool = False,
        workload_type: str | None = None,
    ) -> LLMStructuredResponse:
        del force_fallback
        payload = json.loads(messages[-1].content)
        self.calls.append(payload)
        task_type = str(payload["task_type"])
        return LLMStructuredResponse(
            output=response_model.model_validate(
                {
                    "summary": f"{task_type} 已完成严格结构化研究输出。",
                    "key_findings": [f"{task_type} 仅使用当前 Run 的权威输入。"],
                    "risks": ["结论受当前证据覆盖范围限制。"],
                    "limitations": ["不生成缺失的金融事实或估值。"],
                    "requires_follow_up": False,
                }
            ),
            provider=self.provider_name,
            requested_model=self.model_name,
            actual_model=self.model_name,
            attempted_models=(self.model_name,),
            request_id=f"REQ-{schema_name}",
            input_tokens=100,
            output_tokens=40,
        )


def research_agents(
    provider: RecordingProvider,
    store: ResearchAgentOutputArtifactStore,
) -> AgentRegistry:
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
                artifacts=store,
            )
        )
    return registry


@pytest.mark.asyncio
async def test_real_agent_outputs_persist_and_synthesis_consumes_exact_specialists(
    tmp_path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'application.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    provider = RecordingProvider()
    store = ResearchAgentOutputArtifactStore(tmp_path / "agent-outputs")
    service = ResearchApplicationService(
        repository=SQLAlchemyApplicationRepository(sessions),
        evidence_repository=SessionFactoryEvidenceRepository(sessions),
        agent_registry=research_agents(provider, store),
    )
    research_object = await service.create_object(
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
    )
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Evaluate fundamentals and material risks",
        as_of=date(2026, 9, 3),
        preferences={"depth": "standard"},
    )
    admitted = await service.confirm_run(
        draft_id=draft.draft_id,
        confirm_scheme=True,
    )

    completed = await service.execute_run(admitted.run.run_id)

    assert completed.run.status is RunStatus.RELEASED
    assert len(provider.calls) == 6
    assert {call["actor"] for call in provider.calls} == {
        "fundamental_analyst",
        "peer_analyst",
        "research_news_analyst",
        "valuation_analyst",
        "risk_analyst",
        "research_lead",
    }
    outputs = completed.artifacts.agent_outputs
    assert len(outputs) == 6
    assert all(output.run_id == completed.run.run_id for output in outputs)
    assert all(output.status == "SUCCESS" for output in outputs)
    assert all(output.input_tokens == 100 and output.output_tokens == 40 for output in outputs)
    task_by_id = {task.task_id: task for task in completed.runtime.actual_graph.tasks}
    for output in outputs:
        task = task_by_id[output.task_id]
        assert task.status is TaskStatus.COMPLETED
        assert task.run_id == output.run_id
        assert task.assigned_agent == output.actor
        assert task.result_ref == output.artifact_ref
        assert output.output_id in completed.runtime.completed_output_refs[task.task_id]
        artifact = json.loads(store.read_verified(output))
        assert artifact["run_id"] == completed.run.run_id
        assert artifact["task_id"] == task.task_id
        assert artifact["actor"] == task.assigned_agent

    synthesis = next(output for output in outputs if output.actor == "research_lead")
    specialist_ids = {output.output_id for output in outputs if output.actor != "research_lead"}
    assert specialist_ids.issubset(set(synthesis.input_refs))
    synthesis_call = next(call for call in provider.calls if call["actor"] == "research_lead")
    supplied = synthesis_call["authoritative_inputs"]["upstream_agent_outputs"]
    assert {item["output_id"] for item in supplied} == specialist_ids
    assert completed.artifacts.released_result is not None
    assert completed.artifacts.canonical_record is not None
    assert completed.artifacts.released_result.structured_financial_results[
        "investment_thesis"
    ]["summary"] == synthesis.structured_output.summary
    assert set(completed.artifacts.canonical_record.agent_output_refs) == {
        output.output_id for output in outputs
    }
    assert completed.artifacts.canonical_record.token_usage == 6 * 140

    restored = await SQLAlchemyApplicationRepository(sessions).get_run(completed.run.run_id)
    assert restored is not None
    assert [item.output_id for item in restored.artifacts.agent_outputs] == [
        item.output_id for item in outputs
    ]
    assert all(item.run_id == restored.run.run_id for item in restored.artifacts.agent_outputs)
    await engine.dispose()
