"""One minimal-V1 decision owner shared by publication and authority consumers."""

from pydantic import ValidationError

from src.domain.agent_output import RiskResearchAgentStructuredOutputMinimalV1
from src.domain.evidence import risk_input_consistency_guard_v1
from src.domain.node_binding import (
    BindingDenied,
    canonical_value,
    check_value_identity,
    digest,
    task_fingerprint,
)
from src.domain.risk_admission import contract_for


def derive(aggregate, admission, records, resolved_ids, *, fulfillment=None):
    return _derive(aggregate, admission, records, resolved_ids,
                   contract=contract_for(aggregate), fulfillment=fulfillment)


def _derive(aggregate, admission, records, resolved_ids, *, contract, fulfillment=None):
    # Private synchronous continuation of a gated call, never a persisted/cached authority.
    if contract is None or admission.task_id != contract["task_id"]:
        return None
    root = aggregate.node_binding
    task = aggregate.runtime.task(admission.task_id)
    check_value_identity(admission, "admission_binding_id")
    if (
        admission.run_id != root.run_id
        or admission.object_id != aggregate.run.research_object_id
        or admission.task_fingerprint != task_fingerprint(task)
        or admission.policy_refs.get("risk_semantic_contract") != contract
    ):
        raise BindingDenied("RISK_ADMISSION_SCOPE_MISMATCH")
    from src.application.resume_runtime import validate_cycle_admission

    validate_cycle_admission(aggregate, admission)
    scope = {
        "run_id": root.run_id,
        "task_id": task.task_id,
        "object_id": admission.object_id,
        "graph": canonical_value(admission.graph),
        "cycle": admission.policy_refs.get("external_resume_cycle", "INITIAL"),
        "owner": canonical_value(admission.owner),
        "reservation_id": admission.attempt_reservation_id,
        "admission_binding_id": admission.admission_binding_id,
    }
    candidates = [
        r
        for r in records
        if r.kind == "AGENT_OUTPUT" and r.payload_snapshot.get("task_id") == task.task_id
    ]
    if len(candidates) != 1:
        raise BindingDenied("RISK_CANDIDATE_CARDINALITY")
    candidate = candidates[0]
    decision = "CONTRACT_REJECTED"
    diagnostics = []
    guard = None
    closure = None
    steps = [root.resolved_inputs[key] for key in resolved_ids]
    contexts = [s for s in steps if s.step_id == "agent-context"]
    if len(contexts) != 1:
        raise BindingDenied("RISK_INPUT_BINDING_REQUIRED")
    bound = contexts[0]
    for step in steps:
        check_value_identity(step, "resolved_input_binding_id")
        if (
            step.admission_binding_id != admission.admission_binding_id
            or step.reservation_id != admission.attempt_reservation_id
            or step.input_digest != digest(step.payload_snapshot, "wp02-input-payload/v1")
        ):
            raise BindingDenied("RISK_INPUT_BINDING_MISMATCH")
    try:
        parsed = RiskResearchAgentStructuredOutputMinimalV1.model_validate(
            candidate.payload_snapshot.get("structured_output")
        )
        if candidate.payload_snapshot.get("status") != "SUCCESS":
            raise BindingDenied("RISK_CANDIDATE_SCHEMA_REJECTED")
        if canonical_value(task.output_requirements) != contract["requirements"]:
            raise BindingDenied("RISK_REQUIREMENTS_MISMATCH")
        obligations = set(contract["obligation_refs"])
        if len(parsed.evidence_gap_refs) > 3 * len(obligations) or any(
            g.requirement_ref not in obligations for g in parsed.evidence_gap_refs
        ):
            raise BindingDenied("RISK_GAP_REF_REJECTED")
        available = set()
        unqualified = set()
        allowed = {}
        for dependency in admission.dependency_result_bindings:
            producer = root.results.get(dependency.result_id)
            if (
                producer is None
                or producer.dependency() != dependency
                or root.current_results.get(dependency.producer_task_id) != producer.result_id
                or producer.result_id in root.invalidation_refs
            ):
                raise BindingDenied("RISK_CLOSURE_STALE")
            check_value_identity(producer, "result_digest", "result_id")
            attempt = root.attempts.get(producer.producer_task_id)
            if (
                attempt is None
                or attempt.admission.admission_binding_id != producer.admission_binding_id
                or attempt.status != "COMMITTED"
            ):
                raise BindingDenied("RISK_CLOSURE_UNVERIFIABLE")
            for record in producer.output_records:
                if digest(record.payload_snapshot, record.record_schema) != record.content_digest:
                    raise BindingDenied("RISK_CLOSURE_CORRUPT")
                if record.record_id in allowed and allowed[record.record_id] != record:
                    raise BindingDenied("RISK_MATERIAL_ID_COLLISION")
                allowed[record.record_id] = record
            snapshots = [r for r in producer.output_records if r.kind == "TASK_OUTPUT_SNAPSHOT"]
            if len(snapshots) != 1:
                raise BindingDenied("RISK_CLOSURE_UNVERIFIABLE")
            for output in snapshots[0].payload_snapshot["output_outcomes"]:
                refs = output["refs"]
                output_ref = producer.producer_task_id + "/" + output["output_id"]
                if output["status"] in {"INSUFFICIENT_EVIDENCE", "INSUFFICIENT_DATA"}:
                    unqualified.add(output_ref)
                if output["status"] == "COMPLETED" and refs:
                    if not all(ref in allowed for ref in refs):
                        raise BindingDenied("RISK_CLOSURE_UNVERIFIABLE")
                    if all(
                        allowed[ref].kind != "CALCULATION_CORE"
                        or allowed[ref].payload_snapshot["status"] == "PASS"
                        for ref in refs
                    ):
                        available.add(output_ref)
                    else:
                        unqualified.add(output_ref)
        for record in bound.material_refs:
            if allowed.get(record.record_id) != record:
                raise BindingDenied("RISK_PRODUCER_LINEAGE_REQUIRED", record.record_id)
            if record.kind == "EVIDENCE" and (
                record.payload_snapshot["run_id"] != root.run_id
                or record.payload_snapshot["object_id"] != admission.object_id
                or record.payload_snapshot["status"] != "ACCEPTED"
            ):
                raise BindingDenied("RISK_EVIDENCE_UNQUALIFIED")
        from src.domain.output_dependency import evidence_sufficiency

        closure = canonical_value(evidence_sufficiency(task.output_requirements, available))
        missing = obligations - available
        for gap in parsed.evidence_gap_refs:
            if gap.reason_code == "REQUIRED_OUTPUT_MISSING" and gap.requirement_ref not in missing:
                raise BindingDenied("RISK_GAP_DIAGNOSTIC_MISMATCH")
            if (
                gap.reason_code == "REQUIRED_EVIDENCE_UNQUALIFIED"
                and gap.requirement_ref not in unqualified
            ):
                raise BindingDenied("RISK_GAP_DIAGNOSTIC_MISMATCH")
        guard = risk_input_consistency_guard_v1(
            materials=bound.material_refs,
            binding_id=bound.resolved_input_binding_id,
            input_digest=bound.input_digest,
            policy=contract["policy"],
            scope=scope,
        )
        if (
            parsed.business_outcome == "INSUFFICIENT_EVIDENCE"
            or closure["missing_required"]
            or guard["input_consistency"] != "PASS"
        ):
            decision = "EVIDENCE_INSUFFICIENT"
        elif parsed.requires_follow_up and fulfillment is None:
            from src.application.risk_replan import frozen_policy

            frozen_policy(aggregate)
            decision = "FOLLOW_UP_PENDING"
        else:
            decision = "FINAL_SUCCESS"
    except ValidationError:
        diagnostics.append("RISK_CANDIDATE_SCHEMA_REJECTED")
    except BindingDenied as exc:
        diagnostics.append(exc.code)
    value = {
        "version": "risk_admission_minimal_v1",
        "scope": scope,
        "contract_digest": contract["contract_digest"],
        "requirements_digest": digest(contract["requirements"], "risk-requirements/v1"),
        "candidate_output_id": candidate.record_id,
        "candidate_content_digest": candidate.content_digest,
        "candidate_artifact_digest": candidate.payload_snapshot["artifact_sha256"],
        "resolved_input_binding_id": bound.resolved_input_binding_id,
        "input_digest": bound.input_digest,
        "decision": decision,
        "guard": guard,
        "closure": closure,
        "diagnostics": diagnostics,
        "fulfillment": fulfillment,
    }
    return {**value, "receipt_digest": digest(value, "risk-admission-receipt/v1")}


