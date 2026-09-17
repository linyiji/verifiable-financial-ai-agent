"""V5 controlled matrix: real Confirm/binding/dispatch seams, offline provider ports."""

import asyncio
import json
import sys
from contextlib import contextmanager
from datetime import date

import pytest

from src.application import execution_profiles as profiles
from src.application.evidence_collection import EvidenceAcquisitionScope, evidence_request_plans
from src.application.persistence import SQLAlchemyApplicationRepository
from src.application.repository import compare_whole, validate_root
from src.application.service import ResearchApplicationService
from src.data.provider import ProviderRequest
from src.domain.execution_profile import ExecutionSnapshot
from src.domain.node_binding import BindingDenied, GraphIdentity
from src.domain.owner_policy import TASK_POLICIES


async def confirmed(symbol="ALPHA", preferences=None):
    service = ResearchApplicationService()
    obj = await service.create_object(symbol=symbol, company_name=symbol, exchange="LOCAL")
    draft = await service.prepare_run(
        research_object_id=obj.object_id,
        research_goal="Company fundamental research",
        as_of=date(2026, 9, 17),
        preferences=preferences or {},
    )
    value = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    return service, value


def snapshot(value):
    return ExecutionSnapshot.model_validate(value.node_binding.execution_snapshot)


def task(value, kind):
    return next(t for t in value.runtime.actual_graph.tasks if t.task_type == kind)


def profile(value, kind="evidence_collection"):
    return profiles.frozen_profile(value, task(value, kind))


@contextmanager
def invocation(value, kind="evidence_collection", override=None):
    t = task(value, kind)
    token = profiles.execution_profile_context.set(
        (t.run_id, t.task_id, override or profile(value, kind), {})
    )
    try:
        yield
    finally:
        profiles.execution_profile_context.reset(token)


def fresh(value):
    return SQLAlchemyApplicationRepository._to_aggregate(
        json.loads(json.dumps(SQLAlchemyApplicationRepository._payload(value)))
    )


async def test_case_01_generic_scenario():
    _, value = await confirmed()
    assert snapshot(value).scenario.scenario_id == "company_fundamental_research_v1"
    assert snapshot(value).scenario.scenario_version == "1"
    assert len(snapshot(value).nodes) == len(value.runtime.actual_graph.tasks) == 7


async def test_case_02_confirm_binding_atomic_identity():
    service, value = await confirmed()
    read = await service.repository.get_run_fresh(value.run.run_id)
    assert read.node_binding.frozen_graph == GraphIdentity.of(read.runtime.actual_graph)
    assert (
        read.node_binding.execution_profile_snapshot_digest
        == snapshot(read).execution_profile_snapshot_digest
    )
    validate_root(read)


async def test_case_03_fresh_process(tmp_path):
    _, value = await confirmed()
    path = tmp_path / "aggregate.json"
    path.write_text(json.dumps(SQLAlchemyApplicationRepository._payload(value)))
    script = """import json,sys
from src.application.persistence import SQLAlchemyApplicationRepository as R
from src.application.repository import validate_root
from src.application.execution_profiles import frozen_profile
v=R._to_aggregate(json.load(open(sys.argv[1])))
validate_root(v)
print(json.dumps([v.node_binding.scenario_snapshot_digest,
v.node_binding.execution_profile_snapshot_digest,
frozen_profile(v,v.runtime.actual_graph.tasks[0]).profile_version]))"""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script, str(path), stdout=asyncio.subprocess.PIPE
    )
    out, _ = await process.communicate()
    assert process.returncode == 0
    assert json.loads(out) == [
        value.node_binding.scenario_snapshot_digest,
        value.node_binding.execution_profile_snapshot_digest,
        "1",
    ]


async def test_case_04_policy_drift_rejected(monkeypatch):
    service, value = await confirmed()
    changed = dict(TASK_POLICIES)
    changed["fundamental_analysis"] = changed["fundamental_analysis"].model_copy(
        update={"reason": "later policy"}
    )
    monkeypatch.setattr(profiles, "TASK_POLICIES", changed)
    with pytest.raises(BindingDenied, match="PROFILE_POLICY_INCOMPATIBLE"):
        profiles.validate_runtime_profile(
            service, fresh(value), task(value, "fundamental_analysis")
        )


