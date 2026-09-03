from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from src.data.artifacts import RawArtifactStore
from src.data.freshness import FreshnessPolicy, policy_for
from src.data.provider import Provider, ProviderRequest
from src.data.repository import EvidenceRepository
from src.data.validation import ValidatedRecord, mark_duplicate_conflicts, validate_record
from src.domain.enums import EvidenceStatus
from src.domain.evidence import AcceptedEvidenceBundle, EvidenceRecord


@dataclass(frozen=True, slots=True)
class EvidenceIngestionResult:
    accepted: AcceptedEvidenceBundle
    records: tuple[EvidenceRecord, ...]
    diagnostics: tuple[ValidatedRecord, ...]


class EvidenceIngestionService:
    """Turns quarantined provider data into reviewed domain evidence."""

    def __init__(
        self,
        *,
        repository: EvidenceRepository,
        artifact_store: RawArtifactStore | None = None,
        freshness_policy: FreshnessPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store
        self._freshness_policy = freshness_policy

    async def ingest(
        self,
        *,
        provider: Provider,
        request: ProviderRequest,
        run_id: str,
        object_id: str,
    ) -> EvidenceIngestionResult:
        snapshot = await provider.fetch(request)
        artifact_ref = snapshot.raw_artifact_ref
        if self._artifact_store is not None:
            artifact_ref = await self._artifact_store.put_raw_snapshot(
                run_id=run_id,
                snapshot_hash=snapshot.snapshot_hash,
                payload=snapshot.raw_payload,
            )

        freshness_policy = self._freshness_policy or policy_for(request.dataset)
        diagnostics = mark_duplicate_conflicts(
            [
                validate_record(index, record, request, freshness_policy)
                for index, record in enumerate(snapshot.records)
            ]
        )
        records = tuple(
            _to_evidence_record(
                validated,
                run_id=run_id,
                object_id=object_id,
                provider=snapshot.provider,
                source_locator=snapshot.source_locator,
                retrieved_at=snapshot.retrieved_at,
                raw_artifact_ref=artifact_ref,
                snapshot_hash=snapshot.snapshot_hash,
            )
            for validated in diagnostics
            if validated.normalized is not None
        )
        for record in records:
            await self._repository.add(record)

        accepted_records = [
            record for record in records if record.status is EvidenceStatus.ACCEPTED
        ]
        return EvidenceIngestionResult(
            accepted=AcceptedEvidenceBundle(
                run_id=run_id,
                records=accepted_records,
                created_at=snapshot.retrieved_at,
            ),
            records=records,
            diagnostics=tuple(diagnostics),
        )


def _to_evidence_record(
    validated: ValidatedRecord,
    *,
    run_id: str,
    object_id: str,
    provider: str,
    source_locator: str,
    retrieved_at: datetime,
    raw_artifact_ref: str,
    snapshot_hash: str,
) -> EvidenceRecord:
    assert validated.normalized is not None
    assert validated.period is not None
    assert validated.as_of is not None
    evidence_key = f"{snapshot_hash}:{validated.raw_index}:{run_id}:{object_id}"
    value = validated.normalized.value
    if isinstance(value, Decimal):
        value = _canonical_decimal(value)
    return EvidenceRecord(
        evidence_id=f"EVD-{uuid5(NAMESPACE_URL, evidence_key)}",
        run_id=run_id,
        object_id=object_id,
        provider=provider,
        source_locator=source_locator,
        retrieved_at=retrieved_at,
        period=validated.period,
        as_of=validated.as_of,
        raw_artifact_ref=raw_artifact_ref,
        normalized_field=validated.normalized.field,
        normalized_value=value,
        unit=validated.normalized.unit,
        currency=validated.normalized.currency,
        snapshot_hash=snapshot_hash,
        status=validated.status,
        created_at=retrieved_at,
    )


def _canonical_decimal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return "0" if Decimal(rendered).is_zero() else rendered
