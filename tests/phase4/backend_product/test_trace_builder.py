from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.assurance.independent_financial_review import financial_review_input_snapshot_hash
from src.domain.calculation import CalculationRecord
from src.domain.evidence import EvidenceRecord
from src.domain.financial_semantics import MaterialFinancialClaim, ReleasedFinancialMetric
from src.domain.proof import ProofPolicyDecision
from src.phase4_product.contracts import (
    AvailabilityStatus,
    AvailabilityV1,
    RendererIdentityV1,
    ReportArtifactGroupV1,
    ReportArtifactRepresentationV1,
)
from src.phase4_product.hashing import canonical_json_sha256
from src.phase4_product.projections import (
    ProjectionIntegrityError,
    build_claim_detail,
    build_financial_review,
    build_trace_bundle,
)

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)
AS_OF = date(2026, 9, 5)
SHA = "sha256:" + "a" * 64


def _metric() -> dict[str, object]:
    return {
        "metric_id": "METRIC-A",
        "calculation_id": "CALC-A",
        "name": "SMA 50",
        "canonical_value": "123.4500",
        "canonical_unit": "INDEX",
        "display_value": "123.45",
        "display_unit": "points",
        "period": "CURRENT",
        "period_basis": "CURRENT",
        "actuality": "ACTUAL",
        "as_of": AS_OF,
        "currency": None,
        "formula_id": "sma_close_50_v1",
        "capability_id": "sma",
        "evidence_ids": ("EVIDENCE-A",),
        "method_metadata": None,
        "technical_price_basis": "RAW_CLOSE",
        "corporate_action_status": "NONE_DETECTED",
        "corporate_action_guard_refs": ("EVIDENCE-A",),
        "limitations": (),
    }


def _claim() -> dict[str, object]:
    return {
        "claim_id": "CLAIM-A",
        "run_id": "RUN-A",
        "claim_type": "TECHNICAL_METRIC",
        "statement": "The exact retained SMA is 123.45 points.",
        "metric_id": "METRIC-A",
        "value": "123.4500",
        "unit": "INDEX",
        "period": "CURRENT",
        "period_basis": "CURRENT",
        "actuality": "ACTUAL",
        "as_of": AS_OF,
        "currency": None,
        "calculation_refs": ("CALC-A",),
        "evidence_refs": ("EVIDENCE-A",),
        "judgment_refs": (),
    }


def _calculation() -> dict[str, object]:
    return {
        "calculation_id": "CALC-A",
        "run_id": "RUN-A",
        "task_id": "TASK-A",
        "capability_id": "sma",
        "capability_version": "1.0.0",
        "formula_id": "sma_close_50_v1",
        "input_evidence_ids": ("EVIDENCE-A",),
        "input_values_snapshot": {
            "window": 50,
            "observation_count": 50,
            "first_as_of": "2026-06-18",
            "last_as_of": "2026-09-05",
            "technical_price_basis": "RAW_CLOSE",
            "corporate_action_status": "NONE_DETECTED",
        },
        "parameters": {},
        "output_value": "123.4500",
        "output_unit": "INDEX",
        "status": "PASS",
        "review_status": "PASS",
        "implementation_hash": SHA,
        "runtime_version": "python-3.11",
        "review_record_id": "REVIEW-A",
        "canonical_record_id": "CER-A",
        "proof_ref": None,
        "created_at": NOW,
    }


def _evidence() -> dict[str, object]:
    return {
        "evidence_id": "EVIDENCE-A",
        "run_id": "RUN-A",
        "object_id": "OBJ-A",
        "provider": "market-data",
        "producer_task_id": "TASK-A",
        "evidence_purpose": "SMA close inputs",
        "evidence_category": "MARKET",
        "retrieved_at": NOW,
        "observed_at": NOW,
        "provider_timestamp": NOW,
        "period": "CURRENT",
        "period_basis": "CURRENT",
        "actuality": "ACTUAL",
        "as_of": AS_OF,
        "raw_artifact_ref": "artifact://market-data/EVIDENCE-A",
        "normalized_field": "close",
        "normalized_value": "123.45",
        "unit": "INDEX",
        "currency": None,
        "snapshot_hash": SHA,
        "status": "ACCEPTED",
        "created_at": NOW,
    }


