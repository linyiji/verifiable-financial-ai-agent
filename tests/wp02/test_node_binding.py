"""Local fixtures only: real Service/Scheduler/Executor, fake data and LLM ports."""

import asyncio
import hashlib
import json
import socket
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters.fmp import FMPAccessStatus, FMPEndpoint
from src.adapters.llm import LLMStructuredResponse
from src.agentic.registry import AgentRegistry
from src.agentic.research_agent import LLMResearchAgent
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.application.evidence_collection import (
    EndpointCollectionStatus,
    EvidenceTaskAcquisitionResult,
)
from src.application.execution import IntegratedTaskExecutor
from src.application.models import RunAggregate
from src.application.persistence import SQLAlchemyApplicationRepository
from src.application.repository import InMemoryApplicationRepository, initialize_binding
from src.application.service import ResearchApplicationService
from src.data.ingestion import EvidenceIngestionResult
from src.data.repository import InMemoryEvidenceRepository
from src.domain.enums import EvidenceAcquisitionStatus, EvidenceCategory, EvidenceStatus
from src.domain.evidence import AcceptedEvidenceBundle, EvidenceRecord
from src.domain.node_binding import BindingDenied, canonical_value, digest, task_semantics
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.task import PlannedTaskGraph, Task
from src.infrastructure.database.base import Base
from src.infrastructure.database.execution_ledger import SQLExecutionLedger
from src.runtime.checkpoint import RuntimeCheckpoint
from src.runtime.scheduler import DependencyScheduler, TaskExecutionContext
from src.runtime.state import RuntimeState


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("WP02_LOCAL_TEST_NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", denied)


def aggregate(types=("evidence_collection", "valuation_analysis", "report_synthesis")):
    run_id = "RUN-WP02-LOCAL-FIXTURE"
    tasks = [
        Task(
            task_id=f"{run_id}:{i}",
            run_id=run_id,
            task_type=kind,
            goal="bounded fixture",
            assigned_agent={
                "valuation_analysis": "valuation_analyst",
                "report_synthesis": "research_lead",
            }.get(kind, "fixture"),
            skill_id=kind + "_v1",
            dependencies=[] if i == 0 else [f"{run_id}:{i - 1}"],
        )
        for i, kind in enumerate(types)
    ]
    plan = PlannedTaskGraph(graph_id="PLAN-WP02", run_id=run_id, tasks=tasks)
    goal = ResearchGoal(
        goal_id="GOAL-WP02",
        research_object_id="OBJECT-WP02",
        goal_text="test scoped admission",
        as_of=date(2026, 9, 14),
    )
    scheme = ResearchSchemeSnapshot(
        scheme_id="SCHEME-WP02",
        research_object_id="OBJECT-WP02",
        goal_id=goal.goal_id,
        generated_by="fixture",
        confirmed_at=datetime.now(UTC),
        calculation_requirements=["required_fixture_calculation_not_in_this_slice"],
    )
    run = ResearchRun(
        run_id=run_id,
        research_object_id="OBJECT-WP02",
        goal_id=goal.goal_id,
        scheme_id=scheme.scheme_id,
        as_of=goal.as_of,
    )
    result = RunAggregate(
        run=run,
        goal=goal,
        scheme=scheme,
        runtime=RuntimeState.create(run_id=run_id, planned_graph=plan),
    )
    initialize_binding(result)
    return result


class FakeCollector:
    def __init__(self, repository, root, application):
        self.repository, self.root, self.application = repository, root, application
        self.calls = 0

    async def collect_scope(self, *, task_id, scope, symbol, run_id, object_id, as_of):
        current = await self.application.get_run_fresh(run_id)
        reservation = current.node_binding.attempts[task_id]
        assert reservation.status == "DISPATCHED"
        assert not reservation.admission.preexisting_inputs
        self.calls += 1
        raw = b'{"company":"fixture"}'
        path = self.root / "raw.json"
        path.write_bytes(raw)
        record = EvidenceRecord(
            evidence_id="EVIDENCE-WP02",
            run_id=run_id,
            object_id=object_id,
            provider="fixture",
            producer_task_id=task_id,
            source_endpoint="profile",
            evidence_category=EvidenceCategory.COMPANY_PROFILE,
            retrieved_at=datetime.now(UTC),
            period="2026",
            as_of=as_of,
            raw_artifact_ref=str(path),
            normalized_field="company_name",
            normalized_value="fixture",
            unit="text",
            snapshot_hash=hashlib.sha256(raw).hexdigest(),
            status=EvidenceStatus.ACCEPTED,
        )
        await self.repository.add(record)
        return EvidenceTaskAcquisitionResult(
            task_id,
            scope,
            EvidenceAcquisitionStatus.COMPLETED,
            EvidenceIngestionResult(
                AcceptedEvidenceBundle(run_id=run_id, records=[record]), (record,), (), (record,)
            ),
            (
                EndpointCollectionStatus(
                    FMPEndpoint.PROFILE, FMPAccessStatus.AVAILABLE, 200, 1, 1, 0, None
                ),
            ),
        )


class FakeLLM:
    provider_name = "teamorouter"
    model_name = "gpt-5.6-sol"

    def __init__(self, repository):
        self.repository, self.calls = repository, []

    async def complete_structured(self, *, messages, response_model, **kwargs):
        payload = json.loads(messages[1].content)
        root = (await self.repository.get_run_fresh(payload["run_id"])).node_binding
        reservation = root.attempts[payload["task_id"]]
        steps = [
            item
            for item in root.resolved_inputs.values()
            if item.admission_binding_id == reservation.admission.admission_binding_id
        ]
        assert steps[-1].step_id == "agent-context"
        for dependency in reservation.admission.dependency_result_bindings:
            assert root.current_results[dependency.producer_task_id] == dependency.result_id
        self.calls.append(payload["task_id"])
        output = response_model(
            summary="fixture qualitative result",
            key_findings=["source retained"],
            risks=[],
            limitations=["not financial release"],
            requires_follow_up=False,
        )
        return LLMStructuredResponse(
            output=output,
            provider=self.provider_name,
            requested_model=self.model_name,
            actual_model=self.model_name,
            attempted_models=(self.model_name,),
        )


