"""Fail-closed validation for the explicit Risk Resume command.

The authorization helper mutates an aggregate only for the repository transaction.
Inspection is a proposal, never execution authority; neither path invokes a provider.
"""

from datetime import UTC, datetime

from src.application.execution_profiles import BOUNDED_TERRA_POLICY, frozen_profile
from src.domain.external_failure_resume import (
    ROUTES,
    VERSION,
    CompletedWorkReuseDecisionV1,
    ExternalFailureResumeV1,
    FailureCycleIdentity,
    ResumeExternalFailure,
)
from src.domain.node_binding import (
    BindingDenied,
    canonical_value,
    check_value_identity,
    digest,
    task_fingerprint,
)
from src.domain.recovery import Action, FailureClass, RecoveryBudget

REUSE_KINDS = {
    "evidence_collection": "Evidence",
    "fundamental_analysis": "Fundamentals",
    "peer_analysis": "Peers",
    "research_news_analysis": "ResearchNews",
    "valuation_analysis": "Valuation",
}


def legacy_snapshot(aggregate):
    from src.application.persistence import SQLAlchemyApplicationRepository

    return SQLAlchemyApplicationRepository._payload(aggregate)


def control(aggregate):
    raw = getattr(aggregate.node_binding, "external_failure_resume", None)
    return ExternalFailureResumeV1.model_validate(raw) if raw is not None else None


def committed_request_replay(state, request, *, actor):
    """Authenticate and resolve only the durable command key and canonical payload."""
    if actor != request.actor or not actor:
        raise BindingDenied("RESUME_ACTOR_MISMATCH")
    if state is None:
        return None
    for receipt in state.receipts:
        if (receipt.actor, receipt.idempotency_key) == (actor, request.idempotency_key):
            if receipt.request_digest != digest(request, VERSION):
                raise BindingDenied("RESUME_IDEMPOTENCY_CONFLICT")
            return receipt
    return None


def request_replay(state, request, *, actor):
    """Replay precedes mutable state checks; keys never expire or target a new failure."""
    receipt = committed_request_replay(state, request, actor=actor)
    if receipt is not None or state is None:
        return receipt
    for receipt in state.receipts:
        failure = next(f for f in state.failures if f.failure_id == receipt.prior_failure_id)
        if failure.identity == request.expected_failure_cycle_identity:
            raise BindingDenied("RESUME_FAILURE_ALREADY_CONSUMED")
    return None


def envelope_proposal(aggregate, task):
    """Retain tighter frozen limits; never resolve today's defaults or mint route proof."""
    profile = frozen_profile(aggregate, task)
    b = profile.recovery_budget
    if (
        profile.policy_evidence_source != BOUNDED_TERRA_POLICY
        or profile.resolved_route != ROUTES[0]
        or tuple(profile.recovery_fallback_routes) != ROUTES[1:]
        or profile.accepted_request_proof is None
        or b is None
        or b.max_total_attempts_per_task < 1
    ):
        raise BindingDenied("RESUME_PROFILE_INCOMPATIBLE")
    values = b.model_dump()
    values.update(
        max_total_attempts_per_task=min(2, b.max_total_attempts_per_task),
        max_same_route_attempts=1,
        max_model_fallbacks=min(1, b.max_model_fallbacks),
        max_cross_provider_switches=0,
        max_capability_checks=0,
        max_recovery_decisions=min(5, b.max_recovery_decisions),
        max_runtime_replans=0,
        max_total_recovery_time=min(300, b.max_total_recovery_time),
    )
    budget = RecoveryBudget(**values)
    return {
        "version": VERSION,
        "routes": list(ROUTES),
        "budget": budget.model_dump(mode="json"),
        "duration_seconds": budget.max_total_recovery_time,
        "profile_digest": aggregate.node_binding.execution_profile_snapshot_digest,
        "scenario_digest": aggregate.node_binding.scenario_snapshot_digest,
        "task_fingerprint": task_fingerprint(task),
        "accepted_request_proof": canonical_value(profile.accepted_request_proof),
    }


