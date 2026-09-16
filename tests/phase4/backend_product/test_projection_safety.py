from __future__ import annotations

import math

import pytest

from src.phase4_product.safety import (
    UnsafeProjectionData,
    is_protected_key,
    safe_json,
    safe_json_object,
    safe_text,
)


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "apiKey",
        "Authorization",
        "bearer-token",
        "clientSecret",
        "providerCredentials",
        "raw_provider_payload",
        "rawResponse",
        "raw_artifact_ref",
        "storageLocator",
        "source_locator",
        "filePath",
        "systemPrompt",
        "chainOfThought",
        "scratchpad",
        "hiddenReasoning",
        "reasoningTrace",
        "sql_query",
        "stackTrace",
    ],
)
def test_protected_key_families_are_recognized_after_normalization(key: str) -> None:
    assert is_protected_key(key)


@pytest.mark.parametrize(
    "protected_key",
    [
        "apiKey",
        "authorization",
        "provider_secret",
        "rawProviderPayload",
        "chain_of_thought",
        "scratchpad",
        "hiddenReasoning",
        "artifactRef",
        "sourceLocator",
        "file_path",
        "stackTrace",
    ],
)
def test_recursive_projection_safety_rejects_secret_cot_and_internal_keys(
    protected_key: str,
) -> None:
    value = {
        "public": {
            "entries": [
                {"name": "safe"},
                {"name": "unsafe", protected_key: "must-never-leak"},
            ]
        }
    }
    allowlist = {
        "public": {
            "entries": {
                "name": None,
                # A protected key remains forbidden even if a caller mistakenly
                # places it in its positive allowlist.
                protected_key: None,
            }
        }
    }

    with pytest.raises(UnsafeProjectionData, match="protected key"):
        safe_json_object(value, allowed_keys=allowlist)


def test_safe_json_copies_reviewed_nested_data_without_aliasing() -> None:
    source = {
        "summary": "verified",
        "subjects": [
            {"subject_id": "CALC-A", "status": "PASS"},
            {"subject_id": "CLAIM-A", "status": "PASS"},
        ],
        "counts": [1, 2],
    }
    allowlist = {
        "summary": None,
        "subjects": {"subject_id": None, "status": None},
        "counts": None,
    }

    copied = safe_json_object(source, allowed_keys=allowlist)
    assert copied == source
    assert copied is not source
    assert copied["subjects"] is not source["subjects"]
    source["subjects"][0]["status"] = "BLOCK"  # type: ignore[index]
    assert copied["subjects"][0]["status"] == "PASS"  # type: ignore[index]


def test_positive_allowlist_rejects_unknown_nested_fields() -> None:
    with pytest.raises(UnsafeProjectionData, match="unapproved key 'debug'"):
        safe_json_object(
            {"result": {"value": "0.42", "debug": "internal"}},
            allowed_keys={"result": {"value": None}},
        )


@pytest.mark.parametrize(
    "coverage",
    [
        {"invented_endpoint": {"status": "AVAILABLE"}},
        {"quote": {"status": "AVAILABLE", "debug": "hidden"}},
    ],
)
def test_source_coverage_rejects_unowned_fields(coverage):
    from src.phase4_product.projections import _TASK_COVERAGE_ALLOWLIST

    with pytest.raises(UnsafeProjectionData):
        safe_json_object(coverage, allowed_keys=_TASK_COVERAGE_ALLOWLIST)


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "artifact://reports/internal.html",
        "file:///private/report.html",
        "/Users/operator/.config/provider.json",
        "/tmp/provider-response.json",
        "../secrets/provider.env",
        "C:\\Users\\operator\\secret.txt",
        "-----BEGIN PRIVATE KEY-----\nsecret",
        "Traceback (most recent call last):\ninternal.py:1",
    ],
)
def test_safe_text_rejects_internal_locator_path_key_and_stack_values(
    unsafe_value: str,
) -> None:
    with pytest.raises(UnsafeProjectionData, match="protected internal data"):
        safe_text(unsafe_value)


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "  /Users/operator/.config/provider.json",
        "Provider result was loaded from /Users/operator/private/provider.json",
        "Temporary response retained at /tmp/provider-response.json",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret.signature",
        "Bearer top-secret-credential",
        "Provider returned Bearer top-secret-credential",
        "upstream api_key=must-never-leak",
        "sk-proj-dummycredentialvalue000000000000",
        "sk_" + "live_dummycredentialvalue000000000000",
        "ghp_dummycredentialvalue000000000000",
        "glpat-dummycredentialvalue000000000000",
        "hf_dummycredentialvalue000000000000",
        "AKIAIOSFODNN7EXAMPLE",
        "eyJhbGciOiJIUzI1NiJ9.c2Vuc2l0aXZlLWR1bW15.c2lnbmF0dXJlLWR1bW15",
    ],
)
def test_safe_text_rejects_embedded_paths_and_secret_assignments(unsafe_value: str) -> None:
    with pytest.raises(UnsafeProjectionData, match="protected internal data"):
        safe_text(unsafe_value)


