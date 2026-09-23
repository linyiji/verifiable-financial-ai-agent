from copy import deepcopy

import pytest

from src.adapters.finrobot.professional_reporting import (
    CanonicalReportMapper,
    ControlledArtifactStore,
    ProfessionalReportPublisher,
)
from src.application.execution import IntegratedTaskExecutor
from src.application.execution_profiles import frozen_report_metrics
from src.application.persistence import SQLAlchemyApplicationRepository
from src.domain.node_binding import BindingDenied
from src.runtime.scheduler import DependencyScheduler
from tests.report_metrics.runtime_fixture import report_fixture

GROWTH = "revenue_growth_v1"
MARGIN = "ebitda_margin_v1"


@pytest.mark.parametrize(
    "selection,risk,condition",
    [
        (GROWTH, False, None),
        (GROWTH, True, None),
        (MARGIN, False, None),
        (GROWTH, False, False),
        (GROWTH, False, True),
    ],
)
async def test_rmr09_16_17_19_20_runtime(tmp_path, selection, risk, condition, monkeypatch):
    request = dict(
        schema_version="frozen-report-metric-requirements/v1",
        report_mode="METRIC_FOCUSED",
        required_metric_ids=[selection],
        period="FY2026",
    )
    if condition is not None:
        request.update(
            conditional_requirements=[
                dict(
                    condition_ref="section:ebitda_margin",
                    metric_id=MARGIN,
                    requirement_ref="request",
                )
            ],
            enabled_condition_refs=["section:ebitda_margin"] if condition else [],
        )
    preferences = {"report_metric_requirements": request}
    if risk:
        preferences["risk_semantic_profile"] = "risk_semantic_outcome_minimal_v1"
    service, aggregate, _, _, _ = await report_fixture(tmp_path, preferences=preferences)
    contract = frozen_report_metrics(aggregate)
    snapshot = deepcopy(aggregate.node_binding.execution_snapshot)
    assert aggregate.node_binding.execution_snapshot["scenario"]["report_metric_requirements"]
    assert not service.calculation_extensions
    owner = await service.repository.claim_execution(aggregate.run.run_id)
    aggregate = await service.repository.validate_execution(owner)
    executor = IntegratedTaskExecutor(service, aggregate)
    if selection == GROWTH and condition is None and not risk:
        old_extensions = service.calculation_extensions
        service.calculation_extensions = (object(),)
        fundamental = next(
            t for t in aggregate.runtime.actual_graph.tasks if t.task_type == "fundamental_analysis"
        )
        with pytest.raises(BindingDenied, match="UNSUPPORTED_NEW_BOUND_HANDLER"):
            executor.admission_requirements(fundamental)
        service.calculation_extensions = old_extensions
    scheduler = DependencyScheduler(
        event_store=service.event_store,
        checkpoint_store=service.checkpoint_store,
        admission_repository=service.repository,
        execution_owner=owner,
    )
    await scheduler.execute(
        state=aggregate.runtime,
        executor=executor,
        emit_run_started=True,
        on_execution_admitted=lambda: [
            executor.admission_requirements(t) for t in aggregate.runtime.actual_graph.tasks
        ],
    )
    aggregate = await service.repository.validate_execution(owner)
    if selection == GROWTH and condition is None and not risk:
        missing = deepcopy(aggregate)
        missing.artifacts.calculations = []
        with pytest.raises(BindingDenied, match="REPORT_SOURCE_MAP_INCOMPLETE"):
            await service._assure_and_release(missing)
        malformed = deepcopy(aggregate)
        malformed.artifacts.calculations[0].output_value = "invalid-scalar"
        with pytest.raises(Exception) as failure:
            await service._assure_and_release(malformed)
        assert failure.value.code == "CONTRACT_REJECTED"
    # Confirm resolution is authoritative even if a runtime preference is changed.
    old_preferences = deepcopy(aggregate.goal.preferences)
    aggregate.goal.preferences["report_metric_requirements"]["enabled_condition_refs"] = ["unknown"]
    assert frozen_report_metrics(aggregate) == contract
    from src.application.repository import confirmed_risk_authority

    with pytest.raises(BindingDenied):
        confirmed_risk_authority(aggregate)
    aggregate.goal.preferences = old_preferences
    assert aggregate.node_binding.execution_snapshot == snapshot
    if selection == GROWTH and condition is None and not risk:
        from src.application import service as service_module
        from src.output import financial_metrics

        reordered = tuple(reversed(financial_metrics.MATERIAL_FORMULAS))
        monkeypatch.setattr(service_module, "MATERIAL_FORMULAS", reordered)
        monkeypatch.setattr(financial_metrics, "MATERIAL_FORMULAS", reordered)
    service.report_publisher = ProfessionalReportPublisher(
        ControlledArtifactStore(tmp_path / "html")
    )
    await service._assure_and_release(aggregate)
    result = aggregate.artifacts.released_result
    assert {m.formula_id for m in result.released_metrics} == set(
        contract.resolved_required_metric_ids
    )
    artifact = aggregate.artifacts.report_artifacts[0]
    html = service.report_publisher.read_verified(artifact).decode()
    assert "financial_summary" not in html
    if selection == MARGIN:
        assert "Revenue Growth" not in html
    elif not condition:
        assert "EBITDA Margin" not in html
    assert len(artifact.source_contributions) == len(result.released_metrics)
    assert aggregate.artifacts.review.status.value == "PASS"
    assert aggregate.node_binding.execution_snapshot == snapshot
    # Every opted-in publisher call must independently validate current source identity.
    bad = result.model_copy(
        update={
            "released_metrics": (
                result.released_metrics[0].model_copy(update={"period": "FY1900"}),
            )
        }
    )
    with pytest.raises(BindingDenied):
        await service._revenue_growth_source_contribution(
            aggregate=aggregate,
            result=bad,
            review_id=aggregate.artifacts.review.review_id,
            review_status="PASS",
            proof_records=(),
            selected_formula=selection,
        )
    if selection == GROWTH and condition is None and not risk:
        from src.domain.enums import FinancialUnit

        variants = [
            (),
            (*result.released_metrics, result.released_metrics[0]),
            (
                result.released_metrics[0].model_copy(
                    update={"canonical_unit": FinancialUnit.INDEX}
                ),
            ),
            (result.released_metrics[0].model_copy(update={"evidence_ids": ("foreign",)}),),
        ]
        for metrics in variants:
            with pytest.raises(BindingDenied):
                await service._revenue_growth_source_contribution(
                    aggregate=aggregate,
                    result=result.model_copy(update={"released_metrics": metrics}),
                    review_id=aggregate.artifacts.review.review_id,
                    review_status="PASS",
                    proof_records=(),
                    selected_formula=selection,
                )
        evidence_object = aggregate.artifacts.evidence[0].object_id
        for e in aggregate.artifacts.evidence:
            e.object_id = "OBJ-FOREIGN"
        with pytest.raises(BindingDenied):
            await service._revenue_growth_source_contribution(
                aggregate=aggregate,
                result=result,
                review_id=aggregate.artifacts.review.review_id,
                review_status="PASS",
                proof_records=(),
                selected_formula=selection,
            )
        for e in aggregate.artifacts.evidence:
            e.object_id = evidence_object
        prior_current = dict(aggregate.node_binding.current_results)
        aggregate.node_binding.current_results.clear()
        with pytest.raises(BindingDenied):
            await service._revenue_growth_source_contribution(
                aggregate=aggregate,
                result=result,
                review_id=aggregate.artifacts.review.review_id,
                review_status="PASS",
                proof_records=(),
                selected_formula=selection,
            )
        aggregate.node_binding.current_results.update(prior_current)
    # Typed mapping cannot accept a source for another formula.
    with pytest.raises(ValueError):
        CanonicalReportMapper.map(
            result,
            aggregate.artifacts.canonical_record,
            source_contributions=[
                artifact.source_contributions[0].model_copy(update={"formula_id": "foreign"})
            ],
        )
    # Durable authority rejects marker downgrade / root removal, including fresh decoding.
    payload = SQLAlchemyApplicationRepository._payload(aggregate)
    for mutation in ("root", "marker", "payload", "digest", "cross-run"):
        changed = deepcopy(payload)
        if mutation == "root":
            changed["node_binding"] = None
        elif mutation == "marker":
            changed["scheme"]["report_requirements"] = []
        elif mutation == "payload":
            changed["node_binding"]["execution_snapshot"]["scenario"].pop(
                "report_metric_requirements"
            )
        elif mutation == "digest":
            changed["scheme"]["assurance_requirements"]["report_metric_requirements"][
                "contract_digest"
            ] = "bad"
        else:
            changed["run"]["research_object_id"] = "OBJ-FOREIGN"
        with pytest.raises((BindingDenied, ValueError)):
            SQLAlchemyApplicationRepository._to_aggregate(changed, 2)