async def wired(tmp_path, repository=None, *, persist=True):
    repository = repository or InMemoryApplicationRepository()
    value = aggregate()
    await repository.add_object(
        ResearchObject(
            object_id="OBJECT-WP02", symbol="TEST", company_name="Fixture", exchange="LOCAL"
        )
    )
    evidence = InMemoryEvidenceRepository()
    provider = FakeLLM(repository)
    registry = AgentRegistry()
    store = ResearchAgentOutputArtifactStore(tmp_path / "agent-artifacts")
    for actor, kind in (
        ("valuation_analyst", "valuation_analysis"),
        ("research_lead", "report_synthesis"),
    ):
        registry.register(
            LLMResearchAgent(
                agent_id=actor,
                supported_task_types=frozenset({kind}),
                provider=provider,
                artifacts=store,
            )
        )
    collector = FakeCollector(evidence, tmp_path, repository)
    service = ResearchApplicationService(
        repository=repository,
        evidence_repository=evidence,
        evidence_collector=collector,
        agent_registry=registry,
    )
    # Resolve the fixture composition at initial Confirm, before durable insertion.
    value.node_binding = None
    initialize_binding(value, service=service)
    if persist:
        await repository.add_run(value)
    return service, value, collector, provider


async def admitted(repository, value):
    await repository.add_run(value)
    owner = await repository.claim_execution(value.run.run_id)
    task = value.runtime.actual_graph.tasks[0]
    a = await repository.reserve_node(
        owner, task, {"task": task_semantics(task), "scheme": canonical_value(value.scheme)}
    )
    await repository.dispatch_node(a)
    await repository.enter_node_execution(a)
    return owner, a


async def test_default_service_commits_A_B_R_before_downstream(tmp_path):
    service, value, collector, provider = await wired(tmp_path)
    result = await service.execute_run(value.run.run_id)
    assert collector.calls == 1 and len(provider.calls) == 2
    root = result.node_binding
    assert root.lifecycle == "CLOSED" and root.owner_generation == 2
    assert len(root.current_results) == 3
    assert result.run.status.value == "FAILED"  # unchanged required-calculation closure
    assert all(item.result_version == 1 for item in root.results.values())
    # Optional retained acceptance evidence; never used as runtime input.
    import os
    import shutil
    from pathlib import Path

    destination = os.environ.get("WP02_EVIDENCE_DIR")
    if destination:
        target = Path(destination)
        await asyncio.to_thread(target.mkdir, parents=True, exist_ok=True)
        (target / "primary-root.json").write_text(
            json.dumps(
                SQLAlchemyApplicationRepository._payload(result), indent=2, ensure_ascii=False
            )
        )
        events = [
            item.model_dump(mode="json")
            for item in await service.event_store.replay(value.run.run_id)
        ]
        (target / "primary-events.json").write_text(json.dumps(events, indent=2))
        blobs = {}
        for receipt in root.results.values():
            for record in receipt.output_records:
                original = Path(record.location)
                if record.kind not in {"EVIDENCE", "AGENT_OUTPUT"}:
                    continue
                blob_hash = hashlib.sha256(await asyncio.to_thread(original.read_bytes)).hexdigest()
                copied = target / (blob_hash + ".json")
                shutil.copyfile(original, copied)
                blobs[str(original)] = {"retained_copy": str(copied), "sha256": blob_hash}
        (target / "blob-manifest.json").write_text(json.dumps(blobs, indent=2))
    with pytest.raises(BindingDenied, match="OWNER_ALREADY_CLAIMED"):
        await service.execute_run(value.run.run_id)
    assert collector.calls == 1 and len(provider.calls) == 2


def test_serialization_checkpoint_history_unknown_schema():
    value = aggregate()
    payload = SQLAlchemyApplicationRepository._payload(value)
    restored = SQLAlchemyApplicationRepository._to_aggregate(payload)
    assert SQLAlchemyApplicationRepository._payload(restored) == payload
    checkpoint = RuntimeCheckpoint.capture(checkpoint_id="CHECK-WP02", state=restored.runtime)
    assert (
        checkpoint.restore(planned_graph=restored.runtime.planned_graph).binding_ref
        == restored.runtime.binding_ref
    )
    assert "owner_id" not in checkpoint.model_dump_json()
    payload["node_binding"]["schema_version"] = "unknown"
    with pytest.raises(ValueError):
        SQLAlchemyApplicationRepository._to_aggregate(payload)
    payload.pop("node_binding")
    with pytest.raises(BindingDenied):
        SQLAlchemyApplicationRepository._to_aggregate(payload)
    payload.pop("node_binding_required")
    payload["runtime"].pop("binding_ref")
    assert SQLAlchemyApplicationRepository._to_aggregate(payload).node_binding is None


async def test_claim_exclusion_and_stale_whole_save():
    repo = InMemoryApplicationRepository()
    value = aggregate(("evidence_collection",))
    await repo.add_run(value)
    owners = await asyncio.gather(
        *(repo.claim_execution(value.run.run_id) for _ in range(2)), return_exceptions=True
    )
    assert sum(not isinstance(item, Exception) for item in owners) == 1
    with pytest.raises(BindingDenied, match="STALE_WRITE_REJECTED"):
        await repo.save_run(value)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("run_id", "foreign"),
        ("task_id", "foreign"),
        ("attempt_reservation_id", "wrong"),
        ("task_fingerprint", "wrong"),
        ("scheme_hash", "wrong"),
    ],
)
async def test_wrong_admission_identity_rejected(field, bad):
    repo = InMemoryApplicationRepository()
    value = aggregate(("evidence_collection",))
    _, a = await admitted(repo, value)
    with pytest.raises((BindingDenied, KeyError)):
        await repo.check_invocation(a.model_copy(update={field: bad}))


