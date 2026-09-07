"""Actual production registry authority; no provider or production writes."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from src.agentic.composition import build_research_agent_registry
from src.agentic.llm_integration import (
    PlannerProviderResearchLeadPlanner,
    PlannerProviderSchemeGenerator,
)
from src.agentic.planning_errors import GraphPlanningFailure
from src.agentic.registry import AgentRegistry
from src.agentic.runtime_bindings import GraphRuntimeBindingError, validate_graph_runtime_bindings
from src.agentic.scheme import DeterministicSchemeGenerator
from src.application.persistence import (
    ResearchObjectRow,
    ResearchRunAggregateRow,
    ResearchRunDraftRow,
    RuntimeEventRow,
    TaskRow,
)
from src.application.service import ResearchApplicationService
from src.domain.research_object import ResearchObject
from src.domain.task import PlannedTaskGraph
from src.infrastructure.database.base import Base
from src.infrastructure.database.phase4_product import (
    Phase4IdempotencyOutcomeRow,
    Phase4SchedulerAdmissionRow,
)
from src.phase4_product.contracts import ConfirmResearchRunRequestV1, PrepareResearchRunRequestV1
from src.phase4_product.errors import ProductError
from src.phase4_product.incremental import build_incremental_context
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from tests.phase4.backend_product.test_memory_postgresql import database, pair  # noqa: F401
from tests.unit.llm.test_agentic_llm_integration import (
    FakeProvider,
    research_inputs,
    valid_graph,
    valid_scheme,
)


def registry():
    # Construction performs no invocation; any accidental access fails immediately.
    return build_research_agent_registry(None, None)


def historical():
    return PlannedTaskGraph.model_validate_json(
        Path("tests/fixtures/phase5b_failed_r2_planned_graph.json").read_text()
    )


def canonical(graph, authority):
    tasks = []
    for task in graph.tasks:
        profile = (
            "research_news_analysis" if task.task_type == "evidence_collection" else task.task_type
        )
        agents = authority.for_task_type(profile)
        assert len(agents) == 1
        tasks.append(task.model_copy(update={"assigned_agent": agents[0].agent_id}))
    return graph.model_copy(update={"tasks": tasks})


def test_exact_historical_bad_graph_and_canonical_equivalent():
    old = historical()
    before = old.model_dump()
    with pytest.raises(GraphRuntimeBindingError):
        validate_graph_runtime_bindings(old, registry())
    validate_graph_runtime_bindings(canonical(old, registry()), registry())
    assert old.model_dump() == before


@pytest.mark.parametrize(
    "actor",
    [
        "Peer Analysis Agent",
        "Research News Analysis Agent",
        "Fundamental Analysis Agent",
        "peer analyst",
        "PEER_ANALYST",
        "unknown",
        "fundamental_analyst",
        "",
    ],
)
def test_labels_unknown_missing_and_incompatible_fail(actor):
    graph = canonical(historical(), registry())
    peer = next(t for t in graph.tasks if t.task_type == "peer_analysis")
    graph = graph.model_copy(
        update={
            "tasks": [
                t.model_copy(update={"assigned_agent": actor}) if t.task_id == peer.task_id else t
                for t in graph.tasks
            ]
        }
    )
    with pytest.raises(GraphRuntimeBindingError):
        validate_graph_runtime_bindings(graph, registry())


@pytest.mark.parametrize(
    "actor", ["peer_analyst", "Peer Analysis Agent", "unknown", "fundamental_analyst", None]
)
async def test_planner_receives_actual_registry_and_rejects_labels_without_retry(actor):
    obj, goal = research_inputs()
    scheme = await DeterministicSchemeGenerator().generate(research_object=obj, goal=goal)
    scheme.confirmed_at = datetime.now(UTC)
    response = valid_graph()
    if actor is None:
        del response["tasks"][4]["assigned_agent"]
    else:
        response["tasks"][4]["assigned_agent"] = actor
    provider = FakeProvider([response, valid_graph()])
    authority = registry()
    planner = PlannerProviderResearchLeadPlanner(
        provider, agent_registry=authority, max_validation_attempts=1, fail_closed=True
    )
    if actor == "peer_analyst":
        graph = await planner.plan(run_id="RUN-LOCAL", goal=goal, scheme=scheme)
        validate_graph_runtime_bindings(graph, authority, scheme=scheme)
    else:
        with pytest.raises((GraphRuntimeBindingError, GraphPlanningFailure)):
            await planner.plan(run_id="RUN-LOCAL", goal=goal, scheme=scheme)
    assert len(provider.calls) == 1
    payload = json.loads(provider.calls[0][1][1].content)
    assert payload["available_agents"] == authority.planning_descriptors()
    assert "never display_name" in provider.calls[0][1][0].content
    assert all(
        "agent_id" in d and "supported_task_profiles" in d for d in payload["available_agents"]
    )


def test_registry_extension_is_immediately_authoritative():
    authority = registry()
    authority.register(
        SimpleNamespace(agent_id="new_peer", supported_task_types=frozenset({"peer_analysis"}))
    )
    graph = canonical(historical(), registry())
    graph.tasks[4].assigned_agent = "new_peer"
    validate_graph_runtime_bindings(graph, authority)
    assert "new_peer" in {x["agent_id"] for x in authority.planning_descriptors()}


@pytest.mark.parametrize(
    "mode",
    [
        "historical",
        "unknown",
        "incompatible",
        "badskill",
        "cycle",
        "empty_registry",
        "empty_graph",
        "scheme_mutation",
        "goal_mutation",
        "valid",
    ],
)
async def test_atomic_pre_admission_gate(database, mode):  # noqa: F811
    repo, sessions = database
    memory = await repo.materialize(*pair())
    async with sessions() as session, session.begin():
        conn = await session.connection()
        await conn.run_sync(Base.metadata.create_all)
        row = await session.get(ResearchObjectRow, "OBJ-A")
        row.payload = ResearchObject(
            object_id="OBJ-A", symbol="NVDA", company_name="NVIDIA", exchange="NASDAQ"
        ).model_dump(mode="json")
    context = build_incremental_context(
        memory.current_view,
        object_id="OBJ-A",
        base_run_id="RUN-A",
        base_view_id="RVV-RUN-A",
        target_as_of=date(2026, 9, 7),
    )
    proposal = valid_scheme()
    proposal["incremental_decisions"] = [
        dict(source_identity=d.source_identity, decision=d.decision, reason=d.reason)
        for d in context.decisions
    ]
    provider = FakeProvider([proposal])
    authority = registry()

    class LocalPlanner:
        def plan(self, *, run_id, goal, scheme):
            if mode == "scheme_mutation":
                scheme.scheme_id = "SCHEME-CHANGED"
            if mode == "goal_mutation":
                goal.goal_text = "Changed semantics"
            graph = historical() if mode == "historical" else canonical(historical(), authority)
            old_id = graph.run_id
            tasks = [
                t.model_copy(
                    update={
                        "run_id": run_id,
                        "task_id": t.task_id.replace(old_id, run_id),
                        "dependencies": [d.replace(old_id, run_id) for d in t.dependencies],
                    }
                )
                for t in graph.tasks
            ]
            if mode == "unknown":
                tasks[4].assigned_agent = "unknown"
            if mode == "incompatible":
                tasks[4].assigned_agent = tasks[3].assigned_agent
            if mode == "badskill":
                tasks[4].skill_id = "risk_analysis_v1"
            if mode == "cycle":
                tasks[0].dependencies = [tasks[-1].task_id]
            if mode == "empty_graph":
                tasks = []
            return graph.model_copy(
                update={"run_id": run_id, "graph_id": run_id + ":planned", "tasks": tasks}
            )

    backend = PostgreSQLPhase4ProductBackend(
        sessions=sessions,
        service=ResearchApplicationService(
            agent_registry=AgentRegistry() if mode == "empty_registry" else authority
        ),
        incremental_scheme_generator=PlannerProviderSchemeGenerator(provider),
        incremental_planner=LocalPlanner(),
    )
    draft = await backend.prepare_run(
        PrepareResearchRunRequestV1(
            research_object_id="OBJ-A",
            research_goal="Update current fundamentals",
            as_of="2026-09-07",
            base_run_id="RUN-A",
            base_research_view_version="RVV-RUN-A",
        ),
        idempotency_key="prepare-local",
        request_id=None,
    )
    tables = [
        ResearchRunAggregateRow,
        TaskRow,
        RuntimeEventRow,
        Phase4IdempotencyOutcomeRow,
        Phase4SchedulerAdmissionRow,
    ]

    async def counts():
        async with sessions() as session:
            return [
                await session.scalar(select(func.count()).select_from(table)) for table in tables
            ]

    before = await counts()
    request = ConfirmResearchRunRequestV1(
        research_object_id="OBJ-A",
        draft_id=draft.draft_id,
        draft_hash=draft.draft_hash,
        draft_version=1,
        confirm_scheme=True,
    )
    if mode != "valid":
        with pytest.raises(ProductError) as caught:
            await backend.confirm_run(request, idempotency_key="confirm-local", request_id=None)
        assert caught.value.details["reason_code"] == "GRAPH_RUNTIME_BINDING_INVALID"
        assert await counts() == before
        async with sessions() as session:
            stored = await session.get(ResearchRunDraftRow, draft.draft_id)
            assert stored.consumed_at is None and stored.consumed_run_id is None
            assert stored.payload == draft.model_dump(mode="json")
    else:
        result = await backend.confirm_run(
            request, idempotency_key="confirm-local", request_id=None
        )
        assert (await counts())[0] == before[0] + 1
        async with sessions() as session:
            stored = await session.get(ResearchRunDraftRow, draft.draft_id)
            assert stored.consumed_run_id == result.admission.run_id
            row = await session.get(ResearchRunAggregateRow, result.admission.run_id)
            assert row.payload["scheme"][
                "incremental_context"
            ] == draft.scheme_snapshot.incremental_context.model_dump(mode="json")
    assert len(provider.calls) == 1  # local Scheme fixture only; no model/Graph generation