def settled_failure(aggregate, task_id, records):
    """Prove exact settlement of the exhausted route chain, not merely terminality."""
    root = aggregate.node_binding
    task = aggregate.runtime.task(task_id)
    if task.task_type != "risk_analysis" or task_id in root.current_results:
        raise BindingDenied("RESUME_NOT_ELIGIBLE", "exact failed Risk required")
    if root.replan is not None or aggregate.run.status.value != "FAILED":
        raise BindingDenied("RESUME_NOT_ELIGIBLE", "terminal Run/Replan boundary")
    if aggregate.run.completed_at is None:
        raise BindingDenied("RESUME_NOT_ELIGIBLE", "missing terminal timestamp")
    prior = root.attempts.get(task_id)
    if prior is None:
        state = control(aggregate)
        closure = (
            next((f for f in state.failures if f.failure_id == state.current_failure_id), None)
            if state
            else None
        )
        if closure is None:
            raise BindingDenied("RESUME_NOT_ELIGIBLE", "missing failed reservation")
        prior = root.attempt_history.get(closure.identity.failed_reservation_id)
    if prior is None or prior.status not in {"DISPATCHED", "FAILED", "RESULT_UNKNOWN"}:
        raise BindingDenied("RESUME_NOT_ELIGIBLE", "reservation state")
    if any(a.status != "COMMITTED" for key, a in root.attempts.items() if key != task_id):
        raise BindingDenied("RESUME_RESULT_UNKNOWN", "unsettled sibling")
    if any(
        t.task_type == "report_synthesis"
        and (t.task_id in root.attempts or t.task_id in root.current_results)
        for t in aggregate.runtime.actual_graph.tasks
    ):
        raise BindingDenied("RESUME_NOT_ELIGIBLE", "downstream work exists")
    reservations = {
        a.admission.attempt_reservation_id: a
        for a in (*root.attempt_history.values(), *root.attempts.values())
        if a.admission.task_id == task_id
    }
    rid = prior.admission.attempt_reservation_id
    tail = [r for r in records if r.node_reservation_id == rid]
    if not tail or tail[-1].kind != "TERMINAL" or tail[-1].outcome != "FAIL":
        raise BindingDenied("RESUME_NOT_ELIGIBLE", "missing terminal receipt")
    scope = tail[-1].scope
    if (
        scope.run_id != aggregate.run.run_id
        or scope.task_id != task_id
        or scope.object_id != aggregate.run.research_object_id
        or scope.scheme_id != aggregate.scheme.scheme_id
        or scope.task_profile != task.task_type
    ):
        raise BindingDenied("RESUME_IDENTITY_MISMATCH", "receipt scope")
    owned = [r for r in records if r.scope.operation_id == scope.operation_id]
    if any(r.scope != scope or r.node_reservation_id not in reservations for r in owned):
        raise BindingDenied("RESUME_RESULT_UNKNOWN", "ambiguous operation scope")
    if len({r.record_id for r in owned}) != len(owned):
        raise BindingDenied("RESUME_RESULT_UNKNOWN", "duplicate receipt")
    starts, ends = {}, {}
    for record in owned:
        if record.kind not in {"ATTEMPT_STARTED", "ATTEMPT_COMPLETED"}:
            continue
        target = starts if record.kind == "ATTEMPT_STARTED" else ends
        if not record.attempt_id or record.attempt_id in target:
            raise BindingDenied("RESUME_RESULT_UNKNOWN", "duplicate provider attempt")
        target[record.attempt_id] = record
    if not starts or starts.keys() != ends.keys():
        raise BindingDenied("RESUME_RESULT_UNKNOWN", "unsettled provider request")
    completed = []
    for identity, start in starts.items():
        end = ends[identity]
        if any(
            getattr(start, key) != getattr(end, key)
            for key in (
                "scope",
                "node_reservation_id",
                "attempt_number",
                "route",
                "provider",
                "model",
                "capability_check",
            )
        ):
            raise BindingDenied("RESUME_RESULT_UNKNOWN", "provider pairing mismatch")
        try:
            ordered = datetime.fromisoformat(start.timestamp) < datetime.fromisoformat(
                end.timestamp
            )
        except (ValueError, TypeError):
            ordered = False
        if not ordered or owned.index(start) >= owned.index(end):
            raise BindingDenied("RESUME_RESULT_UNKNOWN", "ambiguous attempt timestamps")
        if (
            start.outcome != "STARTED"
            or start.capability_check
            or end.outcome != "FAIL"
            or end.failure_class != FailureClass.PROVIDER_UNAVAILABLE
            or end.safe_failure is None
            or end.safe_failure.retryable is not True
        ):
            raise BindingDenied("RESUME_NOT_ELIGIBLE", "mixed/nonexternal failure")
        completed.append(end)
    completed.sort(key=lambda r: r.attempt_number)
    if (
        [r.attempt_number for r in completed] != [1, 2]
        or tuple(r.route for r in completed) != ROUTES
        or completed[-1].node_reservation_id != rid
    ):
        raise BindingDenied("RESUME_NOT_ELIGIBLE", "not exhausted Sol/Terra chain")
    decisions = [r for r in owned if r.kind == "DECISION"]
    terminal = tail[-1]
    if (
        len([r for r in owned if r.kind == "TERMINAL"]) != 1
        or owned[-1] != terminal
        or not decisions
        or decisions[-1].outcome != "ALLOW"
        or decisions[-1].decision is None
        or decisions[-1].decision.action != Action.FAIL_TASK
        or decisions[-1].decision.reason_code not in {"NO_ALLOWED_ROUTE", "BUDGET_EXHAUSTED"}
        or decisions[-1].node_reservation_id != rid
        or owned.index(decisions[-1]) <= owned.index(completed[-1])
        or terminal.failure_class != FailureClass.PROVIDER_UNAVAILABLE
    ):
        raise BindingDenied("RESUME_NOT_ELIGIBLE", "terminal exhaustion proof")
    for decision in decisions:
        context = decision.recovery_context
        if (
            context is None
            or context.scope != scope
            or context.failure.failure_stage != "PROVIDER"
            or context.failure.failure_class != FailureClass.PROVIDER_UNAVAILABLE
        ):
            raise BindingDenied("RESUME_NOT_ELIGIBLE", "failure stage evidence")
    return (
        FailureCycleIdentity(
            operation_id=scope.operation_id,
            failed_reservation_id=rid,
            failed_reservation_generation=prior.generation,
            terminal_receipt_id=terminal.record_id,
            terminal_receipt_digest=digest(terminal, VERSION),
            ordered_receipts_digest=digest(owned, VERSION),
            failed_state_snapshot_digest=digest(
                {
                    "reservation": prior,
                    "task": task,
                    "completed_at": aggregate.run.completed_at,
                    "graph": root.frozen_graph,
                    "profile": root.execution_profile_snapshot_digest,
                    "scenario": root.scenario_snapshot_digest,
                },
                VERSION,
            ),
        ),
        prior,
        tuple(owned),
    )


