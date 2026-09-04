"""PostgreSQL-backed recorder for the governed generated-capability workflow."""

from src.capabilities.generated.ports import CapabilityWorkflowRecorder
from src.domain.capability import (
    CapabilityBuildRecord,
    CapabilityGapRecord,
    CapabilityValidationRecord,
    GeneratedCapabilityRecord,
    SandboxExecutionRecord,
    ScopedCapabilityRegistration,
)
from src.infrastructure.database.phase3_records import SQLAlchemyPhase3RecordRepository


class PostgreSQLCapabilityWorkflowRecorder(CapabilityWorkflowRecorder):
    def __init__(self, repository: SQLAlchemyPhase3RecordRepository) -> None:
        self._repository = repository

    async def record_gap(self, gap: CapabilityGapRecord) -> None:
        await self._repository.save(gap)

    async def record_build(self, build: CapabilityBuildRecord) -> None:
        await self._repository.save(build)

    async def record_generated(self, generated: GeneratedCapabilityRecord) -> None:
        await self._repository.save(generated)

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
