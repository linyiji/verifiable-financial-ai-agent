"""Synthetic full-graph production-owner proofs for explicit Resume execution."""

from copy import deepcopy

import pytest

from src.application.external_failure_resume import control, legacy_snapshot
from src.application.resume_runtime import current_risk_success
from src.domain.node_binding import BindingDenied
from tests.external_failure_resume.runtime_fixture import exhaust, legal_fixture, request_for


async def test_explicit_resume_idempotent_repeated_exhaustion(tmp_path):
    service, initial, clients = await legal_fixture(tmp_path)
    failed = await exhaust(service, initial)
    root = failed.node_binding
    old_results = deepcopy(root.results)
    old_attempts = deepcopy(root.attempts)
    old_rows = await service.recovery_evidence_store.records(failed.run.run_id)
    before_calls = {k: c.calls for k, c in clients.items()}
    with pytest.raises(BindingDenied):
        await service.execute_run(failed.run.run_id)
    assert before_calls == {k: c.calls for k, c in clients.items()}
    request = await request_for(service, failed)
    receipt = await service.repository.resume_external_failure(request, actor=request.actor)
    pending = await service.repository.get_run_fresh(failed.run.run_id)
    assert pending.node_binding.lifecycle == "EXTERNAL_RESUME_PENDING"
    replay = await service.repository.resume_external_failure(request, actor=request.actor)
    assert replay == receipt
    assert legacy_snapshot(pending) == legacy_snapshot(
        await service.repository.get_run_fresh(failed.run.run_id)
    )
    assert await service.repository.external_resume_pending_run_ids() == [failed.run.run_id]
    risk = next(t for t in failed.runtime.actual_graph.tasks if t.task_type == "risk_analysis")
    with pytest.raises(BindingDenied):
        await service.repository.check_invocation(old_attempts[risk.task_id].admission)
    again = await exhaust(service, pending)
    assert again.node_binding.lifecycle == "EXTERNAL_FAILURE_PAUSED"
    assert await service.repository.external_resume_pending_run_ids() == []
    assert not current_risk_success(again)
    assert again.node_binding.results == old_results
    assert again.node_binding.frozen_graph == root.frozen_graph
    assert again.node_binding.execution_snapshot == root.execution_snapshot
    for task_id, attempt in old_attempts.items():
        if task_id != risk.task_id:
            assert again.node_binding.attempts[task_id] == attempt
        else:
            assert (
                again.node_binding.attempt_history[attempt.admission.attempt_reservation_id]
                == attempt
            )
    assert (await service.recovery_evidence_store.records(failed.run.run_id))[
        : len(old_rows)
    ] == old_rows
    assert clients["teamorouter-sol"].calls == before_calls["teamorouter-sol"] + 1
    assert clients["teamorouter-terra"].calls == before_calls["teamorouter-terra"] + 1
    assert clients["teamorouter-luna"].calls == clients["mimo-direct"].calls == 0
    assert len(control(again).failures) == 2
    with pytest.raises(BindingDenied):
        await service.execute_run(failed.run.run_id)
    second = await request_for(service, again, "resume-two")
    await service.repository.resume_external_failure(second, actor=second.actor)
    assert (
        control(await service.repository.get_run_fresh(failed.run.run_id))
        .envelopes[-1]
        .cycle_ordinal
        == 2
    )

    clients["teamorouter-sol"].fail_risk = False
    await service.execute_run(failed.run.run_id)
    success = await service.repository.get_run_fresh(failed.run.run_id)
    assert current_risk_success(success)
    assert success.node_binding.attempts[risk.task_id].generation == 5
    assert len(control(success).failures) == 2
    assert any(
        t.task_type == "report_synthesis" and t.status.value == "COMPLETED"
        for t in success.runtime.actual_graph.tasks
    )


async def test_later_success_is_current_and_unblocks_synthesis(tmp_path):
    service, initial, clients = await legal_fixture(tmp_path)
    failed = await exhaust(service, initial)
    risk = next(t for t in failed.runtime.actual_graph.tasks if t.task_type == "risk_analysis")
    synthesis = next(
        t for t in failed.runtime.actual_graph.tasks if t.task_type == "report_synthesis"
    )
    request = await request_for(service, failed)
    await service.repository.resume_external_failure(request, actor=request.actor)
    owner = await service.repository.claim_execution(failed.run.run_id)
    current = await service.repository.validate_execution(owner)
    from src.application.execution import IntegratedTaskExecutor

    with pytest.raises(BindingDenied, match="RESUME_CURRENT_RISK_SUCCESS_REQUIRED"):
        await service.repository.reserve_node(
            owner,
            synthesis,
            IntegratedTaskExecutor(service, current).admission_requirements(synthesis),
        )
    clients["teamorouter-sol"].fail_risk = False
    # Release policy is deliberately unchanged. The asserted boundary is current
    # Risk success and Synthesis commit, regardless of later assurance outcome.
    try:
        await service.execute_run(failed.run.run_id, execution_owner=owner)
    except ExceptionGroup:
        raise
    result = await service.repository.get_run_fresh(failed.run.run_id)
    assert current_risk_success(result)
    assert synthesis.task_id in result.node_binding.current_results
    assert result.node_binding.attempts[risk.task_id].generation == 3
    assert result.node_binding.frozen_graph == failed.node_binding.frozen_graph
    assert result.node_binding.execution_snapshot == failed.node_binding.execution_snapshot
    assert result.node_binding.attempts[synthesis.task_id].generation == 1
    assert len(control(result).failures) == 1
    assert clients["teamorouter-terra"].calls == 1


