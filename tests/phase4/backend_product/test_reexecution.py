"""Re-execution stays inside disposable PostgreSQL schemas; scheduler never starts."""

import copy
import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select

from src.agentic.composition import build_research_agent_registry
from src.agentic.llm_integration import PlannerProviderSchemeGenerator
from src.application.persistence import (
    ResearchObjectRow,
    ResearchRunAggregateRow,
    ResearchRunDraftRow,
    RuntimeEventRow,
    TaskRow,
)
from src.application.service import ResearchApplicationService
from src.domain.research_object import ResearchObject
from src.infrastructure.database.base import Base
from src.infrastructure.database.phase4_product import (
    Phase4IdempotencyOutcomeRow,
    Phase4SchedulerAdmissionRow,
)
from src.infrastructure.database.reexecution import ReexecutionAuthorizationRow
from src.phase4_product.contracts import ConfirmResearchRunRequestV1, PrepareResearchRunRequestV1
from src.phase4_product.errors import ProductError
from src.phase4_product.incremental import build_incremental_context
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from src.phase4_product.reexecution import AuthorizeReexecutionRequest, ReexecuteRequest
from tests.phase4.backend_product.test_graph_runtime_bindings import canonical, historical
from tests.phase4.backend_product.test_memory_postgresql import database, pair  # noqa: F401
from tests.unit.llm.test_agentic_llm_integration import FakeProvider, valid_scheme


