from __future__ import annotations

import json
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.domain.agent_output import (
    ResearchAgentOutputRecord,
    StandardResearchAgentStructuredOutput,
)
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.enums import ReviewStatus, RunStatus, TaskStatus
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.report import ReportArtifactRecord, ReportSourceContribution
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.review import ReviewCheck, ReviewRecord
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.domain.task import Task
from src.phase4_product.api import create_phase4_product_router, install_phase4_error_handlers
from src.phase4_product.contracts import (
    CrossViewEndpointV1,
    CrossViewRefV1,
    ReportAnchorRefV1,
    ReportContributionRefV1,
    ReportSectionRefV1,
    ResultsSurfaceRefV1,
    ReviewCheckSelectorV1,
)
from src.phase4_product.results import (
    ResultsIdentityError,
    ResultsIntegrityError,
    ResultsNotFoundError,
    build_execution_record_surface,
    build_financial_review_surface,
    build_report_surface,
    build_results_workspace,
    resolve_review_check_selector,
)

NOW = datetime(2026, 9, 6, 8, tzinfo=UTC)
RUN_ID = "RUN-A"
OBJECT_ID = "OBJ-A"
RESULT_ID = "RESULT-A"
CANONICAL_ID = "CER-A"
REVIEW_ID = "REVIEW-A"
ARTIFACT_ID = "RPT-HTML-A"


