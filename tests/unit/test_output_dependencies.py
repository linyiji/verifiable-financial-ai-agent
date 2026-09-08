import pytest

from src.application.research_outputs import configure_output_contracts, publish_output
from src.domain.enums import RunStatus, TaskStatus
from src.domain.output_dependency import (
    LocalOutputFailure,
    OutputRequirements,
    OutputStatus,
    evidence_sufficiency,
)
from src.domain.task import PlannedTaskGraph, Task
from src.runtime.checkpoint import InMemoryCheckpointStore
from src.runtime.events import InMemoryRuntimeEventStore
from src.runtime.scheduler import DependencyScheduler, TaskExecutionResult
from src.runtime.state import RuntimeState


def task(name, kind, deps=()):
    actors = {
        "valuation_analysis": "valuation_analyst",
        "risk_analysis": "risk_analyst",
        "report_synthesis": "research_lead",
        "fundamental_analysis": "fundamental_analyst",
    }
    return Task(
        task_id=name,
        run_id="RUN-1",
        task_type=kind,
        goal="test",
        assigned_agent=actors.get(kind, "test"),
        skill_id=kind + "_v1",
        dependencies=list(deps),
    )


def test_sufficiency_any_of_and_enrichment():
    contract = OutputRequirements(
        hard_required=["revenue"],
        any_of=[["transcript", "filing"]],
        supporting=["sma200"],
        enrichment=["news"],
    )
    result = evidence_sufficiency(contract, {"revenue", "filing"})
    assert result.status == "PARTIAL_BUT_SUFFICIENT"
    assert result.unavailable_optional == ["sma200", "news"]
    assert evidence_sufficiency(contract, {"revenue"}).status == "INSUFFICIENT"
    assert evidence_sufficiency(OutputRequirements(any_of=[[]]), set()).status == "INSUFFICIENT"


@pytest.mark.asyncio
@pytest.mark.parametrize("global_failure", [False, True])
async def test_incident_output_dependency_and_global_control(global_failure):
    tasks = [
        task("fund", "fundamental_analysis"),
        task("valuation", "valuation_analysis", ["fund"]),
        task("risk", "risk_analysis", ["fund"]),
        task("narrative_consumer", "custom", ["fund"]),
        task("synthesis", "report_synthesis", ["valuation", "risk", "narrative_consumer"]),
    ]
    tasks[3].output_requirements = OutputRequirements(hard_required=["fund/agent_output"])
    state = RuntimeState.create(
        run_id="RUN-1",
        planned_graph=PlannedTaskGraph(graph_id="PLAN-1", run_id="RUN-1", tasks=tasks),
    )
    configure_output_contracts(state)
    calls = []

    class Executor:
        async def execute(self, t, context):
            calls.append(t.task_id)
            if t.task_id == "fund":
                for capability in (
                    "revenue_growth",
                    "ebitda_margin",
                    "free_cash_flow_margin",
                    "technical_sma_50",
                    "technical_rsi_14",
                    "technical_macd_12_26_9",
                    "technical_volume_ratio_20",
                ):
                    publish_output(
                        state.task("fund"),
                        capability,
                        OutputStatus.COMPLETED,
                        refs=["CALC-" + capability],
                    )
                publish_output(
                    state.task("fund"),
                    "technical_sma_200",
                    OutputStatus.INSUFFICIENT_DATA,
                    reason="131_OF_200",
                )
                publish_output(
                    state.task("fund"),
                    "agent_output",
                    OutputStatus.FAILED,
                    reason="MODEL_IDENTITY_MISMATCH",
                )
                if global_failure:
                    raise ValueError("integrity rejected")
                raise LocalOutputFailure("recorded failure")
            return TaskExecutionResult(result_ref="result://" + t.task_id)

    checkpoints = InMemoryCheckpointStore()
    scheduler = DependencyScheduler(
        event_store=InMemoryRuntimeEventStore(), checkpoint_store=checkpoints
    )
    if global_failure:
        with pytest.raises(ExceptionGroup):
            await scheduler.execute(state=state, executor=Executor())
        assert calls == ["fund"]
        assert state.run_status is RunStatus.FAILED
    else:
        await scheduler.execute(state=state, executor=Executor())
        assert set(calls) == {"fund", "valuation", "risk", "synthesis"}
        assert state.task("narrative_consumer").status is TaskStatus.BLOCKED
        assert state.task("narrative_consumer").missing_output_dependencies == ["fund/agent_output"]
        assert state.task("fund").status is TaskStatus.FAILED
        assert state.run_status is RunStatus.REVIEW  # Not RELEASED.
        saved = await checkpoints.load_latest("RUN-1")
        restored = saved.restore(planned_graph=state.planned_graph)
        assert restored.task("fund").output_outcomes == state.task("fund").output_outcomes


