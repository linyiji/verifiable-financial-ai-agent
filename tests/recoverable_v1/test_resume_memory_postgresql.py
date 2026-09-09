"""Actual Memory repository + V1 fence in one isolated PostgreSQL transaction."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.persistence import (
    ReleasedResearchResultRow,
    ResearchObjectRow,
    ResearchRunAggregateRow,
)
from src.domain.execution_contract import (
    ContractDenied,
    ExecutionBudget,
    ExecutionContract,
    fingerprint,
)
from src.domain.released_research_result import ReleasedResearchResult
from src.infrastructure.database.execution_ledger import ExecutionIntentRow, SQLExecutionLedger
from src.infrastructure.database.research_memory import (
    ResearchMemoryPointerRow,
    ResearchMemoryRepository,
    ResearchObjectVersionRow,
    ResearchViewVersionRow,
)
from src.phase4_product.memory_contracts import ResearchObjectVersion, ResearchViewVersion
from src.runtime.memory_recovery_v1 import materialize_memory_v1, memory_snapshot_hash


@pytest.fixture
async def memory_case():
    raw = os.environ.get("TEST_POSTGRESQL_URL")
    if not raw:
        pytest.skip("requires owner-task isolated PostgreSQL")
    url = make_url(raw)
    if (url.host, url.database, url.username) != (
        "postgres",
        "recovery_v1_isolated",
        "recovery_test",
    ):
        pytest.fail("REFUSED_NON_TASK_POSTGRESQL")
    schema = "recovery_v1_memory_" + uuid4().hex
    admin = create_async_engine(raw)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(raw, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    store = SQLExecutionLedger(sessions)
    repo = ResearchMemoryRepository(sessions)
    rows = (
        ResearchObjectRow,
        ResearchRunAggregateRow,
        ReleasedResearchResultRow,
        ResearchObjectVersionRow,
        ResearchViewVersionRow,
        ResearchMemoryPointerRow,
        ExecutionIntentRow,
    )
    try:
        async with engine.begin() as connection:
            for model in rows:
                await connection.run_sync(model.__table__.create)
        now = datetime(2026, 9, 9, tzinfo=UTC)
        result = ReleasedResearchResult(
            result_id="RESULT-offline-memory",
            run_id="RUN-memory",
            canonical_record_id="CER-memory",
            released_at=now,
        )
        async with sessions() as session, session.begin():
            session.add(ResearchObjectRow(object_id="OBJ-memory", payload={}, created_at=now))
            session.add(
                ResearchRunAggregateRow(
                    run_id="RUN-memory",
                    object_id="OBJ-memory",
                    status="RELEASED",
                    payload={"immutable": "offline fixture"},
                    updated_at=now,
                )
            )
            session.add(
                ReleasedResearchResultRow(
                    result_id=result.result_id,
                    run_id=result.run_id,
                    payload=result.model_dump(mode="json"),
                )
            )
        identity = dict(
            research_object_id="OBJ-memory",
            source_run_id="RUN-memory",
            source_released_result_id=result.result_id,
            source_report_id="REPORT-memory",
            source_canonical_record_id="CER-memory",
            created_at=now,
        )
        obj = ResearchObjectVersion(**identity, object_version=1, object_version_id="ROV-memory")
        view = ResearchViewVersion(
            **identity,
            research_object_version=1,
            research_view_version=1,
            research_view_version_id="RVV-memory",
            as_of="2026-09-09",
            summary=None,
            items=(),
        )
        budget = ExecutionBudget(
            physical_calls=1, execution_calls=0, check_calls=0, decision_calls=0
        )
        digest = fingerprint({"fixture": "memory"})
        c = ExecutionContract(
            intent_id="INTENT-memory",
            run_id="RUN-memory",
            task_id="RUN-memory:closure",
            operation_id="closure",
            scheme_id="SCHEME-memory",
            scheme_hash=digest,
            object_id="OBJ-memory",
            as_of="2026-09-09",
            graph_version=1,
            graph_hash=digest,
            required_outputs=(),
            dependencies=(),
            input_hashes={
                "memory_snapshot": memory_snapshot_hash(obj, view),
                "released_result": fingerprint(result),
            },
            schema_hash=digest,
            formula_hash=digest,
            code_hash=digest,
            policy_version="offline/v1",
            policy_hash=digest,
            source_identity="offline-only",
            task_profile="closure",
            candidates=("fake/none",),
            dynamic_grants={},
            budget=budget,
            task_budget=budget,
            deadline=400,
            task_deadline=400,
            per_call_timeout=1,
            compatibility="fixture/v1",
            check_consumption="SEPARATE_EXECUTION",
        )
        await store.create_intent(c.intent_id, budget, 400)
        await store.admit_run(c.intent_id, c.run_id)
        await store.freeze(c)
        token = await store.claim(c.intent_id, c.operation_id, "owner", 100, 30)
        await store.advance_release(token, "PREPARED", "prepared", c.object_id, 100)
        await store.advance_release(token, "RELEASED", result.result_id, c.object_id, 100)
        clock = [101]
        args = dict(
            repository=repo,
            store=store,
            token=token,
            obj=obj,
            view=view,
            clock=lambda: clock[0],
            memory_authorized=True,
        )
        yield sessions, store, c, args, clock
    finally:
        await engine.dispose()
        # Exact generated schema only, after verifying the dedicated task database.
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def counts(sessions):
    async with sessions() as session:
        return [
            await session.scalar(select(func.count()).select_from(model))
            for model in (
                ResearchObjectVersionRow,
                ResearchViewVersionRow,
                ResearchMemoryPointerRow,
            )
        ]


@pytest.mark.parametrize("fault_at", ["object", "view", "pointer"])
async def test_real_memory_and_ledger_atomic_rollback_then_resume(memory_case, fault_at):
    sessions, store, c, args, _ = memory_case

    def fault(stage):
        if stage == fault_at:
            raise RuntimeError("offline process-loss fixture")

    with pytest.raises(RuntimeError):
        await materialize_memory_v1(**args, checkpoint=fault)
    assert await counts(sessions) == [0, 0, 0]
    assert list((await store.view(c.intent_id))["release"]) == ["PREPARED", "RELEASED"]
    completed = await materialize_memory_v1(**args)
    # A crash after the commit cannot create a second Memory version on re-delivery.
    assert await materialize_memory_v1(**args) == completed
    assert await counts(sessions) == [1, 1, 1]
    assert list((await store.view(c.intent_id))["release"])[-2:] == [
        "MEMORY_MATERIALIZED",
        "COMPLETED",
    ]
    async with sessions() as session:
        source = await session.get(ResearchRunAggregateRow, c.run_id)
        assert source.status == "RELEASED" and source.payload == {"immutable": "offline fixture"}


async def test_real_memory_concurrent_idempotency(memory_case):
    sessions, _, _, args, _ = memory_case
    snapshots = await asyncio.gather(*(materialize_memory_v1(**args) for _ in range(3)))
    assert all(snapshot == snapshots[0] for snapshot in snapshots)
    assert await counts(sessions) == [1, 1, 1]


async def test_real_memory_authority_and_stale_owner_before_any_write(memory_case):
    sessions, store, c, args, clock = memory_case
    with pytest.raises(ContractDenied, match="MEMORY_AUTHORIZATION_REQUIRED"):
        await materialize_memory_v1(**{**args, "memory_authorized": False})
    with pytest.raises(ValueError, match="memory version identity mismatch"):
        await materialize_memory_v1(
            **{**args, "obj": args["obj"].model_copy(update={"source_report_id": "OTHER"})}
        )
    with pytest.raises(ContractDenied, match="MEMORY_SNAPSHOT_IDENTITY_MISMATCH"):
        await materialize_memory_v1(
            **{
                **args,
                "obj": args["obj"].model_copy(update={"source_report_id": "OTHER"}),
                "view": args["view"].model_copy(update={"source_report_id": "OTHER"}),
            }
        )
    clock[0] = 131
    await store.claim(c.intent_id, c.operation_id, "takeover", clock[0], 30)
    with pytest.raises(ContractDenied, match="STALE_EXECUTION_OWNER"):
        await materialize_memory_v1(**args)
    assert await counts(sessions) == [0, 0, 0]


async def test_expired_lease_before_memory_commit_rolls_back_all(memory_case):
    sessions, store, c, args, clock = memory_case

    def expire(stage):
        if stage == "pointer":
            clock[0] = 131

    with pytest.raises(ContractDenied, match="STALE_EXECUTION_OWNER"):
        await materialize_memory_v1(**args, checkpoint=expire)
    assert await counts(sessions) == [0, 0, 0]
    assert list((await store.view(c.intent_id))["release"]) == ["PREPARED", "RELEASED"]