async def test_denials_and_single_claim_are_fail_closed(tmp_path):
    import asyncio

    service, initial, clients = await legal_fixture(tmp_path)
    failed = await exhaust(service, initial)
    request = await request_for(service, failed)
    snapshot = legacy_snapshot(failed)
    calls = {key: c.calls for key, c in clients.items()}
    for updates in (
        {"run_id": "RUN-wrong"},
        {"failed_node_id": "RUN-wrong:risk"},
        {"expected_profile_digest": "wrong"},
        {
            "expected_graph_identity": request.expected_graph_identity.model_copy(
                update={"semantic_hash": "sha256:wrong"}
            )
        },
        {
            "expected_failure_cycle_identity": request.expected_failure_cycle_identity.model_copy(
                update={"operation_id": "wrong-cycle"}
            )
        },
        {
            "expected_binding_ref": request.expected_binding_ref.model_copy(
                update={"binding_revision": 999}
            )
        },
        {"expected_owner_generation": 999},
        {"expected_as_of": "2020-01-01"},
        {"actor": "wrong"},
        {"expected_scenario_digest": "wrong"},
    ):
        with pytest.raises(BindingDenied):
            await service.repository.resume_external_failure(
                request.model_copy(update=updates), actor="local-test"
            )
        assert (
            legacy_snapshot(await service.repository.get_run_fresh(failed.run.run_id)) == snapshot
        )
    assert {key: c.calls for key, c in clients.items()} == calls
    receipts = await asyncio.gather(
        *(
            service.repository.resume_external_failure(request, actor=request.actor)
            for _ in range(2)
        )
    )
    assert receipts[0] == receipts[1]
    owners = await asyncio.gather(
        *(service.repository.claim_execution(failed.run.run_id) for _ in range(2)),
        return_exceptions=True,
    )
    assert sum(isinstance(value, BindingDenied) for value in owners) == 1
    assert await service.repository.external_resume_pending_run_ids() == []
    with pytest.raises(BindingDenied, match="RESUME_IDEMPOTENCY_CONFLICT"):
        await service.repository.resume_external_failure(
            request.model_copy(update={"expected_as_of": "wrong"}), actor=request.actor
        )


async def test_invalid_material_denies_command_and_old_provider_is_fenced(tmp_path):
    import asyncio
    from pathlib import Path
    from uuid import uuid4

    service, initial, clients = await legal_fixture(tmp_path)
    failed = await exhaust(service, initial)
    request = await request_for(service, failed)
    before = legacy_snapshot(failed)
    calls = {key: c.calls for key, c in clients.items()}
    for task_id, result_id in failed.node_binding.current_results.items():
        result = failed.node_binding.results[result_id]
        records = [r for r in result.output_records if r.kind == "AGENT_OUTPUT"]
        if not records:
            records = [r for r in result.output_records if r.kind == "EVIDENCE"]
        assert records, task_id
        path = Path(records[0].location)
        withheld = path.with_name(path.name + ".withheld")
        await asyncio.to_thread(path.rename, withheld)
        try:
            with pytest.raises(BindingDenied):
                await service.repository.resume_external_failure(request, actor=request.actor)
        finally:
            await asyncio.to_thread(withheld.rename, path)
        assert legacy_snapshot(await service.repository.get_run_fresh(failed.run.run_id)) == before
    assert {key: c.calls for key, c in clients.items()} == calls
    await service.repository.resume_external_failure(request, actor=request.actor)
    rows = await service.recovery_evidence_store.records(failed.run.run_id)
    old = next(row for row in rows if row.scope.task_profile == "risk_analysis")
    with pytest.raises(BindingDenied):
        await service.recovery_evidence_store.append(
            old.model_copy(update={"record_id": str(uuid4())})
        )
    assert await service.recovery_evidence_store.records(failed.run.run_id) == rows


async def test_terminal_publisher_must_finish_before_resume(tmp_path, monkeypatch):
    import asyncio

    from src.domain.runtime_event import RuntimeEventType

    service, initial, _ = await legal_fixture(tmp_path)
    reached, release = asyncio.Event(), asyncio.Event()
    emit = service.event_store.emit

    async def delayed_terminal(**kwargs):
        if kwargs["event_type"] is RuntimeEventType.RUN_FAILED:
            reached.set()
            await release.wait()
        return await emit(**kwargs)

    monkeypatch.setattr(service.event_store, "emit", delayed_terminal)
    execution = asyncio.create_task(exhaust(service, initial))
    try:
        await asyncio.wait_for(reached.wait(), 60)
        failed = await service.repository.get_run_fresh(initial.run.run_id)
        assert failed.run.status.value == "FAILED"
        view = await service.repository.inspect_external_failure(
            failed.run.run_id, actor="local-test"
        )
        assert view["legal_actions"] == []
        assert "RESUME_RESULT_UNKNOWN" in view["denial_reasons"]
    finally:
        release.set()
    failed = await execution
    request = await request_for(service, failed)
    await service.repository.resume_external_failure(request, actor=request.actor)
