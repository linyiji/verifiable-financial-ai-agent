"""Direct coverage for the top-level Phase 4 projection builders."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from src.domain.calculation import CalculationRecord
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.enums import (
    CalculationStatus,
    CorporateActionStatus,
    EvidenceStatus,
    FinancialActuality,
    FinancialPeriodBasis,
    FinancialUnit,
    MaterialCalculationDispositionStatus,
    ProofRequirement,
    ReviewStatus,
    RunStatus,
    TaskStatus,
    TechnicalPriceBasis,
)
from src.domain.evidence import EvidenceRecord
from src.domain.financial_semantics import (
    MaterialCalculationDisposition,
    MaterialFinancialClaim,
    ReleasedFinancialMetric,
    TechnicalMethodMetadata,
)
from src.domain.macd_policy import MACD_DECIMAL_CONTEXT_POLICY
from src.domain.proof import ProofPolicyDecision
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph, Task
from src.output.financial_metrics import MATERIAL_FORMULAS
from src.phase4_product.contracts import (
    AvailabilityStatus,
    AvailabilityV1,
    ExecutionProjectionV1,
    ProofSummaryV1,
)
from src.phase4_product.projections import (
    ProjectionIntegrityError,
    build_atomic_run_projection,
    build_released_result_projection,
)

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)
AS_OF = date(2026, 9, 5)
SHA256_A = "sha256:" + "a" * 64


def _technical_method(formula_id: str) -> TechnicalMethodMetadata:
    if formula_id == "rsi_close_14_simple_average_v1":
        return TechnicalMethodMetadata(
            method="RSI_SIMPLE_AVERAGE_NOT_WILDER",
            parameters=(("period", "14"),),
            observation_count=200,
            warmup_required=15,
            warmup_satisfied=True,
            first_as_of=date(2026, 1, 1),
            last_as_of=AS_OF,
            is_wilder=False,
        )
    if formula_id.startswith("macd_"):
        policy = MACD_DECIMAL_CONTEXT_POLICY
        return TechnicalMethodMetadata(
            method="MACD_EMA_12_26_9_FIRST_OBSERVATION_SEED",
            parameters=(
                ("fast", str(policy.fast_span)),
                ("slow", str(policy.slow_span)),
                ("signal", str(policy.signal_span)),
            ),
            observation_count=200,
            warmup_required=policy.warmup_required,
            warmup_satisfied=True,
            first_as_of=date(2026, 1, 1),
            last_as_of=AS_OF,
            ema_adjust=policy.ema_adjust,
            ema_seed=policy.ema_seed,
            fast_span=policy.fast_span,
            slow_span=policy.slow_span,
            signal_span=policy.signal_span,
            decimal_context_policy_id=policy.policy_id,
            decimal_precision=policy.precision,
            decimal_rounding=policy.rounding,
            technical_price_basis=TechnicalPriceBasis.RAW_CLOSE,
        )
    window = 50 if formula_id == "sma_close_50_v1" else 200
    if formula_id == "latest_volume_to_average_volume_20_v1":
        window = 20
    return TechnicalMethodMetadata(
        method=(
            "VOLUME_RATIO"
            if formula_id == "latest_volume_to_average_volume_20_v1"
            else "SIMPLE_MOVING_AVERAGE"
        ),
        parameters=(("window", str(window)),),
        observation_count=max(window, 200),
        warmup_required=window,
        warmup_satisfied=True,
        first_as_of=date(2026, 1, 1),
        last_as_of=AS_OF,
    )


def _full_material_release() -> dict[str, object]:
    evidence: list[EvidenceRecord] = []
    calculations: list[CalculationRecord] = []
    metrics: list[ReleasedFinancialMetric] = []
    claims: list[MaterialFinancialClaim] = []
    dispositions: list[MaterialCalculationDisposition] = []
    policies: list[ProofPolicyDecision] = []

    currency_formulas = {
        "sma_close_50_v1",
        "sma_close_200_v1",
        "macd_line_close_12_26_adjust_false_v1",
        "macd_signal_close_12_26_9_adjust_false_v1",
        "macd_histogram_close_12_26_9_adjust_false_v1",
    }
    close_formulas = currency_formulas | {"rsi_close_14_simple_average_v1"}
    technical_formulas = set(MATERIAL_FORMULAS[3:])

    for index, formula_id in enumerate(MATERIAL_FORMULAS, start=1):
        evidence_id = f"EVIDENCE-{index:02d}"
        calculation_id = f"CALCULATION-{index:02d}"
        metric_id = f"METRIC-{index:02d}"
        claim_id = f"CLAIM-{index:02d}"
        capability_id = f"CAPABILITY-{index:02d}"
        value = str(index)
        unit = (
            FinancialUnit.CURRENCY
            if formula_id in currency_formulas
            else FinancialUnit.INDEX
            if formula_id == "rsi_close_14_simple_average_v1"
            else FinancialUnit.RATIO
        )
        is_technical = formula_id in technical_formulas
        uses_close = formula_id in close_formulas

        evidence.append(
            EvidenceRecord(
                evidence_id=evidence_id,
                run_id="RUN-A",
                object_id="OBJECT-A",
                provider="fixture",
                source_locator=f"fixture://material/{index:02d}",
                producer_task_id="TASK-A",
                retrieved_at=NOW - timedelta(minutes=30),
                period="DAILY" if is_technical else "CURRENT",
                period_basis=(
                    FinancialPeriodBasis.DAILY if is_technical else FinancialPeriodBasis.CURRENT
                ),
                actuality=FinancialActuality.ACTUAL,
                technical_price_basis=(TechnicalPriceBasis.RAW_CLOSE if uses_close else None),
                corporate_action_status=(
                    CorporateActionStatus.NONE_DETECTED if uses_close else None
                ),
                as_of=AS_OF,
                raw_artifact_ref=f"ARTIFACT-EVIDENCE-{index:02d}",
                normalized_field=(
                    "close"
                    if uses_close
                    else "volume"
                    if formula_id == "latest_volume_to_average_volume_20_v1"
                    else "value"
                ),
                normalized_value=value,
                unit=unit.value,
                currency="USD" if formula_id in currency_formulas else None,
                snapshot_hash=SHA256_A,
                status=EvidenceStatus.ACCEPTED,
                created_at=NOW - timedelta(minutes=30),
            )
        )
        calculations.append(
            CalculationRecord(
                calculation_id=calculation_id,
                run_id="RUN-A",
                task_id="TASK-A",
                capability_id=capability_id,
                capability_version="1.0.0",
                formula_id=formula_id,
                input_evidence_ids=[evidence_id],
                input_values_snapshot={},
                parameters={},
                output_value=value,
                output_unit=unit.value,
                status=CalculationStatus.PASS,
                review_status=ReviewStatus.PASS,
                implementation_hash=SHA256_A,
                created_at=NOW - timedelta(minutes=20),
            )
        )
        metric = ReleasedFinancialMetric(
            metric_id=metric_id,
            calculation_id=calculation_id,
            name=f"Material metric {index:02d}",
            canonical_value=value,
            canonical_unit=unit,
            display_value=value,
            display_unit="USD" if unit is FinancialUnit.CURRENCY else unit.value,
            period="DAILY" if is_technical else "CURRENT",
            period_basis=(
                FinancialPeriodBasis.DAILY if is_technical else FinancialPeriodBasis.CURRENT
            ),
            actuality=FinancialActuality.ACTUAL,
            as_of=AS_OF,
            currency="USD" if unit is FinancialUnit.CURRENCY else None,
            formula_id=formula_id,
            capability_id=capability_id,
            evidence_ids=(evidence_id,),
            method_metadata=_technical_method(formula_id) if is_technical else None,
            technical_price_basis=(TechnicalPriceBasis.RAW_CLOSE if uses_close else None),
            corporate_action_status=(CorporateActionStatus.NONE_DETECTED if uses_close else None),
            corporate_action_guard_refs=(evidence_id,) if uses_close else (),
        )
        metrics.append(metric)
        claims.append(
            MaterialFinancialClaim(
                claim_id=claim_id,
                run_id="RUN-A",
                claim_type="MATERIAL_FINANCIAL_METRIC",
                statement=f"Material metric {index:02d} equals {value}.",
                metric_id=metric_id,
                value=value,
                unit=unit,
                period=metric.period,
                period_basis=metric.period_basis,
                actuality=metric.actuality,
                as_of=AS_OF,
                currency=metric.currency,
                calculation_refs=(calculation_id,),
                evidence_refs=(evidence_id,),
            )
        )
        dispositions.append(
            MaterialCalculationDisposition(
                calculation_id=calculation_id,
                metric_id=metric_id,
                status=MaterialCalculationDispositionStatus.REPORTABLE,
            )
        )
        policies.append(
            ProofPolicyDecision(
                decision_id=f"PROOF-POLICY-DECISION-{index:02d}",
                run_id="RUN-A",
                calculation_id=calculation_id,
                formula_id=formula_id,
                requirement=ProofRequirement.NOT_REQUIRED,
                policy_id="PROOF-POLICY-A",
                reason="This deterministic fixture does not require an external proof.",
                created_at=NOW - timedelta(minutes=15),
            )
        )

    canonical_record = CanonicalExecutionRecord(
        record_id="CANONICAL-A",
        run_id="RUN-A",
        object_snapshot_ref="OBJECT-A",
        goal_ref="GOAL-A",
        scheme_ref="SCHEME-A",
        planned_graph={"graph_id": "PLAN-A"},
        actual_graph={"graph_id": "ACTUAL-A"},
        task_refs=["TASK-A"],
        evidence_refs=[item.evidence_id for item in evidence],
        calculation_refs=[item.calculation_id for item in calculations],
        metric_refs=[item.metric_id for item in metrics],
        claim_refs=[item.claim_id for item in claims],
        runtime_outcome="RELEASED",
        created_at=NOW - timedelta(minutes=5),
    )
    released_result = ReleasedResearchResult(
        result_id="RESULT-A",
        run_id="RUN-A",
        canonical_record_id=canonical_record.record_id,
        released_metrics=tuple(metrics),
        material_claims=tuple(claims),
        material_calculation_dispositions=tuple(dispositions),
        limitations=[],
        released_at=NOW,
    )
    run = ResearchRun(
        run_id="RUN-A",
        research_object_id="OBJECT-A",
        goal_id="GOAL-A",
        scheme_id="SCHEME-A",
        status=RunStatus.RELEASED,
        as_of=AS_OF,
        planned_graph_id="PLAN-A",
        actual_graph_id="ACTUAL-A",
        started_at=NOW - timedelta(hours=1),
        completed_at=NOW,
        created_at=NOW - timedelta(hours=2),
    )
    return {
        "run": run,
        "canonical_record": canonical_record,
        "released_result": released_result,
        "calculations": tuple(calculations),
        "evidence": tuple(evidence),
        "proof_policy_decisions": tuple(policies),
    }


def test_build_released_result_projection_accepts_exact_full_material_set() -> None:
    projection = build_released_result_projection(
        expected_object_id="OBJECT-A",
        expected_run_id="RUN-A",
        **_full_material_release(),
    )

    assert len(projection.metrics) == len(MATERIAL_FORMULAS) == 10
    assert tuple(metric.formula_id for metric in projection.metrics) == MATERIAL_FORMULAS
    assert len(projection.claims) == len(MATERIAL_FORMULAS)
    assert len(projection.material_calculation_dispositions) == len(MATERIAL_FORMULAS)
    assert all(metric.proof.status == "NOT_REQUIRED" for metric in projection.metrics)
    assert projection.availability == AvailabilityV1.available()


def test_build_released_result_projection_rejects_coherent_nine_of_ten_set() -> None:
    values = _full_material_release()
    released_result = values["released_result"]
    assert isinstance(released_result, ReleasedResearchResult)
    values["released_result"] = released_result.model_copy(
        update={
            "released_metrics": released_result.released_metrics[:-1],
            "material_claims": released_result.material_claims[:-1],
            "material_calculation_dispositions": (
                released_result.material_calculation_dispositions[:-1]
            ),
        }
    )

    with pytest.raises(ProjectionIntegrityError, match="exact FULL set"):
        build_released_result_projection(
            expected_object_id="OBJECT-A",
            expected_run_id="RUN-A",
            **values,
        )


def _atomic_kwargs() -> dict[str, Any]:
    task = Task(
        task_id="TASK-A",
        run_id="RUN-A",
        task_type="research",
        goal="Collect the deterministic inputs",
        assigned_agent="research-agent",
        skill_id="research-skill",
        status=TaskStatus.RUNNING,
        progress=0.25,
        attempt_count=1,
        created_at=NOW - timedelta(minutes=20),
    )
    run = ResearchRun(
        run_id="RUN-A",
        research_object_id="OBJECT-A",
        goal_id="GOAL-A",
        scheme_id="SCHEME-A",
        status=RunStatus.RUNNING,
        as_of=AS_OF,
        planned_graph_id="PLAN-A",
        actual_graph_id="ACTUAL-A",
        started_at=NOW - timedelta(minutes=15),
        created_at=NOW - timedelta(minutes=30),
    ).model_dump(mode="python")
    run["updated_at"] = NOW

    return {
        "expected_object_id": "OBJECT-A",
        "expected_run_id": "RUN-A",
        "projection_revision": 7,
        "projection_sequence": 0,
        "generated_at": NOW,
        "research_object": ResearchObject(
            object_id="OBJECT-A",
            symbol="ACME",
            company_name="Acme Corporation",
            exchange="NASDAQ",
            created_at=NOW - timedelta(days=1),
            updated_at=NOW,
        ),
        "run": run,
        "goal": ResearchGoal(
            goal_id="GOAL-A",
            research_object_id="OBJECT-A",
            goal_text="Produce a deterministic research snapshot",
            as_of=AS_OF,
            created_at=NOW - timedelta(minutes=30),
        ),
        "confirmed_scheme": ResearchSchemeSnapshot(
            scheme_id="SCHEME-A",
            research_object_id="OBJECT-A",
            goal_id="GOAL-A",
            research_scope=["financials"],
            generated_by="planner-v1",
            confirmed_at=NOW - timedelta(minutes=25),
            created_at=NOW - timedelta(minutes=26),
        ),
        "planned_graph": PlannedTaskGraph(
            graph_id="PLAN-A",
            run_id="RUN-A",
            tasks=[task.model_copy(deep=True)],
            created_at=NOW - timedelta(minutes=24),
        ),
        "actual_graph": ActualRuntimeGraph(
            graph_id="ACTUAL-A",
            run_id="RUN-A",
            tasks=[task.model_copy(deep=True)],
            created_at=NOW - timedelta(minutes=23),
        ),
        "proof_summary": ProofSummaryV1(
            availability=AvailabilityV1.unavailable(
                AvailabilityStatus.PENDING,
                "PROOF_POLICY_PENDING",
                retryable=True,
            ),
            policy="UNKNOWN",
            status=None,
        ),
        "review_availability": AvailabilityV1.unavailable(
            AvailabilityStatus.NOT_RELEASED,
            "REVIEW_NOT_RELEASED",
        ),
        "result_availability": AvailabilityV1.unavailable(
            AvailabilityStatus.NOT_RELEASED,
            "RESULT_NOT_RELEASED",
        ),
        "artifact_availability": AvailabilityV1.unavailable(
            AvailabilityStatus.NOT_RELEASED,
            "ARTIFACTS_NOT_RELEASED",
        ),
        "execution_availability": AvailabilityV1.unavailable(
            AvailabilityStatus.NOT_RELEASED,
            "EXECUTION_NOT_RELEASED",
        ),
    }


def test_build_atomic_run_projection_composes_one_coherent_nonreleased_snapshot() -> None:
    projection = build_atomic_run_projection(**_atomic_kwargs())

    assert projection.object.object_id == "OBJECT-A"
    assert projection.run.run_id == "RUN-A"
    assert projection.run.projection_revision == projection.projection_revision == 7
    assert projection.run.projection_sequence == projection.projection_sequence == 0
    assert set(projection.model_dump(mode="json")["run"]) == {
        "run_id",
        "research_object_id",
        "goal_id",
        "scheme_id",
        "status",
        "stage",
        "as_of",
        "planned_graph_id",
        "actual_graph_id",
        "execution_target",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    }
    assert projection.lifecycle.status == "RUNNING"
    assert projection.lifecycle.progress.fraction == 0.25
    assert tuple(task.task_id for task in projection.tasks) == ("TASK-A",)
    assert projection.terminal.is_terminal is False


def test_build_atomic_run_projection_rejects_cross_object_identity() -> None:
    kwargs = _atomic_kwargs()
    kwargs["research_object"] = ResearchObject(
        object_id="OBJECT-B",
        symbol="OTHER",
        company_name="Other Corporation",
        exchange="NYSE",
        created_at=NOW - timedelta(days=1),
        updated_at=NOW,
    )

    with pytest.raises(ProjectionIntegrityError, match="requested ResearchObject"):
        build_atomic_run_projection(**kwargs)


def test_build_atomic_run_projection_rejects_torn_execution_revision() -> None:
    kwargs = _atomic_kwargs()
    available = AvailabilityV1.available()
    kwargs["execution_availability"] = available
    kwargs["execution_projection"] = ExecutionProjectionV1(
        projection_revision=8,
        projection_sequence=0,
        object_id="OBJECT-A",
        run_id="RUN-A",
        canonical_record_id="CANONICAL-A",
        object_snapshot_ref="OBJECT-A",
        planned_graph={"graph_id": "PLAN-A"},
        actual_graph={"graph_id": "ACTUAL-A"},
        task_refs=("TASK-A",),
        token_usage=0,
        cost=0.0,
        latency_ms=0,
        runtime_outcome="RUNNING",
        availability=available,
    )

    with pytest.raises(ProjectionIntegrityError, match="Execution projection is torn"):
        build_atomic_run_projection(**kwargs)
