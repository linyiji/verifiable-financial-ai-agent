from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.main import create_app
from src.application.persistence import (
    CalculationRecordRow,
    CanonicalExecutionRecordRow,
    ReleasedResearchResultRow,
    ResearchGoalRow,
    ResearchSchemeSnapshotRow,
    ReviewRecordRow,
    RuntimeEventRow,
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
    TaskRow,
)
from src.application.service import ResearchApplicationService
from src.domain.enums import EvidenceStatus, ProofStatus, ReplanDecision, RunStatus, TaskOrigin
from src.domain.runtime_event import RuntimeEventType
from src.infrastructure.database.base import Base


async def completed_service() -> tuple[ResearchApplicationService, str]:
    service = ResearchApplicationService()
    research_object = await service.create_object(
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
        idempotency_key="object-nvda",
    )
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Evaluate fundamentals and material risks",
        as_of=date(2026, 9, 3),
        preferences={"depth": "standard"},
    )
    aggregate = await service.confirm_run(
        draft_id=draft.draft_id,
        confirm_scheme=True,
        idempotency_key="run-nvda",
    )
    await service.execute_run(aggregate.run.run_id)
    return service, aggregate.run.run_id


@pytest.mark.asyncio
async def test_offline_vertical_slice_uses_every_frozen_boundary() -> None:
    service, run_id = await completed_service()
    aggregate = await service._aggregate(run_id)

    assert aggregate.run.status is RunStatus.RELEASED
    assert aggregate.artifacts.parallel_task_peak >= 2
    assert aggregate.artifacts.evidence
    assert all(item.status is EvidenceStatus.ACCEPTED for item in aggregate.artifacts.evidence)
    assert {item.capability_id for item in aggregate.artifacts.calculations} == {
        "revenue_growth",
        "ebitda_margin",
    }
    assert all(item.input_evidence_ids for item in aggregate.artifacts.calculations)
    assert len(aggregate.artifacts.corrections) == 1
    assert aggregate.artifacts.corrections[0].task_id.endswith(":fundamentals")
    assert len(aggregate.artifacts.replans) == 1
    assert aggregate.artifacts.replans[0].decision is ReplanDecision.APPROVED
    child = next(
        task for task in aggregate.runtime.actual_graph.tasks if task.origin is TaskOrigin.REPLAN
    )
    assert child.parent_task_id and child.parent_task_id.endswith(":risk")
    risk_task = aggregate.runtime.task(child.parent_task_id)
    synthesis_task = next(
        task
        for task in aggregate.runtime.actual_graph.tasks
        if task.task_type == "report_synthesis"
    )
    assert child.dependencies == [risk_task.task_id]
    assert risk_task.task_id not in synthesis_task.dependencies
    assert child.task_id in synthesis_task.dependencies
    assert all(task.task_id != child.task_id for task in aggregate.runtime.planned_graph.tasks)
    assert aggregate.artifacts.review is not None
    assert aggregate.artifacts.review.status.value == "PASS"
    assert aggregate.artifacts.proofs[0].status is ProofStatus.NOT_IMPLEMENTED

    record = aggregate.artifacts.canonical_record
    projections = aggregate.artifacts.projections
    assert record is not None and projections is not None
    assert projections.financial_review.canonical_record_id == record.record_id
    assert projections.execution_details.canonical_record_id == record.record_id
    assert aggregate.artifacts.released_result is not None
    assert aggregate.artifacts.report is not None
    assert aggregate.artifacts.writeback is not None

    events = await service.event_store.replay(run_id)
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    event_types = [event.type for event in events]
    fundamentals_task_id = f"{run_id}:fundamentals"
    critical_positions = [
        event_types.index(RuntimeEventType.RUN_CREATED),
        event_types.index(RuntimeEventType.SCHEME_GENERATED),
        event_types.index(RuntimeEventType.PLAN_GENERATED),
        next(
            index
            for index, event in enumerate(events)
            if event.type is RuntimeEventType.TASK_STARTED and event.task_id == fundamentals_task_id
        ),
        next(
            index
            for index, event in enumerate(events)
            if event.type is RuntimeEventType.TASK_PROGRESS
            and event.task_id == fundamentals_task_id
        ),
        event_types.index(RuntimeEventType.TASK_SELF_CORRECTING),
        next(
            index
            for index, event in enumerate(events)
            if event.type is RuntimeEventType.TASK_COMPLETED
            and event.task_id == fundamentals_task_id
        ),
        event_types.index(RuntimeEventType.REVIEW_STARTED),
        event_types.index(RuntimeEventType.RELEASE_COMPLETED),
        event_types.index(RuntimeEventType.RUN_COMPLETED),
    ]
    assert critical_positions == sorted(critical_positions)
    generated = next(event for event in events if event.type is RuntimeEventType.SCHEME_GENERATED)
    assert generated.payload["generation_stage"] == "prepare"
    assert generated.payload["retrospective"] is True
    assert generated.payload["scheme_id"] == aggregate.scheme.scheme_id
    progress = [event for event in events if event.type is RuntimeEventType.TASK_PROGRESS]
    assert progress
    assert all(event.payload["stage"] == "dispatched" for event in progress)
    assert event_types.index(RuntimeEventType.REPLAN_REQUESTED) < event_types.index(
        RuntimeEventType.REPLAN_APPROVED
    )
    assert event_types.index(RuntimeEventType.REPLAN_APPROVED) < event_types.index(
        RuntimeEventType.GRAPH_TASK_ADDED
    )
    graph_audit = [
        event
        for event in events
        if event.type
        in {
            RuntimeEventType.GRAPH_TASK_ADDED,
            RuntimeEventType.GRAPH_EDGE_ADDED,
            RuntimeEventType.GRAPH_EDGE_REMOVED,
            RuntimeEventType.GRAPH_VERSION_CHANGED,
        }
    ]
    assert [event.type for event in graph_audit] == [
        RuntimeEventType.GRAPH_TASK_ADDED,
        RuntimeEventType.GRAPH_EDGE_ADDED,
        RuntimeEventType.GRAPH_EDGE_REMOVED,
        RuntimeEventType.GRAPH_EDGE_ADDED,
        RuntimeEventType.GRAPH_VERSION_CHANGED,
    ]
    completion_sequence = {
        event.task_id: event.sequence
        for event in events
        if event.type is RuntimeEventType.TASK_COMPLETED
    }
    start_sequence = {
        event.task_id: event.sequence
        for event in events
        if event.type is RuntimeEventType.TASK_STARTED
    }
    assert (
        completion_sequence[risk_task.task_id]
        < start_sequence[child.task_id]
        < completion_sequence[child.task_id]
        < start_sequence[synthesis_task.task_id]
        < completion_sequence[synthesis_task.task_id]
        < next(event.sequence for event in events if event.type is RuntimeEventType.REVIEW_STARTED)
    )
    assert event_types[-2:] == [
        RuntimeEventType.RELEASE_COMPLETED,
        RuntimeEventType.RUN_COMPLETED,
    ]
    replay = await service.event_store.replay(run_id, after_sequence=events[-3].sequence)
    assert [event.sequence for event in replay] == [events[-2].sequence, events[-1].sequence]


