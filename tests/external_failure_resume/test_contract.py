"""Local contract predicates only; no claims of scheduler/SQL acceptance."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.application.external_failure_resume import (
    legacy_snapshot,
    request_replay,
    settled_failure,
    validate_control,
    validate_expectations,
)
from src.application.service import ResearchApplicationService
from src.domain.enums import RunStatus, TaskStatus
from src.domain.external_failure_resume import (
    VERSION,
    CompletedWorkReuseDecisionV1,
    ExternalFailureResumeV1,
    FailureClosureV1,
    ResumeExternalFailure,
    ResumeReceiptV1,
    RiskResumeExecutionEnvelopeV1,
)
from src.domain.node_binding import (
    AdmissionBinding,
    AttemptReservation,
    BindingDenied,
    OwnerToken,
    canonical_value,
    digest,
    task_fingerprint,
    value_identity,
)
from src.domain.recovery import (
    FailureAssessment,
    RecoveryBudget,
    RecoveryContext,
    RecoveryDecision,
    RecoveryEvidence,
    SafeFailureEvidence,
    Scope,
)
from tests.wp02.confirmation_fixture import confirm_template
from tests.wp02.test_node_binding import aggregate


def fixture():
    service = ResearchApplicationService()
    value = asyncio.run(confirm_template(service, aggregate(("risk_analysis",))))
    root = value.node_binding
    task = value.runtime.actual_graph.tasks[0]
    root.owner_generation = 1
    root.owner_id = "old-owner"
    root.lifecycle = "RESULT_UNKNOWN"
    value.run.status = value.runtime.run_status = RunStatus.FAILED
    value.run.completed_at = datetime.now(UTC)
    task.status = TaskStatus.FAILED
    owner = OwnerToken(run_id=value.run.run_id, owner_generation=1, owner_id="old-owner")
    reservations = []
    for generation in (1, 2):
        admission = AdmissionBinding(
            admission_binding_id="",
            object_id=value.run.research_object_id,
            run_id=value.run.run_id,
            goal_id=value.goal.goal_id,
            goal_hash=digest(value.goal),
            scheme_id=value.scheme.scheme_id,
            scheme_hash=digest(value.scheme),
            graph=root.frozen_graph,
            task_id=task.task_id,
            task_fingerprint=task_fingerprint(task),
            owner=owner,
            attempt_reservation_id=str(uuid4()),
            authorized_input_requirements={},
            policy_refs={},
        )
        admission = admission.model_copy(
            update={"admission_binding_id": value_identity(admission, "admission_binding_id")}
        )
        reservations.append(
            AttemptReservation(
                admission=admission,
                status="FAILED" if generation == 1 else "DISPATCHED",
                execution_started=True,
                generation=generation,
            )
        )
    root.attempt_history[reservations[0].admission.attempt_reservation_id] = reservations[0]
    root.attempts[task.task_id] = reservations[1]
    scope = Scope(
        run_id=value.run.run_id,
        task_id=task.task_id,
        object_id=value.run.research_object_id,
        scheme_id=value.scheme.scheme_id,
        task_profile="risk_analysis",
        agent_id="risk_analyst",
        context_hash=digest("context"),
        contract_hash=digest("schema"),
    )
    records = []
    base = datetime.now(UTC) - timedelta(seconds=30)
    for number, route in enumerate(("teamorouter-sol", "teamorouter-terra"), 1):
        common = dict(
            scope=scope,
            node_reservation_id=reservations[number - 1].admission.attempt_reservation_id,
            attempt_id="ATT-" + str(uuid4()),
            attempt_number=number,
            route=route,
            provider="teamorouter",
            model="gpt-5.6-" + route.split("-")[-1],
        )
        records.append(
            RecoveryEvidence(
                record_id="REC-" + str(uuid4()),
                kind="ATTEMPT_STARTED",
                outcome="STARTED",
                timestamp=(base + timedelta(seconds=number * 3)).isoformat(),
                **common,
            )
        )
        records.append(
            RecoveryEvidence(
                record_id="REC-" + str(uuid4()),
                kind="ATTEMPT_COMPLETED",
                outcome="FAIL",
                timestamp=(base + timedelta(seconds=number * 3 + 1)).isoformat(),
                failure_class="PROVIDER_UNAVAILABLE",
                safe_failure=SafeFailureEvidence(
                    safe_code="PROVIDER_ERROR",
                    normalized_failure_class="provider_unavailable",
                    retryable=True,
                ),
                **common,
            )
        )
        context = RecoveryContext(
            scope=scope,
            failure=FailureAssessment(
                failure_class="PROVIDER_UNAVAILABLE", failure_stage="PROVIDER", recoverable=True
            ),
            current_route=route,
            candidates=(),
            attempt_history=tuple(r.route for r in records if r.kind == "ATTEMPT_COMPLETED"),
            remaining_attempts=2 - number,
            remaining_checks=0,
            remaining_decisions=3,
            remaining_seconds=120,
        )
        decision = RecoveryDecision(
            scope=scope,
            action="SWITCH_MODEL" if number == 1 else "FAIL_TASK",
            target_route="teamorouter-terra" if number == 1 else None,
            reason_code="NEXT_GOVERNED_ROUTE" if number == 1 else "NO_ALLOWED_ROUTE",
        )
        records.append(
            RecoveryEvidence(
                record_id="REC-" + str(uuid4()),
                scope=scope,
                kind="DECISION",
                outcome="ALLOW",
                node_reservation_id=common["node_reservation_id"],
                decision=decision,
                recovery_context=context,
                timestamp=(base + timedelta(seconds=number * 3 + 2)).isoformat(),
            )
        )
    records.append(
        RecoveryEvidence(
            record_id="REC-" + str(uuid4()),
            scope=scope,
            kind="TERMINAL",
            outcome="FAIL",
            node_reservation_id=reservations[-1].admission.attempt_reservation_id,
            failure_class="PROVIDER_UNAVAILABLE",
            timestamp=(base + timedelta(seconds=10)).isoformat(),
            reason_code="POLICY_DENIED",
        )
    )
    value.runtime.binding_ref = root.reference()
    return value, task, records


def request(value, task, failure):
    return ResumeExternalFailure(
        run_id=value.run.run_id,
        failed_node_id=task.task_id,
        actor="LOCAL_SINGLE_USER",
        idempotency_key="one",
        expected_binding_ref=value.node_binding.reference(),
        expected_owner_generation=value.node_binding.owner_generation,
        expected_graph_identity=value.node_binding.frozen_graph,
        expected_profile_digest=value.node_binding.execution_profile_snapshot_digest,
        expected_scenario_digest=value.node_binding.scenario_snapshot_digest,
        expected_research_object_id=value.run.research_object_id,
        expected_goal_hash=digest(value.goal),
        expected_scheme_hash=digest(value.scheme),
        expected_as_of=value.run.as_of.isoformat(),
        expected_failure_cycle_identity=failure,
        expected_resume_envelope_digest=digest({}, VERSION),
        historical_adoption=dict(
            contract_version=VERSION,
            expected_legacy_snapshot_digest=digest(legacy_snapshot(value), VERSION),
            acknowledge_preserved_terminal_history=True,
        ),
    )


def authorized():
    value, task, records = fixture()
    failure, prior, owned = settled_failure(value, task.task_id, records)
    command = request(value, task, failure)
    now = datetime.now(UTC)
    closure = FailureClosureV1(
        failure_id="failure-one",
        identity=failure,
        task_id=task.task_id,
        original_completed_at=value.run.completed_at,
        closed_at=now,
        archived_reservation=canonical_value(prior),
        receipts=tuple(canonical_value(r) for r in owned),
    )
    manifest = tuple(
        CompletedWorkReuseDecisionV1(
            kind=kind,
            producer_task_id=kind,
            result_id=digest(kind),
            result_digest=digest(kind),
            binding_ref=value.node_binding.reference(),
            graph=value.node_binding.frozen_graph,
            scenario_digest=value.node_binding.scenario_snapshot_digest,
            profile_digest=value.node_binding.execution_profile_snapshot_digest,
            research_object_id=value.run.research_object_id,
            as_of=value.run.as_of.isoformat(),
            dependency_bindings=(),
            material_manifest_digest=digest(kind),
            checks=(),
        )
        for kind in ("Evidence", "Fundamentals", "Peers", "ResearchNews", "Valuation")
    )
    envelope = RiskResumeExecutionEnvelopeV1(
        authorization_id="authorization-one",
        cycle_id="cycle-one",
        operation_id="risk-resume:cycle-one",
        prior_failure_cycle_identity=failure,
        run_id=value.run.run_id,
        task_id=task.task_id,
        object_id=value.run.research_object_id,
        goal_hash=digest(value.goal),
        scheme_hash=digest(value.scheme),
        as_of=value.run.as_of.isoformat(),
        graph=value.node_binding.frozen_graph,
        scenario_digest=value.node_binding.scenario_snapshot_digest,
        profile_digest=value.node_binding.execution_profile_snapshot_digest,
        task_fingerprint=task_fingerprint(task),
        reuse_manifest_digest=digest(manifest, VERSION),
        policy_digest=digest({}, VERSION),
        authorized_at=now,
        deadline_at=now + timedelta(seconds=180),
        budget=RecoveryBudget(
            max_total_attempts_per_task=2,
            max_cross_provider_switches=0,
            max_capability_checks=0,
            max_total_recovery_time=180,
        ),
    )
    receipt = ResumeReceiptV1(
        authorization_id=envelope.authorization_id,
        request_digest=digest(command, VERSION),
        actor=command.actor,
        idempotency_key=command.idempotency_key,
        prior_failure_id=closure.failure_id,
        new_cycle_id=envelope.cycle_id,
        envelope_digest=digest(envelope, VERSION),
        reuse_manifest=manifest,
        reuse_manifest_digest=digest(manifest, VERSION),
        authorized_at=now,
        committed_revision=1,
        event_id="event-one",
        original_failure_timestamp=value.run.completed_at,
    )
    state = ExternalFailureResumeV1(
        failures=(closure,),
        envelopes=(envelope,),
        receipts=(receipt,),
        current_failure_id=closure.failure_id,
        current_cycle_id=envelope.cycle_id,
    )
    return value, task, command, state


def test_settlement_is_read_only_and_keeps_dispatched_snapshot():
    value, task, records = fixture()
    before = legacy_snapshot(value)
    identity, prior, owned = settled_failure(value, task.task_id, records)
    assert prior.status == "DISPATCHED"
    assert identity.failed_reservation_generation == 2
    assert identity.ordered_receipts_digest == digest(owned, VERSION)
    assert legacy_snapshot(value) == before
    assert (
        value.node_binding.attempt_history[next(iter(value.node_binding.attempt_history))].status
        == "FAILED"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_end",
        "duplicate_start",
        "wrong_reservation",
        "same_timestamp",
        "mixed_failure",
        "wrong_stage",
        "no_terminal_decision",
        "no_terminal",
        "wrong_route",
        "downstream",
    ],
)
def test_uncertain_or_ineligible_failure_denied(mutation):
    value, task, records = fixture()
    if mutation == "missing_end":
        del records[1]
    elif mutation == "duplicate_start":
        records.insert(1, records[0].model_copy(update={"record_id": "REC-" + str(uuid4())}))
    elif mutation == "wrong_reservation":
        records[1] = records[1].model_copy(update={"node_reservation_id": "foreign"})
    elif mutation == "same_timestamp":
        records[1] = records[1].model_copy(update={"timestamp": records[0].timestamp})
    elif mutation == "mixed_failure":
        records[1] = records[1].model_copy(update={"failure_class": "READ_TIMEOUT"})
    elif mutation == "wrong_stage":
        ctx = records[2].recovery_context
        records[2] = records[2].model_copy(
            update={
                "recovery_context": ctx.model_copy(
                    update={"failure": ctx.failure.model_copy(update={"failure_stage": "RUNTIME"})}
                )
            }
        )
    elif mutation == "no_terminal_decision":
        del records[-2]
    elif mutation == "no_terminal":
        records.pop()
    elif mutation == "wrong_route":
        for i in (3, 4):
            records[i] = records[i].model_copy(update={"route": "teamorouter-luna"})
    else:
        value.node_binding.current_results[task.task_id] = "fabricated"
        value.runtime.binding_ref = value.node_binding.reference()
    before = legacy_snapshot(value)
    with pytest.raises(BindingDenied):
        settled_failure(value, task.task_id, records)
    assert legacy_snapshot(value) == before


def test_duplicate_command_replays_original_receipt_and_conflicts_do_not_retarget():
    _, _, command, state = authorized()
    assert request_replay(state, command, actor=command.actor) == state.receipts[0]
    with pytest.raises(BindingDenied, match="RESUME_IDEMPOTENCY_CONFLICT"):
        request_replay(
            state,
            command.model_copy(update={"expected_owner_generation": 999}),
            actor=command.actor,
        )
    with pytest.raises(BindingDenied, match="RESUME_FAILURE_ALREADY_CONSUMED"):
        request_replay(
            state, command.model_copy(update={"idempotency_key": "two"}), actor=command.actor
        )
    with pytest.raises(BindingDenied, match="RESUME_ACTOR_MISMATCH"):
        request_replay(state, command, actor="worker")


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_total_attempts_per_task", 3),
        ("max_same_route_attempts", 2),
        ("max_cross_provider_switches", 1),
        ("max_capability_checks", 1),
        ("max_model_fallbacks", 2),
    ],
)
def test_envelope_forbids_extra_allowance(field, value):
    _, _, _, state = authorized()
    raw = state.envelopes[0].model_dump()
    raw["budget"][field] = value
    with pytest.raises(ValidationError):
        RiskResumeExecutionEnvelopeV1.model_validate(raw)


def test_envelope_operation_and_absolute_deadline_are_bound():
    _, _, _, state = authorized()
    raw = state.envelopes[0].model_dump()
    raw["operation_id"] = "new-random-scope"
    with pytest.raises(ValidationError):
        RiskResumeExecutionEnvelopeV1.model_validate(raw)
    raw = state.envelopes[0].model_dump()
    raw["deadline_at"] += timedelta(seconds=1)
    with pytest.raises(ValidationError):
        RiskResumeExecutionEnvelopeV1.model_validate(raw)


def test_state_roundtrip_and_authorization_integrity():
    _, _, _, state = authorized()
    assert ExternalFailureResumeV1.model_validate_json(state.model_dump_json()) == state
    raw = state.model_dump()
    raw["receipts"] = []
    with pytest.raises(ValidationError):
        ExternalFailureResumeV1.model_validate(raw)
    raw = state.model_dump()
    raw["envelopes"][0]["reuse_manifest_digest"] = digest("changed")
    with pytest.raises(ValidationError):
        ExternalFailureResumeV1.model_validate(raw)


def test_exact_expectations_and_explicit_historical_adoption():
    value, task, records = fixture()
    failure, _, _ = settled_failure(value, task.task_id, records)
    command = request(value, task, failure)
    validate_expectations(value, command, failure, {}, actor=command.actor)
    with pytest.raises(BindingDenied, match="HISTORICAL_OPT_IN_REQUIRED"):
        validate_expectations(
            value,
            command.model_copy(update={"historical_adoption": None}),
            failure,
            {},
            actor=command.actor,
        )
    with pytest.raises(BindingDenied, match="RESUME_STALE"):
        validate_expectations(
            value,
            command.model_copy(update={"expected_owner_generation": 20}),
            failure,
            {},
            actor=command.actor,
        )
    with pytest.raises(BindingDenied, match="RESUME_IDENTITY_MISMATCH"):
        validate_expectations(
            value,
            command.model_copy(update={"expected_as_of": "2020-01-01"}),
            failure,
            {},
            actor=command.actor,
        )


def test_no_silent_retrofit_or_unbacked_lifecycle():
    value, _, _ = fixture()
    before = legacy_snapshot(value)
    validate_control(value)
    assert legacy_snapshot(value) == before
    assert "external_failure_resume" not in value.node_binding.model_dump()
    value.node_binding.lifecycle = "EXTERNAL_RESUME_PENDING"
    with pytest.raises(BindingDenied, match="RESUME_AUTHORIZATION_MISSING"):
        validate_control(value)


def test_unknown_command_fields_rejected():
    _, _, command, _ = authorized()
    raw = command.model_dump()
    raw["max_provider_calls"] = 100
    with pytest.raises(ValidationError):
        ResumeExternalFailure.model_validate(raw)
