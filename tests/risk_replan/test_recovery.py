"""Exact child proof, local failures, finite attempts and candidate request reconciliation."""

import asyncio
from copy import deepcopy

import pytest

from src.application.execution import IntegratedTaskExecutor
from src.application.execution_profiles import frozen_profile
from src.application.risk_replan import control
from src.runtime.scheduler import DependencyScheduler
from tests.risk_replan.test_controls import act, pending


async def resume(service, run_id):
    owner = await service.repository.claim_execution(run_id)
    value = await service.repository.get_run_fresh(run_id)
    return await DependencyScheduler(
        event_store=service.event_store,
        checkpoint_store=service.checkpoint_store,
        admission_repository=service.repository,
        execution_owner=owner,
    ).execute(state=value.runtime, executor=IntegratedTaskExecutor(service, value))


@pytest.mark.parametrize("failure", ["timeout"])
async def test_child_sol_failure_terra_only_restart(tmp_path, failure):
    plan = {("risk_follow_up", "gpt-5.6-sol"): [failure]}
    service, value, calls, transport = await pending(tmp_path, failure_plan=plan)
    repo = service.repository
    await act(repo, value, "APPROVE", "A")
    await repo.apply_replan(value.run.run_id)
    with transport:
        # Production service records the known failure and returns RECOVERY_PENDING.
        value = await service.execute_run(value.run.run_id)
        assert value.node_binding.lifecycle == "RECOVERY_PENDING"
        child = value.runtime.task(value.run.run_id + ":risk-follow-up")
        profile = frozen_profile(value, child)
        prior = deepcopy(value.node_binding.attempts[child.task_id])
        await resume(service, value.run.run_id)
    final = await repo.get_run_fresh(value.run.run_id)
    attempt = final.node_binding.attempts[child.task_id]
    assert attempt.status == "COMMITTED" and attempt.generation == 2
    assert attempt.admission.graph == prior.admission.graph == final.node_binding.frozen_graph
    assert final.node_binding.attempt_history[prior.admission.attempt_reservation_id] == prior
    assert frozen_profile(final, child) == profile
    assert [model for kind, model in calls if kind == "risk_follow_up"] == [
        "gpt-5.6-sol",
        "gpt-5.6-terra",
    ]
    assert control(final).finalization is not None
    rows = await service.recovery_evidence_store.records(value.run.run_id, child.task_id)
    assert len([r for r in rows if r.kind == "ATTEMPT_STARTED"]) == 2
    assert not any(r.kind == "CAPABILITY_CHECK_STARTED" for r in rows)
    assert all(r.route not in {"teamorouter-luna", "mimo-direct"} for r in rows)
    assert profile.recovery_budget.max_total_recovery_time == 180
    assert prior.recovery["elapsed"] > 0


@pytest.mark.parametrize("failure", ["400numeric", "400string"])
async def test_child_terminal_failure_keeps_risk_incomplete_and_safe_evidence(tmp_path, failure):
    plan = {
        ("risk_follow_up", "gpt-5.6-sol"): ["timeout"],
        ("risk_follow_up", "gpt-5.6-terra"): [failure],
    }
    service, value, calls, transport = await pending(tmp_path, failure_plan=plan)
    repo = service.repository
    await act(repo, value, "APPROVE", "A")
    await repo.apply_replan(value.run.run_id)
    with transport:
        value = await service.execute_run(value.run.run_id)
        with pytest.raises(ExceptionGroup):
            await resume(service, value.run.run_id)
    final = await repo.get_run_fresh(value.run.run_id)
    assert value.run.run_id + ":risk" not in final.node_binding.current_results
    assert value.run.run_id + ":risk-follow-up" not in final.node_binding.current_results
    assert control(final).finalization is None
    assert [m for k, m in calls if k == "risk_follow_up"] == ["gpt-5.6-sol", "gpt-5.6-terra"]
    rows = await service.recovery_evidence_store.records(
        value.run.run_id, value.run.run_id + ":risk-follow-up"
    )
    ends = [r for r in rows if r.kind == "ATTEMPT_COMPLETED"]
    assert len(ends) == 2
    assert all(r.transport_evidence is not None for r in ends)
    assert "RAW_PROVIDER_SENTINEL_MUST_NOT_PERSIST" not in str([r.model_dump() for r in rows])
    assert ends[-1].safe_failure is not None
    rejection = ends[-1].safe_failure.provider_rejection
    assert rejection.rejected_parameter == "response_format"
    assert rejection.provider_error_type == "invalid_request_error"
    if failure == "400numeric":
        assert rejection.provider_error_code_numeric == 400
        assert rejection.provider_error_code is None
    else:
        assert rejection.provider_error_code == "unsupported_parameter"
        assert rejection.provider_error_code_numeric is None


