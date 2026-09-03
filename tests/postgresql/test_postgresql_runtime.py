from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from importlib.util import find_spec
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.evidence_collection import (
    EvidenceAcquisitionScope,
    EvidenceCollector,
    EvidenceTaskAcquisitionResult,
)
from src.application.persistence import (
    CalculationRecordRow,
    CanonicalExecutionRecordRow,
    ReleasedResearchResultRow,
    ResearchGoalRow,
    ResearchObjectRow,
    ResearchRunAggregateRow,
    ResearchRunDraftRow,
    ResearchSchemeSnapshotRow,
    ReviewRecordRow,
    RuntimeEventRow,
    TaskRow,
)
from src.application.service import ResearchApplicationService
from src.data.ingestion import EvidenceIngestionResult
from src.data.persistence import EvidenceRecordRow
from src.domain.enums import RunStatus, TaskOrigin
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.infrastructure.config.settings import Settings
from src.infrastructure.database.artifacts import TaskDependencyGraphKind
from src.infrastructure.database.composition import (
    PostgreSQLPersistence,
    create_postgresql_persistence,
)
from src.infrastructure.database.models import (
    CorrectionRecordRow,
    ReplanRecordRow,
    RuntimeCheckpointRow,
    TaskDependencyRow,
)
from src.runtime.events import EventSequenceError
from src.runtime.sse import runtime_event_stream

DATABASE_SETTINGS = Settings().database
POSTGRES_AVAILABLE = (
    make_url(DATABASE_SETTINGS.url).get_backend_name() == "postgresql"
    and find_spec("asyncpg") is not None
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="Unified Settings PostgreSQL URL and asyncpg are required for real PostgreSQL tests",
)


@asynccontextmanager
async def _isolated_persistence() -> AsyncIterator[
    tuple[PostgreSQLPersistence, list[str], list[str]]
]:
    persistence = create_postgresql_persistence(
        DATABASE_SETTINGS,
        event_poll_interval_seconds=0.01,
    )
    object_ids: list[str] = []
    run_ids: list[str] = []
    try:
        yield persistence, object_ids, run_ids
    finally:
        async with persistence.engine.begin() as connection:
            if run_ids:
                await connection.execute(
                    delete(ResearchRunAggregateRow).where(
                        ResearchRunAggregateRow.run_id.in_(run_ids)
                    )
                )
            if object_ids:
                await connection.execute(
                    delete(ResearchObjectRow).where(ResearchObjectRow.object_id.in_(object_ids))
                )
        await persistence.close()


def _postgres_service(persistence: PostgreSQLPersistence) -> ResearchApplicationService:
    service = ResearchApplicationService(
        repository=persistence.application_repository,
        evidence_repository=persistence.evidence_repository,
    )
    # Coordinator constructor injection lands separately in fe6a120. Attribute assignment keeps
    # this isolated branch compatible with its frozen pre-composition base without editing service.
    service.event_store = persistence.event_store
    service.checkpoint_store = persistence.checkpoint_store
    service.evidence_collector = _FixtureSymbolAlias(service.evidence_collector)
    return service


class _FixtureSymbolAlias:
    """Keep test object IDs unique while reusing the controlled NVDA fixture."""

    def __init__(self, delegate: EvidenceCollector) -> None:
        self._delegate = delegate

    async def collect(
        self,
        *,
        symbol: str,
        run_id: str,
        object_id: str,
        as_of: date,
    ) -> EvidenceIngestionResult:
        del symbol
        return await self._delegate.collect(
            symbol="NVDA",
            run_id=run_id,
            object_id=object_id,
            as_of=as_of,
        )

    async def collect_scope(
        self,
        *,
        task_id: str,
        scope: EvidenceAcquisitionScope,
        symbol: str,
        run_id: str,
        object_id: str,
        as_of: date,
    ) -> EvidenceTaskAcquisitionResult:
        del symbol
        method = self._delegate.collect_scope
        return await method(
            task_id=task_id,
            scope=scope,
            symbol="NVDA",
            run_id=run_id,
            object_id=object_id,
            as_of=as_of,
        )


async def _confirmed_run(
    persistence: PostgreSQLPersistence,
    *,
    object_ids: list[str],
    run_ids: list[str],
) -> tuple[ResearchApplicationService, str, str, str]:
    marker = uuid4().hex[:12].upper()
    service = _postgres_service(persistence)
    research_object = await service.create_object(
        symbol=f"P{marker}",
        company_name=f"PostgreSQL Integration {marker}",
        exchange="TEST",
    )
    object_ids.append(research_object.object_id)
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Verify durable PostgreSQL execution and restart semantics",
        as_of=date(2026, 9, 4),
        preferences={"test_marker": marker},
    )
    aggregate = await service.confirm_run(
        draft_id=draft.draft_id,
        confirm_scheme=True,
    )
    run_ids.append(aggregate.run.run_id)
    return service, research_object.object_id, draft.draft_id, aggregate.run.run_id


