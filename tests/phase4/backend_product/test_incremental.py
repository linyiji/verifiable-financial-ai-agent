"""Provider-free exact incremental context, scheme, admission and quarantine gates."""

from copy import deepcopy
from datetime import UTC, date, datetime

import pytest

from src.agentic.llm_integration import TeamoRouterSchemeGenerator, _planner_messages
from src.agentic.planner import ResearchLeadPlanner
from src.domain.incremental import IncrementalResearchContext
from src.domain.research_run import ResearchRun
from src.phase4_product.admission import build_prepare_draft, draft_hash_is_valid
from src.phase4_product.contracts import PrepareResearchRunRequestV1
from src.phase4_product.errors import ProductError
from src.phase4_product.incremental import (
    bind_incremental_plan,
    build_incremental_context,
    validate_incremental_scheme,
)
from src.phase4_product.memory import build_memory_versions
from src.phase4_product.memory_contracts import MemoryItem
from src.phase4_product.projections import project_goal, project_scheme
from tests.phase4.backend_product.test_memory_source import source
from tests.unit.llm.test_agentic_llm_integration import FakeProvider, research_inputs, valid_scheme


def context():
    _, view = build_memory_versions("OBJ-A", "RUN-A", *source())
    issue = MemoryItem(
        memory_item_id="MI-ISSUE",
        category="RESOLVED_ISSUE",
        source_run_id="RUN-A",
        reference_id="CORR-A",
        title="Resolved issue",
        statement="PERIOD_MISMATCH",
        review_id="REVIEW-A",
        report_id="REPORT-A",
    )
    view = view.model_copy(update={"items": (*view.items, issue)})
    return build_incremental_context(
        view,
        object_id="OBJ-A",
        base_run_id="RUN-A",
        base_view_id=view.research_view_version_id,
        target_as_of=date(2026, 9, 7),
    )


def test_four_decisions_exact_immutable_and_bounded():
    c = context()
    assert [d.decision for d in c.decisions] == ["REFRESH", "REVALIDATE", "PREVENT"]
    assert all(d.source_run_id == "RUN-A" for d in c.decisions)
    assert not any(d.decision == "REUSE" for d in c.decisions)
    assert len(c.model_dump_json()) < 6000
    assert not any(
        k in c.model_dump_json() for k in ("runtime_events", "provider_body", "chain_of_thought")
    )
    with pytest.raises(ValueError):
        c.base_run_id = "RUN-B"


@pytest.mark.parametrize(
    "field,value",
    [
        ("object_id", "OBJ-B"),
        ("base_run_id", "RUN-B"),
        ("base_view_id", "RVV-B"),
        ("target_as_of", date(2025, 1, 1)),
    ],
)
def test_exact_base_rejects_mismatch(field, value):
    _, v = build_memory_versions("OBJ-A", "RUN-A", *source())
    args = dict(
        object_id="OBJ-A",
        base_run_id="RUN-A",
        base_view_id=v.research_view_version_id,
        target_as_of=date(2026, 9, 7),
    )
    args[field] = value
    with pytest.raises(ValueError):
        build_incremental_context(v, **args)


@pytest.mark.parametrize("index", [0, 1, 2])
def test_unsupported_reuse_rejected(index):
    c = context().model_dump()
    c["decisions"][index]["decision"] = "REUSE"
    with pytest.raises(ValueError):
        IncrementalResearchContext.model_validate(c)


def test_unknown_does_not_become_reuse():
    c = context().model_dump()
    c["decisions"][1]["decision"] = "UNKNOWN"
    assert IncrementalResearchContext.model_validate(c).decisions[1].decision == "UNKNOWN"


@pytest.mark.parametrize(
    "base", [{"base_run_id": "RUN-A"}, {"base_research_view_version": "RVV-A"}]
)
def test_request_requires_paired_ids(base):
    with pytest.raises(ValueError):
        PrepareResearchRunRequestV1(
            research_object_id="OBJ-A",
            research_goal="Update fundamentals",
            as_of=date(2026, 9, 7),
            **base,
        )


async def ai_scheme():
    obj, goal = research_inputs()
    obj.object_id = "OBJ-A"
    goal.research_object_id = "OBJ-A"
    goal.as_of = date(2026, 9, 7)
    c = context()
    proposal = valid_scheme()
    proposal["incremental_decisions"] = [dict(source_identity=d.source_identity,
        decision=d.decision, reason=d.reason) for d in c.decisions]
    provider = FakeProvider([proposal])
    generator = TeamoRouterSchemeGenerator(provider)
    scheme = await generator.generate(research_object=obj, goal=goal, incremental_context=c)
    return goal, scheme, provider