async def test_case_05_explicit_terra_preserved():
    _, value = await confirmed()
    goal = value.goal.model_copy(
        update={"preferences": {"model_selection": {"route_id": "teamorouter-terra"}}}
    )
    only = [task(value, "fundamental_analysis")]
    result = profiles.resolve_execution_snapshot(value.scheme, goal, only)
    p = result.nodes[0].profile
    assert p.requested_route == "teamorouter-terra" and p.selection_origin == "USER_EXPLICIT"
    assert p.profile_default_route == "teamorouter-sol"
    assert p.recovery_fallback_routes == ()
    assert p.observed_route == "UNKNOWN_AT_CONFIRM"


async def test_case_06_terra_denied_task():
    _, value = await confirmed()
    goal = value.goal.model_copy(
        update={"preferences": {"model_selection": {"route_id": "teamorouter-terra"}}}
    )
    with pytest.raises(BindingDenied, match="MODEL_NOT_AUTHORIZED"):
        profiles.resolve_execution_snapshot(value.scheme, goal, [task(value, "peer_analysis")])


async def test_case_07_method_allowlist():
    _, value = await confirmed()
    p = profile(value, "fundamental_analysis")
    for method in ("fundamental_analysis_v1", "revenue_growth_v1", "ebitda_margin_v1"):
        p.require_method(method)
    with pytest.raises(BindingDenied):
        p.require_method("generated_dcf")


async def test_case_08_tool_allowlist():
    _, value = await confirmed()
    p = profile(value, "fundamental_analysis")
    p.require_tool("revenue_growth")
    with pytest.raises(BindingDenied):
        p.require_tool("python_exec")


async def test_case_09_default_behavior():
    service, value = await confirmed()
    for t in value.runtime.actual_graph.tasks:
        p = profiles.validate_runtime_profile(service, fresh(value), t)
        assert p.requested_route is None and p.selection_origin == "SYSTEM_DEFAULT"
        assert p.allowed_model_routes == TASK_POLICIES[t.task_type].candidates


async def test_case_10_missing_corrupt_binding():
    _, value = await confirmed()
    missing = fresh(value)
    missing.node_binding.execution_snapshot = None
    with pytest.raises(BindingDenied, match="PROFILE_BINDING_MISSING"):
        validate_root(missing)
    corrupt = fresh(value)
    corrupt.node_binding.execution_snapshot["nodes"][0]["profile"]["profile_version"] = "tampered"
    with pytest.raises(ValueError, match="Corrupt execution profile"):
        validate_root(corrupt)


async def test_case_11_graph_identity_change():
    _, value = await confirmed()
    altered = fresh(value)
    altered.runtime.actual_graph.version += 1
    with pytest.raises(BindingDenied, match="graph identity"):
        compare_whole(value, altered)


async def test_case_12_run_isolation():
    _, a = await confirmed("ALPHA")
    _, b = await confirmed("BETA")
    with pytest.raises(BindingDenied, match="PROFILE_BINDING_MISSING"):
        snapshot(a).for_task(b.runtime.actual_graph.tasks[0])
    assert a.node_binding.execution_snapshot is not b.node_binding.execution_snapshot


@pytest.mark.parametrize(
    "field",
    ["scenario_snapshot_digest", "execution_profile_snapshot_digest"],
    ids=["case_13_scenario_digest", "case_14_execution_digest"],
)
async def test_fresh_digest_repeatability(field, tmp_path):
    _, value = await confirmed()
    frozen = snapshot(value)
    path = tmp_path / "snapshot.json"
    path.write_text(frozen.model_dump_json())
    code = (
        "import sys; from src.domain.execution_profile import ExecutionSnapshot as E; "
        "from pathlib import Path; s=E.model_validate_json(Path(sys.argv[1]).read_text()); "
        "print(getattr(E.freeze(s.scenario,s.nodes),sys.argv[2]))"
    )
    outputs = []
    for _ in range(2):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code, str(path), field, stdout=asyncio.subprocess.PIPE
        )
        out, _ = await process.communicate()
        assert process.returncode == 0
        outputs.append(out.decode().strip())
    assert outputs == [getattr(frozen, field)] * 2


async def test_case_15_company_is_run_input():
    _, a = await confirmed("ALPHA")
    _, b = await confirmed("BETA")
    assert snapshot(a).scenario == snapshot(b).scenario
    assert [n.profile for n in snapshot(a).nodes] == [n.profile for n in snapshot(b).nodes]
    assert a.goal.research_object_id != b.goal.research_object_id