async def test_unknown_generation_and_missing_context_fail_closed(tmp_path):
    repo = InMemoryApplicationRepository()
    value = aggregate(("evidence_collection",))
    owner, a = await admitted(repo, value)
    await repo.close_execution(owner, unknown=True)
    with pytest.raises(BindingDenied, match="STALE_WRITE_REJECTED"):
        await repo.bind_resolved_inputs(a, step_id="late", materials=(), payload={})
    service = ResearchApplicationService(repository=repo)
    executor = IntegratedTaskExecutor(service, value)
    with pytest.raises(BindingDenied):
        await executor.execute(
            value.runtime.actual_graph.tasks[0],
            TaskExecutionContext(run_id=value.run.run_id, attempt=1),
        )
    scheduler = DependencyScheduler(
        event_store=service.event_store, checkpoint_store=service.checkpoint_store
    )
    with pytest.raises(BindingDenied):
        await scheduler.execute(state=value.runtime, executor=executor)
    with pytest.raises(BindingDenied):
        await executor._execute_evidence_collection(value.runtime.actual_graph.tasks[0])


@pytest.mark.parametrize("mode", ["UNKNOWN", "RECOVERABLE_V1"])
async def test_nondefault_modes_denied(mode):
    repo = InMemoryApplicationRepository()
    value = aggregate()
    value.node_binding.execution_mode = mode
    await repo.add_run(value)
    with pytest.raises(BindingDenied, match="EXECUTION_MODE_CONFLICT"):
        await repo.claim_execution(value.run.run_id)


async def test_unknown_handler_and_extensions_reject_before_effects(tmp_path):
    service, value, collector, provider = await wired(tmp_path)
    task = value.runtime.actual_graph.tasks[0].model_copy(
        update={"task_type": "unknown", "skill_id": "unknown"}
    )
    with pytest.raises(BindingDenied, match="UNSUPPORTED_NEW_BOUND_HANDLER"):
        IntegratedTaskExecutor(service, value).admission_requirements(task)
    service.calculation_extensions.append(object())
    task = task.model_copy(
        update={"task_type": "fundamental_analysis", "skill_id": "fundamental_analysis_v1"}
    )
    with pytest.raises(BindingDenied, match="UNSUPPORTED_NEW_BOUND_HANDLER"):
        IntegratedTaskExecutor(service, value).admission_requirements(task)
    assert collector.calls == 0 and provider.calls == []


async def test_sqlite_cas_rollback_shared_writer_and_v1_denial(tmp_path):
    from src.domain.execution_contract import ContractDenied, ExecutionBudget
    from src.infrastructure.database.artifacts import SQLAlchemyRunRecordRepository

    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "isolated.sqlite"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyApplicationRepository(sessions)
    value = aggregate(("evidence_collection",))
    owner, a = await admitted(repo, value)
    before = digest((await repo.get_run_fresh(value.run.run_id)).node_binding)
    with pytest.raises(BindingDenied):
        await repo.save_run(value)
    assert digest((await repo.get_run_fresh(value.run.run_id)).node_binding) == before
    with pytest.raises(BindingDenied):
        await repo.save_run_with_projection_watermark(
            value, projection_sequence=999, expected_binding_ref=value.node_binding.reference()
        )
    assert digest((await repo.get_run_fresh(value.run.run_id)).node_binding) == before
    from src.infrastructure.database.phase4_product import SQLAlchemyPhase4ProjectionRepository
    from src.phase4_product.durability import ProjectionCommitFence, ProjectionWriteSet

    async with sessions() as session:
        with pytest.raises(BindingDenied):
            await SQLAlchemyPhase4ProjectionRepository(session).publish(
                ProjectionWriteSet(
                    fence=ProjectionCommitFence(run_id=value.run.run_id, expected_revision=1),
                    tasks=(value.runtime.actual_graph.tasks[0],),
                )
            )
    records = SQLAlchemyRunRecordRepository(sessions)
    with pytest.raises(BindingDenied):
        await records.save_task(value.runtime.actual_graph.tasks[0])
    ledger = SQLExecutionLedger(sessions)
    for intent in ("intent1", "intent2"):
        await ledger.create_intent(
            intent,
            ExecutionBudget(physical_calls=2, execution_calls=1, check_calls=1, decision_calls=0),
            100,
        )
        with pytest.raises(ContractDenied, match="V1_BOUND_PATH_DISABLED"):
            await ledger.admit_run(intent, value.run.run_id)
    with pytest.raises(ContractDenied, match="STATE_REFRESH_REQUIRED"):
        await ledger.guard_run_entry("missing-root")
    with pytest.raises(RuntimeError):
        async with repo._binding_transaction(value.run.run_id) as current:
            current.node_binding.current_results["bad"] = "partial"
            raise RuntimeError("injected rollback")
    assert digest((await repo.get_run_fresh(value.run.run_id)).node_binding) == before
    await engine.dispose()


@pytest.mark.parametrize("tamper", ["result_ref", "outputs", "task_output"])
async def test_same_revision_whole_writer_cannot_change_node_material(tamper):
    repo = InMemoryApplicationRepository()
    value = aggregate(("evidence_collection",))
    await repo.add_run(value)
    changed = await repo.get_run_fresh(value.run.run_id)
    if tamper == "result_ref":
        changed.runtime.actual_graph.tasks[0].result_ref = "forged"
    elif tamper == "outputs":
        changed.runtime.completed_output_refs["forged"] = ["forged"]
    else:
        changed.artifacts.task_outputs["forged"] = {"value": 123}
    with pytest.raises(BindingDenied, match="STALE_WRITE_REJECTED"):
        await repo.save_run(changed)


