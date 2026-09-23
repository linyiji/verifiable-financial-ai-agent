"""Synthetic local HTTP transport through production agent/repository/scheduler owners."""

import json
from unittest.mock import patch

import httpx
import pytest

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.teamorouter import TeamoRouterClient
from src.application.repository import initialize_binding
from src.domain.owner_policy import ADAPTIVE_TRANSPORT_POLICY
from src.domain.recovery import Candidate
from src.domain.task import Task
from src.infrastructure.config.settings import Settings
from tests.same_node_recovery.test_durable import configured


async def fixture(
    tmp_path,
    *,
    follow_up=True,
    repository=None,
    store=None,
    sessions=None,
    failure_plan=None,
    valuation_gate=None,
    persist=True,
    complete_requirements=False,
    minimal_risk=False,
    symbol="SYNTHETIC",
):
    service, aggregate, collector, _ = await configured(
        tmp_path, persist=False, failures=(), repository=repository, store=store, sessions=sessions
    )
    if complete_requirements:
        aggregate.scheme.calculation_requirements = ["revenue_growth", "ebitda_margin"]
    original_add = service.evidence_repository.add

    async def add_evidence(record):
        record.evidence_purpose = "COMPANY_FINANCIALS"
        return await original_add(record)

    service.evidence_repository.add = add_evidence
    run_id = aggregate.run.run_id
    root = aggregate.runtime.actual_graph.tasks[1]
    for graph in (aggregate.runtime.actual_graph, aggregate.runtime.planned_graph):
        risk = Task(
            task_id=run_id + ":risk",
            run_id=run_id,
            task_type="risk_analysis",
            assigned_agent="risk_analyst",
            skill_id="risk_analysis_v1",
            goal="Assess material risk",
            dependencies=[root.task_id],
        )
        valuation = Task(
            task_id=run_id + ":valuation",
            run_id=run_id,
            task_type="valuation_analysis",
            assigned_agent="valuation_analyst",
            skill_id="valuation_analysis_v1",
            goal="Qualitative valuation",
            dependencies=[root.task_id],
        )
        synthesis = Task(
            task_id=run_id + ":synthesis",
            run_id=run_id,
            task_type="report_synthesis",
            assigned_agent="research_lead",
            skill_id="report_synthesis_v1",
            goal="Synthesize",
            dependencies=[risk.task_id, valuation.task_id],
        )
        graph.tasks.extend([risk, valuation, synthesis])
    settings = Settings(_env_file=None, teamorouter_api_key="LOCAL_SENTINEL")
    clients = {}
    for route, model in [
        ("teamorouter-sol", "gpt-5.6-sol"),
        ("teamorouter-luna", "gpt-5.6-luna"),
        ("teamorouter-terra", "gpt-5.6-terra"),
    ]:
        clients[route] = TeamoRouterClient(
            settings.llm.model_copy(update={"primary_model": model, "fallback_model": model}),
            execution_policy=ProviderExecutionPolicyV1(**ADAPTIVE_TRANSPORT_POLICY),
        )
        clients[route].route_ids = {model: route}
    from src.application.execution_profiles import configured_agent

    for task in aggregate.runtime.actual_graph.tasks:
        if task.task_type == "evidence_collection":
            continue
        agent = configured_agent(service, task, None)
        agent._provider = clients["teamorouter-sol"]
        agent._recovery.clients.update(clients)
        for route, client in clients.items():
            agent._recovery.detector.routes[route] = Candidate(
                route=route,
                provider=client.provider_name,
                model=client.model_name,
                authority_exists=True,
            )
    if minimal_risk:
        from datetime import date

        from src.adapters.fmp import FMPProvider
        from src.application.evidence_collection import LiveFMPEvidenceCollector
        from src.data.artifacts import LocalRawArtifactStore
        from tests.external_failure_resume.runtime_fixture import Transport

        aggregate.goal.preferences["risk_semantic_profile"] = "risk_semantic_outcome_minimal_v1"
        aggregate.goal.as_of = aggregate.run.as_of = date(2026, 9, 4)
        service.evidence_collector = LiveFMPEvidenceCollector(
            provider=FMPProvider(Transport()), repository=service.evidence_repository,
            artifact_store=LocalRawArtifactStore(tmp_path / "minimal-raw"))
    aggregate.node_binding = None
    aggregate.run.planned_graph_id = aggregate.runtime.planned_graph.graph_id
    aggregate.run.actual_graph_id = aggregate.runtime.actual_graph.graph_id
    initialize_binding(aggregate, service=service)
    if persist:
        from tests.wp02.confirmation_fixture import confirm_template

        aggregate = await confirm_template(service, aggregate, symbol=symbol)
    calls = []

    async def response(request):
        wire = json.loads(request.content)
        prompt = json.loads(wire["messages"][-1]["content"])
        calls.append((prompt["task_type"], wire["model"]))
        if prompt["task_type"] == "valuation_analysis" and valuation_gate is not None:
            await valuation_gate.wait()
        failures = (failure_plan or {}).get((prompt["task_type"], wire["model"]), [])
        failure = failures.pop(0) if failures else None
        if failure == "timeout":
            raise httpx.ReadTimeout("Synthetic timeout", request=request)
        if failure in {"400numeric", "400string"}:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": 400 if failure == "400numeric" else "unsupported_parameter",
                        "type": "invalid_request_error",
                        "param": "response_format",
                        "message": "RAW_PROVIDER_SENTINEL_MUST_NOT_PERSIST",
                    }
                },
            )
        output = dict(
            summary="Synthetic bounded assessment",
            key_findings=["Synthetic finding"],
            risks=["Synthetic risk"],
            limitations=[],
            requires_follow_up=(follow_up and prompt["task_type"] == "risk_analysis")
            or failure == "recursive",
        )
        if minimal_risk and prompt["task_type"] == "risk_analysis":
            output.update(
                business_outcome="SUFFICIENT", outcome_reason_codes=[], evidence_gap_refs=[]
            )
        return httpx.Response(
            200,
            json={
                "model": wire["model"],
                "choices": [{"message": {"content": json.dumps(output)}}],
            },
        )

    client_class = httpx.AsyncClient

    def factory(**kwargs):
        return client_class(
            transport=httpx.MockTransport(response), trust_env=False, timeout=kwargs.get("timeout")
        )

    return (
        service,
        aggregate,
        calls,
        patch("src.adapters.llm.teamorouter.httpx.AsyncClient", factory),
    )


