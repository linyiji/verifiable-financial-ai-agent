"""Explicit local-user Resume boundary over the frozen repository command."""

from typing import Literal

from src.domain.external_failure_resume import (
    ExternalFailureAuditV1,
    ResumeExternalFailure,
    ResumeReceiptV1,
)
from src.domain.node_binding import BindingDenied, BindingValue, canonical_value

LOCAL_ACTOR = "LOCAL_SINGLE_USER"


class AuthorizeExternalResume(ResumeExternalFailure):
    authorize_resume: Literal[True]


class ExternalResumeProjection(BindingValue):
    schema_version: Literal["external-failure-control/v1"]
    run_id: str
    state: str
    lifecycle: str
    binding_revision: int
    owner_generation: int
    current_failure_id: str | None
    current_cycle_id: str | None
    audit: tuple[ExternalFailureAuditV1, ...]
    cycle_status: str
    failed_cycles: tuple[dict, ...]
    authorized_cycles: tuple[dict, ...]
    authoritative_risk_result: str | None
    legal_actions: tuple[dict, ...]
    denial_reasons: tuple[str, ...]


class ExternalResumeResponse(BindingValue):
    outcome: Literal["DENIED", "STALE_RESUME_REJECTED", "AUTHORIZED", "IDEMPOTENT"]
    receipt: ResumeReceiptV1 | None
    reason: str | None = None
    projection: ExternalResumeProjection | None = None


def public_state(run_id, inspected):
    control = inspected["control"] or {}
    audit = control.get("audit", [])
    latest = audit[-1]["type"] if audit else None
    lifecycle = inspected["lifecycle"]
    state = {
        "EXTERNAL_FAILURE_PAUSED": "EXTERNAL_FAILURE_PAUSED",
        "EXTERNAL_RESUME_PENDING": "EXTERNAL_RESUME_PENDING",
    }.get(
        lifecycle,
        {
            "external_failure.cycle_claimed": "RISK_RESUME_CYCLE_RUNNING",
            "external_failure.cycle_succeeded": "RISK_RESUME_CYCLE_SUCCEEDED",
            "external_failure.closed": "RISK_RESUME_CYCLE_EXHAUSTED",
        }.get(latest, lifecycle),
    )
    if inspected["legal_actions"] and not audit:
        state = "EXTERNAL_FAILURE_PAUSED"
    return dict(
        schema_version="external-failure-control/v1",
        run_id=run_id,
        state=state,
        lifecycle=lifecycle,
        binding_revision=inspected["binding_ref"]["binding_revision"],
        owner_generation=inspected["owner_generation"],
        current_failure_id=control.get("current_failure_id"),
        current_cycle_id=control.get("current_cycle_id"),
        audit=audit,
        cycle_status=(
            "EXHAUSTED"
            if latest == "external_failure.closed" and control.get("current_cycle_id")
            else state
        ),
        failed_cycles=[
            {
                key: failure[key]
                for key in (
                    "failure_id",
                    "identity",
                    "task_id",
                    "original_completed_at",
                    "closed_at",
                )
            }
            for failure in control.get("failures", [])
        ],
        authorized_cycles=[
            {
                key: cycle[key]
                for key in (
                    "cycle_id",
                    "authorization_id",
                    "cycle_ordinal",
                    "routes",
                    "authorized_at",
                )
            }
            for cycle in control.get("envelopes", [])
        ],
        authoritative_risk_result=inspected["authoritative_risk_result"],
        legal_actions=inspected["legal_actions"],
        denial_reasons=inspected["denial_reasons"],
    )


async def read(backend, run_id):
    await backend.get_run(run_id)
    inspected = await backend.service.repository.inspect_external_failure(run_id, actor=LOCAL_ACTOR)
    return public_state(run_id, inspected)


async def decide(backend, run_id, payload, key):
    # The same server-local single-user authority as structured Replan. Caller
    # headers and chat content cannot select another actor or grant permission.
    await backend.get_run(run_id)
    if payload.run_id != run_id or payload.actor != LOCAL_ACTOR or payload.idempotency_key != key:
        return dict(outcome="DENIED", reason="RESUME_AUTHORITY_MISMATCH", receipt=None)
    command = ResumeExternalFailure.model_validate(payload.model_dump(exclude={"authorize_resume"}))
    before = await backend.service.repository.get_run_fresh(run_id)
    observed_authorizations = {
        item["authorization_id"]
        for item in (before.node_binding.external_failure_resume or {}).get("receipts", [])
    }
    try:
        receipt = await backend.service.repository.resume_external_failure(
            command, actor=LOCAL_ACTOR
        )
    except BindingDenied as exc:
        return dict(
            outcome="STALE_RESUME_REJECTED",
            reason=exc.code,
            receipt=None,
            projection=await read(backend, run_id),
        )
    backend._wake.set()
    try:
        projection = await read(backend, run_id)
    except BindingDenied:
        # Current projection/material availability cannot revoke a committed receipt.
        projection = None
    # Every successful delivery returns the same durable receipt, including its
    # authorization and cycle identity. Current state is read afresh on replay.
    return dict(
        outcome=(
            "IDEMPOTENT" if receipt.authorization_id in observed_authorizations else "AUTHORIZED"
        ),
        receipt=canonical_value(receipt),
        projection=projection,
    )
