"""Synthetic transports, production preparation/confirmation and PostgreSQL owners."""

import asyncio
import json
import os
from copy import deepcopy
from dataclasses import replace
from datetime import date

import pytest

from src.adapters.fmp import FMPEndpoint, FMPProvider
from src.agentic.composition import build_research_agent_registry
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.application.evidence_collection import LiveFMPEvidenceCollector
from src.application.execution import IntegratedTaskExecutor
from src.application.persistence import (
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.application.service import ResearchApplicationService
from src.data.artifacts import LocalRawArtifactStore
from src.domain.risk_admission import PROFILE, SCHEMA
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.runtime.scheduler import DependencyScheduler
from tests.external_failure_resume.runtime_fixture import Transport
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401
from tests.unit.agentic.test_adaptive_recovery import Client

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL required"
)


async def fixture(
    tmp_path,
    sessions,
    *,
    insufficient=False,
    follow_up=False,
    legacy=False,
    conflict=False,
    malformed=False,
    requirements=None,
    payload_patch=None,
):
    class Synthetic(Client):
        schemas = []

        async def complete_structured(self, **kwargs):
            self.schemas.append(kwargs["schema_name"])
            if kwargs["schema_name"] != SCHEMA:
                return await super().complete_structured(**kwargs)
            self.calls += 1
            prompt = json.loads(kwargs["messages"][-1].content)
            # The server, not the model, supplies the finite obligation refs.
            ref = prompt["authoritative_inputs"]["risk_obligation_refs"][0]
            payload = dict(
                summary="Synthetic bounded risk",
                key_findings=["Synthetic"],
                risks=[],
                limitations=[],
                requires_follow_up=follow_up,
                business_outcome="INSUFFICIENT_EVIDENCE" if insufficient else "SUFFICIENT",
                outcome_reason_codes=["EVIDENCE_COVERAGE_LIMITED"] if insufficient else [],
                evidence_gap_refs=[
                    dict(requirement_ref=ref, reason_code="EVIDENCE_COVERAGE_LIMITED")
                ]
                if insufficient
                else [],
            )
            if payload_patch:
                payload.update(payload_patch)
            if malformed:
                payload.pop("business_outcome")
            # Real production HTTP decoder; only the external transport is synthetic.
            import httpx

            from src.adapters.llm.teamorouter import TeamoRouterClient
            from src.infrastructure.config.settings import Settings

            def response(request):
                wire = json.loads(request.content)
                return httpx.Response(
                    200,
                    json={
                        "model": wire["model"],
                        "choices": [{"message": {"content": json.dumps(payload)}}],
                        "usage": {"prompt_tokens": 12, "completion_tokens": 6},
                    },
                )

            settings = Settings(_env_file=None, teamorouter_api_key="LOCAL_SENTINEL")
            async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as transport:
                decoder = TeamoRouterClient(
                    settings.llm.model_copy(
                        update={
                            "primary_model": self.model_name,
                            "fallback_model": self.model_name,
                        }
                    ),
                    client=transport,
                )
                return await decoder.complete_structured(**kwargs)

    class Snapshots(Transport):
        income_calls = 0

        async def request(self, **kwargs):
            envelope = await super().request(**kwargs)
            if kwargs["endpoint"] == FMPEndpoint.INCOME:
                self.income_calls += 1
                payload = deepcopy(envelope.payload)
                if conflict:
                    payload[0]["revenue"] = 100 if self.income_calls == 1 else 101
                envelope = replace(envelope, payload=payload)
            return envelope

    from src.agentic.planner import ResearchLeadPlanner

    class TwoSnapshots(ResearchLeadPlanner):
        def plan(self, **kwargs):
            graph = super().plan(**kwargs)
            if conflict:
                first = next(t for t in graph.tasks if t.task_type == "evidence_collection")
                fundamental = next(t for t in graph.tasks if t.task_type == "fundamental_analysis")
                second = first.model_copy(
                    update={
                        "task_id": first.task_id + "-snapshot-two",
                        "dependencies": [fundamental.task_id],
                    }
                )
                graph.tasks.append(second)
                for task in graph.tasks:
                    if task.task_type == "risk_analysis":
                        task.dependencies.append(second.task_id)
            if requirements is not None:
                from src.domain.output_dependency import OutputRequirements

                risk = next(t for t in graph.tasks if t.task_type == "risk_analysis")
                fundamental = next(t for t in graph.tasks if t.task_type == "fundamental_analysis")
                risk.output_requirements = OutputRequirements.model_validate(
                    {
                        key: [
                            [v.replace("$F", fundamental.task_id) for v in group]
                            for group in values
                        ]
                        if key == "any_of"
                        else [v.replace("$F", fundamental.task_id) for v in values]
                        for key, values in requirements.items()
                    }
                )
            return graph

    client = Synthetic("teamorouter", "gpt-5.6-sol")
    repo = SQLAlchemyApplicationRepository(sessions)
    evidence = SessionFactoryEvidenceRepository(sessions)
    service = ResearchApplicationService(
        repository=repo,
        planner=TwoSnapshots(),
        event_store=PostgresRuntimeEventStore(sessions),
        evidence_repository=evidence,
        evidence_collector=LiveFMPEvidenceCollector(
            provider=FMPProvider(Snapshots()),
            repository=evidence,
            artifact_store=LocalRawArtifactStore(tmp_path / "raw"),
        ),
        agent_registry=build_research_agent_registry(
            client, ResearchAgentOutputArtifactStore(tmp_path / "agents")
        ),
    )
    obj = await service.create_object(symbol="NVDA", company_name="Synthetic", exchange="LOCAL")
    draft = await service.prepare_run(
        research_object_id=obj.object_id,
        research_goal="Synthetic minimal Risk qualification",
        as_of=date(2026, 9, 4),
        preferences={} if legacy else {"risk_semantic_profile": PROFILE},
    )
    value = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    return service, value, client


