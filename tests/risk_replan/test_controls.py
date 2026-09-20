"""Control-cycle fences, exact graph authority and independent eligibility barriers."""

import asyncio
from copy import deepcopy

import pytest
from pydantic import ValidationError

from src.application.closure_policy import classify_execution_closure
from src.application.repository import validate_root
from src.application.risk_replan import control, proposal
from src.domain.node_binding import BindingDenied
from src.phase4_product.risk_replan import ApproveReplan, DeclineReplan, ReopenReplan
from tests.risk_replan.test_flow import command, fixture


async def pending(tmp_path, **kwargs):
    service, value, calls, transport = await fixture(tmp_path, **kwargs)
    with transport:
        value = await service.execute_run(value.run.run_id)
    return service, value, calls, transport


async def act(repo, value, action, key):
    return await repo.decide_replan(
        value.run.run_id, command(value, action), actor="LOCAL_SINGLE_USER", key=key
    )


async def test_fences_and_historical_reopen(tmp_path):
    service, value, calls, _ = await pending(tmp_path)
    repo, run_id = service.repository, value.run.run_id
    approve_a = command(value, "APPROVE")
    await act(repo, value, "DECLINE", "decline-A")
    value = await repo.get_run_fresh(run_id)
    reopen_a = command(value, "REOPEN")
    first = await repo.decide_replan(run_id, reopen_a, actor="LOCAL_SINGLE_USER", key="reopen-A")
    value = await repo.get_run_fresh(run_id)
    await act(repo, value, "DECLINE", "decline-B")
    before = await repo.get_run_fresh(run_id)
    for key in ("reopen-A", "equivalent-reopen-A"):
        replay = await repo.decide_replan(run_id, reopen_a, actor="LOCAL_SINGLE_USER", key=key)
        assert replay["decision_id"] == first["decision_id"] and replay["historical_replay"]
        assert control(await repo.get_run_fresh(run_id)).reopenable
    stale = await repo.decide_replan(
        run_id, approve_a, actor="LOCAL_SINGLE_USER", key="old-approve"
    )
    assert stale["outcome"] == "REJECTED"
    after = await repo.get_run_fresh(run_id)
    assert proposal(after)[1].decision_revision == proposal(before)[1].decision_revision
    assert after.node_binding.frozen_graph == value.node_binding.frozen_graph
    assert not classify_execution_closure(after).reviewable
    assert len(calls) == 3


@pytest.mark.parametrize(
    "field,wrong",
    [
        ("expected_proposal_digest", "sha256:" + "0" * 64),
        ("expected_decision_revision", 999),
        (
            "expected_graph",
            {"run_id": "OTHER", "graph_id": "WRONG", "version": 1, "semantic_hash": "wrong"},
        ),
    ],
)
async def test_stale_decisions_preserve_authority(tmp_path, field, wrong):
    service, value, calls, _ = await pending(tmp_path)
    repo = service.repository
    for action in ("APPROVE", "DECLINE"):
        payload = {**command(value, action), field: wrong}
        first = await repo.decide_replan(
            value.run.run_id, payload, actor="LOCAL_SINGLE_USER", key=action
        )
        assert first["outcome"] == "REJECTED"
        count = len(control(await repo.get_run_fresh(value.run.run_id)).audit)
        await repo.decide_replan(value.run.run_id, payload, actor="LOCAL_SINGLE_USER", key=action)
        assert len(control(await repo.get_run_fresh(value.run.run_id)).audit) == count
    await act(repo, value, "DECLINE", "valid-decline")
    value = await repo.get_run_fresh(value.run.run_id)
    stale = await repo.decide_replan(
        value.run.run_id,
        {**command(value, "REOPEN"), field: wrong},
        actor="LOCAL_SINGLE_USER",
        key="stale-reopen",
    )
    assert stale["outcome"] == "REJECTED"
    assert control(await repo.get_run_fresh(value.run.run_id)).reopenable


async def test_explicit_authorized_scoped_actions(tmp_path):
    service, value, calls, _ = await pending(tmp_path)
    repo = service.repository
    good = command(value, "APPROVE")
    for altered, actor in [
        ({**good, "run_id": "OTHER"}, "LOCAL_SINGLE_USER"),
        ({**good, "proposal_id": "OTHER"}, "LOCAL_SINGLE_USER"),
        ({**good, "object_id": "OTHER"}, "LOCAL_SINGLE_USER"),
        (good, "risk_analyst"),
        ({**good, "authorize_replan": False}, "LOCAL_SINGLE_USER"),
        ({**good, "message": "approve"}, "LOCAL_SINGLE_USER"),
    ]:
        with pytest.raises(BindingDenied):
            await repo.decide_replan(value.run.run_id, altered, actor=actor, key="wrong")
    for model in (ApproveReplan, DeclineReplan, ReopenReplan):
        with pytest.raises(ValidationError):
            model.model_validate({"message": "Yes, please approve the follow-up"})
    assert (await repo.get_run_fresh(value.run.run_id)).node_binding.frozen_graph.version == 1


