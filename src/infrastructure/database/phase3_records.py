"""Durable Phase 3 record repository over append-only schema migrations."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.capability import (
    CapabilityBuildRecord,
    CapabilityGapRecord,
    CapabilityValidationRecord,
    GeneratedCapabilityArtifactRecord,
    GeneratedCapabilityRecord,
    SandboxExecutionRecord,
    ScopedCapabilityRegistration,
)
from src.domain.proof import (
    ProofArtifactReference,
    ProofInputCommitment,
    ProofPolicyDecision,
    ProofRecord,
    ProofVerificationRecord,
)
from src.domain.report import ReportArtifactRecord
from src.infrastructure.database.models import (
    CapabilityBuildRecordRow,
    CapabilityGapRecordRow,
    CapabilityValidationRecordRow,
    GeneratedCapabilityArtifactRecordRow,
    GeneratedCapabilityRecordRow,
    ProofArtifactReferenceRow,
    ProofInputCommitmentRow,
    ProofPolicyDecisionRow,
    ProofRecordRow,
    ProofVerificationRecordRow,
    ReportArtifactRecordRow,
    SandboxExecutionRecordRow,
    ScopedCapabilityRegistrationRow,
)

Phase3Record = (
    CapabilityGapRecord
    | CapabilityBuildRecord
    | GeneratedCapabilityRecord
    | GeneratedCapabilityArtifactRecord
    | SandboxExecutionRecord
    | CapabilityValidationRecord
    | ScopedCapabilityRegistration
    | ProofPolicyDecision
    | ProofInputCommitment
    | ProofRecord
    | ProofArtifactReference
    | ProofVerificationRecord
    | ReportArtifactRecord
)
RecordT = TypeVar("RecordT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class _RecordMapping:
    row_type: type[Any]
    id_field: str


_MAPPINGS: dict[type[BaseModel], _RecordMapping] = {
    CapabilityGapRecord: _RecordMapping(CapabilityGapRecordRow, "gap_id"),
    CapabilityBuildRecord: _RecordMapping(CapabilityBuildRecordRow, "build_id"),
    GeneratedCapabilityRecord: _RecordMapping(
        GeneratedCapabilityRecordRow, "generated_capability_id"
    ),
    GeneratedCapabilityArtifactRecord: _RecordMapping(
        GeneratedCapabilityArtifactRecordRow, "build_id"
    ),
    SandboxExecutionRecord: _RecordMapping(SandboxExecutionRecordRow, "execution_id"),
    CapabilityValidationRecord: _RecordMapping(CapabilityValidationRecordRow, "validation_id"),
    ScopedCapabilityRegistration: _RecordMapping(
        ScopedCapabilityRegistrationRow, "registration_id"
    ),
    ProofPolicyDecision: _RecordMapping(ProofPolicyDecisionRow, "decision_id"),
    ProofInputCommitment: _RecordMapping(ProofInputCommitmentRow, "commitment_id"),
    ProofRecord: _RecordMapping(ProofRecordRow, "proof_id"),
    ProofArtifactReference: _RecordMapping(ProofArtifactReferenceRow, "artifact_id"),
    ProofVerificationRecord: _RecordMapping(ProofVerificationRecordRow, "verification_id"),
    ReportArtifactRecord: _RecordMapping(ReportArtifactRecordRow, "artifact_id"),
}


class SQLAlchemyPhase3RecordRepository:
    """Store typed records while keeping receipt bytes outside PostgreSQL."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save(self, entity: Phase3Record, *, run_id: str | None = None) -> Phase3Record:
        async with self._sessions() as session:
            async with session.begin():
                await self._save_in_session(session, entity, run_id=run_id)
        return entity

    async def save_many(
        self,
        entities: Sequence[Phase3Record],
        *,
        run_id: str | None = None,
    ) -> list[Phase3Record]:
        """Atomically persist one logically complete Phase 3 record group."""

        if not entities:
            raise ValueError("save_many requires at least one record")
        async with self._sessions() as session:
            async with session.begin():
                for entity in entities:
                    await self._save_in_session(session, entity, run_id=run_id)
        return list(entities)

    async def get(self, model_type: type[RecordT], entity_id: str) -> RecordT | None:
        mapping = self._mapping(model_type)
        async with self._sessions() as session:
            row = await session.get(mapping.row_type, entity_id)
        return model_type.model_validate(row.payload) if row is not None else None

    async def list(self, model_type: type[RecordT], run_id: str) -> list[RecordT]:
        mapping = self._mapping(model_type)
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(mapping.row_type)
                    .where(mapping.row_type.run_id == run_id)
                    .order_by(*mapping.row_type.__table__.primary_key.columns)
                )
            ).all()
        return [model_type.model_validate(row.payload) for row in rows]

    @staticmethod
    def _mapping(model_type: type[BaseModel]) -> _RecordMapping:
        try:
            return _MAPPINGS[model_type]
        except KeyError as exc:
            raise TypeError(f"unsupported Phase 3 record type: {model_type.__name__}") from exc

    async def _save_in_session(
        self,
        session: AsyncSession,
        entity: Phase3Record,
        *,
        run_id: str | None,
    ) -> None:
        mapping = self._mapping(type(entity))
        entity_run_id = getattr(entity, "run_id", None)
        resolved_run_id = run_id or entity_run_id
        if not resolved_run_id:
            raise ValueError("run_id is required for this Phase 3 record")
        if run_id and entity_run_id and run_id != entity_run_id:
            raise ValueError("record cannot be stored under a different run")
        entity_id = str(getattr(entity, mapping.id_field))
        row = await session.get(mapping.row_type, entity_id)
        payload = entity.model_dump(mode="json")
        if row is None:
            values = {
                mapping.id_field: entity_id,
                "run_id": resolved_run_id,
                "payload": payload,
            }
            if isinstance(entity, GeneratedCapabilityArtifactRecord):
                values.update(
                    {
                        "generated_capability_id": entity.generated_capability_id,
                        "capability_id": entity.capability_id,
                        "capability_version": entity.capability_version,
                        "source_artifact_id": entity.source_artifact_id,
                        "source_artifact_ref": entity.source_artifact_ref,
                        "source_sha256": entity.source_sha256,
                        "source_size_bytes": entity.source_size_bytes,
                        "test_artifact_id": entity.test_artifact_id,
                        "test_artifact_ref": entity.test_artifact_ref,
                        "test_sha256": entity.test_sha256,
                        "test_size_bytes": entity.test_size_bytes,
                        "implementation_hash": entity.implementation_hash,
                        "runtime_image_identity": entity.runtime_image_identity,
                        "created_at": entity.created_at,
                    }
                )
            session.add(mapping.row_type(**values))
            return
        if row.run_id != resolved_run_id:
            raise ValueError(f"record {entity_id} cannot move between runs")
        if isinstance(entity, (GeneratedCapabilityArtifactRecord, ReportArtifactRecord)):
            if row.payload != payload:
                raise ValueError("artifact record bindings are immutable")
            return
        row.payload = payload
