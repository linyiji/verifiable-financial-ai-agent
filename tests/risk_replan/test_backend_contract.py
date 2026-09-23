"""BR06-11: exact conservation of both former SQLite positive inventories."""

from copy import deepcopy

import pytest
from sqlalchemy import func, select

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
    SQLAlchemyApplicationRepository,
    TaskRow,
)
from src.data.persistence import EvidenceRecordRow
from src.domain.enums import RunStatus, TaskOrigin
from src.domain.node_binding import BindingDenied
from src.domain.runtime_event import RuntimeEventType
from src.infrastructure.database.artifacts import (
    SQLAlchemyRunRecordRepository,
    TaskDependencyGraphKind,
)
from src.infrastructure.database.models import (
    CorrectionRecordRow,
    ReplanRecordRow,
    RuntimeCheckpointRow,
    TaskDependencyRow,
)
from tests.risk_replan.backend_fixture import durable_snapshot, full_fixture
from tests.risk_replan.test_flow import command, fixture
from tests.risk_replan.test_postgresql import database, fresh, pytestmark  # noqa: F401


async def test_replan_released_record_repository_conservation(
    database,  # noqa: F811
    tmp_path,
    monkeypatch,  # noqa: F811
):
    _, sessions = database
    service, value, calls, transport, draft = await full_fixture(tmp_path, sessions, monkeypatch)
    repo, run_id = service.repository, value.run.run_id
    original_receipt = deepcopy(value.confirmed_risk_semantic_binding)
    with transport:
        pending = await service.execute_run(run_id)
        assert pending.run.status is RunStatus.WAITING_REPLAN
        assert pending.artifacts.report is None and pending.artifacts.released_result is None
        await repo.decide_replan(
            run_id, command(pending, "APPROVE"), actor="LOCAL_SINGLE_USER", key="approve"
        )
        await repo.apply_replan(run_id)
        completed = await service.execute_run(run_id)
    assert completed.run.status is RunStatus.RELEASED
    assert completed.confirmed_risk_semantic_binding == original_receipt
    assert completed.runtime.actual_graph.version == 2
    assert len(completed.runtime.planned_graph.tasks) == 7
    assert len(completed.runtime.actual_graph.tasks) == 8
    follow_up = next(
        t for t in completed.runtime.actual_graph.tasks if t.origin is TaskOrigin.REPLAN
    )
    synthesis = next(
        t for t in completed.runtime.actual_graph.tasks if t.task_type == "report_synthesis"
    )
    assert follow_up.dependencies == [follow_up.parent_task_id]
    assert synthesis.dependencies[-1] == follow_up.task_id
    assert follow_up.parent_task_id not in synthesis.dependencies
    events = await service.event_store.replay(run_id)
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))
    assert events[-1].type is RuntimeEventType.RUN_COMPLETED
    assert len(events) >= 10
    checkpoint = await service.checkpoint_store.load_latest(run_id)
    assert checkpoint is not None
    restored_runtime = checkpoint.restore(planned_graph=completed.runtime.planned_snapshot())
    assert restored_runtime.actual_graph.version == 2
    assert restored_runtime.task(synthesis.task_id).dependencies[-1] == follow_up.task_id
    restored = await SQLAlchemyApplicationRepository(sessions).get_run_fresh(run_id)
    assert restored is not None and restored.run.status is RunStatus.RELEASED
    assert (
        restored.runtime.planned_graph.model_dump() == completed.runtime.planned_graph.model_dump()
    )
    assert restored.runtime.actual_graph.model_dump() == completed.runtime.actual_graph.model_dump()
    assert restored.artifacts.projections is not None
    assert restored.artifacts.projections.canonical_record_id == (
        restored.artifacts.canonical_record.record_id
    )
    records = SQLAlchemyRunRecordRepository(sessions)
    assert len(await records.list_tasks(run_id)) == 8
    evidence = await service.evidence_repository.list_by_run(run_id)
    calculations = await records.list_calculations(run_id)
    corrections = await records.list_corrections(run_id)
    replans = await records.list_replans(run_id)
    reviews = await records.list_reviews(run_id)
    assert len(evidence) == 4
    assert len(calculations) == 2
    evidence_ids = {e.evidence_id for e in evidence}
    assert all(set(c.input_evidence_ids) <= evidence_ids for c in calculations)
    assert all(c.review_record_id for c in calculations)
    assert all(c.canonical_record_id for c in calculations)
    assert len(corrections) == len(replans) == len(reviews) == 1
    assert corrections[0].model_dump() == completed.artifacts.corrections[0].model_dump()
    assert replans[0].model_dump() == completed.artifacts.replans[0].model_dump()
    assert reviews[0].model_dump() == completed.artifacts.review.model_dump()
    planned_dependencies = await records.list_task_dependencies(
        run_id, graph_kind=TaskDependencyGraphKind.PLANNED
    )
    actual_dependencies = await records.list_task_dependencies(
        run_id, graph_kind=TaskDependencyGraphKind.ACTUAL
    )
    assert len(planned_dependencies) == 14
    assert len(actual_dependencies) == 15
    planned_edges = {(e.dependency_task_id, e.task_id) for e in planned_dependencies}
    actual_edges = {(e.dependency_task_id, e.task_id) for e in actual_dependencies}
    assert (follow_up.parent_task_id, synthesis.task_id) in planned_edges
    assert (follow_up.parent_task_id, synthesis.task_id) not in actual_edges
    assert (follow_up.parent_task_id, follow_up.task_id) in actual_edges
    assert (follow_up.task_id, synthesis.task_id) in actual_edges
    canonical = await records.get_canonical(run_id)
    released = await records.get_released(run_id)
    assert canonical is not None and released is not None
    assert restored.artifacts.canonical_record is not None
    assert restored.artifacts.released_result is not None
    assert canonical.model_dump() == restored.artifacts.canonical_record.model_dump()
    assert released.model_dump() == restored.artifacts.released_result.model_dump()
    assert released.run_id == canonical.run_id == run_id
    state = restored.node_binding.replan
    assert canonical.replan_refs == [state["active_proposal_id"]]
    assert canonical.actual_graph["version"] == 2 and canonical.planned_graph["version"] == 1
    assert state["finalization"]["fulfilling_child_task_id"] in canonical.task_refs
    candidate = state["candidate"]["output_record"]
    assert candidate["record_id"] in canonical.agent_output_refs
    assert candidate["payload_snapshot"]["structured_output"]["requires_follow_up"]
    assert restored.artifacts.review and restored.artifacts.proofs
    assert restored.artifacts.report and restored.artifacts.released_result
    assert [m for k, m in calls if k == "risk_follow_up"] == ["gpt-5.6-sol"]
    assert sum(k == "valuation_analysis" for k, _ in calls) == 1
    assert sum(k == "report_synthesis" for k, _ in calls) == 1
    async with sessions() as session:
        for row, column, identity in [
            (ResearchObjectRow, "object_id", value.run.research_object_id),
            (ResearchRunDraftRow, "draft_id", draft.draft_id),
            (ResearchGoalRow, "goal_id", value.goal.goal_id),
            (ResearchSchemeSnapshotRow, "scheme_id", value.scheme.scheme_id),
        ]:
            assert (
                await session.scalar(
                    select(func.count()).select_from(row).where(getattr(row, column) == identity)
                )
                == 1
            )
        for row, count in {
            ResearchRunAggregateRow: 1,
            TaskRow: 8,
            TaskDependencyRow: 29,
            RuntimeEventRow: len(events),
            EvidenceRecordRow: 4,
            CalculationRecordRow: 2,
            CorrectionRecordRow: 1,
            ReplanRecordRow: 1,
            ReviewRecordRow: 1,
            CanonicalExecutionRecordRow: 1,
            ReleasedResearchResultRow: 1,
        }.items():
            assert (
                await session.scalar(
                    select(func.count()).select_from(row).where(row.run_id == run_id)
                )
                == count
            )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(RuntimeCheckpointRow)
                .where(RuntimeCheckpointRow.run_id == run_id)
            )
            >= 1
        )
    process_read = await fresh(sessions, run_id)
    assert process_read["root"] == restored.node_binding.model_dump(mode="json")
    assert process_read["events"] == [e.model_dump(mode="json") for e in events]


