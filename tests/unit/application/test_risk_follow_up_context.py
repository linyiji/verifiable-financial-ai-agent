from datetime import date
from types import SimpleNamespace as NS

import pytest

from src.application.risk_follow_up import build_risk_follow_up_context
from src.domain.agent_output import RiskResearchAgentStructuredOutput
from src.domain.calculation import CalculationRecord
from src.domain.enums import EvidenceStatus


def fixture():
    parent = NS(
        run_id="R", task_type="risk_analysis", task_id="R:risk", task_input_evidence_ids=["E1"]
    )
    child = NS(
        run_id="R",
        parent_task_id="R:risk",
        reason_code="MATERIAL_RISK_FOLLOW_UP",
        goal="Validate the material risk",
    )
    output = NS(
        task_id=parent.task_id,
        run_id="R",
        status="SUCCESS",
        input_refs=["E1"],
        output_id="AO1",
        artifact_sha256="sha256:" + "a" * 64,
        structured_output=RiskResearchAgentStructuredOutput(
            summary="Risk assertion",
            key_findings=["Needs validation"],
            risks=["Unresolved"],
            limitations=[],
            requires_follow_up=True,
        ),
    )
    evidence = NS(evidence_id="E1", status=EvidenceStatus.ACCEPTED, run_id="R", object_id="O")
    aggregate = NS(
        runtime=NS(task=lambda _: parent),
        artifacts=NS(agent_outputs=[output], evidence=[evidence], calculations=[]),
        run=NS(research_object_id="O", as_of=date(2026, 9, 9)),
        goal=NS(goal_id="G", goal_text="Research"),
        scheme=NS(scheme_id="S"),
    )
    return aggregate, child


def test_focused_context_preserves_exact_parent_and_evidence_trace():
    aggregate, child = fixture()
    facts = [{"evidence_id": "E1", "value": 42, "period": "FY2025"}]
    result = build_risk_follow_up_context(aggregate, child, facts)
    assert result["input_refs"] == ["G", "S", "AO1", "E1"]
    assert result["normalized_evidence"] == facts
    focused = result["risk_follow_up"]
    assert focused["parent_risk_artifact_sha256"] == "sha256:" + "a" * 64
    assert focused["relevant_claim_refs"] == []  # No invented claim-level binding.
    assert focused["relevant_evidence_refs"] == ["E1"]
    assert "upstream_agent_outputs" not in result
    assert "supporting_output" not in result


def test_pass_calculation_keeps_formula_value_and_input_lineage():
    aggregate, child = fixture()
    aggregate.artifacts.agent_outputs[0].input_refs.append("C1")
    aggregate.artifacts.calculations.append(
        CalculationRecord(
            calculation_id="C1",
            run_id="R",
            task_id="R:calc",
            capability_id="growth",
            capability_version="1",
            formula_id="growth_v1",
            input_evidence_ids=["E1"],
            input_values_snapshot={"redundant": "body"},
            output_value=42,
            output_unit="percent",
            status="PASS",
        )
    )
    result = build_risk_follow_up_context(aggregate, child, [{"evidence_id": "E1"}])
    assert "C1" in result["input_refs"]
    calculation = result["risk_follow_up"]["calculations"][0]
    assert "E1" in result["input_refs"]
    assert result["risk_follow_up"]["relevant_evidence_refs"] == ["E1"]
    assert "input_evidence_ids" not in calculation  # Canonical record owns per-input lineage.
    assert calculation["output_value"] == 42
    assert calculation["formula_id"] == "growth_v1"
    assert "input_values_snapshot" not in calculation
    aggregate.artifacts.calculations[0].input_evidence_ids.append("MISSING")
    with pytest.raises(ValueError, match="lineage is incomplete"):
        build_risk_follow_up_context(aggregate, child, [])


@pytest.mark.parametrize("defect", ["parent_run", "evidence_run", "unaccepted", "foreign_fact"])
def test_context_rejects_unbound_evidence(defect):
    aggregate, child = fixture()
    facts = [{"evidence_id": "E1"}]
    if defect == "parent_run":
        aggregate.runtime.task(None).run_id = "OTHER"
    elif defect == "evidence_run":
        aggregate.artifacts.evidence[0].run_id = "OTHER"
    elif defect == "unaccepted":
        aggregate.artifacts.evidence[0].status = EvidenceStatus.REJECTED
    else:
        facts = [{"evidence_id": "FOREIGN"}]
    with pytest.raises(ValueError):
        build_risk_follow_up_context(aggregate, child, facts)
