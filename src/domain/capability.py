from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import Field, model_validator

from src.domain.base import JsonObject, TimestampedModel
from src.domain.enums import (
    CapabilityBackend,
    CapabilityLifecycle,
    CapabilityScope,
    CapabilityValidationScope,
    ValidationResult,
)


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
    generated_by_actual_model: str | None = None
    execution_policy: dict | None = None
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


class GeneratedCapabilityArtifactRecord(TimestampedModel):
    """Immutable binding from an accepted build to its exact sandbox inputs."""

    run_id: str
    build_id: str
    generated_capability_id: str
    capability_id: str
    capability_version: str
    source_artifact_id: str
    source_artifact_ref: str
    source_sha256: str
    source_size_bytes: int = Field(gt=0)
    test_artifact_id: str
    test_artifact_ref: str
    test_sha256: str
    test_size_bytes: int = Field(gt=0)
    implementation_hash: str
    runtime_image_identity: str

    @model_validator(mode="after")
    def require_content_addressed_identity(self) -> "GeneratedCapabilityArtifactRecord":
        if self.source_artifact_id != self.source_sha256:
            raise ValueError("source artifact id must equal its content hash")
        if self.test_artifact_id != self.test_sha256:
            raise ValueError("test artifact id must equal its content hash")
        if self.implementation_hash != self.source_sha256:
            raise ValueError("implementation hash must equal the exact source content hash")
        for value in (
            self.source_sha256,
            self.test_sha256,
            self.implementation_hash,
        ):
            if len(value) != 71 or not value.startswith("sha256:"):
                raise ValueError("generated artifact hashes must be sha256 identities")
            try:
                int(value.removeprefix("sha256:"), 16)
            except ValueError as exc:
                raise ValueError("generated artifact hashes must be hexadecimal") from exc
        if not self.runtime_image_identity.strip():
            raise ValueError("runtime image identity must not be blank")
        return self


class CapabilityBuildRecord(TimestampedModel):
    execution_policy: dict | None = None
    execution_outcome: str | None = None
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
    runtime_image_identity: str = "UNRECORDED_LEGACY_RUNTIME"
    input_fixture_hash: str
    network_disabled: bool
    read_only_root: bool
    non_root_user: bool
    resource_limits: JsonObject
    security_attestation: JsonObject = Field(default_factory=dict)
    exit_code: int | None = None
    output_hash: str | None = None
    passed: bool = False
    detail: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    capability_id: str | None = None
    generation_attempt: int | None = Field(default=None, ge=1)
    started_at: datetime | None = None
    finished_at: datetime | None = None


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
    source_hash: str | None = None
    tests_hash: str | None = None
    validation_scope: CapabilityValidationScope = CapabilityValidationScope.PRE_ACTIVATION
    oracle_result: JsonObject = Field(default_factory=dict)
    runtime_result: JsonObject = Field(default_factory=dict)
    validation_result: ValidationResult | None = None

    @model_validator(mode="after")
    def completed_pass_requires_full_identity(self) -> "CapabilityValidationRecord":
        if self.validation_result is not ValidationResult.PASS:
            return self
        checks = (
            self.static_validation_passed,
            self.syntax_compile_passed,
            self.unit_tests_passed,
            self.edge_cases_passed,
            self.financial_invariants_passed,
            self.deterministic_double_run_passed,
            self.output_schema_passed,
            self.unit_validation_passed,
            self.financial_validation_passed,
        )
        if not all(checks) or not self.source_hash or not self.tests_hash:
            raise ValueError("PASS validation requires every check and immutable source hashes")
        if not self.oracle_result or not self.runtime_result:
            raise ValueError("PASS validation requires oracle and runtime results")
        return self


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
