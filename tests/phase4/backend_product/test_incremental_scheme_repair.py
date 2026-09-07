"""Actual request serialization + response parser; HTTP mocked, never admits a Run."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.teamorouter import TeamoRouterClient
from src.agentic.llm_integration import (
    IncrementalDecisionProposal,
    IncrementalSchemeProposal,
    PlannerProviderSchemeGenerator,
    SchemeProposal,
)
from src.agentic.planning_errors import IncrementalSchemeFailure
from src.domain.incremental import IncrementalDecision
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.phase4_product.admission import build_prepare_draft, draft_hash_is_valid
from src.phase4_product.contracts import PrepareResearchRunRequestV1
from src.phase4_product.incremental import (
    build_incremental_context,
    resolve_incremental_decisions,
    validate_incremental_scheme,
)
from src.phase4_product.memory_contracts import ResearchViewVersion
from src.phase4_product.projections import project_goal, project_scheme
from tests.unit.llm.test_agentic_llm_integration import valid_scheme
from tests.unit.llm.test_teamorouter import settings


def real_inputs():
    view = ResearchViewVersion.model_validate_json(
        Path("tests/fixtures/phase5b_base_view.json").read_text()
    )
    obj = ResearchObject(
        object_id="OBJ-NVDA", symbol="NVDA", company_name="NVIDIA Corporation", exchange="NASDAQ"
    )
    goal = ResearchGoal(
        goal_id="GOAL-SCHEME-LOCAL-PREVIEW",
        research_object_id=obj.object_id,
        goal_text="更新 NVIDIA 营收增长、估值与风险研究；重新取得当前证据并检查期间一致性。",
        as_of=date(2026, 9, 7),
    )
    context = build_incremental_context(
        view,
        object_id=obj.object_id,
        base_run_id=view.source_run_id,
        base_view_id=view.research_view_version_id,
        target_as_of=goal.as_of,
    )
    return view, obj, goal, context


def valid_incremental(context):
    proposal = valid_scheme()
    proposal["research_scope"] = [
        "重新获取公司财务证据",
        "重新验证营收增长结论",
        "检查财务输入期间一致性",
        "当前估值与风险研究",
    ]
    proposal["data_requirements"] = ["本次独立取得权威公司披露和财务输入，不复制历史证据"]
    proposal["report_requirements"] = ["区分历史背景和本次验证结论，标记尚未确定的信息"]
    proposal["incremental_decisions"] = [
        dict(source_identity=d.source_identity, decision=d.decision, reason=d.reason)
        for d in context.decisions
    ]
    return proposal


def strict_schema(schema):
    """The provider's closed-object/required-property subset, including nested definitions."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False
            assert set(schema.get("required", [])) == set(schema.get("properties", {}))
        for value in schema.values():
            strict_schema(value)
    elif isinstance(schema, list):
        for value in schema:
            strict_schema(value)


def test_original_open_dictionary_reproduces_strict_schema_contract_defect():
    class OldProposal(SchemeProposal):
        incremental_decision_reasons: dict[str, str]

    with pytest.raises(AssertionError):
        strict_schema(OldProposal.model_json_schema())
    strict_schema(IncrementalSchemeProposal.model_json_schema())