def require_final(aggregate, result):
    return _require_final(aggregate, result, contract_for(aggregate))


def _require_final(aggregate, result, contract):
    if contract is None or result.producer_task_id != contract["task_id"]:
        return
    root = aggregate.node_binding
    attempt = root.attempts.get(result.producer_task_id)
    receipt = (root.risk_admissions or {}).get(result.admission_binding_id)
    if (
        attempt is None
        or receipt is None
        or receipt["decision"] != "FINAL_SUCCESS"
        or result.reservation_id != attempt.admission.attempt_reservation_id
        or result.graph != root.frozen_graph
        or result.result_id in root.invalidation_refs
        or result.observed_execution.get("risk_admission_digest") != receipt["receipt_digest"]
    ):
        raise BindingDenied("RISK_FINAL_ADMISSION_REQUIRED")
    if result.finalization_binding is not None and (
        root.replan is None or root.replan.get("finalization") != result.finalization_binding
    ):
        raise BindingDenied("RISK_FINAL_ADMISSION_STALE")
    check_value_identity(result, "result_digest", "result_id")
    verify_selected_bytes(aggregate, result)
    expected = _derive(
        aggregate,
        attempt.admission,
        result.output_records,
        result.resolved_input_binding_ids,
        contract=contract, fulfillment=result.finalization_binding,
    )
    if expected != receipt:
        raise BindingDenied("RISK_FINAL_ADMISSION_STALE")