async def test_replan_stale_writer_preserves_durable_authority(
    database,  # noqa: F811
    tmp_path,
    monkeypatch,  # noqa: F811
):
    from src.infrastructure.database.recovery import RecoveryEvidenceStore

    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, _, transport = await fixture(
        tmp_path, repository=repo, store=RecoveryEvidenceStore(sessions), sessions=sessions
    )
    late = []
    original = repo.commit_node_result

    async def capture(*args, **kwargs):
        task = args[1] if len(args) > 1 else kwargs["task"]
        if task.task_type == "risk_analysis":
            late.append((deepcopy(args), deepcopy(kwargs)))
        return await original(*args, **kwargs)

    monkeypatch.setattr(repo, "commit_node_result", capture)
    run_id = value.run.run_id
    with transport:
        value = await service.execute_run(run_id)
    stale = deepcopy(value)
    for action in ("DECLINE", "REOPEN", "APPROVE"):
        await repo.decide_replan(
            run_id, command(value, action), actor="LOCAL_SINGLE_USER", key=action
        )
        before = await durable_snapshot(sessions, run_id)
        with pytest.raises(BindingDenied):
            await SQLAlchemyApplicationRepository(sessions).save_run(stale)
        assert await durable_snapshot(sessions, run_id) == before
        value = await repo.get_run_fresh(run_id)
    await repo.apply_replan(run_id)
    before = await durable_snapshot(sessions, run_id)
    assert len(late) == 1
    args, kwargs = late[0]
    # Exact historical candidate replay is permitted. A new late Stage-B write
    # from that old admission must be fenced after graph/owner transition.
    with pytest.raises(BindingDenied):
        await repo.bind_resolved_inputs(
            args[0], step_id="late-callback", materials=(), payload={"late": True}
        )
    assert await durable_snapshot(sessions, run_id) == before
    with pytest.raises(BindingDenied):
        await repo.save_run(stale)
    assert await durable_snapshot(sessions, run_id) == before


