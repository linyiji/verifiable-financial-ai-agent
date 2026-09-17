"""Known-failure continuation through the default repository/scheduler/executor."""

from pathlib import Path

import pytest

from src.adapters.llm.provider import LLMFailureClassification as Code
from src.adapters.llm.provider import LLMProviderError
from src.agentic.composition import build_research_agent_registry
from src.agentic.recovery import AdaptiveRecovery
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.application.repository import InMemoryApplicationRepository, initialize_binding
from src.application.service import ResearchApplicationService
from src.data.ingestion import EvidenceIngestionResult
from src.data.repository import InMemoryEvidenceRepository
from src.domain.evidence import AcceptedEvidenceBundle, EvidenceRecord
from src.domain.recovery import Candidate, retain_attempt_facts
from src.domain.research_object import ResearchObject
from src.infrastructure.database.recovery import MemoryRecoveryEvidenceStore
from tests.unit.agentic.test_adaptive_recovery import Client
from tests.wp02.test_node_binding import FakeCollector, aggregate


class LocalClient(Client):
    async def complete_structured(self, **kwargs):
        retain_attempt_facts(dispatch_state="NOT_DISPATCHED", dispatch_basis="LOCAL_PREFLIGHT")
        try:
            return await super().complete_structured(**kwargs)
        except LLMProviderError as exc:
            raise LLMProviderError(
                "Deterministic local failure before external dispatch",
                failure_classification=exc.failure_classification,
                provider=self.provider_name,
                model=self.model_name,
                retryable=exc.failure_classification is Code.READ_TIMEOUT,
            ) from exc


class FinancialCollector(FakeCollector):
    async def collect_scope(self, **kwargs):
        import asyncio
        import hashlib
        import json
        from datetime import UTC, datetime

        from src.adapters.fmp import FMPAccessStatus, FMPEndpoint
        from src.application.evidence_collection import (
            EndpointCollectionStatus,
            EvidenceTaskAcquisitionResult,
        )
        from src.domain.enums import EvidenceAcquisitionStatus, EvidenceCategory, EvidenceStatus

        self.calls += 1
        rows = [("revenue", "FY2024", 100), ("revenue", "FY2025", 125), ("ebitda", "FY2025", 25)]
        raw = json.dumps(
            {
                "synthetic_test_fixture": True,
                "symbol": kwargs["symbol"],
                "unit": "USD",
                "observations": rows,
            },
            sort_keys=True,
        ).encode()
        path = self.root / "synthetic-financials.json"
        await asyncio.to_thread(path.write_bytes, raw)
        records = []
        for field, period, value in rows:
            record = EvidenceRecord(
                evidence_id=f"E-{field}-{period}",
                run_id=kwargs["run_id"],
                object_id=kwargs["object_id"],
                producer_task_id=kwargs["task_id"],
                provider="fixture",
                source_endpoint="income-statement",
                evidence_category=EvidenceCategory.FINANCIAL_STATEMENT,
                retrieved_at=datetime.now(UTC),
                as_of=kwargs["as_of"],
                raw_artifact_ref=str(path),
                snapshot_hash=hashlib.sha256(raw).hexdigest(),
                normalized_field=field,
                normalized_value=str(value),
                period=period,
                unit="USD",
                currency="USD",
                period_basis="FY",
                statement_series="synthetic:annual",
                status=EvidenceStatus.ACCEPTED,
            )
            await self.repository.add(record)
            records.append(record)
        return EvidenceTaskAcquisitionResult(
            kwargs["task_id"],
            kwargs["scope"],
            EvidenceAcquisitionStatus.COMPLETED,
            EvidenceIngestionResult(
                AcceptedEvidenceBundle(run_id=kwargs["run_id"], records=records),
                tuple(records),
                (),
                tuple(records),
            ),
            (
                EndpointCollectionStatus(
                    FMPEndpoint.INCOME,
                    FMPAccessStatus.AVAILABLE,
                    200,
                    3,
                    3,
                    0,
                    None,
                ),
            ),
        )