async def test_input_digest_and_reservation_reject_result_commit():
    repo = InMemoryApplicationRepository()
    value = aggregate(("evidence_collection",))
    owner, a = await admitted(repo, value)
    step = await repo.bind_resolved_inputs(
        a, step_id="acquisition", materials=(), payload={"exact": 1}
    )
    # Injected durable corruption, not an application update route.
    repo._runs[value.run.run_id].node_binding.resolved_inputs[step.resolved_input_binding_id] = (
        step.model_copy(update={"input_digest": "bad"})
    )
    with pytest.raises(BindingDenied, match="IDENTITY_MISMATCH"):
        await repo.commit_node_result(
            a,
            task=value.runtime.actual_graph.tasks[0],
            artifacts=value.artifacts,
            output_records=(),
            resolved_ids=(step.resolved_input_binding_id,),
        )
    assert not (await repo.get_run_fresh(value.run.run_id)).node_binding.current_results


@pytest.mark.parametrize("change", ["pointer", "invalidate", "digest", "graph", "task"])
async def test_downstream_rejects_changed_current_identity(tmp_path, change):
    service, value, _, provider = await wired(tmp_path)
    owner = await service.repository.claim_execution(value.run.run_id)
    executor = IntegratedTaskExecutor(service, await service.repository.validate_execution(owner))
    first = value.runtime.actual_graph.tasks[0]
    a = await service.repository.reserve_node(owner, first, executor.admission_requirements(first))
    await service.repository.dispatch_node(a)
    await executor.execute(first, TaskExecutionContext(run_id=first.run_id, attempt=1, admission=a))
    raw = service.repository._runs[value.run.run_id]
    root = raw.node_binding
    ref = root.current_results[first.task_id]
    if change == "pointer":
        root.current_results[first.task_id] = "wrong"
    elif change == "invalidate":
        root.invalidation_refs.append(ref)
    elif change == "digest":
        root.results[ref] = root.results[ref].model_copy(update={"result_digest": "wrong"})
    elif change == "graph":
        raw.runtime.actual_graph.version += 1
    else:
        raw.runtime.task(first.task_id).goal = "changed work"
    next_task = value.runtime.actual_graph.tasks[1]
    with pytest.raises(BindingDenied):
        await service.repository.reserve_node(
            owner, next_task, executor.admission_requirements(next_task)
        )
    assert provider.calls == []


async def test_wrong_run_owner_rejects_before_scheduler(tmp_path):
    service, value, collector, _ = await wired(tmp_path)
    from src.domain.node_binding import OwnerToken

    with pytest.raises(BindingDenied, match="IDENTITY_MISMATCH"):
        await service.execute_run(
            value.run.run_id,
            execution_owner=OwnerToken(run_id="foreign", owner_generation=1, owner_id="foreign"),
        )
    assert collector.calls == 0


async def test_default_backend_service_chain_with_isolated_sqlite(tmp_path):
    from src.application.persistence import SessionFactoryEvidenceRepository
    from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "service.sqlite"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repository = SQLAlchemyApplicationRepository(sessions)
    service, value, collector, provider = await wired(tmp_path, repository)
    evidence = SessionFactoryEvidenceRepository(sessions)
    service.evidence_repository = collector.repository = evidence
    backend = object.__new__(PostgreSQLPhase4ProductBackend)
    backend.service, backend.sessions = service, sessions
    await backend._execute_started_run(value.run.run_id)
    current = await repository.get_run_fresh(value.run.run_id)
    assert len(current.node_binding.current_results) == 3
    assert len(provider.calls) == 2
    assert current.node_binding.lifecycle == "CLOSED"
    with pytest.raises(BindingDenied):
        await backend._publish_latest_projection_watermark(
            value.run.run_id, expected_binding_ref=value.node_binding.reference()
        )
    await engine.dispose()


async def test_native_only_calculations_bind_each_step(tmp_path):
    from src.application.repository import node_invocation

    repo = InMemoryApplicationRepository()
    value = aggregate(("evidence_collection", "fundamental_analysis"))
    await repo.add_run(value)
    await repo.add_object(
        ResearchObject(
            object_id="OBJECT-WP02", symbol="TEST", company_name="Fixture", exchange="LOCAL"
        )
    )
    evidence = InMemoryEvidenceRepository()

    class FinancialCollector(FakeCollector):
        async def collect_scope(self, *, task_id, scope, symbol, run_id, object_id, as_of):
            assert node_invocation.get().task_id == task_id
            self.calls += 1
            records = []
            for i, (field, period, number) in enumerate(
                [
                    ("revenue", "FY2024", "100"),
                    ("revenue", "FY2025", "150"),
                    ("ebitda", "FY2025", "30"),
                ]
            ):
                raw = json.dumps({"field": field, "value": number, "period": period}).encode()
                path = self.root / f"financial-{i}.json"
                path.write_bytes(raw)
                record = EvidenceRecord(
                    evidence_id=f"F-{i}",
                    run_id=run_id,
                    object_id=object_id,
                    provider="fixture",
                    producer_task_id=task_id,
                    source_endpoint="income",
                    evidence_category=EvidenceCategory.FINANCIAL_STATEMENT,
                    retrieved_at=datetime.now(UTC),
                    period=period,
                    as_of=as_of,
                    raw_artifact_ref=str(path),
                    normalized_field=field,
                    normalized_value=number,
                    unit="USD",
                    currency="USD",
                    snapshot_hash=hashlib.sha256(raw).hexdigest(),
                    status=EvidenceStatus.ACCEPTED,
                )
                records.append(record)
                await self.repository.add(record)
            return EvidenceTaskAcquisitionResult(
                task_id,
                scope,
                EvidenceAcquisitionStatus.COMPLETED,
                EvidenceIngestionResult(
                    AcceptedEvidenceBundle(run_id=run_id, records=records),
                    tuple(records),
                    (),
                    tuple(records),
                ),
                (),
            )

    collector = FinancialCollector(evidence, tmp_path, repo)
    service = ResearchApplicationService(
        repository=repo, evidence_repository=evidence, evidence_collector=collector
    )
    current = await service.execute_run(value.run.run_id)
    assert len(current.artifacts.calculations) == 2
    assert {str(item.output_value) for item in current.artifacts.calculations} == {"0.5", "0.2"}
    from src.application.repository import compare_whole
    from src.domain.node_binding import calculation_core

    changed = await repo.get_run_fresh(value.run.run_id)
    changed.artifacts.calculations[0].proof_ref = "proof://fixture-assurance-only"
    assert calculation_core(changed.artifacts.calculations[0]) == calculation_core(
        current.artifacts.calculations[0]
    )
    compare_whole(current, changed)
    changed.artifacts.calculations[0].output_value = 999
    with pytest.raises(BindingDenied, match="calculation core"):
        compare_whole(current, changed)
    assert (
        len(
            [
                item
                for item in current.node_binding.resolved_inputs.values()
                if item.step_id.startswith("calculation:")
            ]
        )
        == 3
    )