async def test_legacy_path_keeps_old_missing_material_failure(tmp_path):
    service, aggregate, _, _, _ = await report_fixture(tmp_path, preferences={})
    assert frozen_report_metrics(aggregate) is None
    assert "report_metric_requirements" not in aggregate.node_binding.execution_snapshot["scenario"]
    owner = await service.repository.claim_execution(aggregate.run.run_id)
    aggregate = await service.repository.validate_execution(owner)
    executor = IntegratedTaskExecutor(service, aggregate)
    scheduler = DependencyScheduler(
        event_store=service.event_store,
        checkpoint_store=service.checkpoint_store,
        admission_repository=service.repository,
        execution_owner=owner,
    )
    await scheduler.execute(
        state=aggregate.runtime,
        executor=executor,
        emit_run_started=True,
        on_execution_admitted=lambda: [
            executor.admission_requirements(t) for t in aggregate.runtime.actual_graph.tasks
        ],
    )
    aggregate = await service.repository.validate_execution(owner)
    service.report_publisher = ProfessionalReportPublisher(
        ControlledArtifactStore(tmp_path / "html")
    )
    with pytest.raises(Exception) as failure:
        await service._assure_and_release(aggregate)
    assert failure.value.code == "REPORT_SOURCE_MAP_INCOMPLETE"
