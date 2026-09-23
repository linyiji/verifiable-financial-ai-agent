"""Execution authority for explicitly authorized same-Run Risk cycles."""

from datetime import UTC, datetime
from uuid import uuid4

from src.application.external_failure_resume import (
    audit_event,
    control,
    current_envelope,
    settled_failure,
    validate_reuse,
)
from src.domain.external_failure_resume import FailureClosureV1
from src.domain.node_binding import BindingDenied, canonical_value


def cycle_for(aggregate, task_id):
    cycle = current_envelope(aggregate)
    return cycle if cycle is not None and cycle.task_id == task_id else None


def cycle_attempt_number(aggregate, reservation):
    cycle = cycle_for(aggregate, reservation.admission.task_id)
    if cycle is None:
        return reservation.generation
    validate_cycle_admission(aggregate, reservation.admission)
    return reservation.generation - cycle.prior_failure_cycle_identity.failed_reservation_generation


def validate_cycle_admission(aggregate, admission):
    cycle = cycle_for(aggregate, admission.task_id)
    supplied = admission.policy_refs.get("external_resume_cycle")
    if cycle is None:
        if supplied is not None:
            raise BindingDenied("RESUME_CYCLE_MISMATCH")
        return
    if (
        supplied != cycle.cycle_id
        or admission.policy_refs.get("external_resume_authorization") != cycle.authorization_id
        or admission.policy_refs.get("external_resume_ordinal") != cycle.cycle_ordinal
    ):
        raise BindingDenied("RESUME_CYCLE_MISMATCH")


def current_risk_success(aggregate):
    from src.application.repository import confirmed_risk_authority

    confirmed_risk_authority(aggregate)
    cycle = current_envelope(aggregate)
    if cycle is None:
        return False
    root = aggregate.node_binding
    result = root.results.get(root.current_results.get(cycle.task_id))
    attempt = root.attempts.get(cycle.task_id)
    if result is None or attempt is None or attempt.status != "COMMITTED":
        return False
    validate_cycle_admission(aggregate, attempt.admission)
    if (
        result.reservation_id != attempt.admission.attempt_reservation_id
        or result.admission_binding_id != attempt.admission.admission_binding_id
        or result.result_id in root.invalidation_refs
        or result.graph != cycle.graph
        or aggregate.runtime.task(cycle.task_id).status.value != "COMPLETED"
    ):
        return False
    from src.application.risk_admission import _require_final
    from src.domain.risk_admission import _contract_for_validated

    _require_final(aggregate, result, _contract_for_validated(aggregate))
    return any(
        r.kind == "AGENT_OUTPUT" and r.payload_snapshot.get("status") == "SUCCESS"
        for r in result.output_records
    )


async def validate_retained(repository, aggregate, cycle):
    task = aggregate.runtime.task(cycle.task_id)
    decisions = await validate_reuse(repository, aggregate, task)
    receipt = next(r for r in control(aggregate).receipts if r.new_cycle_id == cycle.cycle_id)

    # Binding references advance as this cycle executes. Producer closures do not.
    def stable(values):
        return [v.model_dump(exclude={"binding_ref"}) for v in values]

    if stable(decisions) != stable(receipt.reuse_manifest):
        raise BindingDenied("RESUME_REUSE_INVALID", "authorized producer closure changed")


async def claim_cycle(repository, aggregate):
    if aggregate.node_binding.lifecycle != "EXTERNAL_RESUME_PENDING":
        return False
    cycle = current_envelope(aggregate)
    if cycle is None or datetime.now(UTC) >= cycle.deadline_at:
        raise BindingDenied("RESUME_AUTHORIZATION_EXPIRED")
    await validate_retained(repository, aggregate, cycle)
    state = control(aggregate)
    if any(
        e["type"] == "external_failure.cycle_claimed" and e["cycle_id"] == cycle.cycle_id
        for e in state.audit
    ):
        raise BindingDenied("OWNER_ALREADY_CLAIMED")
    event = audit_event(
        aggregate,
        "cycle_claimed",
        failure_id=state.current_failure_id,
        cycle_id=cycle.cycle_id,
        authorization_id=cycle.authorization_id,
    )
    aggregate.node_binding.external_failure_resume = state.model_copy(
        update={"audit": (*state.audit, event)}
    ).model_dump(mode="json")
    return True


