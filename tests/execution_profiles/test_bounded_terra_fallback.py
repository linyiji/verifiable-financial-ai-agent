"""Versioned bounded proof adoption and same-node recovery; zero external calls."""

import asyncio
import json
from pathlib import Path

import pytest

from src.adapters.llm.provider import LLMFailureClassification as Code
from src.agentic.research_agent import _messages
from src.application import execution_profiles as profiles
from src.application.execution import IntegratedTaskExecutor
from src.application.persistence import SQLAlchemyApplicationRepository as Repository
from src.domain.agent_output import (
    RiskResearchAgentStructuredOutput,
    StandardResearchAgentStructuredOutput,
)
from src.domain.execution_profile import ExecutionSnapshot
from src.domain.node_binding import BindingDenied
from src.domain.recovery import Capability, Health, Scope
from src.phase4_product.hashing import canonical_json_sha256 as digest
from tests.execution_profiles.fallback_fixture import configured_family
from tests.unit.agentic.test_adaptive_recovery import context

KINDS = ("risk_analysis", "valuation_analysis")


def bound(value):
    task = value.runtime.actual_graph.tasks[1]
    return task, profiles.frozen_profile(value, task)


def request_scope(task):
    ctx = context(task)
    model = (
        RiskResearchAgentStructuredOutput
        if task.task_type == "risk_analysis"
        else StandardResearchAgentStructuredOutput
    )
    request = dict(
        messages=_messages(ctx),
        response_model=model,
        schema_name=f"{task.task_type}_research_output_v1",
        workload_type="RESEARCH_AGENT_EXECUTION",
    )
    scope = Scope(
        run_id=task.run_id,
        task_id=task.task_id,
        object_id="OBJ-local",
        scheme_id="SCHEME-local",
        task_profile=task.task_type,
        agent_id=task.assigned_agent,
        context_hash=digest(ctx.model_dump(mode="json")),
        contract_hash=digest(model.model_json_schema()),
    )
    return ctx, scope, request


@pytest.mark.parametrize("kind", KINDS)
async def test_new_profiles_and_frozen_defaults(tmp_path, kind, monkeypatch):
    service, value, _, _ = await configured_family(tmp_path, kind)
    task, p = bound(value)
    assert p.profile_version == "2" and p.resolved_route == "teamorouter-sol"
    assert p.allowed_model_routes == ("teamorouter-sol", "teamorouter-terra")
    assert p.recovery_fallback_routes == ("teamorouter-terra",)
    assert p.recovery_budget.max_capability_checks == 0
    assert p.owner_policy == profiles.TASK_POLICIES[kind]
    old_budget = p.owner_policy.recovery_budget.model_dump()
    old_budget["max_capability_checks"] = 0
    assert p.recovery_budget.model_dump() == old_budget
    monkeypatch.setattr(profiles, "default_recovery_profile", lambda p: p)
    monkeypatch.setattr(profiles, "accepted_terra_proof", lambda _: None)
    fresh = Repository._to_aggregate(json.loads(json.dumps(Repository._payload(value))))
    assert profiles.validate_runtime_profile(service, fresh, task) == p
    recovery = profiles.recovery_for(profiles.configured_agent(service, task, None))
    ctx, scope, request = request_scope(task)
    assert profiles.adopted_request_matches(
        p, ctx, scope, recovery.detector.routes["teamorouter-terra"], request
    )


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "field,wrong",
    [
        ("schema_digest", "sha256:wrong"),
        ("schema_name", "valuation_context_turn_v1"),
        ("schema_identity", "ValuationTurn"),
        ("task_type", "peer_analysis"),
        ("skill_id", "other_v1"),
        ("model", "gpt-5.6-luna"),
        ("route", "teamorouter-luna"),
        ("provider", "mimo"),
        ("valuation_context_enabled", True),
        ("builder_digest", "sha256:changed"),
        ("template_digest", "sha256:changed"),
        ("request_builder", "another/v1"),
        ("status", "STALE"),
        ("status", "REVOKED"),
        ("profile_version", "1"),
        ("receipt_id", "REC-unaccepted"),
        ("receipt_content_digest", "sha256:tampered"),
        ("attempt_id", "ATT-unaccepted"),
        ("adoption_version", "old/v0"),
    ],
)
async def test_proof_binding_rejects_mismatch(tmp_path, kind, field, wrong):
    service, value, _, _ = await configured_family(tmp_path, kind)
    task, p = bound(value)
    recovery = profiles.recovery_for(profiles.configured_agent(service, task, None))
    ctx, scope, request = request_scope(task)
    candidate = recovery.detector.routes["teamorouter-terra"]
    assert profiles.adopted_request_matches(p, ctx, scope, candidate, request)
    changed = p.model_copy(
        update={
            "accepted_request_proof": p.accepted_request_proof.model_copy(update={field: wrong})
        }
    )
    assert not profiles.adopted_request_matches(changed, ctx, scope, candidate, request)
    with pytest.raises(BindingDenied, match="PROFILE_PROOF_ADOPTION_DENIED"):
        profiles.narrow_profile(
            p,
            changed,
            ExecutionSnapshot.model_validate(value.node_binding.execution_snapshot).scenario,
        )


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "wrong_context",
        "wrong_schema",
        "wrong_messages",
        "wrong_node",
        "unauthorized",
        "extra_request",
    ],
)
async def test_request_and_authorization_are_independent(tmp_path, kind, case):
    service, value, _, _ = await configured_family(tmp_path, kind)
    task, p = bound(value)
    recovery = profiles.recovery_for(profiles.configured_agent(service, task, None))
    ctx, scope, request = request_scope(task)
    candidate = recovery.detector.routes["teamorouter-terra"]
    if case == "missing":
        p = p.model_copy(update={"accepted_request_proof": None})
    if case == "wrong_context":
        p = p.model_copy(
            update={"runtime_configuration": {**p.runtime_configuration, "valuation_context": True}}
        )
    if case == "wrong_schema":
        request["schema_name"] = "valuation_context_turn_v1"
    if case == "wrong_messages":
        request["messages"] = []
    if case == "wrong_node":
        scope = scope.model_copy(update={"task_profile": "peer_analysis"})
    if case == "unauthorized":
        candidate = candidate.model_copy(update={"authority_exists": False})
    if case == "extra_request":
        request["reasoning_effort"] = "medium"
    if case == "wrong_context" and kind == "risk_analysis":
        assert profiles.adopted_request_matches(p, ctx, scope, candidate, request)
    else:
        assert not profiles.adopted_request_matches(p, ctx, scope, candidate, request)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("symbol", ["ALPHA", "BETA"])
