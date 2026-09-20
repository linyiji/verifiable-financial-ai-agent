"""Focused child context, retaining parent-level provenance without replaying ancestors."""

from pydantic import Field

from src.domain.agent_output import StandardResearchAgentStructuredOutput
from src.domain.base import DomainModel, JsonObject
from src.domain.enums import CalculationStatus


class RiskFollowUpContext(DomainModel):
    follow_up_reason: str
    material_risk_question: str
    parent_risk_output_ref: str
    parent_risk_artifact_sha256: str
    parent_risk_output: JsonObject
    relevant_claim_refs: list[str] = Field(default_factory=list)
    relevant_evidence_refs: list[str]
    relevant_calculation_refs: list[str]
    current_as_of: str
    required_output_schema: JsonObject
    calculations: list[JsonObject]
    evidence_rule: str = (
        "Parent narratives are assertions to validate, not independent evidence. "
        "Only supplied accepted facts and completed calculations support new conclusions. "
        "References without supplied facts preserve audit lineage, not additional knowledge. "
        "Disclose any unresolved evidence gap; never reconstruct missing facts."
    )


def build_risk_follow_up_context(aggregate, task, normalized_evidence):
    parent = aggregate.runtime.task(task.parent_task_id)
    if parent.run_id != task.run_id or parent.task_type != "risk_analysis":
        raise ValueError("Follow-up requires an exact-Run Risk parent")
    outputs = [
        output
        for output in aggregate.artifacts.agent_outputs
        if output.task_id == parent.task_id
        and output.run_id == task.run_id
        and output.status == "SUCCESS"
        and output.structured_output is not None
    ]
    if len(outputs) != 1:
        raise ValueError("Follow-up requires one successful parent Risk output")
    output = outputs[0]
    parent_refs = set(output.input_refs)
    selected_refs = {item["evidence_id"] for item in normalized_evidence}
    permitted_refs = set(parent.task_input_evidence_ids)
    if not selected_refs.issubset(permitted_refs):
        raise ValueError("Follow-up evidence is outside parent scope")
    parent_refs.update(selected_refs)
    evidence_refs = [
        item.evidence_id
        for item in aggregate.artifacts.evidence
        if item.evidence_id in parent_refs
        and item.status.value == "ACCEPTED"
        and item.run_id == task.run_id
        and item.object_id == aggregate.run.research_object_id
    ]
    calculations = [
        item
        for item in aggregate.artifacts.calculations
        if item.calculation_id in parent_refs
        and item.run_id == task.run_id
        and item.status is CalculationStatus.PASS
    ]
    relevant = set(evidence_refs)
    if not selected_refs.issubset(relevant):
        raise ValueError("Follow-up evidence must be accepted in the exact Run and Object")
    if any(not set(item.input_evidence_ids).issubset(relevant) for item in calculations):
        raise ValueError("Follow-up calculation evidence lineage is incomplete")
    value = RiskFollowUpContext(
        follow_up_reason=task.reason_code or "MATERIAL_RISK_FOLLOW_UP",
        material_risk_question=task.goal,
        parent_risk_output_ref=output.output_id,
        parent_risk_artifact_sha256=output.artifact_sha256,
        parent_risk_output=output.structured_output.model_dump(mode="json"),
        relevant_evidence_refs=evidence_refs,
        relevant_calculation_refs=[item.calculation_id for item in calculations],
        current_as_of=aggregate.run.as_of.isoformat(),
        required_output_schema=StandardResearchAgentStructuredOutput.model_json_schema(),
        calculations=[
            {
                key: item.model_dump(mode="json")[key]
                for key in (
                    "calculation_id",
                    "capability_id",
                    "formula_id",
                    "output_value",
                    "output_unit",
                    "status",
                )
            }
            for item in calculations
        ],
    )
    return {
        "research_object_id": aggregate.run.research_object_id,
        "goal_id": aggregate.goal.goal_id,
        "scheme_id": aggregate.scheme.scheme_id,
        "as_of": aggregate.run.as_of.isoformat(),
        "research_goal": aggregate.goal.goal_text,
        "normalized_evidence": normalized_evidence,
        "risk_follow_up": value.model_dump(mode="json"),
        "input_refs": list(
            dict.fromkeys(
                [
                    aggregate.goal.goal_id,
                    aggregate.scheme.scheme_id,
                    output.output_id,
                    *evidence_refs,
                    *value.relevant_calculation_refs,
                ]
            )
        ),
    }