@pytest.mark.parametrize(
    "field,wrong",
    [
        ("expected_proposal_digest", "sha256:" + "0" * 64),
        ("expected_decision_revision", 999),
        (
            "expected_graph",
            {"run_id": "OTHER", "graph_id": "WRONG", "version": 1, "semantic_hash": "wrong"},
        ),
    ],
)
async def test_postgresql_stale_decisions_preserve_authority(
    database,  # noqa: F811
    tmp_path,
    field,
    wrong,  # noqa: F811
):
    from src.infrastructure.database.recovery import RecoveryEvidenceStore

    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, _, transport = await fixture(
        tmp_path, repository=repo, store=RecoveryEvidenceStore(sessions), sessions=sessions
    )
    with transport:
        value = await service.execute_run(value.run.run_id)
    run_id = value.run.run_id
    for action in ("APPROVE", "DECLINE", "REOPEN"):
        if action == "REOPEN":
            await repo.decide_replan(
                run_id, command(value, "DECLINE"), actor="LOCAL_SINGLE_USER", key="valid-decline"
            )
            value = await repo.get_run_fresh(run_id)
        before = await repo.get_run_fresh(run_id)
        body = {**command(value, action), field: wrong}
        first = await repo.decide_replan(run_id, body, actor="LOCAL_SINGLE_USER", key=action)
        assert first["outcome"] == "REJECTED"
        after = await repo.get_run_fresh(run_id)
        assert after.node_binding.binding_revision == before.node_binding.binding_revision + 1
        assert after.node_binding.frozen_graph == before.node_binding.frozen_graph
        assert after.node_binding.current_results == before.node_binding.current_results
        assert (
            after.node_binding.replan["active_proposal_id"]
            == (before.node_binding.replan["active_proposal_id"])
        )
        committed = await durable_snapshot(sessions, run_id)
        second = await repo.decide_replan(run_id, body, actor="LOCAL_SINGLE_USER", key=action)
        assert {k: v for k, v in second.items() if k != "historical_replay"} == {
            k: v for k, v in first.items() if k != "historical_replay"
        }
        # Exact receipt replay preserves every durable row, including revision.
        assert await durable_snapshot(sessions, run_id) == committed
        replay = await repo.get_run_fresh(run_id)
        assert replay.node_binding.replan == after.node_binding.replan
        assert (await durable_snapshot(sessions, run_id))["runtime_events"] == (
            committed["runtime_events"]
        )