async def test_approve_decline_race_and_idempotency_conflict(tmp_path):
    service, value, calls, _ = await pending(tmp_path)
    repo = service.repository
    results = await asyncio.gather(
        act(repo, value, "APPROVE", "A"), act(repo, value, "DECLINE", "D")
    )
    assert sorted(r["outcome"] for r in results) == ["COMMITTED", "REJECTED"]
    current = await repo.get_run_fresh(value.run.run_id)
    assert len(proposal(current)[1].history) == 1
    payload = command(value, "APPROVE")
    payload["expected_decision_revision"] += 1
    with pytest.raises(BindingDenied, match="IDEMPOTENCY_CONFLICT"):
        await repo.decide_replan(value.run.run_id, payload, actor="LOCAL_SINGLE_USER", key="A")


@pytest.mark.parametrize("apply_first", [False, True])
async def test_cancel_terminal_retains_lineage(tmp_path, apply_first):
    service, value, calls, _ = await pending(tmp_path)
    repo = service.repository
    if apply_first:
        await act(repo, value, "APPROVE", "A")
        await repo.apply_replan(value.run.run_id)
        value = await repo.get_run_fresh(value.run.run_id)
    else:
        await act(repo, value, "DECLINE", "D")
        value = await repo.get_run_fresh(value.run.run_id)
    before = deepcopy(value.node_binding.current_results)
    receipt = await act(repo, value, "CANCEL", "C")
    cancelled = await repo.get_run_fresh(value.run.run_id)
    assert cancelled.run.status.value == "CANCELLED" and cancelled.run.completed_at
    assert cancelled.node_binding.current_results == before
    assert bool(control(cancelled).transition) == apply_first
    assert not classify_execution_closure(cancelled).reviewable
    assert (await repo.replan_projection(value.run.run_id))["legal_actions"] == []
    denied = await act(repo, cancelled, "REOPEN", "REOPEN")
    assert denied["outcome"] == "REJECTED" and denied["code"] == "REPLAN_TERMINAL_RUN"
    with pytest.raises(BindingDenied, match="TERMINAL"):
        await act(repo, cancelled, "APPROVE", "APPROVE")
    assert (await act(repo, value, "CANCEL", "C"))["decision_id"] == receipt["decision_id"]


async def test_exact_diff_and_candidate_tampering_fail_closed(tmp_path):
    service, value, calls, _ = await pending(tmp_path)
    for path, new in [
        ("proposal_type", "DELETE_NODE"),
        ("source_output_digest", "wrong"),
        ("source_candidate_id", "wrong"),
        ("proposal_digest", "wrong"),
    ]:
        bad = deepcopy(value)
        bad.artifacts.replans[0].risk_follow_up[path] = new
        with pytest.raises((BindingDenied, ValidationError)):
            validate_root(bad)
    bad = deepcopy(value)
    bad.node_binding.replan["candidate"]["output_record"]["payload_snapshot"]["actual_model"] = (
        "gpt-other"
    )
    with pytest.raises(BindingDenied):
        validate_root(bad)
    assert not value.artifacts.task_outputs.get(value.run.run_id + ":risk")
    from src.application.research_outputs import availability_map

    assert not any(
        o["task_id"] == value.run.run_id + ":risk"
        for o in availability_map(value)["available_findings"]
    )


async def test_false_path_commits_without_proposal(tmp_path):
    from src.application.execution import IntegratedTaskExecutor
    from src.runtime.scheduler import DependencyScheduler

    service, value, calls, transport = await fixture(tmp_path, follow_up=False)
    owner = await service.repository.claim_execution(value.run.run_id)
    value = await service.repository.get_run_fresh(value.run.run_id)
    with transport:
        await DependencyScheduler(
            event_store=service.event_store,
            checkpoint_store=service.checkpoint_store,
            admission_repository=service.repository,
            execution_owner=owner,
        ).execute(state=value.runtime, executor=IntegratedTaskExecutor(service, value))
    final = await service.repository.get_run_fresh(value.run.run_id)
    assert final.node_binding.replan is None and not final.artifacts.replans
    assert final.node_binding.frozen_graph.version == 1
    assert final.run.run_id + ":risk" in final.node_binding.current_results
    assert sum(kind == "risk_analysis" for kind, _ in calls) == 1
