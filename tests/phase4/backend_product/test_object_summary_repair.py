from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.persistence import ResearchObjectRow, ResearchRunAggregateRow, RuntimeEventRow
from src.domain.research_object import ResearchObject
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend as Backend
from src.phase4_product.projections import ProjectionIntegrityError

NOW = datetime(2026, 1, 2, tzinfo=UTC)
OBJ = ResearchObject(
    object_id="OBJ-TEST", symbol="TEST", company_name="Test Company", exchange="TEST"
)


def run(run_id="RUN-A", *, object_id="OBJ-TEST", status="RELEASED", at="2026-01-02T00:00:00Z"):
    return ResearchRunAggregateRow(
        run_id=run_id,
        object_id=object_id,
        status=status,
        updated_at=NOW,
        payload={
            "run": {"run_id": run_id, "research_object_id": object_id, "status": status},
            "artifacts": {
                "released_result": {"run_id": run_id, "released_at": at}
                if status == "RELEASED"
                else None
            },
        },
    )


def event(run_id="RUN-A", *, at="2026-01-02T00:00:00Z", sequence=1):
    event_id = f"EVT-{run_id}-{sequence}"
    return RuntimeEventRow(
        event_id=event_id,
        run_id=run_id,
        sequence=sequence,
        payload={
            "event_id": event_id,
            "run_id": run_id,
            "sequence": sequence,
            "type": "run.completed",
            "timestamp": at,
        },
    )


def summary(runs=(), events=()):
    return Backend._object_detail(OBJ, runs=tuple(runs), latest_events=tuple(events))


def test_known_released_run_and_activity_are_projected():
    value = summary([run()], [event()])
    assert value.run_count == 1
    assert value.latest_released_run_id == "RUN-A"
    assert value.released_result_availability.status == "AVAILABLE"
    assert value.last_activity.timestamp == NOW


def test_unreleased_runs_do_not_imply_release():
    value = summary([run(status="FAILED")], [event()])
    assert value.released_result_availability.reason_code == "NO_RELEASED_RUN"
    assert value.last_activity is not None


@pytest.mark.parametrize(
    "events", [[], [event(at=None)], [event(at="bad")], [event(at="2026-01-02T00:00:00")]]
)
def test_missing_activity_remains_unknown_with_positive_count(events):
    value = summary([run()], events)
    assert value.run_count == 1 and value.last_activity is None


def test_zero_runs_true_absence():
    value = summary()
    assert value.run_count == 0 and value.last_activity is None
    assert value.latest_released_run_id is None
    assert value.released_result_availability.reason_code == "NO_RELEASED_RUN"


def test_release_order_uses_timestamp_not_id_or_input_order():
    old = run("RUN-Z", at="2026-01-01T00:00:00Z")
    new = run("RUN-A", at="2026-01-02T00:00:00Z")
    for rows in ([new, old], [old, new]):
        assert summary(rows).latest_released_run_id == "RUN-A"


@pytest.mark.parametrize("at", [None, "bad", "2026-01-02T00:00:00Z"])
def test_missing_or_tied_release_order_does_not_assert_absence(at):
    value = summary([run(), run("RUN-B", at=at)])
    assert value.latest_released_run_id is None
    assert value.released_result_availability.status == "UNAVAILABLE"
    assert value.released_result_availability.reason_code == "RELEASED_RUN_LATEST_UNAVAILABLE"


def test_foreign_object_records_cannot_affect_summary():
    value = summary(
        [run(status="FAILED"), run("RUN-FOREIGN", object_id="OBJ-FOREIGN")],
        [event(), event("RUN-FOREIGN", at="2030-01-01T00:00:00Z")],
    )
    assert value.run_count == 1
    assert value.released_result_availability.reason_code == "NO_RELEASED_RUN"
    assert value.last_activity.timestamp == NOW


def test_foreign_release_payload_is_not_accepted():
    row = run()
    row.payload["artifacts"]["released_result"]["run_id"] = "RUN-FOREIGN"
    with pytest.raises(ProjectionIntegrityError):
        summary([row])


def test_activity_uses_timestamp_across_runs_not_sequence():
    value = summary(
        [run(), run("RUN-B")], [event(sequence=99, at="2026-01-01T00:00:00Z"), event("RUN-B")]
    )
    assert value.last_activity.event_id == "EVT-RUN-B-1"


def test_missing_one_run_activity_does_not_claim_an_older_event_is_latest():
    assert summary([run(), run("RUN-B")], [event()]).last_activity is None


def test_activity_preserves_safe_task_scope_without_forwarding_private_payload():
    item = event()
    item.payload.update(task_id="TASK-A", payload={"private_prompt": "not public"})
    activity = summary([run()], [item]).last_activity
    assert activity.task_id == "TASK-A"
    assert "private_prompt" not in activity.model_dump_json()


def test_list_and_detail_share_object_scoped_persisted_query():
    from src.infrastructure.database.research_memory import ResearchMemoryPointerRow
    async def exercise():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            for table in (
                ResearchObjectRow.__table__,
                ResearchRunAggregateRow.__table__,
                RuntimeEventRow.__table__,
                ResearchMemoryPointerRow.__table__,
            ):
                await conn.run_sync(table.create)
        sessions = async_sessionmaker(engine)
        backend = object.__new__(Backend)
        backend.sessions = sessions
        async with sessions() as session:
            session.add(
                ResearchObjectRow(
                    object_id=OBJ.object_id, payload=OBJ.model_dump(mode="json"), created_at=NOW
                )
            )
            session.add_all(
                [run(), run("RUN-B", status="FAILED"), run("RUN-FOREIGN", object_id="OBJ-FOREIGN")]
            )
            session.add_all(
                [
                    event(sequence=1, at="2026-01-01T00:00:00Z"),
                    event(sequence=2),
                    event("RUN-B", at="2026-01-01T00:00:00Z"),
                    event("RUN-FOREIGN", at="2030-01-01T00:00:00Z"),
                ]
            )
            await session.commit()
        detail = await backend.get_object(OBJ.object_id)
        listing = await backend.list_objects(symbol=None, query=None, cursor=None, limit=10)
        assert listing.items == (detail,)
        # Phase 5A: unmaterialized history cannot infer a current asset by time.
        assert detail.run_count == 2 and detail.latest_released_run_id is None
        assert detail.released_result_availability.reason_code == "MEMORY_NOT_MATERIALIZED"
        assert detail.last_activity.event_id == "EVT-RUN-A-2"
        await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.parametrize("method", ["get_results", "get_report", "get_review", "get_execution"])
def test_unknown_exact_run_never_asks_for_object_latest(method):
    backend = object.__new__(Backend)
    backend.service = SimpleNamespace(
        get_run=AsyncMock(side_effect=LookupError("unknown exact Run")), get_object=AsyncMock()
    )
    with pytest.raises(LookupError, match="unknown exact Run"):
        asyncio.run(getattr(backend, method)("RUN-MISSING"))
    backend.service.get_run.assert_awaited_once_with("RUN-MISSING")
    backend.service.get_object.assert_not_awaited()
