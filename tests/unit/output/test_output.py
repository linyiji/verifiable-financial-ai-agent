from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from src.domain.enums import ProofStatus, ReviewStatus
from src.output import (
    CanonicalExecutionRecordBuilder,
    FinancialReportRenderer,
    ObjectWritebackItem,
    ObjectWritebackProposalBuilder,
    ReleasedResearchResultBuilder,
    ReleaseGateSnapshot,
    ValueType,
    WritebackTarget,
    build_canonical_record_projections,
)


def build_record():
    return CanonicalExecutionRecordBuilder.build(
        record_id="CER-RUN-1",
        run_id="RUN-1",
        object_snapshot_ref="OBJECT-SNAPSHOT-1",
        goal_ref="GOAL-1",
        scheme_ref="SCHEME-1",
        planned_graph={"graph_id": "PG-1", "tasks": ["TASK-1"]},
        actual_graph={"graph_id": "AG-1", "tasks": ["TASK-1", "TASK-2"]},
        task_refs=["TASK-1", "TASK-2"],
        evidence_refs=["EVIDENCE-1"],
        calculation_refs=["CALC-1"],
        decision_refs=["DECISION-1"],
        correction_refs=["CORRECTION-1"],
        replan_refs=["REPLAN-1"],
        generated_capability_refs=["CAPABILITY-1"],
        review_refs=["REVIEW-1"],
        proof_refs=["PROOF-1"],
        trace_refs=["TRACE-1"],
        token_usage=123,
        cost=0.42,
        latency_ms=987,
        runtime_outcome="RELEASED",
        created_at=datetime(2026, 9, 3, tzinfo=UTC),
    )


def test_canonical_builder_detaches_sources_and_stably_deduplicates_refs() -> None:
    planned_graph = {"tasks": [{"task_id": "TASK-1"}]}
    record = CanonicalExecutionRecordBuilder.build(
        record_id="CER-1",
        run_id="RUN-1",
        planned_graph=planned_graph,
        actual_graph={"tasks": []},
        task_refs=["TASK-1", "TASK-1", "TASK-2"],
        runtime_outcome="COMPLETED",
    )

    planned_graph["tasks"].append({"task_id": "TASK-UNPUBLISHED"})

    assert record.planned_graph == {"tasks": [{"task_id": "TASK-1"}]}
    assert record.task_refs == ["TASK-1", "TASK-2"]


def test_financial_and_execution_views_share_one_canonical_record() -> None:
    record = build_record()

    projections = build_canonical_record_projections(record)

    assert projections.canonical_record_id == record.record_id
    assert projections.financial_review.canonical_record_id == record.record_id
    assert projections.execution_details.canonical_record_id == record.record_id
    assert projections.financial_review.evidence_refs == record.evidence_refs
    assert projections.execution_details.actual_graph == record.actual_graph
    assert projections.execution_details.trace_refs == record.trace_refs


def test_projections_are_snapshots_and_do_not_requery_or_recompute() -> None:
    record = build_record()
    projections = build_canonical_record_projections(record)

    record.evidence_refs.append("EVIDENCE-AFTER-PROJECTION")
    record.actual_graph["tasks"].append("TASK-AFTER-PROJECTION")

    assert projections.financial_review.evidence_refs == ["EVIDENCE-1"]
    assert projections.execution_details.actual_graph["tasks"] == ["TASK-1", "TASK-2"]


