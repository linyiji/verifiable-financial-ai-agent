from datetime import date, datetime
from typing import Any

from src.domain.base import TimestampedModel
from src.domain.enums import EvidenceCategory, EvidenceStatus


class EvidenceRecord(TimestampedModel):
    evidence_id: str
    run_id: str
    object_id: str
    provider: str
    source_locator: str | None = None
    producer_task_id: str | None = None
    source_endpoint: str | None = None
    evidence_purpose: str | None = None
    evidence_category: EvidenceCategory = EvidenceCategory.OTHER
    retrieved_at: datetime
    observed_at: datetime | None = None
    provider_timestamp: datetime | None = None
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
