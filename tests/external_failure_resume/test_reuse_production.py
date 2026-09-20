"""Five retained outputs come from the production graph, ingestion and commit owners."""

from datetime import date, timedelta

import pytest

from src.adapters.fmp import FMPProvider
from src.agentic.composition import build_research_agent_registry
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.application.evidence_collection import LiveFMPEvidenceCollector
from src.application.external_failure_resume import validate_evidence_provenance, validate_reuse
from src.application.service import ResearchApplicationService
from src.data.artifacts import LocalRawArtifactStore
from src.data.repository import InMemoryEvidenceRepository
from src.domain.node_binding import BindingDenied, canonical_value
from tests.unit.agentic.test_adaptive_recovery import Client
from tests.unit.application.test_evidence_semantics import SemanticFMPTransport


async def production_fixture(tmp_path):
    evidence = InMemoryEvidenceRepository()
    client = Client("teamorouter", "gpt-5.6-sol")
    service = ResearchApplicationService(
        evidence_repository=evidence,
        evidence_collector=LiveFMPEvidenceCollector(
            provider=FMPProvider(SemanticFMPTransport()), repository=evidence,
            artifact_store=LocalRawArtifactStore(tmp_path / "raw"),
        ),
        agent_registry=build_research_agent_registry(
            client, ResearchAgentOutputArtifactStore(tmp_path / "agents"),
        ),
    )
    obj = await service.create_object(symbol="NVDA", company_name="Synthetic", exchange="LOCAL")
    draft = await service.prepare_run(
        research_object_id=obj.object_id, research_goal="Synthetic five-output closure",
        as_of=date(2026, 9, 4), preferences={},
    )
    value = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    try:
        value = await service.execute_run(value.run.run_id)
    except ExceptionGroup as exc:
        # The fixture exposes the existing Risk sibling-input rejection after all
        # five producers commit. It is not eligible external exhaustion.
        assert "STALE_INPUT" in str(exc.exceptions[0])
        value = await service.repository.get_run_fresh(value.run.run_id)
    return service, value, client


async def test_five_completed_outputs_are_independent_retained_closures(tmp_path):
    service, value, client = await production_fixture(tmp_path)
    risk = next(t for t in value.runtime.actual_graph.tasks if t.task_type == "risk_analysis")
    before = client.calls
    decisions = await validate_reuse(service.repository, value, risk)
    assert {d.kind for d in decisions} == {
        "Evidence", "Fundamentals", "Peers", "ResearchNews", "Valuation",
    }
    assert client.calls == before


@pytest.mark.parametrize("kind", [
    "evidence_collection", "fundamental_analysis", "peer_analysis",
    "research_news_analysis", "valuation_analysis",
])
async def test_each_retained_pointer_is_required_without_upstream_replay(tmp_path, kind):
    service, value, client = await production_fixture(tmp_path)
    risk = next(t for t in value.runtime.actual_graph.tasks if t.task_type == "risk_analysis")
    producer = next(t for t in value.runtime.actual_graph.tasks if t.task_type == kind)
    value.node_binding.current_results.pop(producer.task_id)
    before = client.calls
    with pytest.raises(BindingDenied):
        await validate_reuse(service.repository, value, risk)
    assert client.calls == before


async def test_missing_unsupported_or_wrong_policy_fails_closed(tmp_path):
    service, value, client = await production_fixture(tmp_path)
    evidence = next(r for r in value.artifacts.evidence if r.status.value == "ACCEPTED")
    payload = canonical_value(evidence)
    before = client.calls
    assert validate_evidence_provenance(value, payload, expected_symbol="NVDA")
    for mutation in ("missing", "version", "as_of", "future", "symbol", "permission"):
        import copy

        changed = copy.deepcopy(payload)
        if mutation == "missing":
            changed.pop("validation_provenance")
        elif mutation == "version":
            changed["validation_provenance"]["validator_version"] = "unknown"
        elif mutation == "as_of":
            changed["validation_provenance"]["request"]["as_of"] = "2020-01-01"
        elif mutation == "future":
            changed["as_of"] = (value.run.as_of + timedelta(days=1)).isoformat()
        elif mutation == "symbol":
            changed["validation_provenance"]["request"]["symbol"] = "FOREIGN"
        else:
            changed["validation_provenance"]["request"]["fields"] = ["ungranted"]
        with pytest.raises(BindingDenied):
            validate_evidence_provenance(value, changed, expected_symbol="NVDA")
    assert canonical_value(evidence) == payload
    assert client.calls == before