async def reserve_cycle(repository, aggregate, task):
    cycle = current_envelope(aggregate)
    if cycle is None:
        return None
    if task.task_id == cycle.task_id:
        if datetime.now(UTC) >= cycle.deadline_at:
            raise BindingDenied("RESUME_AUTHORIZATION_EXPIRED")
        await validate_retained(repository, aggregate, cycle)
        return cycle
    if task.task_type != "report_synthesis" or not current_risk_success(aggregate):
        raise BindingDenied("RESUME_CURRENT_RISK_SUCCESS_REQUIRED")
    await validate_retained(repository, aggregate, cycle)
    return None


def committed_cycle(aggregate, task):
    cycle = cycle_for(aggregate, task.task_id)
    if cycle is None:
        return
    if not current_risk_success(aggregate):
        raise BindingDenied("RESUME_CURRENT_RISK_SUCCESS_REQUIRED")
    state = control(aggregate)
    event = audit_event(
        aggregate,
        "cycle_succeeded",
        failure_id=state.current_failure_id,
        cycle_id=cycle.cycle_id,
        authorization_id=cycle.authorization_id,
    )
    aggregate.node_binding.external_failure_resume = state.model_copy(
        update={"audit": (*state.audit, event)}
    ).model_dump(mode="json")


async def settle_cycle(repository, aggregate):
    cycle = current_envelope(aggregate)
    if cycle is None or aggregate.run.status.value != "FAILED":
        return False
    try:
        records = await repository._current_recovery_records(aggregate.run.run_id, cycle.task_id)
        identity, prior, receipts = settled_failure(aggregate, cycle.task_id, records)
    except BindingDenied:
        # Unknown/mixed failure remains closed. Lease expiry grants no authority.
        return False
    if identity.operation_id != cycle.operation_id:
        return False
    state = control(aggregate)
    now = datetime.now(UTC)
    closure = FailureClosureV1(
        failure_id="failure:" + str(uuid4()),
        identity=identity,
        task_id=cycle.task_id,
        original_completed_at=aggregate.run.completed_at,
        closed_at=now,
        archived_reservation=canonical_value(prior),
        receipts=tuple(canonical_value(r) for r in receipts),
    )
    root = aggregate.node_binding
    root.attempt_history[identity.failed_reservation_id] = prior
    event = audit_event(
        aggregate,
        "closed",
        failure_id=closure.failure_id,
        cycle_id=cycle.cycle_id,
        authorization_id=cycle.authorization_id,
    )
    root.external_failure_resume = state.model_copy(
        update={
            "failures": (*state.failures, closure),
            "current_failure_id": closure.failure_id,
            "audit": (*state.audit, event),
        }
    ).model_dump(mode="json")
    root.owner_generation += 1
    root.owner_id = None
    root.scheduler_started = False
    root.lifecycle = "EXTERNAL_FAILURE_PAUSED"
    return True


