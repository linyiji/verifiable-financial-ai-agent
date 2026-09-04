from typing import Any, Protocol, runtime_checkable

from pydantic import Field, model_validator

from src.domain.base import JsonObject, TimestampedModel
from src.domain.enums import CapabilityBackend, CapabilityLifecycle, CapabilityScope


class CapabilityDefinition(TimestampedModel):
    capability_id: str
    version: str
    name: str
    category: str
    backend: CapabilityBackend
    input_schema: JsonObject = Field(default_factory=dict)
    output_schema: JsonObject = Field(default_factory=dict)
    deterministic: bool
    proof_eligible: bool = False
    lifecycle: str = "CERTIFIED"
    implementation_ref: str
    owner: str = "system"


class CapabilityContext(TimestampedModel):
    run_id: str
    task_id: str
    accepted_evidence_ids: list[str] = Field(default_factory=list)


class CapabilityRequirement(TimestampedModel):
    requirement_id: str
    capability_id: str
    purpose: str
    input_schema: JsonObject
    output_schema: JsonObject
    formula_id: str
    deterministic: bool = True
    allowed_imports: list[str] = Field(default_factory=list)
    financial_invariants: list[str] = Field(default_factory=list)


class CapabilityGapRecord(TimestampedModel):
    gap_id: str
    run_id: str
    task_id: str
    requirement: CapabilityRequirement
    lifecycle: CapabilityLifecycle = CapabilityLifecycle.GAP_DETECTED
    requested_by: str
    detail: str | None = None


class GeneratedCapabilityRecord(TimestampedModel):
    generated_capability_id: str
    run_id: str
    task_id: str
    gap_id: str
    capability_id: str
    capability_version: str
    formula_id: str
    purpose: str
    input_schema: JsonObject
    output_schema: JsonObject
    formula_description: str
    implementation_hash: str
    source_ref: str
    unit_test_ref: str
    allowed_imports: list[str] = Field(default_factory=list)
    financial_invariants: list[str] = Field(default_factory=list)
    runtime_version: str
    lifecycle: CapabilityLifecycle = CapabilityLifecycle.GENERATED


class CapabilityBuildRecord(TimestampedModel):
    build_id: str
    gap_id: str
    run_id: str
    task_id: str
    requested_by: str
    approved_by: str | None = None
    requested_model: str | None = None
    actual_model: str | None = None
    provider: str | None = None
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=2, ge=1)
    lifecycle: CapabilityLifecycle = CapabilityLifecycle.GAP_DETECTED
    generated_capability_ref: str | None = None
    error_code: str | None = None
    error_detail: str | None = None


class SandboxExecutionRecord(TimestampedModel):
    execution_id: str
    build_id: str
    backend: str
    implementation_hash: str
    runtime_version: str
    input_fixture_hash: str
    network_disabled: bool
    read_only_root: bool
    non_root_user: bool
    resource_limits: JsonObject
    exit_code: int | None = None
    output_hash: str | None = None
    passed: bool = False
    detail: str | None = None


class CapabilityValidationRecord(TimestampedModel):
    validation_id: str
    build_id: str
    implementation_hash: str
    static_validation_passed: bool = False
    syntax_compile_passed: bool = False
    unit_tests_passed: bool = False
    edge_cases_passed: bool = False
    financial_invariants_passed: bool = False
    deterministic_double_run_passed: bool = False
    output_schema_passed: bool = False
    unit_validation_passed: bool = False
    financial_validation_passed: bool = False
    lifecycle: CapabilityLifecycle
    findings: list[JsonObject] = Field(default_factory=list)


class ScopedCapabilityRegistration(TimestampedModel):
    registration_id: str
    generated_capability_ref: str
    capability_id: str
    capability_version: str
    scope: CapabilityScope
    run_id: str
    task_id: str | None = None
    approved_by: str
    lifecycle: CapabilityLifecycle = CapabilityLifecycle.TASK_APPROVED

    @model_validator(mode="after")
    def task_scope_requires_task_id(self) -> "ScopedCapabilityRegistration":
        if self.scope is CapabilityScope.TASK and not self.task_id:
            raise ValueError("task_id is required for TASK scoped capability registration")
        return self


@runtime_checkable
class Capability(Protocol):
    definition: CapabilityDefinition

    async def execute(self, inputs: JsonObject, context: CapabilityContext) -> Any: ...
