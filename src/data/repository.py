from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.evidence import EvidenceRecord


@runtime_checkable
class EvidenceRepository(Protocol):
    async def add(self, entity: EvidenceRecord) -> EvidenceRecord: ...

    async def get(self, evidence_id: str) -> EvidenceRecord | None: ...

    async def list(self) -> list[EvidenceRecord]: ...

    async def list_by_run(self, run_id: str) -> list[EvidenceRecord]: ...


class InMemoryEvidenceRepository:
    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}

    async def add(self, entity: EvidenceRecord) -> EvidenceRecord:
        if entity.evidence_id in self._records:
            raise ValueError(f"evidence already exists: {entity.evidence_id}")
        self._records[entity.evidence_id] = entity.model_copy(deep=True)
        return entity

    async def get(self, evidence_id: str) -> EvidenceRecord | None:
        record = self._records.get(evidence_id)
        return record.model_copy(deep=True) if record else None

    async def list(self) -> list[EvidenceRecord]:
        return [record.model_copy(deep=True) for record in self._records.values()]

    async def list_by_run(self, run_id: str) -> list[EvidenceRecord]:
        return [
            record.model_copy(deep=True)
            for record in self._records.values()
            if record.run_id == run_id
        ]