@pytest.mark.parametrize("insufficient,follow_up", [(False, False), (True, False), (True, True)])
async def test_m02_m03_production(database, tmp_path, insufficient, follow_up):  # noqa: F811
    _, sessions = database
    service, value, client = await fixture(
        tmp_path, sessions, insufficient=insufficient, follow_up=follow_up
    )
    repo = service.repository
    owner = await repo.claim_execution(value.run.run_id)
    value = await repo.get_run_fresh(value.run.run_id)
    await DependencyScheduler(
        event_store=service.event_store,
        checkpoint_store=service.checkpoint_store,
        admission_repository=repo,
        execution_owner=owner,
    ).execute(state=value.runtime, executor=IntegratedTaskExecutor(service, value))
    fresh = await SQLAlchemyApplicationRepository(sessions).get_run_fresh(value.run.run_id)
    receipts = fresh.node_binding.risk_admissions
    assert receipts, client.schemas
    receipt = next(iter(receipts.values()))
    assert receipt["decision"] == ("EVIDENCE_INSUFFICIENT" if insufficient else "FINAL_SUCCESS"), (
        receipt
    )
    risk = receipt["scope"]["task_id"]
    assert (risk in fresh.node_binding.current_results) is (not insufficient)
    assert fresh.node_binding.replan is None
    assert client.schemas.count(SCHEMA) == 1
    assert ("report_synthesis_research_output_v1" in client.schemas) is (not insufficient)