def test_same_origin_authorized_resource_path_is_safe_text_not_a_bearer_locator() -> None:
    ref = "/api/research-runs/RUN-A/artifacts/ARTIFACT-A/content"
    assert safe_text(ref) == ref


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, b"raw", object()])
def test_non_json_or_non_finite_projection_values_fail_closed(value: object) -> None:
    with pytest.raises(UnsafeProjectionData):
        safe_json({"value": value}, allowed_keys={"value"})


def test_recursive_objects_and_depth_overflow_fail_closed() -> None:
    recursive: dict[str, object] = {}
    recursive["child"] = recursive
    with pytest.raises(UnsafeProjectionData, match="recursive object"):
        safe_json_object(recursive, allowed_keys={"child"})

    nested: object = "leaf"
    for _ in range(5):
        nested = [nested]
    with pytest.raises(UnsafeProjectionData, match="maximum nesting depth"):
        safe_json(nested, allowed_keys=set(), max_depth=2)


def test_none_child_allowlist_never_opens_an_unreviewed_object() -> None:
    with pytest.raises(UnsafeProjectionData, match="unreviewed nested object"):
        safe_json_object(
            {"metadata": {"surprise": "value"}},
            allowed_keys={"metadata": None},
        )


# Explicit library invocation is the admitted delivery seam for WP07.
from src.phase4_product.admission import (
    build_prepare_draft,
    classify_request_shape_v1,
    clarity_from_prepare_rejection_v1,
    draft_hash_is_valid,
)
from src.phase4_product.contracts import ResearchBriefViewV1, ResearchTaskContractViewV1, TaskProjectionV1
from src.phase4_product.projections import (
    ProjectionIntegrityError,
    derive_research_brief_v1,
    derive_research_task_contract_v1,
    project_goal,
)
from tests.phase4.backend_product.test_admission import _draft, _prepare_values, NOW
from tests.phase4.backend_product.test_api_contract import _admission as _api_admission, _projection


@pytest.mark.parametrize("preferences", [{"unknown": True}, {"currency": {"debug": "hidden"}}])
def test_wp07_policy_rejection_stays_at_existing_boundary(preferences):
    request, goal, _ = _prepare_values()
    raw = request.model_dump(mode="json")
    raw["preferences"] = preferences
    assert classify_request_shape_v1(raw).state == "REQUEST_SHAPE_VALID"
    with pytest.raises(ProjectionIntegrityError):
        project_goal(goal.model_copy(update={"preferences": preferences}), expected_object_id="OBJ-A")
    result = clarity_from_prepare_rejection_v1()
    assert (result.state, result.validation_phase, result.reason_code) == (
        "REJECTED", "EXISTING_PREPARE_POLICY", "EXISTING_POLICY_REJECTION")