def validate_expectations(aggregate, request, failure, proposal, *, actor):
    if not isinstance(request, ResumeExternalFailure):
        request = ResumeExternalFailure.model_validate(request)
    if request.actor != actor:
        raise BindingDenied("RESUME_ACTOR_MISMATCH")
    root = aggregate.node_binding
    if (
        request.expected_binding_ref != root.reference()
        or request.expected_owner_generation != root.owner_generation
        or request.expected_run_state != aggregate.run.status.value
        or request.expected_failure_cycle_identity != failure
    ):
        raise BindingDenied("RESUME_STALE")
    if (
        request.run_id != aggregate.run.run_id
        or request.expected_graph_identity != root.frozen_graph
        or request.expected_profile_digest != root.execution_profile_snapshot_digest
        or request.expected_scenario_digest != root.scenario_snapshot_digest
        or request.expected_research_object_id != aggregate.run.research_object_id
        or request.expected_goal_hash != digest(aggregate.goal)
        or request.expected_scheme_hash != digest(aggregate.scheme)
        or request.expected_as_of != aggregate.run.as_of.isoformat()
        or request.expected_resume_envelope_digest != digest(proposal, VERSION)
    ):
        raise BindingDenied("RESUME_IDENTITY_MISMATCH")
    state = control(aggregate)
    if state is None:
        adoption = request.historical_adoption
        if adoption is None:
            raise BindingDenied("HISTORICAL_OPT_IN_REQUIRED")
        if adoption.expected_legacy_snapshot_digest != digest(legacy_snapshot(aggregate), VERSION):
            raise BindingDenied("RESUME_STALE", "legacy snapshot")
    elif request.historical_adoption is not None:
        raise BindingDenied("RESUME_IDENTITY_MISMATCH", "already adopted")