def nonfinal_task(aggregate):
    """Only a current, rederived D01 receipt can settle Risk as non-final.

    Follow-up candidates retain their existing governed Replan path. Local
    output outcomes and diagnostic strings never grant settlement authority.
    """
    return _nonfinal_task(aggregate, contract_for(aggregate))


def _nonfinal_task(aggregate, contract):
    if contract is None:
        return None
    task_id = contract["task_id"]
    if aggregate.runtime.task(task_id).task_type != "risk_analysis":
        raise BindingDenied("RISK_ADMISSION_SCOPE_MISMATCH")
    root = aggregate.node_binding
    attempt = root.attempts.get(task_id)
    receipt = ((root.risk_admissions or {}).get(attempt.admission.admission_binding_id)
               if attempt else None)
    if receipt is None or receipt["decision"] not in {
        "EVIDENCE_INSUFFICIENT", "CONTRACT_REJECTED"
    }:
        return None
    results = [result for result in root.results.values()
               if result.admission_binding_id == attempt.admission.admission_binding_id]
    if attempt.status != "COMMITTED" or len(results) != 1:
        raise BindingDenied("RISK_NONFINAL_ADMISSION_STALE")
    result = results[0]
    if (
        result.producer_task_id != task_id
        or result.run_id != root.run_id
        or result.reservation_id != attempt.admission.attempt_reservation_id
        or result.graph != root.frozen_graph
        or result.result_id in root.invalidation_refs
        or result.owner_generation != attempt.admission.owner.owner_generation
        or result.producer_owner != attempt.admission.owner.owner_id
        or result.observed_execution.get("risk_admission_digest") != receipt["receipt_digest"]
    ):
        raise BindingDenied("RISK_NONFINAL_ADMISSION_STALE")
    check_value_identity(result, "result_digest", "result_id")
    verify_selected_bytes(aggregate, result)
    if _derive(aggregate, attempt.admission, result.output_records,
               result.resolved_input_binding_ids, contract=contract) != receipt:
        raise BindingDenied("RISK_NONFINAL_ADMISSION_STALE")
    return task_id


def final_current_results(aggregate):
    return _final_current_results(aggregate, contract_for(aggregate))


def _final_current_results(aggregate, contract):
    root = aggregate.node_binding
    values = dict(root.current_results)
    if contract and contract["task_id"] in values:
        _require_final(aggregate, root.results[values[contract["task_id"]]], contract)
    return values


def dependency_state(aggregate):
    # One synchronous read: no mutation or await between the gate and its consumers.
    contract = contract_for(aggregate)
    return (_final_current_results(aggregate, contract), contract,
            _nonfinal_task(aggregate, contract))


def verify_selected_bytes(aggregate, result):
    """Synchronous authority readers verify exact bytes; SQL owners also check rows."""
    import hashlib
    from pathlib import Path

    root = aggregate.node_binding
    records = list(result.output_records)
    for key in result.resolved_input_binding_ids:
        bound = root.resolved_inputs.get(key)
        if bound is None or bound.admission_binding_id != result.admission_binding_id:
            raise BindingDenied("RISK_INPUT_BINDING_MISMATCH")
        check_value_identity(bound, "resolved_input_binding_id")
        records.extend(bound.material_refs)
    for record in records:
        if digest(record.payload_snapshot, record.record_schema) != record.content_digest:
            raise BindingDenied("RISK_MATERIAL_CORRUPT")
        if record.kind in {"EVIDENCE", "AGENT_OUTPUT"}:
            field = "snapshot_hash" if record.kind == "EVIDENCE" else "artifact_sha256"
            try:
                actual = "sha256:" + hashlib.sha256(Path(record.location).read_bytes()).hexdigest()
            except OSError as exc:
                raise BindingDenied("RISK_MATERIAL_MISSING") from exc
            if actual.removeprefix("sha256:") != record.payload_snapshot[field].removeprefix(
                "sha256:"
            ):
                raise BindingDenied("RISK_MATERIAL_CORRUPT")


def projection(aggregate):
    contract = contract_for(aggregate)
    if contract is None:
        return None
    final_current_results(aggregate)
    root = aggregate.node_binding
    attempt = root.attempts.get(contract["task_id"])
    receipt = (
        (root.risk_admissions or {}).get(attempt.admission.admission_binding_id)
        if attempt
        else None
    )
    return {
        "schema_version": "risk-admission-projection/v1",
        "run_id": root.run_id,
        "task_id": contract["task_id"],
        "profile": contract["policy"]["profile"],
        "decision": receipt["decision"] if receipt else None,
        "receipt_digest": receipt["receipt_digest"] if receipt else None,
        "current_final": contract["task_id"] in root.current_results,
        "diagnostics": receipt["diagnostics"] if receipt else [],
        "input_consistency": receipt["guard"]["input_consistency"]
        if receipt and receipt["guard"]
        else None,
    }


class RiskResultReplay(Exception):
    """Exit the owning transaction without any write or revision/budget consumption."""

    def __init__(self, result):
        self.result = result
