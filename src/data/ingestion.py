from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from src.data.artifacts import RawArtifactStore
from src.data.freshness import FreshnessPolicy, policy_for
from src.data.provider import Provider, ProviderRequest
from src.data.repository import EvidenceRepository
from src.data.validation import ValidatedRecord, mark_duplicate_conflicts, validate_record
from src.domain.base import JsonObject
from src.domain.enums import (
    CashFlowSignConvention,
    CorporateActionStatus,
    EvidenceCategory,
    EvidenceStatus,
    FinancialActuality,
    FinancialPeriodBasis,
    TechnicalPriceBasis,
)
from src.domain.evidence import AcceptedEvidenceBundle, EvidenceRecord
from src.observability.performance import observe, span


@dataclass(frozen=True, slots=True)
class EvidenceProvenance:
    producer_task_id: str | None = None
    source_endpoint: str | None = None
    evidence_purpose: str | None = None
    evidence_category: EvidenceCategory = EvidenceCategory.OTHER
    observed_at: datetime | None = None
    provider_timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class EvidenceIngestionResult:
    accepted: AcceptedEvidenceBundle
    records: tuple[EvidenceRecord, ...]
    diagnostics: tuple[ValidatedRecord, ...]
    created_records: tuple[EvidenceRecord, ...] = ()


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

    @observe("evidence.ingest", run="run_id")
    async def ingest(
        self,
        *,
        provider: Provider,
        request: ProviderRequest,
        run_id: str,
        object_id: str,
        provenance: EvidenceProvenance | None = None,
    ) -> EvidenceIngestionResult:
        snapshot = await provider.fetch(request)
        provenance = provenance or EvidenceProvenance()
        artifact_ref = snapshot.raw_artifact_ref
        if self._artifact_store is not None:
            artifact_ref = await self._artifact_store.put_raw_snapshot(
                run_id=run_id,
                snapshot_hash=snapshot.snapshot_hash,
                payload=snapshot.raw_payload,
            )

        freshness_policy = self._freshness_policy or policy_for(request.dataset)
        with span("evidence.validation"):
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
                provenance=provenance,
                raw_record=snapshot.records[validated.raw_index],
            )
            for validated in diagnostics
            if validated.normalized is not None
        )
        persisted_records: list[EvidenceRecord] = []
        created_records: list[EvidenceRecord] = []
        with span("evidence.persistence"):
            for record in records:
                existing = await self._repository.get(record.evidence_id)
                if existing is None:
                    await self._repository.add(record)
                    persisted_records.append(record)
                    created_records.append(record)
                    continue
                _assert_same_evidence_identity(existing, record)
                persisted_records.append(existing)

        accepted_records = [
            record for record in persisted_records if record.status is EvidenceStatus.ACCEPTED
        ]
        return EvidenceIngestionResult(
            accepted=AcceptedEvidenceBundle(
                run_id=run_id,
                records=accepted_records,
                created_at=snapshot.retrieved_at,
            ),
            records=tuple(persisted_records),
            diagnostics=tuple(diagnostics),
            created_records=tuple(created_records),
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
    provenance: EvidenceProvenance,
    raw_record: JsonObject,
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
        producer_task_id=provenance.producer_task_id,
        source_endpoint=provenance.source_endpoint
        or _optional_text(raw_record.get("source_endpoint")),
        evidence_purpose=provenance.evidence_purpose,
        evidence_category=provenance.evidence_category,
        retrieved_at=retrieved_at,
        observed_at=_optional_datetime(raw_record.get("observed_at"))
        or provenance.observed_at
        or retrieved_at,
        provider_timestamp=_optional_datetime(raw_record.get("provider_timestamp"))
        or provenance.provider_timestamp,
        period=validated.period,
        period_basis=_optional_enum(raw_record.get("period_basis"), FinancialPeriodBasis),
        actuality=(
            _optional_enum(raw_record.get("actuality"), FinancialActuality)
            or FinancialActuality.ACTUAL
        ),
        statement_series=_optional_text(raw_record.get("statement_series")),
        statement_cohort=_optional_text(raw_record.get("statement_cohort")),
        technical_price_basis=_optional_enum(
            raw_record.get("technical_price_basis"), TechnicalPriceBasis
        ),
        corporate_action_status=_optional_enum(
            raw_record.get("corporate_action_status"), CorporateActionStatus
        ),
        cash_flow_sign_convention=_optional_enum(
            raw_record.get("cash_flow_sign_convention"), CashFlowSignConvention
        ),
        cash_flow_normalization_applied=_optional_bool(
            raw_record.get("cash_flow_normalization_applied")
        ),
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


def _assert_same_evidence_identity(existing: EvidenceRecord, candidate: EvidenceRecord) -> None:
    identity_fields = (
        "run_id",
        "object_id",
        "provider",
        "source_locator",
        "source_endpoint",
        "evidence_purpose",
        "evidence_category",
        "observed_at",
        "provider_timestamp",
        "period",
        "period_basis",
        "actuality",
        "statement_series",
        "statement_cohort",
        "technical_price_basis",
        "corporate_action_status",
        "cash_flow_sign_convention",
        "cash_flow_normalization_applied",
        "as_of",
        "raw_artifact_ref",
        "normalized_field",
        "normalized_value",
        "unit",
        "currency",
        "snapshot_hash",
        "status",
    )
    if any(getattr(existing, field) != getattr(candidate, field) for field in identity_fields):
        raise ValueError(f"evidence identity collision: {candidate.evidence_id}")


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_enum(value: object, enum_type: type):
    if value is None:
        return None
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {enum_type.__name__} evidence metadata: {value!r}") from exc


def _optional_bool(value: object) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError(f"invalid boolean evidence metadata: {value!r}")
    return value


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
