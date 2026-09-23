"""Version, readiness, orphan, reuse and finite-budget negative contracts."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from src.application.execution import IntegratedTaskExecutor
from src.application.repository import validate_root
from src.application.risk_replan import ReplanSuspended, admission_allowed, apply, control
from src.domain.node_binding import BindingDenied, OwnerToken
from tests.risk_replan.test_controls import act, pending
from tests.risk_replan.test_flow import fixture
from tests.risk_replan.test_recovery import resume


async def test_every_wait_state_denies_cached_synthesis_and_assurance(tmp_path):
    from src.application.closure_policy import classify_execution_closure

    service, value, _, _ = await pending(tmp_path)
    repo = service.repository
    stale = deepcopy(value)
    for action in (None, "DECLINE", "REOPEN", "APPROVE"):
        if action:
            await act(repo, value, action, action)
            value = await repo.get_run_fresh(value.run.run_id)
        task = value.runtime.task(value.run.run_id + ":synthesis")
        task.status = "READY"
        for dispatch in (False, True):
            with pytest.raises(ReplanSuspended):
                admission_allowed(value, task, dispatch=dispatch)
        assert not classify_execution_closure(value).reviewable
        assert not (await repo.replan_projection(value.run.run_id))["release_eligible"]
        if action:
            with pytest.raises(BindingDenied):
                await repo.save_run(stale)
    await repo.apply_replan(value.run.run_id)
    value = await repo.get_run_fresh(value.run.run_id)
    with pytest.raises(ReplanSuspended):
        admission_allowed(value, value.runtime.task(task.task_id), dispatch=False)
    assert not classify_execution_closure(value).reviewable


async def test_unknown_orphan_holds_apply_and_affected_consumer_fails(tmp_path):
    service, value, calls, _ = await pending(tmp_path)
    await act(service.repository, value, "APPROVE", "A")
    value = await service.repository.get_run_fresh(value.run.run_id)
    task_id = value.run.run_id + ":valuation"
    orphan = deepcopy(value)
    orphan.node_binding.attempts[task_id] = orphan.node_binding.attempts[task_id].model_copy(
        update={"status": "RESULT_UNKNOWN"}
    )
    with pytest.raises(
        BindingDenied, match="CONFIRMED_AUTHORITY_MISMATCH: current binding reference"
    ):
        await apply(service.repository, orphan)
    orphan.runtime.binding_ref = orphan.node_binding.reference()
    assert await apply(service.repository, orphan) is None
    assert orphan.node_binding.frozen_graph == value.node_binding.frozen_graph
    affected = deepcopy(value)
    affected.node_binding.attempts[value.run.run_id + ":synthesis"] = (
        affected.node_binding.attempts[task_id]
    )
    with pytest.raises(
        BindingDenied, match="CONFIRMED_AUTHORITY_MISMATCH: current binding reference"
    ):
        await apply(service.repository, affected)
    affected.runtime.binding_ref = affected.node_binding.reference()
    with pytest.raises(BindingDenied, match="AFFECTED_CONSUMER"):
        await apply(service.repository, affected)
    assert len(calls) == 3


async def test_reuse_certificates_and_child_admission_are_exact(tmp_path):
    service, value, _, _ = await pending(tmp_path)
    repo = service.repository
    await act(repo, value, "APPROVE", "A")
    await repo.apply_replan(value.run.run_id)
    owner = await repo.claim_execution(value.run.run_id)
    value = await repo.get_run_fresh(value.run.run_id)
    child = value.runtime.task(value.run.run_id + ":risk-follow-up")
    repo._current_dependencies(value, child)
    for field, replacement in [("reused_results", []), ("new_graph", {"version": 999})]:
        bad = deepcopy(value)
        bad.node_binding.replan["transition"][field] = replacement
        with pytest.raises((BindingDenied, ValidationError)):
            repo._current_dependencies(bad, child)
    cert = value.node_binding.replan["transition"]["reused_results"][0]
    for key in ("profile_digest", "task_fingerprint", "material_digests", "source_result_digest"):
        bad = deepcopy(value)
        bad.node_binding.replan["transition"]["reused_results"][0][key] = (
            ["wrong"] if key == "material_digests" else "wrong"
        )
        with pytest.raises((BindingDenied, ValidationError)):
            repo._current_dependencies(bad, child)
    req = IntegratedTaskExecutor(service, value).admission_requirements(child)
    await repo.reserve_node(owner, child, req)
    with pytest.raises(BindingDenied):
        await repo.reserve_node(owner, child, req)
    assert cert


async def test_selected_undispatched_recovery_retains_prior_budget(tmp_path):
    service, value, calls, transport = await fixture(
        tmp_path, failure_plan={("valuation_analysis", "gpt-5.6-sol"): ["timeout"]}
    )
    repo = service.repository
    original = repo.suspend_replan
    selected = []

    async def suspend(owner):
        current = await repo.get_run_fresh(owner.run_id)
        task = current.runtime.task(owner.run_id + ":valuation")
        prior = deepcopy(current.node_binding.attempts[task.task_id])
        token = OwnerToken(
            run_id=owner.run_id,
            owner_id=current.node_binding.owner_id,
            owner_generation=current.node_binding.owner_generation,
        )
        req = IntegratedTaskExecutor(service, current).admission_requirements(task)
        admission = await repo.reserve_node(token, task, req)
        selected.append((prior, admission))
        return await original(owner)

    repo.suspend_replan = suspend
    with transport:
        value = await service.execute_run(value.run.run_id)
    assert len(selected) == 1
    prior, admission = selected[0]
    await act(repo, value, "APPROVE", "A")
    transition = await repo.apply_replan(value.run.run_id)
    assert transition.carried_recovery[0].reservation_id == prior.admission.attempt_reservation_id
    with transport:
        await resume(service, value.run.run_id)
    final = await repo.get_run_fresh(value.run.run_id)
    assert final.node_binding.attempt_history[admission.attempt_reservation_id].status == "RESERVED"
    assert [m for k, m in calls if k == "valuation_analysis"] == ["gpt-5.6-sol", "gpt-5.6-terra"]


async def test_child_total_time_cannot_refill_on_resume(tmp_path):
    service, value, calls, transport = await pending(
        tmp_path, failure_plan={("risk_follow_up", "gpt-5.6-sol"): ["timeout"]}
    )
    repo = service.repository
    await act(repo, value, "APPROVE", "A")
    await repo.apply_replan(value.run.run_id)
    with transport:
        value = await service.execute_run(value.run.run_id)
    task_id = value.run.run_id + ":risk-follow-up"
    async with repo._binding_transaction(value.run.run_id) as current:
        attempt = current.node_binding.attempts[task_id]
        recovery = {**attempt.recovery, "elapsed": 180.0}
        current.node_binding.attempts[task_id] = attempt.model_copy(update={"recovery": recovery})
    with transport, pytest.raises(ExceptionGroup) as caught:
        await resume(service, value.run.run_id)
    assert any(
        isinstance(e, BindingDenied) and e.code == "RECOVERY_BUDGET_EXHAUSTED"
        for e in caught.value.exceptions
    )
    assert [m for k, m in calls if k == "risk_follow_up"] == ["gpt-5.6-sol"]


async def test_extension_codec_and_missing_agent(tmp_path):
    from src.domain.execution_profile import ScenarioProfile
    from src.domain.runtime_event import RuntimeEventType, validate_runtime_event_payload

    legacy = ScenarioProfile(task_categories=("risk_analysis",))
    assert "risk_follow_up_policy" not in legacy.model_dump(mode="json")
    with pytest.raises(ValidationError):
        ScenarioProfile.model_validate(
            {**legacy.model_dump(), "risk_follow_up_policy": {"unknown": 1}}
        )
    service, value, _, _ = await pending(tmp_path)
    old = value.node_binding.model_copy(update={"replan": None})
    assert "replan" not in old.model_dump(mode="json")
    for kind in RuntimeEventType:
        if kind.value.startswith("replan.") and kind not in {
            RuntimeEventType.REPLAN_REQUESTED,
            RuntimeEventType.REPLAN_APPROVED,
            RuntimeEventType.REPLAN_REJECTED,
        }:
            with pytest.raises(ValueError):
                validate_runtime_event_payload(kind, {})
    bad = deepcopy(value)
    bad.node_binding.replan["unknown"] = True
    with pytest.raises(
        BindingDenied, match="CONFIRMED_AUTHORITY_MISMATCH: current binding reference"
    ):
        validate_root(bad)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        control(bad)
    bad.runtime.binding_ref = bad.node_binding.reference()
    with pytest.raises(BindingDenied, match="CONFIRMED_AUTHORITY_MISMATCH: root/snapshot"):
        validate_root(bad)


@pytest.mark.parametrize("route", ["teamorouter-sol", "teamorouter-terra"])
@pytest.mark.parametrize("negative", ["UNAVAILABLE", "QUARANTINED", "UNSUPPORTED"])
async def test_child_negative_evidence_has_priority(tmp_path, route, negative):
    from src.application.execution_profiles import configured_agent, frozen_profile
    from src.domain.recovery import Capability, Health

    service, value, calls, transport = await pending(
        tmp_path, failure_plan={("risk_follow_up", "gpt-5.6-sol"): ["timeout"]}
    )
    repo = service.repository
    await act(repo, value, "APPROVE", "A")
    await repo.apply_replan(value.run.run_id)
    value = await repo.get_run_fresh(value.run.run_id)
    child = value.runtime.task(value.run.run_id + ":risk-follow-up")
    recovery = configured_agent(service, child, None)._recovery
    if negative == "UNAVAILABLE":
        recovery.initial_health[route] = Health.UNAVAILABLE
    else:
        profile = frozen_profile(value, child)
        model = "gpt-5.6-sol" if route.endswith("sol") else "gpt-5.6-terra"
        recovery.certifications[
            ("risk_follow_up", route, model, profile.accepted_request_proof.schema_digest)
        ] = Capability(negative)
    with transport:
        try:
            await service.execute_run(value.run.run_id)
        except (ExceptionGroup, BindingDenied):
            pass
    assert not any(
        k == "risk_follow_up" and m == ("gpt-5.6-sol" if route.endswith("sol") else "gpt-5.6-terra")
        for k, m in calls
    )
    current = await repo.get_run_fresh(value.run.run_id)
    assert control(current).finalization is None


async def test_missing_child_agent_cannot_publish_supporting_success(tmp_path):
    from src.agentic.registry import AgentRegistry

    service, value, calls, transport = await pending(tmp_path)
    repo = service.repository
    await act(repo, value, "APPROVE", "A")
    await repo.apply_replan(value.run.run_id)
    service.agent_registry = AgentRegistry()
    with transport:
        try:
            await service.execute_run(value.run.run_id)
        except (ExceptionGroup, BindingDenied):
            pass
    current = await repo.get_run_fresh(value.run.run_id)
    assert control(current).finalization is None
    assert not any(k == "risk_follow_up" for k, m in calls)


async def test_new_confirm_requires_independent_configuration_and_selection(tmp_path):
    from src.application.risk_replan_profile import freeze_child_template

    service, value, _, _ = await fixture(tmp_path)
    task = value.runtime.task(value.run.run_id + ":risk")
    agent = service.agent_registry.get("risk_analyst")
    original = agent._recovery.clients.pop("teamorouter-terra")
    with pytest.raises((BindingDenied, ValueError)):
        freeze_child_template(service, value.scheme, value.goal, task)
    agent._recovery.clients["teamorouter-terra"] = original
    goal = value.goal.model_copy(deep=True)
    goal.preferences["model_selection"] = {"route_id": "teamorouter-terra"}
    with pytest.raises((BindingDenied, ValueError)):
        freeze_child_template(service, value.scheme, goal, task)