async def test_pending_candidate_production_execution(tmp_path):
    service, aggregate, calls, transport = await fixture(tmp_path)
    with transport:
        result = await service.execute_run(aggregate.run.run_id)
    assert result.run.status.value == "WAITING_REPLAN"
    state = result.node_binding.replan
    assert state is not None
    assert aggregate.run.run_id + ":risk" not in result.node_binding.current_results
    assert len(result.artifacts.replans) == 1
    assert result.runtime.actual_graph.version == 1
    assert not any(kind == "report_synthesis" for kind, model in calls)


def command(value, action):
    from src.application.risk_replan import control, proposal

    state = control(value)
    req, p = proposal(value)
    base = dict(
        run_id=value.run.run_id,
        object_id=value.run.research_object_id,
        proposal_id=req.replan_id,
        action=action,
    )
    if action == "CANCEL":
        return {**base, "abandon": True, "expected_control_revision": state.control_revision}
    return {
        **base,
        {
            "APPROVE": "authorize_replan",
            "DECLINE": "reject_replan",
            "REOPEN": "reopen_declined_replan",
        }[action]: True,
        "expected_proposal_digest": p.proposal_digest,
        "expected_graph": p.base_graph.model_dump(mode="json"),
        "expected_decision_revision": p.decision_revision,
    }


