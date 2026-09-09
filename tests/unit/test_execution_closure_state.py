"""Offline A–H closure matrix; no provider, calculation or Proof execution."""

from types import SimpleNamespace as NS

import pytest

from src.application.closure_policy import classify_execution_closure, closure_diagnostic
from src.application.errors import ApplicationError
from src.application.models import CompletedRunArtifacts
from src.domain.enums import TaskStatus
from src.domain.model_execution import TASK_CANDIDATES
from src.domain.output_dependency import OutputOutcome, OutputRequirements, OutputStatus
from src.domain.task import PlannedTaskGraph, Task
from src.runtime.state import RuntimeState


def task(key, status=TaskStatus.COMPLETED, deps=(), contract=None, outcome=None):
    return Task(
        task_id=key,
        run_id="R",
        task_type="custom",
        goal="bounded",
        assigned_agent="research_lead",
        skill_id="custom_v1",
        status=status,
        dependencies=list(deps),
        output_requirements=contract,
        output_outcomes=[]
        if outcome is None
        else [
            OutputOutcome(
                output_id="agent_output",
                status=outcome,
                refs=["retained-output"] if outcome is OutputStatus.COMPLETED else [],
                reason_code=None if outcome is OutputStatus.COMPLETED else "read_timeout",
            )
        ],
    )


def aggregate(tasks):
    state = RuntimeState.create(
        run_id="R", planned_graph=PlannedTaskGraph(graph_id="G", run_id="R", tasks=tasks)
    )
    return NS(
        runtime=state,
        scheme=NS(calculation_requirements=[]),
        run=NS(run_id="R"),
        artifacts=CompletedRunArtifacts(),
    )


@pytest.mark.parametrize("kind", ["hard_required", "supporting", "enrichment"])
def test_a_b_c_required_supporting_enrichment(kind):
    a = aggregate(
        [
            task("producer", TaskStatus.FAILED, outcome=OutputStatus.FAILED),
            task(
                "consumer",
                deps=["producer"],
                contract=OutputRequirements(**{kind: ["producer/agent_output"]}),
            ),
        ]
    )
    result = classify_execution_closure(a)
    assert result.reviewable is (kind != "hard_required")
    assert bool(result.limitations) is (kind != "hard_required")
    if kind == "hard_required":
        assert result.fatal_reason == "REQUIRED_RESEARCH_OUTPUT_MISSING"


@pytest.mark.parametrize("alternative", [False, True])
def test_d_e_f_g_dynamic_and_fundamental_exact_any_of(alternative):
    # Names confer no authority: only the actual completed alternative discharges ANY_OF.
    a = aggregate(
        [
            task("followup", TaskStatus.FAILED, outcome=OutputStatus.FAILED),
            task(
                "main",
                TaskStatus.COMPLETED if alternative else TaskStatus.FAILED,
                outcome=OutputStatus.COMPLETED if alternative else OutputStatus.FAILED,
            ),
            task(
                "synthesis",
                deps=["followup", "main"],
                contract=OutputRequirements(
                    any_of=[["followup/agent_output", "main/agent_output"]]
                ),
            ),
        ]
    )
    result = classify_execution_closure(a)
    assert result.reviewable is alternative
    if alternative:
        assert "followup" in result.supporting_outputs.failed
        assert "main" in result.supporting_outputs.satisfied


def test_approved_child_with_no_optional_contract_remains_required():
    a = aggregate(
        [task("risk"), task("child", TaskStatus.FAILED), task("synthesis", TaskStatus.WAITING)]
    )
    result = classify_execution_closure(a)
    assert not result.reviewable
    assert set(result.required_outputs.missing) == {"child", "synthesis"}


@pytest.mark.parametrize("kind", ["supporting", "enrichment", "any_of"])
def test_unrelated_contract_cannot_discharge_required_task(kind):
    refs = ["producer/agent_output"]
    contract = OutputRequirements(**{kind: [refs] if kind == "any_of" else refs})
    a = aggregate(
        [
            task("producer", TaskStatus.FAILED, outcome=OutputStatus.FAILED),
            task("unrelated", contract=contract),
        ]
    )
    assert not classify_execution_closure(a).reviewable


def test_h_real_implementation_exception_preserves_stage():
    a = aggregate([])
    assert (
        closure_diagnostic(a, ValueError("private"), "POST_SCHEDULER")["code"]
        == "UNEXPECTED_CLOSURE_FAILURE"
    )
    scheduler = closure_diagnostic(a, ValueError("private"), "TASK_EXECUTION")
    assert scheduler["code"] == "UNEXPECTED_EXECUTION_FAILURE"
    assert scheduler["seam"] == "src/runtime/scheduler.py:execute"
    assert "private" not in str(scheduler)
    assert (
        closure_diagnostic(
            a, ApplicationError("REQUIRED_RESEARCH_OUTPUT_MISSING", "missing"), "POST_SCHEDULER"
        )["code"]
        == "REQUIRED_RESEARCH_OUTPUT_MISSING"
    )


def test_registered_child_has_explicit_governed_authority(monkeypatch):
    from src.agentic.composition import build_research_agent_registry

    assert TASK_CANDIDATES["risk_follow_up"] == TASK_CANDIDATES["risk_analysis"]
    monkeypatch.delitem(TASK_CANDIDATES, "risk_follow_up")
    with pytest.raises(ValueError, match="governed model authority"):
        build_research_agent_registry(None, None, recovery=object())


@pytest.mark.asyncio
async def test_required_failure_stops_before_review_proof_or_report():
    from src.application.service import ResearchApplicationService

    a = aggregate([task("required", TaskStatus.FAILED)])
    with pytest.raises(ApplicationError, match="Required research") as exc:
        await ResearchApplicationService()._assure_and_release(a)
    assert exc.value.code == "REQUIRED_RESEARCH_OUTPUT_MISSING"
    assert a.artifacts.review is None and not a.artifacts.proofs
    assert a.artifacts.report is None