def _policy() -> dict[str, object]:
    return {
        "decision_id": "DECISION-A",
        "run_id": "RUN-A",
        "calculation_id": "CALC-A",
        "formula_id": "sma_close_50_v1",
        "requirement": "NOT_REQUIRED",
        "policy_id": "proof-policy-v1",
        "reason": "Not required under the frozen policy.",
        "created_at": NOW,
    }


def _run() -> dict[str, object]:
    return {
        "run_id": "RUN-A",
        "research_object_id": "OBJ-A",
        "status": "RELEASED",
        "as_of": AS_OF,
    }


def _canonical() -> dict[str, object]:
    return {
        "record_id": "CER-A",
        "run_id": "RUN-A",
        "object_snapshot_ref": "OBJ-A",
        "review_refs": ("REVIEW-A",),
    }


def _released_result() -> dict[str, object]:
    return {
        "result_id": "RESULT-A",
        "run_id": "RUN-A",
        "canonical_record_id": "CER-A",
        "material_claims": (_claim(),),
        "released_metrics": (_metric(),),
    }


def _review_projection():
    evidence_records = (EvidenceRecord.model_validate(_evidence()),)
    calculation_records = (CalculationRecord.model_validate(_calculation()),)
    metric_records = (ReleasedFinancialMetric.model_validate(_metric()),)
    claim_records = (MaterialFinancialClaim.model_validate(_claim()),)
    judgment_records: tuple[dict[str, object], ...] = ()
    proof_policy_decisions = (ProofPolicyDecision.model_validate(_policy()),)
    input_snapshot_hash = financial_review_input_snapshot_hash(
        run_id="RUN-A",
        run_as_of=AS_OF,
        evidence=evidence_records,
        calculations=calculation_records,
        metrics=metric_records,
        claims=claim_records,
        judgments=list(judgment_records),
        proof_requirements={
            decision.calculation_id: decision.requirement for decision in proof_policy_decisions
        },
    )
    return build_financial_review(
        expected_object_id="OBJ-A",
        expected_run_id="RUN-A",
        projection_revision=6,
        projection_sequence=11,
        run=_run(),
        review={
            "review_id": "REVIEW-A",
            "run_id": "RUN-A",
            "status": "PASS",
            "reviewer": "independent-financial-review-v2",
            "input_snapshot_hash": input_snapshot_hash,
            "reviewed_evidence_refs": ("EVIDENCE-A",),
            "reviewed_calculation_refs": ("CALC-A",),
            "reviewed_metric_refs": ("METRIC-A",),
            "reviewed_claim_refs": ("CLAIM-A",),
            "reviewed_judgment_refs": (),
            "required_proof_calculation_refs": (),
            "checks": (
                {
                    "check_id": "CHECK-A",
                    "check_code": "CALCULATION_MATCH",
                    "status": "PASS",
                    "subjects": (
                        {
                            "subject_type": "CALCULATION",
                            "subject_id": "CALC-A",
                            "run_id": "RUN-A",
                        },
                    ),
                    "expected": {"formula_id": "sma_close_50_v1"},
                    "actual": {"formula_id": "sma_close_50_v1"},
                    "detail": None,
                    "exception_state": "NONE",
                    "correction_refs": (),
                    "created_at": NOW,
                    "resolved_at": None,
                },
            ),
        },
        canonical_record={**_canonical(), "review_refs": ("REVIEW-A",)},
        released_result=_released_result(),
        evidence_records=evidence_records,
        calculation_records=calculation_records,
        metric_records=metric_records,
        claim_records=claim_records,
        judgment_records=judgment_records,
        proof_policy_decisions=proof_policy_decisions,
    )