@pytest.mark.asyncio
async def test_missing_required_calculation_blocks_valuation():
    from src.runtime.output_dependencies import resolve_outputs

    state = RuntimeState.create(
        run_id="RUN-1",
        planned_graph=PlannedTaskGraph(
            graph_id="PLAN",
            run_id="RUN-1",
            tasks=[
                task("fund", "fundamental_analysis"),
                task("val", "valuation_analysis", ["fund"]),
            ],
        ),
    )
    configure_output_contracts(state)
    state.task("fund").status = TaskStatus.FAILED
    publish_output(state.task("fund"), "revenue_growth", OutputStatus.COMPLETED, refs=["CALC"])
    assert resolve_outputs(state, state.task("val")) == ("BLOCKED", ["fund/ebitda_margin"])


@pytest.mark.asyncio
@pytest.mark.parametrize("synthesis_fails", [False, True])
async def test_integrated_partial_synthesis_persists_but_release_stays_strict(
    monkeypatch, synthesis_fails
):
    from datetime import UTC, datetime

    from src.application.execution import IntegratedTaskExecutor
    from src.application.service import ResearchApplicationService

    async def narrative(self, t, **kwargs):
        if synthesis_fails and t.task_type == "report_synthesis":
            publish_output(
                self._aggregate.runtime.task(t.task_id),
                "agent_output",
                OutputStatus.FAILED,
                reason="read_timeout",
            )
            raise LocalOutputFailure("typed synthesis failure")
        if t.task_type == "fundamental_analysis":
            assert len(self._aggregate.artifacts.calculations) == 2
            publish_output(
                self._aggregate.runtime.task(t.task_id),
                "agent_output",
                OutputStatus.FAILED,
                reason="MODEL_IDENTITY_MISMATCH",
            )
            raise LocalOutputFailure("typed test narrative failure")
        return None

    monkeypatch.setattr(IntegratedTaskExecutor, "_invoke_research_agent", narrative)
    service = ResearchApplicationService()
    proof_calls = 0
    original_proof = service._execute_proof_workflow

    async def once(aggregate):
        nonlocal proof_calls
        proof_calls += 1
        assert proof_calls == 1, "A partial execution must not regenerate the same Proof"
        return await original_proof(aggregate)

    monkeypatch.setattr(service, "_execute_proof_workflow", once)
    obj = await service.create_object(symbol="NVDA", company_name="NVIDIA", exchange="NASDAQ")
    draft = await service.prepare_run(
        research_object_id=obj.object_id,
        research_goal="financial",
        as_of=datetime(2026, 9, 8, tzinfo=UTC),
        preferences={},
    )
    aggregate = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    await service.execute_run(aggregate.run.run_id)
    assert proof_calls == 1
    assert aggregate.run.status is (RunStatus.FAILED if synthesis_fails else RunStatus.RELEASED)
    if synthesis_fails:
        assert aggregate.artifacts.released_result is None
        assert aggregate.artifacts.closure_diagnostic["code"] in {
            "INCOMPLETE_RESEARCH_NOT_RELEASED",
            "REQUIRED_RESEARCH_OUTPUT_MISSING",
            "REVIEW_BLOCKED",
        }
    else:
        assert aggregate.artifacts.released_result is not None
        assert aggregate.artifacts.review.status.value == "PASS"
    assert aggregate.artifacts.partial_research["status"] == (
        "PARTIAL_NOT_RELEASED" if synthesis_fails else "PARTIAL_RELEASED"
    )
    assert len(aggregate.artifacts.partial_research["available_calculations"]) == 2
    assert aggregate.artifacts.proofs  # real existing policy, no invented verification
    for kind in ("valuation_analysis", "risk_analysis", "report_synthesis"):
        t = next(t for t in aggregate.runtime.actual_graph.tasks if t.task_type == kind)
        assert t.status is (
            TaskStatus.FAILED
            if synthesis_fails and kind == "report_synthesis"
            else TaskStatus.COMPLETED
        )
    saved = await service.repository.get_run(aggregate.run.run_id)
    assert saved.artifacts.partial_research == aggregate.artifacts.partial_research


