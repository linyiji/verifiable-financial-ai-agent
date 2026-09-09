"""Owner authority and bilingual parity, without live availability or credential discovery."""

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from src.domain.model_execution import DYNAMIC_GRANTS, TASK_CANDIDATES, resolve_model_execution
from src.domain.owner_policy import (
    ADAPTIVE_TRANSPORT_POLICY,
    INDEPENDENT_CALL_POLICIES,
    TASK_POLICIES,
    effective_policy_snapshot,
    effective_recovery_budget,
    policy_parity_payload,
    render_policy_table,
)
from src.domain.recovery import Candidate, Capability, RecoveryBudget, Scope


def test_exact_ten_profiles_preserve_prior_authority_without_uniform_four_model_grants():
    assert set(TASK_POLICIES) == {
        "fundamental_analysis",
        "valuation_analysis",
        "risk_analysis",
        "risk_follow_up",
        "peer_analysis",
        "research_news_analysis",
        "report_synthesis",
        "evidence_collection",
        "GENERATED_CAPABILITY:gross_margin",
        "GENERATED_CAPABILITY:free_cash_flow_margin",
    }
    assert len(TASK_CANDIDATES) == 9
    assert TASK_CANDIDATES["report_synthesis"] == (
        "teamorouter-sol",
        "teamorouter-luna",
        "teamorouter-terra",
        "mimo-direct",
    )
    assert TASK_CANDIDATES["peer_analysis"] == (
        "mimo-direct",
        "teamorouter-sol",
        "teamorouter-luna",
    )
    assert "mimo-direct" not in TASK_CANDIDATES["GENERATED_CAPABILITY:free_cash_flow_margin"]
    assert {profile for profile, _ in DYNAMIC_GRANTS} == {
        "fundamental_analysis",
        "valuation_analysis",
        "risk_analysis",
        "risk_follow_up",
        "GENERATED_CAPABILITY:free_cash_flow_margin",
    }


def test_effective_snapshot_retains_overrides_without_expanding_authority_or_mutating_defaults():
    baseline = effective_policy_snapshot("report_synthesis")
    override = RecoveryBudget(max_total_attempts_per_task=2, max_capability_checks=1)
    frozen = effective_policy_snapshot(
        "report_synthesis",
        budget=override,
        preferred_route="teamorouter-terra",
        override_source="isolated-owner-fixture-1",
    )
    assert frozen["policy"]["preferred_route"] == "teamorouter-terra"
    assert frozen["policy"]["effective_override_source"] == "isolated-owner-fixture-1"
    assert frozen["policy"]["recovery_budget"] == override.model_dump(mode="json")
    assert frozen["policy"]["candidates"] == baseline["policy"]["candidates"]
    assert frozen["policy"]["dynamic_grants"] == []
    assert frozen["sha256"] != baseline["sha256"]
    assert effective_policy_snapshot("report_synthesis") == baseline
    with pytest.raises(ValueError, match="retained source"):
        effective_policy_snapshot("report_synthesis", budget=override)
    with pytest.raises(ValueError, match="outside prospective"):
        effective_policy_snapshot(
            "peer_analysis",
            preferred_route="teamorouter-terra",
            override_source="not-a-new-authorization",
        )


@pytest.mark.parametrize("profile", tuple(TASK_CANDIDATES))
def test_budget_defaults_and_explicit_override_do_not_mutate_descriptor(profile):
    descriptor = TASK_POLICIES[profile]
    budget = effective_recovery_budget(profile)
    ordered = profile in {"risk_follow_up", "report_synthesis"}
    assert (
        budget.max_total_attempts_per_task,
        budget.max_capability_checks,
        budget.max_total_recovery_time,
    ) == ((4, 3, 300) if ordered else (3, 1, 300))
    assert descriptor.physical_call_ceiling() == 4
    override = RecoveryBudget(
        max_total_attempts_per_task=1, max_capability_checks=0, max_total_recovery_time=30
    )
    assert effective_recovery_budget(profile, override) == override
    assert effective_recovery_budget(profile) == budget
    assert descriptor.exact_check_consumption == (
        "CONSUME_ONCE" if ordered else "SEPARATE_EXECUTION"
    )
    assert descriptor.outer_deadline_seconds == (180 if profile.startswith("GENERATED") else None)


@pytest.mark.parametrize(
    "profile,allowed",
    [
        ("fundamental_analysis", True),
        ("valuation_analysis", True),
        ("risk_analysis", True),
        ("risk_follow_up", True),
        ("GENERATED_CAPABILITY:free_cash_flow_margin", True),
        ("report_synthesis", False),
        ("GENERATED_CAPABILITY:gross_margin", False),
        ("peer_analysis", False),
        ("research_news_analysis", False),
    ],
)
def test_direct_terra_candidate_is_not_luna_substitution_authority(profile, allowed):
    scope = Scope(
        run_id="RUN-POLICY",
        task_id="RUN-POLICY:task",
        object_id="OBJ-FAKE",
        scheme_id="SCHEME-FAKE",
        task_profile=profile,
        agent_id="AGENT-FAKE",
        context_hash="sha256:" + "a" * 64,
        contract_hash="sha256:" + "b" * 64,
    )
    routes = {
        route: Candidate(route=route, provider="teamorouter", model=model, authority_exists=True)
        for route, model in (
            ("teamorouter-luna", "gpt-5.6-luna"),
            ("teamorouter-terra", "gpt-5.6-terra"),
        )
    }
    policy = resolve_model_execution(
        scope,
        "teamorouter-luna",
        routes,
        {key: Capability.VERIFIED for key in routes},
        RecoveryBudget(),
    )
    assert (
        policy.outcome("teamorouter", "gpt-5.6-luna", "gpt-5.6-terra")
        == "MODEL_EXECUTION_SUBSTITUTED"
    ) is allowed
    assert policy.outcome("mimo", "gpt-5.6-luna", "mimo-v2.5") == "PROVIDER_IDENTITY_OUT_OF_POLICY"