def _representation_anchor(
    format_: str,
    *,
    artifact_id: str | None,
    availability: AvailabilityV1,
) -> dict[str, object]:
    return {
        "anchor_id": f"ANCHOR-{format_}-A" if artifact_id is not None else None,
        "anchor_kind": "REPORT_CLAIM",
        "object_id": "OBJ-A",
        "run_id": "RUN-A",
        "claim_id": "CLAIM-A",
        "availability": availability.model_dump(mode="json"),
        "metric_id": "METRIC-A",
        "report_id": "RESULT-A",
        "released_result_id": "RESULT-A",
        "canonical_record_id": "CER-A",
        "format": format_,
        "artifact_id": artifact_id,
    }


def _manifest(*, include_task_anchor: bool = True) -> dict[str, object]:
    available = AvailabilityV1.available()
    pdf_absent = AvailabilityV1.unavailable(
        AvailabilityStatus.NOT_GENERATED,
        "PDF_NOT_GENERATED_BY_POLICY",
    )
    manifest: dict[str, object] = {
        "schema_version": "phase4-claim-anchor-manifest/v1",
        "anchor_manifest_id": "MANIFEST-A",
        "object_id": "OBJ-A",
        "run_id": "RUN-A",
        "claim_id": "CLAIM-A",
        "metric_id": "METRIC-A",
        "canonical_record_id": "CER-A",
        "released_result_id": "RESULT-A",
        "report_id": "RESULT-A",
        "representations": [
            _representation_anchor("HTML", artifact_id="ARTIFACT-HTML-A", availability=available),
            _representation_anchor("PDF", artifact_id=None, availability=pdf_absent),
        ],
        "review_anchors": [],
        "task_anchors": (
            [
                {
                    "anchor_id": "ANCHOR-TASK-A",
                    "anchor_kind": "TASK",
                    "object_id": "OBJ-A",
                    "run_id": "RUN-A",
                    "claim_id": "CLAIM-A",
                    "availability": available.model_dump(mode="json"),
                    "task_id": "TASK-A",
                }
            ]
            if include_task_anchor
            else []
        ),
        "execution_anchors": [],
        "created_at": NOW.isoformat(),
    }
    manifest["anchor_manifest_sha256"] = canonical_json_sha256(manifest)
    return manifest


def _artifact_group(manifest: dict[str, object]) -> ReportArtifactGroupV1:
    renderer = RendererIdentityV1(renderer_id="report-renderer", renderer_version="v1")
    html = ReportArtifactRepresentationV1(
        format="HTML",
        required_for_release=True,
        content_type="text/html; charset=utf-8",
        availability=AvailabilityV1.available(),
        artifact_id="ARTIFACT-HTML-A",
        safe_failure_code=None,
        generation_attempt_id="ATTEMPT-HTML-A",
        generation_attempt_count=1,
        sha256=SHA,
        size_bytes=128,
        renderer=renderer,
        generated_at=NOW,
        authorized_ref="/api/research-runs/RUN-A/artifacts/ARTIFACT-HTML-A/content",
    )
    pdf = ReportArtifactRepresentationV1(
        format="PDF",
        required_for_release=False,
        content_type="application/pdf",
        availability=AvailabilityV1.unavailable(
            AvailabilityStatus.NOT_GENERATED,
            "PDF_NOT_GENERATED_BY_POLICY",
        ),
        artifact_id=None,
        safe_failure_code=None,
        generation_attempt_id=None,
        generation_attempt_count=0,
        sha256=None,
        size_bytes=None,
        renderer=None,
        generated_at=None,
        authorized_ref=None,
    )
    return ReportArtifactGroupV1(
        object_id="OBJ-A",
        run_id="RUN-A",
        report_id="RESULT-A",
        canonical_record_id="CER-A",
        released_result_id="RESULT-A",
        anchor_manifest_id="MANIFEST-A",
        anchor_manifest_sha256=manifest["anchor_manifest_sha256"],
        availability=AvailabilityV1.available(),
        representations=(html, pdf),
    )