def test_wp07_brief_exact_source_fields():
    draft = _draft()
    view = derive_research_brief_v1(draft)
    source = draft.model_dump(mode="json")
    expected = {name: source[name] for name in (
        "draft_id", "draft_version", "draft_hash", "prepare_request_hash", "object_id",
        "scheme_snapshot", "created_at", "expires_at", "planned_graph_availability")}
    expected.update(view_schema_version="phase4-research-brief-view/v1",
                    goal_id=source["goal"]["goal_id"], research_goal=source["goal"]["goal_text"],
                    as_of=source["goal"]["as_of"], preferences=source["goal"]["preferences"],
                    clarity={"view_schema_version": "phase4-request-clarity/v1", "state": "PREPARED",
                             "validation_phase": "PREPARE_RESULT", "reason_code": "EXISTING_DRAFT_PREPARED",
                             "semantic_assessment": "NOT_ASSESSED"})
    assert view.model_dump(mode="json") == expected
    assert "incremental_context" not in expected["scheme_snapshot"]
    assert ResearchBriefViewV1.model_validate_json(view.model_dump_json()) == view
    assert view.model_dump_json() == derive_research_brief_v1(draft).model_dump_json()


@pytest.mark.parametrize("updates", [
    {"object_id": "OBJ-B"}, {"draft_hash": "sha256:" + "0" * 64},
    {"draft_version": 2}, {"expires_at": NOW},
])
def test_wp07_brief_rejects_tamper_without_repair(updates):
    draft = _draft().model_copy(update=updates)
    before = draft.model_dump_json()
    with pytest.raises(ProjectionIntegrityError):
        derive_research_brief_v1(draft)
    assert draft.model_dump_json() == before


def test_wp07_brief_has_no_identity_or_write_effect():
    request, goal, scheme = _prepare_values()
    preferences = {"currency": {"currency": ["USD"]}}
    request = request.model_copy(update={"preferences": preferences})
    goal = goal.model_copy(update={"preferences": preferences})
    draft = build_prepare_draft(request, draft_id="DRAFT-A", goal=goal, scheme_snapshot=scheme, created_at=NOW)
    before = (request.model_dump_json(), draft.model_dump_json())
    view = derive_research_brief_v1(draft)
    assert "brief_id" not in type(view).model_fields
    view.preferences["currency"]["currency"].append("EUR")
    view.scheme_snapshot.assurance_requirements["test"] = ["detached"]
    assert (request.model_dump_json(), draft.model_dump_json()) == before
    assert draft_hash_is_valid(draft)


def _wp07_projection_with_tasks():
    projection = _projection()
    tasks = tuple(TaskProjectionV1(task_id=identity, run_id="RUN-A", task_type="research",
                                  goal="Source goal", assigned_agent="existing-agent", skill_id="existing-skill",
                                  origin="INITIAL", status="CREATED", progress=0, attempt_count=0, created_at=NOW)
                  for identity in ("TASK-B", "TASK-A"))
    return projection.model_copy(update={"planned_graph": projection.planned_graph.model_copy(update={"tasks": tasks})})


def test_wp07_task_contract_exact_admission_and_graph():
    admission, projection = _api_admission(), _wp07_projection_with_tasks()
    before = (admission.model_dump_json(), projection.model_dump_json())
    view = derive_research_task_contract_v1(admission, projection)
    assert view.model_dump(mode="json") == {
        "view_schema_version": "phase4-research-task-contract-view/v1",
        "admission": admission.model_dump(mode="json"), "projection_revision": 4,
        "projection_sequence": 7, "planned_graph_version": 1,
        "task_ids": ["TASK-B", "TASK-A"], "task_refs_status": "AVAILABLE",
        "node_binding_refs": None, "node_binding_refs_status": "NOT_EXPOSED_BY_SOURCE"}
    assert ResearchTaskContractViewV1.model_validate_json(view.model_dump_json()) == view
    assert view.model_dump_json() == derive_research_task_contract_v1(admission, projection).model_dump_json()
    assert (admission.model_dump_json(), projection.model_dump_json()) == before


@pytest.mark.parametrize("case", ["object", "run", "goal", "scheme", "graph", "graph_run", "run_graph",
                                  "task_run", "duplicate", "revision", "sequence", "unconfirmed"])
