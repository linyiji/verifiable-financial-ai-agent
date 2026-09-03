from datetime import date, datetime
from typing import Any

from src.domain.base import TimestampedModel
from src.domain.enums import EvidenceStatus


class EvidenceRecord(TimestampedModel):
    evidence_id: str
    run_id: str
    object_id: str
    provider: str
    source_locator: str | None = None
    retrieved_at: datetime
    period: str
    as_of: date
    raw_artifact_ref: str
    normalized_field: str
    normalized_value: Any
    unit: str
    currency: str | None = None
    snapshot_hash: str
    status: EvidenceStatus


class AcceptedEvidenceBundle(TimestampedModel):
    run_id: str
    records: list[EvidenceRecord]

