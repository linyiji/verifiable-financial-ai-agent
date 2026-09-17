"""Real isolated PostgreSQL proof of the synchronous publication authority."""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.models import ResearchRunDraft
from src.application.persistence import ResearchRunAggregateRow, SQLAlchemyApplicationRepository
from src.domain.node_binding import BindingDenied, canonical_value, task_semantics
from src.domain.research_object import ResearchObject
from src.domain.runtime_event import RuntimeEventType
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from tests.wp02.test_node_binding import aggregate

pytestmark = pytest.mark.skipif(
    "TEST_POSTGRESQL_URL" not in os.environ, reason="isolated PostgreSQL required"
)


@asynccontextmanager
async def bound_publisher():
    engine = create_async_engine(os.environ["TEST_POSTGRESQL_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyApplicationRepository(sessions)
    value = aggregate(("evidence_collection", "evidence_collection"))
    # Construct independent tasks before the real authority initializes the root.
    value.node_binding = None
    value.runtime.binding_ref = None
    value = repo._to_aggregate(json.loads(
        json.dumps(repo._payload(value)).replace("WP02", "WM-" + uuid4().hex)
    ))
    for graph in (value.runtime.planned_graph, value.runtime.actual_graph):
        for task in graph.tasks:
            task.dependencies = []
    await repo.add_object(ResearchObject(
        object_id=value.run.research_object_id, symbol="WM", company_name="Watermark fixture",
        exchange="LOCAL",
    ))
    await repo.add_draft(ResearchRunDraft(
        draft_id="DRAFT-WM", goal=value.goal, scheme_snapshot=value.scheme,
    ))
    await repo.add_run(value)
    owner = await repo.claim_execution(value.run.run_id)
    await repo.begin_scheduler(owner)
    admissions = []
    for task in value.runtime.actual_graph.tasks:
        admissions.append(await repo.reserve_node(
            owner, task, {"task": task_semantics(task), "scheme": canonical_value(value.scheme)},
        ))
    await repo.dispatch_node(admissions[0])
    await repo.enter_node_execution(admissions[0])
    service = SimpleNamespace(repository=repo, event_store=PostgresRuntimeEventStore(sessions))
    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    try:
        yield repo, backend, admissions, owner
    finally:
        await engine.dispose()


async def snapshot(backend, run_id):
    async with backend.sessions() as session:
        row = await session.get(ResearchRunAggregateRow, run_id)
        return row.payload, row.projection_sequence, row.projection_revision


async def emit(backend, task_id, kind=RuntimeEventType.TASK_PROGRESS):
    return await backend.service.event_store.emit(
        run_id=task_id.rsplit(":", 1)[0], task_id=task_id, event_type=kind,
        payload={"progress": 0.1, "stage": "dispatched"},
    )


@pytest.mark.parametrize("kind,task_index", [
    (RuntimeEventType.TASK_PROGRESS, 0), (RuntimeEventType.TASK_READY, 1),
])
async def test_transition_before_capture_uses_current_ref_and_rejects_stale(
    monkeypatch, kind, task_index,
):
    async with bound_publisher() as (repo, backend, admissions, owner):
        run_id = owner.run_id
        stale = await repo.get_run_fresh(run_id)
        entered, committed = asyncio.Event(), asyncio.Event()
        original = repo.projection_publication
        seen = []

        @asynccontextmanager
        async def fenced(event):
            entered.set()
            await committed.wait()
            async with original(event) as pair:
                seen.append(pair[0].node_binding.reference())
                yield pair

        monkeypatch.setattr(repo, "projection_publication", fenced)
        publication = asyncio.create_task(emit(backend, admissions[task_index].task_id, kind))
        await asyncio.wait_for(entered.wait(), 5)
        await repo.dispatch_node(admissions[1])
        current = await repo.get_run_fresh(run_id)
        before = await snapshot(backend, run_id)
        committed.set()
        event = await asyncio.wait_for(publication, 5)
        after = await snapshot(backend, run_id)
        assert seen == [current.node_binding.reference()]
        assert stale.node_binding.binding_revision + 1 == seen[0].binding_revision
        assert after[0] == before[0]  # includes business facts, owner, graph and task identities
        assert after[1:] == (event.sequence, before[2] + 1)
        assert current.node_binding.owner_generation == owner.owner_generation == 1
        assert current.node_binding.owner_id == owner.owner_id

        late = await backend.service.event_store._delegate.emit(
            run_id=run_id, task_id=admissions[0].task_id,
            event_type=RuntimeEventType.TASK_PROGRESS, payload={"stage": "late"},
        )
        with pytest.raises(
            BindingDenied, match="STALE_WRITE_REJECTED: watermark binding reference"
        ):
            await repo.save_run_with_projection_watermark(
                stale, projection_sequence=late.sequence,
                expected_binding_ref=stale.node_binding.reference(),
            )
        assert await snapshot(backend, run_id) == after
        await backend._publish_runtime_event(late)
        accepted = await snapshot(backend, run_id)
        await backend._publish_runtime_event(late)
        await backend._publish_runtime_event(event)
        assert await snapshot(backend, run_id) == accepted
        events = await backend.service.event_store._delegate.replay(run_id)
        assert [e.event_id for e in events] == [event.event_id, late.event_id]
        assert accepted[0] == before[0]
        print(json.dumps({
            "ordering": "transition_before_capture", "kind": kind.value,
            "task_id": event.task_id, "stale": stale.node_binding.reference().model_dump(),
            "accepted": seen[0].model_dump(), "events": len(events),
            "guard": "STALE_WRITE_REJECTED", "business_payload_unchanged": True,
        }))


async def test_capture_before_transition_holds_only_root_publication_lock(monkeypatch):
    async with bound_publisher() as (repo, backend, admissions, owner):
        acquired, release = asyncio.Event(), asyncio.Event()
        original = repo.projection_publication
        captured = []
        before = await snapshot(backend, owner.run_id)

        @asynccontextmanager
        async def fenced(event):
            async with original(event) as pair:
                captured.append(pair[0].node_binding.reference())
                acquired.set()
                await release.wait()
                yield pair

        monkeypatch.setattr(repo, "projection_publication", fenced)
        publication = asyncio.create_task(emit(backend, admissions[0].task_id))
        await asyncio.wait_for(acquired.wait(), 5)
        competitor = asyncio.create_task(repo.dispatch_node(admissions[1]))

        async def server_confirms_blocked_writer():
            async with backend.sessions() as session:
                while True:
                    blocked = await session.scalar(text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname=current_database() "
                        "AND cardinality(pg_blocking_pids(pid)) > 0"
                    ))
                    if blocked:
                        return
        try:
            await asyncio.wait_for(server_confirms_blocked_writer(), 5)
            assert not competitor.done()
            release.set()
            event = await asyncio.wait_for(publication, 5)
            await asyncio.wait_for(competitor, 5)
        finally:
            release.set()
            for task in (publication, competitor):
                if not task.done():
                    task.cancel()
            await asyncio.gather(publication, competitor, return_exceptions=True)
        current = await repo.get_run_fresh(owner.run_id)
        after = await snapshot(backend, owner.run_id)
        assert current.node_binding.binding_revision == captured[0].binding_revision + 1
        assert after[1:] == (event.sequence, before[2] + 1)
        assert current.node_binding.attempts[admissions[1].task_id].status == "DISPATCHED"
        assert current.node_binding.owner_generation == owner.owner_generation
        assert current.node_binding.owner_id == owner.owner_id
        assert len(await backend.service.event_store._delegate.replay(owner.run_id)) == 1
        print(json.dumps({"ordering": "capture_before_transition", "server_lock_wait": True,
                          "captured": captured[0].model_dump(),
                          "after": current.node_binding.reference().model_dump()}))


async def test_unverified_event_and_foreign_owner_fail_closed():
    async with bound_publisher() as (repo, backend, admissions, owner):
        event = await emit(backend, admissions[0].task_id)
        before = await snapshot(backend, owner.run_id)
        for changes in (
            {"event_id": "not-durable"}, {"sequence": event.sequence + 1},
            {"payload": {"stage": "forged"}}, {"run_id": "FOREIGN-RUN"},
        ):
            with pytest.raises(BindingDenied):
                await backend._publish_runtime_event(event.model_copy(update=changes))
            assert await snapshot(backend, owner.run_id) == before
        for changes in ({"owner_id": "foreign"}, {"owner_generation": 0},
                        {"run_id": "FOREIGN-RUN"}):
            with pytest.raises(BindingDenied):
                await repo.validate_execution(owner.model_copy(update=changes))
        old = await repo.get_run_fresh(owner.run_id)
        await repo.close_execution(owner)
        with pytest.raises(BindingDenied, match="execution owner"):
            await repo.validate_execution(owner)
        closed = await snapshot(backend, owner.run_id)
        current = await repo.get_run_fresh(owner.run_id)
        assert current.node_binding.owner_generation == 2
        with pytest.raises(BindingDenied, match="watermark binding reference"):
            await repo.save_run_with_projection_watermark(
                old, projection_sequence=event.sequence + 1,
                expected_binding_ref=old.node_binding.reference(),
            )
        with pytest.raises(BindingDenied, match="watermark binding reference"):
            await repo.save_run_with_projection_watermark(
                current, projection_sequence=event.sequence + 1, expected_binding_ref=None,
            )
        assert await snapshot(backend, owner.run_id) == closed


async def test_existing_session_cannot_reuse_cached_root_to_accept_stale_ref():
    async with bound_publisher() as (repo, backend, admissions, owner):
        stale = await repo.get_run_fresh(owner.run_id)
        async with backend.sessions() as session, session.begin():
            cached = await session.get(ResearchRunAggregateRow, owner.run_id)
            await repo.dispatch_node(admissions[1])
            with pytest.raises(BindingDenied, match="watermark binding reference"):
                await repo.save_run_with_projection_watermark(
                    stale, projection_sequence=1,
                    expected_binding_ref=stale.node_binding.reference(),
                    publication_session=session,
                )
            assert cached.payload["node_binding"]["binding_revision"] == (
                stale.node_binding.binding_revision + 1
            )
        assert (await snapshot(backend, owner.run_id))[1] == 0