async def generate_through_http(proposal=None, *, status=200, raw=None, context=None):
    _, obj, goal, baseline = real_inputs()
    context = context or baseline
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        strict_schema(payload["response_format"]["json_schema"]["schema"])
        seen.append(payload)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "PRIVATE_PROVIDER_BODY"}})
        return httpx.Response(
            200,
            json={
                "model": "test-planner-local",
                "choices": [
                    {
                        "message": {
                            "content": raw
                            if raw is not None
                            else json.dumps(proposal or valid_incremental(context))
                        }
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TeamoRouterClient(
            settings(),
            client=http,
            execution_policy=ProviderExecutionPolicyV1(
                max_attempts=1, overall_workload_deadline_seconds=90
            ),
        )
        generator = PlannerProviderSchemeGenerator(client, max_validation_attempts=1)
        scheme = await generator.generate(
            research_object=obj, goal=goal, incremental_context=context
        )
    return scheme, seen


async def test_sparse_real_memory_zero_reuse_http_schema_parser_draft_closure():
    view, obj, goal, context = real_inputs()
    original = view.model_dump_json()
    assert [d.decision for d in context.decisions] == ["REFRESH", "REVALIDATE", "PREVENT"]
    scheme, requests = await generate_through_http()
    validate_incremental_scheme(scheme, context)
    sent = json.loads(requests[0]["messages"][1]["content"])
    assert sent["previous_research_memory"]["prior_summary"] == view.summary
    assert {d["source_identity"] for d in sent["previous_research_memory"]["decisions"]} == {
        i.memory_item_id for i in view.items
    }
    assert len(requests) == 1 and "runtime_events" not in json.dumps(sent)
    assert view.model_dump_json() == original
    scheme.assurance_requirements = {}
    request = PrepareResearchRunRequestV1(
        research_object_id=obj.object_id,
        research_goal=goal.goal_text,
        as_of=goal.as_of,
        base_run_id=view.source_run_id,
        base_research_view_version=view.research_view_version_id,
    )
    draft = build_prepare_draft(
        request,
        draft_id="DRAFT-SCHEME-LOCAL-PREVIEW",
        goal=project_goal(goal, expected_object_id=obj.object_id),
        scheme_snapshot=project_scheme(
            scheme,
            expected_object_id=obj.object_id,
            expected_goal_id=goal.goal_id,
            require_confirmed=False,
        ),
    )
    assert draft_hash_is_valid(draft)
    assert draft.scheme_snapshot.confirmed_at is None
    assert "run_id" not in draft.model_dump()  # no R2, graph or runtime output is created


@pytest.mark.parametrize(
    "change", ["foreign", "missing", "duplicate", "unsupported_reuse", "unknown_upgrade"]
)
async def test_exact_decision_validation_fails_closed(change):
    *_, context = real_inputs()
    proposal = valid_incremental(context)
    if change == "foreign":
        proposal["incremental_decisions"][0]["source_identity"] = "FOREIGN"
    if change == "missing":
        proposal["incremental_decisions"].pop()
    if change == "duplicate":
        proposal["incremental_decisions"].append(proposal["incremental_decisions"][0])
    if change == "unsupported_reuse":
        proposal["incremental_decisions"][0]["decision"] = "REUSE"
    if change == "unknown_upgrade":
        context = context.model_copy(
            update={
                "decisions": (
                    context.decisions[0].model_copy(update={"decision": "UNKNOWN"}),
                    *context.decisions[1:],
                )
            }
        )
    with pytest.raises(IncrementalSchemeFailure) as error:
        await generate_through_http(proposal, context=context)
    assert error.value.stage == "DECISION_VALIDATION"
    assert "FOREIGN" not in str(error.value)


@pytest.mark.parametrize(
    "raw,stage",
    [
        ("not-json", "DECODER_PARSER"),
        ('{"bad":"PRIVATE_PROVIDER_BODY"}', "STRUCTURED_OUTPUT_SCHEMA"),
    ],
)
async def test_malformed_output_keeps_safe_failure_classification(raw, stage):
    with pytest.raises(IncrementalSchemeFailure) as error:
        await generate_through_http(raw=raw)
    assert error.value.stage == stage and error.value.attempted_count == 1
    assert "PRIVATE_PROVIDER_BODY" not in str(error.value)


@pytest.mark.parametrize(
    "status,classification",
    [(400, "request_rejected"), (401, "authentication_failure"), (429, "quota_or_rate_limit")],
)
async def test_provider_failure_does_not_disappear(status, classification):
    with pytest.raises(IncrementalSchemeFailure) as error:
        await generate_through_http(status=status)
    assert error.value.provider_failure == classification
    assert error.value.attempted_count == 1
    assert "PRIVATE_PROVIDER_BODY" not in str(error.value)


def test_reuse_mechanism_requires_an_explicit_eligible_context_source():
    *_, context = real_inputs()
    eligible = IncrementalDecision(
        decision="REUSE",
        category="VIEW_CONTEXT",
        source_run_id=context.base_run_id,
        source_identity=context.base_research_view_version,
        statement="Explicitly eligible historical context",
        reason="Historical applicability only",
    )
    synthetic = context.model_copy(update={"decisions": (eligible,)})
    result = resolve_incremental_decisions(
        synthetic,
        [
            IncrementalDecisionProposal(
                source_identity=eligible.source_identity,
                decision="REUSE",
                reason="Historical context only, not current evidence",
            )
        ],
    )
    assert result.decisions[0].source_run_id == context.base_run_id
    assert not any(d.decision == "REUSE" for d in context.decisions)


async def test_research_lead_can_propose_metric_revalidation():
    *_, context = real_inputs()
    proposal = valid_incremental(context)
    proposal["incremental_decisions"][0]["decision"] = "REVALIDATE"
    scheme, _ = await generate_through_http(proposal)
    validate_incremental_scheme(scheme, context)
    assert scheme.incremental_context.decisions[0].decision == "REVALIDATE"


async def test_independent_plan_contract_without_run_creation():
    from datetime import UTC, datetime

    from src.agentic.llm_integration import PlannerProviderResearchLeadPlanner
    from src.phase4_product.incremental import bind_incremental_plan
    from tests.unit.llm.test_agentic_llm_integration import valid_graph

    _, obj, goal, context = real_inputs()
    scheme, _ = await generate_through_http()
    scheme = scheme.model_copy(update={"confirmed_at": datetime.now(UTC)})

    def handler(request):
        payload = json.loads(request.content)
        sent = json.loads(payload["messages"][1]["content"])
        assert sent["confirmed_scheme"]["incremental_context"]["base_run_id"] == context.base_run_id
        return httpx.Response(
            200,
            json={
                "model": "test-planner-local",
                "choices": [{"message": {"content": json.dumps(valid_graph())}}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        planner = PlannerProviderResearchLeadPlanner(TeamoRouterClient(settings(), client=http))
        graph = await planner.plan(run_id="PREVIEW-ONLY", goal=goal, scheme=scheme)
    graph = bind_incremental_plan(graph, context)
    assert all(
        t.task_id.startswith("PREVIEW-ONLY:") and t.run_id != context.base_run_id
        for t in graph.tasks
    )
    assert all(
        not t.task_input_evidence_ids and "period consistency" in t.goal for t in graph.tasks
    )
    assert obj.object_id == context.research_object_id


@pytest.mark.parametrize(
    "field,value", [("research_object_id", "FOREIGN"), ("target_as_of", date(2026, 9, 8))]
)
async def test_provider_not_called_for_foreign_planning_input(field, value):
    *_, context = real_inputs()
    with pytest.raises(IncrementalSchemeFailure, match="PLANNING_INPUT_CONTRACT"):
        await generate_through_http(context=context.model_copy(update={field: value}))


def test_empty_memory_does_not_fabricate_reuse():
    view, obj, goal, _ = real_inputs()
    empty = view.model_copy(update={"items": (), "summary": None})
    context = build_incremental_context(
        empty,
        object_id=obj.object_id,
        base_run_id=view.source_run_id,
        base_view_id=view.research_view_version_id,
        target_as_of=goal.as_of,
    )
    assert context.decisions == () and context.prior_summary is None


def test_unknown_issue_does_not_gain_period_authority_by_substring():
    view, obj, goal, _ = real_inputs()
    issue = view.items[-1].model_copy(update={"statement": "SOME_UNSUPPORTED_PERIOD_THING"})
    context = build_incremental_context(
        view.model_copy(update={"items": (issue,)}),
        object_id=obj.object_id,
        base_run_id=view.source_run_id,
        base_view_id=view.research_view_version_id,
        target_as_of=goal.as_of,
    )
    assert context.decisions[0].decision == "UNKNOWN"
