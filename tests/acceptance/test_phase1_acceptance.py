from datetime import date

import pytest

from src.application.service import ResearchApplicationService
from src.domain.enums import ProofStatus, RunStatus


@pytest.mark.asyncio
async def test_phase1_minimum_acceptance_chain() -> None:
    service = ResearchApplicationService()
    research_object = await service.create_object(
        symbol="NVDA", company_name="NVIDIA Corporation", exchange="NASDAQ"
    )
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Assess fundamentals, valuation limitations, and risks",
        as_of=date(2026, 9, 3),
        preferences={"depth": "standard"},
    )
    assert draft.scheme_snapshot.generated_by == "deterministic-scheme-generator-v1"
    assert draft.scheme_snapshot.confirmed_at is None

    aggregate = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    assert aggregate.scheme.confirmed_at is not None
    assert aggregate.runtime.planned_graph.tasks
    await service.execute_run(aggregate.run.run_id)

    assert aggregate.run.status is RunStatus.RELEASED
    assert aggregate.artifacts.parallel_task_peak >= 2
    assert len(aggregate.artifacts.calculations) == 2
    assert aggregate.artifacts.corrections
    assert aggregate.artifacts.replans
    assert aggregate.artifacts.review and aggregate.artifacts.review.status.value == "PASS"
    assert aggregate.artifacts.proofs[0].status is ProofStatus.NOT_IMPLEMENTED
    assert aggregate.artifacts.canonical_record
    assert aggregate.artifacts.released_result
    assert aggregate.artifacts.report
    assert aggregate.artifacts.writeback
