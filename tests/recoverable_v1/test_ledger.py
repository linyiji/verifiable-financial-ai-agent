import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.domain.execution_contract import (
    CallPurpose,
    ContractDenied,
    ExecutionBudget,
    ExecutionContract,
    PlanningContract,
    fingerprint,
    invalidated_closure,
)
from src.infrastructure.database.execution_ledger import ExecutionIntentRow, SQLExecutionLedger


def budget(physical=4, execution=3, check=2, decision=0, cost=None):
    return ExecutionBudget(
        physical_calls=physical,
        execution_calls=execution,
        check_calls=check,
        decision_calls=decision,
        max_cost=cost,
    )


def contract(intent="INTENT-test", operation="op", **changes):
    digest = fingerprint({"fixture": "offline"})
    fields = dict(
        intent_id=intent,
        run_id="RUN-fixture",
        task_id="RUN-fixture:task",
        operation_id=operation,
        scheme_id="S1",
        scheme_hash=digest,
        object_id="OBJ-NVDA",
        as_of="2026-09-09",
        graph_version=1,
        graph_hash=digest,
        required_outputs=("answer",),
        dependencies=(),
        input_hashes={"E1": digest},
        schema_hash=digest,
        formula_hash=digest,
        code_hash=digest,
        policy_version="fixture/v1",
        policy_hash=digest,
        source_identity="offline-source",
        task_profile="report_synthesis",
        candidates=("teamorouter-sol", "mimo-direct"),
        dynamic_grants={},
        budget=budget(),
        task_budget=budget(),
        deadline=400,
        task_deadline=400,
        per_call_timeout=60,
        compatibility="fixture/v1",
        check_consumption="EXACT_VALIDATED_ONCE",
    )
    fields.update(changes)
    return ExecutionContract(**fields)


@pytest.fixture(params=["sqlite", "postgres"])
async def ledger(tmp_path, request):
    url = "sqlite+aiosqlite:///" + str(tmp_path / "ledger.sqlite")
    if request.param == "postgres":
        url = os.environ.get("TEST_POSTGRESQL_URL")
        if not url:
            pytest.skip("separate isolated PostgreSQL gate required")
        parsed = make_url(url)
        if parsed.host != "postgres" or parsed.database != "recovery_v1_isolated":
            raise RuntimeError("refusing non-isolated ledger test database")
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda conn: ExecutionIntentRow.__table__.create(conn, checkfirst=True)
        )
        await connection.execute(delete(ExecutionIntentRow))
    store = SQLExecutionLedger(
        async_sessionmaker(engine, expire_on_commit=False), composition="ISOLATED_OFFLINE"
    )
    yield store
    await engine.dispose()


async def initialized(store, **overrides):
    c = contract(**overrides)
    await store.create_intent(c.intent_id, budget(), 400)
    await store.admit_run(c.intent_id, c.run_id)
    await store.freeze(c)
    token = await store.claim(c.intent_id, c.operation_id, "worker-A", 100, 100)
    return c, token


async def test_concurrent_physical_and_check_accounting(ledger):
    c, token = await initialized(ledger, budget=budget(physical=2))

    async def reserve():
        try:
            return await ledger.reserve(
                token, str(uuid4()), CallPurpose.CAPABILITY_CHECK, "teamorouter-sol", 101, 60
            )
        except ContractDenied as exc:
            return str(exc)

    results = await asyncio.gather(*(reserve() for _ in range(8)))
    assert sum(isinstance(v, dict) for v in results) == 2
    assert len((await ledger.view(c.intent_id))["calls"]) == 2


async def test_task_budget_shared_across_operations(ledger):
    c, token = await initialized(ledger, task_budget=budget(physical=1))
    await ledger.freeze(contract(operation="other", task_budget=budget(physical=1)))
    other = await ledger.claim(c.intent_id, "other", "worker-B", 100, 100)
    await ledger.reserve(token, "first", "TASK_EXECUTION", "teamorouter-sol", 101, 60)
    with pytest.raises(ContractDenied, match="PHYSICAL_BUDGET"):
        await ledger.reserve(other, "second", "TASK_EXECUTION", "mimo-direct", 101, 60)