async def test_duplicate_exact_executor_reservation_invokes_once(tmp_path):
    service, value, collector, provider = await wired(tmp_path)
    repo = service.repository
    owner = await repo.claim_execution(value.run.run_id)
    executor = IntegratedTaskExecutor(service, await repo.validate_execution(owner))
    task = value.runtime.actual_graph.tasks[0]
    a = await repo.reserve_node(owner, task, executor.admission_requirements(task))
    await repo.dispatch_node(a)
    context = TaskExecutionContext(run_id=task.run_id, attempt=1, admission=a)
    results = await asyncio.gather(
        executor.execute(task, context), executor.execute(task, context), return_exceptions=True
    )
    assert sum(isinstance(item, BindingDenied) for item in results) == 1
    assert collector.calls == 1 and not provider.calls


async def test_result_failure_leaves_raw_orphan_and_zero_downstream(tmp_path, monkeypatch):
    service, value, collector, provider = await wired(tmp_path)

    async def fail(*args, **kwargs):
        raise BindingDenied("STALE_WRITE_REJECTED", "injected result commit")

    monkeypatch.setattr(service.repository, "commit_node_result", fail)
    with pytest.raises(ExceptionGroup):
        await service.execute_run(value.run.run_id)
    current = await service.repository.get_run_fresh(value.run.run_id)
    assert (tmp_path / "raw.json").is_file()
    assert not current.node_binding.current_results and not provider.calls
    assert current.node_binding.lifecycle == "RESULT_UNKNOWN"
    events = await service.event_store.replay(value.run.run_id)
    assert not any(
        event.type.value in {"task.completed", "run.completed", "release.completed"}
        for event in events
    )
    assert current.artifacts.closure_diagnostic["code"] == "STALE_WRITE_REJECTED"


async def test_independent_task_patches_preserve_both_results():
    repo = InMemoryApplicationRepository()
    value = aggregate(("valuation_analysis", "valuation_analysis"))
    value.runtime.actual_graph.tasks[1].dependencies = []
    value.runtime.planned_graph.tasks[1].dependencies = []
    value.node_binding = None
    initialize_binding(value)
    await repo.add_run(value)
    await repo.add_object(
        ResearchObject(
            object_id="OBJECT-WP02", symbol="TEST", company_name="Fixture", exchange="LOCAL"
        )
    )
    service = ResearchApplicationService(repository=repo)
    current = await service.execute_run(value.run.run_id)
    assert len(current.node_binding.current_results) == 2
    assert len(current.artifacts.task_outputs) == 2


async def test_run_identity_cannot_change_at_same_revision():
    repo = InMemoryApplicationRepository()
    value = aggregate()
    await repo.add_run(value)
    changed = await repo.get_run_fresh(value.run.run_id)
    changed.run.execution_target = "different"
    with pytest.raises(BindingDenied, match="IDENTITY_MISMATCH"):
        await repo.save_run(changed)


def test_business_work_and_input_hashes_are_distinct_from_audit_state():
    from src.domain.node_binding import GraphIdentity

    value = aggregate()
    graph = value.runtime.actual_graph
    before = GraphIdentity.of(graph)
    graph.tasks[0].progress = 0.5
    graph.tasks[0].attempt_count = 2
    assert GraphIdentity.of(graph) == before
    graph.tasks[0].goal = "changed authorized scope"
    assert GraphIdentity.of(graph) != before
    assert digest({"as_of": "2026-09-14"}) != digest({"as_of": "2026-09-13"})
    with pytest.raises(BindingDenied):
        digest(float("nan"))
    with pytest.raises(BindingDenied):
        digest(object())


async def test_initial_scheme_confirmation_roundtrip(tmp_path):
    from src.application.models import ResearchRunDraft

    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "confirm.db"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repo = SQLAlchemyApplicationRepository(async_sessionmaker(engine, expire_on_commit=False))
    value = aggregate()
    await repo.add_object(
        ResearchObject(
            object_id="OBJECT-WP02", symbol="TEST", company_name="Fixture", exchange="LOCAL"
        )
    )
    draft = ResearchRunDraft(
        draft_id="DRAFT-WP02",
        goal=value.goal,
        scheme_snapshot=value.scheme.model_copy(update={"confirmed_at": None}),
    )
    await repo.add_draft(draft)

    class Planner:
        def plan(self, *, run_id, goal, scheme):
            return value.runtime.planned_graph

    service = ResearchApplicationService(
        repository=repo, planner=Planner(), run_id_factory=lambda: value.run.run_id
    )
    created = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    fresh = await repo.get_run_fresh(created.run.run_id)
    assert fresh.scheme.confirmed_at is not None
    assert fresh.node_binding == created.node_binding
    assert fresh.node_binding.owner_generation == 0
    await engine.dispose()