@pytest.mark.parametrize(
    ("gate", "message"),
    [
        (ReleaseGateSnapshot(review_status=ReviewStatus.REVIEW), "release gate"),
        (
            ReleaseGateSnapshot(
                review_status=ReviewStatus.PASS,
                must_prove_statuses=[ProofStatus.FAILED],
            ),
            "release gate",
        ),
        (
            ReleaseGateSnapshot(review_status=ReviewStatus.PASS, has_hard_block=True),
            "release gate",
        ),
    ],
)
def test_released_result_builder_enforces_release_gate(
    gate: ReleaseGateSnapshot,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ReleasedResearchResultBuilder.build(
            result_id="RESULT-1",
            canonical_record=build_record(),
            release_gate=gate,
            structured_financial_results={},
        )


def test_released_result_and_financial_report_preserve_released_data() -> None:
    financial_results = {
        "research_object": "NVDA",
        "financial_summary": {"revenue": 130_497},
        "fundamental_result": {"growth": "strong"},
        "peer_result": {"peer": "AMD"},
        "valuation_result": {"method": "DCF"},
        "investment_thesis": {"summary": "Released judgment"},
    }
    result = ReleasedResearchResultBuilder.build(
        result_id="RESULT-1",
        canonical_record=build_record(),
        release_gate=ReleaseGateSnapshot(
            review_status=ReviewStatus.PASS,
            must_prove_statuses=[ProofStatus.VERIFIED],
        ),
        structured_financial_results=financial_results,
        released_claims=[{"claim_id": "CLAIM-1"}],
        judgments=[{"judgment_id": "JUDGMENT-1"}],
        assumption_refs=["ASSUMPTION-1"],
        risk_output={"risk": "customer concentration"},
        limitations=["Illustrative fixture"],
    )
    financial_results["financial_summary"]["revenue"] = -1

    report = FinancialReportRenderer.render(result)
    report_json = report.model_dump(mode="json")

    assert result.run_id == "RUN-1"
    assert report_json == {
        "research_object": "NVDA",
        "financial_summary": {"revenue": 130_497},
        "fundamental_result": {"growth": "strong"},
        "peer_result": {"peer": "AMD"},
        "valuation_result": {"method": "DCF"},
        "risk_result": {"risk": "customer concentration"},
        "investment_thesis": {"summary": "Released judgment"},
        "limitations": ["Illustrative fixture"],
    }


def writeback_items() -> list[ObjectWritebackItem]:
    common = {
        "period": "FY2026",
        "as_of": date(2026, 1, 31),
        "definition_version": "v1",
        "unit": "USDm",
    }
    return [
        ObjectWritebackItem(
            metric_code="revenue",
            value=130_497,
            value_type=ValueType.FACT,
            writeback_target=WritebackTarget.CANONICAL_STATE,
            source_evidence_ids=["EVIDENCE-1"],
            **common,
        ),
        ObjectWritebackItem(
            metric_code="revenue_growth",
            value=0.114,
            value_type=ValueType.CALCULATION,
            writeback_target=WritebackTarget.VERSIONED_METRIC,
            calculation_id="CALC-1",
            **common,
        ),
        ObjectWritebackItem(
            metric_code="forecast_revenue",
            value=150_000,
            value_type=ValueType.FORECAST,
            writeback_target=WritebackTarget.VERSIONED_FORECAST,
            assumption_set_id="ASSUMPTIONS-1",
            **common,
        ),
        ObjectWritebackItem(
            metric_code="investment_quality",
            value="high quality with valuation risk",
            value_type=ValueType.JUDGMENT,
            writeback_target=WritebackTarget.VERSIONED_JUDGMENT,
            judgment_ref="JUDGMENT-1-v1",
            **common,
        ),
    ]


def test_writeback_proposal_preserves_all_four_value_types() -> None:
    proposal = ObjectWritebackProposalBuilder.build(
        proposal_id="WRITEBACK-1",
        object_id="OBJECT-NVDA",
        run_id="RUN-1",
        items=writeback_items(),
    )

    assert [item.value_type for item in proposal.items] == [
        ValueType.FACT,
        ValueType.CALCULATION,
        ValueType.FORECAST,
        ValueType.JUDGMENT,
    ]
    assert proposal.items[-1].writeback_target is WritebackTarget.VERSIONED_JUDGMENT
    assert proposal.items[-1].writeback_target is not WritebackTarget.CANONICAL_STATE


def test_judgment_cannot_overwrite_canonical_fact_state() -> None:
    with pytest.raises(ValidationError, match="VERSIONED_JUDGMENT"):
        ObjectWritebackItem(
            metric_code="investment_quality",
            period="FY2026",
            as_of=date(2026, 1, 31),
            definition_version="v1",
            value="buy",
            unit="text",
            value_type=ValueType.JUDGMENT,
            writeback_target=WritebackTarget.CANONICAL_STATE,
            judgment_ref="JUDGMENT-1-v1",
        )


@pytest.mark.parametrize(
    ("value_type", "writeback_target", "missing_message"),
    [
        (ValueType.FACT, WritebackTarget.CANONICAL_STATE, "source evidence"),
        (ValueType.CALCULATION, WritebackTarget.VERSIONED_METRIC, "calculation_id"),
        (ValueType.FORECAST, WritebackTarget.VERSIONED_FORECAST, "assumption_set_id"),
        (ValueType.JUDGMENT, WritebackTarget.VERSIONED_JUDGMENT, "judgment_ref"),
    ],
)
def test_writeback_items_require_type_specific_lineage(
    value_type: ValueType,
    writeback_target: WritebackTarget,
    missing_message: str,
) -> None:
    with pytest.raises(ValidationError, match=missing_message):
        ObjectWritebackItem(
            metric_code="metric",
            period="FY2026",
            as_of=date(2026, 1, 31),
            definition_version="v1",
            value=1,
            unit="USD",
            value_type=value_type,
            writeback_target=writeback_target,
        )