async def validate_reuse(repository, aggregate, risk_task):
    """Validate current producers and all exact admitted material/dependency bindings.

    Original collector freshness authority must be retained in evidence provenance;
    absence is unknown, never replaced with a contemporary default TTL.
    """
    root = aggregate.node_binding
    kinds = {}
    for task in aggregate.runtime.actual_graph.tasks:
        if task.task_type in REUSE_KINDS:
            kind = REUSE_KINDS[task.task_type]
            if kind in kinds:
                raise BindingDenied("RESUME_REUSE_INVALID", "ambiguous producer " + kind)
            kinds[kind] = task
    if set(kinds) != set(REUSE_KINDS.values()):
        raise BindingDenied("RESUME_REUSE_INVALID", "five retained producers required")
    # Risk has its own exact closure. Peers and Valuation are retained siblings,
    # validated independently below, not invented Risk ancestors.
    _validate_dependency_topology(aggregate, (*kinds.values(), risk_task))
    dependencies = repository._current_dependencies(aggregate, risk_task)
    risk_prior = root.attempts.get(risk_task.task_id)
    if risk_prior is None:
        state = control(aggregate)
        failure = next(
            (f for f in state.failures if f.failure_id == state.current_failure_id), None
        ) if state else None
        if failure is not None:
            risk_prior = root.attempt_history.get(failure.identity.failed_reservation_id)
    if risk_prior is None or risk_prior.admission.dependency_result_bindings != dependencies:
        raise BindingDenied("RESUME_REUSE_INVALID", "changed Risk input closure")
    decisions = []
    materials = {}
    for kind in REUSE_KINDS.values():
        task = kinds[kind]
        result = root.results.get(root.current_results.get(task.task_id))
        prior = root.attempts.get(task.task_id)
        if (
            result is None
            or prior is None
            or task.status.value != "COMPLETED"
            or prior.status != "COMMITTED"
            or result.reservation_id != prior.admission.attempt_reservation_id
            or result.admission_binding_id != prior.admission.admission_binding_id
            or result.producer_task_id != task.task_id
            or result.run_id != aggregate.run.run_id
            or result.task_fingerprint != task_fingerprint(task)
            or result.owner_generation != prior.admission.owner.owner_generation
            or result.owner_generation > root.owner_generation
            or prior.admission.graph != root.frozen_graph
            or result.result_id in root.invalidation_refs
            or result.graph != root.frozen_graph
            or prior.admission.goal_hash != digest(aggregate.goal)
            or prior.admission.scheme_hash != digest(aggregate.scheme)
            or prior.admission.dependency_result_bindings
            != repository._current_dependencies(aggregate, task)
        ):
            raise BindingDenied("RESUME_REUSE_INVALID", kind)
        check_value_identity(result, "result_digest", "result_id")
        check_value_identity(prior.admission, "admission_binding_id")
        refs = list(result.output_records) + list(prior.admission.preexisting_inputs)
        for identity in result.resolved_input_binding_ids:
            resolved = root.resolved_inputs.get(identity)
            if (
                resolved is None
                or resolved.reservation_id != result.reservation_id
                or resolved.admission_binding_id != result.admission_binding_id
                or resolved.input_digest
                != digest(resolved.payload_snapshot, "wp02-input-payload/v1")
            ):
                raise BindingDenied("RESUME_REUSE_INVALID", "resolved inputs " + kind)
            check_value_identity(resolved, "resolved_input_binding_id")
            refs.extend(resolved.material_refs)
        await repository.verify_materials(refs, run_id=aggregate.run.run_id)
        for ref in refs:
            if ref.record_id in materials and materials[ref.record_id] != ref:
                raise BindingDenied("RESUME_REUSE_INVALID", "material collision")
            materials[ref.record_id] = ref
        snapshots = [r for r in result.output_records if r.kind == "TASK_OUTPUT_SNAPSHOT"]
        if len(snapshots) != 1 or snapshots[0].payload_snapshot != {
            "task_output": canonical_value(aggregate.artifacts.task_outputs.get(task.task_id, {})),
            "output_outcomes": canonical_value(task.output_outcomes),
            "coverage": canonical_value(task.evidence_source_coverage),
            "admission_binding_id": result.admission_binding_id,
            "resolved_inputs": list(result.resolved_input_binding_ids),
        }:
            raise BindingDenied("RESUME_REUSE_INVALID", "output snapshot " + kind)
        repository._validate_wp04_result(aggregate, task, aggregate.artifacts)
        decisions.append(
            CompletedWorkReuseDecisionV1(
                kind=kind,
                producer_task_id=task.task_id,
                result_id=result.result_id,
                result_digest=result.result_digest,
                binding_ref=root.reference(),
                graph=root.frozen_graph,
                scenario_digest=root.scenario_snapshot_digest,
                profile_digest=root.execution_profile_snapshot_digest,
                research_object_id=aggregate.run.research_object_id,
                as_of=aggregate.run.as_of.isoformat(),
                dependency_bindings=tuple(
                    canonical_value(d) for d in prior.admission.dependency_result_bindings
                ),
                material_manifest_digest=digest(refs, VERSION),
                checks=(
                    "CURRENT_RESULT",
                    "EXACT_ADMISSION",
                    "INPUT_CLOSURE",
                    "MATERIAL_BYTES",
                    "OUTPUT_SNAPSHOT",
                    "WP04",
                    "HARD_ANCHORS",
                    "FROZEN_FRESHNESS",
                ),
            )
        )
    for name in ("revenue_growth", "ebitda_margin"):
        outcomes = [o for t in kinds.values() for o in t.output_outcomes if o.output_id == name]
        if len(outcomes) != 1 or outcomes[0].status.value != "COMPLETED" or not outcomes[0].refs:
            raise BindingDenied("RESUME_REUSE_INVALID", "required hard anchor " + name)
        for identity in outcomes[0].refs:
            record = materials.get(identity)
            if (
                record is None
                or record.kind != "CALCULATION_CORE"
                or record.payload_snapshot.get("status") != "PASS"
            ):
                raise BindingDenied("RESUME_REUSE_INVALID", "calculation " + name)
            for evidence_id in record.payload_snapshot.get("input_evidence_ids", ()):
                evidence = materials.get(evidence_id)
                if evidence is None or evidence.payload_snapshot.get("status") != "ACCEPTED":
                    raise BindingDenied("RESUME_REUSE_INVALID", "anchor evidence")
    research_object = await repository.get_object(aggregate.run.research_object_id)
    if research_object is None:
        raise BindingDenied("RESUME_REUSE_INVALID", "research object missing")
    # Crucially do not guess the original ingestion policy from the current dataset
    # defaults. Versioned provenance is a prerequisite for automatic reuse.
    for record in materials.values():
        if record.kind != "EVIDENCE" or record.payload_snapshot.get("status") != "ACCEPTED":
            continue
        validate_evidence_provenance(
            aggregate, record.payload_snapshot, expected_symbol=research_object.symbol
        )
    return tuple(decisions)