def test_api_routes_are_thin_idempotent_and_return_contract_errors() -> None:
    with TestClient(create_app()) as client:
        object_payload = {
            "symbol": "NVDA",
            "company_name": "NVIDIA Corporation",
            "exchange": "NASDAQ",
        }
        first = client.post(
            "/api/objects",
            json=object_payload,
            headers={"Idempotency-Key": "object-1"},
        )
        second = client.post(
            "/api/objects",
            json=object_payload,
            headers={"Idempotency-Key": "object-1"},
        )
        assert first.status_code == second.status_code == 201
        assert first.json()["object_id"] == second.json()["object_id"] == "OBJ-NVDA"

        invalid = client.post("/api/objects", json={})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
        missing = client.get("/api/objects/OBJ-MISSING")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

        prepared = client.post(
            "/api/research-runs/prepare",
            json={
                "research_object_id": "OBJ-NVDA",
                "research_goal": "Evaluate fundamentals",
                "as_of": "2026-09-03",
                "preferences": {"depth": "standard"},
            },
        )
        assert prepared.status_code == 201
        confirmed = client.post(
            "/api/research-runs",
            json={"draft_id": prepared.json()["draft_id"], "confirm_scheme": True},
            headers={"Idempotency-Key": "run-1"},
        )
        assert confirmed.status_code == 201
        run_id = confirmed.json()["run_id"]
        assert client.get(f"/api/research-runs/{run_id}").json()["status"] == "RELEASED"
        graph = client.get(f"/api/research-runs/{run_id}/graph").json()
        assert len(graph["actual_graph"]["tasks"]) == len(graph["planned_graph"]["tasks"]) + 1
        result = client.get(f"/api/research-runs/{run_id}/result")
        review = client.get(f"/api/research-runs/{run_id}/review-view")
        execution = client.get(f"/api/research-runs/{run_id}/execution-view")
        assert result.status_code == review.status_code == execution.status_code == 200
        assert review.json()["canonical_record_id"] == execution.json()["canonical_record_id"]

        stream = client.get(f"/api/research-runs/{run_id}/events")
        assert stream.status_code == 200
        data_lines = [
            json.loads(line.removeprefix("data: "))
            for line in stream.text.splitlines()
            if line.startswith("data: ")
        ]
        assert [item["sequence"] for item in data_lines] == list(range(1, len(data_lines) + 1))
        resumed = client.get(
            f"/api/research-runs/{run_id}/events",
            headers={"Last-Event-ID": str(data_lines[-2]["sequence"])},
        )
        resumed_data = [
            json.loads(line.removeprefix("data: "))
            for line in resumed.text.splitlines()
            if line.startswith("data: ")
        ]
        assert [item["sequence"] for item in resumed_data] == [data_lines[-1]["sequence"]]