async def configured(
    tmp_path,
    *,
    repository=None,
    store=None,
    failures=(Code.READ_TIMEOUT,),
    persist=True,
    symbol="ALPHA",
    sessions=None,
    budget=None,
    certify=False,
    all_fail=False,
    downstream=False,
):
    repository = repository or InMemoryApplicationRepository()
    store = store or MemoryRecoveryEvidenceStore()
    clients = {
        "teamorouter-sol": LocalClient("teamorouter", "gpt-5.6-sol", failures),
        "teamorouter-luna": LocalClient("teamorouter", "gpt-5.6-luna"),
        "mimo-direct": LocalClient("mimo", "mimo-v2.5"),
    }
    routes = {
        k: Candidate(route=k, provider=c.provider_name, model=c.model_name, authority_exists=True)
        for k, c in clients.items()
    }
    # Certification is a deterministic fixture input, never learned from a fake PASS.
    certificates = {}
    if certify:
        from src.domain.agent_output import StandardResearchAgentStructuredOutput
        from src.domain.recovery import Capability
        from src.phase4_product.hashing import canonical_json_sha256

        certificates = {
            (
                "fundamental_analysis",
                key,
                client.model_name,
                canonical_json_sha256(StandardResearchAgentStructuredOutput.model_json_schema()),
            ): Capability.VERIFIED
            for key, client in clients.items()
        }
    if all_fail:
        for client in clients.values():
            client.failures = list(failures)
    recovery = AdaptiveRecovery(routes, clients, store, budget=budget, capabilities=certificates)
    registry = build_research_agent_registry(
        clients["teamorouter-sol"],
        ResearchAgentOutputArtifactStore(Path(tmp_path) / "agents"),
        recovery=recovery,
    )
    if sessions is not None:
        from src.application.persistence import SessionFactoryEvidenceRepository
        from src.infrastructure.database.checkpoints import SQLAlchemyCheckpointStore
        from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore

        evidence = SessionFactoryEvidenceRepository(sessions)
        persistence = dict(
            event_store=PostgresRuntimeEventStore(sessions),
            checkpoint_store=SQLAlchemyCheckpointStore(sessions),
        )
    else:
        evidence = InMemoryEvidenceRepository()
        persistence = {}
    collector = FinancialCollector(evidence, Path(tmp_path), repository)
    service = ResearchApplicationService(
        repository=repository,
        evidence_repository=evidence,
        evidence_collector=collector,
        agent_registry=registry,
        recovery_evidence_store=store,
        **persistence,
    )
    kinds = ("evidence_collection", "fundamental_analysis")
    value = aggregate(kinds + (("report_synthesis",) if downstream else ()))
    value.runtime.actual_graph.tasks[1].assigned_agent = "fundamental_analyst"
    value.runtime.planned_graph.tasks[1].assigned_agent = "fundamental_analyst"
    value.node_binding = None
    initialize_binding(value, service=service)
    if persist:
        await repository.add_object(
            ResearchObject(
                object_id="OBJECT-WP02",
                symbol=symbol,
                company_name="Local synthetic",
                exchange="LOCAL",
            )
        )
        if sessions is not None:
            from src.application.persistence import ResearchGoalRow

            async with sessions() as session, session.begin():
                session.add(
                    ResearchGoalRow(
                        goal_id=value.goal.goal_id,
                        object_id=value.goal.research_object_id,
                        payload=value.goal.model_dump(mode="json"),
                    )
                )
        await repository.add_run(value)
    return service, value, collector, clients


@pytest.mark.parametrize("symbol", ["ALPHA", "BETA"])
async def test_same_node_resume(tmp_path, symbol):
    service, value, collector, clients = await configured(tmp_path, symbol=symbol)
    pending = await service.execute_run(value.run.run_id)
    root = pending.node_binding
    assert root.lifecycle == "RECOVERY_PENDING"
    first = root.attempts[value.runtime.actual_graph.tasks[1].task_id]
    assert first.status == "FAILED" and first.generation == 1
    assert len(root.current_results) == 1 and collector.calls == 1
    result = await service.execute_run(value.run.run_id)
    assert len(result.node_binding.current_results) == 2
    assert collector.calls == 1
    second = result.node_binding.attempts[first.admission.task_id]
    assert second.generation == 2 and second.status == "COMMITTED"
    assert second.admission.attempt_reservation_id != first.admission.attempt_reservation_id
    assert second.admission.graph == first.admission.graph
    assert second.admission.task_fingerprint == first.admission.task_fingerprint
    assert second.admission.dependency_result_bindings == first.admission.dependency_result_bindings
    assert result.node_binding.attempt_history[first.admission.attempt_reservation_id] == first
    assert clients["teamorouter-sol"].calls == 1