def _validate_dependency_topology(aggregate, tasks):
    """Reject incomplete/cyclic closures before traversing repository bindings."""
    graph = {task.task_id: task for task in aggregate.runtime.actual_graph.tasks}
    visiting, complete = set(), set()

    def visit(identity):
        if identity in visiting or identity not in graph:
            raise BindingDenied("RESUME_REUSE_INVALID", "cyclic/incomplete dependency closure")
        if identity in complete:
            return
        visiting.add(identity)
        for dependency in graph[identity].dependencies:
            visit(dependency)
        visiting.remove(identity)
        complete.add(identity)

    for task in tasks:
        visit(task.task_id)


def validate_evidence_provenance(aggregate, payload, *, expected_symbol):
    """Read persisted validation semantics and match the frozen producer permission.

    A supported policy is necessary, not sufficient: result/material validation and
    the exact admitted consumer closure remain the caller's responsibility.
    """
    from pydantic import ValidationError

    from src.data.freshness import FreshnessPolicy, FreshnessStatus
    from src.domain.evidence import EvidenceRecord

    if not payload.get("validation_provenance"):
        raise BindingDenied("RESUME_REUSE_POLICY_UNKNOWN", payload.get("evidence_id", ""))
    try:
        record = EvidenceRecord.model_validate(payload)
    except ValidationError as exc:
        raise BindingDenied("RESUME_REUSE_POLICY_UNKNOWN", "unsupported provenance") from exc
    provenance = record.validation_provenance
    request = provenance.request
    if (
        record.run_id != aggregate.run.run_id
        or record.object_id != aggregate.run.research_object_id
        or request.as_of != aggregate.run.as_of
        or request.symbol != expected_symbol
        or record.status.value != "ACCEPTED"
        or (request.expected_period and record.period != request.expected_period.upper())
        or FreshnessPolicy(provenance.freshness.max_age_days).evaluate(
            record.as_of, request.as_of
        ) != FreshnessStatus.FRESH
    ):
        raise BindingDenied("RESUME_REUSE_INVALID", "evidence freshness/identity")
    producers = [t for t in aggregate.runtime.actual_graph.tasks
                 if t.task_id == record.producer_task_id]
    if len(producers) != 1:
        raise BindingDenied("RESUME_REUSE_POLICY_UNKNOWN", "evidence producer")
    profile = frozen_profile(aggregate, producers[0])
    matches = [p for p in profile.data_permissions if (
        p.capability_id == request.dataset
        and p.fields == request.fields
        and p.observation_limit == request.limit
        and p.expected_period == request.expected_period
        and record.provider in p.providers
        and p.category == record.evidence_category.value
        and p.purpose == record.evidence_purpose
        and p.data_scope_id in profile.data_scope_ids
    )]
    if len(matches) != 1:
        raise BindingDenied("RESUME_REUSE_POLICY_UNKNOWN", "frozen data permission")
    return provenance

