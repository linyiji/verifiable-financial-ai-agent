"""Deterministic, independently verifiable TraceReference retention."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import ConfigDict, Field

from src.domain.base import DomainModel
from src.observability.references import TraceReference


class TraceReferenceLedgerError(ValueError):
    """Raised when a retained TraceReference ledger cannot close exactly."""


class TraceReferenceLedger(DomainModel):
    """Canonical retained snapshot of one Run's complete TraceReference set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["trace_reference_ledger.v1"] = "trace_reference_ledger.v1"
    run_id: str
    trace_id: str
    total_reference_count: int = Field(ge=0)
    mapped_reference_count: int = Field(ge=0)
    same_run_count: int = Field(ge=0)
    same_trace_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    cer_reference_count: int = Field(ge=0)
    cer_resolved_count: int = Field(ge=0)
    authoritative_reference_ids: tuple[str, ...]
    cer_reference_ids: tuple[str, ...]
    records: tuple[TraceReference, ...]

    def canonical_json_bytes(self) -> bytes:
        """Return stable bytes after independently rechecking ledger closure."""

        closed = verify_trace_reference_ledger(self)
        return (
            json.dumps(
                closed.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")


def build_trace_reference_ledger(
    *,
    run_id: str,
    trace_id: str,
    authoritative_reference_ids: Sequence[str],
    cer_reference_ids: Sequence[str],
    records: Sequence[TraceReference],
) -> TraceReferenceLedger:
    """Close a full repository snapshot against its inventory and CER subset."""

    normalized_run_id = _required_identity("run_id", run_id)
    normalized_trace_id = _required_identity("trace_id", trace_id)
    authoritative_ids = _canonical_id_set(
        "authoritative_reference_ids", authoritative_reference_ids
    )
    cer_ids = _canonical_id_set("cer_reference_ids", cer_reference_ids)
    if not authoritative_ids:
        raise TraceReferenceLedgerError("authoritative TraceReference inventory must not be empty")
    if not cer_ids:
        raise TraceReferenceLedgerError("CER TraceReference subset must not be empty")
    record_map = _canonical_record_map(records)

    for reference in record_map.values():
        if reference.run_id != normalized_run_id:
            raise TraceReferenceLedgerError(
                f"foreign Run reference {reference.reference_id!r}: "
                f"expected {normalized_run_id!r}, observed {reference.run_id!r}"
            )
        if reference.trace_id != normalized_trace_id:
            raise TraceReferenceLedgerError(
                f"wrong trace for reference {reference.reference_id!r}: "
                f"expected {normalized_trace_id!r}, observed {reference.trace_id!r}"
            )

    record_ids = set(record_map)
    authoritative_set = set(authoritative_ids)
    missing_rows = authoritative_set - record_ids
    unexpected_rows = record_ids - authoritative_set
    if missing_rows:
        raise TraceReferenceLedgerError(f"missing ledger row(s): {', '.join(sorted(missing_rows))}")
    if unexpected_rows:
        raise TraceReferenceLedgerError(
            f"unknown ledger row(s): {', '.join(sorted(unexpected_rows))}"
        )

    unresolved_cer = set(cer_ids) - record_ids
    if unresolved_cer:
        raise TraceReferenceLedgerError(
            f"unknown CER TraceReference ID(s): {', '.join(sorted(unresolved_cer))}"
        )

    canonical_records = tuple(record_map[item] for item in authoritative_ids)
    reference_count = len(authoritative_ids)
    return TraceReferenceLedger(
        run_id=normalized_run_id,
        trace_id=normalized_trace_id,
        total_reference_count=reference_count,
        mapped_reference_count=len(record_ids & authoritative_set),
        same_run_count=sum(item.run_id == normalized_run_id for item in canonical_records),
        same_trace_count=sum(item.trace_id == normalized_trace_id for item in canonical_records),
        unresolved_count=0,
        cer_reference_count=len(cer_ids),
        cer_resolved_count=len(cer_ids),
        authoritative_reference_ids=authoritative_ids,
        cer_reference_ids=cer_ids,
        records=canonical_records,
    )


def verify_trace_reference_ledger(
    value: TraceReferenceLedger | Mapping[str, Any],
) -> TraceReferenceLedger:
    """Independently reconstruct and verify a retained ledger artifact."""

    retained = (
        value
        if isinstance(value, TraceReferenceLedger)
        else TraceReferenceLedger.model_validate(value)
    )
    closed = build_trace_reference_ledger(
        run_id=retained.run_id,
        trace_id=retained.trace_id,
        authoritative_reference_ids=retained.authoritative_reference_ids,
        cer_reference_ids=retained.cer_reference_ids,
        records=retained.records,
    )
    for field_name in (
        "total_reference_count",
        "mapped_reference_count",
        "same_run_count",
        "same_trace_count",
        "unresolved_count",
        "cer_reference_count",
        "cer_resolved_count",
    ):
        if getattr(retained, field_name) != getattr(closed, field_name):
            raise TraceReferenceLedgerError(
                f"retained {field_name} does not match independent reconstruction"
            )
    return closed


def _canonical_record_map(records: Sequence[TraceReference]) -> dict[str, TraceReference]:
    result: dict[str, TraceReference] = {}
    for value in records:
        reference = TraceReference.model_validate(value).model_copy(deep=True)
        reference_id = _required_identity("TraceReference.reference_id", reference.reference_id)
        _required_identity("TraceReference.run_id", reference.run_id)
        _required_identity("TraceReference.trace_id", reference.trace_id)
        _required_identity("TraceReference.stage", reference.stage)
        existing = result.get(reference_id)
        if existing is not None:
            if existing.model_dump(mode="json") != reference.model_dump(mode="json"):
                raise TraceReferenceLedgerError(
                    f"duplicate conflicting TraceReference: {reference_id}"
                )
            continue
        result[reference_id] = reference
    return result


def _canonical_id_set(name: str, values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({_required_identity(name, value) for value in values}))


def _required_identity(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TraceReferenceLedgerError(f"{name} must not be blank")
    return value.strip()