async def test_same_node_terra_selection_and_result(tmp_path, kind, symbol):
    service, value, collector, clients = await configured_family(tmp_path, kind, symbol=symbol)
    task, p = bound(value)
    pending = await service.execute_run(value.run.run_id)
    a = pending.node_binding
    assert a.lifecycle == "RECOVERY_PENDING"
    failed = a.attempts[task.task_id]
    assert failed.status == "FAILED" and failed.generation == 1
    assert len(a.current_results) == 1
    result = await service.execute_run(value.run.run_id)
    b = result.node_binding
    success = b.attempts[task.task_id]
    assert result.run.run_id == value.run.run_id
    assert success.status == "COMMITTED" and success.generation == 2
    assert success.admission.task_id == failed.admission.task_id
    assert success.admission.task_fingerprint == failed.admission.task_fingerprint
    assert success.admission.graph == failed.admission.graph
    assert (
        success.admission.dependency_result_bindings == failed.admission.dependency_result_bindings
    )
    assert success.admission.attempt_reservation_id != failed.admission.attempt_reservation_id
    assert b.frozen_graph == a.frozen_graph
    assert b.execution_snapshot == a.execution_snapshot
    assert b.attempt_history[failed.admission.attempt_reservation_id] == failed
    assert len(b.current_results) == 2 and collector.calls == 1
    assert all(b.results[key] == val for key, val in a.results.items())
    assert {key: c.calls for key, c in clients.items()} == {
        "teamorouter-sol": 1,
        "teamorouter-terra": 1,
        "teamorouter-luna": 0,
        "mimo-direct": 0,
    }
    rows = await service.recovery_evidence_store.records()
    starts = [r for r in rows if r.kind == "ATTEMPT_STARTED"]
    assert [r.route for r in starts] == ["teamorouter-sol", "teamorouter-terra"]
    assert all(not r.capability_check for r in starts)
    assert starts[0].scope == starts[1].scope
    assert sum(r.kind == "ATTEMPT_COMPLETED" and r.outcome == "PASS" for r in rows) == 1
    assert profiles.frozen_profile(result, task) == p