def validate_control(aggregate):
    """Cross-field load/write invariants; there is one lifecycle authority."""
    state = control(aggregate)
    root = aggregate.node_binding
    if state is None:
        if root.lifecycle in {"EXTERNAL_FAILURE_PAUSED", "EXTERNAL_RESUME_PENDING"}:
            raise BindingDenied("RESUME_AUTHORIZATION_MISSING")
        return
    for failure in state.failures:
        archive = root.attempt_history.get(failure.identity.failed_reservation_id)
        if archive is None or canonical_value(archive) != failure.archived_reservation:
            raise BindingDenied("RESUME_HISTORY_MISMATCH")
    for envelope in state.envelopes:
        if (
            envelope.run_id != aggregate.run.run_id
            or envelope.graph != root.frozen_graph
            or envelope.profile_digest != root.execution_profile_snapshot_digest
            or envelope.scenario_digest != root.scenario_snapshot_digest
            or envelope.goal_hash != digest(aggregate.goal)
            or envelope.scheme_hash != digest(aggregate.scheme)
            or envelope.object_id != aggregate.run.research_object_id
            or envelope.as_of != aggregate.run.as_of.isoformat()
        ):
            raise BindingDenied("RESUME_IDENTITY_MISMATCH")
    if root.lifecycle == "EXTERNAL_FAILURE_PAUSED":
        if (
            state.current_failure_id is None
            or aggregate.run.status.value != "FAILED"
            or aggregate.runtime.run_status.value != "FAILED"
            or root.owner_id is not None
            or root.scheduler_started
        ):
            raise BindingDenied("RESUME_STATE_MISMATCH")
    if root.lifecycle == "EXTERNAL_RESUME_PENDING":
        envelope = current_envelope(aggregate)
        if (
            envelope is None
            or root.owner_id is not None
            or root.scheduler_started
            or aggregate.run.status.value != "RUNNING"
            or aggregate.runtime.run_status.value != "RUNNING"
            or aggregate.run.completed_at is not None
            or envelope.task_id in root.attempts
            or aggregate.runtime.task(envelope.task_id).status.value != "WAITING"
        ):
            raise BindingDenied("RESUME_STATE_MISMATCH")