async def test_preexisting_evidence_cannot_be_silently_omitted():
    repo = InMemoryApplicationRepository()
    value = aggregate(("evidence_collection",))
    value.runtime.actual_graph.tasks[0].task_input_evidence_ids = ["missing-original"]
    await repo.add_run(value)
    owner = await repo.claim_execution(value.run.run_id)
    task = value.runtime.actual_graph.tasks[0]
    with pytest.raises(BindingDenied, match="preexisting Evidence"):
        await repo.reserve_node(
            owner, task, {"task": task_semantics(task), "scheme": canonical_value(value.scheme)}
        )
    assert not (await repo.get_run_fresh(value.run.run_id)).node_binding.attempts


async def test_result_snapshot_must_match_scoped_patch(tmp_path, monkeypatch):
    service, value, collector, provider = await wired(tmp_path)
    commit = service.repository.commit_node_result

    async def changed(admission, **kwargs):
        kwargs["artifacts"].task_outputs[admission.task_id] = {"forged": True}
        return await commit(admission, **kwargs)

    monkeypatch.setattr(service.repository, "commit_node_result", changed)
    with pytest.raises(ExceptionGroup):
        await service.execute_run(value.run.run_id)
    current = await service.repository.get_run_fresh(value.run.run_id)
    assert not current.node_binding.current_results
    assert not provider.calls


@pytest.mark.parametrize(
    "method,arguments",
    [
        ("add_tasks", {"tasks": "tasks"}),
        ("add_node", {"task": "task"}),
        ("add_edge", {"source_task_id": "first", "target_task_id": "second"}),
        ("remove_edge", {"source_task_id": "first", "target_task_id": "second"}),
        (
            "replace_dependency",
            {
                "target_task_id": "second",
                "old_dependency_id": "first",
                "new_dependency_id": "third",
            },
        ),
        (
            "insert_node_between",
            {"task": "task", "predecessor_task_id": "first", "successor_task_id": "second"},
        ),
    ],
)
async def test_every_graph_mutation_rejects_before_swap_or_event(method, arguments):
    from src.runtime.events import InMemoryRuntimeEventStore
    from src.runtime.graph import GraphMutationService

    value = aggregate()
    repo = InMemoryApplicationRepository()
    await repo.add_run(value)
    events = InMemoryRuntimeEventStore()
    graph = GraphMutationService(events, repository=repo)
    task = value.runtime.actual_graph.tasks[0].model_copy(update={"task_id": "new"})
    arguments = {
        key: ([task] if val == "tasks" else task if val == "task" else val)
        for key, val in arguments.items()
    }
    before = digest(value.runtime.actual_graph)
    with pytest.raises(BindingDenied):
        await getattr(graph, method)(state=value.runtime, request=None, actor=None, **arguments)
    assert digest(value.runtime.actual_graph) == before
    assert not await events.replay(value.run.run_id)


async def test_closure_rejected_before_started_or_assurance(tmp_path):
    from sqlalchemy import select

    from src.application.closure_recovery import ClosureRecoveryRecordRow, recover_closure

    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "closure.db"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyApplicationRepository(sessions)
    value = aggregate()
    await repo.add_run(value)
    before = SQLAlchemyApplicationRepository._payload(await repo.get_run_fresh(value.run.run_id))

    class ForbiddenService:
        async def _assure_and_release(self, *args):
            raise AssertionError("assurance must not run")

    with pytest.raises(BindingDenied, match="closure recovery excluded"):
        await recover_closure(
            sessions=sessions,
            service=ForbiddenService(),
            run_id=value.run.run_id,
            expected_snapshot_hash="unused",
            source_sha="a" * 40,
            owner_authorization="REUSE_REVIEW_AND_VERIFIED_PROOF_RELEASE_REPORT_MEMORY_ONCE",
            materialize_memory=None,
        )
    assert (
        SQLAlchemyApplicationRepository._payload(await repo.get_run_fresh(value.run.run_id))
        == before
    )
    async with sessions() as session:
        assert not list(await session.scalars(select(ClosureRecoveryRecordRow)))
    await engine.dispose()


@pytest.mark.parametrize("missing", ["schema_version", "execution_mode", "owner_generation"])
def test_required_binding_fields_are_not_invented(missing):
    payload = SQLAlchemyApplicationRepository._payload(aggregate())
    payload["node_binding"].pop(missing)
    with pytest.raises(BindingDenied):
        SQLAlchemyApplicationRepository._to_aggregate(payload)


async def test_direct_scheduler_reentry_with_same_owner_is_rejected():
    from src.runtime.events import InMemoryRuntimeEventStore

    repo = InMemoryApplicationRepository()
    value = aggregate()
    await repo.add_run(value)
    owner = await repo.claim_execution(value.run.run_id)
    await repo.begin_scheduler(owner)
    events = InMemoryRuntimeEventStore()
    scheduler = DependencyScheduler(
        event_store=events, checkpoint_store=None, admission_repository=repo, execution_owner=owner
    )
    with pytest.raises(BindingDenied, match="Scheduler already started"):
        await scheduler.execute(state=value.runtime, executor=None)
    assert not await events.replay(value.run.run_id)