def test_unknown_valuation_profile_is_not_relaxed():
    custom = task("val", "valuation_analysis", ["fund"])
    custom.skill_id = "custom_dcf_v2"
    state = RuntimeState.create(
        run_id="RUN-1",
        planned_graph=PlannedTaskGraph(
            graph_id="PLAN", run_id="RUN-1", tasks=[task("fund", "fundamental_analysis"), custom]
        ),
    )
    configure_output_contracts(state)
    assert state.task("val").output_requirements is None


def test_scoped_context_excludes_nonancestor_calculations():
    from types import SimpleNamespace

    from src.application.models import CompletedRunArtifacts
    from src.application.research_outputs import availability_map
    from src.domain.calculation import CalculationRecord
    from src.domain.enums import CalculationStatus

    state = RuntimeState.create(
        run_id="RUN-1",
        planned_graph=PlannedTaskGraph(
            graph_id="PLAN",
            run_id="RUN-1",
            tasks=[
                task("fund", "fundamental_analysis"),
                task("risk", "risk_analysis", ["fund"]),
                task("other", "custom"),
            ],
        ),
    )
    artifacts = CompletedRunArtifacts()
    for producer in ("fund", "other"):
        artifacts.calculations.append(
            CalculationRecord(
                calculation_id="CALC-" + producer,
                run_id="RUN-1",
                task_id=producer,
                capability_id="revenue_growth",
                capability_version="1",
                formula_id="growth",
                input_evidence_ids=["E-" + producer],
                output_value="0.5",
                output_unit="ratio",
                status=CalculationStatus.PASS,
            )
        )
    scoped = availability_map(
        SimpleNamespace(runtime=state, artifacts=artifacts), state.task("risk")
    )
    assert [c["calculation_id"] for c in scoped["available_calculations"]] == ["CALC-fund"]


def test_source_any_of_uses_retained_refs_and_blocks_only_consumer():
    from src.runtime.output_dependencies import resolve_outputs

    source = task("source", "evidence_collection")
    guidance = task("guidance", "custom", ["source"])
    guidance.output_requirements = OutputRequirements(
        any_of=[["source/source.transcript", "source/source.filing"]]
    )
    state = RuntimeState.create(
        run_id="RUN-1",
        planned_graph=PlannedTaskGraph(graph_id="PLAN", run_id="RUN-1", tasks=[source, guidance]),
    )
    state.task("source").status = TaskStatus.COMPLETED
    publish_output(state.task("source"), "source.transcript", OutputStatus.UNAVAILABLE_ENTITLEMENT)
    assert resolve_outputs(state, state.task("guidance"))[0] == "BLOCKED"
    publish_output(state.task("source"), "source.filing", OutputStatus.COMPLETED, refs=["E-FILING"])
    assert resolve_outputs(state, state.task("guidance")) == ("READY", [])