@pytest.mark.parametrize("boundary", ["RESERVED", "DISPATCHED", "RESULT_SAVED", "SETTLED"])
async def test_crash_windows_and_stale_owner(ledger, boundary):
    c, token = await initialized(ledger)
    await ledger.reserve(token, "call", "TASK_EXECUTION", "teamorouter-sol", 101, 60)
    if boundary != "RESERVED":
        await ledger.dispatch(token, "call", 102)
    if boundary in {"RESULT_SAVED", "SETTLED"}:
        await ledger.save_result(token, "call", {"answer": 7}, 103)
    if boundary == "SETTLED":
        await ledger.settle(token, "call", 104)
    new = await ledger.claim(c.intent_id, c.operation_id, "worker-B", 201, 100)
    assert new.epoch == 2
    state = (await ledger.view(c.intent_id))["calls"]["call"]["state"]
    assert state == {"RESERVED": "CANCELLED_UNSENT", "DISPATCHED": "RESULT_UNKNOWN"}.get(
        boundary, boundary
    )
    for kind in ("task_output", "aggregate", "runtime_event", "report", "release", "memory"):
        with pytest.raises(ContractDenied, match="STALE_EXECUTION_OWNER"):
            await ledger.publish(token, kind, "ref", {"late": True}, 202)
    with pytest.raises(ContractDenied, match="STALE_EXECUTION_OWNER"):
        await ledger.checkpoint(token, {}, 202)
    if boundary == "DISPATCHED":
        with pytest.raises(ContractDenied, match="RESULT_UNKNOWN"):
            await ledger.reserve(new, "duplicate", "TASK_EXECUTION", "mimo-direct", 202, 60)
    if boundary == "RESULT_SAVED":
        await ledger.settle(new, "call", 202)
        await ledger.settle(new, "call", 203)
    assert (await ledger.view(c.intent_id))["deadline"] == 400


async def test_pre_run_planning_budget_not_reset_at_admission(ledger):
    c = PlanningContract(
        **{
            **contract(task_id="RUN-fixture:planning").model_dump(),
            "task_id": "INTENT-test:planning",
            "run_id": None,
            "task_profile": "scheme",
            "scheme_id": None,
            "scheme_hash": None,
            "graph_hash": None,
            "graph_version": 0,
            "planning_phase": "SCHEME",
        }
    )
    await ledger.create_intent(c.intent_id, budget(physical=1), 400)
    await ledger.freeze(c)
    token = await ledger.claim(c.intent_id, c.operation_id, "worker", 100, 100)
    await ledger.reserve(token, "planning", "PLANNING", "mimo-direct", 101, 60)
    await ledger.admit_run(c.intent_id, "RUN-fixture")
    with pytest.raises(ContractDenied, match="PHYSICAL_BUDGET"):
        await ledger.reserve(token, "graph", "PLANNING", "mimo-direct", 102, 60)


async def test_cost_deadline_and_unauthorized_route(ledger):
    c, token = await initialized(ledger, budget=budget(cost=1))
    with pytest.raises(ContractDenied, match="COST_METERING_UNAVAILABLE"):
        await ledger.reserve(token, "c", "TASK_EXECUTION", "mimo-direct", 101, 60)
    with pytest.raises(ContractDenied, match="CANDIDATE_NOT_AUTHORIZED"):
        await ledger.reserve(token, "c", "TASK_EXECUTION", "not-authorized", 101, 60)
    with pytest.raises(ContractDenied, match="TOTAL_DEADLINE_EXHAUSTED"):
        await ledger.claim(c.intent_id, c.operation_id, "worker", 400, 100)
    assert not (await ledger.view(c.intent_id))["calls"]


