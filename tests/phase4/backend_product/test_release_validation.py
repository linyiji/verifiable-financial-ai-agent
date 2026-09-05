"""Focused gates for durable release validation and exact Review references."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from src.assurance.independent_financial_review import (
    financial_review_input_snapshot_hash,
)
from src.domain.calculation import CalculationRecord
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.enums import (
    CalculationStatus,
    CorporateActionStatus,
    EvidenceCategory,
    EvidenceStatus,
    FinancialActuality,
    FinancialPeriodBasis,
    FinancialUnit,
    MaterialCalculationDispositionStatus,
    ProofRequirement,
    ProofStatus,
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
from src.domain.proof import (
    ProofInputCommitment,
    ProofPolicyDecision,
    ProofRecord,
    ProofVerificationRecord,
)
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.task import ActualRuntimeGraph, PlannedTaskGraph, Task
from src.output.financial_metrics import MATERIAL_FORMULAS
from src.phase4_product.artifacts import (
    ArtifactRepresentationSource,
    build_report_artifact_group,
)
from src.phase4_product.contracts import (
    AvailabilityStatus,
    AvailabilityV1,
    FinancialReviewProjectionV1,
    ProofSummaryV1,
    RendererIdentityV1,
    ReportArtifactGroupV1,
    ReportArtifactRepresentationV1,
    RunCollectionItemV1,
    RunProgressV1,
    SafeRuntimeActivityV1,
)
from src.phase4_product.errors import ProductError
from src.phase4_product.hashing import canonical_json_sha256, sha256_bytes
from src.phase4_product.projections import (
    EligibleReleasedObjectCandidate,
    ProjectionIntegrityError,
    ReleaseCandidateSourceV1,
    _validate_atomic_release_validation,
    build_execution_projection,
    build_financial_review,
    build_released_object_core,
    build_released_result_projection,
    compute_release_validation_hashes,
    project_run_status,
)
from src.phase4_product.reconstruction import (
    PersistedReleaseValidation,
    PersistedRunSnapshot,
    reconstruct_product_run,
)

NOW = datetime(2026, 9, 5, 10, tzinfo=UTC)
SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64


def _persisted_validation(**updates: object) -> PersistedReleaseValidation:
    values: dict[str, object] = {
        "validation_id": "VALIDATION-A",
        "run_id": "RUN-A",
        "object_id": "OBJ-A",
        "decision": "ALLOWED",
        "reason_codes": (),
        "review_id": "REVIEW-A",
        "canonical_record_id": "CER-A",
        "released_result_id": "RESULT-A",
        "release_policy_version": "phase4-release-eligibility/v1",
        "review_policy_version": "phase4-independent-financial-review/v1",
        "proof_policy_id": "PROOF-POLICY-A",
        "proof_policy_hash": SHA_A,
        "material_output_policy_version": "phase4-full-material-output/v1",
        "material_output_manifest_hash": SHA_A,
        "artifact_policy_version": "phase4-html-required-pdf-optional/v1",
        "artifact_manifest_hash": SHA_A,
        "review_input_snapshot_hash": SHA_A,
        "closure_hash": SHA_A,
        "evaluated_at": NOW - timedelta(minutes=1),
        "released_at": NOW,
    }
    values.update(updates)
    return PersistedReleaseValidation(**values)  # type: ignore[arg-type]


def _draft_snapshot(
    *,
    validations: tuple[PersistedReleaseValidation, ...] = (),
) -> PersistedRunSnapshot:
    research_object = ResearchObject(
        object_id="OBJ-A",
        symbol="ACME",
        company_name="Acme Corp",
        exchange="NASDAQ",
        created_at=NOW,
        updated_at=NOW,
    )
    goal = ResearchGoal(
        goal_id="GOAL-A",
        research_object_id="OBJ-A",
        goal_text="Validate the exact release boundary",
        as_of=date(2026, 9, 5),
        created_at=NOW,
    )
    scheme = ResearchSchemeSnapshot(
        scheme_id="SCHEME-A",
        research_object_id="OBJ-A",
        goal_id="GOAL-A",
        generated_by="planner-v1",
        confirmed_at=NOW,
        created_at=NOW,
    )
    task = Task(
        task_id="TASK-A",
        run_id="RUN-A",
        task_type="research",
        goal="Collect exact inputs",
        assigned_agent="research-agent",
        skill_id="research-skill",
        status=TaskStatus.CREATED,
        created_at=NOW,
    )
    planned = PlannedTaskGraph(
        graph_id="PLAN-A",
        run_id="RUN-A",
        tasks=[task.model_copy(deep=True)],
        created_at=NOW,
    )
    actual = ActualRuntimeGraph(
        graph_id="ACTUAL-A",
        run_id="RUN-A",
        tasks=[task.model_copy(deep=True)],
        created_at=NOW,
    )
    run = ResearchRun(
        run_id="RUN-A",
        research_object_id="OBJ-A",
        goal_id="GOAL-A",
        scheme_id="SCHEME-A",
        status=RunStatus.DRAFT,
        as_of=date(2026, 9, 5),
        planned_graph_id="PLAN-A",
        actual_graph_id="ACTUAL-A",
        created_at=NOW,
    )
    return PersistedRunSnapshot(
        requested_object_id="OBJ-A",
        requested_run_id="RUN-A",
        projection_revision=1,
        projection_sequence=0,
        research_objects=(research_object,),
        goals=(goal,),
        schemes=(scheme,),
        runs=(run,),
        planned_graphs=(planned,),
        actual_graphs=(actual,),
        tasks=(task,),
        release_validations=validations,
    )


def test_persisted_validation_enforces_decision_and_hash_state() -> None:
    assert _persisted_validation().decision == "ALLOWED"

    with pytest.raises(ProductError, match="requires released_at"):
        _persisted_validation(released_at=None)
    with pytest.raises(ProductError, match="sha256"):
        _persisted_validation(closure_hash="placeholder")
    with pytest.raises(ProductError, match="requires reasons"):
        _persisted_validation(decision="BLOCKED", released_at=None)


def test_nonreleased_exact_snapshot_rejects_allowed_validation() -> None:
    with pytest.raises(ProductError, match="non-RELEASED"):
        reconstruct_product_run(_draft_snapshot(validations=(_persisted_validation(),)))


def _candidate() -> EligibleReleasedObjectCandidate:
    evidence_records: list[EvidenceRecord] = []
    calculation_records: list[CalculationRecord] = []
    metric_records: list[ReleasedFinancialMetric] = []
    claim_records: list[MaterialFinancialClaim] = []
    dispositions: list[MaterialCalculationDisposition] = []
    proof_policy_decisions: list[ProofPolicyDecision] = []
    proof_records: list[ProofRecord] = []
    proof_verifications: list[ProofVerificationRecord] = []
    proof_commitments: list[ProofInputCommitment] = []
    for index, formula_id in enumerate(MATERIAL_FORMULAS):
        metric_id = f"METRIC-{index}"
        calculation_id = f"CALC-{index}"
        claim_id = f"CLAIM-{index}"
        evidence_id = f"EVIDENCE-{index}"
        capability_id = f"CAPABILITY-{index}"
        must_prove = index == 0

        evidence_records.append(
            EvidenceRecord(
                evidence_id=evidence_id,
                run_id="RUN-A",
                object_id="OBJ-A",
                provider="fixture",
                source_locator=f"fixture://release/{evidence_id}",
                producer_task_id="TASK-A",
                evidence_category=EvidenceCategory.MARKET,
                retrieved_at=NOW - timedelta(minutes=20),
                period="CURRENT",
                period_basis=FinancialPeriodBasis.CURRENT,
                actuality=FinancialActuality.ACTUAL,
                technical_price_basis=(None if index < 3 else TechnicalPriceBasis.ADJUSTED_CLOSE),
                corporate_action_status=(None if index < 3 else CorporateActionStatus.RESOLVED),
                as_of=date(2026, 9, 5),
                raw_artifact_ref=f"ARTIFACT-{evidence_id}",
                normalized_field=f"value_{index}",
                normalized_value=str(index + 1),
                unit="RATIO",
                snapshot_hash=SHA_A,
                status=EvidenceStatus.ACCEPTED,
                created_at=NOW - timedelta(minutes=20),
            )
        )
        calculation_records.append(
            CalculationRecord(
                calculation_id=calculation_id,
                run_id="RUN-A",
                task_id="TASK-A",
                capability_id=capability_id,
                capability_version="v1",
                formula_id=formula_id,
                input_evidence_ids=[evidence_id],
                input_values_snapshot={f"value_{index}": str(index + 1)},
                parameters={},
                output_value=str(index + 1),
                output_unit="RATIO",
                status=CalculationStatus.PASS,
                review_status=ReviewStatus.PASS,
                implementation_hash=SHA_A,
                created_at=NOW - timedelta(minutes=15),
            )
        )
        metric = ReleasedFinancialMetric(
            metric_id=metric_id,
            calculation_id=calculation_id,
            name=f"Metric {index}",
            canonical_value=str(index + 1),
            canonical_unit=FinancialUnit.RATIO,
            display_value=str(index + 1),
            display_unit="x",
            period="CURRENT",
            period_basis=FinancialPeriodBasis.CURRENT,
            actuality=FinancialActuality.ACTUAL,
            as_of=date(2026, 9, 5),
            formula_id=formula_id,
            capability_id=capability_id,
            evidence_ids=(evidence_id,),
            method_metadata=TechnicalMethodMetadata(
                method="reported" if index < 3 else "adjusted-close-series",
                technical_price_basis=(None if index < 3 else TechnicalPriceBasis.ADJUSTED_CLOSE),
            ),
            technical_price_basis=(None if index < 3 else TechnicalPriceBasis.ADJUSTED_CLOSE),
            corporate_action_status=None if index < 3 else CorporateActionStatus.RESOLVED,
            corporate_action_guard_refs=() if index < 3 else (evidence_id,),
        )
        metric_records.append(metric)
        claim_records.append(
            MaterialFinancialClaim(
                claim_id=claim_id,
                run_id="RUN-A",
                claim_type="FINANCIAL_METRIC",
                statement=f"Metric {index} is {index + 1}",
                metric_id=metric_id,
                value=metric.canonical_value,
                unit=metric.canonical_unit,
                period=metric.period,
                period_basis=metric.period_basis,
                actuality=metric.actuality,
                as_of=metric.as_of,
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
        proof_policy_decisions.append(
            ProofPolicyDecision(
                decision_id=f"PROOF-DECISION-{index}",
                run_id="RUN-A",
                calculation_id=calculation_id,
                formula_id=formula_id,
                requirement=(
                    ProofRequirement.MUST_PROVE if must_prove else ProofRequirement.NOT_REQUIRED
                ),
                policy_id="PROOF-POLICY-A",
                reason="Deterministic release policy fixture.",
                created_at=NOW - timedelta(minutes=10),
            )
        )
        if must_prove:
            proof_commitments.append(
                ProofInputCommitment(
                    commitment_id="COMMITMENT-0",
                    run_id="RUN-A",
                    calculation_id=calculation_id,
                    formula_id=formula_id,
                    capability_id=capability_id,
                    implementation_hash=SHA_A,
                    input_evidence_refs=[evidence_id],
                    canonical_inputs={f"value_{index}": str(index + 1)},
                    input_commitment=SHA_A,
                    expected_output_commitment=SHA_B,
                    created_at=NOW - timedelta(minutes=9),
                )
            )
            proof_records.append(
                ProofRecord(
                    proof_id="PROOF-0",
                    run_id="RUN-A",
                    calculation_id=calculation_id,
                    backend="risc0",
                    program_id="PROGRAM-A",
                    image_id="IMAGE-A",
                    implementation_hash=SHA_A,
                    input_commitment=SHA_A,
                    receipt_hash=SHA_A,
                    journal_hash=SHA_B,
                    status=ProofStatus.VALID,
                    created_at=NOW - timedelta(minutes=8),
                )
            )
            proof_verifications.append(
                ProofVerificationRecord(
                    verification_id="VERIFICATION-0",
                    proof_id="PROOF-0",
                    verifier="risc0-verifier",
                    image_id="IMAGE-A",
                    receipt_hash=SHA_A,
                    journal_hash=SHA_B,
                    status=ProofStatus.VERIFIED,
                    verified=True,
                    created_at=NOW - timedelta(minutes=7),
                )
            )

    availability = AvailabilityV1.available()
    source_run = ResearchRun(
        run_id="RUN-A",
        research_object_id="OBJ-A",
        goal_id="GOAL-A",
        scheme_id="SCHEME-A",
        status=RunStatus.RELEASED,
        as_of=date(2026, 9, 5),
        planned_graph_id="PLAN-A",
        actual_graph_id="ACTUAL-A",
        started_at=NOW - timedelta(minutes=30),
        completed_at=NOW,
        created_at=NOW - timedelta(hours=1),
    )
    task = Task(
        task_id="TASK-A",
        run_id="RUN-A",
        task_type="research",
        goal="Produce the exact material set",
        assigned_agent="research-agent",
        skill_id="research-skill",
        status=TaskStatus.COMPLETED,
        progress=1.0,
        attempt_count=1,
        result_ref="RESULT-A",
        created_at=NOW - timedelta(minutes=29),
    )
    planned_graph = PlannedTaskGraph(
        graph_id="PLAN-A",
        run_id="RUN-A",
        tasks=[task.model_copy(deep=True)],
        created_at=NOW - timedelta(minutes=28),
    )
    actual_graph = ActualRuntimeGraph(
        graph_id="ACTUAL-A",
        run_id="RUN-A",
        tasks=[task.model_copy(deep=True)],
        created_at=NOW - timedelta(minutes=27),
    )
    canonical_record = CanonicalExecutionRecord(
        record_id="CER-A",
        run_id="RUN-A",
        object_snapshot_ref="OBJ-A",
        goal_ref="GOAL-A",
        scheme_ref="SCHEME-A",
        planned_graph=planned_graph.model_dump(mode="python"),
        actual_graph=actual_graph.model_dump(mode="python"),
        task_refs=["TASK-A"],
        evidence_refs=[item.evidence_id for item in evidence_records],
        calculation_refs=[item.calculation_id for item in calculation_records],
        metric_refs=[item.metric_id for item in metric_records],
        claim_refs=[item.claim_id for item in claim_records],
        review_refs=["REVIEW-A"],
        proof_refs=[item.proof_id for item in proof_records],
        token_usage=1,
        cost=0.01,
        latency_ms=1,
        runtime_outcome="RELEASED",
        created_at=NOW - timedelta(minutes=5),
    )
    released_result = ReleasedResearchResult(
        result_id="RESULT-A",
        run_id="RUN-A",
        canonical_record_id="CER-A",
        released_metrics=tuple(metric_records),
        material_claims=tuple(claim_records),
        material_calculation_dispositions=tuple(dispositions),
        released_at=NOW,
    )
    review_input_hash = financial_review_input_snapshot_hash(
        run_id="RUN-A",
        run_as_of=date(2026, 9, 5),
        evidence=tuple(evidence_records),
        calculations=tuple(calculation_records),
        metrics=tuple(metric_records),
        claims=tuple(claim_records),
        judgments=(),
        proof_requirements={
            item.calculation_id: item.requirement for item in proof_policy_decisions
        },
    )
    review_record = {
        "review_id": "REVIEW-A",
        "run_id": "RUN-A",
        "status": "PASS",
        "reviewer": "independent-financial-review-v2",
        "input_snapshot_hash": review_input_hash,
        "reviewed_evidence_refs": tuple(item.evidence_id for item in evidence_records),
        "reviewed_calculation_refs": tuple(item.calculation_id for item in calculation_records),
        "reviewed_metric_refs": tuple(item.metric_id for item in metric_records),
        "reviewed_claim_refs": tuple(item.claim_id for item in claim_records),
        "reviewed_judgment_refs": (),
        "required_proof_calculation_refs": ("CALC-0",),
        "checks": (
            {
                "check_id": "CHECK-A",
                "check_code": "FULL_SET",
                "status": "PASS",
                "subjects": ({"subject_type": "RUN", "subject_id": "RUN-A", "run_id": "RUN-A"},),
                "expected": {"count": len(MATERIAL_FORMULAS)},
                "actual": {"count": len(MATERIAL_FORMULAS)},
                "exception_state": "NONE",
                "correction_refs": (),
                "created_at": NOW - timedelta(minutes=3),
            },
        ),
    }
    result = build_released_result_projection(
        expected_object_id="OBJ-A",
        expected_run_id="RUN-A",
        run=source_run,
        canonical_record=canonical_record,
        released_result=released_result,
        calculations=calculation_records,
        evidence=evidence_records,
        proof_policy_decisions=proof_policy_decisions,
        proof_records=proof_records,
        proof_verifications=proof_verifications,
        proof_commitments=proof_commitments,
    )
    review = build_financial_review(
        expected_object_id="OBJ-A",
        expected_run_id="RUN-A",
        projection_revision=9,
        projection_sequence=20,
        run=source_run,
        review=review_record,
        canonical_record=canonical_record,
        released_result=released_result,
        tasks=(task,),
        proof_records=proof_records,
        correction_records=(),
        evidence_records=evidence_records,
        calculation_records=calculation_records,
        metric_records=metric_records,
        claim_records=claim_records,
        judgment_records=(),
        proof_policy_decisions=proof_policy_decisions,
    )
    execution = build_execution_projection(
        expected_object_id="OBJ-A",
        expected_run_id="RUN-A",
        projection_revision=9,
        projection_sequence=20,
        canonical_record=canonical_record,
        released_result=released_result,
    )
    run = RunCollectionItemV1(
        run_id="RUN-A",
        object={"object_id": "OBJ-A", "symbol": "ACME", "company_name": "Acme Corp"},
        status="RELEASED",
        stage="COMPLETE",
        progress=RunProgressV1(completed_tasks=1, total_tasks=1, fraction=1.0),
        activity=None,
        graph_version=1,
        projection_revision=9,
        projection_sequence=20,
        as_of=date(2026, 9, 5),
        created_at=NOW - timedelta(hours=1),
        updated_at=NOW,
        started_at=NOW - timedelta(minutes=30),
        completed_at=NOW,
        terminal=True,
        result_availability=availability,
    )
    html_payload = b"<!doctype html><html><body>Exact release A</body></html>"
    html_sha256 = sha256_bytes(html_payload)
    html_attempt = {
        "attempt_id": "ATTEMPT-HTML-A",
        "object_id": "OBJ-A",
        "run_id": "RUN-A",
        "report_id": "RESULT-A",
        "canonical_record_id": "CER-A",
        "released_result_id": "RESULT-A",
        "format": "HTML",
        "renderer": {"renderer_id": "renderer", "renderer_version": "v1"},
        "semantic_input_sha256": SHA_A,
        "outcome": "AVAILABLE",
        "safe_failure_code": None,
        "started_at": NOW - timedelta(minutes=2),
        "completed_at": NOW - timedelta(minutes=1),
    }
    html_artifact_record = {
        "artifact_id": "ARTIFACT-HTML-A",
        "run_id": "RUN-A",
        "canonical_record_id": "CER-A",
        "released_result_id": "RESULT-A",
        "artifact_type": "text/html; charset=utf-8",
        "content_hash": html_sha256,
        "size_bytes": len(html_payload),
        "renderer_version": "v1",
        "created_at": NOW - timedelta(minutes=1),
    }
    html_source = ArtifactRepresentationSource(
        format="HTML",
        availability=availability,
        generation_attempt_count=1,
        artifact=html_artifact_record,
        generation_attempt=html_attempt,
        authorized=True,
    )
    pdf_availability = AvailabilityV1.unavailable(
        AvailabilityStatus.NOT_GENERATED,
        "PDF_NOT_GENERATED_BY_POLICY",
    )
    pdf_source = ArtifactRepresentationSource(
        format="PDF",
        availability=pdf_availability,
        generation_attempt_count=0,
    )
    anchor_manifest = {
        "schema_version": "phase4-claim-anchor-manifest/v1",
        "anchor_manifest_id": "MANIFEST-A",
        "object_id": "OBJ-A",
        "run_id": "RUN-A",
        "claim_id": "CLAIM-0",
        "metric_id": "METRIC-0",
        "canonical_record_id": "CER-A",
        "released_result_id": "RESULT-A",
        "report_id": "RESULT-A",
        "representations": [
            {
                "anchor_id": "ANCHOR-HTML-A",
                "anchor_kind": "REPORT_CLAIM",
                "object_id": "OBJ-A",
                "run_id": "RUN-A",
                "claim_id": "CLAIM-0",
                "availability": availability.model_dump(mode="json"),
                "metric_id": "METRIC-0",
                "report_id": "RESULT-A",
                "released_result_id": "RESULT-A",
                "canonical_record_id": "CER-A",
                "format": "HTML",
                "artifact_id": "ARTIFACT-HTML-A",
            },
            {
                "anchor_id": None,
                "anchor_kind": "REPORT_CLAIM",
                "object_id": "OBJ-A",
                "run_id": "RUN-A",
                "claim_id": "CLAIM-0",
                "availability": pdf_availability.model_dump(mode="json"),
                "metric_id": "METRIC-0",
                "report_id": "RESULT-A",
                "released_result_id": "RESULT-A",
                "canonical_record_id": "CER-A",
                "format": "PDF",
                "artifact_id": None,
            },
        ],
        "review_anchors": [],
        "task_anchors": [],
        "execution_anchors": [],
        "created_at": "2026-09-05T10:00:00Z",
    }
    anchor_manifest["anchor_manifest_sha256"] = canonical_json_sha256(anchor_manifest)
    artifacts = build_report_artifact_group(
        expected_object_id="OBJ-A",
        expected_run_id="RUN-A",
        run=source_run,
        canonical_record=canonical_record,
        released_result=released_result,
        anchor_manifest=anchor_manifest,
        html=html_source,
        pdf=pdf_source,
        availability=availability,
    )
    candidate = EligibleReleasedObjectCandidate(
        run=run,
        validation=({},),
        review=review,
        result=result,
        execution=execution,
        artifacts=artifacts,
        proof=ProofSummaryV1(
            availability=availability,
            policy="MIXED",
            status="VERIFIED",
            proof_refs=("PROOF-0",),
        ),
        source=ReleaseCandidateSourceV1(
            run=source_run,
            review=review_record,
            canonical_record=canonical_record,
            released_result=released_result,
            tasks=(task,),
            proof_records=tuple(proof_records),
            correction_records=(),
            evidence_records=tuple(evidence_records),
            calculation_records=tuple(calculation_records),
            metric_records=tuple(metric_records),
            claim_records=tuple(claim_records),
            judgment_records=(),
            proof_policy_decisions=tuple(proof_policy_decisions),
            anchor_manifest=anchor_manifest,
            html_artifact=html_source,
            pdf_artifact=pdf_source,
            artifact_availability=availability,
            html_payload=html_payload,
            proof_verifications=tuple(proof_verifications),
            proof_commitments=tuple(proof_commitments),
        ),
    )
    hashes = compute_release_validation_hashes(candidate, validation_id="VALIDATION-A")
    validation = {
        "validation_id": "VALIDATION-A",
        "run_id": "RUN-A",
        "object_id": "OBJ-A",
        "decision": "ALLOWED",
        "reason_codes": (),
        "review_id": "REVIEW-A",
        "canonical_record_id": "CER-A",
        "released_result_id": "RESULT-A",
        "release_policy_version": "phase4-release-eligibility/v1",
        "review_policy_version": "phase4-independent-financial-review/v1",
        "proof_policy_id": "PROOF-POLICY-A",
        "proof_policy_hash": hashes.proof_policy_hash,
        "material_output_policy_version": "phase4-full-material-output/v1",
        "material_output_manifest_hash": hashes.material_output_manifest_hash,
        "artifact_policy_version": "phase4-html-required-pdf-optional/v1",
        "artifact_manifest_hash": hashes.artifact_manifest_hash,
        "review_input_snapshot_hash": review_input_hash,
        "closure_hash": hashes.closure_hash,
        "evaluated_at": NOW - timedelta(seconds=1),
        "released_at": NOW,
    }
    return replace(candidate, validation=(validation,))


def _object_record() -> dict[str, object]:
    return {
        "object_id": "OBJ-A",
        "symbol": "ACME",
        "company_name": "Acme Corp",
        "object_type": "public_company",
        "exchange": "NASDAQ",
        "sector": None,
        "currency": "USD",
        "identity_version": 1,
    }


def _rehash_candidate(
    candidate: EligibleReleasedObjectCandidate,
) -> EligibleReleasedObjectCandidate:
    hashes = compute_release_validation_hashes(candidate, validation_id="VALIDATION-A")
    validation = {
        **candidate.validation[0],
        "proof_policy_hash": hashes.proof_policy_hash,
        "material_output_manifest_hash": hashes.material_output_manifest_hash,
        "artifact_manifest_hash": hashes.artifact_manifest_hash,
        "closure_hash": hashes.closure_hash,
    }
    return replace(candidate, validation=(validation,))


def _assert_release_candidate_rejected(
    candidate: EligibleReleasedObjectCandidate,
    match: str,
) -> None:
    with pytest.raises(ProjectionIntegrityError, match=match):
        build_released_object_core(
            projection_revision=3,
            generated_at=NOW,
            research_object=_object_record(),
            runs=(candidate.run,),
            eligible_releases=(_rehash_candidate(candidate),),
            authoritative_run_ids=("RUN-A",),
            release_ineligibility={},
        )


def test_release_rejects_cross_run_metric_and_review_subject() -> None:
    candidate = _candidate()
    foreign_metric = candidate.result.metrics[0].model_copy(update={"run_id": "RUN-B"})
    _assert_release_candidate_rejected(
        replace(
            candidate,
            result=candidate.result.model_copy(
                update={"metrics": (foreign_metric, *candidate.result.metrics[1:])}
            ),
        ),
        "exact authoritative records",
    )

    check = candidate.review.checks[0]
    foreign_subject = check.subjects[0].model_copy(
        update={"subject_id": "RUN-B", "run_id": "RUN-B"}
    )
    foreign_review = candidate.review.model_copy(
        update={"checks": (check.model_copy(update={"subjects": (foreign_subject,)}),)}
    )
    _assert_release_candidate_rejected(
        replace(candidate, review=foreign_review),
        "exact authoritative preimage",
    )


def test_release_rejects_execution_substitution_and_torn_watermarks() -> None:
    candidate = _candidate()
    _assert_release_candidate_rejected(
        replace(
            candidate,
            execution=candidate.execution.model_copy(update={"object_snapshot_ref": "OBJ-B"}),
        ),
        "identity/gate closure",
    )
    _assert_release_candidate_rejected(
        replace(
            candidate,
            execution=candidate.execution.model_copy(
                update={"evidence_refs": (), "review_refs": (), "proof_refs": ()}
            ),
        ),
        "exact authoritative record",
    )
    _assert_release_candidate_rejected(
        replace(
            candidate,
            review=candidate.review.model_copy(update={"projection_revision": 1}),
            execution=candidate.execution.model_copy(update={"projection_revision": 999}),
        ),
        "identity/gate closure",
    )


def test_release_rejects_self_asserted_review_and_proof_authority() -> None:
    candidate = _candidate()
    run_subject = candidate.review.checks[0].subjects[0]
    foreign_evidence_subject = run_subject.model_copy(
        update={"subject_type": "EVIDENCE", "subject_id": "EVIDENCE-FOREIGN"}
    )
    foreign_calculation_subject = run_subject.model_copy(
        update={"subject_type": "CALCULATION", "subject_id": "CALC-FOREIGN"}
    )
    check = candidate.review.checks[0].model_copy(
        update={
            "subjects": (
                run_subject,
                foreign_evidence_subject,
                foreign_calculation_subject,
            )
        }
    )
    asserted_review = candidate.review.model_copy(
        update={
            "reviewed_evidence_refs": (
                *candidate.review.reviewed_evidence_refs,
                "EVIDENCE-FOREIGN",
            ),
            "reviewed_calculation_refs": (
                *candidate.review.reviewed_calculation_refs,
                "CALC-FOREIGN",
            ),
            "checks": (check,),
        }
    )
    asserted_execution = candidate.execution.model_copy(
        update={
            "evidence_refs": (*candidate.execution.evidence_refs, "EVIDENCE-FOREIGN"),
            "calculation_refs": (
                *candidate.execution.calculation_refs,
                "CALC-FOREIGN",
            ),
        }
    )
    _assert_release_candidate_rejected(
        replace(candidate, review=asserted_review, execution=asserted_execution),
        "exact authoritative preimage",
    )

    metric = candidate.result.metrics[1]
    forged_metric = metric.model_copy(
        update={
            "proof": metric.proof.model_copy(
                update={
                    "requirement": "MUST_PROVE",
                    "status": "VERIFIED",
                    "proof_refs": ("PROOF-FORGED",),
                }
            )
        }
    )
    forged_result = candidate.result.model_copy(
        update={
            "metrics": (
                candidate.result.metrics[0],
                forged_metric,
                *candidate.result.metrics[2:],
            )
        }
    )
    forged_proof = candidate.proof.model_copy(update={"proof_refs": ("PROOF-0", "PROOF-FORGED")})
    forged_execution = candidate.execution.model_copy(
        update={"proof_refs": ("PROOF-0", "PROOF-FORGED")}
    )
    _assert_release_candidate_rejected(
        replace(
            candidate,
            result=forged_result,
            proof=forged_proof,
            execution=forged_execution,
        ),
        "exact authoritative records",
    )


def test_release_rejects_missing_source_and_duplicate_proof_summary_refs() -> None:
    candidate = _candidate()
    _assert_release_candidate_rejected(
        replace(candidate, source=None),  # type: ignore[arg-type]
        "lacks its exact retained",
    )
    _assert_release_candidate_rejected(
        replace(
            candidate,
            proof=candidate.proof.model_copy(update={"proof_refs": ("PROOF-0", "PROOF-0")}),
        ),
        "repeats a Proof identity",
    )


def test_release_rejects_self_asserted_artifact_metadata_and_tampered_bytes() -> None:
    candidate = _candidate()
    html = candidate.artifacts.representations[0]
    asserted_html = html.model_copy(update={"sha256": SHA_B})
    asserted_group = candidate.artifacts.model_copy(
        update={
            "representations": (
                asserted_html,
                candidate.artifacts.representations[1],
            )
        }
    )
    _assert_release_candidate_rejected(
        replace(candidate, artifacts=asserted_group),
        "exact authoritative records",
    )

    tampered_source = replace(
        candidate.source,
        html_payload=candidate.source.html_payload + b"tampered",
    )
    _assert_release_candidate_rejected(
        replace(candidate, source=tampered_source),
        "artifact bytes fail exact content integrity",
    )


def test_release_rejects_non_verified_proof_and_nonreportable_disposition() -> None:
    candidate = _candidate()
    metric = candidate.result.metrics[0]
    pending_metric = metric.model_copy(
        update={"proof": metric.proof.model_copy(update={"status": "PENDING"})}
    )
    _assert_release_candidate_rejected(
        replace(
            candidate,
            result=candidate.result.model_copy(
                update={"metrics": (pending_metric, *candidate.result.metrics[1:])}
            ),
        ),
        "exact authoritative records",
    )

    disposition = {
        **candidate.result.material_calculation_dispositions[0],
        "status": "BLOCKED",
        "reason": "REVIEW_BLOCKED",
    }
    _assert_release_candidate_rejected(
        replace(
            candidate,
            result=candidate.result.model_copy(
                update={
                    "material_calculation_dispositions": (
                        disposition,
                        *candidate.result.material_calculation_dispositions[1:],
                    )
                }
            ),
        ),
        "exact authoritative records",
    )


def test_release_rejects_duplicate_calculation_and_unavailable_closure() -> None:
    candidate = _candidate()
    duplicate = candidate.result.metrics[1].model_copy(
        update={"calculation_id": candidate.result.metrics[0].calculation_id}
    )
    _assert_release_candidate_rejected(
        replace(
            candidate,
            result=candidate.result.model_copy(
                update={
                    "metrics": (
                        candidate.result.metrics[0],
                        duplicate,
                        *candidate.result.metrics[2:],
                    )
                }
            ),
        ),
        "exact authoritative records",
    )

    unavailable = AvailabilityV1.unavailable(
        AvailabilityStatus.NOT_RELEASED,
        "RESULT_NOT_RELEASED",
    )
    _assert_release_candidate_rejected(
        replace(
            candidate,
            result=candidate.result.model_copy(update={"availability": unavailable}),
        ),
        "exact authoritative records",
    )
    _assert_release_candidate_rejected(
        replace(
            candidate,
            execution=candidate.execution.model_copy(update={"availability": unavailable}),
        ),
        "exact authoritative record",
    )


def test_release_rejects_open_review_block_and_missing_evidence_review() -> None:
    candidate = _candidate()
    check = candidate.review.checks[0]
    blocked_review = candidate.review.model_copy(
        update={
            "checks": (check.model_copy(update={"status": "BLOCK", "exception_state": "OPEN"}),)
        }
    )
    _assert_release_candidate_rejected(
        replace(candidate, review=blocked_review),
        "exact authoritative preimage",
    )

    incomplete_review = candidate.review.model_copy(
        update={"reviewed_evidence_refs": candidate.review.reviewed_evidence_refs[:-1]}
    )
    _assert_release_candidate_rejected(
        replace(candidate, review=incomplete_review),
        "exact authoritative preimage",
    )


def test_released_object_recomputes_every_validation_hash() -> None:
    candidate = _candidate()
    projection = build_released_object_core(
        projection_revision=3,
        generated_at=NOW,
        research_object=_object_record(),
        runs=(candidate.run,),
        eligible_releases=(candidate,),
        authoritative_run_ids=("RUN-A",),
        release_ineligibility={},
    )
    assert projection.latest_released_run_id == "RUN-A"

    for field_name in (
        "proof_policy_hash",
        "material_output_manifest_hash",
        "artifact_manifest_hash",
        "closure_hash",
    ):
        validation = dict(candidate.validation[0])
        validation[field_name] = SHA_B
        tampered = replace(candidate, validation=(validation,))
        with pytest.raises(ProjectionIntegrityError, match="canonical preimage"):
            build_released_object_core(
                projection_revision=3,
                generated_at=NOW,
                research_object=_object_record(),
                runs=(candidate.run,),
                eligible_releases=(tampered,),
                authoritative_run_ids=("RUN-A",),
                release_ineligibility={},
            )


def test_release_closure_hash_uses_pagination_independent_execution_preimage() -> None:
    candidate = _candidate()
    baseline = compute_release_validation_hashes(
        candidate,
        validation_id="VALIDATION-A",
    )
    page_event = SafeRuntimeActivityV1(
        event_id="EVENT-PAGE-A",
        type="release.completed",
        sequence=20,
        timestamp=NOW,
        message_code="RELEASE_COMPLETED",
        status="RELEASED",
    )
    another_page = replace(
        candidate,
        execution=candidate.execution.model_copy(
            update={
                "events": (page_event,),
                "next_cursor": "opaque-page-cursor",
            }
        ),
    )
    paged = compute_release_validation_hashes(
        another_page,
        validation_id="VALIDATION-A",
    )

    assert paged == baseline

    changed_execution = replace(
        candidate,
        execution=candidate.execution.model_copy(
            update={"token_usage": candidate.execution.token_usage + 1}
        ),
    )
    changed = compute_release_validation_hashes(
        changed_execution,
        validation_id="VALIDATION-A",
    )
    assert changed.closure_hash != baseline.closure_hash
    assert changed.proof_policy_hash == baseline.proof_policy_hash
    assert changed.material_output_manifest_hash == baseline.material_output_manifest_hash
    assert changed.artifact_manifest_hash == baseline.artifact_manifest_hash


def test_released_object_requires_observable_validation_and_run_cardinality() -> None:
    candidate = _candidate()
    singular = replace(candidate, validation=candidate.validation[0])  # type: ignore[arg-type]
    with pytest.raises(ProjectionIntegrityError, match="must be a sequence"):
        build_released_object_core(
            projection_revision=3,
            generated_at=NOW,
            research_object=_object_record(),
            runs=(candidate.run,),
            eligible_releases=(singular,),
            authoritative_run_ids=("RUN-A",),
            release_ineligibility={},
        )

    duplicate = replace(candidate, validation=candidate.validation * 2)
    with pytest.raises(ProjectionIntegrityError, match="duplicate ReleaseValidation"):
        build_released_object_core(
            projection_revision=3,
            generated_at=NOW,
            research_object=_object_record(),
            runs=(candidate.run,),
            eligible_releases=(duplicate,),
            authoritative_run_ids=("RUN-A",),
            release_ineligibility={},
        )

    blocked = {
        **candidate.validation[0],
        "validation_id": "VALIDATION-BLOCKED-A",
        "decision": "BLOCKED",
        "reason_codes": ("EARLIER_REVIEW_BLOCK",),
        "released_at": None,
    }
    with_history = replace(candidate, validation=(blocked, candidate.validation[0]))
    with pytest.raises(
        ProjectionIntegrityError,
        match="BLOCKED ReleaseValidation preimage",
    ):
        build_released_object_core(
            projection_revision=3,
            generated_at=NOW,
            research_object=_object_record(),
            runs=(candidate.run,),
            eligible_releases=(with_history,),
            authoritative_run_ids=("RUN-A",),
            release_ineligibility={},
        )

    malformed_blocked = {**blocked, "closure_hash": "sha256:not-a-digest"}
    with pytest.raises(ProjectionIntegrityError, match="sha256"):
        build_released_object_core(
            projection_revision=3,
            generated_at=NOW,
            research_object=_object_record(),
            runs=(candidate.run,),
            eligible_releases=(
                replace(
                    candidate,
                    validation=(malformed_blocked, candidate.validation[0]),
                ),
            ),
            authoritative_run_ids=("RUN-A",),
            release_ineligibility={},
        )

    with pytest.raises(ProjectionIntegrityError, match="authoritative full-Run"):
        build_released_object_core(
            projection_revision=3,
            generated_at=NOW,
            research_object=_object_record(),
            runs=(candidate.run,),
            eligible_releases=(candidate,),
        )

    newer = candidate.run.model_copy(
        update={"run_id": "RUN-B", "updated_at": NOW + timedelta(minutes=1)}
    )
    with pytest.raises(ProjectionIntegrityError, match="eligibility assessment"):
        build_released_object_core(
            projection_revision=3,
            generated_at=NOW,
            research_object=_object_record(),
            runs=(candidate.run, newer),
            eligible_releases=(candidate,),
            authoritative_run_ids=("RUN-A", "RUN-B"),
            release_ineligibility={},
        )

    selected = build_released_object_core(
        projection_revision=3,
        generated_at=NOW,
        research_object=_object_record(),
        runs=(candidate.run, newer),
        eligible_releases=(candidate,),
        authoritative_run_ids=("RUN-A", "RUN-B"),
        release_ineligibility={"RUN-B": "HTML_UNAVAILABLE"},
    )
    assert selected.latest_released_run_id == "RUN-A"


def test_atomic_release_projection_requires_the_same_exact_validation() -> None:
    candidate = _candidate()
    values = {
        "status": project_run_status("RELEASED"),
        "object_id": "OBJ-A",
        "run_id": "RUN-A",
        "review": candidate.review,
        "result": candidate.result,
        "artifacts": candidate.artifacts,
        "proof": candidate.proof,
        "execution": candidate.execution,
        "source": candidate.source,
    }
    _validate_atomic_release_validation(validations=candidate.validation, **values)

    pending_pdf = ReportArtifactRepresentationV1(
        format="PDF",
        required_for_release=False,
        content_type="application/pdf",
        availability=AvailabilityV1.unavailable(
            AvailabilityStatus.PENDING,
            "PDF_GENERATION_PENDING",
            retryable=True,
        ),
        artifact_id=None,
        safe_failure_code=None,
        generation_attempt_id="ATTEMPT-PDF-A",
        generation_attempt_count=1,
        sha256=None,
        size_bytes=None,
        renderer=RendererIdentityV1(renderer_id="renderer", renderer_version="v1"),
        generated_at=None,
        authorized_ref=None,
    )
    pending_artifacts = ReportArtifactGroupV1.model_validate(
        {
            **candidate.artifacts.model_dump(mode="python"),
            "representations": (
                candidate.artifacts.representations[0],
                pending_pdf,
            ),
        }
    )
    pending_candidate = replace(candidate, artifacts=pending_artifacts)
    pending_hashes = compute_release_validation_hashes(
        pending_candidate,
        validation_id="VALIDATION-A",
    )
    pending_validation = {
        **candidate.validation[0],
        "proof_policy_hash": pending_hashes.proof_policy_hash,
        "material_output_manifest_hash": pending_hashes.material_output_manifest_hash,
        "artifact_manifest_hash": pending_hashes.artifact_manifest_hash,
        "closure_hash": pending_hashes.closure_hash,
    }
    with pytest.raises(ProjectionIntegrityError, match="artifact slot cannot remain PENDING"):
        _validate_atomic_release_validation(
            validations=(pending_validation,),
            **{**values, "artifacts": pending_artifacts},
        )

    blocked = {
        **candidate.validation[0],
        "validation_id": "VALIDATION-BLOCKED-A",
        "decision": "BLOCKED",
        "reason_codes": ("EARLIER_REVIEW_BLOCK",),
        "released_at": None,
    }
    with pytest.raises(
        ProjectionIntegrityError,
        match="BLOCKED ReleaseValidation preimage",
    ):
        _validate_atomic_release_validation(
            validations=(blocked, candidate.validation[0]),
            **values,
        )

    with pytest.raises(
        ProjectionIntegrityError,
        match="BLOCKED ReleaseValidation preimage",
    ):
        _validate_atomic_release_validation(
            status=project_run_status("RUNNING"),
            object_id="OBJ-A",
            run_id="RUN-A",
            validations=(blocked,),
            review=None,
            result=None,
            artifacts=None,
            proof=candidate.proof,
            execution=None,
        )

    with pytest.raises(ProjectionIntegrityError, match="exactly one ALLOWED"):
        _validate_atomic_release_validation(validations=(), **values)

    partial = replace(
        candidate,
        result=candidate.result.model_copy(
            update={
                "metrics": candidate.result.metrics[:-1],
                "claims": candidate.result.claims[:-1],
                "material_calculation_dispositions": (
                    candidate.result.material_calculation_dispositions[:-1]
                ),
            }
        ),
    )
    partial_hashes = compute_release_validation_hashes(
        partial,
        validation_id="VALIDATION-A",
    )
    partial_validation = {
        **partial.validation[0],
        "proof_policy_hash": partial_hashes.proof_policy_hash,
        "material_output_manifest_hash": partial_hashes.material_output_manifest_hash,
        "artifact_manifest_hash": partial_hashes.artifact_manifest_hash,
        "closure_hash": partial_hashes.closure_hash,
    }
    with pytest.raises(ProjectionIntegrityError, match="exact authoritative records"):
        _validate_atomic_release_validation(
            validations=(partial_validation,),
            status=project_run_status("RELEASED"),
            object_id="OBJ-A",
            run_id="RUN-A",
            review=partial.review,
            result=partial.result,
            artifacts=partial.artifacts,
            proof=partial.proof,
            execution=partial.execution,
            source=partial.source,
        )


def _exact_review_input_records() -> dict[str, tuple[object, ...]]:
    evidence = EvidenceRecord(
        evidence_id="EVIDENCE-A",
        run_id="RUN-A",
        object_id="OBJ-A",
        provider="fixture",
        source_locator="fixture://review-input/EVIDENCE-A",
        producer_task_id="TASK-A",
        evidence_category=EvidenceCategory.MARKET,
        retrieved_at=NOW - timedelta(minutes=10),
        period="CURRENT",
        period_basis=FinancialPeriodBasis.CURRENT,
        actuality=FinancialActuality.ACTUAL,
        as_of=date(2026, 9, 5),
        raw_artifact_ref="ARTIFACT-EVIDENCE-A",
        normalized_field="last_price",
        normalized_value="10",
        unit="INDEX",
        snapshot_hash=SHA_A,
        status=EvidenceStatus.ACCEPTED,
        created_at=NOW - timedelta(minutes=10),
    )
    calculation = CalculationRecord(
        calculation_id="CALC-A",
        run_id="RUN-A",
        task_id="TASK-A",
        capability_id="CAPABILITY-A",
        capability_version="v1",
        formula_id="review_fixture_ratio",
        input_evidence_ids=[evidence.evidence_id],
        input_values_snapshot={"last_price": "10"},
        parameters={},
        output_value="10",
        output_unit="RATIO",
        status=CalculationStatus.PASS,
        review_status=ReviewStatus.PASS,
        implementation_hash=SHA_A,
        created_at=NOW - timedelta(minutes=8),
    )
    metric = ReleasedFinancialMetric(
        metric_id="METRIC-A",
        calculation_id=calculation.calculation_id,
        name="Review fixture ratio",
        canonical_value="10",
        canonical_unit=FinancialUnit.RATIO,
        display_value="10x",
        display_unit="x",
        period="CURRENT",
        period_basis=FinancialPeriodBasis.CURRENT,
        actuality=FinancialActuality.ACTUAL,
        as_of=date(2026, 9, 5),
        formula_id=calculation.formula_id,
        capability_id=calculation.capability_id,
        evidence_ids=(evidence.evidence_id,),
    )
    claim = MaterialFinancialClaim(
        claim_id="CLAIM-A",
        run_id="RUN-A",
        claim_type="FINANCIAL_METRIC",
        statement="The review fixture ratio is 10x.",
        metric_id=metric.metric_id,
        value=metric.canonical_value,
        unit=metric.canonical_unit,
        period=metric.period,
        period_basis=metric.period_basis,
        actuality=metric.actuality,
        as_of=metric.as_of,
        calculation_refs=(calculation.calculation_id,),
        evidence_refs=(evidence.evidence_id,),
    )
    decision = ProofPolicyDecision(
        decision_id="PROOF-DECISION-A",
        run_id="RUN-A",
        calculation_id=calculation.calculation_id,
        formula_id=calculation.formula_id,
        requirement=ProofRequirement.NOT_REQUIRED,
        policy_id="PROOF-POLICY-A",
        reason="Review fixture formula does not require a proof.",
        created_at=NOW - timedelta(minutes=7),
    )
    return {
        "evidence_records": (evidence,),
        "calculation_records": (calculation,),
        "metric_records": (metric,),
        "claim_records": (claim,),
        "judgment_records": (),
        "proof_policy_decisions": (decision,),
    }


def _review_with_exact_subjects(*, input_snapshot_hash: str) -> dict[str, object]:
    return {
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
                "check_code": "CORRECTION_VERIFIED",
                "status": "REVIEW",
                "subjects": (
                    {"subject_type": "RUN", "subject_id": "RUN-A", "run_id": "RUN-A"},
                    {"subject_type": "TASK", "subject_id": "TASK-A", "run_id": "RUN-A"},
                    {"subject_type": "PROOF", "subject_id": "PROOF-A", "run_id": "RUN-A"},
                    {
                        "subject_type": "CANONICAL_RECORD",
                        "subject_id": "CER-A",
                        "run_id": "RUN-A",
                    },
                    {
                        "subject_type": "RELEASED_RESULT",
                        "subject_id": "RESULT-A",
                        "run_id": "RUN-A",
                    },
                ),
                "expected": {"status": "RESOLVED"},
                "actual": {"status": "RESOLVED"},
                "exception_state": "RESOLVED",
                "correction_refs": (
                    {
                        "correction_id": "CORRECTION-A",
                        "run_id": "RUN-A",
                        "task_id": "TASK-A",
                        "status": "RESOLVED",
                        "resolved_at": NOW,
                    },
                ),
                "created_at": NOW - timedelta(minutes=2),
                "resolved_at": NOW,
            },
        ),
    }


def _build_exact_subject_review(**updates: object) -> FinancialReviewProjectionV1:
    review_inputs = _exact_review_input_records()
    evidence = review_inputs["evidence_records"]
    calculations = review_inputs["calculation_records"]
    metrics = review_inputs["metric_records"]
    claims = review_inputs["claim_records"]
    judgments = review_inputs["judgment_records"]
    proof_decisions = review_inputs["proof_policy_decisions"]
    input_snapshot_hash = financial_review_input_snapshot_hash(
        run_id="RUN-A",
        run_as_of=date(2026, 9, 5),
        evidence=evidence,  # type: ignore[arg-type]
        calculations=calculations,  # type: ignore[arg-type]
        metrics=metrics,  # type: ignore[arg-type]
        claims=claims,  # type: ignore[arg-type]
        judgments=judgments,  # type: ignore[arg-type]
        proof_requirements={
            item.calculation_id: item.requirement
            for item in proof_decisions
            if isinstance(item, ProofPolicyDecision)
        },
    )
    values: dict[str, object] = {
        "expected_object_id": "OBJ-A",
        "expected_run_id": "RUN-A",
        "projection_revision": 1,
        "projection_sequence": 1,
        "run": {
            "run_id": "RUN-A",
            "research_object_id": "OBJ-A",
            "status": "RELEASED",
            "as_of": date(2026, 9, 5),
        },
        "review": _review_with_exact_subjects(input_snapshot_hash=input_snapshot_hash),
        "canonical_record": {
            "record_id": "CER-A",
            "run_id": "RUN-A",
            "object_snapshot_ref": "OBJ-A",
            "review_refs": ("REVIEW-A",),
        },
        "released_result": {
            "result_id": "RESULT-A",
            "run_id": "RUN-A",
            "canonical_record_id": "CER-A",
        },
        "tasks": ({"task_id": "TASK-A", "run_id": "RUN-A"},),
        "proof_records": ({"proof_id": "PROOF-A", "run_id": "RUN-A"},),
        "correction_records": (
            {
                "correction_id": "CORRECTION-A",
                "run_id": "RUN-A",
                "task_id": "TASK-A",
                "status": "RESOLVED",
                "resolved_at": NOW,
            },
        ),
        **review_inputs,
    }
    values.update(updates)
    return build_financial_review(**values)  # type: ignore[arg-type]


def test_review_subjects_and_corrections_require_exact_retained_records() -> None:
    projection = _build_exact_subject_review()
    assert projection.status == "PASS"
    assert projection.checks[0].correction_refs[0].task_id == "TASK-A"

    with pytest.raises(ProjectionIntegrityError, match="exact retained.*Task"):
        _build_exact_subject_review(tasks=None)
    with pytest.raises(ProjectionIntegrityError, match="Correction/Task state"):
        _build_exact_subject_review(
            correction_records=(
                {
                    "correction_id": "CORRECTION-A",
                    "run_id": "RUN-A",
                    "task_id": "TASK-A",
                    "status": "FAILED",
                    "resolved_at": NOW,
                },
            )
        )
