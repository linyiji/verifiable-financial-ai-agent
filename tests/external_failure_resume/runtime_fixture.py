from datetime import date

from src.adapters.fmp import FMPAccessStatus, FMPEndpoint, FMPProvider, FMPResponseEnvelope
from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.provider import LLMFailureClassification as Code
from src.adapters.llm.provider import LLMProviderError
from src.agentic.composition import build_research_agent_registry
from src.agentic.recovery import AdaptiveRecovery
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.application.evidence_collection import LiveFMPEvidenceCollector
from src.application.external_failure_resume import (
    envelope_proposal,
    settled_failure,
    validate_reuse,
)
from src.application.service import ResearchApplicationService
from src.data.artifacts import LocalRawArtifactStore
from src.data.repository import InMemoryEvidenceRepository
from src.domain.owner_policy import ADAPTIVE_TRANSPORT_POLICY
from src.domain.recovery import Candidate, retain_attempt_facts
from src.infrastructure.config.settings import Settings
from src.infrastructure.database.recovery import MemoryRecoveryEvidenceStore
from tests.unit.agentic.test_adaptive_recovery import Client
from tests.unit.application.test_evidence_semantics import RETRIEVED_AT, SemanticFMPTransport


class Transport(SemanticFMPTransport):
    async def request(self, **kwargs):
        if kwargs["endpoint"] == FMPEndpoint.PEERS:
            return FMPResponseEnvelope(
                endpoint=FMPEndpoint.PEERS,
                status=FMPAccessStatus.NO_DATA,
                http_status=200,
                retrieved_at=RETRIEVED_AT,
                payload=[],
            )
        return await super().request(**kwargs)


class RiskFailure(Client):
    fail_risk = True
    risk_calls = 0

    async def complete_structured(self, **kwargs):
        if kwargs["schema_name"] in {
            "risk_analysis_research_output_v1", "risk_analysis_research_output_minimal_v1"
        } and self.fail_risk:
            self.risk_calls += 1
            self.calls += 1
            retain_attempt_facts(dispatch_state="NOT_DISPATCHED", dispatch_basis="LOCAL_PREFLIGHT")
            raise LLMProviderError(
                "Synthetic unavailable",
                failure_classification=Code.PROVIDER_UNAVAILABLE,
                provider=self.provider_name,
                model=self.model_name,
                retryable=True,
            )
        if kwargs["schema_name"] == "risk_analysis_research_output_minimal_v1":
            from src.adapters.llm.provider import LLMStructuredResponse

            self.calls += 1
            return LLMStructuredResponse(output=kwargs["response_model"].model_validate(dict(
                summary="Synthetic resumed Risk", key_findings=["Current selected evidence"],
                risks=[], limitations=[], requires_follow_up=False, business_outcome="SUFFICIENT",
                outcome_reason_codes=[], evidence_gap_refs=[])), provider=self.provider_name,
                requested_model=self.model_name, actual_model=self.model_name,
                attempted_models=(self.model_name,), input_tokens=12, output_tokens=6)
        return await super().complete_structured(**kwargs)


async def legal_fixture(root, *, repository=None, evidence=None, store=None, event_store=None,
                        minimal=False):
    evidence = evidence or InMemoryEvidenceRepository()
    store = store or MemoryRecoveryEvidenceStore()
    clients = {
        f"teamorouter-{name}": RiskFailure("teamorouter", f"gpt-5.6-{name}")
        for name in ("sol", "terra", "luna")
    }
    clients["mimo-direct"] = RiskFailure("mimo", "mimo-v2.5")
    for c in clients.values():
        c.execution_policy = ProviderExecutionPolicyV1(**ADAPTIVE_TRANSPORT_POLICY)
        c._settings = Settings(_env_file=None, teamorouter_api_key="LOCAL_SENTINEL").llm.model_copy(
            update={"primary_model": c.model_name, "fallback_model": c.model_name}
        )
    recovery = AdaptiveRecovery(
        {
            k: Candidate(
                route=k, provider=v.provider_name, model=v.model_name, authority_exists=True
            )
            for k, v in clients.items()
        },
        clients,
        store,
    )
    service = ResearchApplicationService(
        repository=repository,
        event_store=event_store,
        evidence_repository=evidence,
        recovery_evidence_store=store,
        evidence_collector=LiveFMPEvidenceCollector(
            provider=FMPProvider(Transport()),
            repository=evidence,
            artifact_store=LocalRawArtifactStore(root / "raw"),
        ),
        agent_registry=build_research_agent_registry(
            clients["teamorouter-sol"],
            ResearchAgentOutputArtifactStore(root / "agents"),
            recovery=recovery,
        ),
    )
    obj = await service.create_object(symbol="NVDA", company_name="Synthetic", exchange="LOCAL")
    draft = await service.prepare_run(
        research_object_id=obj.object_id,
        research_goal="Synthetic legal external-failure closure",
        as_of=date(2026, 9, 4),
        preferences=(
            {"risk_semantic_profile": "risk_semantic_outcome_minimal_v1"} if minimal else {}
        ),
    )
    value = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    return service, value, clients


async def exhaust(service, value):
    for _ in range(2):
        try:
            value = await service.execute_run(value.run.run_id)
        except ExceptionGroup:
            value = await service.repository.get_run_fresh(value.run.run_id)
        if value.node_binding.lifecycle != "RECOVERY_PENDING":
            break
    assert value.run.status.value == "FAILED"
    risk = next(t for t in value.runtime.actual_graph.tasks if t.task_type == "risk_analysis")
    decisions = await validate_reuse(service.repository, value, risk)
    assert len(decisions) == 5
    rows = await service.recovery_evidence_store.records(value.run.run_id, risk.task_id)
    identity, prior, records = settled_failure(value, risk.task_id, rows)
    assert [r.route for r in records if r.kind == "ATTEMPT_STARTED"] == [
        "teamorouter-sol",
        "teamorouter-terra",
    ]
    assert prior.generation >= 2
    steps = [
        b
        for b in value.node_binding.resolved_inputs.values()
        if b.reservation_id == prior.admission.attempt_reservation_id
        and b.step_id == "agent-context"
    ]
    assert len(steps) == 1
    await service.repository.verify_materials(steps[0].material_refs, run_id=value.run.run_id)
    assert all(
        r.payload_snapshot.get("validation_provenance")
        for r in steps[0].material_refs
        if r.kind == "EVIDENCE"
    )
    assert envelope_proposal(value, risk)["routes"] == ["teamorouter-sol", "teamorouter-terra"]
    return value


async def request_for(service, value, key="resume-one"):
    from src.domain.external_failure_resume import ResumeExternalFailure

    view = await service.repository.inspect_external_failure(value.run.run_id, actor="local-test")
    assert len(view["legal_actions"]) == 1, view["denial_reasons"]
    return ResumeExternalFailure(**view["legal_actions"][0]["expectations"], idempotency_key=key)