@pytest.mark.parametrize("kind", KINDS)
async def test_sol_success_never_calls_fallback(tmp_path, kind):
    service, value, _, clients = await configured_family(tmp_path, kind, failures=())
    await service.execute_run(value.run.run_id)
    assert clients["teamorouter-sol"].calls == 1
    assert sum(c.calls for k, c in clients.items() if k != "teamorouter-sol") == 0


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "case", ["terminal", "unavailable", "quarantine", "missing_proof", "registry_only"]
)
async def test_no_fallback_and_terminal_semantics(tmp_path, kind, case):
    service, value, _, clients = await configured_family(tmp_path, kind, persist=False)
    task, p = bound(value)
    recovery = profiles.recovery_for(profiles.configured_agent(service, task, None))
    if case == "terminal":
        clients["teamorouter-terra"].failures = [Code.REQUEST_REJECTED]
    if case == "unavailable":
        recovery.initial_health["teamorouter-terra"] = Health.UNAVAILABLE
    if case == "quarantine":
        recovery.certifications[
            (kind, "teamorouter-terra", "gpt-5.6-terra", p.accepted_request_proof.schema_digest)
        ] = Capability.QUARANTINED
    if case == "registry_only":
        recovery.certifications[(kind, "teamorouter-terra", "gpt-5.6-terra",
                                 p.accepted_request_proof.schema_digest)] = Capability.VERIFIED
    if case in {"missing_proof", "registry_only"}:
        snap = ExecutionSnapshot.model_validate(value.node_binding.execution_snapshot)
        nodes = tuple(
            n.model_copy(
                update={"profile": n.profile.model_copy(update={"accepted_request_proof": None})}
            )
            if n.task_id == task.task_id
            else n
            for n in snap.nodes
        )
        snap = ExecutionSnapshot.freeze(snap.scenario, nodes)
        value.node_binding.execution_snapshot = snap.model_dump(mode="json")
        value.node_binding.execution_profile_snapshot_digest = (
            snap.execution_profile_snapshot_digest
        )
    from src.domain.research_object import ResearchObject

    await service.repository.add_object(
        ResearchObject(
            object_id="OBJECT-WP02", symbol="ALPHA", company_name="Local", exchange="LOCAL"
        )
    )
    await service.repository.add_run(value)
    if case == "terminal":
        pending = await service.execute_run(value.run.run_id)
        assert pending.node_binding.lifecycle == "RECOVERY_PENDING"
    with pytest.raises(ExceptionGroup):
        await service.execute_run(value.run.run_id)
    fresh = await service.repository.get_run_fresh(value.run.run_id)
    assert fresh.node_binding.lifecycle != "RECOVERY_PENDING"
    assert len(fresh.node_binding.current_results) == 1
    with pytest.raises(BindingDenied):
        await service.execute_run(value.run.run_id)
    assert clients["teamorouter-luna"].calls == clients["mimo-direct"].calls == 0
    assert clients["teamorouter-terra"].calls == (1 if case == "terminal" else 0)


@pytest.mark.parametrize("kind", KINDS)
async def test_one_active_attempt_and_stale_admission(tmp_path, kind):
    service, value, _, _ = await configured_family(tmp_path, kind)
    pending = await service.execute_run(value.run.run_id)
    task, _ = bound(pending)
    prior = pending.node_binding.attempts[task.task_id].admission
    owners = await asyncio.gather(
        *(service.repository.claim_execution(value.run.run_id) for _ in range(2)),
        return_exceptions=True,
    )
    assert sum(isinstance(v, BindingDenied) for v in owners) == 1
    owner = next(v for v in owners if not isinstance(v, BaseException))
    requirements = IntegratedTaskExecutor(service, pending).admission_requirements(task)
    reservations = await asyncio.gather(
        *(service.repository.reserve_node(owner, task, requirements) for _ in range(2)),
        return_exceptions=True,
    )
    assert sum(isinstance(v, BindingDenied) for v in reservations) == 1
    with pytest.raises(BindingDenied):
        await service.repository.dispatch_node(prior)


@pytest.mark.parametrize("kind", KINDS)
async def test_context_path_keeps_old_envelope_and_guard(tmp_path, kind):
    service, value, _, _ = await configured_family(tmp_path, kind)
    service.valuation_context_enabled = True
    result = profiles.resolve_execution_snapshot(
        value.scheme, value.goal, value.runtime.actual_graph.tasks, service
    )
    task, _ = bound(value)
    p = result.for_task(task)
    if kind == "risk_analysis":
        assert p.accepted_request_proof is not None
        assert p.recovery_fallback_routes == ("teamorouter-terra",)
    if kind == "valuation_analysis":
        assert p.accepted_request_proof is None
        assert p.allowed_model_routes == profiles.TASK_POLICIES[kind].candidates
        from src.agentic.valuation_context import validate_composition

        with pytest.raises(BindingDenied, match="WP03_UNSUPPORTED_RECOVERY_COMPOSITION"):
            validate_composition(profiles.configured_agent(service, task, None), task)