async def test_case_16_unapproved_method_at_dispatch():
    from src.application.execution import IntegratedTaskExecutor
    from src.application.repository import node_invocation

    service, value = await confirmed()
    t = task(value, "fundamental_analysis")
    executor = IntegratedTaskExecutor(service, value)
    owner = await service.repository.claim_execution(value.run.run_id)
    # Native dispatch checks method/tool permission before looking up any registry entry.
    from types import SimpleNamespace

    token = node_invocation.set(SimpleNamespace(run_id=t.run_id, task_id=t.task_id))
    try:
        with pytest.raises(BindingDenied, match="TOOL_NOT_AUTHORIZED"):
            await executor._execute_calculation(
                task=t, capability_id="generated_dcf", inputs={}, context=None
            )
    finally:
        node_invocation.reset(token)
    assert owner.run_id == t.run_id


async def test_case_17_no_ambient_tools():
    _, value = await confirmed()
    before = profile(value).allowed_tool_ids
    with pytest.raises(BindingDenied):
        profile(value).require_tool("official_document_search")
    assert profile(value).allowed_tool_ids == before


async def test_case_18_unapproved_provider_dispatch():
    from types import SimpleNamespace

    _, value = await confirmed()
    with (
        invocation(value, "peer_analysis"),
        pytest.raises(BindingDenied, match="MODEL_NOT_AUTHORIZED"),
    ):
        profiles.authorize_model_provider(
            SimpleNamespace(provider_name="teamorouter", model_name="gpt-5.6-terra", route_ids={})
        )


async def test_case_19_dependencies_fixed():
    _, value = await confirmed()
    altered = fresh(value)
    task(altered, "report_synthesis").dependencies = []
    with pytest.raises(BindingDenied):
        compare_whole(value, altered)


async def test_case_20_registered_data_not_permission(monkeypatch):
    from src.data.capability_policy import CAPABILITIES

    _, value = await confirmed()
    monkeypatch.setitem(CAPABILITIES, "new_registered", ("fmp",))
    with invocation(value), pytest.raises(BindingDenied, match="DATA_CAPABILITY_NOT_AUTHORIZED"):
        profiles.authorize_data_request(
            ProviderRequest(symbol="ALPHA", as_of=value.run.as_of, dataset="new_registered"), "fmp"
        )


async def test_case_21_recovery_envelope_persisted():
    _, value = await confirmed()
    p = profile(fresh(value), "report_synthesis")
    assert p.recovery_budget.max_total_attempts_per_task == 4
    assert p.recovery_budget.max_model_fallbacks == 2
    assert p.recovery_budget.max_runtime_replans == 0
    assert p.owner_policy.dynamic_grants == TASK_POLICIES["report_synthesis"].dynamic_grants


async def test_case_22_no_aggregate_budget_admits():
    service, value = await confirmed()
    assert "budget" not in value.goal.preferences
    owner = await service.repository.claim_execution(value.run.run_id)
    assert owner.run_id == value.run.run_id
    assert all(
        p.max_requests > 0 for n in snapshot(value).nodes for p in n.profile.data_permissions
    )


async def test_case_23_budget_policy_durable():
    _, value = await confirmed()
    assert snapshot(fresh(value)).scenario.budget_policy == "WIDE_NODE_LEVEL_ENVELOPES_V1"


async def test_case_24_absent_numeric_ceiling_explicit():
    _, value = await confirmed()
    s = snapshot(value).scenario
    assert s.aggregate_numeric_ceiling == "NOT_YET_ENFORCED_IN_V1"
    assert not isinstance(s.aggregate_numeric_ceiling, (int, float))


async def test_case_25_existing_measurable_exhaustion():
    _, value = await confirmed()
    request = ProviderRequest(
        symbol="ALPHA", as_of=value.run.as_of, dataset="company_profile", limit=1
    )
    with invocation(value):
        for _ in range(profile(value).data_permission("company_profile").max_requests):
            profiles.authorize_data_request(request, "fmp")
        with pytest.raises(BindingDenied, match="DATA_REQUEST_ENVELOPE_EXHAUSTED"):
            profiles.authorize_data_request(request, "fmp")


async def test_case_26_versioned_tightening():
    service, value = await confirmed()
    old = snapshot(value)
    p = profile(value, "fundamental_analysis")
    narrowed = p.model_copy(
        update={
            "profile_version": "2",
            "recovery_budget": p.recovery_budget.model_copy(
                update={"max_total_attempts_per_task": 2}
            ),
        }
    )
    scenario = old.scenario.model_copy(
        update={"scenario_version": "2", "execution_family_version": "2"}
    )
    new = profiles.resolve_execution_snapshot(
        value.scheme,
        value.goal,
        value.runtime.actual_graph.tasks,
        service,
        scenario=scenario,
        node_profiles={"fundamental_analysis": narrowed},
    )
    assert new.scenario.scenario_version == "2"
    assert (
        new.for_task(
            task(value, "fundamental_analysis")
        ).recovery_budget.max_total_attempts_per_task
        == 2
    )
    assert snapshot(fresh(value)) == old
    assert new.execution_profile_snapshot_digest != old.execution_profile_snapshot_digest


