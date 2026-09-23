"""Single-Run Risk follow-up control, called only inside the Run owner's transaction."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from src.domain.enums import ReplanDecision, RunStatus, TaskStatus
from src.domain.execution_profile import ExecutionSnapshot, NodeExecutionProfile
from src.domain.node_binding import BindingDenied, GraphIdentity, digest, task_fingerprint
from src.domain.risk_replan import (
    POLICY,
    CandidateBinding,
    ReplanControl,
    ReplanDecisionRecord,
    ReplanProposalV1,
    RiskFollowUpDiff,
)
from src.domain.task import ReplanRequest


class ReplanSuspended(Exception):
    """Durable nonterminal human-decision or child barrier; never a task failure."""


class _MutationDisposition(Enum):
    MUTATED = "MUTATED"
    NO_OP_REPLAY = "NO_OP_REPLAY"
    REJECTED = "REJECTED"


class _ReplanReadOnly(Exception):
    def __init__(self, result):
        self.result = result


@dataclass
class _MutationResult:
    disposition: _MutationDisposition = _MutationDisposition.REJECTED

    def consume(self, result):
        if self.disposition is _MutationDisposition.NO_OP_REPLAY:
            raise _ReplanReadOnly(result)
        if self.disposition is not _MutationDisposition.MUTATED:
            raise RuntimeError("REPLAN_MUTATION_DISPOSITION_REQUIRED")


def _classify(carrier, disposition):
    if carrier is not None:
        carrier.disposition = disposition


def control(aggregate):
    raw = aggregate.node_binding.replan
    return ReplanControl.model_validate(raw) if raw is not None else None


def proposal(aggregate):
    state = control(aggregate)
    if state is None:
        raise BindingDenied("REPLAN_NOT_FOUND")
    found = [r for r in aggregate.artifacts.replans if r.replan_id == state.active_proposal_id]
    if len(found) != 1:
        raise BindingDenied("REPLAN_IDENTITY_MISMATCH", "active proposal")
    request = found[0]
    value = ReplanProposalV1.model_validate(request.risk_follow_up)
    if (
        request.run_id != aggregate.run.run_id
        or value.proposal_digest != value.semantic_digest(request)
        or value.source_candidate_id != state.candidate.candidate_id
    ):
        raise BindingDenied("REPLAN_IDENTITY_MISMATCH", "proposal digest")
    return request, value


def store(aggregate, state, request=None, value=None):
    aggregate.node_binding.replan = state.model_dump(mode="json")
    aggregate.runtime.binding_ref = aggregate.node_binding.reference()
    if request is not None:
        request.risk_follow_up = value.model_dump(mode="json")


def audit(aggregate, state, kind, *, actor=None, decision_id=None, code=None,
          proposal_digest=None, command_binding=None):
    if proposal_digest is None:
        proposal_digest = proposal(aggregate)[1].proposal_digest
    value = {
        "schema_version": "risk-follow-up-audit/v1",
        "event_id": "EVT-" + uuid4().hex,
        "type": kind,
        "run_id": aggregate.run.run_id,
        "object_id": aggregate.run.research_object_id,
        "proposal_id": state.active_proposal_id,
        "proposal_digest": proposal_digest,
        "base_graph": state.candidate.graph.model_dump(mode="json"),
        "graph": aggregate.node_binding.frozen_graph.model_dump(mode="json"),
        "control_revision": state.control_revision,
        "actor": actor,
        "decision_id": decision_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "failure_code": code,
    }
    if command_binding is not None:
        value.update(command_binding)
    if kind == "replan.applied":
        transition = state.transition
        if transition is None:
            raise BindingDenied("REPLAN_IDENTITY_MISMATCH", "applied audit transition")
        value.update(
            transition_id=transition.transition_id,
            authorized_diff_digest=digest(transition.authorized_diff),
            old_execution_snapshot_digest=transition.old_execution_snapshot_digest,
            new_execution_snapshot_digest=transition.new_execution_snapshot_digest,
        )
    return state.model_copy(update={"audit": (*state.audit, value)})


def frozen_policy(aggregate):
    snapshot = ExecutionSnapshot.model_validate(aggregate.node_binding.execution_snapshot)
    policy = snapshot.scenario.risk_follow_up_policy
    if (
        snapshot.scenario.scenario_version != "2"
        or snapshot.scenario.graph_mutation != POLICY
        or policy is None
        or policy.get("policy_version") != POLICY
        or policy.get("max_approved_expansions_per_run") != 1
        or policy.get("max_per_source_node") != 1
        or policy.get("max_child_expansions") != 0
    ):
        raise BindingDenied("UNSUPPORTED_NEW_BOUND_HANDLER", "Risk Replan capability absent")
    return policy


def validate_candidate(aggregate, candidate, *, validate_semantic_admission=True):
    from src.domain.node_binding import canonical_value, check_value_identity

    root = aggregate.node_binding
    source = aggregate.runtime.task(candidate.task_id)
    reservation = root.attempts.get(source.task_id)
    if (
        candidate.run_id != root.run_id
        or source.task_type != "risk_analysis"
        or task_fingerprint(source) != candidate.task_fingerprint
        or reservation is None
        or reservation.status != "CANDIDATE_RETAINED"
        or reservation.admission.admission_binding_id != candidate.admission_binding_id
        or reservation.admission.attempt_reservation_id != candidate.reservation_id
        or reservation.admission.graph != candidate.graph
        or digest(candidate.output_record.payload_snapshot, candidate.output_record.record_schema)
        != candidate.output_record.content_digest
        or candidate.candidate_id != candidate.candidate_digest
        or digest(
            candidate.model_dump(exclude={"candidate_id", "candidate_digest"}),
            candidate.schema_version,
        )
        != candidate.candidate_digest
    ):
        raise BindingDenied("REPLAN_CANDIDATE_MISMATCH")
    for identity in candidate.resolved_input_binding_ids:
        bound = root.resolved_inputs.get(identity)
        if bound is None or bound.admission_binding_id != candidate.admission_binding_id:
            raise BindingDenied("REPLAN_CANDIDATE_MISMATCH", "resolved inputs")
        check_value_identity(bound, "resolved_input_binding_id")
    outputs = [
        o
        for o in aggregate.artifacts.agent_outputs
        if o.output_id == candidate.output_record.record_id
    ]
    if len(outputs) != 1 or canonical_value(outputs[0]) != (
        candidate.output_record.payload_snapshot
    ):
        raise BindingDenied("REPLAN_CANDIDATE_MISMATCH", "retained output")
    from src.application.risk_admission import derive
    from src.domain.risk_admission import contract_for

    if validate_semantic_admission and contract_for(aggregate) is not None:
        receipt = (root.risk_admissions or {}).get(candidate.admission_binding_id)
        fulfillment = (root.replan or {}).get("finalization")
        expected = derive(aggregate, reservation.admission, [candidate.output_record],
                          candidate.resolved_input_binding_ids, fulfillment=fulfillment)
        if (receipt != expected or receipt["decision"] not in {
                "FOLLOW_UP_PENDING", "FINAL_SUCCESS"}):
            raise BindingDenied("RISK_FINAL_ADMISSION_REQUIRED")
    return outputs[0]


def exact_diff(aggregate, task):
    from src.domain.output_dependency import OutputRequirements

    consumers = [t for t in aggregate.runtime.actual_graph.tasks if task.task_id in t.dependencies]
    if len(consumers) != 1 or consumers[0].task_type != "report_synthesis":
        raise BindingDenied("REPLAN_UNSUPPORTED_PLACEMENT")
    child_id = f"{task.run_id}:risk-follow-up"
    if any(
        t.task_id == child_id or t.task_type == "risk_follow_up"
        for t in aggregate.runtime.actual_graph.tasks
    ):
        raise BindingDenied("REPLAN_BOUND_EXHAUSTED")
    requirements = task.output_requirements
    if requirements is None:
        raise BindingDenied("REPLAN_MISSING_HARD_INPUT")
    anchors = requirements.hard_required
    revenue = [a for a in anchors if a.endswith("/revenue_growth")]
    margin = [a for a in anchors if a.endswith("/ebitda_margin")]
    if (
        len(revenue) != 1
        or len(margin) != 1
        or revenue[0].rsplit("/", 1)[0] != margin[0].rsplit("/", 1)[0]
    ):
        raise BindingDenied("REPLAN_MISSING_HARD_INPUT")
    producer = aggregate.runtime.task(revenue[0].rsplit("/", 1)[0])
    if (
        producer.task_type != "fundamental_analysis"
        or producer.task_id not in aggregate.node_binding.current_results
    ):
        raise BindingDenied("REPLAN_MISSING_HARD_INPUT")
    return RiskFollowUpDiff(
        child_task_id=child_id,
        source_task_id=task.task_id,
        synthesis_task_id=consumers[0].task_id,
        output_requirements=OutputRequirements(
            hard_required=[revenue[0], margin[0]],
            supporting=list(requirements.supporting),
        ).model_dump(mode="json"),
    )


def validate_context_scope(aggregate, admission, payload):
    """Admit Replan context under the current Run lock, including Recovery snapshots."""
    from datetime import date

    task = aggregate.runtime.task(admission.task_id)
    if not (
        (task.task_type == "risk_analysis"
         and "risk_replan_policy_digest" in admission.authorized_input_requirements)
        or (task.task_type == "risk_follow_up" and aggregate.node_binding.replan is not None)
    ):
        return
    # Confirm copies the goal date into Run.as_of. The admission already binds the
    # confirmed goal hash; neither a later request nor a saved context owns scope.
    cutoff = aggregate.run.as_of
    context = payload.get("context", {})
    inputs = context.get("inputs", {})
    if (
        type(cutoff) is not date
        or cutoff != aggregate.goal.as_of
        or inputs.get("as_of") != cutoff.isoformat()
        or inputs.get("research_object_id") != aggregate.run.research_object_id
        or context.get("task", {}).get("run_id") != aggregate.run.run_id
    ):
        raise BindingDenied("IDENTITY_MISMATCH", "Replan confirmed temporal scope")
    follow_up = inputs.get("risk_follow_up")
    if follow_up is not None and follow_up.get("current_as_of") != cutoff.isoformat():
        raise BindingDenied("IDENTITY_MISMATCH", "Replan child temporal scope")
    normalized = inputs.get("normalized_evidence", [])
    refs = set(task.task_input_evidence_ids) | set(context.get("accepted_evidence_ids", []))
    refs.update(item.get("evidence_id") for item in normalized)
    input_refs = set(inputs.get("input_refs", []))
    # A completed producer/output label is not semantic calculation success.
    # Resolve both mandatory anchors from its accepted result before accepting any
    # context, including a saved Recovery context or the focused child payload.
    from src.domain.enums import CalculationStatus
    from src.domain.node_binding import calculation_core

    required = task.output_requirements
    anchors = []
    for capability in ("revenue_growth", "ebitda_margin"):
        matches = [key for key in (required.hard_required if required else [])
                   if key.endswith("/" + capability)]
        if len(matches) != 1:
            raise BindingDenied("REPLAN_MISSING_HARD_INPUT", capability)
        anchors.append((matches[0].rsplit("/", 1)[0], capability))
    if anchors[0][0] != anchors[1][0]:
        raise BindingDenied("REPLAN_MISSING_HARD_INPUT", "common fundamental producer")
    producer = aggregate.runtime.task(anchors[0][0])
    root = aggregate.node_binding
    result = root.results.get(root.current_results.get(producer.task_id))
    if producer.task_type != "fundamental_analysis" or result is None:
        raise BindingDenied("REPLAN_MISSING_HARD_INPUT", "accepted fundamental result")
    for _, capability in anchors:
        records = [record for record in result.output_records
                   if record.kind == "CALCULATION_CORE"
                   and record.payload_snapshot.get("capability_id") == capability]
        if len(records) != 1:
            raise BindingDenied("REPLAN_MISSING_HARD_INPUT", capability)
        record = records[0]
        calculations = [item for item in aggregate.artifacts.calculations
                        if item.calculation_id == record.record_id]
        if len(calculations) != 1:
            raise BindingDenied("REPLAN_MISSING_HARD_INPUT", capability)
        calculation = calculations[0]
        if (calculation.status is not CalculationStatus.PASS
                or calculation.run_id != aggregate.run.run_id
                or calculation.task_id != producer.task_id
                or calculation_core(calculation) != record.payload_snapshot
                or calculation.calculation_id not in input_refs
                or not calculation.input_evidence_ids):
            raise BindingDenied("REPLAN_MISSING_HARD_INPUT", "valid PASS " + capability)
        refs.update(calculation.input_evidence_ids)
    evidence = {item.evidence_id: item for item in aggregate.artifacts.evidence}
    refs.update(input_refs & evidence.keys())
    for calculation in aggregate.artifacts.calculations:
        if calculation.calculation_id in input_refs:
            refs.update(calculation.input_evidence_ids)
    for ref in refs:
        record = evidence.get(ref)
        if record is None or type(record.as_of) is not date:
            raise BindingDenied("MISSING_INPUT", "Replan evidence temporal scope")
        if (
            record.run_id != aggregate.run.run_id
            or record.object_id != aggregate.run.research_object_id
            or record.status.value != "ACCEPTED"
        ):
            raise BindingDenied("IDENTITY_MISMATCH", "Replan evidence scope")
        if record.as_of > cutoff:
            raise BindingDenied("STALE_INPUT", "Replan evidence exceeds frozen Run.as_of")
    for item in normalized:
        record = evidence.get(item.get("evidence_id"))
        if record is None or item.get("as_of") != record.as_of.isoformat():
            raise BindingDenied("IDENTITY_MISMATCH", "Replan evidence temporal identity")


def capture(aggregate, admission, task, artifacts, records, resolved_ids, observed):
    """After the same Stage B/material checks as a normal result; no accepted result."""
    from src.application.execution_profiles import frozen_profile
    from src.application.risk_replan_profile import validate_child_profile
    from src.domain.agent_output import RiskResearchAgentStructuredOutput
    from src.phase4_product.hashing import canonical_json_sha256

    policy = frozen_policy(aggregate)
    root = aggregate.node_binding
    if root.replan is not None:
        raise BindingDenied("REPLAN_BOUND_EXHAUSTED")
    selected = [o for o in artifacts.agent_outputs if o.task_id == task.task_id]
    if len(selected) != 1:
        raise BindingDenied("REPLAN_CANDIDATE_MISMATCH")
    output = selected[0]
    from src.domain.agent_output import RiskResearchAgentStructuredOutputMinimalV1
    from src.domain.risk_admission import contract_for

    schema = (RiskResearchAgentStructuredOutputMinimalV1 if contract_for(aggregate)
              else RiskResearchAgentStructuredOutput)
    parsed = schema.model_validate(output.structured_output.model_dump())
    if not parsed.requires_follow_up:
        raise BindingDenied("REPLAN_CANDIDATE_MISMATCH")
    selected_records = [
        r for r in records if r.kind == "AGENT_OUTPUT" and r.record_id == output.output_id
    ]
    if len(selected_records) != 1:
        raise BindingDenied("REPLAN_CANDIDATE_MISMATCH")
    attempt_ids = observed.get("attempt_ids", [])
    if len(attempt_ids) != 1:
        raise BindingDenied("REPLAN_CANDIDATE_ATTEMPT_REQUIRED")
    diff = exact_diff(aggregate, task)
    child = validate_child_profile(NodeExecutionProfile.model_validate(policy["child_template"]))
    profile = frozen_profile(aggregate, task)
    candidate = CandidateBinding(
        candidate_id="",
        candidate_digest="",
        run_id=task.run_id,
        task_id=task.task_id,
        graph=admission.graph,
        task_fingerprint=admission.task_fingerprint,
        admission_binding_id=admission.admission_binding_id,
        reservation_id=admission.attempt_reservation_id,
        attempt_id=attempt_ids[0],
        resolved_input_binding_ids=tuple(resolved_ids),
        output_record=selected_records[0],
        source_output_digest=digest(parsed, "risk-candidate-output/v1"),
        source_artifact_sha256=output.artifact_sha256,
        schema_identity=schema.__name__,
        schema_digest=canonical_json_sha256(schema.model_json_schema()),
        profile_digest=digest(profile, "node-execution-profile/v1"),
        created_at=datetime.now(UTC),
    )
    identity = digest(
        candidate.model_dump(exclude={"candidate_id", "candidate_digest"}), candidate.schema_version
    )
    candidate = candidate.model_copy(
        update={"candidate_id": identity, "candidate_digest": identity}
    )
    request = ReplanRequest(
        replan_id="REPLAN-" + uuid4().hex,
        run_id=task.run_id,
        requesting_task_id=task.task_id,
        requested_by=task.assigned_agent,
        reason_code="MATERIAL_RISK_FOLLOW_UP",
        reason_detail=parsed.summary,
        proposed_graph_change=diff.model_dump(mode="json"),
    )
    value = ReplanProposalV1(
        source_candidate_id=identity,
        source_output_id=output.output_id,
        source_admission_binding_id=admission.admission_binding_id,
        source_reservation_id=admission.attempt_reservation_id,
        source_attempt_id=attempt_ids[0],
        source_output_digest=candidate.source_output_digest,
        source_artifact_sha256=output.artifact_sha256,
        base_graph=root.frozen_graph,
        base_execution_snapshot_digest=root.execution_profile_snapshot_digest,
        scenario_snapshot_digest=root.scenario_snapshot_digest,
        diff=diff,
        reason_summary=parsed.summary,
        relevant_evidence_refs=tuple(task.task_input_evidence_ids),
        required_child_profile=child.model_dump(mode="json"),
        child_profile_digest=digest(child, "node-execution-profile/v1"),
        output_contract_digest=digest(diff.output_requirements, "output-contract/v1"),
        proposal_digest="",
    )
    value = value.model_copy(update={"proposal_digest": value.semantic_digest(request)})
    state = ReplanControl(active_proposal_id=request.replan_id, candidate=candidate)
    state = audit(aggregate, state, "replan.requested", proposal_digest=value.proposal_digest)
    state = audit(
        aggregate, state, "replan.waiting_for_decision", proposal_digest=value.proposal_digest
    )
    aggregate.artifacts.agent_outputs.append(output.model_copy(deep=True))
    aggregate.artifacts.replans.append(request)
    root.attempts[task.task_id] = root.attempts[task.task_id].model_copy(
        update={
            "status": "CANDIDATE_RETAINED",
            "completed_at": datetime.now(UTC),
        }
    )
    retained_task = task.model_copy(deep=True)
    retained_task.status = TaskStatus.WAITING_REPLAN
    retained_task.output_outcomes = []
    retained_task.result_ref = None
    retained_task.progress = 0.0
    aggregate.runtime.actual_graph.tasks = [
        retained_task if item.task_id == task.task_id else item
        for item in aggregate.runtime.actual_graph.tasks
    ]
    aggregate.run.status = aggregate.runtime.run_status = RunStatus.WAITING_REPLAN
    aggregate.run.completed_at = None
    store(aggregate, state, request, value)
    return candidate


def decide(aggregate, command, *, actor, key, _mutation=None):
    """Server-scoped structured decision; caller holds the same Run row lock."""
    state = control(aggregate)
    request, value = proposal(aggregate)
    if (
        actor != "LOCAL_SINGLE_USER"
        or command.get("run_id") != aggregate.run.run_id
        or command.get("proposal_id") != request.replan_id
        or command.get("object_id") != aggregate.run.research_object_id
    ):
        raise BindingDenied("REPLAN_ACCESS_DENIED")
    action = command.get("action")
    confirmation = {
        "APPROVE": "authorize_replan",
        "DECLINE": "reject_replan",
        "REOPEN": "reopen_declined_replan",
        "CANCEL": "abandon",
    }.get(action)
    expected_keys = {"run_id", "object_id", "proposal_id", "action", confirmation}
    expected_keys |= (
        {"expected_control_revision"}
        if action == "CANCEL"
        else {"expected_proposal_digest", "expected_graph", "expected_decision_revision"}
    )
    if (
        confirmation is None
        or command.get(confirmation) is not True
        or set(command) != expected_keys
        or not isinstance(key, str)
        or not key.strip()
    ):
        raise BindingDenied("REPLAN_EXPLICIT_ACTION_REQUIRED")
    receipt_key = digest([actor, aggregate.run.run_id, action, key], "replan-command-key/v1")
    request_hash = digest(command, "replan-command/v1")
    if receipt_key in state.receipts:
        receipt = state.receipts[receipt_key]
        if receipt["request_hash"] != request_hash:
            raise BindingDenied("REPLAN_IDEMPOTENCY_CONFLICT")
        _classify(_mutation, _MutationDisposition.NO_OP_REPLAY)
        return {**receipt, "historical_replay": True}
    # Equivalent commands retain their original cycle authority across later decisions.
    matching = [r for r in state.receipts.values() if r["request_hash"] == request_hash]
    if matching:
        receipt = matching[0]
        store(
            aggregate,
            state.model_copy(
                update={
                    "receipts": {**state.receipts, receipt_key: receipt},
                }
            ),
        )
        _classify(_mutation, _MutationDisposition.MUTATED)
        return {**receipt, "historical_replay": True}
    failure = None
    if aggregate.run.status in {RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.RELEASED}:
        if action != "REOPEN":
            raise BindingDenied("REPLAN_TERMINAL_RUN")
        # Return through the normal rejected-command transaction. Raising here
        # would bypass (or roll back) the durable denial required for Reopen.
        failure = "REPLAN_TERMINAL_RUN"
    elif action == "CANCEL":
        if command["expected_control_revision"] != state.control_revision:
            failure = "REPLAN_STALE_CONTROL"
    else:
        if (
            command["expected_proposal_digest"] != value.proposal_digest
            or command["expected_graph"]
            != aggregate.node_binding.frozen_graph.model_dump(mode="json")
            or command["expected_graph"] != value.base_graph.model_dump(mode="json")
            or command["expected_decision_revision"] != value.decision_revision
        ):
            failure = "REPLAN_STALE_DECISION"
        elif action == "REOPEN":
            if (
                request.decision != ReplanDecision.REJECTED
                or value.disposition != "DECLINED"
                or not state.reopenable
                or value.decline_base_graph != value.base_graph
            ):
                failure = "REPLAN_NOT_REOPENABLE"
        elif request.decision != ReplanDecision.PENDING:
            failure = "REPLAN_DECISION_CONFLICT"
    if failure is not None:
        receipt = {
            "request_hash": request_hash,
            "outcome": "REJECTED",
            "code": failure,
            "proposal_id": request.replan_id,
            "run_id": aggregate.run.run_id,
            "object_id": aggregate.run.research_object_id,
            "actor": actor,
            "action": action,
            "command_key_digest": receipt_key,
            "decision_revision": value.decision_revision,
            "control_revision": state.control_revision,
            "expectations": {
                name: item for name, item in command.items() if name.startswith("expected_")
            },
            "historical_replay": False,
        }
        state = audit(
            aggregate,
            state,
            "replan.reopen_stale_rejected" if action == "REOPEN" else "replan.stale_rejected",
            actor=actor,
            code=failure,
            decision_id=value.latest_decision_id,
            command_binding={
                "command_key_digest": receipt_key,
                "request_hash": request_hash,
                "decision_revision": value.decision_revision,
                "terminal_status": (
                    aggregate.run.status.value if failure == "REPLAN_TERMINAL_RUN" else None
                ),
            },
        )
        receipt["audit_event_id"] = state.audit[-1]["event_id"]
        state = state.model_copy(update={"receipts": {**state.receipts, receipt_key: receipt}})
        store(aggregate, state)
        _classify(_mutation, _MutationDisposition.MUTATED)
        return receipt
    validate_candidate(aggregate, state.candidate)
    frozen_policy(aggregate)
    if action == "APPROVE":
        from src.application.risk_replan_profile import validate_child_profile

        validate_child_profile(NodeExecutionProfile.model_validate(value.required_child_profile))
        if state.expansion_count or state.transition is not None:
            raise BindingDenied("REPLAN_BOUND_EXHAUSTED")
    now = datetime.now(UTC)
    decision = ReplanDecisionRecord(
        decision_id="DEC-" + uuid4().hex,
        action=action,
        actor=actor,
        prior_revision=value.decision_revision,
        new_revision=value.decision_revision + 1,
        prior_decision_id=value.latest_decision_id,
        proposal_digest=value.proposal_digest,
        graph=aggregate.node_binding.frozen_graph,
        decided_at=now,
    )
    value = value.model_copy(
        update={
            "decision_revision": decision.new_revision,
            "latest_decision_id": decision.decision_id,
            "history": (*value.history, decision),
        }
    )
    state = state.model_copy(update={"control_revision": state.control_revision + 1})
    request.decided_by = actor
    if action == "APPROVE":
        request.decision = ReplanDecision.APPROVED
        value = value.model_copy(update={"application_state": "AWAITING_QUIESCENCE"})
        state = state.model_copy(update={"wait_reason": "DECISION_APPLY", "reopenable": False})
        event = "replan.approved"
    elif action == "DECLINE":
        request.decision = ReplanDecision.REJECTED
        value = value.model_copy(
            update={
                "disposition": "DECLINED",
                "decline_base_graph": value.base_graph,
            }
        )
        state = state.model_copy(
            update={
                "wait_reason": "DECLINED_INCOMPLETE",
                "reopenable": True,
                "resume_eligible": False,
            }
        )
        event = "replan.rejected"
    elif action == "REOPEN":
        request.decision = ReplanDecision.PENDING
        value = value.model_copy(update={"disposition": None, "reopened": True})
        state = state.model_copy(
            update={
                "wait_reason": "DECISION",
                "reopenable": False,
                "resume_eligible": False,
            }
        )
        event = "replan.reopened"
    else:
        state = state.model_copy(
            update={
                "wait_reason": "CANCELLED",
                "reopenable": False,
                "resume_eligible": False,
            }
        )
        aggregate.run.status = aggregate.runtime.run_status = RunStatus.CANCELLED
        aggregate.run.completed_at = now
        aggregate.node_binding.lifecycle = "CLOSED"
        aggregate.node_binding.owner_generation += 1
        for task in aggregate.runtime.actual_graph.tasks:
            if task.status != TaskStatus.COMPLETED:
                task.status = TaskStatus.CANCELLED
        event = "research.cancelled"
    if action != "CANCEL":
        aggregate.run.status = aggregate.runtime.run_status = RunStatus.WAITING_REPLAN
        aggregate.run.completed_at = None
    aggregate.run.updated_at = now
    receipt = {
        "request_hash": request_hash,
        "outcome": "COMMITTED",
        "proposal_id": request.replan_id,
        "decision_id": decision.decision_id,
        "decision_revision": decision.new_revision,
        "control_revision": state.control_revision,
        "action": action,
        "historical_replay": False,
    }
    state = state.model_copy(update={"receipts": {**state.receipts, receipt_key: receipt}})
    state = audit(aggregate, state, event, actor=actor, decision_id=decision.decision_id)
    if action == "DECLINE":
        state = audit(
            aggregate,
            state,
            "replan.paused_incomplete",
            actor=actor,
            decision_id=decision.decision_id,
        )
    store(aggregate, state, request, value)
    _classify(_mutation, _MutationDisposition.MUTATED)
    return receipt


def projection(aggregate):
    state = control(aggregate)
    root = aggregate.node_binding
    result = {
        "schema_version": "risk-follow-up-projection/v1",
        "run_id": aggregate.run.run_id,
        "object_id": aggregate.run.research_object_id,
        "status": aggregate.run.status.value,
        "graph": root.frozen_graph.model_dump(mode="json"),
        "binding_revision": root.binding_revision,
        "scenario_snapshot_digest": root.scenario_snapshot_digest,
        "execution_snapshot_digest": root.execution_profile_snapshot_digest,
        "completed_results": dict(root.current_results),
        "active_proposal": None,
        "legal_actions": [],
        "action_expectations": {},
        "report_eligible": False,
        "release_eligible": False,
    }
    if state is None:
        return result
    request, value = proposal(aggregate)
    if state.finalization is not None and aggregate.run.status == RunStatus.RELEASED:
        result["report_eligible"] = aggregate.artifacts.report is not None
        result["release_eligible"] = aggregate.artifacts.released_result is not None
    if aggregate.run.status not in {RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.RELEASED}:
        result["legal_actions"] = ["CANCEL"]
        if state.reopenable:
            result["legal_actions"] += ["REOPEN"]
        elif request.decision == ReplanDecision.PENDING:
            result["legal_actions"] += ["APPROVE", "DECLINE"]
    result.update(
        {
            "logical_state": "DECLINED_INCOMPLETE_PAUSED"
            if state.reopenable
            else state.wait_reason,
            "control_revision": state.control_revision,
            "decision_revision": value.decision_revision,
            "resume_eligible": state.resume_eligible,
            "active_proposal": {
                "proposal_id": request.replan_id,
                "digest": value.proposal_digest,
                "base_graph": value.base_graph.model_dump(mode="json"),
                "status": "DECLINED" if state.reopenable else request.decision.value,
                "why": value.reason_summary,
                "diff": value.diff.model_dump(mode="json"),
                "application_state": value.application_state,
                "candidate_authority": "FINALIZED" if state.finalization else "NON_AUTHORITATIVE",
                "history": [d.model_dump(mode="json") for d in value.history],
                "child_profile_digest": value.child_profile_digest,
            },
            "attempts": {
                key: {"status": a.status, "generation": a.generation}
                for key, a in root.attempts.items()
            },
            "eligibility_reason": "EXISTING_REVIEW_REQUIRED"
            if state.finalization
            else "RISK_FOLLOW_UP_INCOMPLETE",
            "estimated_time": "UNKNOWN",
            "estimated_cost": "UNKNOWN",
        }
    )
    for action in result["legal_actions"]:
        expected = {"run_id": aggregate.run.run_id}
        if action == "CANCEL":
            expected.update(expected_control_revision=state.control_revision, abandon=True)
        else:
            expected.update(
                proposal_id=request.replan_id,
                expected_proposal_digest=value.proposal_digest,
                expected_base_graph=value.base_graph.model_dump(mode="json"),
                expected_decision_revision=value.decision_revision,
            )
            expected[
                {
                    "APPROVE": "authorize_replan",
                    "DECLINE": "reject_replan",
                    "REOPEN": "reopen_declined_replan",
                }[action]
            ] = True
        result["action_expectations"][action] = expected
    result["disabled_reason"] = {
        action: "NOT_LEGAL_IN_CURRENT_DURABLE_STATE"
        for action in {"APPROVE", "DECLINE", "REOPEN", "CANCEL"} - set(result["legal_actions"])
    }
    result["child"] = (
        None
        if state.transition is None
        else {
            "task_id": value.diff.child_task_id,
            "status": aggregate.runtime.task(value.diff.child_task_id).status.value,
            "profile_id": "risk_follow_up_v1",
            "profile_version": "1",
        }
    )
    return result


async def apply(repository, aggregate, *, _mutation=None):
    """Apply only one approved exact diff after old-graph admissions have settled."""
    from src.application.execution_profiles import frozen_profile
    from src.application.risk_replan_profile import validate_child_profile
    from src.domain.execution_profile import NodeProfileBinding
    from src.domain.node_binding import canonical_value, graph_semantics
    from src.domain.risk_replan import (
        RecoveryCarryCertificate,
        ReplanTransition,
        ResultReuseCertificate,
    )
    from src.domain.task import Task

    state = control(aggregate)
    request, value = proposal(aggregate)
    root = aggregate.node_binding
    if state.transition is not None:
        if value.application_state != "APPLIED" or state.transition.new_graph != root.frozen_graph:
            raise BindingDenied("REPLAN_TRANSITION_MISMATCH")
        _classify(_mutation, _MutationDisposition.NO_OP_REPLAY)
        return state.transition
    if (
        aggregate.run.status in {RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.RELEASED}
        or request.decision != ReplanDecision.APPROVED
        or value.application_state not in {"AWAITING_QUIESCENCE", "FAILED"}
        or not value.history
        or value.history[-1].action != "APPROVE"
        or value.latest_decision_id != value.history[-1].decision_id
        or value.history[-1].new_revision != value.decision_revision
        or state.expansion_count
    ):
        raise BindingDenied("REPLAN_NOT_AUTHORIZED")
    frozen_policy(aggregate)
    validate_candidate(aggregate, state.candidate)
    if (
        root.frozen_graph != value.base_graph
        or root.execution_profile_snapshot_digest != value.base_execution_snapshot_digest
        or root.scenario_snapshot_digest != value.scenario_snapshot_digest
    ):
        raise BindingDenied("REPLAN_STALE_GRAPH")
    source = aggregate.runtime.task(request.requesting_task_id)
    if exact_diff(aggregate, source) != value.diff:
        raise BindingDenied("REPLAN_DIFF_MISMATCH")
    affected = {value.diff.synthesis_task_id}
    while True:
        found = {
            t.task_id
            for t in aggregate.runtime.actual_graph.tasks
            if set(t.dependencies) & affected
        }
        if found <= affected:
            break
        affected |= found
    if affected & (set(root.attempts) | set(root.current_results)):
        raise BindingDenied("REPLAN_AFFECTED_CONSUMER_ADMITTED")
    # Only undispatched reservations may be retired. Every observed dispatch drains.
    for task_id, attempt in list(root.attempts.items()):
        if attempt.status == "RESERVED":
            root.attempt_history[attempt.admission.attempt_reservation_id] = attempt
            if attempt.prior_reservation_id is not None:
                prior = root.attempt_history.get(attempt.prior_reservation_id)
                if prior is None or prior.status != "FAILED":
                    raise BindingDenied("REPLAN_RECOVERY_CARRY_NOT_PROVEN")
                root.attempts[task_id] = prior
            else:
                del root.attempts[task_id]
            aggregate.runtime.task(task_id).status = TaskStatus.WAITING
    aggregate.runtime.binding_ref = root.reference()
    if any(a.status in {"DISPATCHED", "RESULT_UNKNOWN"} for a in root.attempts.values()):
        return None
    old_graph = aggregate.runtime.actual_graph.model_copy(deep=True)
    old_snapshot = ExecutionSnapshot.model_validate(root.execution_snapshot)
    child_profile = validate_child_profile(
        NodeExecutionProfile.model_validate(value.required_child_profile)
    )
    if digest(child_profile, "node-execution-profile/v1") != value.child_profile_digest:
        raise BindingDenied("REPLAN_PROFILE_MISMATCH")
    child = Task(
        task_id=value.diff.child_task_id,
        run_id=root.run_id,
        parent_task_id=source.task_id,
        task_type="risk_follow_up",
        assigned_agent="risk_analyst",
        skill_id="risk_analysis_v1",
        goal=value.diff.goal,
        origin="REPLAN",
        reason_code="MATERIAL_RISK_FOLLOW_UP",
        dependencies=[source.task_id],
        output_requirements=value.diff.output_requirements,
        task_input_evidence_ids=list(source.task_input_evidence_ids),
        status=TaskStatus.WAITING,
    )
    graph = old_graph.model_copy(deep=True)
    graph.tasks.append(child)
    synthesis = next(t for t in graph.tasks if t.task_id == value.diff.synthesis_task_id)
    synthesis.dependencies = [
        child.task_id if key == source.task_id else key for key in synthesis.dependencies
    ]
    graph.version += 1
    new_identity = GraphIdentity.of(graph)
    transition_id = digest(
        [request.replan_id, value.proposal_digest, value.latest_decision_id, new_identity],
        "risk-follow-up-transition/v1",
    )
    graph.mutation_history.append(
        {
            "transition_id": transition_id,
            "replan_id": request.replan_id,
            "version_before": old_graph.version,
            "version_after": graph.version,
            "operations": [
                {"operation": "add_node", "task_id": child.task_id},
                {
                    "operation": "add_edge",
                    "source_task_id": source.task_id,
                    "target_task_id": child.task_id,
                },
                {
                    "operation": "remove_edge",
                    "source_task_id": source.task_id,
                    "target_task_id": synthesis.task_id,
                },
                {
                    "operation": "add_edge",
                    "source_task_id": child.task_id,
                    "target_task_id": synthesis.task_id,
                },
            ],
            "proposal_id": request.replan_id,
            "proposal_digest": value.proposal_digest,
            "decision_id": value.latest_decision_id,
            "candidate_id": state.candidate.candidate_id,
            "base_graph": root.frozen_graph.model_dump(mode="json"),
            "new_graph": new_identity.model_dump(mode="json"),
            "authorized_diff": value.diff.model_dump(mode="json"),
        }
    )
    snapshot = ExecutionSnapshot.freeze(
        old_snapshot.scenario,
        (
            *old_snapshot.nodes,
            NodeProfileBinding(
                task_id=child.task_id,
                profile=child_profile,
                output_contract_digest=value.output_contract_digest,
            ),
        ),
    )
    reuse = []
    carry = []
    for task_id, result_id in root.current_results.items():
        task = aggregate.runtime.task(task_id)
        result = root.results[result_id]
        repository._current_dependencies(aggregate, task)
        await repository.verify_materials(result.output_records, run_id=root.run_id)
        attempt = root.attempts[task_id]
        if attempt.status != "COMMITTED" or result.graph != root.frozen_graph:
            raise BindingDenied("REPLAN_REUSE_NOT_PROVEN")
        profile = frozen_profile(aggregate, task)
        reuse.append(
            ResultReuseCertificate(
                transition_id=transition_id,
                source_result_id=result_id,
                source_result_digest=result.result_digest,
                source_graph=result.graph,
                target_graph=new_identity,
                task_fingerprint=result.task_fingerprint,
                admission_digest=attempt.admission.admission_binding_id,
                profile_digest=digest(profile, "node-execution-profile/v1"),
                output_contract_digest=digest(task.output_requirements, "output-contract/v1"),
                dependency_result_ids=tuple(
                    d.result_id for d in attempt.admission.dependency_result_bindings
                ),
                material_digests=tuple(r.content_digest for r in result.output_records),
            )
        )
    for task_id, attempt in root.attempts.items():
        if attempt.status != "FAILED":
            continue
        task = aggregate.runtime.task(task_id)
        repository._validate_recovery(aggregate, task, attempt)
        await repository._validate_current_recovery_evidence(attempt)
        carry.append(
            RecoveryCarryCertificate(
                transition_id=transition_id,
                reservation_id=attempt.admission.attempt_reservation_id,
                prior_admission_digest=attempt.admission.admission_binding_id,
                source_graph=attempt.admission.graph,
                target_graph=new_identity,
                task_fingerprint=task_fingerprint(task),
                profile_digest=digest(frozen_profile(aggregate, task), "node-execution-profile/v1"),
                recovery_digest=digest(attempt.recovery, "recovery-carry/v1"),
                dependency_result_ids=tuple(
                    d.result_id for d in attempt.admission.dependency_result_bindings
                ),
            )
        )
    # Every original task except the sole synthesis keeps exactly its semantic bytes.
    old_tasks = {t["task_id"]: t for t in graph_semantics(old_graph)["tasks"]}
    for t in graph_semantics(graph)["tasks"]:
        if t["task_id"] in {child.task_id, synthesis.task_id}:
            continue
        if t != old_tasks[t["task_id"]]:
            raise BindingDenied("REPLAN_DIFF_MISMATCH")
    transition = ReplanTransition(
        transition_id=transition_id,
        run_id=root.run_id,
        proposal_id=request.replan_id,
        proposal_digest=value.proposal_digest,
        decision_id=value.latest_decision_id,
        actor="LOCAL_SINGLE_USER",
        base_graph=root.frozen_graph,
        new_graph=new_identity,
        authorized_diff=value.diff,
        old_graph_snapshot=canonical_value(old_graph),
        old_execution_snapshot=canonical_value(old_snapshot),
        old_execution_snapshot_digest=root.execution_profile_snapshot_digest,
        new_execution_snapshot_digest=snapshot.execution_profile_snapshot_digest,
        applied_at=datetime.now(UTC),
        reused_results=tuple(reuse),
        carried_recovery=tuple(carry),
    )
    aggregate.runtime.actual_graph = graph
    root.frozen_graph = new_identity
    root.execution_snapshot = snapshot.model_dump(mode="json")
    root.execution_profile_snapshot_digest = snapshot.execution_profile_snapshot_digest
    root.owner_generation += 1
    root.owner_id = None
    root.lifecycle = "WAITING_REPLAN"
    root.scheduler_started = False
    request.created_task_ids = [child.task_id]
    value = value.model_copy(
        update={
            "application_state": "APPLIED",
            "applied_graph": new_identity,
            "transition_id": transition_id,
            "failure_code": None,
        }
    )
    state = state.model_copy(
        update={
            "transition": transition,
            "expansion_count": 1,
            "wait_reason": "FOLLOW_UP_EXECUTION",
            "resume_eligible": True,
            "control_revision": state.control_revision + 1,
        }
    )
    state = audit(
        aggregate,
        state,
        "replan.applied",
        actor="LOCAL_SINGLE_USER",
        decision_id=value.latest_decision_id,
    )
    store(aggregate, state, request, value)
    _classify(_mutation, _MutationDisposition.MUTATED)
    return transition


def child_dependency(aggregate, task):
    from src.domain.risk_replan import CandidateDependency

    state = control(aggregate)
    if state is None or state.transition is None or task.task_type != "risk_follow_up":
        return None
    request, value = proposal(aggregate)
    if (
        task.task_id != value.diff.child_task_id
        or task.parent_task_id != request.requesting_task_id
        or task.dependencies != [request.requesting_task_id]
        or request.decision != ReplanDecision.APPROVED
        or value.application_state != "APPLIED"
        or state.transition.new_graph != aggregate.node_binding.frozen_graph
        or aggregate.run.status == RunStatus.CANCELLED
    ):
        raise BindingDenied("REPLAN_CHILD_DEPENDENCY_DENIED")
    validate_candidate(aggregate, state.candidate)
    return CandidateDependency(
        proposal_id=request.replan_id,
        proposal_digest=value.proposal_digest,
        transition_id=state.transition.transition_id,
        candidate_id=state.candidate.candidate_id,
        candidate_digest=state.candidate.candidate_digest,
        source_attempt_id=state.candidate.attempt_id,
    )


def reuse_valid(aggregate, result):
    from src.application.execution_profiles import frozen_profile

    state = control(aggregate)
    root = aggregate.node_binding
    if state is None or state.transition is None:
        return False
    transition = state.transition
    certificates = [c for c in transition.reused_results if c.source_result_id == result.result_id]
    if len(certificates) != 1:
        return False
    certificate = certificates[0]
    task = aggregate.runtime.task(result.producer_task_id)
    attempt = root.attempts.get(task.task_id)
    if attempt is None:
        return False
    return (
        certificate.transition_id == transition.transition_id
        and certificate.source_result_digest == result.result_digest
        and certificate.source_graph == result.graph == transition.base_graph
        and certificate.target_graph == transition.new_graph == root.frozen_graph
        and certificate.task_fingerprint == task_fingerprint(task) == result.task_fingerprint
        and certificate.admission_digest == attempt.admission.admission_binding_id
        and certificate.profile_digest
        == digest(frozen_profile(aggregate, task), "node-execution-profile/v1")
        and certificate.output_contract_digest
        == digest(task.output_requirements, "output-contract/v1")
        and certificate.dependency_result_ids
        == tuple(d.result_id for d in attempt.admission.dependency_result_bindings)
        and all(
            root.current_results.get(d.producer_task_id) == d.result_id
            for d in attempt.admission.dependency_result_bindings
        )
        and certificate.material_digests == tuple(r.content_digest for r in result.output_records)
        and result.result_id not in root.invalidation_refs
    )


def finalize_parent(aggregate, child_result):
    """The caller has already validated/inserted the executed child in this transaction."""
    from src.application.research_outputs import publish_output
    from src.domain.node_binding import OutputRecord, ResultBinding, canonical_value, value_identity
    from src.domain.output_dependency import OutputStatus
    from src.domain.risk_replan import FinalizationBinding

    state = control(aggregate)
    request, value = proposal(aggregate)
    root = aggregate.node_binding
    child = aggregate.runtime.task(child_result.producer_task_id)
    child_dependency(aggregate, child)
    output = validate_candidate(aggregate, state.candidate)
    if state.finalization is not None:
        raise BindingDenied("REPLAN_ALREADY_FINALIZED")
    child_outputs = [
        r
        for r in child_result.output_records
        if r.kind == "AGENT_OUTPUT" and r.payload_snapshot["task_id"] == child.task_id
    ]
    if len(child_outputs) != 1:
        raise BindingDenied("REPLAN_CHILD_OUTPUT_MISMATCH")
    child_output = child_outputs[0]
    from src.domain.agent_output import StandardResearchAgentStructuredOutput

    StandardResearchAgentStructuredOutput.model_validate(
        child_output.payload_snapshot["structured_output"]
    )
    candidate = state.candidate
    group_id = digest(
        [value.proposal_digest, candidate.candidate_digest, child_output],
        "risk-follow-up-finalization-group/v1",
    )
    binding = FinalizationBinding(
        finalization_id="",
        finalization_digest="",
        run_id=root.run_id,
        source_task_id=candidate.task_id,
        source_candidate_id=candidate.candidate_id,
        source_candidate_digest=candidate.candidate_digest,
        source_admission_binding_id=candidate.admission_binding_id,
        source_graph=candidate.graph,
        source_profile_digest=candidate.profile_digest,
        target_graph=root.frozen_graph,
        transition_id=state.transition.transition_id,
        proposal_digest=value.proposal_digest,
        decision_id=value.latest_decision_id,
        fulfilling_child_task_id=child.task_id,
        child_output_id=child_output.record_id,
        child_output_content_digest=child_output.content_digest,
        finalization_group_id=group_id,
        committed_at=datetime.now(UTC),
    )
    identity = digest(
        binding.model_dump(exclude={"finalization_id", "finalization_digest"}),
        "risk-follow-up-finalization/v1",
    )
    binding = binding.model_copy(
        update={"finalization_id": identity, "finalization_digest": identity}
    )
    parent = aggregate.runtime.task(candidate.task_id)
    parent.status = TaskStatus.COMPLETED
    parent.progress = 1.0
    parent.result_ref = output.artifact_ref
    publish_output(parent, "agent_output", OutputStatus.COMPLETED, refs=[output.output_id])
    payload = {
        **output.structured_output.model_dump(mode="json"),
        "agent_output_id": output.output_id,
        "follow_up_fulfillment": {
            "finalization_id": identity,
            "child_output_id": child_output.record_id,
            "finalization_group_id": group_id,
        },
    }
    aggregate.artifacts.task_outputs[parent.task_id] = payload
    snapshot_payload = {
        "task_output": payload,
        "output_outcomes": canonical_value(parent.output_outcomes),
        "coverage": canonical_value(parent.evidence_source_coverage),
        "admission_binding_id": candidate.admission_binding_id,
        "resolved_inputs": list(candidate.resolved_input_binding_ids),
        "finalization_id": identity,
    }
    snapshot_digest = digest(snapshot_payload, "task-output-snapshot/v1")
    snapshot = OutputRecord(
        kind="TASK_OUTPUT_SNAPSHOT",
        record_id=snapshot_digest,
        content_digest=snapshot_digest,
        location="task-output-snapshot/" + snapshot_digest,
        record_schema="task-output-snapshot/v1",
        payload_snapshot=snapshot_payload,
    )
    reservation = root.attempts[parent.task_id]
    final = ResultBinding(
        result_id="",
        result_digest="",
        producer_task_id=parent.task_id,
        run_id=root.run_id,
        graph=root.frozen_graph,
        task_fingerprint=candidate.task_fingerprint,
        admission_binding_id=candidate.admission_binding_id,
        resolved_input_binding_ids=candidate.resolved_input_binding_ids,
        owner_generation=reservation.admission.owner.owner_generation,
        reservation_id=candidate.reservation_id,
        result_version=1,
        output_records=(candidate.output_record, snapshot),
        producer_owner=reservation.admission.owner.owner_id,
        finalization_binding=binding.model_dump(mode="json"),
        observed_execution={"provenance": "REPLAN_FINALIZED"},
    )
    from src.application.risk_admission import derive

    receipt = derive(aggregate, reservation.admission, final.output_records,
                     final.resolved_input_binding_ids,
                     fulfillment=binding.model_dump(mode="json"))
    if receipt is not None:
        if receipt["decision"] != "FINAL_SUCCESS":
            raise BindingDenied("RISK_FINAL_ADMISSION_REQUIRED")
        root.risk_admissions = {**(root.risk_admissions or {}),
                                reservation.admission.admission_binding_id: receipt}
        final = final.model_copy(update={"observed_execution": {
            **final.observed_execution, "risk_admission_digest": receipt["receipt_digest"]}})
    result_id = value_identity(final, "result_id", "result_digest")
    final = final.model_copy(update={"result_id": result_id, "result_digest": result_id})
    root.results[result_id] = final
    root.current_results[parent.task_id] = result_id
    aggregate.runtime.completed_output_refs[parent.task_id] = [output.output_id]
    state = state.model_copy(
        update={
            "finalization": binding,
            "wait_reason": "FULFILLED",
            "control_revision": state.control_revision + 1,
        }
    )
    state = audit(aggregate, state, "replan.fulfilled", decision_id=value.latest_decision_id)
    store(aggregate, state)
    return final


def admission_allowed(aggregate, task, *, dispatch):
    state = control(aggregate)
    if state is None or state.wait_reason == "FULFILLED":
        return
    if state.wait_reason == "CANCELLED":
        raise BindingDenied("REPLAN_CANCELLED")
    request, value = proposal(aggregate)
    if state.wait_reason == "FOLLOW_UP_EXECUTION" and state.transition is not None:
        if task.task_type == "risk_follow_up":
            child_dependency(aggregate, task)
            return
        # Unchanged independent recovery is admissible; downstream still lacks Risk.
        attempt = aggregate.node_binding.attempts.get(task.task_id)
        if attempt is not None:
            prior = (
                aggregate.node_binding.attempt_history.get(attempt.prior_reservation_id)
                if attempt.prior_reservation_id
                else attempt
            )
            if prior is not None and recovery_carried(aggregate, task, prior):
                return
        raise ReplanSuspended()
    if (
        state.wait_reason == "DECISION"
        and not value.reopened
        and request.decision == ReplanDecision.PENDING
    ):
        prior = aggregate.node_binding.attempts.get(task.task_id)
        if (
            task.task_id != request.requesting_task_id
            and prior is not None
            and (
                prior.status == "FAILED"
                or (
                    dispatch
                    and prior.status == "RESERVED"
                    and prior.prior_reservation_id is not None
                )
            )
        ):
            return
    raise ReplanSuspended()


def validate_replan_root(aggregate, *, validate_semantic_admission=True):
    state = control(aggregate)
    request, value = proposal(aggregate)
    validate_candidate(aggregate, state.candidate,
                       validate_semantic_admission=validate_semantic_admission)
    frozen_policy(aggregate)
    root = aggregate.node_binding
    if state.transition is not None:
        transition = state.transition
        expected = digest(
            [
                request.replan_id,
                value.proposal_digest,
                transition.decision_id,
                transition.new_graph,
            ],
            "risk-follow-up-transition/v1",
        )
        if (
            transition.transition_id != expected
            or transition.run_id != root.run_id
            or transition.proposal_digest != value.proposal_digest
            or transition.authorized_diff != value.diff
            or transition.base_graph != value.base_graph
            or transition.new_graph != root.frozen_graph
            or transition.new_graph.version != transition.base_graph.version + 1
            or transition.new_graph.graph_id != transition.base_graph.graph_id
            or transition.old_execution_snapshot_digest != value.base_execution_snapshot_digest
            or transition.new_execution_snapshot_digest != root.execution_profile_snapshot_digest
            or state.expansion_count != 1
        ):
            raise BindingDenied("REPLAN_TRANSITION_MISMATCH")
        old_snapshot = ExecutionSnapshot.model_validate(transition.old_execution_snapshot)
        current_snapshot = ExecutionSnapshot.model_validate(root.execution_snapshot)
        old_nodes = {n.task_id: n for n in old_snapshot.nodes}
        current_nodes = {n.task_id: n for n in current_snapshot.nodes}
        if (
            old_snapshot.execution_profile_snapshot_digest
            != transition.old_execution_snapshot_digest
            or old_snapshot.scenario != current_snapshot.scenario
            or any(current_nodes.get(key) != node for key, node in old_nodes.items())
            or set(current_nodes) != {*old_nodes, value.diff.child_task_id}
        ):
            raise BindingDenied("REPLAN_PROFILE_MISMATCH")
        from src.domain.node_binding import graph_semantics
        from src.domain.task import ActualRuntimeGraph, Task

        expected = ActualRuntimeGraph.model_validate(transition.old_graph_snapshot)
        if GraphIdentity.of(expected) != transition.base_graph:
            raise BindingDenied("REPLAN_TRANSITION_MISMATCH", "base graph bytes")
        expected.tasks.append(
            Task(
                task_id=value.diff.child_task_id,
                run_id=root.run_id,
                parent_task_id=value.diff.source_task_id,
                task_type="risk_follow_up",
                assigned_agent=value.diff.assigned_agent,
                skill_id=value.diff.skill_id,
                goal=value.diff.goal,
                origin=value.diff.origin,
                reason_code=value.diff.reason_code,
                dependencies=[value.diff.source_task_id],
                output_requirements=value.diff.output_requirements,
            )
        )
        synthesis = next(t for t in expected.tasks if t.task_id == value.diff.synthesis_task_id)
        synthesis.dependencies = [
            value.diff.child_task_id if key == value.diff.source_task_id else key
            for key in synthesis.dependencies
        ]
        expected.version += 1
        if graph_semantics(expected) != graph_semantics(aggregate.runtime.actual_graph):
            raise BindingDenied("REPLAN_DIFF_MISMATCH")
    if state.finalization is not None:
        binding = state.finalization
        identity = digest(
            binding.model_dump(exclude={"finalization_id", "finalization_digest"}),
            "risk-follow-up-finalization/v1",
        )
        child_result = root.results.get(root.current_results.get(binding.fulfilling_child_task_id))
        parent_result = root.results.get(root.current_results.get(binding.source_task_id))
        if (
            binding.finalization_id != identity
            or binding.finalization_digest != identity
            or binding.source_candidate_id != state.candidate.candidate_id
            or binding.source_candidate_digest != state.candidate.candidate_digest
            or binding.source_graph != state.candidate.graph
            or binding.target_graph != root.frozen_graph
            or state.transition is None
            or binding.transition_id != state.transition.transition_id
            or binding.proposal_digest != value.proposal_digest
            or child_result is None
            or parent_result is None
            or parent_result.finalization_binding != binding.model_dump(mode="json")
            or not any(
                r.record_id == binding.child_output_id
                and r.content_digest == binding.child_output_content_digest
                for r in child_result.output_records
            )
        ):
            raise BindingDenied("REPLAN_FINALIZATION_MISMATCH")


def recovery_carried(aggregate, task, prior):
    from src.application.execution_profiles import frozen_profile

    state = control(aggregate)
    if state is None or state.transition is None:
        return False
    certs = [
        c
        for c in state.transition.carried_recovery
        if c.reservation_id == prior.admission.attempt_reservation_id
    ]
    if len(certs) != 1:
        return False
    cert = certs[0]
    return (
        cert.transition_id == state.transition.transition_id
        and cert.prior_admission_digest == prior.admission.admission_binding_id
        and cert.source_graph == prior.admission.graph == state.transition.base_graph
        and cert.target_graph == aggregate.node_binding.frozen_graph
        and cert.task_fingerprint == task_fingerprint(task)
        and cert.profile_digest
        == digest(frozen_profile(aggregate, task), "node-execution-profile/v1")
        and cert.recovery_digest == digest(prior.recovery, "recovery-carry/v1")
        and prior.recovery["profile_digest"] == state.transition.old_execution_snapshot_digest
        and prior.recovery["scenario_digest"] == aggregate.node_binding.scenario_snapshot_digest
        and cert.dependency_result_ids
        == tuple(d.result_id for d in prior.admission.dependency_result_bindings)
    )