def validate_recovery_writer(aggregate, record, records):
    """Called while holding the same aggregate lock as Resume authorization."""
    cycle = cycle_for(aggregate, record.scope.task_id)
    if cycle is None:
        if record.scope.operation_id.startswith("risk-resume:"):
            raise BindingDenied("RESUME_AUTHORIZATION_MISSING")
        return
    from src.application.repository import InMemoryApplicationRepository

    attempt = aggregate.node_binding.attempts.get(record.scope.task_id)
    if attempt is None or record.node_reservation_id != attempt.admission.attempt_reservation_id:
        raise BindingDenied("STALE_WRITE_REJECTED", "provider reservation")
    InMemoryApplicationRepository._validate_admission(
        aggregate, attempt.admission, require_started=True
    )
    if record.scope.operation_id != cycle.operation_id:
        raise BindingDenied("RESUME_CYCLE_MISMATCH")
    owned = [
        r
        for r in records
        if r.scope.operation_id == cycle.operation_id
        and r.scope.task_id == cycle.task_id
        and r.scope.run_id == cycle.run_id
    ]
    if any(r.kind == "TERMINAL" for r in owned):
        raise BindingDenied("RESUME_CYCLE_SETTLED")
    starts = [r for r in owned if r.kind == "ATTEMPT_STARTED"]
    if record.kind == "ATTEMPT_STARTED":
        n = len(starts) + 1
        if (
            datetime.now(UTC) >= cycle.deadline_at
            or n > cycle.budget.max_total_attempts_per_task
            or record.attempt_number != n
            or record.capability_check
            or record.route != cycle.routes[n - 1]
            or record.model != ("gpt-5.6-sol", "gpt-5.6-terra")[n - 1]
            or record.provider != "teamorouter"
            or cycle_attempt_number(aggregate, attempt) != n
        ):
            raise BindingDenied("RESUME_PROVIDER_ENTRY_DENIED")
        if n > 1 and not any(
            r.kind == "ATTEMPT_COMPLETED"
            and r.outcome == "FAIL"
            and r.attempt_id == starts[-1].attempt_id
            for r in owned
        ):
            raise BindingDenied("RESUME_RESULT_UNKNOWN")
    elif record.kind == "ATTEMPT_COMPLETED":
        matches = [s for s in starts if s.attempt_id == record.attempt_id]
        if len(matches) != 1 or any(
            r.kind == "ATTEMPT_COMPLETED" and r.attempt_id == record.attempt_id for r in owned
        ):
            raise BindingDenied("RESUME_PROVIDER_ENTRY_DENIED")
        if any(
            getattr(matches[0], key) != getattr(record, key)
            for key in (
                "scope",
                "node_reservation_id",
                "attempt_number",
                "route",
                "model",
                "provider",
                "capability_check",
            )
        ):
            raise BindingDenied("RESUME_CYCLE_MISMATCH")


async def publish_memory_events(repository, aggregate, items):
    """Isolated-test counterpart to root/event commit; caller holds the root lock."""
    from src.domain.runtime_event import RuntimeEvent, RuntimeEventType, normalize_runtime_event_v1
    from src.runtime.events import InMemoryRuntimeEventStore, validate_event_log

    store = getattr(repository, "resume_event_store", None)
    if not isinstance(store, InMemoryRuntimeEventStore):
        raise BindingDenied("RESUME_EVENT_AUTHORITY_MISSING")
    run_id = aggregate.run.run_id
    async with store._locks[run_id]:
        existing = store._events[run_id]
        events = [
            RuntimeEvent(
                event_id=item["event_id"],
                run_id=run_id,
                task_id=current_envelope(aggregate).task_id,
                type=RuntimeEventType(item["type"]),
                timestamp=datetime.fromisoformat(item["timestamp"]),
                sequence=len(existing) + index + 1,
                payload={"external_failure": item},
            )
            for index, item in enumerate(items)
        ]
        for event in events:
            normalize_runtime_event_v1(event)
        validate_event_log(run_id, [*existing, *events])
        existing.extend(events)


def require_terminal_event(aggregate, event):
    """A draining terminal publisher cannot race an authorized new cycle."""
    from src.domain.runtime_event import RuntimeEventType

    if (
        event is None
        or event.type is not RuntimeEventType.RUN_FAILED
        or event.run_id != aggregate.run.run_id
        or event.payload.get("status") != "FAILED"
        or event.timestamp != aggregate.run.completed_at
    ):
        raise BindingDenied("RESUME_RESULT_UNKNOWN", "terminal event publication is incomplete")