async def test_case_27_real_provider_boundary_rejects_registered_capability():
    from src.adapters.fmp import FMPProvider

    _, value = await confirmed()

    class NeverTransport:
        async def request(self, **kwargs):
            pytest.fail("Unauthorized capability reached transport")

    with invocation(value), pytest.raises(BindingDenied, match="DATA_CAPABILITY_NOT_AUTHORIZED"):
        await FMPProvider(NeverTransport()).probe(
            ProviderRequest(symbol="ALPHA", as_of=value.run.as_of, dataset="peer_multiples")
        )


async def test_case_28_finite_profile_not_system_limits():
    _, value = await confirmed()
    for n in snapshot(value).nodes:
        p = n.profile
        assert p.profile_version == "1" and p.envelope_classification == "PROFILE_POLICY"
        if p.recovery_budget:
            assert 0 < p.recovery_budget.max_total_attempts_per_task <= 4
        for d in p.data_permissions:
            assert 0 < d.observation_limit <= 500 and 0 < d.max_requests < 100


@pytest.mark.parametrize(
    "scope,kind,expected",
    [
        (
            "COMPANY",
            "evidence_collection",
            {
                "company_profile",
                "annual_financials",
                "balance_sheet",
                "cash_flow",
                "market_price",
                "historical_prices",
                "analyst_recommendations",
            },
        ),
        ("PEER", "peer_analysis", {"peer_multiples"}),
        ("RESEARCH_NEWS", "research_news_analysis", {"news", "transcript"}),
    ],
    ids=["case_29_COMPANY", "case_30_PEER", "case_31_RESEARCH_NEWS"],
)
async def test_exact_product_adopted_request_sets(scope, kind, expected):
    _, value = await confirmed()
    p = profile(value, kind)
    assert set(p.allowed_data_capability_ids) == expected
    assert p.data_scope_ids == (scope,)
    current = evidence_request_plans(
        symbol="ALPHA", as_of=value.run.as_of, scope=EvidenceAcquisitionScope(scope)
    )
    with invocation(value, kind):
        actual = profiles.profile_request_plans(
            symbol="ALPHA", as_of=value.run.as_of, scope=EvidenceAcquisitionScope(scope)
        )
    assert actual == current


async def test_case_32_bocha_arbitrary_capability_rejected():
    from src.adapters.bocha import BochaDiscovery

    _, value = await confirmed()
    with invocation(value, "research_news_analysis"), pytest.raises(BindingDenied):
        await BochaDiscovery(None).acquire(
            ProviderRequest(symbol="ALPHA", as_of=value.run.as_of, dataset="news", limit=5),
            "web_research",
        )


async def test_case_33_history_optional_context():
    _, value = await confirmed()
    p = profile(value).data_permission("historical_prices")
    assert p.observation_limit == 250
    assert p.purpose == "historical_market_context"
    assert p.requirement == "ALLOWED_COLLECTOR_OWNS_REQUIREMENT"
    assert all("technical" not in m for m in profile(value).allowed_method_ids)


async def test_case_34_analyst_opinion_context():
    _, value = await confirmed()
    p = profile(value).data_permission("analyst_recommendations")
    assert p.category == "ANALYST" and p.purpose == "analyst_consensus_context"
    assert p.requirement == "ALLOWED_COLLECTOR_OWNS_REQUIREMENT"
    assert "ACCEPTED" in profile(value).evidence_requirement