async def test_legacy_fixture_uri_is_readable_but_not_new_bound_material(tmp_path):
    # The old integrated output-dependency fixtures use fixture:// refs without
    # retained raw bytes. This is an intentional new-bound contract exclusion.
    from src.application.evidence_collection import FixtureEvidenceCollector

    service, value, collector, provider = await wired(tmp_path)
    service.evidence_collector = FixtureEvidenceCollector(
        repository=service.evidence_repository, fixture_path=service.fixture_path
    )
    # Fixture dataset belongs to NVDA; keep the synthetic Run/Object identity.
    obj = await service.repository.get_object("OBJECT-WP02")
    obj.symbol = "NVDA"
    service.repository._objects[obj.object_id] = obj
    with pytest.raises(ExceptionGroup) as rejected:
        await service.execute_run(value.run.run_id)
    assert any(
        isinstance(e, BindingDenied) and e.subject == "raw evidence bytes"
        for e in rejected.value.exceptions
    )
    current = await service.repository.get_run_fresh(value.run.run_id)
    assert not current.node_binding.current_results and not provider.calls


async def test_stripped_executor_marker_cannot_bypass_invocation(tmp_path):
    service, value, collector, provider = await wired(tmp_path)
    value.node_binding = None
    value.runtime.binding_ref = None
    executor = IntegratedTaskExecutor(service, value)
    task = value.runtime.actual_graph.tasks[0]
    with pytest.raises(BindingDenied, match="read only"):
        await executor._execute_evidence_collection(task)
    with pytest.raises(BindingDenied, match="read only"):
        await executor.execute(task, TaskExecutionContext(run_id=task.run_id, attempt=1))
    assert collector.calls == 0 and not provider.calls


async def r1_snapshot(service, run_id, collector, provider, calls):
    current = await service.repository.get_run_fresh(run_id)
    return {
        "aggregate": SQLAlchemyApplicationRepository._payload(current),
        "events": [e.model_dump(mode="json") for e in await service.event_store.replay(run_id)],
        "calls": {"collector": collector.calls, "provider": len(provider.calls), **calls},
    }


def retain_r1_snapshots(case, snapshots):
    import os
    from pathlib import Path

    destination = os.environ.get("WP02_R1_EVIDENCE_DIR")
    if destination:
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        (target / (case + ".json")).write_text(json.dumps(snapshots, indent=2))


async def r1_wired(tmp_path, backend):
    engine = None
    if backend == "sqlite":
        from src.application.persistence import SessionFactoryEvidenceRepository

        engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "r1.sqlite"))
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        service, value, collector, provider = await wired(
            tmp_path, SQLAlchemyApplicationRepository(sessions)
        )
        service.evidence_repository = collector.repository = SessionFactoryEvidenceRepository(
            sessions
        )
    else:
        service, value, collector, provider = await wired(tmp_path)
    return service, value, collector, provider, engine


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
@pytest.mark.parametrize(
    "reentry",
    [
        "same_owner",
        "no_owner",
        "foreign_owner",
        "foreign_run",
        "stale_generation",
        "same_owner_existing_policy",
    ],
)
async def test_r1_service_reentry_preserves_active_execution_and_first_finishes(
    tmp_path, monkeypatch, backend, reentry
):
    from src.domain.enums import RunStatus
    from src.domain.runtime_event import RuntimeEventType

    service, value, collector, provider, engine = await r1_wired(tmp_path, backend)
    run_id = value.run.run_id
    entered, resume = asyncio.Event(), asyncio.Event()
    calls = {"tool": 0, "save_run": 0, "close_execution": 0, "assurance_fixture": 0}
    collect = collector.collect_scope
    save_run, close = service.repository.save_run, service.repository.close_execution

    async def paused_collect(**kwargs):
        result = await collect(**kwargs)
        entered.set()  # Real Executor is DISPATCHED; raw fake bytes exist, no lock is held.
        await resume.wait()
        return result

    async def counted_save(*args, **kwargs):
        calls["save_run"] += 1
        return await save_run(*args, **kwargs)

    async def counted_close(*args, **kwargs):
        calls["close_execution"] += 1
        return await close(*args, **kwargs)

    async def forbidden_tool(*args, **kwargs):
        calls["tool"] += 1
        raise AssertionError("qualitative R1 fixture must not call a capability")

    async def successful_assurance_fixture(current):
        # Isolate Service success/close control flow; this is NOT financial Release evidence.
        calls["assurance_fixture"] += 1
        assert len(current.node_binding.current_results) == 3
        service._apply_terminal_lifecycle(
            current, status=RunStatus.RELEASED, terminal_at=datetime.now(UTC)
        )

    async def completion_fixture(current):
        await service.event_store.emit(
            run_id=current.run.run_id,
            event_type=RuntimeEventType.RUN_COMPLETED,
            payload={"status": "RELEASED", "fixture": "R1_CONTROL_FLOW_ONLY"},
        )

    monkeypatch.setattr(collector, "collect_scope", paused_collect)
    monkeypatch.setattr(service.repository, "save_run", counted_save)
    monkeypatch.setattr(service.repository, "close_execution", counted_close)
    monkeypatch.setattr(service.tool_runtime, "execute", forbidden_tool)
    if reentry != "same_owner_existing_policy":
        monkeypatch.setattr(service, "_assure_and_release", successful_assurance_fixture)
        monkeypatch.setattr(service, "_emit_release_completion", completion_fixture)
    snapshots = {"S0": await r1_snapshot(service, run_id, collector, provider, calls)}
    first = None
    try:
        owner = await service.repository.claim_execution(run_id)
        first = asyncio.create_task(service.execute_run(run_id, execution_owner=owner))
        await asyncio.wait_for(entered.wait(), timeout=5)
        snapshots["S1"] = await r1_snapshot(service, run_id, collector, provider, calls)
        root = snapshots["S1"]["aggregate"]["node_binding"]
        assert root["scheduler_started"] and root["lifecycle"] == "ACTIVE"
        assert root["owner_generation"] == 1
        assert any(a["status"] == "DISPATCHED" for a in root["attempts"].values())
        assert not first.done()
        duplicate_owner = {
            "same_owner": owner,
            "same_owner_existing_policy": owner,
            "no_owner": None,
            "foreign_owner": owner.model_copy(update={"owner_id": "foreign-owner"}),
            "foreign_run": owner.model_copy(update={"run_id": "foreign-run"}),
            "stale_generation": owner.model_copy(update={"owner_generation": 0}),
        }[reentry]
        with pytest.raises(BindingDenied):
            await service.execute_run(run_id, execution_owner=duplicate_owner)
        snapshots["S2"] = await r1_snapshot(service, run_id, collector, provider, calls)
        assert snapshots["S2"] == snapshots["S1"]  # Whole root/task/result/events/counters.
        assert not first.done()
        resume.set()
        completed = await asyncio.wait_for(first, timeout=5)
        snapshots["S3"] = await r1_snapshot(service, run_id, collector, provider, calls)
        existing_policy = reentry == "same_owner_existing_policy"
        assert completed.run.status is (RunStatus.FAILED if existing_policy else RunStatus.RELEASED)
        if existing_policy:
            assert (
                completed.artifacts.closure_diagnostic["code"] == "REQUIRED_CALCULATION_UNAVAILABLE"
            )
        root = completed.node_binding
        assert root.lifecycle == "CLOSED" and root.owner_generation == 2
        assert root.owner_id == owner.owner_id and root.execution_mode == "DEFAULT"
        assert len(root.current_results) == len(root.results) == 3
        assert all(a.status == "COMMITTED" for a in root.attempts.values())
        assert all(r.owner_generation == 1 for r in root.results.values())
        for attempt in root.attempts.values():
            for dependency in attempt.admission.dependency_result_bindings:
                assert root.current_results[dependency.producer_task_id] == dependency.result_id
        assert len(provider.calls) == 2 and collector.calls == 1
        assert calls == {
            "tool": 0,
            "save_run": 1,
            "close_execution": 1,
            "assurance_fixture": 0 if existing_policy else 1,
        }
        events = await service.event_store.replay(run_id)
        assert sum(e.type is RuntimeEventType.RUN_FAILED for e in events) == int(existing_policy)
        assert sum(e.type is RuntimeEventType.RUN_COMPLETED for e in events) == int(
            not existing_policy
        )
    finally:
        resume.set()
        if first is not None:
            await asyncio.gather(first, return_exceptions=True)
        retain_r1_snapshots(f"{backend}-{reentry}", snapshots)
        if engine is not None:
            await engine.dispose()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
