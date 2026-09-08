from datetime import date

import pytest

from src.application.phase3_financial import Phase3FinancialCapabilityExtension
from src.assurance import IndependentFinancialReviewer
from src.assurance.requirements import requirement_context
from src.capabilities.financial.growth import RevenueGrowthCapability
from src.capabilities.financial.profitability import EbitdaMarginCapability
from src.domain.capability import CapabilityContext
from src.domain.enums import ProofRequirement
from src.domain.financial_branch import BRANCH_FORMULAS, BranchRequirement, BranchStatus
from src.domain.output_dependency import LocalOutputFailure
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.output.financial_metrics import build_material_financial_release
from src.runtime.events import InMemoryRuntimeEventStore
from tests.unit.test_phase3_financial_extension import (
    FakeGeneratedOrchestrator,
    GeneratedFCFMarginCapability,
    _evidence,
    _orchestration_result,
    _state,
    _task,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("required_sma", [False, True])
async def test_partial_real_financial_pipeline_requirement_and_judgment_parity(required_sma):
    task = _task()
    state = _state(task)
    evidence = [
        e
        for e in _evidence()
        if not e.evidence_id.startswith(("E-CLOSE-", "E-VOLUME-"))
        or int(e.evidence_id.rsplit("-", 1)[1]) >= 180
    ]
    events = InMemoryRuntimeEventStore()
    extension = Phase3FinancialCapabilityExtension(
        event_store=events,
        generated=FakeGeneratedOrchestrator(_orchestration_result(GeneratedFCFMarginCapability())),
    )
    context = CapabilityContext(
        run_id="RUN-1",
        task_id=task.task_id,
        accepted_evidence_ids=[e.evidence_id for e in evidence],
    )
    result = await extension.execute_incremental(
        task=state.task(task.task_id),
        state=state,
        evidence=evidence,
        context=context,
        requirements={"technical_sma_200": BranchRequirement.REQUIRED} if required_sma else {},
    )
    by_id = {e.evidence_id: e for e in evidence}
    growth = await RevenueGrowthCapability().execute(
        {
            "prior": by_id["E-REV-PRIOR"],
            "current": by_id["E-REV"],
            "calculation_id": "CALC-RUN-1-GROWTH",
        },
        context,
    )
    margin = await EbitdaMarginCapability().execute(
        {
            "ebitda": by_id["E-EBITDA"],
            "revenue": by_id["E-REV"],
            "calculation_id": "CALC-RUN-1-EBITDA",
        },
        context,
    )
    calculations = [growth, margin, *result.calculations]
    unavailable = frozenset(
        f
        for b in result.branch_results
        if b.status is not BranchStatus.COMPLETED
        for f in BRANCH_FORMULAS[b.calculation_type]
    )
    metrics, claims, _ = build_material_financial_release(
        run_id="RUN-1",
        evidence=evidence,
        calculations=calculations,
        judgments=result.judgments,
        unavailable_formulas=unavailable,
    )
    scheme = ResearchSchemeSnapshot(
        scheme_id="SCHEME-1",
        research_object_id="OBJ-1",
        goal_id="GOAL-1",
        generated_by="deterministic",
        calculation_requirements=["technical_sma_200"]
        if required_sma
        else ["calculation_records_for_reported_values"],
    )
    review = IndependentFinancialReviewer().review(
        review_id="REVIEW-RUN-1",
        run_id="RUN-1",
        run_as_of=date(2026, 9, 4),
        evidence=evidence,
        calculations=calculations,
        metrics=metrics,
        claims=claims,
        judgments=result.judgments,
        branch_results=result.branch_results,
        requirement_context=requirement_context(scheme, result.branch_results),
        proof_requirements={
            c.calculation_id: ProofRequirement.MUST_PROVE
            if c is growth
            else ProofRequirement.NOT_REQUIRED
            for c in calculations
        },
    )
    assert review.status.value == ("BLOCK" if required_sma else "PASS")
    assert {j["judgment_type"] for j in result.judgments} == {"rsi_state"}
    assert next(c for c in review.checks if c.code == "FIN_JUDGMENT_SUPPORT").status.value == "PASS"
    assert not any(c.capability_id == "technical_sma_200" for c in calculations)
    assert len(calculations) == len(metrics) == len(claims) == 5


@pytest.mark.asyncio
async def test_period_mismatch_remains_failed_correction_not_insufficient_history():
    task, events = _task(), InMemoryRuntimeEventStore()
    state = _state(task)
    evidence = _evidence()
    for e in evidence:
        if e.normalized_field == "operating_cash_flow":
            e.period = "FY2030"
    extension = Phase3FinancialCapabilityExtension(
        event_store=events,
        generated=FakeGeneratedOrchestrator(_orchestration_result(GeneratedFCFMarginCapability())),
    )
    outcomes = []

    async def publish(outcome):
        outcomes.append(outcome)

    with pytest.raises(LocalOutputFailure):
        await extension.execute_incremental(
            task=state.task(task.task_id),
            state=state,
            evidence=evidence,
            context=CapabilityContext(
                run_id="RUN-1",
                task_id=task.task_id,
                accepted_evidence_ids=[e.evidence_id for e in evidence],
            ),
            publish=publish,
        )
    fcf = next(b for b in outcomes if b.calculation_type == "free_cash_flow_margin")
    assert fcf.status is BranchStatus.FAILED
    assert fcf.reason_code == "PERIOD_MISMATCH_CORRECTION_REQUIRED"
    assert not fcf.calculation_ids
    assert sum(b.status is BranchStatus.COMPLETED for b in outcomes) == 5
    assert not any(e.type.value == "task.correction_resolved" for e in await events.replay("RUN-1"))
