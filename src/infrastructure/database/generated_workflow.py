"""PostgreSQL-backed recorder for the governed generated-capability workflow."""

import asyncio

from src.capabilities.generated.artifacts import GeneratedCapabilityArtifactStore
from src.capabilities.generated.models import GeneratedCapabilityCandidate
from src.capabilities.generated.ports import CapabilityWorkflowRecorder
from src.domain.capability import (
    CapabilityBuildRecord,
    CapabilityGapRecord,
    CapabilityValidationRecord,
    GeneratedCapabilityArtifactRecord,
    GeneratedCapabilityRecord,
    SandboxExecutionRecord,
    ScopedCapabilityRegistration,
)
from src.infrastructure.database.phase3_records import SQLAlchemyPhase3RecordRepository


class PostgreSQLCapabilityWorkflowRecorder(CapabilityWorkflowRecorder):
    def __init__(
        self,
        repository: SQLAlchemyPhase3RecordRepository,
        *,
        artifact_store: GeneratedCapabilityArtifactStore | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store

    async def record_gap(self, gap: CapabilityGapRecord) -> None:
        await self._repository.save(gap)

    async def record_build(self, build: CapabilityBuildRecord) -> None:
        await self._repository.save(build)

    async def record_generated(self, generated: GeneratedCapabilityRecord) -> None:
        await self._repository.save(generated)

    async def retain_generated_artifacts(
        self,
        *,
        generated: GeneratedCapabilityRecord,
        candidate: GeneratedCapabilityCandidate,
        sandbox_execution: SandboxExecutionRecord,
    ) -> GeneratedCapabilityArtifactRecord:
        if self._artifact_store is None:
            raise RuntimeError("generated capability activation requires an artifact store")
        if sandbox_execution.build_id != candidate.build_id:
            raise ValueError("sandbox execution references a different generated build")
        record = await asyncio.to_thread(
            self._artifact_store.retain,
            run_id=generated.run_id,
            generated=generated,
            candidate=candidate,
            runtime_image_identity=sandbox_execution.runtime_image_identity,
        )
        await self._repository.save(record)
        return record

    async def record_validation(
        self,
        validation: CapabilityValidationRecord,
        sandbox_execution: SandboxExecutionRecord,
    ) -> None:
        build = await self._repository.get(CapabilityBuildRecord, validation.build_id)
        if build is None:
            raise ValueError("capability validation references an unknown build")
        if sandbox_execution.build_id != build.build_id:
            raise ValueError("sandbox execution references a different build")
        await self._repository.save(validation, run_id=build.run_id)
        await self._repository.save(sandbox_execution, run_id=build.run_id)

    async def record_registration(self, registration: ScopedCapabilityRegistration) -> None:
        await self._repository.save(registration)