@pytest.mark.parametrize("follow_up,malformed", [(False, False), (True, False), (True, True)])
async def test_m05_m06_lawful_structured_conflict(database, tmp_path, follow_up, malformed):  # noqa: F811
    _, sessions = database
    service, value, client = await fixture(
        tmp_path, sessions, conflict=True, follow_up=follow_up, malformed=malformed
    )
    repo = service.repository
    owner = await repo.claim_execution(value.run.run_id)
    value = await repo.get_run_fresh(value.run.run_id)
    await DependencyScheduler(
        event_store=service.event_store,
        checkpoint_store=service.checkpoint_store,
        admission_repository=repo,
        execution_owner=owner,
    ).execute(state=value.runtime, executor=IntegratedTaskExecutor(service, value))
    fresh = await SQLAlchemyApplicationRepository(sessions).get_run_fresh(value.run.run_id)
    receipt = next(iter(fresh.node_binding.risk_admissions.values()))
    assert receipt["decision"] == ("CONTRACT_REJECTED" if malformed else "EVIDENCE_INSUFFICIENT"), (
        receipt
    )
    if not malformed:
        assert "UNRESOLVED_STRUCTURED_CONFLICT" in receipt["guard"]["reason_codes"]
        assert receipt["closure"]["missing_required"] == []
        pairs = receipt["guard"]["conflicts"]
        assert pairs
        selected = fresh.node_binding.resolved_inputs[receipt["resolved_input_binding_id"]]
        evidence = {
            r.record_id: r.payload_snapshot for r in selected.material_refs if r.kind == "EVIDENCE"
        }
        left, right = [evidence[k] for k in pairs[0]["evidence_refs"]]
        assert left["status"] == right["status"] == "ACCEPTED"
        assert left["snapshot_hash"] != right["snapshot_hash"]
        assert left["producer_task_id"] != right["producer_task_id"]
    assert fresh.node_binding.replan is None
    assert receipt["scope"]["task_id"] not in fresh.node_binding.current_results
    assert client.schemas.count(SCHEMA) == 1
    assert "report_synthesis_research_output_v1" not in client.schemas


async def test_m10_governed_follow_up_finalization(database, tmp_path):  # noqa: F811
    from src.infrastructure.database.recovery import RecoveryEvidenceStore
    from tests.risk_replan.test_flow import command
    from tests.risk_replan.test_flow import fixture as replan_fixture

    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, calls, transport = await replan_fixture(
        tmp_path,
        repository=repo,
        store=RecoveryEvidenceStore(sessions),
        sessions=sessions,
        complete_requirements=True,
        minimal_risk=True,
    )
    run_id = value.run.run_id
    with transport:
        value = await service.execute_run(run_id)
        assert value.node_binding.replan is not None, value.node_binding.risk_admissions
        receipt = next(iter(value.node_binding.risk_admissions.values()))
        assert receipt["decision"] == "FOLLOW_UP_PENDING"
        assert receipt["scope"]["task_id"] not in value.node_binding.current_results
        await repo.decide_replan(
            run_id, command(value, "APPROVE"), actor="LOCAL_SINGLE_USER", key="minimal-follow-up"
        )
        await repo.apply_replan(run_id)
        owner = await repo.claim_execution(run_id)
        value = await repo.get_run_fresh(run_id)
        await DependencyScheduler(
            event_store=service.event_store,
            checkpoint_store=service.checkpoint_store,
            admission_repository=repo,
            execution_owner=owner,
        ).execute(state=value.runtime, executor=IntegratedTaskExecutor(service, value))
    fresh = await repo.get_run_fresh(run_id)
    receipt = next(iter(fresh.node_binding.risk_admissions.values()))
    assert receipt["decision"] == "FINAL_SUCCESS", receipt
    from src.application.risk_admission import require_final

    result = fresh.node_binding.results[
        fresh.node_binding.current_results[receipt["scope"]["task_id"]]
    ]
    require_final(fresh, result)
    assert sum(kind == "report_synthesis" for kind, _ in calls) == 1


@pytest.mark.parametrize(
    "requirements,expected",
    [
        ({"hard_required": ["$F/missing"]}, False),
        ({"any_of": [["$F/missing-a", "$F/missing-b"]]}, False),
        (
            {
                "any_of": [["$F/missing", "$F/revenue_growth"]],
                "enrichment": ["$F/missing-optional"],
            },
            True,
        ),
    ],
)
async def test_m04_current_closure(database, tmp_path, requirements, expected):  # noqa: F811
    _, sessions = database
    service, value, client = await fixture(tmp_path, sessions, requirements=requirements)
    repo = service.repository
    owner = await repo.claim_execution(value.run.run_id)
    value = await repo.get_run_fresh(value.run.run_id)
    await DependencyScheduler(
        event_store=service.event_store,
        checkpoint_store=service.checkpoint_store,
        admission_repository=repo,
        execution_owner=owner,
    ).execute(state=value.runtime, executor=IntegratedTaskExecutor(service, value))
    fresh = await repo.get_run_fresh(value.run.run_id)
    risk = next(t for t in fresh.runtime.actual_graph.tasks if t.task_type == "risk_analysis")
    assert (risk.task_id in fresh.node_binding.current_results) is expected
    assert client.schemas.count(SCHEMA) == int(expected)


