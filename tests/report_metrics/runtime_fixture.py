from datetime import date

from src.adapters.fmp import FMPAccessStatus, FMPEndpoint, FMPProvider, FMPResponseEnvelope
from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.provider import LLMFailureClassification as Code
from src.adapters.llm.provider import LLMProviderError
from src.agentic.composition import build_research_agent_registry
from src.agentic.recovery import AdaptiveRecovery
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.application.evidence_collection import LiveFMPEvidenceCollector
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
        if (
            kwargs["schema_name"]
            in {"risk_analysis_research_output_v1", "risk_analysis_research_output_minimal_v1"}
            and self.fail_risk
        ):
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
            return LLMStructuredResponse(
                output=kwargs["response_model"].model_validate(
                    dict(
                        summary="Synthetic resumed Risk",
                        key_findings=["Current selected evidence"],
                        risks=[],
                        limitations=[],
                        requires_follow_up=False,
                        business_outcome="SUFFICIENT",
                        outcome_reason_codes=[],
                        evidence_gap_refs=[],
                    )
                ),
                provider=self.provider_name,
                requested_model=self.model_name,
                actual_model=self.model_name,
                attempted_models=(self.model_name,),
                input_tokens=12,
                output_tokens=6,
            )
        return await super().complete_structured(**kwargs)


async def report_fixture(
    root,
    *,
    repository=None,
    evidence=None,
    store=None,
    event_store=None,
    sessions=None,
    preferences=None,
):
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
    for client in clients.values():
        client.fail_risk = False
    preferences = (
        preferences
        if preferences is not None
        else {
            "report_metric_requirements": {
                "schema_version": "frozen-report-metric-requirements/v1",
                "report_mode": "METRIC_FOCUSED",
                "required_metric_ids": ["revenue_growth_v1"],
                "period": "FY2026",
            }
        }
    )
    backend = None
    if sessions is None:
        obj = await service.create_object(symbol="NVDA", company_name="Synthetic", exchange="LOCAL")
        draft = await service.prepare_run(
            research_object_id=obj.object_id,
            research_goal="Single selected financial metric",
            as_of=date(2026, 9, 4),
            preferences=preferences,
        )
        value = await service.confirm_run(
            draft_id=draft.draft_id, confirm_scheme=True, idempotency_key="rmc1-app-confirm"
        )
        replay = await service.confirm_run(
            draft_id=draft.draft_id, confirm_scheme=True, idempotency_key="rmc1-app-confirm"
        )
        assert value.run.run_id == replay.run.run_id
    else:
        from src.phase4_product.contracts import (
            ConfirmResearchRunRequestV1,
            CreateResearchObjectRequestV1,
            PrepareResearchRunRequestV1,
        )
        from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

        backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
        obj = await backend.create_object(
            CreateResearchObjectRequestV1(
                symbol="NVDA", company_name="Synthetic", exchange="LOCAL"
            ),
            idempotency_key="rmc1-object",
            request_id=None,
        )
        draft = await backend.prepare_run(
            PrepareResearchRunRequestV1(
                research_object_id=obj.object.object_id,
                research_goal="Single selected financial metric",
                as_of=date(2026, 9, 4),
                preferences=preferences,
            ),
            idempotency_key="rmc1-prepare",
            request_id=None,
        )
        payload = ConfirmResearchRunRequestV1(
            draft_id=draft.draft_id,
            draft_version=draft.draft_version,
            draft_hash=draft.draft_hash,
            research_object_id=obj.object.object_id,
            confirm_scheme=True,
        )
        response = await backend.confirm_run(
            payload, idempotency_key="rmc1-confirm", request_id=None
        )
        replay = await backend.confirm_run(payload, idempotency_key="rmc1-confirm", request_id=None)
        assert response.admission == replay.admission
        value = await repository.get_run_fresh(response.admission.run_id)
    return service, value, clients, backend, draft