@pytest.mark.asyncio
async def test_real_postgresql_version_and_alembic_head() -> None:
    async with _isolated_persistence() as (persistence, _, _):
        assert repr(persistence) == "PostgreSQLPersistence(backend='postgresql', adapters=ready)"
        async with persistence.engine.connect() as connection:
            row = (
                await connection.execute(text("SELECT version(), current_database(), current_user"))
            ).one()
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))

        assert row[0].startswith("PostgreSQL 16.15")
        assert row[1] == "verifiable_financial_agent"
        assert row[2] == "vfa"
        assert revision == "20260904_0003"


@pytest.mark.asyncio
async def test_real_postgresql_atomic_event_sequence_and_sse_replay() -> None:
    async with _isolated_persistence() as (persistence, object_ids, run_ids):
        _, _, _, run_id = await _confirmed_run(
            persistence,
            object_ids=object_ids,
            run_ids=run_ids,
        )
        initial = await persistence.event_store.replay(run_id)
        emitted = await asyncio.gather(
            *(
                persistence.event_store.emit(
                    run_id=run_id,
                    event_type=RuntimeEventType.TASK_PROGRESS,
                    payload={"concurrency_probe": index},
                )
                for index in range(50)
            )
        )
        replay = await persistence.event_store.replay(run_id)
        sequences = [event.sequence for event in replay]

        assert sorted(event.sequence for event in emitted) == list(
            range(len(initial) + 1, len(initial) + 51)
        )
        assert sequences == list(range(1, len(replay) + 1))
        assert len(sequences) == len(set(sequences))
        async with persistence.sessions() as session:
            count, distinct_count, minimum, maximum = (
                await session.execute(
                    select(
                        func.count(RuntimeEventRow.sequence),
                        func.count(func.distinct(RuntimeEventRow.sequence)),
                        func.min(RuntimeEventRow.sequence),
                        func.max(RuntimeEventRow.sequence),
                    ).where(RuntimeEventRow.run_id == run_id)
                )
            ).one()
        assert count == distinct_count == maximum == len(replay)
        assert minimum == 1

        with pytest.raises(EventSequenceError, match="database rejected"):
            await persistence.event_store.append(
                RuntimeEvent(
                    event_id=f"EVT-{uuid4()}",
                    run_id=run_id,
                    type=RuntimeEventType.TASK_PROGRESS,
                    sequence=len(replay) + 2,
                )
            )

        stream = runtime_event_stream(
            store=persistence.event_store,
            run_id=run_id,
            last_event_id=str(len(replay) - 1),
            heartbeat_seconds=0.1,
        )
        payload = await anext(stream)
        await stream.aclose()
        assert payload.startswith(f"id: {len(replay)}\n")
        assert (
            await persistence.event_store.resolve_resume_sequence(run_id, emitted[0].event_id)
            == emitted[0].sequence
        )


