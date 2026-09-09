"""Opt-in recovery read/authorization API; deliberately not mounted by default.

The host must inject its identity/permission resolver and the V1 durable store.
This router never admits a Run, calls a Provider, or manufactures an actor from
request headers. Authorization leaves execution to the durable delivery runner.
"""

import re
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from src.domain.execution_contract import ContractDenied, Immutable, fingerprint


class RecoverRequest(Immutable):
    contract_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    action: Literal["AUTHORIZE_FAILED_OPERATION"]


def create_recovery_router(
    store,
    *,
    resolve_actor: Callable[[Request, str, str], Awaitable[str]],
    clock,
    actions_accepted=False,
):
    router = APIRouter(prefix="/api/research-runs", tags=["recoverable-execution-v1"])

    async def operation(run_id, intent_id, operation_id):
        try:
            doc = await store.view(intent_id)
        except ContractDenied as exc:
            raise HTTPException(409, str(exc)) from None
        op = doc["operations"].get(operation_id)
        if doc["run_id"] != run_id or op is None or op["contract"]["run_id"] != run_id:
            raise HTTPException(404, "RECOVERY_IDENTITY_NOT_FOUND")
        return doc, op

    @router.get("/{run_id}/recovery/{intent_id}/{operation_id}")
    async def read(run_id: str, intent_id: str, operation_id: str, request: Request):
        actor = await resolve_actor(request, run_id, "recovery:read")
        if not actor:
            raise HTTPException(403, "RECOVERY_ACCESS_DENIED")
        doc, op = await operation(run_id, intent_id, operation_id)
        c = op["contract"]
        calls = [v for v in doc["calls"].values() if v["state"] != "CANCELLED_UNSENT"]
        relevant = [v for v in calls if v["operation_id"] == operation_id]
        remaining = min(doc["deadline"], c["deadline"], c["task_deadline"]) - clock()
        unknown = any(v["state"] in {"DISPATCHED", "RESULT_UNKNOWN"} for v in relevant)
        exhausted = (
            len(calls) >= doc["budget"]["physical_calls"]
            or len(relevant) >= c["budget"]["physical_calls"]
        )
        denial = (
            "ACTIONS_NOT_ACCEPTED"
            if not actions_accepted
            else "RESULT_UNKNOWN_REQUIRES_RECONCILIATION"
            if unknown
            else "TOTAL_DEADLINE_EXHAUSTED"
            if remaining <= 0
            else "PHYSICAL_BUDGET_EXHAUSTED"
            if exhausted
            else "NOT_BUSINESS_FAILED"
            if op["status"] != "FAILED"
            else None
        )
        failure = op["failures"][0].get("failure") if op["failures"] else None
        failure_code = failure.get("code") if isinstance(failure, dict) else None
        if not isinstance(failure_code, str) or not re.fullmatch(r"[A-Z0-9_]{1,128}", failure_code):
            failure_code = "UNKNOWN" if failure is not None else None
        return {
            "version": "recovery-summary/v1",
            "run_id": run_id,
            "intent_id": intent_id,
            "operation_id": operation_id,
            "contract_hash": op["contract_hash"],
            "status": op["status"],
            "original_failure": failure_code,
            "attempt": op["epoch"],
            "scope": [c["task_id"]],
            "reusable_output_refs": [
                v["reference"]
                for v in op["published"].values()
                if isinstance(v["payload"], dict) and v["payload"].get("validated") is True
            ],
            "physical_calls_used": len(calls),
            "physical_calls_limit": doc["budget"]["physical_calls"],
            "deadline": min(doc["deadline"], c["deadline"], c["task_deadline"]),
            "recoverable": denial is None,
            "denial_reason": denial,
            "accepted_actions": ["AUTHORIZE_FAILED_OPERATION"] if denial is None else [],
            "execution_started": False,
        }

    @router.post("/{run_id}/recovery/{intent_id}/{operation_id}")
    async def authorize(
        run_id: str,
        intent_id: str,
        operation_id: str,
        body: RecoverRequest,
        request: Request,
    ):
        actor = await resolve_actor(request, run_id, "recovery:authorize")
        if not actor:
            raise HTTPException(403, "RECOVERY_ACCESS_DENIED")
        if not actions_accepted:
            raise HTTPException(409, "ACTIONS_NOT_ACCEPTED")
        keys = request.headers.getlist("Idempotency-Key")
        if len(keys) != 1 or not 1 <= len(keys[0].strip()) <= 128:
            raise HTTPException(400, "IDEMPOTENCY_KEY_REQUIRED")
        doc, op = await operation(run_id, intent_id, operation_id)
        authorization_id = fingerprint(
            {"actor": actor, "key": keys[0], "run": run_id, "operation": operation_id}
        )
        request_hash = fingerprint(body)
        if authorization_id not in op["authorizations"]:
            c = op["contract"]
            if min(doc["deadline"], c["deadline"], c["task_deadline"]) <= clock():
                raise HTTPException(409, "TOTAL_DEADLINE_EXHAUSTED")
            if any(
                v["operation_id"] == operation_id and v["state"] in {"DISPATCHED", "RESULT_UNKNOWN"}
                for v in doc["calls"].values()
            ):
                raise HTTPException(409, "RESULT_UNKNOWN_REQUIRES_RECONCILIATION")
        try:
            await store.authorize_recovery(
                intent_id,
                operation_id,
                authorization_id,
                body.contract_hash,
                actor=actor,
                request_hash=request_hash,
            )
        except ContractDenied as exc:
            raise HTTPException(409, str(exc)) from None
        return {
            "version": "recovery-authorization/v1",
            "run_id": run_id,
            "operation_id": operation_id,
            "authorization_id": authorization_id,
            "status": "AUTHORIZED_PENDING_DELIVERY",
            "execution_started": False,
            "new_run_created": False,
        }

    return router
