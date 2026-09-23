"""Frozen minimal Risk identities. No implicit opt-in or global conflict authority."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from src.domain.agent_output import RiskResearchAgentStructuredOutputMinimalV1
from src.domain.node_binding import (
    BindingDenied,
    BindingReference,
    BindingValue,
    GraphIdentity,
    canonical_value,
    digest,
)

PROFILE = "risk_semantic_outcome_minimal_v1"
SCHEMA = "risk_analysis_research_output_minimal_v1"
POLICY = {
    "profile": PROFILE, "schema": SCHEMA, "admission": "risk_admission_minimal_v1",
    "dependency": "risk_output_dependency_minimal_v1",
    "guard": "risk_input_consistency_guard_v1",
    "max_materials": 500, "max_pairs": 124750, "max_obligations": 500,
    "required_comparisons": [],
}


def freeze_contract(tasks):
    risks = [t for t in tasks if t.task_type == "risk_analysis"]
    if len(risks) != 1 or risks[0].output_requirements is None:
        raise BindingDenied("RISK_REQUIREMENTS_REQUIRED")
    task = risks[0]
    requirements = canonical_value(task.output_requirements)
    refs = sorted(set(requirements["hard_required"] + requirements["supporting"]
                      + requirements["enrichment"]
                      + [r for group in requirements["any_of"] for r in group]))
    if len(refs) > POLICY["max_obligations"]:
        raise BindingDenied("RISK_REQUIREMENTS_BOUND_EXCEEDED")
    value = {"policy": POLICY, "schema_digest": digest(
        RiskResearchAgentStructuredOutputMinimalV1.model_json_schema(), "risk-schema/v1"),
        "task_id": task.task_id, "requirements": requirements, "obligation_refs": refs}
    return {**value, "contract_digest": digest(value, "risk-minimal-contract/v1")}


def validate_contract(value):
    if set(value) != {"policy", "schema_digest", "task_id", "requirements", "obligation_refs",
                      "contract_digest"} or value["policy"] != POLICY:
        raise BindingDenied("RISK_CONTRACT_VERSION_REJECTED")
    from src.domain.output_dependency import OutputRequirements

    requirements = OutputRequirements.model_validate(value["requirements"])
    refs = sorted(set(requirements.hard_required + requirements.supporting + requirements.enrichment
                      + [r for group in requirements.any_of for r in group]))
    if value["obligation_refs"] != refs or len(refs) > POLICY["max_obligations"]:
        raise BindingDenied("RISK_REQUIREMENTS_MISMATCH")
    expected = digest(RiskResearchAgentStructuredOutputMinimalV1.model_json_schema(),
                      "risk-schema/v1")
    if value["schema_digest"] != expected or value["contract_digest"] != digest(
        {k: v for k, v in value.items() if k != "contract_digest"}, "risk-minimal-contract/v1"
    ):
        raise BindingDenied("RISK_CONTRACT_DIGEST_REJECTED")
    return value


def contract_for(aggregate):
    from src.application.repository import confirmed_risk_authority

    confirmed_risk_authority(aggregate)
    return _contract_for_validated(aggregate)


def _contract_for_validated(aggregate):
    # Internal synchronous continuation only; public callers enter contract_for.
    root = aggregate.node_binding
    if root is None or root.execution_snapshot is None:
        return None
    value = root.execution_snapshot["scenario"].get("risk_semantic_contract")
    return validate_contract(value) if value is not None else None


def active_contract():
    from src.application.repository import node_invocation

    admission = node_invocation.get()
    value = admission.policy_refs.get("risk_semantic_contract") if admission else None
    return validate_contract(value) if value is not None else None


# Confirmation receipt values contain only frozen scalar/frozen-model fields.

Digest = Annotated[str, Field(strict=True, pattern=r"^sha256:[0-9a-f]{64}$")]
Identity = Annotated[str, Field(strict=True, min_length=1)]
RECEIPT_SCHEMA = "confirmed-risk-semantic-binding/v1"
LEGACY_VERSION = "legacy-risk-projection/v1"


class ConfirmedRiskSemanticBindingV1(BindingValue):
    schema_version: Literal["confirmed-risk-semantic-binding/v1"]
    run_id: Identity
    object_id: Identity
    goal_id: Identity
    goal_hash: Digest
    scheme_id: Identity
    scheme_hash: Digest
    planned_graph_id: Identity
    graph_identity: GraphIdentity
    risk_semantic_mode: Literal["D01_V1", "LEGACY"]
    risk_semantic_contract_version: Identity
    risk_semantic_contract_digest: Digest
    scenario_profile_digest: Digest
    execution_profile_snapshot_digest: Digest
    execution_snapshot_digest: Digest
    confirmation_binding_reference: BindingReference
    confirmed_at: str
    binding_digest: Digest

    @model_validator(mode="before")
    @classmethod
    def closed_nested_identity(cls, value):
        if not isinstance(value, dict):
            raise ValueError("receipt must be reparsed from a closed object")
        for field, keys in (
            ("graph_identity", {"run_id", "graph_id", "version", "semantic_hash"}),
            ("confirmation_binding_reference",
             {"schema_version", "run_id", "binding_revision", "binding_hash"}),
        ):
            nested = value.get(field)
            if isinstance(nested, BindingValue):
                nested = nested.model_dump()
            if not isinstance(nested, dict) or set(nested) != keys:
                raise ValueError("missing/unknown nested confirmation identity")
            number = "version" if field == "graph_identity" else "binding_revision"
            if type(nested[number]) is not int:
                raise ValueError("non-integer confirmation identity")
            hash_key = "semantic_hash" if field == "graph_identity" else "binding_hash"
            import re

            if not isinstance(nested[hash_key], str) or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", nested[hash_key]
            ):
                raise ValueError("noncanonical confirmation identity digest")
        return value

    @field_validator("confirmed_at")
    @classmethod
    def canonical_time(cls, value):
        instant = datetime.fromisoformat(value)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("confirmation timestamp must be aware")
        if instant.astimezone(UTC).isoformat() != value:
            raise ValueError("confirmation timestamp must be canonical UTC")
        return value

    @model_validator(mode="after")
    def check_digest(self):
        if self.binding_digest != digest(
            self.model_dump(exclude={"binding_digest"}), RECEIPT_SCHEMA
        ):
            raise ValueError("confirmation receipt digest mismatch")
        if self.confirmation_binding_reference.binding_revision != 0:
            raise ValueError("confirmation reference must be revision zero")
        if (self.graph_identity.run_id != self.run_id
                or self.confirmation_binding_reference.run_id != self.run_id):
            raise ValueError("foreign confirmation graph/reference")
        if (self.risk_semantic_mode == "LEGACY" and self.risk_semantic_contract_digest != digest(
            {"risk_semantic_mode": "LEGACY", "risk_semantic_contract": None},
            "confirmed-legacy-risk-semantic/v1"
        )):
            raise ValueError("legacy descriptor digest mismatch")
        expected = PROFILE if self.risk_semantic_mode == "D01_V1" else LEGACY_VERSION
        if self.risk_semantic_contract_version != expected:
            raise ValueError("unknown semantic contract version")
        return self


class ConfirmedRiskAuthority(StrEnum):
    CONFIRMED_D01_V1 = "CONFIRMED_D01_V1"
    CONFIRMED_LEGACY = "CONFIRMED_LEGACY"
    HISTORICAL_PRE_BINDING = "HISTORICAL_PRE_BINDING"