async def test_decline_reopen_approve_exact_graph(tmp_path):
    service, aggregate, calls, transport = await fixture(tmp_path)
    repo = service.repository
    run_id = aggregate.run.run_id
    with transport:
        value = await service.execute_run(run_id)
    original = value.node_binding.frozen_graph
    await repo.decide_replan(
        run_id, command(value, "DECLINE"), actor="LOCAL_SINGLE_USER", key="decline"
    )
    value = await repo.get_run_fresh(run_id)
    assert value.node_binding.frozen_graph == original
    assert value.node_binding.replan["reopenable"]
    reopen_command = command(value, "REOPEN")
    await repo.decide_replan(run_id, reopen_command, actor="LOCAL_SINGLE_USER", key="reopen")
    value = await repo.get_run_fresh(run_id)
    assert not value.node_binding.replan["resume_eligible"]
    assert value.node_binding.frozen_graph == original
    approval_command = command(value, "APPROVE")
    await repo.decide_replan(run_id, approval_command, actor="LOCAL_SINGLE_USER", key="approve")
    transition = await repo.apply_replan(run_id)
    value = await repo.get_run_fresh(run_id)
    assert transition.new_graph.version == 2
    assert transition.base_graph == original
    assert len(transition.reused_results) == 3
    assert len(value.runtime.actual_graph.tasks) == 6
    assert value.node_binding.execution_snapshot["nodes"][-1]["profile"] is not None
    again = await repo.decide_replan(
        run_id, approval_command, actor="LOCAL_SINGLE_USER", key="approve"
    )
    assert again["historical_replay"]
    assert (await repo.apply_replan(run_id)) == transition


async def test_child_pair_and_synthesis(tmp_path):
    from src.application.execution import IntegratedTaskExecutor
    from src.runtime.scheduler import DependencyScheduler

    service, aggregate, calls, transport = await fixture(tmp_path)
    repo = service.repository
    run_id = aggregate.run.run_id
    with transport:
        value = await service.execute_run(run_id)
        await repo.decide_replan(
            run_id, command(value, "APPROVE"), actor="LOCAL_SINGLE_USER", key="approve"
        )
        await repo.apply_replan(run_id)
        owner = await repo.claim_execution(run_id)
        value = await repo.get_run_fresh(run_id)
        scheduler = DependencyScheduler(
            event_store=service.event_store,
            checkpoint_store=service.checkpoint_store,
            admission_repository=repo,
            execution_owner=owner,
        )
        await scheduler.execute(
            state=value.runtime, executor=IntegratedTaskExecutor(service, value)
        )
    final = await repo.get_run_fresh(run_id)
    assert final.node_binding.replan["finalization"] is not None
    assert run_id + ":risk" in final.node_binding.current_results
    assert run_id + ":risk-follow-up" in final.node_binding.current_results
    assert run_id + ":synthesis" in final.node_binding.current_results
    assert sum(kind == "valuation_analysis" for kind, _ in calls) == 1
    assert sum(kind == "risk_follow_up" for kind, _ in calls) == 1


@pytest.mark.parametrize("symbol", ["ALPHA", "BETA"])
async def test_existing_release_gates_preserve_replan_lineage(tmp_path, symbol):
    from src.application.risk_replan import control

    service, value, calls, transport = await fixture(
        tmp_path, complete_requirements=True, symbol=symbol
    )
    repo = service.repository
    with transport:
        value = await service.execute_run(value.run.run_id)
        assert value.run.status.value == "WAITING_REPLAN"
        assert value.artifacts.report is None and value.artifacts.released_result is None
        await repo.decide_replan(
            value.run.run_id, command(value, "APPROVE"), actor="LOCAL_SINGLE_USER", key="A"
        )
        await repo.apply_replan(value.run.run_id)
        final = await service.execute_run(value.run.run_id)
    assert final.run.status.value == "RELEASED"
    state = control(final)
    record = final.artifacts.canonical_record
    assert record.replan_refs == [state.active_proposal_id]
    assert record.actual_graph["version"] == 2 and record.planned_graph["version"] == 1
    assert state.finalization.fulfilling_child_task_id in record.task_refs
    assert state.candidate.output_record.record_id in record.agent_output_refs
    assert state.candidate.output_record.payload_snapshot["structured_output"]["requires_follow_up"]
    assert final.artifacts.review and final.artifacts.proofs
    assert final.artifacts.report and final.artifacts.released_result
    assert [m for k, m in calls if k == "risk_follow_up"] == ["gpt-5.6-sol"]
    assert sum(k == "valuation_analysis" for k, m in calls) == 1
