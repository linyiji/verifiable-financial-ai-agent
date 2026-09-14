"""Real DependencyScheduler + SQL repository, fake physical transport only."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.domain.enums import RunStatus
from src.domain.execution_contract import (
    ContractDenied,
    ExecutionBudget,
    ExecutionContract,
    fingerprint,
)
from src.domain.task import PlannedTaskGraph, Task
from src.infrastructure.database.execution_ledger import ExecutionIntentRow, SQLExecutionLedger
from src.runtime.recoverable_execution import (
    AttemptArtifacts,
    ProcessInterrupted,
    RecoverableDependencyRunner,
)
from src.runtime.scheduler import TaskExecutionResult


@pytest.fixture
async def scenario(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "resume.sqlite"))
    async with engine.begin() as connection:
        await connection.run_sync(ExecutionIntentRow.__table__.create)
    store = SQLExecutionLedger(
        async_sessionmaker(engine, expire_on_commit=False), composition="ISOLATED_OFFLINE"
    )
    task = Task(
        task_id="RUN-offline:one",
        run_id="RUN-offline",
        task_type="test",
        goal="fake local evidence",
        assigned_agent="fixture",
        skill_id="fixture",
    )
    plan = PlannedTaskGraph(graph_id="GRAPH-offline", run_id=task.run_id, tasks=[task])
    budget = ExecutionBudget(physical_calls=6, execution_calls=4, check_calls=2, decision_calls=0)
    digest = fingerprint({"fixture": "offline-only"})
    common = dict(
        intent_id="INTENT-offline",
        run_id=task.run_id,
        scheme_id="S-offline",
        scheme_hash=digest,
        object_id="OBJ-offline",
        as_of="2026-09-09",
        graph_version=1,
        graph_hash=fingerprint(plan),
        required_outputs=("answer",),
        dependencies=(),
        input_hashes={"task": fingerprint(task)},
        schema_hash=digest,
        formula_hash=digest,
        code_hash=digest,
        policy_version="fixture/v1",
        policy_hash=digest,
        source_identity="fixture-only",
        task_profile="report_synthesis",
        candidates=("fake/one",),
        dynamic_grants={},
        budget=budget,
        task_budget=budget,
        deadline=400,
        task_deadline=400,
        per_call_timeout=10,
        compatibility="fixture/v1",
        check_consumption="SEPARATE_EXECUTION",
    )
    coordinator = ExecutionContract(
        **common, task_id="RUN-offline:coordinator", operation_id="coordinator"
    )
    child = ExecutionContract(**common, task_id=task.task_id, operation_id="one")
    await store.create_intent(coordinator.intent_id, budget, 400)
    await store.admit_run(coordinator.intent_id, task.run_id)
    clock = [100.0]
    yield store, coordinator, {task.task_id: child}, plan, clock
    await engine.dispose()


class FakePhysicalExecutor:
    def __init__(self):
        self.calls = 0
        self.attempts = []

    async def execute(self, task, context, calls):
        self.attempts.append(context.attempt)

        async def send(payload, limit_seconds):
            self.calls += 1
            assert limit_seconds <= 10
            return {"answer": 7}

        result = await calls.request(
            request_id="answer",
            route="fake/one",
            purpose="TASK_EXECUTION",
            payload={"question": task.goal},
            send=send,
            validate=lambda value: value == {"answer": 7},
        )
        return TaskExecutionResult(
            result_ref=f"result:{result['answer']}", output_refs=("answer:7",)
        )

    def validate_result(self, task, result):
        return result.result_ref == "result:7" and result.output_refs == ("answer:7",)


def runner_args(scenario, executor, owner="first"):
    _, coordinator, tasks, plan, _ = scenario
    return dict(
        coordinator=coordinator, tasks=tasks, planned_graph=plan, owner=owner, executor=executor
    )


@pytest.mark.parametrize(
    "boundary",
    [
        "AFTER_CLAIM",
        "AFTER_RESERVE",
        "AFTER_RESULT_SAVE",
        "AFTER_SETTLEMENT",
        "AFTER_OUTPUT_SAVE",
        "AFTER_TASK_EVENT",
        "BEFORE_CHECKPOINT",
    ],
)
async def test_durable_redelivery_reconciles_without_duplicate_physical_call(scenario, boundary):
    store, coordinator, _, _, clock = scenario
    fired = False

    def interrupt(point):
        nonlocal fired
        if point == boundary and not fired:
            fired = True
            raise ProcessInterrupted()

    executor = FakePhysicalExecutor()
    runner = RecoverableDependencyRunner(store, lambda: clock[0], lease_seconds=30, fault=interrupt)
    with pytest.raises(ProcessInterrupted):
        await runner.run(**runner_args(scenario, executor))
    before = await store.view(coordinator.intent_id)
    assert before["operations"]["coordinator"]["status"] == "CLAIMED"
    assert not before["operations"]["coordinator"]["failures"]
    clock[0] = 131
    restarted = RecoverableDependencyRunner(store, lambda: clock[0], lease_seconds=30)
    result = await restarted.run(**runner_args(scenario, executor, "restarted"))
    assert result.run_status is RunStatus.REVIEW
    assert executor.calls == 1
    after = await store.view(coordinator.intent_id)
    assert after["deadline"] == 400
    op = after["operations"]["coordinator"]
    assert op["epoch"] == 2 and op["status"] == "COMPLETE"
    assert op["checkpoint"]["version"] == 2
    assert op["checkpoint"]["contract_hash"] == coordinator.contract_hash
    assert op["checkpoint"]["intent_deadline"] == 400
    child = after["operations"]["one"]
    assert child["status"] == "COMPLETE"
    assert result.task("RUN-offline:one").attempt_count == child["epoch"]
    completions = [
        publication["payload"]
        for key, publication in op["published"].items()
        if key.startswith("EVENT:") and publication["payload"]["type"] == "task.completed"
    ]
    assert completions[-1]["payload"]["attempt"] == child["epoch"]
    assert len([c for c in after["calls"].values() if c["state"] != "CANCELLED_UNSENT"]) == 1
    with pytest.raises(ContractDenied, match="ALREADY_COMPLETE"):
        await restarted.run(**runner_args(scenario, executor, "duplicate"))
    assert executor.calls == 1


async def test_possible_dispatch_is_unknown_and_never_automatically_resent(scenario):
    store, coordinator, _, _, clock = scenario

    def interrupt(point):
        if point == "AFTER_DISPATCH":
            raise ProcessInterrupted()

    executor = FakePhysicalExecutor()
    with pytest.raises(ProcessInterrupted):
        await RecoverableDependencyRunner(store, lambda: clock[0], fault=interrupt).run(
            **runner_args(scenario, executor)
        )
    clock[0] = 161
    with pytest.raises(ExceptionGroup):
        await RecoverableDependencyRunner(store, lambda: clock[0]).run(
            **runner_args(scenario, executor, "restarted")
        )
    assert executor.calls == 0  # dispatch window is ambiguous, not declared unsent
    doc = await store.view(coordinator.intent_id)
    assert next(iter(doc["calls"].values()))["state"] == "RESULT_UNKNOWN"


async def test_dispatch_timeout_immediately_blocks_same_process_fallback(scenario):
    store, coordinator, _, _, clock = scenario

    class TimeoutExecutor(FakePhysicalExecutor):
        async def execute(self, task, context, calls):
            async def send(payload, limit_seconds):
                self.calls += 1
                raise TimeoutError("offline transport fixture")

            for request_id in ("first", "fallback"):
                with pytest.raises(ContractDenied, match="RESULT_UNKNOWN"):
                    await calls.request(
                        request_id=request_id,
                        route="fake/one",
                        purpose="TASK_EXECUTION",
                        payload={},
                        send=send,
                        validate=lambda _: True,
                    )
            raise ContractDenied("RESULT_UNKNOWN_REQUIRES_RECONCILIATION")

    executor = TimeoutExecutor()
    with pytest.raises(ExceptionGroup):
        await RecoverableDependencyRunner(store, lambda: clock[0]).run(
            **runner_args(scenario, executor)
        )
    assert executor.calls == 1
    assert (
        next(iter((await store.view(coordinator.intent_id))["calls"].values()))["state"]
        == "RESULT_UNKNOWN"
    )


async def test_mutable_contract_does_not_expand_saved_authority(scenario):
    store, coordinator, _, _, clock = scenario

    class MutatingExecutor(FakePhysicalExecutor):
        async def execute(self, task, context, calls):
            calls.contract.input_hashes["task"] = fingerprint({"tampered": True})
            return await super().execute(task, context, calls)

    executor = MutatingExecutor()
    with pytest.raises(ExceptionGroup):
        await RecoverableDependencyRunner(store, lambda: clock[0]).run(
            **runner_args(scenario, executor)
        )
    assert executor.calls == 0
    assert not (await store.view(coordinator.intent_id))["calls"]


async def test_changed_frozen_input_cannot_resume_and_deadline_is_absolute(scenario):
    store, _, tasks, plan, clock = scenario
    runner = RecoverableDependencyRunner(store, lambda: clock[0])
    args = runner_args(scenario, FakePhysicalExecutor())
    task_id = plan.tasks[0].task_id
    args["tasks"] = {task_id: tasks[task_id].model_copy(update={"input_hashes": {}})}
    with pytest.raises(ContractDenied, match="TASK_CONTRACT_CHANGED"):
        await runner.run(**args)
    clock[0] = 400
    with pytest.raises(ContractDenied, match="TOTAL_DEADLINE_EXHAUSTED"):
        await runner.run(**runner_args(scenario, FakePhysicalExecutor()))


async def test_coordinator_takeover_fences_late_child_and_attempt_files(scenario, tmp_path):
    store, coordinator, tasks, _, clock = scenario
    child = next(iter(tasks.values()))
    await store.freeze(coordinator)
    await store.freeze(child)
    parent = await store.claim(coordinator.intent_id, "coordinator", "old", 100, 30)
    old = await store.claim(child.intent_id, "one", "old", 100, 30, coordinator=parent)
    artifacts = AttemptArtifacts(
        tmp_path / "artifacts", store=store, token=old, clock=lambda: clock[0]
    )
    reference = await artifacts.save(b"immutable answer")
    assert artifacts.verify(reference)
    clock[0] = 131
    new = await store.claim(coordinator.intent_id, "coordinator", "new", 131, 30)
    for kind in ("TASK_OUTPUT", "AGGREGATE", "EVENT", "REPORT", "RELEASE", "MEMORY"):
        with pytest.raises(ContractDenied, match="STALE_EXECUTION_OWNER"):
            await store.publish(old, kind, "late", {}, clock[0])
    with pytest.raises(ContractDenied, match="STALE_EXECUTION_OWNER"):
        await artifacts.save(b"late answer")
    current = await store.claim(child.intent_id, "one", "new", 131, 30, coordinator=new)
    current_artifacts = AttemptArtifacts(
        tmp_path / "artifacts", store=store, token=current, clock=lambda: clock[0]
    )
    new_reference = await current_artifacts.save(b"immutable answer")
    assert new_reference != reference
    assert artifacts.verify(reference) and current_artifacts.verify(new_reference)
    assert not artifacts.verify("../../secret")


async def test_live_lease_prevents_two_scheduler_deliveries(scenario):
    store, coordinator, _, _, clock = scenario
    await store.freeze(coordinator)
    tokens = await asyncio.gather(
        *(
            store.claim(coordinator.intent_id, "coordinator", str(index), clock[0], 30)
            for index in range(2)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(token, ContractDenied) for token in tokens) == 1


async def test_api_authorization_and_real_scheduler_resume_same_failed_run(scenario):
    from apps.api.recovery_v1 import create_recovery_router

    store, coordinator, tasks, _, clock = scenario

    class FailedExecutor(FakePhysicalExecutor):
        async def execute(self, task, context, calls):
            raise ValueError("deterministic fixture business failure before dispatch")

    runner = RecoverableDependencyRunner(store, lambda: clock[0])
    with pytest.raises(ExceptionGroup):
        await runner.run(**runner_args(scenario, FailedExecutor()))
    before = await store.view(coordinator.intent_id)
    assert before["operations"]["coordinator"]["status"] == "FAILED"
    assert before["operations"]["one"]["status"] == "FAILED"
    with pytest.raises(ContractDenied, match="RECOVERY_AUTHORIZATION_REQUIRED"):
        await runner.run(**runner_args(scenario, FakePhysicalExecutor(), "unauthorized"))

    async def actor(request, run_id, permission):
        assert run_id == coordinator.run_id
        return "fixture-owner"

    app = FastAPI()
    app.include_router(
        create_recovery_router(
            store, resolve_actor=actor, clock=lambda: clock[0], actions_accepted=True
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://isolated-fixture"
    ) as client:
        for contract in (coordinator, *tasks.values()):
            path = (
                f"/api/research-runs/{contract.run_id}/recovery/"
                f"{contract.intent_id}/{contract.operation_id}"
            )
            request = dict(
                json={
                    "action": "AUTHORIZE_FAILED_OPERATION",
                    "contract_hash": contract.contract_hash,
                },
                headers={"Idempotency-Key": "fixture-one-shot"},
            )
            response = await client.post(path, **request)
            assert response.status_code == 200
            assert response.json()["execution_started"] is False
            assert (await client.post(path, **request)).json() == response.json()
    # POST does not execute, renew deadlines, or admit another Run.
    assert not (await store.view(coordinator.intent_id))["calls"]
    clock[0] = 101
    executor = FakePhysicalExecutor()
    result = await runner.run(**runner_args(scenario, executor, "authorized-recovery"))
    assert result.run_id == coordinator.run_id and result.run_status is RunStatus.REVIEW
    assert executor.calls == 1
    after = await store.view(coordinator.intent_id)
    for operation_id in ("coordinator", "one"):
        op = after["operations"][operation_id]
        assert op["epoch"] == 2
        assert op["failures"] == before["operations"][operation_id]["failures"]
        assert all(auth["consumed"] for auth in op["authorizations"].values())
