import pytest
from pydantic import ValidationError

from src.domain.capability import (
    CapabilityRequirement,
    ScopedCapabilityRegistration,
)
from src.domain.enums import (
    CapabilityLifecycle,
    CapabilityScope,
    ProofRequirement,
    ProofStatus,
    TaskStatus,
)
from src.domain.proof import ProofInputCommitment, ProofPolicyDecision, ProofRecord
from src.domain.report import CanonicalReportDTO
from src.domain.runtime_event import RuntimeEventType


def test_generated_capability_lifecycle_and_scope_are_frozen() -> None:
    assert CapabilityLifecycle.GAP_DETECTED.value == "GAP_DETECTED"
    assert CapabilityLifecycle.ACTIVE_FOR_SCOPE.value == "ACTIVE_FOR_SCOPE"
    assert CapabilityScope.TASK.value == "TASK"
    assert CapabilityScope.RUN.value == "RUN"
    assert TaskStatus.WAITING_FOR_CAPABILITY.value == "WAITING_FOR_CAPABILITY"
    assert TaskStatus.CAPABILITY_BUILD_FAILED.value == "CAPABILITY_BUILD_FAILED"


def test_task_scoped_registration_requires_task_id() -> None:
    with pytest.raises(ValidationError, match="task_id is required"):
        ScopedCapabilityRegistration(
            registration_id="REG-1",
            generated_capability_ref="GEN-1",
            capability_id="gross_margin",
            capability_version="1",
            scope=CapabilityScope.TASK,
            run_id="RUN-1",
            approved_by="research-lead",
        )


def test_capability_requirement_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CapabilityRequirement(
            requirement_id="REQ-1",
            capability_id="gross_margin",
            purpose="Compute a deterministic margin.",
            input_schema={},
            output_schema={},
            formula_id="gross_margin_v1",
            global_reusable=True,
        )


def test_proof_contract_binds_program_input_and_expected_output() -> None:
    decision = ProofPolicyDecision(
        decision_id="PPD-1",
        run_id="RUN-1",
        calculation_id="CALC-1",
        formula_id="revenue_growth_v1",
        requirement=ProofRequirement.MUST_PROVE,
        policy_id="phase3-acceptance-v1",
        reason="Revenue growth must be proven for this run.",
    )
    commitment = ProofInputCommitment(
        commitment_id="PIC-1",
        run_id="RUN-1",
        calculation_id="CALC-1",
        formula_id="revenue_growth_v1",
        capability_id="finance.revenue_growth",
        implementation_hash="sha256:implementation",
        input_evidence_refs=["EVD-1", "EVD-2"],
        canonical_inputs={"previous_revenue": "100", "current_revenue": "125"},
        input_commitment="sha256:inputs",
        expected_output_commitment="sha256:output",
    )
    proof = ProofRecord(
        proof_id="PROOF-1",
        run_id="RUN-1",
        calculation_id="CALC-1",
        backend="risc0",
        program_id="revenue_growth_v1",
        image_id="IMAGE-1",
        implementation_hash=commitment.implementation_hash,
        input_commitment=commitment.input_commitment,
        status=ProofStatus.REQUIRED_PENDING,
    )

    assert decision.requirement is ProofRequirement.MUST_PROVE
    assert proof.input_commitment == commitment.input_commitment


def test_canonical_report_dto_is_immutable() -> None:
    source = {
        "financial_summary": {"revenue": 130.5},
        "series": [{"year": 2025}],
    }
    report = CanonicalReportDTO(
        canonical_record_id="CAN-1",
        released_result_id="REL-1",
        run_id="RUN-1",
        research_object="NVDA",
        structured_financial_results=source,
        released_claims=[{"claim": "accepted", "evidence_refs": ["EVD-1"]}],
        limitations=["historical only"],
    )
    with pytest.raises(ValidationError):
        report.research_object = "AMD"
    with pytest.raises(TypeError):
        report.structured_financial_results["financial_summary"]["revenue"] = 1
    with pytest.raises(AttributeError):
        report.structured_financial_results["series"].append({"year": 2026})
    with pytest.raises(AttributeError):
        report.released_claims.append({"claim": "mutated"})
    with pytest.raises(TypeError):
        report.released_claims[0]["evidence_refs"][0] = "EVD-OTHER"
    source["financial_summary"]["revenue"] = 1
    assert report.structured_financial_results["financial_summary"]["revenue"] == 130.5

    payload = report.model_dump(mode="json")
    assert isinstance(payload["structured_financial_results"], dict)
    assert isinstance(payload["released_claims"], list)
    assert CanonicalReportDTO.model_validate_json(report.model_dump_json()) == report

    updated = report.model_copy(
        update={
            "structured_financial_results": {"nested": {"value": 1}},
            "limitations": ["updated"],
        }
    )
    with pytest.raises(TypeError):
        updated.structured_financial_results["nested"]["value"] = 2
    with pytest.raises(AttributeError):
        updated.limitations.append("mutable")

    with pytest.raises((TypeError, ValidationError)):
        CanonicalReportDTO(
            canonical_record_id="CAN-2",
            released_result_id="REL-2",
            run_id="RUN-2",
            research_object="NVDA",
            structured_financial_results={"mutable": {"not", "json"}},
        )


def test_phase3_runtime_events_are_available() -> None:
    expected = {
        "capability.gap_detected",
        "capability.build_requested",
        "capability.build_started",
        "capability.generated",
        "capability.static_validated",
        "capability.sandbox_started",
        "capability.test_passed",
        "capability.test_failed",
        "capability.financial_validated",
        "capability.approved",
        "capability.registered",
        "capability.build_failed",
        "task.waiting_for_capability",
        "task.resumed",
        "proof.required",
        "proof.started",
        "proof.generated",
        "proof.verified",
        "proof.failed",
    }
    assert expected <= {event.value for event in RuntimeEventType}