def _trace_values(**updates: object) -> dict[str, object]:
    manifest = _manifest()
    values: dict[str, object] = {
        "expected_object_id": "OBJ-A",
        "expected_run_id": "RUN-A",
        "claim_id": "CLAIM-A",
        "projection_revision": 6,
        "projection_sequence": 11,
        "run": _run(),
        "canonical_record": _canonical(),
        "released_result": _released_result(),
        "calculations": (_calculation(),),
        "evidence": (_evidence(),),
        "tasks": ({"task_id": "TASK-A", "run_id": "RUN-A"},),
        "proof_policy_decisions": (_policy(),),
        "anchor_manifest": manifest,
        "artifact_group": _artifact_group(manifest),
        "review_projections": (_review_projection(),),
        "primary_task_id": "TASK-A",
    }
    values.update(updates)
    return values


def _build_trace(**updates: object):
    return build_trace_bundle(**_trace_values(**updates))  # type: ignore[arg-type]


def test_trace_bundle_closes_exact_claim_metric_calculation_and_report_identities() -> None:
    trace = _build_trace()

    assert trace.schema_version == "phase4-trace/v1"
    assert (trace.object_id, trace.run_id, trace.claim_id) == ("OBJ-A", "RUN-A", "CLAIM-A")
    assert (trace.metric_id, trace.calculation_id) == ("METRIC-A", "CALC-A")
    assert trace.canonical_record_id == "CER-A"
    assert trace.released_result_id == "RESULT-A"
    assert trace.report.report_id == "RESULT-A"
    assert [item.format for item in trace.report.representations] == ["HTML", "PDF"]
    assert [item.task_id for item in trace.task_refs] == ["TASK-A"]
    assert [item.evidence_id for item in trace.evidence_refs] == ["EVIDENCE-A"]
    assert [item.calculation_id for item in trace.calculation_refs] == ["CALC-A"]
    assert [item.review_id for item in trace.review_refs] == ["REVIEW-A"]
    assert trace.proof_refs == ()


def test_claim_detail_uses_the_same_exact_authoritative_closure() -> None:
    detail = build_claim_detail(**_trace_values())  # type: ignore[arg-type]

    assert (detail.object_id, detail.run_id, detail.claim_id) == (
        "OBJ-A",
        "RUN-A",
        "CLAIM-A",
    )
    assert detail.released_metric.metric_id == "METRIC-A"
    assert detail.canonical_record_id == "CER-A"
    assert detail.released_result_id == "RESULT-A"
    assert detail.primary_task_id == "TASK-A"
    assert detail.anchors.anchor_manifest_id == "MANIFEST-A"


def test_trace_rejects_absent_exact_claim_instead_of_selecting_another_claim() -> None:
    with pytest.raises(ProjectionIntegrityError, match="absent or ambiguous"):
        _build_trace(claim_id="CLAIM-NOT-THERE")


def test_trace_rejects_cross_run_artifact_group_and_missing_task_anchor() -> None:
    manifest = _manifest()
    foreign_group = _artifact_group(manifest).model_copy(update={"run_id": "RUN-B"})
    with pytest.raises(ProjectionIntegrityError, match="artifact group belongs"):
        _build_trace(artifact_group=foreign_group)

    torn_manifest = _manifest(include_task_anchor=False)
    with pytest.raises(ProjectionIntegrityError, match="Task anchors"):
        _build_trace(
            anchor_manifest=torn_manifest,
            artifact_group=_artifact_group(torn_manifest),
        )


def test_trace_rejects_secret_bearing_calculation_payload() -> None:
    calculation = {**_calculation(), "input_values_snapshot": {"api_key": "secret"}}
    with pytest.raises(ProjectionIntegrityError, match="api_key"):
        _build_trace(calculations=(calculation,))