def test_historical_snapshot_codec():
    paths = list(Path(__file__).with_name("fixtures").glob("fallback_v1_*.json"))
    assert len(paths) == 2
    for path in paths:
        raw = json.loads(path.read_text())
        snap = ExecutionSnapshot.model_validate(raw)
        assert snap.model_dump(mode="json") == raw
        assert snap.model_dump_json(indent=2) + "\n" == path.read_text()
        assert all(n.profile.accepted_request_proof is None for n in snap.nodes)
        assert snap.nodes[1].profile.allowed_model_routes == (
            "teamorouter-sol",
            "teamorouter-luna",
            "teamorouter-terra",
            "mimo-direct",
        )


@pytest.mark.parametrize("kind", KINDS)
async def test_old_confirm_and_pending_decision_survive(tmp_path, kind):
    from src.application.repository import initialize_binding
    from src.domain.research_object import ResearchObject

    service, value, _, clients = await configured_family(tmp_path, kind, persist=False)
    raw = Path(__file__).with_name("fixtures").joinpath(f"fallback_v1_{kind}.json").read_text()
    snap = ExecutionSnapshot.model_validate_json(raw)
    value.node_binding = None
    initialize_binding(value, snapshot=snap)
    task, old = bound(value)
    assert old.profile_version == "1"
    assert profiles.validate_runtime_profile(service, value, task) == old
    await service.repository.add_object(
        ResearchObject(
            object_id="OBJECT-WP02",
            symbol="ALPHA",
            company_name="Local",
            exchange="LOCAL",
        )
    )
    await service.repository.add_run(value)
    pending = await service.execute_run(value.run.run_id)
    assert pending.node_binding.lifecycle == "RECOVERY_PENDING"
    before = json.loads(json.dumps(Repository._payload(pending)))
    restored = Repository._to_aggregate(before)
    assert json.loads(json.dumps(Repository._payload(restored))) == before
    assert profiles.frozen_profile(restored, task) == old
    result = await service.execute_run(value.run.run_id)
    assert result.node_binding.execution_snapshot == json.loads(raw)
    assert clients["teamorouter-luna"].calls == 2  # old UNKNOWN check + execution unchanged
    assert clients["teamorouter-terra"].calls == 0


@pytest.mark.parametrize("kind", KINDS)
async def test_late_quarantine_blocks_saved_terra_decision(tmp_path, kind):
    from datetime import UTC, datetime
    from uuid import uuid4

    from src.domain.recovery import FailureClass

    service, value, _, clients = await configured_family(tmp_path, kind)
    pending = await service.execute_run(value.run.run_id)
    assert pending.node_binding.lifecycle == "RECOVERY_PENDING"
    store = service.recovery_evidence_store
    rows = await store.records()
    start = next(r for r in rows if r.kind == "ATTEMPT_STARTED")
    scope = start.scope.model_copy(update={"run_id": "RUN-other", "task_id": "RUN-other:task"})
    check = start.model_copy(
        update={
            "record_id": "REC-" + str(uuid4()),
            "attempt_id": "ATT-other",
            "execution_policy": None,
            "scope": scope,
            "timestamp": datetime.now(UTC).isoformat(),
            "route": "teamorouter-terra",
            "model": "gpt-5.6-terra",
            "requested_model": "gpt-5.6-terra",
            "capability_check": True,
        }
    )
    await store.append(check)
    await store.append(
        check.model_copy(
            update={
                "record_id": "REC-" + str(uuid4()),
                "kind": "ATTEMPT_COMPLETED",
                "outcome": "FAIL",
                "failure_class": FailureClass.MODEL_IDENTITY_MISMATCH,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
    )
    with pytest.raises(ExceptionGroup):
        await service.execute_run(value.run.run_id)
    assert clients["teamorouter-terra"].calls == 0
    assert clients["teamorouter-luna"].calls == clients["mimo-direct"].calls == 0


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("failure", [None, "400"])
async def test_sol_terra_transport_and_rejection_retained(tmp_path, kind, failure):
    from tests.execution_profiles.fallback_transport_fixture import physical_fixture

    rows = await physical_fixture(tmp_path, kind, terra_failure=failure)
    completed = [r for r in rows if r.kind == "ATTEMPT_COMPLETED"]
    assert len(completed) == 2
    sol, terra = completed
    assert sol.transport_evidence.proxy_connect_http_status == 200
    assert sol.transport_evidence.provider_http_status is None
    assert sol.transport_evidence.target_body_completed is True
    assert sol.safe_failure.dispatch_state == "DISPATCHED"
    assert terra.transport_evidence.proxy_connect_http_status == 200
    assert terra.transport_evidence.provider_http_status == (400 if failure else 200)
    if failure:
        assert terra.safe_failure.provider_rejection.provider_error_code_numeric == 400
        assert terra.safe_failure.dispatch_state == "DISPATCHED"
    assert "SENTINEL_SECRET" not in json.dumps([r.model_dump(mode="json") for r in rows])