@pytest.mark.parametrize("failure", ["binding_denied", "runtime_error"])
async def test_r1_admitted_execution_failure_still_terminalizes(
    tmp_path, monkeypatch, backend, failure
):
    from src.domain.runtime_event import RuntimeEventType

    service, value, collector, provider, engine = await r1_wired(tmp_path, backend)
    run_id = value.run.run_id
    snapshots = {}

    async def fail_after_admission(**kwargs):
        current = await service.repository.get_run_fresh(run_id)
        assert current.node_binding.scheduler_started
        assert current.node_binding.attempts[kwargs["task_id"]].status == "DISPATCHED"
        snapshots["admitted"] = SQLAlchemyApplicationRepository._payload(current)
        if failure == "binding_denied":
            raise BindingDenied("MISSING_INPUT", "R1 genuine admitted failure")
        raise RuntimeError("R1 genuine admitted failure")

    monkeypatch.setattr(collector, "collect_scope", fail_after_admission)
    try:
        with pytest.raises(ExceptionGroup) as raised:
            await service.execute_run(run_id)
        expected = BindingDenied if failure == "binding_denied" else RuntimeError
        assert any(isinstance(e, expected) for e in raised.value.exceptions)
        current = await service.repository.get_run_fresh(run_id)
        snapshots["terminal"] = SQLAlchemyApplicationRepository._payload(current)
        assert current.run.status.value == "FAILED"
        assert current.node_binding.lifecycle == "RESULT_UNKNOWN"
        assert current.node_binding.owner_generation == 2
        assert not current.node_binding.current_results
        assert all(a.status == "RESULT_UNKNOWN" for a in current.node_binding.attempts.values())
        events = await service.event_store.replay(run_id)
        snapshots["events"] = [e.model_dump(mode="json") for e in events]
        assert sum(e.type is RuntimeEventType.RUN_FAILED for e in events) == 1
        assert not provider.calls
    finally:
        retain_r1_snapshots(f"{backend}-{failure}", snapshots)
        if engine is not None:
            await engine.dispose()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
async def test_r1_admitted_preflight_failure_still_terminalizes(tmp_path, monkeypatch, backend):
    from src.domain.runtime_event import RuntimeEventType

    service, value, collector, provider, engine = await r1_wired(tmp_path, backend)

    def unsupported(executor, task):
        raise BindingDenied("UNSUPPORTED_NEW_BOUND_HANDLER", task.task_id)

    monkeypatch.setattr(IntegratedTaskExecutor, "admission_requirements", unsupported)
    try:
        with pytest.raises(BindingDenied, match="UNSUPPORTED_NEW_BOUND_HANDLER"):
            await service.execute_run(value.run.run_id)
        current = await service.repository.get_run_fresh(value.run.run_id)
        assert current.node_binding.scheduler_started
        assert current.node_binding.lifecycle == "RESULT_UNKNOWN"
        assert current.node_binding.owner_generation == 2
        assert current.run.status.value == "FAILED"
        assert not current.node_binding.attempts and not current.node_binding.current_results
        assert collector.calls == 0 and not provider.calls
        events = await service.event_store.replay(value.run.run_id)
        assert sum(e.type is RuntimeEventType.RUN_FAILED for e in events) == 1
    finally:
        if engine is not None:
            await engine.dispose()