@pytest.mark.parametrize(
    "code", [Code.AUTHENTICATION_FAILURE, Code.REQUEST_REJECTED, Code.SEMANTIC_SCHEMA_FAILURE]
)
async def test_nonrecoverable_does_not_retry(tmp_path, code):
    from src.domain.node_binding import BindingDenied

    service, value, _, clients = await configured(tmp_path, failures=(code,))
    with pytest.raises(ExceptionGroup):
        await service.execute_run(value.run.run_id)
    current = await service.repository.get_run_fresh(value.run.run_id)
    assert current.node_binding.lifecycle != "RECOVERY_PENDING"
    assert not current.node_binding.attempt_history
    assert len(current.node_binding.current_results) == 1
    with pytest.raises(BindingDenied):
        await service.execute_run(value.run.run_id)
    assert sum(client.calls for client in clients.values()) == 1


@pytest.mark.parametrize("ceiling", [1, 2, 3])
async def test_attempt_budget_exhausted(tmp_path, ceiling):
    from src.domain.recovery import RecoveryBudget

    service, value, collector, clients = await configured(
        tmp_path,
        budget=RecoveryBudget(max_total_attempts_per_task=ceiling),
        certify=True,
        all_fail=True,
    )
    for _ in range(ceiling):
        try:
            current = await service.execute_run(value.run.run_id)
        except ExceptionGroup:
            break
        assert current.node_binding.lifecycle == "RECOVERY_PENDING"
    current = await service.repository.get_run_fresh(value.run.run_id)
    assert current.node_binding.lifecycle != "RECOVERY_PENDING"
    target = current.node_binding.attempts[value.runtime.actual_graph.tasks[1].task_id]
    assert target.generation == ceiling
    assert len(current.node_binding.current_results) == 1
    assert sum(client.calls for client in clients.values()) == ceiling
    assert collector.calls == 1


async def test_no_fallback_expansion(tmp_path):
    from src.domain.recovery import RecoveryBudget

    service, value, _, clients = await configured(
        tmp_path,
        budget=RecoveryBudget(max_model_fallbacks=0, max_cross_provider_switches=0),
    )
    with pytest.raises(ExceptionGroup):
        await service.execute_run(value.run.run_id)
    current = await service.repository.get_run_fresh(value.run.run_id)
    assert current.node_binding.lifecycle != "RECOVERY_PENDING"
    assert clients["teamorouter-sol"].calls == 1
    assert all(c.calls == 0 for k, c in clients.items() if k != "teamorouter-sol")


async def test_concurrent_reservation_and_stale_recovery(tmp_path):
    import asyncio

    from src.application.execution import IntegratedTaskExecutor
    from src.domain.node_binding import BindingDenied

    service, value, _, _ = await configured(tmp_path)
    pending = await service.execute_run(value.run.run_id)
    target = pending.runtime.actual_graph.tasks[1]
    previous = pending.node_binding.attempts[target.task_id].admission
    owners = await asyncio.gather(
        *(service.repository.claim_execution(value.run.run_id) for _ in range(2)),
        return_exceptions=True,
    )
    assert sum(isinstance(owner, BindingDenied) for owner in owners) == 1
    owner = next(owner for owner in owners if not isinstance(owner, BaseException))
    fresh = await service.repository.validate_execution(owner)
    requirements = IntegratedTaskExecutor(service, fresh).admission_requirements(target)
    attempts = await asyncio.gather(
        *(service.repository.reserve_node(owner, target, requirements) for _ in range(2)),
        return_exceptions=True,
    )
    assert sum(isinstance(attempt, BindingDenied) for attempt in attempts) == 1
    with pytest.raises(BindingDenied):
        await service.repository.dispatch_node(previous)
    root = (await service.repository.get_run_fresh(value.run.run_id)).node_binding
    assert sum(a.status in {"RESERVED", "DISPATCHED"} for a in root.attempts.values()) == 1
    assert len(root.attempt_history) == 1