def run(run_id: str = RUN_ID) -> ResearchRun:
    return ResearchRun(
        run_id=run_id,
        research_object_id=OBJECT_ID,
        goal_id="GOAL-A",
        scheme_id="SCHEME-A",
        status=RunStatus.RELEASED,
        as_of=date(2026, 9, 6),
        planned_graph_id="GRAPH-P-A",
        actual_graph_id="GRAPH-A-A",
        started_at=NOW,
        completed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def research_object() -> ResearchObject:
    return ResearchObject(
        object_id=OBJECT_ID,
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
        created_at=NOW,
        updated_at=NOW,
    )


def task(run_id: str = RUN_ID) -> Task:
    return Task(
        task_id="TASK-A",
        run_id=run_id,
        task_type="fundamental_analysis",
        goal="Analyze fundamentals",
        assigned_agent="fundamental_analyst",
        skill_id="fundamental-analysis",
        status=TaskStatus.COMPLETED,
        progress=1,
        result_ref=f"agent-output://sha256/{'a' * 64}",
        created_at=NOW,
    )


def canonical(run_id: str = RUN_ID) -> CanonicalExecutionRecord:
    return CanonicalExecutionRecord(
        record_id=CANONICAL_ID,
        run_id=run_id,
        object_snapshot_ref=OBJECT_ID,
        goal_ref="GOAL-A",
        scheme_ref="SCHEME-A",
        planned_graph={"graph_id": "GRAPH-P-A"},
        actual_graph={"graph_id": "GRAPH-A-A"},
        task_refs=["TASK-A"],
        evidence_refs=["EVD-A"],
        calculation_refs=["CALC-A"],
        agent_output_refs=["AGOUT-A"],
        review_refs=[REVIEW_ID],
        runtime_outcome="RELEASED",
        created_at=NOW,
    )


def released(run_id: str = RUN_ID) -> ReleasedResearchResult:
    return ReleasedResearchResult(
        result_id=RESULT_ID,
        run_id=run_id,
        canonical_record_id=CANONICAL_ID,
        structured_financial_results={"investment_thesis": {"summary": "Released thesis"}},
        released_claims=[{"claim": "Revenue increased", "evidence_refs": ["EVD-A"]}],
        released_at=NOW,
    )


def review_check(
    *, code: str = "FIN_CALCULATION_IDENTITY", subject_refs: list[str] | None = None
) -> ReviewCheck:
    return ReviewCheck(
        code=code,
        status=ReviewStatus.PASS,
        subject_refs=subject_refs or ["CALC-A"],
        expected={"status": "PASS"},
        actual={"status": "PASS"},
        detail="Exact reviewed subject passed.",
        created_at=NOW,
    )


def review_record(*, run_id: str = RUN_ID, checks: list[ReviewCheck] | None = None) -> ReviewRecord:
    return ReviewRecord(
        review_id=REVIEW_ID,
        run_id=run_id,
        status=ReviewStatus.PASS,
        reviewer="independent-financial-review-v2",
        reviewed_evidence_refs=["EVD-A"],
        reviewed_calculation_refs=["CALC-A"],
        reviewed_claim_refs=["CLAIM-A"],
        input_snapshot_hash="sha256:" + "b" * 64,
        checks=checks or [review_check()],
        created_at=NOW,
    )


def agent_output(*, input_refs: list[str] | None = None, run_id: str = RUN_ID):
    return ResearchAgentOutputRecord(
        output_id="AGOUT-A",
        run_id=run_id,
        task_id="TASK-A",
        actor="fundamental_analyst",
        provider="test-provider",
        requested_model="test-model",
        actual_model="test-model",
        attempted_models=["test-model"],
        input_tokens=10,
        output_tokens=5,
        duration_ms=12,
        status="SUCCESS",
        input_refs=input_refs or ["GOAL-A", "EVD-A", "CALC-A"],
        structured_output=StandardResearchAgentStructuredOutput(
            summary="Fundamental analysis completed.",
            key_findings=["Revenue increased."],
            risks=["Demand may change."],
            limitations=["Point-in-time evidence."],
            requires_follow_up=False,
        ),
        artifact_id="sha256:" + "a" * 64,
        artifact_ref=f"agent-output://sha256/{'a' * 64}",
        artifact_sha256="sha256:" + "a" * 64,
        artifact_size_bytes=100,
        created_at=NOW,
    )


def event(run_id: str = RUN_ID) -> RuntimeEvent:
    return RuntimeEvent(
        event_id="EVT-A",
        run_id=run_id,
        task_id="TASK-A",
        type=RuntimeEventType.TASK_COMPLETED,
        timestamp=NOW,
        sequence=1,
        payload={"result_ref": f"agent-output://sha256/{'a' * 64}"},
    )


def source(run_id: str = RUN_ID) -> ReportSourceContribution:
    return ReportSourceContribution(
        run_id=run_id,
        report_id=RESULT_ID,
        report_anchor="metric-revenue-growth",
        execution_anchor="execution-AGOUT-A",
        report_section="Financial Analysis / Revenue Growth",
        actor_id="fundamental_analyst",
        task_id="TASK-A",
        agent_output_id="AGOUT-A",
        agent_output_artifact_id="sha256:" + "a" * 64,
        execution_event_id="EVT-A",
        provider="test-provider",
        actual_model="test-model",
        duration_ms=12,
        input_refs=("EVD-A", "CALC-A"),
        observable_process=("Strict structured output validation passed.",),
        output_summary="Revenue increased.",
        key_findings=("Revenue increased.",),
        calculation_id="CALC-A",
        evidence_refs=("EVD-A",),
        review_id=REVIEW_ID,
        review_status="PASS",
    )


def report_artifact(*, source_contributions=None, run_id: str = RUN_ID):
    return ReportArtifactRecord(
        artifact_id=ARTIFACT_ID,
        run_id=run_id,
        artifact_type="text/html",
        artifact_ref="artifact://reports/report.html",
        content_hash="sha256:" + "c" * 64,
        renderer_version="renderer-v1",
        canonical_record_id=CANONICAL_ID,
        released_result_id=RESULT_ID,
        size_bytes=100,
        anchor_manifest_id="MANIFEST-A",
        anchor_manifest_hash="sha256:" + "d" * 64,
        source_contributions=[source()] if source_contributions is None else source_contributions,
        created_at=NOW,
    )


def surfaces(*, output=None):
    output = output or agent_output()
    review = review_record()
    report = build_report_surface(
        expected_run_id=RUN_ID,
        expected_object_id=OBJECT_ID,
        run=run(),
        research_object=research_object(),
        canonical_record=canonical(),
        released_result=released(),
        report_artifact=report_artifact(),
        tasks=(task(),),
        agent_outputs=(output,),
        events=(event(),),
        review=review,
    )
    financial_review = build_financial_review_surface(
        expected_run_id=RUN_ID,
        expected_object_id=OBJECT_ID,
        review=review,
        canonical_record=canonical(),
        released_result=released(),
        authoritative_subject_refs=("CALC-A",),
    )
    execution = build_execution_record_surface(
        expected_run_id=RUN_ID,
        expected_object_id=OBJECT_ID,
        run=run(),
        canonical_record=canonical(),
        released_result=released(),
        review=review,
        tasks=(task(),),
        agent_outputs=(output,),
        events=(event(),),
        report_contributions=report.source_contributions,
    )
    return report, financial_review, execution


def test_one_exact_run_results_root_closes_three_explicit_surfaces() -> None:
    report, review, execution = surfaces()
    workspace = build_results_workspace(
        run=run(), report=report, review=review, execution=execution
    )

    assert workspace.run_id == RUN_ID
    assert workspace.object_id == OBJECT_ID
    assert workspace.released_result_id == RESULT_ID
    assert {
        workspace.report_surface.availability.status,
        workspace.review_surface.availability.status,
        workspace.execution_surface.availability.status,
    } <= {"READY", "PARTIAL", "UNAVAILABLE"}
    assert {item.run_id for item in workspace.cross_view_refs} == {RUN_ID}
    assert len(workspace.cross_view_refs) == 4


def test_report_anchor_and_contribution_are_representation_scoped_exact_refs() -> None:
    report, _, _ = surfaces()
    anchor = report.anchors[0]
    contribution = report.source_contributions[0]

    assert (anchor.run_id, anchor.report_id, anchor.artifact_id, anchor.anchor) == (
        RUN_ID,
        RESULT_ID,
        ARTIFACT_ID,
        "metric-revenue-growth",
    )
    assert (
        contribution.task_id,
        contribution.actor_id,
        contribution.agent_output_id,
        contribution.execution_event_id,
        contribution.calculation_id,
        contribution.evidence_refs,
        contribution.review_id,
    ) == ("TASK-A", "fundamental_analyst", "AGOUT-A", "EVT-A", "CALC-A", ("EVD-A",), REVIEW_ID)


def test_accepted_hero_trace_identity_is_frozen_without_a_lookup_fallback() -> None:
    accepted_run = "RUN-57aed683-75d6-4b47-acc6-a73053ea492e"
    hero = ReportContributionRefV1(
        run_id=accepted_run,
        report_id="RESULT-HERO",
        artifact_id="RPT-HTML-HERO",
        report_anchor="metric-revenue-growth",
        task_id="TASK-HERO",
        actor_id="fundamental_analyst",
        agent_output_id="AGOUT-9ab72a67-87e1-523a-a88f-1c4246a26330",
        execution_event_id="EVT-9dc4ef04-5617-4652-9510-61b9905274a0",
        calculation_id=f"CALC-{accepted_run}-GROWTH",
    )
    assert (
        hero.run_id,
        hero.report_anchor,
        hero.actor_id,
        hero.agent_output_id,
        hero.execution_event_id,
        hero.calculation_id,
    ) == (
        accepted_run,
        "metric-revenue-growth",
        "fundamental_analyst",
        "AGOUT-9ab72a67-87e1-523a-a88f-1c4246a26330",
        "EVT-9dc4ef04-5617-4652-9510-61b9905274a0",
        f"CALC-{accepted_run}-GROWTH",
    )


def test_selector_resolves_one_exact_persisted_check_and_canonicalizes_ref_order() -> None:
    check = review_check(subject_refs=["EVD-A", "CALC-A"])
    review = review_record(checks=[check])
    selector = ReviewCheckSelectorV1(
        review_id=REVIEW_ID,
        check_code=check.code,
        subject_refs=("EVD-A", "CALC-A"),
    )

    assert selector.subject_refs == ("CALC-A", "EVD-A")
    assert (
        resolve_review_check_selector(requested_run_id=RUN_ID, review=review, selector=selector)
        is check
    )


@pytest.mark.parametrize(
    ("requested_run_id", "selector", "error"),
    [
        (
            RUN_ID,
            ReviewCheckSelectorV1(
                review_id="REVIEW-X",
                check_code="FIN_CALCULATION_IDENTITY",
                subject_refs=("CALC-A",),
            ),
            ResultsNotFoundError,
        ),
        (
            "RUN-X",
            ReviewCheckSelectorV1(
                review_id=REVIEW_ID, check_code="FIN_CALCULATION_IDENTITY", subject_refs=("CALC-A",)
            ),
            ResultsIdentityError,
        ),
        (
            RUN_ID,
            ReviewCheckSelectorV1(
                review_id=REVIEW_ID, check_code="WRONG", subject_refs=("CALC-A",)
            ),
            ResultsNotFoundError,
        ),
        (
            RUN_ID,
            ReviewCheckSelectorV1(
                review_id=REVIEW_ID, check_code="FIN_CALCULATION_IDENTITY", subject_refs=("CALC-X",)
            ),
            ResultsNotFoundError,
        ),
    ],
)
def test_selector_fails_closed_for_wrong_review_run_code_or_subject(
    requested_run_id, selector, error
) -> None:
    with pytest.raises(error):
        resolve_review_check_selector(
            requested_run_id=requested_run_id,
            review=review_record(),
            selector=selector,
        )


def test_same_code_different_subject_resolves_without_list_order_identity() -> None:
    first = review_check(subject_refs=["CALC-A"])
    second = review_check(subject_refs=["EVD-A"])
    selector = ReviewCheckSelectorV1(
        review_id=REVIEW_ID,
        check_code=first.code,
        subject_refs=("EVD-A",),
    )
    for checks in ([first, second], [second, first]):
        assert resolve_review_check_selector(
            requested_run_id=RUN_ID,
            review=review_record(checks=checks),
            selector=selector,
        ).subject_refs == ["EVD-A"]


def test_duplicate_matching_selector_is_ambiguous_and_never_chooses_an_index() -> None:
    duplicate = review_check()
    review = review_record(checks=[duplicate, duplicate.model_copy()])
    selector = ReviewCheckSelectorV1(
        review_id=REVIEW_ID,
        check_code=duplicate.code,
        subject_refs=("CALC-A",),
    )
    with pytest.raises(ResultsIntegrityError, match="AMBIGUOUS_REVIEW_CHECK"):
        resolve_review_check_selector(requested_run_id=RUN_ID, review=review, selector=selector)


def test_display_text_is_not_selector_identity() -> None:
    check = review_check().model_copy(update={"detail": "Changed display explanation."})
    selector = ReviewCheckSelectorV1(
        review_id=REVIEW_ID,
        check_code=check.code,
        subject_refs=("CALC-A",),
    )
    assert (
        resolve_review_check_selector(
            requested_run_id=RUN_ID,
            review=review_record(checks=[check]),
            selector=selector,
        ).detail
        == "Changed display explanation."
    )


def test_selector_rejects_duplicate_subject_refs_and_public_review_has_no_check_id() -> None:
    with pytest.raises(ValidationError):
        ReviewCheckSelectorV1(
            review_id=REVIEW_ID,
            check_code="FIN_CALCULATION_IDENTITY",
            subject_refs=("CALC-A", "CALC-A"),
        )
    _, review, _ = surfaces()
    serialized = review.model_dump(mode="json")
    assert "check_id" not in json.dumps(serialized)
    assert set(serialized["checks"][0]["selector"]) == {"review_id", "check_code", "subject_refs"}


def test_cross_view_and_each_child_reject_cross_run_substitution() -> None:
    report, review, execution = surfaces()
    with pytest.raises(ValidationError, match="crossed Run"):
        CrossViewRefV1(
            run_id=RUN_ID,
            source=CrossViewEndpointV1(surface="A_REPORT", run_id=RUN_ID, identity_id=RESULT_ID),
            target=CrossViewEndpointV1(
                surface="C_EXECUTION_RECORD", run_id="RUN-X", identity_id=CANONICAL_ID
            ),
            status="AVAILABLE",
        )
    with pytest.raises(ResultsIdentityError):
        build_results_workspace(
            run=run(),
            report=report,
            review=review.model_copy(update={"run_id": "RUN-X"}),
            execution=execution,
        )
    with pytest.raises(ResultsIdentityError):
        build_report_surface(
            expected_run_id=RUN_ID,
            expected_object_id=OBJECT_ID,
            run=run(),
            research_object=research_object(),
            canonical_record=canonical(),
            released_result=released(),
            report_artifact=report_artifact(run_id="RUN-X", source_contributions=[]),
            tasks=(task(),),
            agent_outputs=(agent_output(),),
            events=(event(),),
            review=review_record(),
        )
    with pytest.raises(ResultsIdentityError):
        build_financial_review_surface(
            expected_run_id=RUN_ID,
            expected_object_id=OBJECT_ID,
            review=review_record(run_id="RUN-X"),
            canonical_record=canonical(),
            released_result=released(),
            authoritative_subject_refs=("CALC-A",),
        )
    with pytest.raises(ResultsIdentityError):
        build_execution_record_surface(
            expected_run_id=RUN_ID,
            expected_object_id=OBJECT_ID,
            run=run(),
            canonical_record=canonical(),
            released_result=released(),
            review=review_record(),
            tasks=(task(),),
            agent_outputs=(agent_output(run_id="RUN-X"),),
            events=(event(),),
            report_contributions=(),
        )


def test_missing_relation_is_empty_not_fabricated() -> None:
    _, review, _ = surfaces()
    check = review.checks[0]
    assert check.output_refs == ()
    assert all(item.status == "AVAILABLE" for item in check.input_refs)


def test_execution_actor_is_exact_and_unknown_input_ref_is_quarantined() -> None:
    dangling = "EVD-210857b6-862e-5225-9ae7-b876ed1f947c"
    valid = "EVD-210857b6-862e-522e-9ae7-b876ed1f947c"
    output = agent_output(input_refs=["GOAL-A", "EVD-A", valid, dangling])
    report, review, _ = surfaces(output=output)
    exact_canonical = canonical().model_copy(update={"evidence_refs": ["EVD-A", valid]})
    execution = build_execution_record_surface(
        expected_run_id=RUN_ID,
        expected_object_id=OBJECT_ID,
        run=run(),
        canonical_record=exact_canonical,
        released_result=released(),
        review=review_record(),
        tasks=(task(),),
        agent_outputs=(output,),
        events=(event(),),
        report_contributions=report.source_contributions,
    )
    actor = next(item for item in execution.actors if item.actor_id == "fundamental_analyst")
    detail = next(item for item in execution.actor_details if item.actor_id == actor.actor_id)
    assert actor.actor_type == "SPECIALIST"
    assert valid in {item.ref_id for item in detail.input_refs}
    assert dangling not in {item.ref_id for item in detail.input_refs}
    assert detail.quarantined_input_ref_count == 1


def test_partial_release_keeps_failed_execution_without_claiming_a_contribution() -> None:
    failed = agent_output().model_copy(
        update={"status": "FAILED", "structured_output": None, "failure_code": "TIMEOUT"}
    )
    failed_task = task().model_copy(update={"status": TaskStatus.FAILED, "result_ref": None})
    failed_event = event().model_copy(
        update={
            "type": RuntimeEventType.TASK_FAILED,
            "payload": {"failure_code": "TASK_EXECUTION_FAILED"},
        }
    )
    args = dict(
        expected_run_id=RUN_ID,
        expected_object_id=OBJECT_ID,
        run=run(),
        canonical_record=canonical().model_copy(update={"agent_output_refs": []}),
        released_result=released(),
        review=review_record(),
        tasks=(failed_task,),
        agent_outputs=(failed,),
        events=(failed_event,),
        report_contributions=(),
    )
    surface = build_execution_record_surface(**args)
    assert surface.actors[0].status == "FAILED"
    assert surface.actor_details[0].outputs[0].status == "FAILED"
    assert surface.actor_details[0].observable_process[0].status == "FAILED"
    assert not surface.actor_details[0].report_contributions
    for changes in (
        {"canonical_record": canonical()},
        {"events": (event(),)},
        {"tasks": (task(),)},
        {"agent_outputs": (failed.model_copy(update={"run_id": "RUN-FOREIGN"}),)},
    ):
        with pytest.raises((ResultsIdentityError, ResultsIntegrityError)):
            build_execution_record_surface(**(args | changes))


def test_execution_quarantines_internal_path_even_if_retained_as_a_known_ref() -> None:
    internal_path = "/Users/private/agent-scratch.json"
    output = agent_output(input_refs=["GOAL-A", internal_path])
    report, _, _ = surfaces(output=output)
    exact_canonical = canonical().model_copy(update={"evidence_refs": ["EVD-A", internal_path]})
    execution = build_execution_record_surface(
        expected_run_id=RUN_ID,
        expected_object_id=OBJECT_ID,
        run=run(),
        canonical_record=exact_canonical,
        released_result=released(),
        review=review_record(),
        tasks=(task(),),
        agent_outputs=(output,),
        events=(event(),),
        report_contributions=report.source_contributions,
    )
    detail = execution.actor_details[0]
    assert internal_path not in {item.ref_id for item in detail.input_refs}
    assert detail.quarantined_input_ref_count == 1


def test_execution_output_requires_one_exact_matching_completion_event() -> None:
    report, _, _ = surfaces()
    wrong_result = event().model_copy(update={"payload": {"result_ref": "artifact://wrong"}})
    with pytest.raises(ResultsIntegrityError, match="exactly one matching"):
        build_execution_record_surface(
            expected_run_id=RUN_ID,
            expected_object_id=OBJECT_ID,
            run=run(),
            canonical_record=canonical(),
            released_result=released(),
            review=review_record(),
            tasks=(task(),),
            agent_outputs=(agent_output(),),
            events=(wrong_result,),
            report_contributions=report.source_contributions,
        )
    with pytest.raises(ResultsIntegrityError, match="exactly one matching"):
        build_execution_record_surface(
            expected_run_id=RUN_ID,
            expected_object_id=OBJECT_ID,
            run=run(),
            canonical_record=canonical(),
            released_result=released(),
            review=review_record(),
            tasks=(task(),),
            agent_outputs=(agent_output(),),
            events=(event(), event().model_copy(update={"event_id": "EVT-B", "sequence": 2})),
            report_contributions=report.source_contributions,
        )


def test_nested_report_anchor_and_surface_href_fail_closed() -> None:
    report, _, _ = surfaces()
    foreign_anchor = ReportAnchorRefV1(
        run_id="RUN-X",
        report_id=RESULT_ID,
        artifact_id=ARTIFACT_ID,
        anchor="metric-revenue-growth",
    )
    with pytest.raises(ValidationError, match="Report section crossed"):
        report.model_copy(
            update={
                "sections": (
                    ReportSectionRefV1(
                        section_key="metric-revenue-growth",
                        title="Revenue Growth",
                        anchor=foreign_anchor,
                    ),
                )
            }
        ).model_validate(
            report.model_copy(
                update={
                    "sections": (
                        ReportSectionRefV1(
                            section_key="metric-revenue-growth",
                            title="Revenue Growth",
                            anchor=foreign_anchor,
                        ),
                    )
                }
            ).model_dump()
        )
    with pytest.raises(ValidationError, match="exact Run/surface"):
        ResultsSurfaceRefV1(
            surface="A_REPORT",
            run_id=RUN_ID,
            object_id=OBJECT_ID,
            released_result_id=RESULT_ID,
            canonical_execution_record_id=CANONICAL_ID,
            surface_id=RESULT_ID,
            href="/api/research-runs/RUN-X/report-view",
            availability=report.availability,
        )


def test_public_contract_has_no_prompt_raw_provider_or_hidden_reasoning_fields() -> None:
    report, review, execution = surfaces()
    workspace = build_results_workspace(
        run=run(), report=report, review=review, execution=execution
    )
    public = json.dumps(
        {
            "workspace": workspace.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
            "review": review.model_dump(mode="json"),
            "execution": execution.model_dump(mode="json"),
        }
    ).lower()
    for forbidden in (
        "chain_of_thought",
        "hidden_reasoning",
        "scratchpad",
        '"prompt"',
        "raw_provider",
        "authorization",
        "artifact://",
        "/users/",
    ):
        assert forbidden not in public


class _ResultsRouteBackend:
    def __init__(self, response_run_id: str = RUN_ID) -> None:
        report, review, execution = surfaces()
        workspace = build_results_workspace(
            run=run(), report=report, review=review, execution=execution
        )
        self.workspace = workspace.model_copy(update={"run_id": response_run_id})
        self.report = report.model_copy(update={"run_id": response_run_id})
        self.review = review.model_copy(update={"run_id": response_run_id})
        self.execution = execution.model_copy(update={"run_id": response_run_id})

    async def get_results(self, _run_id):
        return self.workspace

    async def get_report(self, _run_id):
        return self.report

    async def get_review(self, _run_id):
        return self.review

    async def get_execution(self, _run_id, **_kwargs):
        return self.execution


def _results_client(response_run_id: str = RUN_ID) -> TestClient:
    app = FastAPI()
    app.state.phase4_product_backend = _ResultsRouteBackend(response_run_id)
    install_phase4_error_handlers(app)
    app.include_router(create_phase4_product_router())
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "suffix",
    ("results", "report-view", "review-view", "execution-view"),
)
def test_exact_run_results_api_routes_dispatch_typed_contracts(suffix: str) -> None:
    response = _results_client().get(f"/api/research-runs/{RUN_ID}/{suffix}")
    assert response.status_code == 200, response.text
    assert response.json()["run_id"] == RUN_ID


