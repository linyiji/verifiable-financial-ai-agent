"""Closure recovery boundaries never permit generic post-terminal execution."""

import pytest

from src.application.closure_recovery import NoProofExecution, fingerprint, recover_closure
from src.domain.runtime_event import RuntimeEventType as T
from src.runtime.events import (
    EventReconciliationRequired,
    InMemoryRuntimeEventStore,
    validate_event_log,
)


@pytest.mark.asyncio
async def test_closure_boundary_preserves_failed_prefix_and_closes_once():
    store = InMemoryRuntimeEventStore()
    failed = await store.emit(
        run_id="R",
        event_type=T.RUN_FAILED,
        payload={
            "status": "FAILED",
            "failure_stage": "RELEASE",
            "failure_code": "RELEASE_GATE_BLOCKED",
        },
    )
    snapshot = failed.model_dump(mode="json")
    with pytest.raises(EventReconciliationRequired):
        await store.emit(
            run_id="R",
            event_type=T.CLOSURE_RECOVERY_STARTED,
            payload={
                "attempt_id": "A",
                "failed_event_id": "foreign",
                "snapshot_hash": "sha256:a",
                "status": "REVIEW",
            },
        )
    await store.emit(
        run_id="R",
        event_type=T.CLOSURE_RECOVERY_STARTED,
        payload={
            "attempt_id": "A",
            "failed_event_id": failed.event_id,
            "snapshot_hash": "sha256:a",
            "status": "REVIEW",
        },
    )
    assert validate_event_log("R", await store.replay("R")) is None
    final = await store.emit(run_id="R", event_type=T.RUN_COMPLETED, payload={"status": "RELEASED"})
    events = await store.replay("R")
    assert events[0].model_dump(mode="json") == snapshot
    assert validate_event_log("R", events) == final
    with pytest.raises(EventReconciliationRequired):
        await store.emit(
            run_id="R",
            event_type=T.CLOSURE_RECOVERY_STARTED,
            payload={
                "attempt_id": "B",
                "failed_event_id": final.event_id,
                "snapshot_hash": "sha256:a",
                "status": "REVIEW",
            },
        )


@pytest.mark.asyncio
async def test_missing_authority_stops_before_any_repository_or_model_call():
    with pytest.raises(ValueError, match="authorization"):
        await recover_closure(
            sessions=None,
            service=None,
            run_id="R",
            expected_snapshot_hash="x",
            source_sha="a" * 40,
            owner_authorization="",
            materialize_memory=None,
        )
    with pytest.raises(RuntimeError, match="never execute"):
        await NoProofExecution().execute()
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