async def test_committed_result_prevents_duplicate(tmp_path):
    from src.domain.node_binding import BindingDenied

    service, value, collector, clients = await configured(tmp_path)
    pending = await service.execute_run(value.run.run_id)
    prior = pending.node_binding.attempts[value.runtime.actual_graph.tasks[1].task_id]
    result = await service.execute_run(value.run.run_id)
    with pytest.raises(BindingDenied):
        service.repository._validate_recovery(
            result, result.runtime.task(prior.admission.task_id), prior
        )
    with pytest.raises(BindingDenied):
        await service.execute_run(value.run.run_id)
    assert len(result.node_binding.results) == len(result.node_binding.current_results) == 2
    assert collector.calls == 1 and clients["teamorouter-sol"].calls == 1


async def test_newer_policy_cannot_expand_pending_run(tmp_path, monkeypatch):
    from src.application import execution_profiles

    service, value, _, clients = await configured(tmp_path)
    pending = await service.execute_run(value.run.run_id)
    before = pending.node_binding.execution_profile_snapshot_digest
    changed = dict(execution_profiles.TASK_POLICIES)
    changed["fundamental_analysis"] = changed["fundamental_analysis"].model_copy(
        update={"reason": "new mutable version"}
    )
    monkeypatch.setattr(execution_profiles, "TASK_POLICIES", changed)
    with pytest.raises(ExceptionGroup) as rejected:
        await service.execute_run(value.run.run_id)
    assert "PROFILE_POLICY_INCOMPATIBLE" in str(rejected.value.exceptions[0])
    current = await service.repository.get_run_fresh(value.run.run_id)
    assert current.node_binding.execution_profile_snapshot_digest == before
    assert sum(c.calls for c in clients.values()) == 1


async def test_default_no_failure(tmp_path):
    service, value, collector, clients = await configured(tmp_path, failures=())
    current = await service.execute_run(value.run.run_id)
    assert len(current.node_binding.results) == 2 and not current.node_binding.attempt_history
    assert all(a.generation == 1 for a in current.node_binding.attempts.values())
    assert collector.calls == 1 and sum(c.calls for c in clients.values()) == 1


@pytest.mark.parametrize("change", ["graph", "profile", "decision", "recoverability", "ceiling"])
async def test_current_durable_state_denies_stale_recovery(tmp_path, change):
    from src.domain.node_binding import BindingDenied

    service, value, _, clients = await configured(tmp_path)
    pending = await service.execute_run(value.run.run_id)
    target_id = value.runtime.actual_graph.tasks[1].task_id
    # Deliberate durable-state corruption to exercise fail-closed read-current checks.
    durable = service.repository._runs[value.run.run_id]
    prior = durable.node_binding.attempts[target_id]
    if change == "graph":
        durable.runtime.actual_graph.version += 1
    elif change == "profile":
        durable.node_binding.execution_profile_snapshot_digest = "changed"
    elif change == "decision":
        prior.recovery["decision"]["target_route"] = "teamorouter-terra"
    elif change == "recoverability":
        prior.recovery["context"]["failure"]["recoverable"] = False
    else:
        durable.node_binding.attempts[target_id] = prior.model_copy(update={"generation": 3})
    with pytest.raises(BindingDenied):
        await service.repository.claim_execution(pending.run.run_id)
    assert sum(c.calls for c in clients.values()) == 1
    assert not durable.node_binding.attempt_history


async def test_native_definition_restart_metadata_not_executable_authority(tmp_path, monkeypatch):
    from datetime import timedelta

    from src.application.execution_profiles import validate_runtime_profile
    from src.domain.node_binding import BindingDenied

    service, value, _, _ = await configured(tmp_path)
    target = value.runtime.actual_graph.tasks[1]
    capability = service.capability_registry.get("revenue_growth")
    frozen = value.node_binding.execution_profile_snapshot_digest
    monkeypatch.setattr(
        capability,
        "definition",
        capability.definition.model_copy(
            update={
                "created_at": capability.definition.created_at + timedelta(seconds=1),
            }
        ),
    )
    validate_runtime_profile(service, value, target)
    assert value.node_binding.execution_profile_snapshot_digest == frozen
    monkeypatch.setattr(
        capability,
        "definition",
        capability.definition.model_copy(
            update={
                "version": "99.0.0",
            }
        ),
    )
    with pytest.raises(BindingDenied, match="PROFILE_COMPOSITION_INCOMPATIBLE"):
        validate_runtime_profile(service, value, target)


