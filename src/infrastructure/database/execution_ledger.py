"""Durable V1 Intent ledger; all writes lock one budget owner before read/modify/write.

Separate table, no mutation or automatic adoption of historical application rows.
The UPDATE lock works for PostgreSQL and serialized SQLite isolated tests.
"""

from copy import deepcopy
from math import isfinite

from sqlalchemy import JSON, Integer, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.execution_contract import (
    CallPurpose,
    ContractDenied,
    ExecutionBudget,
    ExecutionContract,
    LeaseToken,
    PlanningContract,
    fingerprint,
)
from src.infrastructure.database.base import Base


class ExecutionIntentRow(Base):
    __tablename__ = "execution_intents_v1"
    intent_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class SQLExecutionLedger:
    def __init__(self, sessions):
        self.sessions = sessions

    async def create_intent(self, intent_id, budget: ExecutionBudget, deadline):
        if deadline <= 0 or not isfinite(deadline):
            raise ContractDenied("DEADLINE_REQUIRED")
        async with self.sessions() as session, session.begin():
            old = await session.get(ExecutionIntentRow, intent_id)
            if old:
                if (
                    old.payload["budget"] != budget.model_dump()
                    or old.payload["deadline"] != deadline
                ):
                    raise ContractDenied("INTENT_CONFLICT")
                return
            session.add(
                ExecutionIntentRow(
                    intent_id=intent_id,
                    revision=0,
                    payload={
                        "version": "recoverable-execution/v1",
                        "run_id": None,
                        "budget": budget.model_dump(),
                        "deadline": deadline,
                        "operations": {},
                        "calls": {},
                        "release": {},
                    },
                )
            )

    async def view(self, intent_id):
        async with self.sessions() as session:
            row = await session.get(ExecutionIntentRow, intent_id)
            if row is None:
                raise ContractDenied("LEGACY_NOT_RESUMABLE")
            return deepcopy(row.payload)

    async def _mutate(self, intent_id, function):
        async with self.sessions() as session, session.begin():
            locked = await session.execute(
                update(ExecutionIntentRow)
                .where(ExecutionIntentRow.intent_id == intent_id)
                .values(revision=ExecutionIntentRow.revision + 1)
            )
            if locked.rowcount != 1:
                raise ContractDenied("LEGACY_NOT_RESUMABLE")
            row = await session.scalar(
                select(ExecutionIntentRow)
                .where(ExecutionIntentRow.intent_id == intent_id)
                .execution_options(populate_existing=True)
            )
            value = deepcopy(row.payload)
            result = function(value)
            row.payload = value
            return deepcopy(result)

    async def admit_run(self, intent_id, run_id):
        def change(doc):
            if doc["run_id"] not in (None, run_id):
                raise ContractDenied("RUN_BINDING_CONFLICT")
            doc["run_id"] = run_id

        await self._mutate(intent_id, change)

    async def freeze(self, contract: ExecutionContract):
        # Revalidate nested mutable values; store a detached JSON copy.
        kind = PlanningContract if isinstance(contract, PlanningContract) else ExecutionContract
        contract = kind.model_validate(contract.model_dump())

        def change(doc):
            if contract.run_id is not None and contract.run_id != doc["run_id"]:
                raise ContractDenied("RUN_BINDING_CONFLICT")
            object_identity = {"object_id": contract.object_id, "as_of": contract.as_of}
            if doc.get("object_identity", object_identity) != object_identity:
                raise ContractDenied("RESEARCH_INTENT_IDENTITY_CONFLICT")
            doc["object_identity"] = object_identity
            if contract.run_id is not None:
                identity = {
                    key: getattr(contract, key)
                    for key in ("run_id", "scheme_id", "scheme_hash", "object_id", "as_of")
                }
                if doc.get("research_identity", identity) != identity:
                    raise ContractDenied("RESEARCH_INTENT_IDENTITY_CONFLICT")
                doc["research_identity"] = identity
            old = doc["operations"].get(contract.operation_id)
            if old:
                if old["contract_hash"] != contract.contract_hash:
                    raise ContractDenied("APPROVAL_CONTRACT_CHANGED")
                return old
            for other in doc["operations"].values():
                prior = other["contract"]
                if prior["task_id"] == contract.task_id and (
                    prior["task_budget"] != contract.task_budget.model_dump()
                    or prior["task_deadline"] != contract.task_deadline
                ):
                    raise ContractDenied("TASK_BUDGET_DRIFT")
            op = {
                "contract": contract.model_dump(mode="json"),
                "contract_hash": contract.contract_hash,
                "status": "PENDING",
                "epoch": 0,
                "lease_until": 0,
                "owner": None,
                "attempts": [],
                "published": {},
                "checkpoint": None,
                "failures": [],
                "authorizations": {},
            }
            doc["operations"][contract.operation_id] = op
            return op

        return await self._mutate(contract.intent_id, change)

    @staticmethod
    def _op(doc, operation_id):
        op = doc["operations"].get(operation_id)
        if op is None:
            raise ContractDenied("LEGACY_NOT_RESUMABLE")
        if fingerprint(op["contract"]) != op["contract_hash"]:
            raise ContractDenied("CONTRACT_CORRUPT")
        return op

    def _fence(self, doc, token, now):
        if not isfinite(now):
            raise ContractDenied("INVALID_CLOCK")
        op = self._op(doc, token.operation_id)
        if (
            op["epoch"] != token.epoch
            or op["owner"] != token.owner
            or op["lease_until"] <= now
            or op["status"] != "CLAIMED"
        ):
            raise ContractDenied("STALE_EXECUTION_OWNER")
        parent = op.get("coordinator")
        if parent:
            self._fence(doc, LeaseToken.model_validate(parent), now)
        return op

    async def claim(self, intent_id, operation_id, owner, now, lease_seconds, coordinator=None):
        def change(doc):
            if not isfinite(now) or not isfinite(lease_seconds):
                raise ContractDenied("INVALID_CLOCK")
            if coordinator is not None:
                if coordinator.intent_id != intent_id or coordinator.operation_id == operation_id:
                    raise ContractDenied("COORDINATOR_IDENTITY_MISMATCH")
                coordinator_op = self._fence(doc, coordinator, now)
                if coordinator_op.get("coordinator"):
                    raise ContractDenied("NESTED_COORDINATOR_UNSUPPORTED")
            op = self._op(doc, operation_id)
            contract = op["contract"]
            if min(doc["deadline"], contract["deadline"], contract["task_deadline"]) <= now:
                raise ContractDenied("TOTAL_DEADLINE_EXHAUSTED")
            if lease_seconds <= 0 or not owner:
                raise ContractDenied("INVALID_LEASE")
            if op["status"] == "COMPLETE":
                raise ContractDenied("ALREADY_COMPLETE")
            if op["lease_until"] > now and op["status"] == "CLAIMED":
                raise ContractDenied("OWNER_LEASE_ACTIVE")
            if op["status"] == "FAILED":
                failure_hash = fingerprint(op["failures"][-1]) if op["failures"] else None
                auth = next(
                    (
                        v
                        for v in op["authorizations"].values()
                        if not v["consumed"] and v.get("failure_hash") == failure_hash
                    ),
                    None,
                )
                if auth is None:
                    raise ContractDenied("RECOVERY_AUTHORIZATION_REQUIRED")
                auth["consumed"] = True
            for call in doc["calls"].values():
                if call["operation_id"] != operation_id:
                    continue
                if call["state"] == "DISPATCHED":
                    call["state"] = "RESULT_UNKNOWN"
                elif call["state"] == "RESERVED":
                    call["state"] = "CANCELLED_UNSENT"
            op.update(
                epoch=op["epoch"] + 1,
                owner=owner,
                status="CLAIMED",
                lease_until=min(
                    now + lease_seconds,
                    doc["deadline"],
                    contract["deadline"],
                    contract["task_deadline"],
                ),
            )
            if coordinator is not None:
                op["coordinator"] = coordinator.model_dump()
                op["lease_until"] = min(op["lease_until"], coordinator_op["lease_until"])
            elif op.get("coordinator"):
                raise ContractDenied("COORDINATOR_REQUIRED")
            op["attempts"].append({"epoch": op["epoch"], "owner": owner, "started_at": now})
            return LeaseToken(
                intent_id=intent_id, operation_id=operation_id, owner=owner, epoch=op["epoch"]
            )

        return await self._mutate(intent_id, change)

    @staticmethod
    def _check_budget(budget, calls, purpose, estimated_cost):
        active = [c for c in calls if c["state"] != "CANCELLED_UNSENT"]
        if len(active) >= budget["physical_calls"]:
            raise ContractDenied("PHYSICAL_BUDGET_EXHAUSTED")
        field = {
            CallPurpose.TASK_EXECUTION: "execution_calls",
            CallPurpose.CAPABILITY_CHECK: "check_calls",
            CallPurpose.DECISION: "decision_calls",
        }.get(purpose)
        if field and sum(c["purpose"] == purpose for c in active) >= budget[field]:
            raise ContractDenied("PURPOSE_BUDGET_EXHAUSTED")
        if budget["max_cost"] is not None:
            if estimated_cost is None or any(c["cost_reserved"] is None for c in active):
                raise ContractDenied("COST_METERING_UNAVAILABLE")
            used = sum(
                c["actual_cost"] if c["actual_cost"] is not None else c["cost_reserved"]
                for c in active
            )
            if used + estimated_cost > budget["max_cost"]:
                raise ContractDenied("COST_BUDGET_EXHAUSTED")

    async def reserve(self, token, call_id, purpose, route, now, timeout, estimated_cost=None):  # noqa: ASYNC109
        # timeout is a durable budget field; the transport enforces asyncio.timeout.
        purpose = CallPurpose(purpose)

        def change(doc):
            op = self._fence(doc, token, now)
            c = op["contract"]
            if call_id in doc["calls"]:
                raise ContractDenied("CALL_ID_ALREADY_RESERVED")
            if route not in c["candidates"]:
                raise ContractDenied("CANDIDATE_NOT_AUTHORIZED")
            relevant = [v for v in doc["calls"].values() if v["operation_id"] == token.operation_id]
            if any(v["state"] == "RESULT_UNKNOWN" for v in relevant):
                raise ContractDenied("RESULT_UNKNOWN_REQUIRES_RECONCILIATION")
            deadline = min(doc["deadline"], c["deadline"], c["task_deadline"], op["lease_until"])
            remaining = deadline - now
            if remaining <= 0 or timeout <= 0 or not isfinite(timeout):
                raise ContractDenied("TOTAL_DEADLINE_EXHAUSTED")
            if estimated_cost is not None and (estimated_cost < 0 or not isfinite(estimated_cost)):
                raise ContractDenied("INVALID_COST")
            self._check_budget(doc["budget"], doc["calls"].values(), purpose, estimated_cost)
            self._check_budget(c["budget"], relevant, purpose, estimated_cost)
            self._check_budget(
                c["task_budget"],
                [v for v in doc["calls"].values() if v["task_id"] == c["task_id"]],
                purpose,
                estimated_cost,
            )
            call = {
                "call_id": call_id,
                "operation_id": token.operation_id,
                "task_id": c["task_id"],
                "epoch": token.epoch,
                "contract_hash": op["contract_hash"],
                "purpose": purpose.value,
                "route": route,
                "state": "RESERVED",
                "reserved_at": now,
                "timeout": min(timeout, c["per_call_timeout"], remaining),
                "absolute_deadline": deadline,
                "cost_reserved": estimated_cost,
                "actual_cost": None,
                "result": None,
                "result_hash": None,
                "consumed": False,
            }
            doc["calls"][call_id] = call
            return call

        return await self._mutate(token.intent_id, change)

    async def _call_change(self, token, call_id, now, change):
        def mutation(doc):
            self._fence(doc, token, now)
            call = doc["calls"].get(call_id)
            if call is None or call["operation_id"] != token.operation_id:
                raise ContractDenied("CALL_IDENTITY_MISMATCH")
            return change(call)

        return await self._mutate(token.intent_id, mutation)

    async def dispatch(self, token, call_id, now):
        def change(call):
            if call["state"] != "RESERVED" or call["epoch"] != token.epoch:
                raise ContractDenied("CALL_NOT_RESERVED")
            remaining = call["absolute_deadline"] - now
            if remaining <= 0:
                raise ContractDenied("TOTAL_DEADLINE_EXHAUSTED")
            call["timeout"] = min(call["timeout"], remaining)
            call.update(state="DISPATCHED", dispatched_at=now)
            return call

        return await self._call_change(token, call_id, now, change)

    async def save_result(self, token, call_id, payload, now):
        payload = deepcopy(payload)

        def change(call):
            digest = fingerprint(payload)
            if call["state"] in {"RESULT_SAVED", "SETTLED"} and call["result_hash"] == digest:
                return call
            if call["state"] != "DISPATCHED" or call["epoch"] != token.epoch:
                raise ContractDenied("CALL_RESULT_CONFLICT")
            call.update(state="RESULT_SAVED", result=payload, result_hash=digest)
            return call

        return await self._call_change(token, call_id, now, change)

    async def settle(self, token, call_id, now, actual_cost=None):
        def change(call):
            if actual_cost is not None and (actual_cost < 0 or not isfinite(actual_cost)):
                raise ContractDenied("INVALID_COST")
            if call["state"] == "SETTLED":
                if call["actual_cost"] != actual_cost:
                    raise ContractDenied("SETTLEMENT_CONFLICT")
                return call
            if call["state"] != "RESULT_SAVED":
                raise ContractDenied("RESULT_NOT_SAVED")
            call.update(state="SETTLED", actual_cost=actual_cost)
            return call

        return await self._call_change(token, call_id, now, change)

    async def cancel(self, token, call_id, now):
        def change(call):
            if call["state"] not in {"RESERVED", "CANCELLED_UNSENT"}:
                raise ContractDenied("POSSIBLY_SENT_NOT_REFUNDABLE")
            call["state"] = "CANCELLED_UNSENT"
            return call

        return await self._call_change(token, call_id, now, change)

    async def mark_unknown(self, token, call_id, now):
        def change(call):
            if call["state"] not in {"DISPATCHED", "RESULT_UNKNOWN"}:
                raise ContractDenied("UNKNOWN_STATE_CONFLICT")
            call["state"] = "RESULT_UNKNOWN"
            return call

        return await self._call_change(token, call_id, now, change)

    async def consume_check(self, token, call_id, result_hash, actual_route, now):
        def change(doc):
            op = self._fence(doc, token, now)
            call = doc["calls"].get(call_id)
            expected_identity = {
                "contract_hash": op["contract_hash"],
                "task_id": op["contract"]["task_id"],
                "operation_id": token.operation_id,
                "input_hashes": op["contract"]["input_hashes"],
            }
            provider_model = {
                "teamorouter-sol": ("teamorouter", "gpt-5.6-sol"),
                "teamorouter-luna": ("teamorouter", "gpt-5.6-luna"),
                "teamorouter-terra": ("teamorouter", "gpt-5.6-terra"),
                "mimo-direct": ("mimo", "mimo-v2.5"),
            }.get(actual_route)
            if (
                call is None
                or not isinstance(call["result"], dict)
                or call["operation_id"] != token.operation_id
                or call["contract_hash"] != op["contract_hash"]
                or call["purpose"] != "CAPABILITY_CHECK"
                or call["state"] not in {"RESULT_SAVED", "SETTLED"}
                or call["result_hash"] != result_hash
                or fingerprint(call["result"]) != result_hash
                or any(call["result"].get(key) != value for key, value in expected_identity.items())
                or provider_model is None
                or (call["result"].get("actual_provider"), call["result"].get("actual_model"))
                != provider_model
                or op["contract"]["check_consumption"] != "EXACT_VALIDATED_ONCE"
                or call["result"].get("validated") is not True
                or call["result"].get("schema_hash") != op["contract"]["schema_hash"]
                or actual_route != call["route"]
                or call["result"].get("actual_route") != actual_route
            ):
                raise ContractDenied("CHECK_NOT_EXACT_VALIDATED")
            if not call["consumed"]:
                # Atomic consumption and authoritative publication close the crash
                # window; identical replay returns the saved output, not another call.
                op["published"]["CHECK_OUTPUT:" + call_id] = {
                    "reference": call_id,
                    "payload": deepcopy(call["result"]),
                    "hash": result_hash,
                    "epoch": token.epoch,
                    "contract_hash": op["contract_hash"],
                }
                call["consumed"] = True
            return call["result"]

        return await self._mutate(token.intent_id, change)

    async def publish(self, token, kind, reference, payload, now):
        payload = deepcopy(payload)

        def change(doc):
            op = self._fence(doc, token, now)
            key = kind + ":" + reference
            value = {
                "reference": reference,
                "payload": payload,
                "hash": fingerprint(payload),
                "epoch": token.epoch,
                "contract_hash": op["contract_hash"],
            }
            prior = op["published"].get(key)
            if prior and prior["hash"] != value["hash"]:
                raise ContractDenied("IMMUTABLE_PUBLICATION_CONFLICT")
            if not prior:
                op["published"][key] = value
            return op["published"][key]

        return await self._mutate(token.intent_id, change)

    async def checkpoint(self, token, payload, now):
        def change(doc):
            op = self._fence(doc, token, now)
            op["checkpoint"] = {
                "version": 2,
                "contract_hash": op["contract_hash"],
                "owner": token.model_dump(),
                "deadline": op["contract"]["deadline"],
                "task_deadline": op["contract"]["task_deadline"],
                "intent_deadline": doc["deadline"],
                "compatibility": op["contract"]["compatibility"],
                "published": deepcopy(op["published"]),
                "ledger": deepcopy(doc["calls"]),
                "payload": deepcopy(payload),
            }
            return op["checkpoint"]

        return await self._mutate(token.intent_id, change)

    async def complete(self, token, now):
        def change(doc):
            op = self._fence(doc, token, now)
            if any(
                c["operation_id"] == token.operation_id
                and c["state"] in {"RESERVED", "DISPATCHED", "RESULT_UNKNOWN"}
                for c in doc["calls"].values()
            ):
                raise ContractDenied("UNRESOLVED_CALLS")
            op["status"] = "COMPLETE"

        await self._mutate(token.intent_id, change)

    async def fail(self, token, failure, now):
        def change(doc):
            op = self._fence(doc, token, now)
            op["failures"].append({"epoch": token.epoch, "failure": failure, "at": now})
            op["status"] = "FAILED"

        await self._mutate(token.intent_id, change)

    async def authorize_recovery(
        self,
        intent_id,
        operation_id,
        authorization_id,
        contract_hash,
        actor=None,
        request_hash=None,
    ):
        def change(doc):
            op = self._op(doc, operation_id)
            identity = {
                "actor": actor,
                "request_hash": request_hash,
                "contract_hash": contract_hash,
            }
            old = op["authorizations"].get(authorization_id)
            if old:
                if any(old.get(k) != v for k, v in identity.items()):
                    raise ContractDenied("RECOVERY_IDEMPOTENCY_CONFLICT")
                return old
            if op["contract_hash"] != contract_hash or op["status"] != "FAILED":
                raise ContractDenied("RECOVERY_AUTHORIZATION_MISMATCH")
            op["authorizations"][authorization_id] = {
                **identity,
                "consumed": False,
                "failure_hash": fingerprint(op["failures"][-1]),
            }
            return op["authorizations"][authorization_id]

        return await self._mutate(intent_id, change)

    async def advance_release(
        self, token, stage, reference, object_id, now, memory_authorized=False
    ):
        stages = ["PREPARED", "RELEASED", "MEMORY_MATERIALIZED", "COMPLETED"]

        def change(doc):
            op = self._fence(doc, token, now)
            if object_id != op["contract"]["object_id"] or not doc["run_id"]:
                raise ContractDenied("RELEASE_IDENTITY_MISMATCH")
            history = doc["release"]
            if any(
                v["object_id"] != object_id or v["run_id"] != doc["run_id"]
                for v in history.values()
            ):
                raise ContractDenied("RELEASE_IDENTITY_MISMATCH")
            if stage not in stages:
                raise ContractDenied("UNSUPPORTED_STAGE")
            if stage in history:
                if history[stage]["reference"] != reference:
                    raise ContractDenied("RELEASE_BINDING_CONFLICT")
                return history
            if stages.index(stage) != len(history):
                raise ContractDenied("RELEASE_STAGE_ORDER")
            if stage == "MEMORY_MATERIALIZED" and not memory_authorized:
                raise ContractDenied("MEMORY_AUTHORIZATION_REQUIRED")
            history[stage] = {
                "reference": reference,
                "object_id": object_id,
                "run_id": doc["run_id"],
                "epoch": token.epoch,
            }
            return history

        return await self._mutate(token.intent_id, change)
