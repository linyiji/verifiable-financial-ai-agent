from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.observability.reference_ledger import (
    TraceReferenceLedgerError,
    build_trace_reference_ledger,
    verify_trace_reference_ledger,
)
from src.observability.references import InMemoryTraceReferenceRepository, TraceReference

RUN_ID = "RUN-AUTHORITATIVE"
TRACE_ID = "trace-authoritative"
CREATED_AT = datetime(2026, 9, 5, tzinfo=UTC)


def _reference(number: int, **updates: object) -> TraceReference:
    values: dict[str, object] = {
        "reference_id": f"TRACE-REF-{number}",
        "run_id": RUN_ID,
        "trace_id": TRACE_ID,
        "span_id": f"span-{number}",
        "stage": "tool" if number % 2 else "calculation",
        "task_id": f"TASK-{number}",
        "created_at": CREATED_AT,
    }
    values.update(updates)
    return TraceReference.model_validate(values)


def _records() -> tuple[TraceReference, ...]:
    return tuple(_reference(number) for number in range(1, 6))


def _build(*, records=None, inventory=None, cer=None):
    rows = _records() if records is None else records
    authoritative = [item.reference_id for item in _records()] if inventory is None else inventory
    return build_trace_reference_ledger(
        run_id=RUN_ID,
        trace_id=TRACE_ID,
        authoritative_reference_ids=authoritative,
        cer_reference_ids=["TRACE-REF-1", "TRACE-REF-3", "TRACE-REF-5"] if cer is None else cer,
        records=rows,
    )


def test_complete_ledger_retains_records_and_closes_cer_subset() -> None:
    ledger = _build()
    assert ledger.total_reference_count == 5
    assert ledger.mapped_reference_count == 5
    assert ledger.same_run_count == 5
    assert ledger.same_trace_count == 5
    assert ledger.unresolved_count == 0
    assert ledger.cer_reference_count == 3
    assert ledger.cer_resolved_count == 3
    assert len(ledger.records) == 5
    assert all(item.created_at == CREATED_AT for item in ledger.records)


def test_foreign_run_reference_fails_closed() -> None:
    with pytest.raises(TraceReferenceLedgerError, match="foreign Run reference"):
        _build(records=(*_records()[:-1], _reference(5, run_id="RUN-FOREIGN")))


def test_wrong_trace_reference_fails_closed() -> None:
    with pytest.raises(TraceReferenceLedgerError, match="wrong trace"):
        _build(records=(*_records()[:-1], _reference(5, trace_id="trace-foreign")))


def test_unknown_cer_reference_fails_closed() -> None:
    with pytest.raises(TraceReferenceLedgerError, match="unknown CER TraceReference ID"):
        _build(cer=["TRACE-REF-1", "TRACE-REF-UNKNOWN"])


def test_missing_ledger_row_fails_closed() -> None:
    with pytest.raises(TraceReferenceLedgerError, match="missing ledger row"):
        _build(records=_records()[:-1])


def test_empty_authoritative_inventory_fails_closed() -> None:
    with pytest.raises(TraceReferenceLedgerError, match="inventory must not be empty"):
        _build(records=(), inventory=[])


def test_duplicate_conflicting_reference_fails_closed() -> None:
    with pytest.raises(TraceReferenceLedgerError, match="duplicate conflicting"):
        _build(records=(*_records(), _reference(5, stage="review")))


def test_reordered_rows_and_ids_have_identical_canonical_set_serialization() -> None:
    first = _build()
    second = _build(
        records=tuple(reversed(_records())),
        inventory=list(reversed([item.reference_id for item in _records()])),
        cer=["TRACE-REF-5", "TRACE-REF-1", "TRACE-REF-3"],
    )
    assert verify_trace_reference_ledger(second) == first
    assert second.canonical_json_bytes() == first.canonical_json_bytes()


def test_independent_verification_rejects_tampered_summary_count() -> None:
    retained = _build().model_dump(mode="json")
    retained["mapped_reference_count"] = 4
    with pytest.raises(TraceReferenceLedgerError, match="independent reconstruction"):
        verify_trace_reference_ledger(retained)


def test_exact_duplicate_is_set_equivalent_and_does_not_inflate_counts() -> None:
    duplicate = _records()[0].model_copy(deep=True)
    ledger = _build(records=(*_records(), duplicate))
    assert ledger.total_reference_count == 5
    assert len(ledger.records) == 5


@pytest.mark.asyncio
async def test_repository_rejects_duplicate_conflict_and_lists_canonical_order() -> None:
    repository = InMemoryTraceReferenceRepository()
    rows = tuple(reversed(_records()))
    for row in rows:
        await repository.add(row)
    await repository.add(rows[0].model_copy(deep=True))
    with pytest.raises(ValueError, match="conflicting TraceReference identity"):
        await repository.add(_reference(5, stage="review"))
    retained = await repository.list_by_run(RUN_ID)
    assert [item.reference_id for item in retained] == sorted(item.reference_id for item in rows)