async def test_registering_terra_later_does_not_expand_frozen_composition(tmp_path):
    service, value, _, clients = await configured(tmp_path)
    pending = await service.execute_run(value.run.run_id)
    profile_digest = pending.node_binding.execution_profile_snapshot_digest
    recovery = service.agent_registry.get("fundamental_analyst")._recovery
    terra = LocalClient("teamorouter", "gpt-5.6-terra")
    recovery.clients["teamorouter-terra"] = terra
    recovery.detector.routes["teamorouter-terra"] = Candidate(
        route="teamorouter-terra",
        provider="teamorouter",
        model="gpt-5.6-terra",
        authority_exists=True,
    )
    with pytest.raises(ExceptionGroup) as denied:
        await service.execute_run(value.run.run_id)
    assert "PROFILE_COMPOSITION_INCOMPATIBLE" in str(denied.value.exceptions[0])
    current = await service.repository.get_run_fresh(value.run.run_id)
    assert current.node_binding.execution_profile_snapshot_digest == profile_digest
    assert terra.calls == 0 and sum(c.calls for c in clients.values()) == 1


async def test_elapsed_budget_prevents_new_reservation(tmp_path):
    from datetime import UTC, datetime, timedelta

    service, value, _, clients = await configured(tmp_path)
    pending = await service.execute_run(value.run.run_id)
    target_id = pending.runtime.actual_graph.tasks[1].task_id
    root = service.repository._runs[value.run.run_id].node_binding
    root.attempts[target_id].recovery["saved_at"] = (
        datetime.now(UTC) - timedelta(seconds=301)
    ).isoformat()
    with pytest.raises(ExceptionGroup) as denied:
        await service.execute_run(value.run.run_id)
    assert "RECOVERY_BUDGET_EXHAUSTED" in str(denied.value.exceptions[0])
    current = await service.repository.get_run_fresh(value.run.run_id)
    assert current.node_binding.lifecycle != "RECOVERY_PENDING"
    assert current.node_binding.attempts[target_id].generation == 1
    assert not current.node_binding.attempt_history
    assert sum(c.calls for c in clients.values()) == 1


async def test_downstream_continues_after_recovered_result(tmp_path):
    service, value, collector, _ = await configured(tmp_path, downstream=True)
    pending = await service.execute_run(value.run.run_id)
    assert pending.node_binding.lifecycle == "RECOVERY_PENDING"
    assert len(pending.node_binding.results) == 1
    completed = await service.execute_run(value.run.run_id)
    assert len(completed.node_binding.results) == 3
    downstream = value.runtime.actual_graph.tasks[2]
    assert completed.node_binding.attempts[downstream.task_id].status == "COMMITTED"
    assert completed.node_binding.attempts[downstream.task_id].generation == 1
    assert completed.node_binding.frozen_graph == pending.node_binding.frozen_graph
    assert collector.calls == 1


@pytest.mark.parametrize("requirements", [{"acquire": True}, {"wp04_candidates": {}}])
async def test_non_reentrant_invocations_keep_in_call_recovery(tmp_path, requirements):
    from types import SimpleNamespace

    from src.application.repository import node_recovery
    from tests.unit.agentic.test_adaptive_recovery import agent, context, setup

    recovery, clients, _ = setup()

    class NoDurableHandoff:
        async def fail_node_for_recovery(self, *args):
            raise AssertionError("Unretained/resevervation-coupled inputs cannot reenter")

    admission = SimpleNamespace(
        attempt_reservation_id="fixture-reservation",
        authorized_input_requirements=requirements,
    )
    token = node_recovery.set((NoDurableHandoff(), admission, None))
    try:
        result = await agent(tmp_path, recovery, clients).execute(context())
        assert result.agent_output.status == "SUCCESS"
        assert clients["teamorouter-sol"].calls == 1
    finally:
        node_recovery.reset(token)
