"""Exact D01 proof adoption; local synthetic ports only, no Resume command."""

import copy
import hashlib
import inspect
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.adapters.llm.teamorouter import _structured_request_template
from src.agentic.research_agent import _messages
from src.application import execution_profiles as profiles
from src.application.external_failure_resume import legacy_snapshot
from src.application.persistence import SQLAlchemyApplicationRepository as Repository
from src.application.repository import node_invocation
from src.domain.agent_output import RiskResearchAgentStructuredOutputMinimalV1 as D01
from src.domain.execution_profile import AcceptedRequestProof, ExecutionSnapshot
from src.domain.node_binding import BindingDenied
from src.domain.risk_admission import POLICY, PROFILE, SCHEMA, freeze_contract
from src.phase4_product.hashing import canonical_json_sha256 as digest
from tests.execution_profiles.test_bounded_terra_fallback import request_scope
from tests.external_failure_resume.runtime_fixture import exhaust, legal_fixture


@pytest.fixture
async def d01(tmp_path):
    service, value, clients = await legal_fixture(tmp_path, minimal=True)
    task = next(t for t in value.runtime.actual_graph.tasks if t.task_type == "risk_analysis")
    profile = profiles.frozen_profile(value, task)
    ctx, scope, request = request_scope(task)
    request.update(response_model=D01, schema_name=SCHEMA)
    scope = scope.model_copy(update={"contract_hash": digest(D01.model_json_schema())})
    recovery = profiles.recovery_for(profiles.configured_agent(service, task, None))
    contract = freeze_contract([task])
    token = node_invocation.set(SimpleNamespace(policy_refs={"risk_semantic_contract": contract}))
    try:
        yield service, value, clients, profile, ctx, scope, request, recovery
    finally:
        node_invocation.reset(token)


def matches(fixture, *, profile=None, ctx=None, scope=None, request=None, candidate=None):
    _, _, _, p, c, s, req, recovery = fixture
    return profiles.adopted_request_matches(
        profile or p, ctx or c, scope or s,
        candidate or recovery.detector.routes["teamorouter-terra"], request or req,
    )


def test_r01_r02_accepted_identity_and_validation():
    proof = profiles.accepted_terra_proof("risk_analysis", request_profile=PROFILE)
    assert AcceptedRequestProof.model_validate_json(proof.model_dump_json()) == proof
    assert proof.acceptance_digest == proof.content_digest()
    assert proof.receipt_id == "REC-c97f2b81-d8e5-402f-a67c-1d6af81b693d"
    assert proof.attempt_id == "ATT-7043e7d1-735d-4abe-9ab2-efadf9150708"
    assert proof.d01_evidence["proof_id"] == "D01-TERRA-6dd4f49c-1c49-4162-9421-4c0408e5c4f4"
    family = proof.d01_identity["family"]
    assert set(family) == {
        "agent_id", "builder_digest", "execution_profile_version", "model", "policy_digest",
        "profile", "provider", "response_format_digest", "route", "schema_digest",
        "schema_identity", "schema_name", "skill_id", "system_prompt_digest", "task_type",
        "template_digest", "workload",
    }
    assert digest(family) == proof.d01_identity["family_digest"]
    assert family["policy_digest"] == digest(POLICY)
    assert family["schema_digest"] == digest(D01.model_json_schema())
    for key, function in (("builder_digest", _messages),
                          ("template_digest", _structured_request_template)):
        actual = "sha256:" + hashlib.sha256(inspect.getsource(function).encode()).hexdigest()
        assert family[key] == actual
    for section in ("d01_identity", "d01_evidence"):
        broken = proof.model_dump()
        broken[section] = {**broken[section], "tampered": True}
        with pytest.raises(ValidationError):
            AcceptedRequestProof.model_validate(broken)


def test_r08_old_proof_bytes_and_identity_unchanged():
    old = profiles.accepted_terra_proof("risk_analysis")
    assert hashlib.sha256(old.model_dump_json().encode()).hexdigest() == (
        "efec1b52691f9907f405f549dbee5a44955a108922dcc9a2418f5db18998e7f8"
    )
    assert old.acceptance_digest == (
        "sha256:edd6bd87a2ab554872dddd582e1048afe49f057a959565a5065e142b47d1a10a"
    )
    assert "d01_identity" not in old.model_dump()
    assert AcceptedRequestProof.model_validate_json(old.model_dump_json()) == old


async def test_r03_r09_confirm_freezes_exact_d01_proof(d01):
    _, value, _, p, ctx, _, _, _ = d01
    assert matches(d01)
    assert p.accepted_request_proof == profiles.accepted_terra_proof(
        "risk_analysis", request_profile=PROFILE
    )
    snap = ExecutionSnapshot.model_validate(value.node_binding.execution_snapshot)
    assert snap.scenario.risk_semantic_contract == freeze_contract([ctx.task])
    assert p.profile_version == "2" and p.resolved_route == "teamorouter-sol"
    assert p.allowed_model_routes == ("teamorouter-sol", "teamorouter-terra")
    assert p.recovery_fallback_routes == ("teamorouter-terra",)
    assert p.recovery_budget.max_same_route_attempts == 1
    assert p.recovery_budget.max_model_fallbacks == 1
    assert p.recovery_budget.max_capability_checks == 0