async def test_m08_m09_durable_replay_atomicity_and_consumers(database, tmp_path, monkeypatch):  # noqa: F811
    from src.application.risk_admission import require_final
    from src.domain.node_binding import BindingDenied
    from tests.risk_replan.test_postgresql import fresh as process_read

    _, sessions = database
    service, value, client = await fixture(tmp_path, sessions)
    repo = service.repository
    captured = {}
    commit = repo.commit_node_result
    persist = repo._persist_children
    injected = False

    async def capture(admission, **kwargs):
        if kwargs["task"].task_type == "risk_analysis":
            captured.update(admission=admission, kwargs=deepcopy(kwargs))
        return await commit(admission, **kwargs)

    async def fail(session, aggregate):
        nonlocal injected
        await persist(session, aggregate)
        if aggregate.node_binding.risk_admissions and not injected:
            injected = True
            raise RuntimeError("synthetic admission publication crash")

    monkeypatch.setattr(repo, "commit_node_result", capture)
    monkeypatch.setattr(repo, "_persist_children", fail)
    owner = await repo.claim_execution(value.run.run_id)
    value = await repo.get_run_fresh(value.run.run_id)
    with pytest.raises(ExceptionGroup):
        await DependencyScheduler(
            event_store=service.event_store,
            checkpoint_store=service.checkpoint_store,
            admission_repository=repo,
            execution_owner=owner,
        ).execute(state=value.runtime, executor=IntegratedTaskExecutor(service, value))
    fresh = await repo.get_run_fresh(value.run.run_id)
    assert injected and captured
    assert fresh.node_binding.risk_admissions is None
    assert captured["admission"].task_id not in fresh.node_binding.current_results
    monkeypatch.setattr(repo, "_persist_children", persist)
    raced = await asyncio.gather(
        *(
            SQLAlchemyApplicationRepository(sessions).commit_node_result(
                captured["admission"], **captured["kwargs"]
            )
            for _ in range(2)
        )
    )
    assert raced[0] == raced[1]
    final = raced[0]
    before_calls = client.calls
    before = await process_read(sessions, value.run.run_id)
    replay = await SQLAlchemyApplicationRepository(sessions).commit_node_result(
        captured["admission"], **captured["kwargs"]
    )
    after = await process_read(sessions, value.run.run_id)
    assert replay == final and client.calls == before_calls
    assert before["root"]["risk_admissions"] == after["root"]["risk_admissions"]
    assert before["root"]["results"] == after["root"]["results"]
    assert before["events"] == after["events"]
    assert before["root"] == after["root"]
    assert before["pid"] != after["pid"]
    await retain_trace("B15-B18-atomic-replay", after)
    fresh = await repo.get_run_fresh(value.run.run_id)
    require_final(fresh, final)
    for field, bad in [
        ("run_id", "foreign"),
        ("owner_generation", 999),
        ("reservation_id", "foreign"),
        ("admission_binding_id", "foreign"),
    ]:
        with pytest.raises(BindingDenied):
            require_final(fresh, final.model_copy(update={field: bad}))
    from src.runtime.output_dependencies import resolve_outputs

    synthesis = next(
        t for t in fresh.runtime.actual_graph.tasks if t.task_type == "report_synthesis"
    )
    tampered = deepcopy(fresh)
    tampered.node_binding.risk_admissions = None
    with pytest.raises(
        BindingDenied, match="CONFIRMED_AUTHORITY_MISMATCH: current binding reference"
    ):
        require_final(tampered, final)
    tampered.runtime.binding_ref = tampered.node_binding.reference()
    with pytest.raises(BindingDenied, match="RISK_FINAL"):
        require_final(tampered, final)
    with pytest.raises(BindingDenied, match="RISK_FINAL"):
        repo._current_dependencies(tampered, synthesis)
    with pytest.raises(BindingDenied, match="RISK_FINAL"):
        resolve_outputs(tampered.runtime, synthesis, aggregate=tampered, require_current=True)
    # Actual reserve_node rechecks material under the PostgreSQL transaction owner.
    from pathlib import Path

    bound = fresh.node_binding.resolved_inputs[final.resolved_input_binding_ids[0]]
    evidence = next(r for r in bound.material_refs if r.kind == "EVIDENCE")
    path = Path(evidence.location)
    original = await asyncio.to_thread(path.read_bytes)
    try:
        await asyncio.to_thread(path.write_bytes, b"synthetic corrupt selected material")
        with pytest.raises(BindingDenied, match="MATERIAL"):
            require_final(fresh, final)
        with pytest.raises(BindingDenied):
            await repo.reserve_node(
                owner,
                synthesis,
                IntegratedTaskExecutor(service, fresh).admission_requirements(synthesis),
            )
    finally:
        await asyncio.to_thread(path.write_bytes, original)
    for mutation in ("input_digest", "receipt", "missing_binding", "cycle", "graph"):
        altered = deepcopy(fresh)
        if mutation == "input_digest":
            selected = altered.node_binding.resolved_inputs[bound.resolved_input_binding_id]
            altered.node_binding.resolved_inputs[bound.resolved_input_binding_id] = (
                selected.model_copy(update={"input_digest": "changed"})
            )
        elif mutation == "receipt":
            altered.node_binding.risk_admissions[final.admission_binding_id]["guard"][
                "guard_digest"
            ] = "changed"
        elif mutation == "missing_binding":
            altered.node_binding.resolved_inputs.pop(bound.resolved_input_binding_id)
        elif mutation == "cycle":
            attempt = altered.node_binding.attempts[final.producer_task_id]
            altered.node_binding.attempts[final.producer_task_id] = attempt.model_copy(
                update={
                    "admission": attempt.admission.model_copy(
                        update={
                            "policy_refs": {
                                **attempt.admission.policy_refs,
                                "external_resume_cycle": "foreign-cycle",
                            }
                        }
                    ),
                }
            )
        else:
            altered.node_binding.frozen_graph = altered.node_binding.frozen_graph.model_copy(
                update={"version": 999}
            )
        with pytest.raises(BindingDenied):
            require_final(altered, final)
    # Wrong candidate/replay material cannot reuse the receipt.
    changed = deepcopy(captured["kwargs"])
    changed["resolved_ids"] = []
    with pytest.raises(BindingDenied, match="REPLAY"):
        await commit(captured["admission"], **changed)