def test_independent_planning_native_data_and_transport_remain_explicit():
    descriptors = {policy.name: policy for policy in INDEPENDENT_CALL_POLICIES}
    assert set(descriptors) == {"SCHEME_PLANNER", "LEAD_PLANNER", "FMP", "BOCHA_WEB"}
    assert all(not policy.dynamic_substitution_allowed for policy in descriptors.values())
    assert descriptors["SCHEME_PLANNER"].validation_passes == 2
    assert descriptors["LEAD_PLANNER"].validation_passes == 1
    assert ADAPTIVE_TRANSPORT_POLICY["max_attempts"] == 1
    assert ADAPTIVE_TRANSPORT_POLICY["read_timeout_seconds"] == 60
    with pytest.raises(ValueError, match="Native data"):
        effective_recovery_budget("evidence_collection")
    with pytest.raises(KeyError):
        effective_recovery_budget("quality_review")
    assert policy_parity_payload()["unknown_cost"] is None


def test_independent_descriptors_match_actual_constructors_and_production_composition():
    from src.adapters.bocha import BochaDiscovery
    from src.adapters.fmp.provider import HttpxFMPTransport
    from src.adapters.llm.teamorouter import TeamoRouterClient
    from src.agentic.llm_integration import (
        PlannerProviderResearchLeadPlanner,
        PlannerProviderSchemeGenerator,
    )
    from src.infrastructure.config.settings import LLMSettings

    descriptors = {policy.name: policy for policy in INDEPENDENT_CALL_POLICIES}
    client = TeamoRouterClient(
        LLMSettings(
            provider="teamorouter",
            api_key=SecretStr("fake-policy-only"),
            base_url="https://example.invalid",
            primary_model="gpt-5.6-sol",
            fallback_model="gpt-5.6-luna",
        )
    )
    scheme = PlannerProviderSchemeGenerator(client)
    assert scheme._max_validation_attempts == descriptors["SCHEME_PLANNER"].validation_passes
    for name in ("SCHEME_PLANNER", "LEAD_PLANNER"):
        descriptor = descriptors[name]
        assert (
            client.execution_policy.per_attempt_deadline_seconds == descriptor.per_attempt_seconds
        )
        assert (
            client.execution_policy.overall_workload_deadline_seconds == descriptor.workload_seconds
        )
    root = Path(__file__).resolve().parents[3]
    api_tree = ast.parse((root / "apps/api/main.py").read_text())
    planner_calls = [
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "PlannerProviderResearchLeadPlanner"
    ]
    assert len(planner_calls) == 1
    keywords = {keyword.arg: keyword.value for keyword in planner_calls[0].keywords}
    assert ast.literal_eval(keywords["max_validation_attempts"]) == (
        descriptors["LEAD_PLANNER"].validation_passes
    )
    assert ast.literal_eval(keywords["fail_closed"]) is True
    graph = PlannerProviderResearchLeadPlanner(client, max_validation_attempts=1, fail_closed=True)
    assert graph._max_validation_attempts == 1 and graph._fail_closed
    assert inspect.signature(HttpxFMPTransport).parameters["timeout_seconds"].default == (
        descriptors["FMP"].per_attempt_seconds
    )
    bocha_tree = ast.parse(inspect.getsource(BochaDiscovery))
    client_calls = [
        node
        for node in ast.walk(bocha_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "AsyncClient"
    ]
    assert len(client_calls) == 1
    timeout = next(
        keyword.value for keyword in client_calls[0].keywords if keyword.arg == "timeout"
    )
    assert ast.literal_eval(timeout) == descriptors["BOCHA_WEB"].per_attempt_seconds


def test_generated_outer_deadline_matches_descriptor_and_retains_tighter_override():
    from src.capabilities.generated.governed_builder import GovernedCodeBuilder

    candidate = Candidate(
        route="teamorouter-sol", provider="teamorouter", model="gpt-5.6-sol", authority_exists=True
    )
    recovery = SimpleNamespace(
        detector=SimpleNamespace(routes={"teamorouter-sol": candidate}), budget=RecoveryBudget()
    )
    builder = GovernedCodeBuilder(recovery, repository=None)
    assert builder.execution_policy.overall_workload_deadline_seconds == (
        TASK_POLICIES["GENERATED_CAPABILITY:gross_margin"].outer_deadline_seconds
    )
    recovery.budget = RecoveryBudget(max_total_recovery_time=30)
    assert (
        GovernedCodeBuilder(
            recovery, repository=None
        ).execution_policy.overall_workload_deadline_seconds
        == 30
    )


def test_runtime_assembly_uses_descriptor_not_duplicate_budget_literals():
    from src.agentic import recovery, recovery_composition

    assert "owner_policy.effective_budget()" in inspect.getsource(recovery)
    assert "ProviderExecutionPolicyV1(**ADAPTIVE_TRANSPORT_POLICY)" in inspect.getsource(
        recovery_composition
    )


@pytest.mark.parametrize("suffix", [".md", ".zh-CN.md"])
def test_bilingual_owner_policy_matrix_exactly_matches_descriptor(suffix):
    root = Path(__file__).resolve().parents[3]
    doc = (root / f"docs/architecture/OWNER_POLICY_V1{suffix}").read_text()
    block = doc.split("<!-- OWNER_POLICY_TABLE_START -->\n", 1)[1].split(
        "\n<!-- OWNER_POLICY_TABLE_END -->", 1
    )[0]
    assert block == render_policy_table()