@pytest.mark.parametrize(
    "suffix",
    ("results", "report-view", "review-view", "execution-view"),
)
def test_results_api_routes_reject_self_consistent_foreign_run_responses(suffix: str) -> None:
    response = _results_client("RUN-X").get(f"/api/research-runs/{RUN_ID}/{suffix}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "IDENTITY_MISMATCH"


def test_frontend_results_decoders_accept_exact_contract_and_fail_closed() -> None:
    report, review, execution = surfaces()
    workspace = build_results_workspace(
        run=run(), report=report, review=review, execution=execution
    )
    payloads = json.dumps(
        {
            "workspace": workspace.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
            "review": review.model_dump(mode="json"),
            "execution": execution.model_dump(mode="json"),
        }
    )
    module_url = (Path.cwd() / "apps/web/src/types/domain.ts").as_uri()
    script = f"""
      import assert from "node:assert/strict";
      import {{ readFile }} from "node:fs/promises";
      import {{ stripTypeScriptTypes }} from "node:module";
      const source = await readFile(new URL({json.dumps(module_url)}), "utf8");
      const javascript = stripTypeScriptTypes(source, {{ mode: "transform" }});
      const dataUrl = `data:text/javascript;base64,${{Buffer.from(javascript).toString("base64")}}`;
      const domain = await import(dataUrl);
      const payloads = JSON.parse({json.dumps(payloads)});
      try {{
      const workspace = domain.decodeResultsWorkspace(payloads.workspace, "RUN-A", "OBJ-A");
      const report = domain.decodeReportSurface(payloads.report, "RUN-A", "OBJ-A");
      const review = domain.decodeFinancialReviewSurface(payloads.review, "RUN-A", "OBJ-A");
      const execution = domain.decodeExecutionRecordSurface(payloads.execution, "RUN-A", "OBJ-A");
      assert.equal(workspace.runId, "RUN-A");
      assert.equal(report.sourceContributions[0].calculationId, "CALC-A");
      assert.equal(review.checks.length, 1);
      assert.equal(execution.actorDetails.length, 1);

      const retainedReview = structuredClone(payloads.review);
      retainedReview.released_result_id = null;
      assert.throws(() => domain.decodeFinancialReviewSurface(retainedReview, "RUN-A", "OBJ-A"));
      retainedReview.canonical_execution_record_id = null;
      const retained = domain.decodeFinancialReviewSurface(retainedReview, "RUN-A", "OBJ-A");
      assert.equal(retained.releasedResultId, null);

      const foreignReport = structuredClone(payloads.report);
      foreignReport.sections[0].anchor.run_id = "RUN-X";
      assert.throws(() => domain.decodeReportSurface(foreignReport, "RUN-A", "OBJ-A"));

      const foreignWorkspace = structuredClone(payloads.workspace);
      foreignWorkspace.execution_surface.href = "/api/research-runs/RUN-X/execution-view";
      assert.throws(() => domain.decodeResultsWorkspace(foreignWorkspace, "RUN-A", "OBJ-A"));

      const unsafeExecution = structuredClone(payloads.execution);
      unsafeExecution.actor_details[0].prompt = "private prompt";
      assert.throws(() => domain.decodeExecutionRecordSurface(unsafeExecution, "RUN-A", "OBJ-A"));
      }} catch (error) {{
        console.error(error instanceof Error ? error.message : String(error));
        process.exit(1);
      }}
    """
    completed = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "--eval", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
