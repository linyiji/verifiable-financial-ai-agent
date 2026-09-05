from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, field_validator, model_validator

from src.domain.base import DomainModel, JsonObject
from src.domain.capability import (
    Capability,
    CapabilityBuildRecord,
    CapabilityGapRecord,
    CapabilityRequirement,
    CapabilityValidationRecord,
    GeneratedCapabilityArtifactRecord,
    GeneratedCapabilityRecord,
    SandboxExecutionRecord,
    ScopedCapabilityRegistration,
)
from src.domain.enums import CapabilityLifecycle, CapabilityScope


class SpecialistCapabilityRequest(DomainModel):
    """The only capability-build message a Specialist is allowed to create.

    Approval and registration fields are intentionally absent.  ``extra=forbid``
    inherited from ``DomainModel`` prevents a caller from smuggling either into
    the request.
    """

    run_id: str
    task_id: str
    skill_id: str
    requested_by: str
    requester_role: Literal["SPECIALIST"] = "SPECIALIST"
    requirement: CapabilityRequirement
    scope: CapabilityScope = CapabilityScope.TASK


class ResearchLeadCapabilityApproval(DomainModel):
    decision_id: str
    run_id: str
    task_id: str
    gap_id: str
    phase: Literal["SPEC", "ACTIVATION"]
    authority_role: Literal["RESEARCH_LEAD"] = "RESEARCH_LEAD"
    approved: bool
    approved_by: str
    reason_code: str
    summary: str


class CapabilityBuildRequest(DomainModel):
    build_id: str
    gap: CapabilityGapRecord
    approval: ResearchLeadCapabilityApproval
    attempt: int = Field(ge=1)
    max_attempts: int = Field(ge=1)

    @model_validator(mode="after")
    def require_matching_spec_approval(self) -> CapabilityBuildRequest:
        if self.approval.phase != "SPEC" or not self.approval.approved:
            raise ValueError("an approved Research Lead SPEC decision is required")
        if (
            self.approval.run_id != self.gap.run_id
            or self.approval.task_id != self.gap.task_id
            or self.approval.gap_id != self.gap.gap_id
        ):
            raise ValueError("build approval and capability gap identifiers must match")
        if self.attempt > self.max_attempts:
            raise ValueError("attempt cannot exceed max_attempts")
        return self


class CodeBuilderOutput(DomainModel):
    """Strict structured output accepted from the selected governed planner route."""

    capability_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    input_schema: JsonObject
    output_schema: JsonObject
    formula_id: str = Field(min_length=1)
    formula_description: str = Field(min_length=1)
    source_code: str = Field(min_length=1)
    unit_tests: str = Field(min_length=1)
    financial_invariants: list[str]
    allowed_imports: list[str]

    @field_validator(
        "capability_id",
        "version",
        "purpose",
        "formula_id",
        "formula_description",
        "source_code",
        "unit_tests",
    )
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text fields must not be blank")
        return value

    @field_validator("allowed_imports", "financial_invariants")
    @classmethod
    def reject_duplicate_list_values(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("list values must not be blank")
        if len(values) != len(set(values)):
            raise ValueError("list values must be unique")
        return values


class CodeBuilderSchemaField(DomainModel):
    """Strict provider-wire representation for one approved schema field."""

    name: str = Field(min_length=1)
    type: str = Field(min_length=1)

    @field_validator("name", "type")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("schema field values must not be blank")
        return value


class CodeBuilderProviderOutput(CodeBuilderOutput):
    """Strict JSON-schema wire model adapted back to the owned domain contract.

    OpenAI-compatible strict structured-output routes reject free-form object
    schemas.  The approved input/output mappings therefore cross the provider
    boundary as deterministic name/type arrays and are restored before any
    validation, hashing, persistence, or execution.
    """

    input_schema: list[CodeBuilderSchemaField]
    output_schema: list[CodeBuilderSchemaField]

    @field_validator("input_schema", "output_schema")
    @classmethod
    def reject_duplicate_schema_fields(
        cls, values: list[CodeBuilderSchemaField]
    ) -> list[CodeBuilderSchemaField]:
        names = [item.name for item in values]
        if len(names) != len(set(names)):
            raise ValueError("schema field names must be unique")
        return values

    def to_domain(self) -> CodeBuilderOutput:
        return CodeBuilderOutput(
            capability_id=self.capability_id,
            version=self.version,
            purpose=self.purpose,
            input_schema={item.name: item.type for item in self.input_schema},
            output_schema={item.name: item.type for item in self.output_schema},
            formula_id=self.formula_id,
            formula_description=self.formula_description,
            source_code=self.source_code,
            unit_tests=self.unit_tests,
            financial_invariants=self.financial_invariants,
            allowed_imports=self.allowed_imports,
        )


@dataclass(frozen=True, slots=True)
class GeneratedCapabilityCandidate:
    build_id: str
    output: CodeBuilderOutput
    implementation_hash: str
    provider: str
    requested_model: str
    actual_model: str
    attempted_models: tuple[str, ...]
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    spec_bytes: bytes | None = None
    spec_sha256: str | None = None
    compiler_id: str | None = None
    compiler_version: str | None = None
    compiler_runtime_policy: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationHandoff:
    """U2/U3 result consumed by U1; it does not implement validation itself."""

    validation: CapabilityValidationRecord
    sandbox_execution: SandboxExecutionRecord
    capability: Capability

    def assert_ready_for_task_approval(self, candidate: GeneratedCapabilityCandidate) -> None:
        record = self.validation
        if record.build_id != candidate.build_id:
            raise ValueError("validation belongs to a different build")
        if record.implementation_hash != candidate.implementation_hash:
            raise ValueError("validation implementation hash does not match generated source")
        if self.sandbox_execution.build_id != candidate.build_id:
            raise ValueError("sandbox execution belongs to a different build")
        if self.sandbox_execution.implementation_hash != candidate.implementation_hash:
            raise ValueError("sandbox implementation hash does not match generated source")
        if not self.sandbox_execution.passed:
            raise ValueError("sandbox execution did not pass")
        required_checks = (
            record.static_validation_passed,
            record.syntax_compile_passed,
            record.unit_tests_passed,
            record.edge_cases_passed,
            record.financial_invariants_passed,
            record.deterministic_double_run_passed,
            record.output_schema_passed,
            record.unit_validation_passed,
            record.financial_validation_passed,
        )
        if not all(required_checks):
            raise ValueError("generated capability validation is incomplete")
        if record.lifecycle is not CapabilityLifecycle.FINANCIAL_VALIDATED:
            raise ValueError("financial validation lifecycle is required before task approval")
        definition = self.capability.definition
        if definition.capability_id != candidate.output.capability_id:
            raise ValueError("validated capability id does not match generated output")
        if definition.version != candidate.output.version:
            raise ValueError("validated capability version does not match generated output")


@dataclass(frozen=True, slots=True)
class CapabilityOrchestrationResult:
    gap: CapabilityGapRecord
    build_records: tuple[CapabilityBuildRecord, ...]
    generated: GeneratedCapabilityRecord
    artifact_retention: GeneratedCapabilityArtifactRecord
    validation: CapabilityValidationRecord
    sandbox_execution: SandboxExecutionRecord
    registration: ScopedCapabilityRegistration
    capability: Capability