async def test_case_35_narrowed_data_version_consumed():
    _, value = await confirmed()
    old = snapshot(value)
    p = profile(value)
    narrowed = p.model_copy(
        update={
            "profile_version": "2",
            "data_permission_policy_version": "v2",
            "data_permissions": tuple(
                x for x in p.data_permissions if x.capability_id != "historical_prices"
            ),
        }
    )
    scenario = old.scenario.model_copy(
        update={"scenario_version": "2", "execution_family_version": "2"}
    )
    adopted = profiles.resolve_execution_snapshot(
        value.scheme,
        value.goal,
        value.runtime.actual_graph.tasks,
        scenario=scenario,
        node_profiles={"evidence_collection": narrowed},
    )
    narrowed = adopted.for_task(task(value, "evidence_collection"))
    with invocation(value, override=narrowed):
        plans = profiles.profile_request_plans(
            symbol="ALPHA", as_of=value.run.as_of, scope=EvidenceAcquisitionScope.COMPANY
        )
        assert "historical_prices" not in {x.request.dataset for x in plans}
        with pytest.raises(BindingDenied):
            profiles.authorize_data_request(
                ProviderRequest(symbol="ALPHA", as_of=value.run.as_of, dataset="historical_prices"),
                "fmp",
            )
    assert snapshot(fresh(value)) == old


async def test_frozen_model_attempt_ceiling_is_consumed_without_durable_recovery():
    from src.adapters.llm.provider import LLMFailureClassification as Code
    from src.agentic.recovery import RecoveryStopped
    from src.domain.recovery import RecoveryBudget
    from tests.unit.agentic.test_adaptive_recovery import Output, context, setup

    _, value = await confirmed()
    recovery, clients, store = setup(first_failure=Code.PROVIDER_UNAVAILABLE)
    frozen = profile(value, "fundamental_analysis").model_copy(
        update={
            "recovery_budget": RecoveryBudget(max_total_attempts_per_task=1),
            "recovery_fallback_routes": profile(value, "fundamental_analysis").allowed_model_routes,
            "runtime_configuration": {
                "recovery": profiles.canonical_value(profiles.recovery_configuration(recovery))
            },
        }
    )
    frozen = frozen.model_copy(
        update={
            "runtime_configuration_digest": profiles.digest(
                frozen.runtime_configuration, "execution-composition/v1"
            )
        }
    )
    frozen = type(frozen).model_validate(frozen.model_dump())
    with invocation(value, "fundamental_analysis", override=frozen):
        with pytest.raises(RecoveryStopped):
            await recovery.execute(
                context(task(value, "fundamental_analysis")),
                clients["teamorouter-sol"],
                messages=[],
                response_model=Output,
            )
    assert sum(c.calls for c in clients.values()) == 1
    assert len([r for r in store.values if r.kind == "ATTEMPT_STARTED"]) == 1


async def test_configured_profile_default_origin_is_distinct():
    from src.agentic.composition import build_research_agent_registry
    from tests.unit.agentic.test_adaptive_recovery import Client

    service, value = await confirmed()
    mimo = Client("mimo", "mimo-v2.5")
    mimo.task_profile = "peer_analysis"
    service.agent_registry = build_research_agent_registry(
        Client("teamorouter", "gpt-5.6-sol"), None, profile_providers={"peer_analysis": mimo}
    )
    resolved = profiles.resolve_execution_snapshot(
        value.scheme, value.goal, value.runtime.actual_graph.tasks, service
    )
    assert resolved.for_task(task(value, "peer_analysis")).selection_origin == "PROFILE_DEFAULT"
    assert (
        resolved.for_task(task(value, "fundamental_analysis")).selection_origin == "SYSTEM_DEFAULT"
    )


async def test_post_confirm_provider_change_fails_before_dispatch():
    from src.agentic.composition import build_research_agent_registry
    from tests.unit.agentic.test_adaptive_recovery import Client

    service, value = await confirmed()
    changed = Client("teamorouter", "gpt-5.6-sol")
    service.agent_registry = build_research_agent_registry(changed, None)
    with pytest.raises(BindingDenied, match="PROFILE_COMPOSITION_INCOMPATIBLE"):
        profiles.validate_runtime_profile(service, value, task(value, "fundamental_analysis"))
    assert changed.calls == 0


async def test_current_request_plan_addition_does_not_grant_product_permission(monkeypatch):
    from dataclasses import replace

    _, value = await confirmed()
    original = profiles.evidence_request_plans

    def expanded(**kwargs):
        plans = original(**kwargs)
        if kwargs["scope"] == EvidenceAcquisitionScope.COMPANY:
            plans += (
                replace(
                    plans[0],
                    request=plans[0].request.model_copy(
                        update={"dataset": "official_document_search"}
                    ),
                ),
            )
        return plans

    monkeypatch.setattr(profiles, "evidence_request_plans", expanded)
    with pytest.raises(BindingDenied, match="DATA_PERMISSION_ADOPTION_REQUIRED"):
        profiles.resolve_execution_snapshot(
            value.scheme, value.goal, value.runtime.actual_graph.tasks
        )
