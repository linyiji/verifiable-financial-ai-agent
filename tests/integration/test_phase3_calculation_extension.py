from datetime import date
from decimal import Decimal

import pytest

from src.application.extensions import TaskCalculationExtensionResult
from src.application.service import ResearchApplicationService
from src.domain.calculation import CalculationRecord
from src.domain.enums import CalculationStatus, RunStatus


class AcceptedEvidenceCalculationExtension:
    async def execute(self, *, task, state, evidence, context):
        assert state.task(task.task_id).status.value == "RUNNING"
        assert evidence
        return TaskCalculationExtensionResult(
            calculations=[
                CalculationRecord(
                    calculation_id=f"CALC-{task.run_id}-EXTENSION",
                    run_id=task.run_id,
                    task_id=task.task_id,
                    capability_id="generated_test_margin",
                    capability_version="1.0.0-generated",
                    formula_id="generated_test_margin_v1",
                    input_evidence_ids=[evidence[0].evidence_id],
                    input_values_snapshot={"value": "0.25"},
                    output_value=Decimal("0.25"),
                    output_unit="ratio",
                    status=CalculationStatus.PASS,
                    implementation_hash="sha256:generated",
                    source_ref="generated://BUILD-TEST/source.py",
                    runtime_version="Python 3.11.test",
                )
            ],
            generated_capability_refs=["GEN-TEST"],
            judgments=[
                {
                    "judgment_ref": "JUDGMENT-TECHNICAL-TEST",
                    "version": 1,
                    "requires_review": True,
                }
            ],
            task_output={"generated_test_margin": "0.25"},
        )


@pytest.mark.asyncio
async def test_calculation_extension_closes_canonical_and_release_lineage() -> None:
    service = ResearchApplicationService(
        calculation_extensions=[AcceptedEvidenceCalculationExtension()]
    )
    research_object = await service.create_object(
        symbol="NVDA",
        company_name="NVIDIA",
        exchange="NASDAQ",
    )
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Exercise Phase 3 extension integration",
        as_of=date(2026, 9, 4),
        preferences={},
    )
    aggregate = await service.confirm_run(
        draft_id=draft.draft_id,
        confirm_scheme=True,
    )

    aggregate = await service.execute_run(aggregate.run.run_id)

    assert aggregate.run.status is RunStatus.RELEASED
    assert aggregate.artifacts.canonical_record is not None
    assert aggregate.artifacts.released_result is not None
    assert "GEN-TEST" in aggregate.artifacts.canonical_record.generated_capability_refs
    assert f"CALC-{aggregate.run.run_id}-EXTENSION" in (
        aggregate.artifacts.canonical_record.calculation_refs
    )
    assert any(
        item.get("judgment_ref") == "JUDGMENT-TECHNICAL-TEST"
        for item in aggregate.artifacts.released_result.judgments
    )