def current_envelope(aggregate):
    state = control(aggregate)
    return (
        next((e for e in state.envelopes if e.cycle_id == state.current_cycle_id), None)
        if state
        else None
    )


def audit_event(aggregate, kind, *, failure_id, cycle_id=None, authorization_id=None):
    from uuid import uuid4

    return dict(
        event_id="EXT-" + str(uuid4()),
        type="external_failure." + kind,
        timestamp=datetime.now(UTC).isoformat(),
        run_id=aggregate.run.run_id,
        failure_id=failure_id,
        cycle_id=cycle_id,
        authorization_id=authorization_id,
        binding_revision=aggregate.node_binding.binding_revision + 1,
    )


async def inspect(repository, aggregate, *, actor):
    """Read-only projection: no adoption, clock extension, reservation or claim."""
    root = aggregate.node_binding
    state = control(aggregate)
    result = dict(
        lifecycle=root.lifecycle,
        binding_ref=canonical_value(root.reference()),
        owner_generation=root.owner_generation,
        control=canonical_value(state),
        legal_actions=[],
        denial_reasons=[],
        authoritative_risk_result=None,
    )
    risks = [t for t in aggregate.runtime.actual_graph.tasks if t.task_type == "risk_analysis"]
    if len(risks) != 1:
        result["denial_reasons"].append("RESUME_NOT_ELIGIBLE")
        return result
    task = risks[0]
    result["authoritative_risk_result"] = root.current_results.get(task.task_id)
    try:
        records = await repository._current_recovery_records(aggregate.run.run_id, task.task_id)
        failure, _, _ = settled_failure(aggregate, task.task_id, records)
        await repository._resume_terminal_event(aggregate)
        proposal = envelope_proposal(aggregate, task)
        reuse = await validate_reuse(repository, aggregate, task)
        expectations = dict(
            run_id=aggregate.run.run_id,
            failed_node_id=task.task_id,
            actor=actor,
            expected_run_state="FAILED",
            expected_binding_ref=canonical_value(root.reference()),
            expected_owner_generation=root.owner_generation,
            expected_graph_identity=canonical_value(root.frozen_graph),
            expected_profile_digest=root.execution_profile_snapshot_digest,
            expected_scenario_digest=root.scenario_snapshot_digest,
            expected_research_object_id=aggregate.run.research_object_id,
            expected_goal_hash=digest(aggregate.goal),
            expected_scheme_hash=digest(aggregate.scheme),
            expected_as_of=aggregate.run.as_of.isoformat(),
            expected_failure_cycle_identity=canonical_value(failure),
            expected_resume_envelope_digest=digest(proposal, VERSION),
        )
        if state is None:
            expectations["historical_adoption"] = dict(
                contract_version=VERSION,
                expected_legacy_snapshot_digest=digest(legacy_snapshot(aggregate), VERSION),
                acknowledge_preserved_terminal_history=True,
            )
            result["denial_reasons"].append("HISTORICAL_OPT_IN_REQUIRED")
        result.update(reuse_validation=canonical_value(reuse), envelope_proposal=proposal)
        result["legal_actions"] = [dict(command="ResumeExternalFailure", expectations=expectations)]
    except BindingDenied as exc:
        result["denial_reasons"].append(exc.code)
    return result