async def test_active_sibling_drains_before_apply(tmp_path):
    from tests.risk_replan.test_flow import fixture

    gate = asyncio.Event()
    service, value, calls, transport = await fixture(tmp_path, valuation_gate=gate)
    repo = service.repository
    with transport:
        worker = asyncio.create_task(service.execute_run(value.run.run_id))
        for _ in range(300):
            current = await repo.get_run_fresh(value.run.run_id)
            if current.node_binding.replan is not None:
                break
            await asyncio.sleep(0.01)
        assert current.node_binding.replan is not None
        await act(repo, current, "APPROVE", "A")
        assert await repo.apply_replan(value.run.run_id) is None
        assert (await repo.get_run_fresh(value.run.run_id)).node_binding.frozen_graph.version == 1
        gate.set()
        await worker
    transition = await repo.apply_replan(value.run.run_id)
    final = await repo.get_run_fresh(value.run.run_id)
    assert any(
        c.source_result_id == final.node_binding.current_results[value.run.run_id + ":valuation"]
        for c in transition.reused_results
    )
    assert sum(k == "valuation_analysis" for k, m in calls) == 1


async def test_recursive_child_output_is_invalid_and_never_expands(tmp_path):
    service, value, calls, transport = await pending(
        tmp_path, failure_plan={("risk_follow_up", "gpt-5.6-sol"): ["recursive"]}
    )
    repo = service.repository
    await act(repo, value, "APPROVE", "A")
    await repo.apply_replan(value.run.run_id)
    with transport, pytest.raises(ExceptionGroup):
        await service.execute_run(value.run.run_id)
    final = await repo.get_run_fresh(value.run.run_id)
    assert len(final.artifacts.replans) == 1
    assert final.node_binding.frozen_graph.version == 2
    assert value.run.run_id + ":risk" not in final.node_binding.current_results
    assert [m for k, m in calls if k == "risk_follow_up"] == ["gpt-5.6-sol"]


async def test_undispatched_valuation_recovery_carries_exact_budget(tmp_path):
    service, value, calls, transport = await pending(
        tmp_path, failure_plan={("valuation_analysis", "gpt-5.6-sol"): ["timeout"]}
    )
    repo = service.repository
    task_id = value.run.run_id + ":valuation"
    prior = deepcopy(value.node_binding.attempts[task_id])
    assert prior.status == "FAILED" and prior.recovery is not None
    await act(repo, value, "APPROVE", "A")
    transition = await repo.apply_replan(value.run.run_id)
    assert len(transition.carried_recovery) == 1
    assert transition.carried_recovery[0].reservation_id == prior.admission.attempt_reservation_id
    with transport:
        await resume(service, value.run.run_id)
    final = await repo.get_run_fresh(value.run.run_id)
    current = final.node_binding.attempts[task_id]
    assert current.status == "COMMITTED"
    assert current.admission.graph == transition.new_graph
    assert final.node_binding.attempt_history[prior.admission.attempt_reservation_id] == prior
    assert [m for k, m in calls if k == "valuation_analysis"] == ["gpt-5.6-sol", "gpt-5.6-terra"]


async def test_decline_pause_installs_before_admitted_sibling_drains(tmp_path):
    from tests.risk_replan.test_flow import fixture

    gate = asyncio.Event()
    service, value, calls, transport = await fixture(tmp_path, valuation_gate=gate)
    repo = service.repository
    with transport:
        worker = asyncio.create_task(service.execute_run(value.run.run_id))
        for _ in range(300):
            current = await repo.get_run_fresh(value.run.run_id)
            if current.node_binding.replan is not None:
                break
            await asyncio.sleep(0.01)
        await act(repo, current, "DECLINE", "D")
        paused = await repo.get_run_fresh(value.run.run_id)
        assert control(paused).reopenable
        assert paused.node_binding.attempts[value.run.run_id + ":valuation"].status == "DISPATCHED"
        gate.set()
        await worker
    final = await repo.get_run_fresh(value.run.run_id)
    assert control(final).reopenable and not control(final).resume_eligible
    assert final.node_binding.lifecycle == "WAITING_REPLAN"
    assert value.run.run_id + ":valuation" in final.node_binding.current_results
    assert value.run.run_id + ":risk" not in final.node_binding.current_results
    assert final.node_binding.frozen_graph.version == 1
    assert sum(k == "valuation_analysis" for k, m in calls) == 1