@pytest.mark.asyncio
async def test_real_postgresql_full_run_restart_graph_and_lineage_restore() -> None:
    async with _isolated_persistence() as (persistence, object_ids, run_ids):
        service, object_id, draft_id, run_id = await _confirmed_run(
            persistence,
            object_ids=object_ids,
            run_ids=run_ids,
        )
        completed = await service.execute_run(run_id)

        assert completed.run.status is RunStatus.RELEASED
        assert completed.runtime.actual_graph.version == 2
        assert len(completed.runtime.planned_graph.tasks) == 7
        assert len(completed.runtime.actual_graph.tasks) == 8
        follow_up = next(
            task
            for task in completed.runtime.actual_graph.tasks
            if task.origin is TaskOrigin.REPLAN
        )
        synthesis = next(
            task
            for task in completed.runtime.actual_graph.tasks
            if task.task_type == "report_synthesis"
        )
        assert follow_up.dependencies == [follow_up.parent_task_id]
        assert synthesis.dependencies[-1] == follow_up.task_id
        assert follow_up.parent_task_id not in synthesis.dependencies

        events = await persistence.event_store.replay(run_id)
        assert [event.sequence for event in events] == list(range(1, len(events) + 1))
        assert events[-1].type is RuntimeEventType.RUN_COMPLETED
        checkpoint = await persistence.checkpoint_store.load_latest(run_id)
        assert checkpoint is not None
        restored_runtime = checkpoint.restore(planned_graph=completed.runtime.planned_snapshot())
        assert restored_runtime.actual_graph.version == 2
        assert restored_runtime.task(synthesis.task_id).dependencies[-1] == follow_up.task_id

        restarted_repository = type(persistence.application_repository)(persistence.sessions)
        restored = await restarted_repository.get_run(run_id)
        assert restored is not None and restored.run.status is RunStatus.RELEASED
        assert restored.runtime.planned_graph.model_dump() == (
            completed.runtime.planned_graph.model_dump()
        )
        assert restored.runtime.actual_graph.model_dump() == (
            completed.runtime.actual_graph.model_dump()
        )
        evidence = await persistence.evidence_repository.list_by_run(run_id)
        calculations = await persistence.run_record_repository.list_calculations(run_id)
        corrections = await persistence.run_record_repository.list_corrections(run_id)
        replans = await persistence.run_record_repository.list_replans(run_id)
        reviews = await persistence.run_record_repository.list_reviews(run_id)
        planned_dependencies = await persistence.run_record_repository.list_task_dependencies(
            run_id,
            graph_kind=TaskDependencyGraphKind.PLANNED,
        )
        actual_dependencies = await persistence.run_record_repository.list_task_dependencies(
            run_id,
            graph_kind=TaskDependencyGraphKind.ACTUAL,
        )
        evidence_ids = {record.evidence_id for record in evidence}
        assert len(evidence) == 4
        assert len(calculations) == 2
        assert all(set(record.input_evidence_ids) <= evidence_ids for record in calculations)
        assert all(record.review_record_id for record in calculations)
        assert all(record.canonical_record_id for record in calculations)
        assert len(corrections) == len(replans) == len(reviews) == 1
        assert corrections[0].model_dump() == completed.artifacts.corrections[0].model_dump()
        assert replans[0].model_dump() == completed.artifacts.replans[0].model_dump()
        assert reviews[0].model_dump() == completed.artifacts.review.model_dump()
        planned_edges = {(edge.dependency_task_id, edge.task_id) for edge in planned_dependencies}
        actual_edges = {(edge.dependency_task_id, edge.task_id) for edge in actual_dependencies}
        assert len(planned_dependencies) == 14
        assert len(actual_dependencies) == 15
        assert (follow_up.parent_task_id, synthesis.task_id) in planned_edges
        assert (follow_up.parent_task_id, synthesis.task_id) not in actual_edges
        assert (follow_up.parent_task_id, follow_up.task_id) in actual_edges
        assert (follow_up.task_id, synthesis.task_id) in actual_edges

        canonical = await persistence.run_record_repository.get_canonical(run_id)
        released = await persistence.run_record_repository.get_released(run_id)
        assert canonical is not None and released is not None
        assert restored.artifacts.canonical_record is not None
        assert restored.artifacts.released_result is not None
        assert canonical.model_dump() == restored.artifacts.canonical_record.model_dump()
        assert released.model_dump() == restored.artifacts.released_result.model_dump()
        assert released.run_id == canonical.run_id == run_id

        async with persistence.sessions() as session:
            counts = {
                "objects": await session.scalar(
                    select(func.count())
                    .select_from(ResearchObjectRow)
                    .where(ResearchObjectRow.object_id == object_id)
                ),
                "drafts": await session.scalar(
                    select(func.count())
                    .select_from(ResearchRunDraftRow)
                    .where(ResearchRunDraftRow.draft_id == draft_id)
                ),
                "goals": await session.scalar(
                    select(func.count())
                    .select_from(ResearchGoalRow)
                    .where(ResearchGoalRow.goal_id == completed.goal.goal_id)
                ),
                "schemes": await session.scalar(
                    select(func.count())
                    .select_from(ResearchSchemeSnapshotRow)
                    .where(ResearchSchemeSnapshotRow.scheme_id == completed.scheme.scheme_id)
                ),
                "runs": await session.scalar(
                    select(func.count())
                    .select_from(ResearchRunAggregateRow)
                    .where(ResearchRunAggregateRow.run_id == run_id)
                ),
                "tasks": await _run_count(session, TaskRow, run_id),
                "task_dependencies": await _run_count(session, TaskDependencyRow, run_id),
                "events": await _run_count(session, RuntimeEventRow, run_id),
                "evidence": await _run_count(session, EvidenceRecordRow, run_id),
                "calculations": await _run_count(session, CalculationRecordRow, run_id),
                "corrections": await _run_count(session, CorrectionRecordRow, run_id),
                "replans": await _run_count(session, ReplanRecordRow, run_id),
                "reviews": await _run_count(session, ReviewRecordRow, run_id),
                "canonical": await _run_count(session, CanonicalExecutionRecordRow, run_id),
                "released": await _run_count(session, ReleasedResearchResultRow, run_id),
                "checkpoints": await _run_count(session, RuntimeCheckpointRow, run_id),
            }
        assert counts["objects"] == counts["drafts"] == counts["goals"] == 1
        assert counts["schemes"] == counts["runs"] == 1
        assert counts["tasks"] == 8
        assert counts["task_dependencies"] == 29
        assert counts["events"] == len(events)
        assert counts["evidence"] == 4
        assert counts["calculations"] == 2
        assert counts["corrections"] == counts["replans"] == counts["reviews"] == 1
        assert counts["canonical"] == counts["released"] == 1
        assert counts["checkpoints"] >= 1


async def _run_count(session: AsyncSession, row_type: type[Any], run_id: str) -> int:
    value = await session.scalar(
        select(func.count()).select_from(row_type).where(row_type.run_id == run_id)
    )
    assert value is not None
    return value