async def test_ai_receives_bounded_memory_and_scheme_hash_binds_it():
    goal, scheme, provider = await ai_scheme()
    c = scheme.incremental_context
    assert "previous_research_memory" in provider.calls[0][1][1].content
    assert c.base_run_id in provider.calls[0][1][1].content
    validate_incremental_scheme(scheme, context())
    scheme.assurance_requirements = {}
    request = PrepareResearchRunRequestV1(
        research_object_id="OBJ-A",
        research_goal=goal.goal_text,
        as_of=goal.as_of,
        base_run_id=c.base_run_id,
        base_research_view_version=c.base_research_view_version,
    )
    draft = build_prepare_draft(
        request,
        draft_id="DRAFT-R2",
        goal=project_goal(goal, expected_object_id="OBJ-A"),
        scheme_snapshot=project_scheme(
            scheme,
            expected_object_id="OBJ-A",
            expected_goal_id=goal.goal_id,
            require_confirmed=False,
        ),
    )
    assert draft_hash_is_valid(draft)
    altered = draft.model_copy(
        update={
            "scheme_snapshot": draft.scheme_snapshot.model_copy(
                update={"incremental_context": c.model_copy(update={"base_run_id": "RUN-B"})}
            )
        }
    )
    assert not draft_hash_is_valid(altered)


async def test_ai_invalid_reference_no_fallback():
    obj, goal = research_inputs()
    obj.object_id = goal.research_object_id = "OBJ-A"
    goal.as_of = date(2026, 9, 7)
    p = valid_scheme()
    p["incremental_decisions"] = [
        dict(source_identity="FOREIGN", decision="UNKNOWN", reason="Unsupported")
    ]
    generator = TeamoRouterSchemeGenerator(FakeProvider([p]), max_validation_attempts=1)
    with pytest.raises(ValueError, match="DECISION_VALIDATION"):
        await generator.generate(research_object=obj, goal=goal, incremental_context=context())


async def test_independent_run_tasks_new_acquisition_and_checks():
    goal, scheme, _ = await ai_scheme()
    scheme.confirmed_at = datetime.now(UTC)
    graph = ResearchLeadPlanner().plan(run_id="RUN-R2", goal=goal, scheme=scheme)
    original = deepcopy(graph)
    bound = bind_incremental_plan(graph, scheme.incremental_context)
    assert graph == original
    assert all(t.run_id == "RUN-R2" and t.task_id.startswith("RUN-R2:") for t in bound.tasks)
    assert all(
        not t.task_input_evidence_ids and not t.task_output_evidence_ids and t.result_ref is None
        for t in bound.tasks
    )
    assert all("period consistency" in t.goal and "Do not inherit" in t.goal for t in bound.tasks)
    assert "incremental_context" in _planner_messages("RUN-R2", goal, scheme)[1].content
    run = ResearchRun(
        run_id="RUN-R2",
        research_object_id="OBJ-A",
        goal_id=goal.goal_id,
        scheme_id=scheme.scheme_id,
        as_of=goal.as_of,
        base_run_id="RUN-A",
        base_research_view_version=scheme.incremental_context.base_research_view_version,
    )
    assert ResearchRun.model_validate(run.model_dump()).base_run_id == "RUN-A"


@pytest.mark.parametrize("mutation", ["run", "task", "evidence", "output", "result"])
async def test_cross_run_initial_plan_quarantine(mutation):
    goal, scheme, _ = await ai_scheme()
    scheme.confirmed_at = datetime.now(UTC)
    graph = ResearchLeadPlanner().plan(run_id="RUN-R2", goal=goal, scheme=scheme)
    if mutation == "run":
        graph.run_id = "RUN-A"
    if mutation == "task":
        graph.tasks[0].run_id = "RUN-A"
    if mutation == "evidence":
        graph.tasks[0].task_input_evidence_ids = ["R1-EVD"]
    if mutation == "output":
        graph.tasks[0].task_output_evidence_ids = ["R1-EVD"]
    if mutation == "result":
        graph.tasks[0].result_ref = "R1-RESULT"
    with pytest.raises(ValueError):
        bind_incremental_plan(graph, context())


def test_no_base_fields_added_to_historical_serialization():
    run = ResearchRun(
        run_id="RUN-A",
        research_object_id="OBJ-A",
        goal_id="G",
        scheme_id="S",
        as_of=date(2026, 9, 6),
    )
    assert "base_run_id" not in run.model_dump()


@pytest.mark.parametrize("status", ["FAILED", "RUNNING", "REVIEW", "CANCELLED"])
def test_r2_nonrelease_no_memory(status):
    data = source()
    data[0].run.status = status
    with pytest.raises(ProductError):
        build_memory_versions("OBJ-A", "RUN-A", *data, version=2)