async def test_m10_resume_current_admission(database, tmp_path):  # noqa: F811
    from src.application.resume_runtime import current_risk_success
    from src.domain.node_binding import BindingDenied
    from src.infrastructure.database.recovery import RecoveryEvidenceStore
    from tests.external_failure_resume.runtime_fixture import exhaust, legal_fixture, request_for

    _, sessions = database
    repo = SQLAlchemyApplicationRepository(sessions)
    service, value, clients = await legal_fixture(
        tmp_path,
        repository=repo,
        evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions),
        event_store=PostgresRuntimeEventStore(sessions),
        minimal=True,
    )
    failed = await exhaust(service, value)
    request = await request_for(service, failed)
    await repo.resume_external_failure(request, actor=request.actor)
    for client in clients.values():
        client.fail_risk = False
    pending = await repo.get_run_fresh(value.run.run_id)
    owner = await repo.claim_execution(value.run.run_id)
    pending = await repo.get_run_fresh(value.run.run_id)
    await DependencyScheduler(
        event_store=service.event_store,
        checkpoint_store=service.checkpoint_store,
        admission_repository=repo,
        execution_owner=owner,
    ).execute(state=pending.runtime, executor=IntegratedTaskExecutor(service, pending))
    fresh = await SQLAlchemyApplicationRepository(sessions).get_run_fresh(value.run.run_id)
    assert current_risk_success(fresh)
    receipt = next(iter(fresh.node_binding.risk_admissions.values()))
    assert receipt["scope"]["cycle"] != "INITIAL"
    fresh.node_binding.risk_admissions = None
    with pytest.raises(
        BindingDenied, match="CONFIRMED_AUTHORITY_MISMATCH: current binding reference"
    ):
        current_risk_success(fresh)
    fresh.runtime.binding_ref = fresh.node_binding.reference()
    with pytest.raises(BindingDenied, match="RISK_FINAL"):
        current_risk_success(fresh)