@pytest.mark.parametrize("field", [
    "agent_id", "builder_digest", "execution_profile_version", "model", "policy_digest",
    "profile", "provider", "response_format_digest", "route", "schema_digest",
    "schema_identity", "schema_name", "skill_id", "system_prompt_digest", "task_type",
    "template_digest", "workload",
])
async def test_r02_r04_r05_every_family_field_is_exact(d01, field):
    p = d01[3]
    proof = p.accepted_request_proof
    identity = copy.deepcopy(proof.d01_identity)
    identity["family"][field] += "-changed"
    identity["family_digest"] = digest(identity["family"])
    changed = proof.model_copy(update={"d01_identity": identity})
    changed = changed.model_copy(update={"acceptance_digest": changed.content_digest()})
    assert not matches(d01, profile=p.model_copy(update={"accepted_request_proof": changed}))


@pytest.mark.parametrize("field", ["schema_name", "workload_type", "messages", "response_model"])
async def test_r04_r05_changed_request_rejected(d01, field):
    from src.domain.agent_output import RiskResearchAgentStructuredOutput

    request = dict(d01[6])
    request[field] = {
        "schema_name": "risk_analysis_research_output_v1", "workload_type": "OTHER",
        "messages": [], "response_model": RiskResearchAgentStructuredOutput,
    }[field]
    assert not matches(d01, request=request)


@pytest.mark.parametrize("kind", [
    "peer_analysis", "valuation_analysis", "ValuationTurn", "risk_follow_up", "risk_other",
])
async def test_r06_r07_sibling_families_denied(d01, kind):
    ctx = d01[4]
    task = ctx.task.model_copy(update={"task_type": kind, "skill_id": f"{kind}_v1"})
    assert not matches(d01, ctx=ctx.model_copy(update={"task": task}))
    assert profiles.accepted_terra_proof(kind, request_profile=PROFILE) is None


async def test_r05_r06_unbound_or_wrong_contract_denied(d01):
    token = node_invocation.set(None)
    try:
        assert not matches(d01)
    finally:
        node_invocation.reset(token)
    profile = d01[3]
    old = profiles.accepted_terra_proof("risk_analysis")
    assert not matches(d01, profile=profile.model_copy(update={"accepted_request_proof": old}))
    assert profiles.accepted_terra_proof(
        "risk_analysis", request_profile=PROFILE + "-other"
    ) is None


async def test_r08_legacy_resolution_and_r10_no_reresolution(d01, monkeypatch):
    service, value, _, p, ctx, _, _, _ = d01
    before = json.dumps(Repository._payload(value), sort_keys=True, default=str)
    monkeypatch.setattr(profiles, "accepted_terra_proof", lambda *args, **kwargs: None)
    restored = Repository._to_aggregate(json.loads(json.dumps(Repository._payload(value))), 2)
    assert profiles.validate_runtime_profile(service, restored, ctx.task) == p
    assert matches(d01, profile=profiles.frozen_profile(restored, ctx.task))
    assert json.dumps(Repository._payload(value), sort_keys=True, default=str) == before


async def test_r09_narrow_profile_rejects_old_proof_for_d01(d01):
    _, value, _, p, _, _, _, _ = d01
    scenario = ExecutionSnapshot.model_validate(value.node_binding.execution_snapshot).scenario
    selected = p.model_copy(update={
        "accepted_request_proof": profiles.accepted_terra_proof("risk_analysis"),
    })
    with pytest.raises(BindingDenied, match="PROFILE_PROOF_ADOPTION_DENIED"):
        profiles.narrow_profile(p, selected, scenario)


async def test_r11_r14_synthetic_settled_chain_and_normal_eligibility(tmp_path):
    service, initial, clients = await legal_fixture(tmp_path, minimal=True)
    failed = await exhaust(service, initial)
    before = legacy_snapshot(failed)
    calls = {key: client.risk_calls for key, client in clients.items()}
    assert calls == {
        "teamorouter-sol": 1, "teamorouter-terra": 1, "teamorouter-luna": 0, "mimo-direct": 0,
    }
    view = await service.repository.inspect_external_failure(failed.run.run_id, actor="local-test")
    assert view["denial_reasons"] == ["HISTORICAL_OPT_IN_REQUIRED"]
    assert view["legal_actions"][0]["expectations"]["historical_adoption"][
        "acknowledge_preserved_terminal_history"
    ] is True
    assert len(view["legal_actions"]) == 1
    assert legacy_snapshot(await service.repository.get_run_fresh(failed.run.run_id)) == before
    assert {key: client.risk_calls for key, client in clients.items()} == calls
    print("R11-R14 synthetic eligibility:", json.dumps(view, sort_keys=True, default=str))