@pytest.mark.asyncio
async def test_sql_repository_restores_released_aggregate(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'application.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repository = SQLAlchemyApplicationRepository(sessions)
    evidence_repository = SessionFactoryEvidenceRepository(sessions)
    service = ResearchApplicationService(
        repository=repository,
        evidence_repository=evidence_repository,
    )
    research_object = await service.create_object(
        symbol="NVDA", company_name="NVIDIA", exchange="NASDAQ"
    )
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Evaluate",
        as_of=date(2026, 9, 3),
        preferences={},
    )
    aggregate = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    await service.execute_run(aggregate.run.run_id)

    restored = await SQLAlchemyApplicationRepository(sessions).get_run(aggregate.run.run_id)
    assert restored is not None
    assert restored.run.status is RunStatus.RELEASED
    assert restored.artifacts.canonical_record is not None
    assert restored.artifacts.projections is not None
    assert restored.artifacts.projections.canonical_record_id == (
        restored.artifacts.canonical_record.record_id
    )
    restored_evidence = await SessionFactoryEvidenceRepository(sessions).list_by_run(
        aggregate.run.run_id
    )
    assert len(restored_evidence) == 4

    expected_counts = {
        ResearchGoalRow: 1,
        ResearchSchemeSnapshotRow: 1,
        TaskRow: 8,
        CalculationRecordRow: 2,
        ReviewRecordRow: 1,
        CanonicalExecutionRecordRow: 1,
        ReleasedResearchResultRow: 1,
    }
    async with sessions() as session:
        for row_type, expected in expected_counts.items():
            count = await session.scalar(select(func.count()).select_from(row_type))
            assert count == expected
        event_count = await session.scalar(select(func.count()).select_from(RuntimeEventRow))
        assert event_count is not None and event_count >= 10
    await engine.dispose()