async def retain_trace(label, value):
    """Optional external receipt export; never read by production authority."""
    from pathlib import Path

    directory = os.environ.get("D01_PROOF_DIRECTORY")
    if directory:
        path = Path(directory) / (label + ".json")
        await asyncio.to_thread(path.write_text, json.dumps(value, indent=2, default=str))


@pytest.mark.parametrize(
    "case_id,insufficient,malformed,conflict,patch,expected",
    [
        ("A2-05", True, False, False, {}, "EVIDENCE_INSUFFICIENT"),
        ("A6-06", True, False, False, {}, "EVIDENCE_INSUFFICIENT"),
        (
            "A2-10",
            False,
            True,
            False,
            {"summary": "Need more evidence; EVIDENCE_INSUFFICIENT"},
            "CONTRACT_REJECTED",
        ),
        (
            "A2-10-substitution",
            False,
            True,
            False,
            {"summary": "Everything is sufficient"},
            "CONTRACT_REJECTED",
        ),
        ("A2-19", False, False, True, {}, "EVIDENCE_INSUFFICIENT"),
        (
            "B07",
            True,
            False,
            False,
            {
                "evidence_gap_refs": [
                    {
                        "requirement_ref": "model-invented",
                        "reason_code": "EVIDENCE_COVERAGE_LIMITED",
                    }
                ]
            },
            "CONTRACT_REJECTED",
        ),
        ("B08", False, False, False, {"conflict_refs": []}, "CONTRACT_REJECTED"),
        (
            "B12",
            False,
            False,
            False,
            {"summary": "Need more evidence; contradictory prose; EVIDENCE_INSUFFICIENT"},
            "FINAL_SUCCESS",
        ),
    ],
)
async def test_b_matrix_and_shock_preflight(
    database,  # noqa: F811
    tmp_path,
    case_id,
    insufficient,
    malformed,
    conflict,
    patch,
    expected,
):
    from src.application.resume_runtime import current_risk_success
    from tests.risk_replan.test_postgresql import fresh as process_read

    _, sessions = database
    service, value, client = await fixture(
        tmp_path,
        sessions,
        insufficient=insufficient,
        malformed=malformed,
        conflict=conflict,
        payload_patch=patch,
    )
    repo = service.repository
    owner = await repo.claim_execution(value.run.run_id)
    value = await repo.get_run_fresh(value.run.run_id)
    await DependencyScheduler(
        event_store=service.event_store,
        checkpoint_store=service.checkpoint_store,
        admission_repository=repo,
        execution_owner=owner,
    ).execute(state=value.runtime, executor=IntegratedTaskExecutor(service, value))
    fresh = await SQLAlchemyApplicationRepository(sessions).get_run_fresh(value.run.run_id)
    receipt = next(iter(fresh.node_binding.risk_admissions.values()))
    assert receipt["decision"] == expected, receipt
    final = expected == "FINAL_SUCCESS"
    assert (receipt["scope"]["task_id"] in fresh.node_binding.current_results) is final
    if final:
        from src.application.risk_admission import require_final

        result_id = fresh.node_binding.current_results[receipt["scope"]["task_id"]]
        require_final(fresh, fresh.node_binding.results[result_id])
    else:
        assert not current_risk_success(fresh)
    assert fresh.node_binding.replan is None
    assert client.schemas.count(SCHEMA) == 1  # No semantic retry.
    assert client.schemas.count("report_synthesis_research_output_v1") == int(final)
    if case_id == "A2-19":
        assert receipt["guard"]["reason_codes"] == ["UNRESOLVED_STRUCTURED_CONFLICT"]
        assert receipt["closure"]["missing_required"] == []
    durable = await process_read(sessions, value.run.run_id)
    assert durable["root"]["risk_admissions"] == fresh.node_binding.risk_admissions
    await retain_trace(
        case_id,
        {"case_id": case_id, "calls": client.schemas, "expected": expected, "durable": durable},
    )
