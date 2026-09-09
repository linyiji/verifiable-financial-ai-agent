"""Explicit V1 assembly of the existing dependency scheduler and durable ledger.

This is NOT selected by legacy/production composition. Executors in this assembly
must perform every physical request through ``LedgerPhysicalCalls.request``; an
adapter hiding retries is not compatible. Events and aggregates below are V1
authoritative records, not unfenced writes into the legacy projection tables.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from src.domain.execution_contract import (
    CallPurpose,
    ContractDenied,
    ExecutionContract,
    fingerprint,
)
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.runtime.checkpoint import RuntimeCheckpoint
from src.runtime.scheduler import (
    DependencyScheduler,
    RuntimeProcessInterrupted,
    TaskExecutionContext,
    TaskExecutionResult,
)
from src.runtime.state import RuntimeState


class ProcessInterrupted(RuntimeProcessInterrupted):
    """Deterministic process-loss fixture; never a business failure authorization."""


def _no_fault(_point):
    pass


class LedgerPhysicalCalls:
    """One reservation for one callback invocation; callers expose each retry.

    A saved exact response can be reconciled after process loss. A possibly sent
    request cannot. Validation is required on both fresh and reused responses.
    Request contents are hashed, never retained in ledger diagnostics.
    """

    def __init__(self, *, store, token, contract, clock, fault=_no_fault):
        self.store = store
        self.token = token
        self.contract = ExecutionContract.model_validate(contract.model_dump())
        self._contract_hash = self.contract.contract_hash
        self.clock = clock
        self.fault = fault

    async def request(
        self, *, request_id, route, purpose, payload, send, validate, estimated_cost=None
    ):
        payload = deepcopy(payload)
        doc = await self.store.view(self.token.intent_id)
        operation = doc["operations"].get(self.token.operation_id)
        if (
            operation is None
            or operation["contract_hash"] != self._contract_hash
            or fingerprint(operation["contract"]) != self._contract_hash
            or self.contract.contract_hash != self._contract_hash
        ):
            raise ContractDenied("APPROVAL_CONTRACT_CHANGED")
        contract = ExecutionContract.model_validate(operation["contract"])
        binding = fingerprint(
            {
                "request_id": request_id,
                "route": route,
                "purpose": CallPurpose(purpose).value,
                "input": fingerprint(payload),
                "contract": contract.contract_hash,
            }
        )
        prefix = f"{self.token.operation_id}:{binding}:"
        for call in doc["calls"].values():
            if not call["call_id"].startswith(prefix):
                continue
            if call["state"] in {"DISPATCHED", "RESULT_UNKNOWN"}:
                raise ContractDenied("RESULT_UNKNOWN_REQUIRES_RECONCILIATION")
            if call["state"] in {"RESULT_SAVED", "SETTLED"}:
                saved = call["result"]
                if fingerprint(saved) != call["result_hash"] or saved["binding"] != binding:
                    raise ContractDenied("SAVED_RESULT_CORRUPT")
                if not validate(saved["response"]):
                    raise ContractDenied("SAVED_RESULT_INVALID")
                if call["state"] == "RESULT_SAVED":
                    await self.store.settle(self.token, call["call_id"], self.clock())
                return saved["response"]
        call_id = prefix + str(self.token.epoch) + ":" + uuid4().hex
        call = await self.store.reserve(
            self.token,
            call_id,
            purpose,
            route,
            self.clock(),
            contract.per_call_timeout,
            estimated_cost=estimated_cost,
        )
        self.fault("AFTER_RESERVE")
        call = await self.store.dispatch(self.token, call_id, self.clock())
        self.fault("AFTER_DISPATCH")
        # This outer timeout bounds the actual dispatch, including adapters that
        # neglect the timeout argument. Cancellation leaves a truthful unknown.
        try:
            remaining = min(call["timeout"], call["absolute_deadline"] - self.clock())
            async with asyncio.timeout(max(0, remaining)):
                response = await send(payload, remaining)
        except (Exception, asyncio.CancelledError):
            await self.store.mark_unknown(self.token, call_id, self.clock())
            raise ContractDenied("RESULT_UNKNOWN_REQUIRES_RECONCILIATION") from None
        await self.store.save_result(
            self.token,
            call_id,
            {"binding": binding, "response": response},
            self.clock(),
        )
        self.fault("AFTER_RESULT_SAVE")
        await self.store.settle(self.token, call_id, self.clock())
        if not validate(response):
            raise ContractDenied("MODEL_RESULT_INVALID")
        self.fault("AFTER_SETTLEMENT")
        return response


class AttemptArtifacts:
    """Exclusive, digest-bound files; stale writers cannot overwrite another epoch.

    The private directory is supplied by the owning installation. Authoritative
    references are only returned after a fenced database publication succeeds.
    """

    def __init__(self, root: Path, *, store, token, clock):
        self.root, self.store, self.token, self.clock = root, store, token, clock

    async def save(self, content: bytes) -> str:
        digest = sha256(content).hexdigest()
        namespace = sha256(
            (self.token.intent_id + "\0" + self.token.operation_id).encode()
        ).hexdigest()
        directory = self.root / namespace / str(self.token.epoch)
        if any(path.is_symlink() for path in (self.root, *self.root.parents)):
            raise ContractDenied("ARTIFACT_PATH_UNSAFE")
        directory.mkdir(parents=True, exist_ok=True)
        if any(path.is_symlink() for path in (directory, directory.parent)):
            raise ContractDenied("ARTIFACT_PATH_UNSAFE")
        target = directory / digest
        try:
            with target.open("xb") as handle:
                handle.write(content)
        except FileExistsError:
            if target.is_symlink() or sha256(target.read_bytes()).hexdigest() != digest:
                raise ContractDenied("ARTIFACT_HASH_MISMATCH") from None
        reference = f"{namespace}/{self.token.epoch}/{digest}"
        await self.store.publish(
            self.token,
            "ARTIFACT",
            reference,
            {"sha256": digest, "size": len(content)},
            self.clock(),
        )
        return reference

    def verify(self, reference: str) -> bool:
        parts = reference.split("/")
        namespace = sha256(
            (self.token.intent_id + "\0" + self.token.operation_id).encode()
        ).hexdigest()
        if len(parts) != 3 or parts[0] != namespace or not parts[1].isdigit():
            return False
        if len(parts[2]) != 64 or any(c not in "0123456789abcdef" for c in parts[2]):
            return False
        path = self.root.joinpath(*parts)
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
            return False
        return sha256(path.read_bytes()).hexdigest() == parts[2]


class _FencedEvents:
    def __init__(self, store, token, run_id, clock, fault):
        self.store, self.token, self.run_id = store, token, run_id
        self.clock, self.fault = clock, fault
        self.lock = asyncio.Lock()

    async def emit(self, *, run_id, event_type, task_id=None, payload=None, timestamp=None):
        if run_id != self.run_id:
            raise ContractDenied("EVENT_RUN_MISMATCH")
        async with self.lock:
            doc = await self.store.view(self.token.intent_id)
            publications = doc["operations"][self.token.operation_id]["published"]
            sequence = sum(key.startswith("EVENT:") for key in publications) + 1
            event = RuntimeEvent(
                event_id=f"EVT-V1-{uuid4()}",
                run_id=run_id,
                task_id=task_id,
                type=event_type,
                sequence=sequence,
                payload=payload or {},
                timestamp=timestamp or datetime.fromtimestamp(self.clock(), UTC),
            )
            await self.store.publish(
                self.token, "EVENT", str(sequence), event.model_dump(mode="json"), self.clock()
            )
            if event_type is RuntimeEventType.TASK_COMPLETED:
                self.fault("AFTER_TASK_EVENT")
            return event


class _FencedCheckpoints:
    def __init__(self, store, token, clock, fault):
        self.store, self.token, self.clock, self.fault = store, token, clock, fault

    async def save(self, checkpoint: RuntimeCheckpoint):
        checkpoint.validate_payload_identity()
        self.fault("BEFORE_CHECKPOINT")
        await self.store.checkpoint(self.token, checkpoint.model_dump(mode="json"), self.clock())


class _FencedExecutor:
    def __init__(self, runner, coordinator_token, tasks, executor, owner):
        self.runner, self.coordinator_token, self.tasks = runner, coordinator_token, tasks
        self.executor, self.owner = executor, owner
        self.tokens = {}

    async def begin_attempt(self, task, _retry_number):
        contract = self.tasks[task.task_id]
        doc = await self.runner.store.view(contract.intent_id)
        operation = doc["operations"][contract.operation_id]
        saved = operation["published"].get("TASK_OUTPUT:result")
        if saved and operation["status"] == "COMPLETE":
            return saved["epoch"]
        token = await self.runner.store.claim(
            contract.intent_id,
            contract.operation_id,
            self.owner,
            self.runner.clock(),
            self.runner.lease_seconds,
            coordinator=self.coordinator_token,
        )
        self.tokens[task.task_id] = token
        return token.epoch

    async def execute(self, task, context):
        runner = self.runner
        contract = self.tasks[task.task_id]
        doc = await runner.store.view(contract.intent_id)
        saved = doc["operations"][contract.operation_id]["published"].get("TASK_OUTPUT:result")
        if saved:
            if saved["contract_hash"] != contract.contract_hash:
                raise ContractDenied("SAVED_OUTPUT_CONTRACT_CHANGED")
            if saved["hash"] != fingerprint(saved["payload"]):
                raise ContractDenied("SAVED_OUTPUT_CORRUPT")
            result = TaskExecutionResult(
                **{
                    **saved["payload"],
                    "output_refs": tuple(saved["payload"]["output_refs"]),
                }
            )
            if not self.executor.validate_result(task, result):
                raise ContractDenied("SAVED_OUTPUT_INVALID")
            if task.task_id in self.tokens:
                token = self.tokens[task.task_id]
                await runner.store.checkpoint(
                    token,
                    {
                        "output": saved["payload"],
                        "validation": "PASS",
                        "reused_from_epoch": saved["epoch"],
                    },
                    runner.clock(),
                )
                await runner.store.complete(token, runner.clock())
            return result
        token = self.tokens[task.task_id]
        calls = LedgerPhysicalCalls(
            store=runner.store,
            token=token,
            contract=contract,
            clock=runner.clock,
            fault=runner.fault,
        )
        try:
            result = await self.executor.execute(
                task,
                TaskExecutionContext(run_id=context.run_id, attempt=token.epoch),
                calls,
            )
            if not self.executor.validate_result(task, result):
                raise ContractDenied("TASK_OUTPUT_INVALID")
            payload = {"result_ref": result.result_ref, "output_refs": list(result.output_refs)}
            await runner.store.publish(token, "TASK_OUTPUT", "result", payload, runner.clock())
            runner.fault("AFTER_OUTPUT_SAVE")
            await runner.store.checkpoint(
                token, {"output": payload, "validation": "PASS"}, runner.clock()
            )
            await runner.store.complete(token, runner.clock())
            return result
        except Exception as exc:
            # Contract/fencing denials must never turn a newer owner's operation
            # into business FAILED. The store independently rechecks that fence.
            if not isinstance(exc, ContractDenied) or str(exc) not in {
                "STALE_EXECUTION_OWNER",
                "RESULT_UNKNOWN_REQUIRES_RECONCILIATION",
            }:
                code = str(exc) if isinstance(exc, ContractDenied) else "TASK_EXECUTION_FAILED"
                await runner.store.fail(token, {"code": code}, runner.clock())
            raise


class RecoverableDependencyRunner:
    """Opt-in repository + real Scheduler integration, no background auto-resume."""

    def __init__(self, store, clock: Callable[[], float], *, lease_seconds=60, fault=None):
        self.store, self.clock, self.lease_seconds = store, clock, lease_seconds
        self.fault = fault or _no_fault

    async def run(
        self,
        *,
        coordinator: ExecutionContract,
        tasks: dict[str, ExecutionContract],
        planned_graph,
        owner,
        executor,
    ):
        coordinator = ExecutionContract.model_validate(coordinator.model_dump())
        tasks = {
            key: ExecutionContract.model_validate(value.model_dump())
            for key, value in tasks.items()
        }
        planned_graph = planned_graph.model_copy(deep=True)
        if not coordinator.run_id or coordinator.run_id != planned_graph.run_id:
            raise ContractDenied("RUN_BINDING_CONFLICT")
        if coordinator.graph_hash != fingerprint(planned_graph):
            raise ContractDenied("GRAPH_CONTRACT_CHANGED")
        if set(tasks) != {task.task_id for task in planned_graph.tasks}:
            raise ContractDenied("INCOMPLETE_GRAPH_FREEZE")
        for task in planned_graph.tasks:
            contract = tasks[task.task_id]
            if (
                contract.run_id != coordinator.run_id
                or contract.intent_id != coordinator.intent_id
                or contract.graph_hash != coordinator.graph_hash
                or contract.task_id != task.task_id
                or contract.dependencies != tuple(task.dependencies)
                or contract.input_hashes.get("task") != fingerprint(task)
            ):
                raise ContractDenied("TASK_CONTRACT_CHANGED")
        await self.store.freeze(coordinator)
        for contract in tasks.values():
            await self.store.freeze(contract)
        token = await self.store.claim(
            coordinator.intent_id, coordinator.operation_id, owner, self.clock(), self.lease_seconds
        )
        self.fault("AFTER_CLAIM")
        # Reconstruct only from the immutable approved plan. Interrupted mutable
        # statuses are not copied. Durable exact outputs are reconciled by the
        # executor before any request, including checkpoint-behind-output windows.
        state = RuntimeState.create(run_id=coordinator.run_id, planned_graph=planned_graph)
        events = _FencedEvents(self.store, token, coordinator.run_id, self.clock, self.fault)
        checkpoints = _FencedCheckpoints(self.store, token, self.clock, self.fault)
        fenced_executor = _FencedExecutor(self, token, tasks, executor, owner)
        scheduler = DependencyScheduler(
            event_store=events,
            checkpoint_store=checkpoints,
            attempt_resolver=fenced_executor.begin_attempt,
        )
        try:
            result = await scheduler.execute(
                state=state,
                executor=fenced_executor,
            )
        except Exception:
            # The V1 delivery remains CLAIMED on crash/unknown/contract denial;
            # only explicitly persisted child business failures authorize FAILED.
            doc = await self.store.view(coordinator.intent_id)
            failed = [
                key
                for key, op in doc["operations"].items()
                if key != coordinator.operation_id and op["status"] == "FAILED"
            ]
            if failed:
                await self.store.fail(
                    token, {"code": "TASK_EXECUTION_FAILED", "tasks": failed}, self.clock()
                )
            raise
        await self.store.publish(
            token,
            "AGGREGATE",
            f"epoch-{token.epoch}",
            RuntimeCheckpoint.capture(checkpoint_id=f"CHK-{uuid4()}", state=result).model_dump(
                mode="json"
            ),
            self.clock(),
        )
        await self.store.complete(token, self.clock())
        return result
