"""A1R terminal failure revision lineage on a disposable PostgreSQL schema."""

import asyncio
import os
from copy import deepcopy

import pytest
from sqlalchemy import delete, select, text

from src.application.persistence import (
    ResearchRunAggregateRow,
    RuntimeEventRow,
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
    TaskRow,
    TerminalSettlementBudget,
)
from src.application.terminal_failure import failure_command
from src.domain.node_binding import BindingDenied, digest
from src.domain.runtime_event import RuntimeEventType
from src.infrastructure.database.models import TaskDependencyRow
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from tests.external_failure_resume.runtime_fixture import legal_fixture
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL required",
)


async def test_terminal_revision_lineage_and_full_set(database, tmp_path, monkeypatch):  # noqa: F811
    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    store = PostgresRuntimeEventStore(sessions)
    service, initial, _ = await legal_fixture(
        tmp_path, repository=repo, evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions), event_store=store,
    )
    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    captured = {}
    finalize = repo.finalize_failure

    async def capture(owner, proposed, **kwargs):
        captured.update(owner=owner, proposed=deepcopy(proposed), kwargs=kwargs)
        return await finalize(owner, proposed, **kwargs)

    monkeypatch.setattr(repo, "finalize_failure", capture)
    try:
        for _ in range(2):
            try:
                await service.execute_run(initial.run.run_id)
            except ExceptionGroup:
                pass
            if captured:
                break
        assert captured
        owner = captured["owner"]
        proposed = captured["proposed"]
        kwargs = captured["kwargs"]
        command = failure_command(owner, proposed, kwargs["unknown"], kwargs["payload"])
        async with sessions() as session:
            row = await session.get(ResearchRunAggregateRow, owner.run_id)
            event = await session.get(RuntimeEventRow, command["event_id"])
            assert event is not None
            revision = event.payload["payload"]["terminal_failure"][
                "terminal_failure_projection_revision"
            ]
            assert revision == row.projection_revision
            assert row.projection_sequence == event.sequence
            schema = await session.scalar(text("SELECT current_schema()"))
            command["search_path"] = schema
            command["baseline"] = {"projection_revision": revision - 1}
        replay = await repo.finalize_failure(owner, proposed, **kwargs)
        assert replay.event_id == command["event_id"]
        readback = await repo._read_failure_outcome(
            owner, command, TerminalSettlementBudget(asyncio.get_running_loop().time() + 30),
        )
        assert readback.event_id == replay.event_id
        command["baseline"]["projection_revision"] = revision
        with pytest.raises(BindingDenied, match="INTEGRITY_STOP"):
            await repo._read_failure_outcome(
                owner, command,
                TerminalSettlementBudget(asyncio.get_running_loop().time() + 30),
            )
        command["baseline"]["projection_revision"] = revision - 1
        current = await repo.get_run_fresh(owner.run_id)
        for offset in (1, 2):
            await backend._publish_latest_projection_watermark(
                owner.run_id, expected_binding_ref=current.node_binding.reference(),
            )
            async with sessions() as session:
                row = await session.get(ResearchRunAggregateRow, owner.run_id)
                assert row.projection_revision == revision + offset
                assert row.projection_sequence == replay.sequence
            again = await repo.finalize_failure(owner, proposed, **kwargs)
            assert again.event_id == replay.event_id

        async def reject(mutator):
            async with sessions() as session, session.begin():
                row = await session.get(ResearchRunAggregateRow, owner.run_id)
                event = await session.get(RuntimeEventRow, command["event_id"])
                await mutator(session, row, event)
                await session.flush()
                with pytest.raises(BindingDenied, match="INTEGRITY_STOP"):
                    await repo._validate_failure_full_set(session, row, command)
                await session.rollback()

        async def revision_regression(_session, row, _event):
            row.projection_revision = revision - 1

        async def sequence_change(_session, row, _event):
            row.projection_sequence += 1

        async def status_change(_session, row, _event):
            row.status = "RUNNING"

        async def serialized_status_change(_session, row, _event):
            payload = deepcopy(row.payload)
            payload["runtime"]["run_status"] = "RUNNING"
            row.payload = payload

        async def payload_change(_session, _row, event):
            payload = deepcopy(event.payload)
            payload["payload"]["failure_code"] = "CHANGED"
            event.payload = payload

        async def event_change(_session, _row, event):
            payload = deepcopy(event.payload)
            payload["payload"]["terminal_failure"]["event_id"] = "EVT-OTHER"
            event.payload = payload

        async def owner_change(_session, row, _event):
            payload = deepcopy(row.payload)
            payload["node_binding"]["owner_generation"] += 1
            row.payload = payload

        async def fence_change(_session, row, _event):
            payload = deepcopy(row.payload)
            payload["node_binding"]["binding_revision"] += 1
            row.payload = payload

        async def child_missing(session, _row, _event):
            await session.execute(delete(TaskRow).where(TaskRow.run_id == owner.run_id))

        async def anchor_missing(_session, _row, event):
            payload = deepcopy(event.payload)
            failure = payload["payload"]["terminal_failure"]
            failure.pop("terminal_failure_projection_revision")
            failure.pop("payload_digest")
            failure["payload_digest"] = digest(payload["payload"], "terminal-failure/v1")
            event.payload = payload

        for mutator in (
            revision_regression, sequence_change, status_change,
            serialized_status_change, payload_change, event_change,
            owner_change, fence_change, child_missing, anchor_missing,
        ):
            await reject(mutator)

        async def non_latest(session, _row, event):
            session.add(RuntimeEventRow(
                event_id="EVT-A1R-NONLATEST", run_id=owner.run_id,
                sequence=event.sequence + 1, payload=deepcopy(event.payload),
            ))

        async def public_reject(mutator):
            async with sessions() as session:
                row = await session.get(ResearchRunAggregateRow, owner.run_id)
                event = await session.get(RuntimeEventRow, command["event_id"])
                original = (
                    deepcopy(row.payload), row.status, row.projection_revision,
                    row.projection_sequence, deepcopy(event.payload),
                )
                children = [
                    (item.task_id, deepcopy(item.payload))
                    for item in await session.scalars(select(TaskRow).where(
                        TaskRow.run_id == owner.run_id,
                    ))
                ]
                dependencies = [
                    (item.graph_kind, item.task_id, item.position,
                     item.dependency_task_id)
                    for item in await session.scalars(select(TaskDependencyRow).where(
                        TaskDependencyRow.run_id == owner.run_id,
                    ))
                ]
            try:
                async with sessions() as session, session.begin():
                    row = await session.get(ResearchRunAggregateRow, owner.run_id)
                    event = await session.get(RuntimeEventRow, command["event_id"])
                    await mutator(session, row, event)
                with pytest.raises(BindingDenied, match="INTEGRITY_STOP"):
                    await repo.finalize_failure(owner, proposed, **kwargs)
            finally:
                async with sessions() as session, session.begin():
                    row = await session.get(ResearchRunAggregateRow, owner.run_id)
                    event = await session.get(RuntimeEventRow, command["event_id"])
                    row.payload, row.status, row.projection_revision, row.projection_sequence = (
                        original[:4]
                    )
                    event.payload = original[4]
                    await session.execute(delete(RuntimeEventRow).where(
                        RuntimeEventRow.event_id == "EVT-A1R-NONLATEST",
                    ))
                    existing = set(await session.scalars(select(TaskRow.task_id).where(
                        TaskRow.run_id == owner.run_id,
                    )))
                    session.add_all(
                        TaskRow(task_id=task_id, run_id=owner.run_id, payload=payload)
                        for task_id, payload in children if task_id not in existing
                    )
                    await session.flush()
                    actual_dependencies = {
                        (item.graph_kind, item.task_id, item.position,
                         item.dependency_task_id)
                        for item in await session.scalars(select(TaskDependencyRow).where(
                            TaskDependencyRow.run_id == owner.run_id,
                        ))
                    }
                    session.add_all(
                        TaskDependencyRow(
                            run_id=owner.run_id, graph_kind=kind, task_id=task_id,
                            position=position, dependency_task_id=dependency,
                        )
                        for kind, task_id, position, dependency in dependencies
                        if (kind, task_id, position, dependency) not in actual_dependencies
                    )
            again = await repo.finalize_failure(owner, proposed, **kwargs)
            assert again.event_id == replay.event_id

        for mutator in (
            revision_regression, sequence_change, status_change,
            anchor_missing, child_missing, non_latest,
        ):
            await public_reject(mutator)

        with pytest.raises(Exception, match="terminal"):
            await store.emit(
                run_id=owner.run_id, event_type=RuntimeEventType.RUN_FAILED,
                payload={"status": "FAILED"},
            )
        with pytest.raises(Exception, match="terminal"):
            await store.emit(
                run_id=owner.run_id, event_type=RuntimeEventType.TASK_STARTED,
                payload={},
            )
    finally:
        await backend.close()