async def authorize(repository, aggregate, request, *, actor):
    """Called only inside the existing aggregate transaction; events commit with it."""
    from datetime import timedelta
    from uuid import uuid4

    from src.domain.enums import RunStatus, TaskStatus
    from src.domain.external_failure_resume import (
        FailureClosureV1,
        ResumeReceiptV1,
        RiskResumeExecutionEnvelopeV1,
    )

    request = ResumeExternalFailure.model_validate(request)
    matches = [t for t in aggregate.runtime.actual_graph.tasks
               if t.task_id == request.failed_node_id and t.task_type == "risk_analysis"]
    if request.run_id != aggregate.run.run_id or len(matches) != 1:
        raise BindingDenied("RESUME_IDENTITY_MISMATCH", "exact Run/Risk required")
    state = control(aggregate)
    replay = request_replay(state, request, actor=actor)
    if replay is not None:
        return replay
    records = await repository._current_recovery_records(request.run_id, request.failed_node_id)
    failure, prior, owned = settled_failure(aggregate, request.failed_node_id, records)
    await repository._resume_terminal_event(aggregate)
    task = aggregate.runtime.task(request.failed_node_id)
    proposal = envelope_proposal(aggregate, task)
    validate_expectations(aggregate, request, failure, proposal, actor=actor)
    reuse = await validate_reuse(repository, aggregate, task)
    legacy = legacy_snapshot(aggregate) if state is None else None
    state = state or ExternalFailureResumeV1()
    root = aggregate.node_binding
    now = datetime.now(UTC)
    closure = next((f for f in state.failures if f.identity == failure), None)
    audit = list(state.audit)
    failures = list(state.failures)
    if closure is None:
        closure = FailureClosureV1(
            failure_id="failure:" + str(uuid4()),
            identity=failure,
            task_id=task.task_id,
            original_completed_at=aggregate.run.completed_at,
            closed_at=now,
            archived_reservation=canonical_value(prior),
            receipts=tuple(canonical_value(r) for r in owned),
            legacy_snapshot=legacy,
        )
        failures.append(closure)
        audit.append(audit_event(aggregate, "closed", failure_id=closure.failure_id))
    old = root.attempt_history.get(failure.failed_reservation_id)
    if old is not None and old != prior:
        raise BindingDenied("RESUME_HISTORY_MISMATCH")
    root.attempt_history[failure.failed_reservation_id] = prior
    root.attempts.pop(task.task_id, None)
    cycle_id, authorization_id = str(uuid4()), str(uuid4())
    manifest_digest = digest(reuse, VERSION)
    envelope = RiskResumeExecutionEnvelopeV1(
        authorization_id=authorization_id,
        cycle_id=cycle_id,
        operation_id="risk-resume:" + cycle_id,
        cycle_ordinal=len(state.envelopes) + 1,
        prior_failure_cycle_identity=failure,
        run_id=aggregate.run.run_id,
        task_id=task.task_id,
        object_id=aggregate.run.research_object_id,
        goal_hash=digest(aggregate.goal),
        scheme_hash=digest(aggregate.scheme),
        as_of=aggregate.run.as_of.isoformat(),
        graph=root.frozen_graph,
        scenario_digest=root.scenario_snapshot_digest,
        profile_digest=root.execution_profile_snapshot_digest,
        task_fingerprint=task_fingerprint(task),
        reuse_manifest_digest=manifest_digest,
        policy_digest=digest(proposal, VERSION),
        authorized_at=now,
        deadline_at=now + timedelta(seconds=proposal["duration_seconds"]),
        budget=RecoveryBudget.model_validate(proposal["budget"]),
    )
    event = audit_event(
        aggregate,
        "resume_authorized",
        failure_id=closure.failure_id,
        cycle_id=cycle_id,
        authorization_id=authorization_id,
    )
    audit.append(event)
    receipt = ResumeReceiptV1(
        authorization_id=authorization_id,
        request_digest=digest(request, VERSION),
        actor=actor,
        idempotency_key=request.idempotency_key,
        prior_failure_id=closure.failure_id,
        new_cycle_id=cycle_id,
        envelope_digest=digest(envelope, VERSION),
        reuse_manifest=reuse,
        reuse_manifest_digest=manifest_digest,
        authorized_at=now,
        committed_revision=root.binding_revision + 1,
        event_id=event["event_id"],
        original_failure_timestamp=closure.original_completed_at,
    )
    state = ExternalFailureResumeV1(
        failures=tuple(failures),
        envelopes=(*state.envelopes, envelope),
        receipts=(*state.receipts, receipt),
        current_failure_id=closure.failure_id,
        current_cycle_id=cycle_id,
        audit=tuple(audit),
    )
    root.external_failure_resume = state.model_dump(mode="json")
    root.owner_generation += 1
    root.owner_id = None
    root.scheduler_started = False
    root.lifecycle = "EXTERNAL_RESUME_PENDING"
    task.status = TaskStatus.WAITING
    aggregate.run.status = aggregate.runtime.run_status = RunStatus.RUNNING
    aggregate.run.completed_at = None
    aggregate.run.updated_at = now
    validate_control(aggregate)
    return receipt