async def test_reservation_latency_does_not_extend_absolute_deadline(ledger):
    _, token = await initialized(ledger, deadline=190)
    reserved = await ledger.reserve(token, "slow-reserve", "TASK_EXECUTION", "mimo-direct", 100, 60)
    assert reserved["timeout"] == 60
    dispatched = await ledger.dispatch(token, "slow-reserve", 170)
    assert dispatched["timeout"] == 20
    assert dispatched["absolute_deadline"] == 190


async def test_failed_business_requires_bound_single_use_authority(ledger):
    c, token = await initialized(ledger)
    await ledger.fail(token, {"code": "REQUIRED_MISSING"}, 102)
    with pytest.raises(ContractDenied, match="RECOVERY_AUTHORIZATION_REQUIRED"):
        await ledger.claim(c.intent_id, c.operation_id, "worker-B", 201, 100)
    await ledger.authorize_recovery(
        c.intent_id, c.operation_id, "auth", c.contract_hash, actor="owner", request_hash="request"
    )
    await ledger.authorize_recovery(
        c.intent_id, c.operation_id, "extra-same-failure", c.contract_hash
    )
    new = await ledger.claim(c.intent_id, c.operation_id, "worker-B", 201, 100)
    await ledger.fail(new, {"code": "STILL_MISSING"}, 202)
    with pytest.raises(ContractDenied, match="RECOVERY_AUTHORIZATION_REQUIRED"):
        await ledger.claim(c.intent_id, c.operation_id, "worker-C", 301, 90)
    replay = await ledger.authorize_recovery(
        c.intent_id, c.operation_id, "auth", c.contract_hash, actor="owner", request_hash="request"
    )
    assert replay["consumed"]
    assert len((await ledger.view(c.intent_id))["operations"]["op"]["failures"]) == 2


async def test_dynamic_approval_and_downstream_invalidation(ledger):
    c, _ = await initialized(ledger)
    await ledger.freeze(c)
    with pytest.raises(ContractDenied, match="APPROVAL_CONTRACT_CHANGED"):
        await ledger.freeze(c.model_copy(update={"schema_hash": fingerprint({"changed": True})}))
    with pytest.raises(ContractDenied, match="RESEARCH_INTENT_IDENTITY_CONFLICT"):
        await ledger.freeze(
            c.model_copy(update={"operation_id": "other", "object_id": "OBJ-other"})
        )
    assert invalidated_closure(
        {"input"}, {"calc": ("input",), "review": ("calc",), "proof": ("review",), "unrelated": ()}
    ) == {"input", "calc", "review", "proof"}


async def test_coordinator_fences_child_and_cannot_be_bypassed(ledger):
    c, parent = await initialized(ledger)
    child = contract(operation="child", task_id="RUN-fixture:child")
    await ledger.freeze(child)
    token = await ledger.claim(c.intent_id, "child", "worker-A", 101, 200, coordinator=parent)
    await ledger.claim(c.intent_id, c.operation_id, "worker-B", 201, 100)
    with pytest.raises(ContractDenied, match="STALE_EXECUTION_OWNER"):
        await ledger.reserve(token, "late", "TASK_EXECUTION", "mimo-direct", 202, 60)
    with pytest.raises(ContractDenied, match="COORDINATOR_REQUIRED"):
        await ledger.claim(c.intent_id, "child", "worker-C", 202, 90)


async def test_release_no_rollback_memory_requires_auth_and_same_identity(ledger):
    c, token = await initialized(ledger)
    for stage in ("PREPARED", "RELEASED"):
        await ledger.advance_release(token, stage, "result", c.object_id, 101)
    with pytest.raises(ContractDenied, match="MEMORY_AUTHORIZATION_REQUIRED"):
        await ledger.advance_release(token, "MEMORY_MATERIALIZED", "memory", c.object_id, 102)
    for _ in range(2):
        await ledger.advance_release(
            token, "MEMORY_MATERIALIZED", "memory", c.object_id, 103, memory_authorized=True
        )
    with pytest.raises(ContractDenied, match="RELEASE_BINDING_CONFLICT"):
        await ledger.advance_release(token, "RELEASED", "other", c.object_id, 104)
    assert len((await ledger.view(c.intent_id))["release"]) == 3
