"""Canonical identity for the root-owned, co-committed failure event.

The runtime event row is the only receipt. No new event log or Resume authority
is created here; PostgreSQL's root lock, event allocator and transaction own it.
"""
from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from src.domain.enums import RunStatus
from src.domain.node_binding import BindingDenied, canonical_value, digest

SCHEMA = "terminal-failure/v1"


class FailureReplay(Exception):
    def __init__(self, event):
        self.event = event


def aggregate_payload(aggregate):
    from src.application.persistence import SQLAlchemyApplicationRepository

    return SQLAlchemyApplicationRepository._payload(aggregate)


def failure_command(owner, proposed, unknown, payload):
    if (
        proposed.run.run_id != owner.run_id
        or proposed.run.status is not RunStatus.FAILED
        or proposed.runtime.run_status is not RunStatus.FAILED
        or proposed.run.completed_at is None
        or payload.get("status") != "FAILED"
    ):
        raise BindingDenied("IDENTITY_MISMATCH", "terminal failure command")
    if (proposed.node_binding is not None
            and proposed.runtime.binding_ref != proposed.node_binding.reference()):
        raise BindingDenied("IDENTITY_MISMATCH", "terminal command root reference")
    identity = digest(canonical_value(owner), SCHEMA)
    return {
        "event_id": "EVT-" + str(uuid5(NAMESPACE_URL, SCHEMA + identity)),
        "owner": canonical_value(owner),
        "request_digest": digest({
            "owner": owner, "proposed": aggregate_payload(proposed),
            "unknown": unknown, "payload": payload,
        }, SCHEMA),
        "payload": deepcopy(payload),
    }


def failure_payload(aggregate, command, predecessor, causal, terminal_revision):
    payload = deepcopy(command["payload"])
    payload["terminal_failure"] = {
        "schema": SCHEMA,
        "event_id": command["event_id"],
        "run_id": aggregate.run.run_id,
        "completed_at": aggregate.run.completed_at.isoformat(),
        "status": "FAILED",
        "terminal_failure_projection_revision": terminal_revision,
        "owner": command["owner"],
        "binding_ref": canonical_value(aggregate.node_binding.reference()),
        "root_digest": digest(aggregate_payload(aggregate), SCHEMA),
        "request_digest": command["request_digest"],
        "predecessor_event_id": predecessor.event_id if predecessor else None,
        "predecessor_sequence": predecessor.sequence if predecessor else 0,
        "causal_task_failed_event_id": causal.event_id if causal else None,
        "causal_task_failed_sequence": causal.sequence if causal else None,
    }
    payload["terminal_failure"]["payload_digest"] = digest(payload, SCHEMA)
    return payload


def verify_failure_event(event):
    metadata = event.payload.get("terminal_failure")
    if metadata is None:
        return  # Existing historical and other terminal owners retain their contracts.
    payload = deepcopy(event.payload)
    expected = payload["terminal_failure"].pop("payload_digest", None)
    if (
        expected != digest(payload, SCHEMA)
        or metadata.get("schema") != SCHEMA
        or metadata.get("event_id") != event.event_id
        or metadata.get("run_id") != event.run_id
        or metadata.get("completed_at") != event.timestamp.isoformat()
        or metadata.get("status") != "FAILED"
        or event.payload.get("status") != "FAILED"
        or event.type.value != "run.failed"
        or metadata.get("predecessor_sequence") != event.sequence - 1
    ):
        raise BindingDenied("IDENTITY_MISMATCH", "terminal failure event")


def verify_failure_replay(aggregate, event, command):
    verify_failure_event(event)
    metadata = event.payload.get("terminal_failure", {})
    business_payload = deepcopy(event.payload)
    business_payload.pop("terminal_failure", None)
    if (
        business_payload != command["payload"]
        or metadata.get("request_digest") != command["request_digest"]
        or metadata.get("owner") != command["owner"]
        or metadata.get("binding_ref") != canonical_value(aggregate.node_binding.reference())
        or metadata.get("root_digest") != digest(aggregate_payload(aggregate), SCHEMA)
        or aggregate.run.status is not RunStatus.FAILED
        or aggregate.run.completed_at != event.timestamp
    ):
        raise BindingDenied("IDENTITY_MISMATCH", "terminal failure replay")
