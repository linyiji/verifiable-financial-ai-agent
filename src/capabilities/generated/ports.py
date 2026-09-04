from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.capabilities.generated.models import (
    CapabilityBuildRequest,
    GeneratedCapabilityCandidate,
    ResearchLeadCapabilityApproval,
    ValidationHandoff,
)
from src.domain.capability import (
    Capability,
    CapabilityBuildRecord,
    CapabilityGapRecord,
    CapabilityValidationRecord,
    GeneratedCapabilityArtifactRecord,
    GeneratedCapabilityRecord,
    SandboxExecutionRecord,
    ScopedCapabilityRegistration,
)


@runtime_checkable
class CodeBuilder(Protocol):
    async def generate(self, request: CapabilityBuildRequest) -> GeneratedCapabilityCandidate: ...


@runtime_checkable
class CapabilityValidationProgressPort(Protocol):
    async def static_validated(self, implementation_hash: str) -> None: ...

    async def sandbox_started(self, implementation_hash: str) -> None: ...

    async def tests_passed(self, implementation_hash: str) -> None: ...

    async def financial_validated(self, implementation_hash: str) -> None: ...


@runtime_checkable
class GeneratedCapabilityValidationPort(Protocol):
    async def validate(
        self,
        candidate: GeneratedCapabilityCandidate,
        *,
        progress: CapabilityValidationProgressPort,
    ) -> ValidationHandoff: ...


@runtime_checkable
class ResearchLeadCapabilityAuthority(Protocol):
    lead_agent_id: str

    async def approve_spec(self, gap: CapabilityGapRecord) -> ResearchLeadCapabilityApproval: ...

    async def approve_activation(
        self,
        gap: CapabilityGapRecord,
        generated: GeneratedCapabilityRecord,
        validation: CapabilityValidationRecord,
    ) -> ResearchLeadCapabilityApproval: ...


@runtime_checkable
class ScopedCapabilityRegistryPort(Protocol):
    async def lookup(
        self,
        capability_id: str,
        *,
        version: str | None,
        run_id: str,
        task_id: str,
    ) -> Capability | None: ...

    async def register(
        self,
        registration: ScopedCapabilityRegistration,
        capability: Capability,
    ) -> ScopedCapabilityRegistration: ...


@runtime_checkable
class CapabilityWorkflowRecorder(Protocol):
    """Persistence port; concrete PostgreSQL mapping remains a separate workstream."""

    async def record_gap(self, gap: CapabilityGapRecord) -> None: ...

    async def record_build(self, build: CapabilityBuildRecord) -> None: ...

    async def record_generated(self, generated: GeneratedCapabilityRecord) -> None: ...

    async def retain_generated_artifacts(
        self,
        *,
        generated: GeneratedCapabilityRecord,
        candidate: GeneratedCapabilityCandidate,
        sandbox_execution: SandboxExecutionRecord,
    ) -> GeneratedCapabilityArtifactRecord: ...

    async def record_validation(
        self,
        validation: CapabilityValidationRecord,
        sandbox_execution: SandboxExecutionRecord,
    ) -> None: ...

    async def record_registration(self, registration: ScopedCapabilityRegistration) -> None: ...


class NoopCapabilityWorkflowRecorder:
    async def record_gap(self, gap: CapabilityGapRecord) -> None:
        del gap

    async def record_build(self, build: CapabilityBuildRecord) -> None:
        del build

    async def record_generated(self, generated: GeneratedCapabilityRecord) -> None:
        del generated

    async def retain_generated_artifacts(
        self,
        *,
        generated: GeneratedCapabilityRecord,
        candidate: GeneratedCapabilityCandidate,
        sandbox_execution: SandboxExecutionRecord,
    ) -> GeneratedCapabilityArtifactRecord:
        del generated, candidate, sandbox_execution
        raise RuntimeError("generated capability activation requires durable artifact retention")

    async def record_validation(
        self,
        validation: CapabilityValidationRecord,
        sandbox_execution: SandboxExecutionRecord,
    ) -> None:
        del validation, sandbox_execution

    async def record_registration(self, registration: ScopedCapabilityRegistration) -> None:
        del registration