def test_wp07_task_contract_rejects_foreign_projection(case):
    admission, projection = _api_admission(), _wp07_projection_with_tasks()
    paths = {"object": ("object", "object_id", "OBJ-B"), "run": ("run", "run_id", "RUN-B"),
             "goal": ("goal", "goal_id", "GOAL-B"), "scheme": ("confirmed_scheme", "scheme_id", "SCHEME-B"),
             "graph": ("planned_graph", "graph_id", "GRAPH-B"), "graph_run": ("planned_graph", "run_id", "RUN-B"),
             "run_graph": ("run", "planned_graph_id", "GRAPH-B"),
             "unconfirmed": ("confirmed_scheme", "confirmed_at", None)}
    if case in paths:
        field, child, value = paths[case]
        projection = projection.model_copy(update={field: getattr(projection, field).model_copy(update={child: value})})
    elif case in ("revision", "sequence"):
        projection = projection.model_copy(update={"projection_" + case: 99})
    else:
        tasks = projection.planned_graph.tasks
        tasks = (tasks[0], tasks[0]) if case == "duplicate" else (tasks[0].model_copy(update={"run_id": "RUN-B"}),)
        projection = projection.model_copy(update={"planned_graph": projection.planned_graph.model_copy(update={"tasks": tasks})})
    before = (admission.model_dump_json(), projection.model_dump_json())
    with pytest.raises(ProjectionIntegrityError):
        derive_research_task_contract_v1(admission, projection)
    assert (admission.model_dump_json(), projection.model_dump_json()) == before


def test_wp07_task_contract_is_detached_read_only_view():
    admission = _api_admission()
    before = admission.model_dump_json()
    missing = derive_research_task_contract_v1(admission)
    empty = derive_research_task_contract_v1(admission, _projection())
    assert missing.task_ids is None and missing.task_refs_status == "NOT_PROVIDED"
    assert missing.projection_revision is missing.projection_sequence is missing.planned_graph_version is None
    assert empty.model_dump(mode="json")["task_ids"] == []
    assert empty.task_refs_status == "AVAILABLE"
    assert missing.node_binding_refs is empty.node_binding_refs is None
    assert missing.node_binding_refs_status == "NOT_EXPOSED_BY_SOURCE"
    assert missing.admission is not admission
    assert missing.admission.auto_start is not admission.auto_start
    assert not ({"contract_id", "store", "draft_hash"} & type(missing).model_fields.keys())
    assert admission.model_dump_json() == before


@pytest.mark.parametrize("preferences", [
    {}, {"currency": "USD"}, {"depth": "deep"}, {"include_peers": True}, {"include_peers": False},
    {"currency": ["USD", None, 7]}, {"depth": {"depth": ["deep", False]}},
])
def test_wp07_legacy_preferences_unchanged(preferences):
    request, goal, scheme = _prepare_values()
    raw = request.model_dump(mode="json")
    raw["preferences"] = preferences
    from src.phase4_product.contracts import PrepareResearchRunRequestV1
    request = PrepareResearchRunRequestV1.model_validate(raw)
    goal = project_goal(goal.model_copy(update={"preferences": preferences}), expected_object_id="OBJ-A")
    assert goal.preferences == preferences
    draft = build_prepare_draft(request, draft_id="DRAFT-A", goal=goal, scheme_snapshot=scheme, created_at=NOW)
    assert derive_research_brief_v1(draft).preferences == preferences
    raw.pop("preferences")
    assert PrepareResearchRunRequestV1.model_validate(raw).preferences == {}


@pytest.mark.parametrize("key", ["research_constraints", "requested_scope", "exclusions", "requested_outputs", "debug"])
def test_wp07_nested_namespace_remains_rejected(key):
    goal = _prepare_values()[1]
    with pytest.raises(ProjectionIntegrityError):
        project_goal(goal.model_copy(update={"preferences": {"currency": {key: []}}}), expected_object_id="OBJ-A")


def test_wp07_observation_and_views_do_not_invoke_authorities(monkeypatch):
    import src.phase4_product.admission as module
    draft, admission, projection = _draft(), _api_admission(), _wp07_projection_with_tasks()
    def forbidden(*args, **kwargs):
        pytest.fail("view invoked an authoritative operation")
    for name in ("build_prepare_draft", "build_run_admission", "validate_confirm_request", "mark_draft_consumed", "build_scheduler_admission"):
        monkeypatch.setattr(module, name, forbidden)
    for _ in range(2):
        assert derive_research_brief_v1(draft).draft_hash == draft.draft_hash
        assert derive_research_task_contract_v1(admission, projection).task_ids == ("TASK-B", "TASK-A")