@pytest.fixture
async def prepared(database):  # noqa: F811
    memory_repo, sessions = database
    memory = await memory_repo.materialize(*pair())

    def migrate(conn):
        spec = importlib.util.spec_from_file_location(
            "reexec_migration", Path("alembic/versions/20260907_0011_reexecution_authorizations.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
        Base.metadata.create_all(conn)

    async with sessions() as s, s.begin():
        await (await s.connection()).run_sync(migrate)
        obj = await s.get(ResearchObjectRow, "OBJ-A")
        obj.payload = ResearchObject(
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
    registry = build_research_agent_registry(None, None)

    class Planner:
        calls = 0
        invalid = False

        def plan(self, *, run_id, goal, scheme):
            self.calls += 1
            old = canonical(historical(), registry)
            tasks = [
                t.model_copy(
                    update={
                        "run_id": run_id,
                        "task_id": t.task_id.replace(old.run_id, run_id),
                        "dependencies": [d.replace(old.run_id, run_id) for d in t.dependencies],
                    }
                )
                for t in old.tasks
            ]
            if self.invalid:
                tasks[4].assigned_agent = "Peer Analysis Agent"
            return old.model_copy(
                update={"run_id": run_id, "graph_id": run_id + ":planned", "tasks": tasks}
            )

    planner = Planner()
    backend = PostgreSQLPhase4ProductBackend(
        sessions=sessions,
        service=ResearchApplicationService(agent_registry=registry),
        incremental_scheme_generator=PlannerProviderSchemeGenerator(provider),
        incremental_planner=planner,
    )
    draft = await backend.prepare_run(
        PrepareResearchRunRequestV1(
            research_object_id="OBJ-A",
            research_goal="Update current fundamentals",
            as_of="2026-09-07",
            base_run_id="RUN-A",
            base_research_view_version="RVV-RUN-A",
        ),
        idempotency_key="prepare",
        request_id=None,
    )
    admitted = await backend.confirm_run(
        ConfirmResearchRunRequestV1(
            research_object_id="OBJ-A",
            draft_id=draft.draft_id,
            draft_hash=draft.draft_hash,
            draft_version=1,
            confirm_scheme=True,
        ),
        idempotency_key="confirm",
        request_id=None,
    )
    prior = admitted.admission.run_id
    async with sessions() as s, s.begin():
        row = await s.get(ResearchRunAggregateRow, prior)
        payload = copy.deepcopy(row.payload)
        payload["run"]["status"] = "FAILED"
        payload["run"]["completed_at"] = datetime.now(UTC).isoformat()
        payload["runtime"]["run_status"] = "FAILED"
        row.status, row.payload = "FAILED", payload
    planner.calls = 0
    return backend, sessions, prior, draft, planner


async def snapshot(sessions):
    async with sessions() as s:
        return {
            cls.__tablename__: [
                (getattr(r, "run_id", None), getattr(r, "payload", None))
                for r in await s.scalars(select(cls))
            ]
            for cls in (
                ResearchRunAggregateRow,
                ResearchRunDraftRow,
                TaskRow,
                RuntimeEventRow,
                Phase4SchedulerAdmissionRow,
                Phase4IdempotencyOutcomeRow,
            )
        }


async def authorize(backend, prior, key="auth"):
    return await backend.authorize_reexecution(
        prior,
        AuthorizeReexecutionRequest(research_object_id="OBJ-A", authorize_reexecution=True),
        idempotency_key=key,
    )


async def test_atomic_reexecution_replay_and_history(prepared):
    backend, sessions, prior, draft, planner = prepared
    before = await snapshot(sessions)
    auth = await authorize(backend, prior)
    assert await authorize(backend, prior) == auth
    request = ReexecuteRequest(research_object_id="OBJ-A", authorization_id=auth.authorization_id)
    result = await backend.reexecute_run(prior, request, idempotency_key="admit")
    replay = await backend.reexecute_run(prior, request, idempotency_key="admit")
    assert replay.run_id == result.run_id != prior and replay.idempotency_replayed
    assert planner.calls == 1
    async with sessions() as s:
        old = await s.get(ResearchRunAggregateRow, prior)
        new = await s.get(ResearchRunAggregateRow, result.run_id)
        assert old.payload == next(p for rid, p in before["research_runs"] if rid == prior)
        assert new.payload["scheme"] == old.payload["scheme"]
        assert new.payload["goal"] == old.payload["goal"]
        assert new.payload["run"]["base_run_id"] == "RUN-A"
        assert new.payload["run"]["reexecution_of_run_id"] == prior
        assert new.payload["run"]["planned_graph_id"] != old.payload["run"]["planned_graph_id"]
        assert (await s.get(ResearchRunDraftRow, draft.draft_id)).consumed_run_id == prior
        assert (
            await s.get(ReexecutionAuthorizationRow, auth.authorization_id)
        ).consumed_by_run_id == result.run_id
        assert await s.scalar(select(func.count()).select_from(ResearchRunDraftRow)) == 1
    assert (await backend.get_run(result.run_id)).reexecution_of_run_id == prior
    # Reconstructed public projection remains usable without starting scheduler execution.
    await backend.get_projection(result.run_id)
    with pytest.raises(ProductError):
        await backend.reexecute_run(prior, request, idempotency_key="different")
    with pytest.raises(ProductError):
        await backend.authorize_reexecution(
            "RUN-A",
            AuthorizeReexecutionRequest(research_object_id="OBJ-A", authorize_reexecution=True),
            idempotency_key="auth",
        )


async def test_invalid_graph_is_atomic_and_authorization_survives(prepared):
    backend, sessions, prior, draft, planner = prepared
    auth = await authorize(backend, prior)
    before = await snapshot(sessions)
    planner.invalid = True
    with pytest.raises(ProductError) as caught:
        await backend.reexecute_run(
            prior,
            ReexecuteRequest(research_object_id="OBJ-A", authorization_id=auth.authorization_id),
            idempotency_key="admit",
        )
    assert caught.value.details["reason_code"] == "GRAPH_RUNTIME_BINDING_INVALID"
    assert await snapshot(sessions) == before
    async with sessions() as s:
        assert (
            await s.get(ReexecutionAuthorizationRow, auth.authorization_id)
        ).consumed_by_run_id is None
    assert planner.calls == 1


@pytest.mark.parametrize(
    "mode",
    ["unknown", "object", "released", "running", "scheme", "goal", "base", "view", "snapshot"],
)
async def test_invalid_authority_rejected_without_graph(prepared, mode):
    backend, sessions, prior, draft, planner = prepared
    if mode in {"released", "running", "scheme", "goal", "base", "view", "snapshot"}:
        async with sessions() as s, s.begin():
            row = await s.get(ResearchRunAggregateRow, prior)
            p = copy.deepcopy(row.payload)
            if mode in {"released", "running"}:
                row.status = mode.upper()
            if mode == "scheme":
                p["run"]["scheme_id"] = "SCHEME-WRONG"
            if mode == "goal":
                p["goal"]["goal_text"] = "tampered"
            if mode == "base":
                p["run"]["base_run_id"] = "RUN-BAD"
            if mode == "view":
                p["run"]["base_research_view_version"] = "RVV-WRONG"
            if mode == "snapshot":
                p["scheme"]["research_scope"] = ["tampered"]
            row.payload = p
    with pytest.raises(ProductError):
        await backend.authorize_reexecution(
            "UNKNOWN" if mode == "unknown" else prior,
            AuthorizeReexecutionRequest(
                research_object_id="OBJ-B" if mode == "object" else "OBJ-A",
                authorize_reexecution=True,
            ),
            idempotency_key="auth",
        )
    assert planner.calls == 0


async def test_authorization_identity_is_database_immutable(prepared):
    from sqlalchemy.exc import DBAPIError

    backend, sessions, prior, draft, planner = prepared
    auth = await authorize(backend, prior)
    with pytest.raises(DBAPIError):
        async with sessions() as s, s.begin():
            row = await s.get(ReexecutionAuthorizationRow, auth.authorization_id)
            row.payload = {**row.payload, "scheme_id": "SCHEME-OTHER"}


async def test_concurrent_same_authorization_one_admission(prepared):
    import asyncio

    backend, sessions, prior, draft, planner = prepared
    auth = await authorize(backend, prior)
    request = ReexecuteRequest(research_object_id="OBJ-A", authorization_id=auth.authorization_id)
    a, b = await asyncio.gather(
        *[backend.reexecute_run(prior, request, idempotency_key="same") for _ in range(2)]
    )
    assert a.run_id == b.run_id and planner.calls == 1
    assert a.idempotency_replayed != b.idempotency_replayed


async def test_expiry_stops_before_graph(prepared, monkeypatch):
    from datetime import timedelta

    import src.phase4_product.reexecution as module

    backend, sessions, prior, draft, planner = prepared
    auth = await authorize(backend, prior)

    class Future(datetime):
        @classmethod
        def now(cls, tz=None):
            return auth.expires_at + timedelta(seconds=1)

    monkeypatch.setattr(module, "datetime", Future)
    with pytest.raises(ProductError) as caught:
        await backend.reexecute_run(
            prior,
            ReexecuteRequest(research_object_id="OBJ-A", authorization_id=auth.authorization_id),
            idempotency_key="expired",
        )
    assert caught.value.details["reason_code"] == "REEXECUTION_AUTHORIZATION_EXPIRED"
    assert planner.calls == 0


async def test_rollback_after_staging_leaves_no_partial_admission(prepared, monkeypatch):
    backend, sessions, prior, draft, planner = prepared
    auth = await authorize(backend, prior)
    before = await snapshot(sessions)
    from src.infrastructure.database.phase4_product import PostgreSQLProductUnitOfWork

    async def fail_commit(self):
        raise RuntimeError("injected local failure")

    monkeypatch.setattr(PostgreSQLProductUnitOfWork, "commit", fail_commit)
    with pytest.raises(RuntimeError):
        await backend.reexecute_run(
            prior,
            ReexecuteRequest(research_object_id="OBJ-A", authorization_id=auth.authorization_id),
            idempotency_key="rollback",
        )
    assert await snapshot(sessions) == before
    async with sessions() as s:
        assert (await s.get(ReexecutionAuthorizationRow, auth.authorization_id)).consumed_at is None


@pytest.mark.parametrize("target", ["object", "prior"])
async def test_authorization_cannot_cross_target(prepared, target):
    backend, sessions, prior, draft, planner = prepared
    auth = await authorize(backend, prior)
    with pytest.raises(ProductError):
        await backend.reexecute_run(
            "RUN-A" if target == "prior" else prior,
            ReexecuteRequest(
                research_object_id="OBJ-B" if target == "object" else "OBJ-A",
                authorization_id=auth.authorization_id,
            ),
            idempotency_key="cross",
        )
    assert planner.calls == 0


async def test_failed_chain_retains_root_intent_and_released_blocks_new_authority(prepared):
    backend, sessions, prior, draft, planner = prepared
    auth = await authorize(backend, prior)
    first = await backend.reexecute_run(
        prior,
        ReexecuteRequest(research_object_id="OBJ-A", authorization_id=auth.authorization_id),
        idempotency_key="first",
    )
    async with sessions() as s, s.begin():
        row = await s.get(ResearchRunAggregateRow, first.run_id)
        p = copy.deepcopy(row.payload)
        p["run"]["status"] = "FAILED"
        row.payload, row.status = p, "FAILED"
    second_auth = await authorize(backend, first.run_id, "second-auth")
    second = await backend.reexecute_run(
        first.run_id,
        ReexecuteRequest(research_object_id="OBJ-A", authorization_id=second_auth.authorization_id),
        idempotency_key="second",
    )
    assert second.reexecution_of_run_id == first.run_id and second.scheme_id == first.scheme_id
    async with sessions() as s, s.begin():
        row = await s.get(ResearchRunAggregateRow, second.run_id)
        row.status = "RELEASED"
    with pytest.raises(ProductError):
        await authorize(backend, first.run_id, "third-auth")


async def test_run_lineage_cannot_be_rewritten(prepared):
    from sqlalchemy.exc import DBAPIError

    backend, sessions, prior, draft, planner = prepared
    auth = await authorize(backend, prior)
    result = await backend.reexecute_run(
        prior,
        ReexecuteRequest(research_object_id="OBJ-A", authorization_id=auth.authorization_id),
        idempotency_key="immutable",
    )
    with pytest.raises(DBAPIError):
        async with sessions() as s, s.begin():
            row = await s.get(ResearchRunAggregateRow, result.run_id)
            p = copy.deepcopy(row.payload)
            p["run"]["reexecution_of_run_id"] = "OTHER"
            row.payload = p
