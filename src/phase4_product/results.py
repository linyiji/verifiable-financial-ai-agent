"""Phase 4.5 exact-Run Results Workspace projection builders.

The builders close already-persisted Report, Review, AgentOutput, and RuntimeEvent
records.  They never perform latest/ticker lookup and never synthesize a durable
ReviewCheck identity.  A ReviewCheck selector is valid only inside one exact
ReviewRecord.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from src.domain.agent_output import ResearchAgentOutputRecord
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.report import ReportArtifactRecord, ReportSourceContribution
from src.domain.research_object import ResearchObject
from src.domain.research_run import ResearchRun
from src.domain.review import ReviewCheck, ReviewRecord
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.domain.task import Task
from src.phase4_product.contracts import (
    CrossViewEndpointV1,
    CrossViewRefV1,
    ExecutionActorDetailV1,
    ExecutionActorSummaryV1,
    ExecutionInputRefV1,
    ExecutionObservableRecordV1,
    ExecutionOutputRecordV1,
    ExecutionRecordSurfaceV1,
    FinancialReviewCheckV1,
    FinancialReviewSurfaceV1,
    ReportAnchorRefV1,
    ReportContributionRefV1,
    ReportSectionRefV1,
    ReportSurfaceV1,
    ResultsRelationRefV1,
    ResultsSurfaceAvailabilityV1,
    ResultsSurfaceRefV1,
    ResultsWorkspaceV1,
    ReviewCheckSelectorV1,
)
from src.phase4_product.safety import UnsafeProjectionData, safe_text


class ResultsIdentityError(ValueError):
    """An input record does not belong to the requested exact Run."""


class ResultsNotFoundError(LookupError):
    """An exact scoped selector has no match."""


class ResultsIntegrityError(ValueError):
    """Persisted records cannot produce one unambiguous public projection."""


_ACTOR_LABELS = {
    "research_lead": "Research Lead",
    "fundamental_analyst": "Fundamental Analyst",
    "peer_analyst": "Peer Analyst",
    "research_news_analyst": "Research & News Analyst",
    "valuation_analyst": "Valuation Analyst",
    "risk_analyst": "Risk Analyst",
}

_SUPPORTING_EVENTS: tuple[tuple[str, str, frozenset[RuntimeEventType]], ...] = (
    (
        "fmp_data",
        "FMP / Data",
        frozenset({RuntimeEventType.EVIDENCE_ACCEPTED}),
    ),
    (
        "evidence_pipeline",
        "Evidence Pipeline",
        frozenset(
            {
                RuntimeEventType.EVIDENCE_CONFLICT,
                RuntimeEventType.TASK_SELF_CORRECTING,
                RuntimeEventType.TASK_CORRECTION_RESOLVED,
            }
        ),
    ),
    (
        "financial_code_runtime",
        "Financial Code Runtime",
        frozenset(
            event_type
            for event_type in RuntimeEventType
            if event_type.value.startswith("calculation.")
            or event_type.value.startswith("capability.")
        ),
    ),
    (
        "review",
        "Review",
        frozenset(
            {
                RuntimeEventType.REVIEW_STARTED,
                RuntimeEventType.REVIEW_REQUIRED,
                RuntimeEventType.REVIEW_RESOLVED,
            }
        ),
    ),
    (
        "proof",
        "Proof",
        frozenset(
            event_type for event_type in RuntimeEventType if event_type.value.startswith("proof.")
        ),
    ),
    (
        "release",
        "Release",
        frozenset({RuntimeEventType.RELEASE_COMPLETED, RuntimeEventType.RUN_COMPLETED}),
    ),
)


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _safe(value: str | None, *, context: str) -> str | None:
    if value is None:
        return None
    try:
        return safe_text(value, context=context, max_length=800)
    except UnsafeProjectionData as exc:
        raise ResultsIntegrityError(str(exc)) from exc


def _is_safe_ref(value: str) -> bool:
    if value.strip() != value:
        return False
    try:
        safe_text(value, context="public reference", max_length=1024)
    except UnsafeProjectionData:
        return False
    return True


def _exact_run(value: object, expected_run_id: str, context: str) -> None:
    if getattr(value, "run_id", None) != expected_run_id:
        raise ResultsIdentityError(f"{context} belongs to another Run")


def _check_selector(review_id: str, check: ReviewCheck) -> ReviewCheckSelectorV1:
    return ReviewCheckSelectorV1(
        review_id=review_id,
        check_code=check.code,
        subject_refs=tuple(check.subject_refs),
    )


def resolve_review_check_selector(
    *,
    requested_run_id: str,
    review: ReviewRecord,
    selector: ReviewCheckSelectorV1,
) -> ReviewCheck:
    """Resolve one scoped selector without inventing a Check entity identity."""

    _exact_run(review, requested_run_id, "ReviewRecord")
    if selector.review_id != review.review_id:
        raise ResultsNotFoundError("ReviewCheck selector names another ReviewRecord")
    matches = [
        check
        for check in review.checks
        if check.code == selector.check_code
        and tuple(sorted(check.subject_refs)) == selector.subject_refs
    ]
    if not matches:
        raise ResultsNotFoundError("ReviewCheck selector did not match this ReviewRecord")
    if len(matches) > 1:
        raise ResultsIntegrityError("AMBIGUOUS_REVIEW_CHECK")
    return matches[0]


def _contribution_ref(
    source: ReportSourceContribution,
    *,
    artifact_id: str,
) -> ReportContributionRefV1:
    return ReportContributionRefV1(
        run_id=source.run_id,
        report_id=source.report_id,
        artifact_id=artifact_id,
        report_anchor=source.report_anchor,
        task_id=source.task_id,
        actor_id=source.actor_id,
        agent_output_id=source.agent_output_id,
        execution_event_id=source.execution_event_id,
        calculation_id=source.calculation_id,
        evidence_refs=source.evidence_refs,
        review_id=source.review_id,
    )


def build_report_surface(
    *,
    expected_run_id: str,
    expected_object_id: str,
    run: ResearchRun,
    research_object: ResearchObject,
    canonical_record: CanonicalExecutionRecord,
    released_result: ReleasedResearchResult,
    report_artifact: ReportArtifactRecord,
    tasks: Sequence[Task],
    agent_outputs: Sequence[ResearchAgentOutputRecord],
    events: Sequence[RuntimeEvent],
    review: ReviewRecord | None,
) -> ReportSurfaceV1:
    for value, context in (
        (run, "Run"),
        (canonical_record, "CanonicalExecutionRecord"),
        (released_result, "ReleasedResult"),
        (report_artifact, "ReportArtifact"),
    ):
        _exact_run(value, expected_run_id, context)
    if review is not None:
        _exact_run(review, expected_run_id, "ReviewRecord")
    if (
        run.research_object_id != expected_object_id
        or research_object.object_id != expected_object_id
        or canonical_record.object_snapshot_ref != expected_object_id
        or released_result.canonical_record_id != canonical_record.record_id
        or report_artifact.canonical_record_id != canonical_record.record_id
        or report_artifact.released_result_id != released_result.result_id
        or report_artifact.artifact_type != "text/html"
        or report_artifact.anchor_manifest_id is None
    ):
        raise ResultsIdentityError("Report closure does not match exact Run/Object/Result")
    task_index = {item.task_id: item for item in tasks}
    output_index = {item.output_id: item for item in agent_outputs}
    event_index = {item.event_id: item for item in events}
    if (
        len(task_index) != len(tasks)
        or len(output_index) != len(agent_outputs)
        or len(event_index) != len(events)
    ):
        raise ResultsIntegrityError("Report source identities are ambiguous")
    contributions: list[ReportContributionRefV1] = []
    anchors: list[ReportAnchorRefV1] = []
    sections: list[ReportSectionRefV1] = []
    for source in report_artifact.source_contributions:
        _exact_run(source, expected_run_id, "ReportSourceContribution")
        task = task_index.get(source.task_id)
        output = output_index.get(source.agent_output_id)
        event = event_index.get(source.execution_event_id)
        deterministic = source.agent_output_id is None
        if deterministic and (
            source.calculation_id not in canonical_record.calculation_refs
            or event is None
            or event.type is not RuntimeEventType.CALCULATION_COMPLETED
            or event.payload.get("calculation_id") != source.calculation_id
        ):
            raise ResultsIdentityError("Deterministic contribution lacks exact calculation event")
        if (
            not all(
                _is_safe_ref(item)
                for item in (
                    source.report_id,
                    source.report_anchor,
                    source.task_id,
                    source.actor_id,
                    *([source.agent_output_id] if source.agent_output_id else []),
                    source.execution_event_id,
                    *source.evidence_refs,
                    *(item for item in (source.calculation_id, source.review_id) if item),
                )
            )
            or source.report_id != released_result.result_id
            or source.task_id not in canonical_record.task_refs
            or (
                not deterministic
                and source.agent_output_id not in canonical_record.agent_output_refs
            )
            or task is None
            or task.run_id != expected_run_id
            or task.assigned_agent != source.actor_id
            or (
                not deterministic
                and (
                    output is None
                    or task.result_ref != output.artifact_ref
                    or output.run_id != expected_run_id
                    or output.task_id != source.task_id
                    or output.actor != source.actor_id
                    or output.artifact_id != source.agent_output_artifact_id
                )
            )
            or event is None
            or event.run_id != expected_run_id
            or event.task_id != source.task_id
            or (
                not deterministic
                and (
                    event.type is not RuntimeEventType.TASK_COMPLETED
                    or event.payload.get("result_ref") != output.artifact_ref
                )
            )
            or (
                source.calculation_id is not None
                and source.calculation_id not in canonical_record.calculation_refs
            )
            or any(item not in canonical_record.evidence_refs for item in source.evidence_refs)
            or (
                source.review_id is not None
                and (
                    review is None
                    or source.review_id != review.review_id
                    or source.review_id not in canonical_record.review_refs
                )
            )
        ):
            raise ResultsIdentityError("Report contribution lacks exact retained source closure")
        anchor = ReportAnchorRefV1(
            run_id=expected_run_id,
            report_id=released_result.result_id,
            artifact_id=report_artifact.artifact_id,
            anchor=source.report_anchor,
        )
        anchors.append(anchor)
        sections.append(
            ReportSectionRefV1(
                section_key=source.report_anchor,
                title=_safe(source.report_section, context="Report section") or "",
                anchor=anchor,
            )
        )
        contributions.append(_contribution_ref(source, artifact_id=report_artifact.artifact_id))
    successful_output_ids = {item.output_id for item in agent_outputs if item.status == "SUCCESS"}
    contributed_output_ids = {item.agent_output_id for item in contributions}
    complete = bool(successful_output_ids) and contributed_output_ids == successful_output_ids
    availability = ResultsSurfaceAvailabilityV1(
        status="READY" if complete else "PARTIAL",
        reason_code=None if complete else "REPORT_SOURCE_MAP_PARTIAL",
    )
    return ReportSurfaceV1(
        run_id=expected_run_id,
        object_id=expected_object_id,
        released_result_id=released_result.result_id,
        canonical_execution_record_id=canonical_record.record_id,
        report_id=released_result.result_id,
        artifact_id=report_artifact.artifact_id,
        title=_safe(f"{research_object.company_name} Research Report", context="Report title")
        or "",
        company_name=_safe(research_object.company_name, context="Company name") or "",
        symbol=research_object.symbol,
        as_of=run.as_of,
        sections=tuple(sections),
        anchors=tuple(anchors),
        source_contributions=tuple(contributions),
        availability=availability,
    )


def build_financial_review_surface(
    *,
    expected_run_id: str,
    expected_object_id: str,
    review: ReviewRecord,
    canonical_record: CanonicalExecutionRecord | None,
    released_result: ReleasedResearchResult | None,
    authoritative_subject_refs: Iterable[str],
) -> FinancialReviewSurfaceV1:
    for value, context in (
        (review, "ReviewRecord"),
        (canonical_record, "CanonicalExecutionRecord"),
        (released_result, "ReleasedResult"),
    ):
        if value is not None:
            _exact_run(value, expected_run_id, context)
    if (canonical_record is None) != (released_result is None):
        raise ResultsIdentityError("Review release bindings are incomplete")
    if (
        canonical_record is not None
        and released_result is not None
        and (
            canonical_record.object_snapshot_ref != expected_object_id
            or released_result.canonical_record_id != canonical_record.record_id
            or review.review_id not in canonical_record.review_refs
        )
    ):
        raise ResultsIdentityError(
            "Financial Review closure does not match exact Run/Object/Result"
        )
    known_refs = set(authoritative_subject_refs)
    checks: list[FinancialReviewCheckV1] = []
    for check in review.checks:
        selector = _check_selector(review.review_id, check)
        if any(
            subject not in known_refs or not _is_safe_ref(subject)
            for subject in selector.subject_refs
        ):
            raise ResultsIdentityError("ReviewCheck subject is not an exact retained same-Run ref")
        checks.append(
            FinancialReviewCheckV1(
                selector=selector,
                status=_enum_value(check.status),
                safe_explanation=_safe(check.detail, context="ReviewCheck explanation"),
                input_refs=tuple(
                    ResultsRelationRefV1(
                        run_id=expected_run_id,
                        relation_type="REVIEW_SUBJECT",
                        status="AVAILABLE",
                        target_ref=subject,
                    )
                    for subject in selector.subject_refs
                ),
                output_refs=(),
            )
        )
    return FinancialReviewSurfaceV1(
        run_id=expected_run_id,
        object_id=expected_object_id,
        released_result_id=released_result.result_id if released_result else None,
        canonical_execution_record_id=canonical_record.record_id if canonical_record else None,
        review_id=review.review_id,
        reviewer=_safe(review.reviewer, context="Review reviewer") or "",
        verdict=_enum_value(review.status),
        checks=tuple(checks),
        availability=ResultsSurfaceAvailabilityV1(status="READY", reason_code=None),
    )


def _known_execution_refs(
    *,
    run: ResearchRun,
    canonical_record: CanonicalExecutionRecord,
    released_result: ReleasedResearchResult,
    tasks: Sequence[Task],
    agent_outputs: Sequence[ResearchAgentOutputRecord],
    review: ReviewRecord,
) -> set[str]:
    refs = {
        run.run_id,
        run.research_object_id,
        run.goal_id,
        run.scheme_id,
        canonical_record.record_id,
        released_result.result_id,
        review.review_id,
        *(item.task_id for item in tasks),
        *(item.output_id for item in agent_outputs),
        *canonical_record.evidence_refs,
        *canonical_record.calculation_refs,
        *canonical_record.decision_refs,
        *canonical_record.generated_capability_refs,
        *canonical_record.review_refs,
        *canonical_record.proof_refs,
        *canonical_record.trace_refs,
    }
    return {item for item in refs if item}


def build_execution_record_surface(
    *,
    expected_run_id: str,
    expected_object_id: str,
    run: ResearchRun,
    canonical_record: CanonicalExecutionRecord,
    released_result: ReleasedResearchResult,
    review: ReviewRecord,
    tasks: Sequence[Task],
    agent_outputs: Sequence[ResearchAgentOutputRecord],
    events: Sequence[RuntimeEvent],
    report_contributions: Sequence[ReportContributionRefV1],
) -> ExecutionRecordSurfaceV1:
    for value, context in (
        (run, "Run"),
        (canonical_record, "CanonicalExecutionRecord"),
        (released_result, "ReleasedResult"),
        (review, "ReviewRecord"),
    ):
        _exact_run(value, expected_run_id, context)
    if (
        run.research_object_id != expected_object_id
        or canonical_record.object_snapshot_ref != expected_object_id
        or released_result.canonical_record_id != canonical_record.record_id
    ):
        raise ResultsIdentityError("Execution closure does not match exact Run/Object/Result")
    if any(item.run_id != expected_run_id for item in (*tasks, *agent_outputs, *events)):
        raise ResultsIdentityError("Execution child record crossed Run identity")
    task_ids = {item.task_id for item in tasks}
    if len(task_ids) != len(tasks):
        raise ResultsIntegrityError("Execution task identities are ambiguous")
    output_ids = {item.output_id for item in agent_outputs}
    event_ids = {item.event_id for item in events}
    if len(output_ids) != len(agent_outputs) or len(event_ids) != len(events):
        raise ResultsIntegrityError("Execution output/event identities are ambiguous")
    if set(canonical_record.task_refs) != task_ids or set(canonical_record.agent_output_refs) != {
        item.output_id for item in agent_outputs if item.status == "SUCCESS"
    }:
        raise ResultsIdentityError(
            "Execution Task/AgentOutput refs differ from the canonical record"
        )
    known_refs = _known_execution_refs(
        run=run,
        canonical_record=canonical_record,
        released_result=released_result,
        tasks=tasks,
        agent_outputs=agent_outputs,
        review=review,
    )
    safe_known_refs = {item for item in known_refs if _is_safe_ref(item)}
    outputs_by_actor: dict[str, list[ResearchAgentOutputRecord]] = defaultdict(list)
    for output in agent_outputs:
        if output.task_id not in task_ids:
            raise ResultsIdentityError("AgentOutput references no exact same-Run Task")
        outputs_by_actor[output.actor].append(output)
    actors: list[ExecutionActorSummaryV1] = []
    details: list[ExecutionActorDetailV1] = []
    for actor_id, actor_outputs in sorted(
        outputs_by_actor.items(), key=lambda item: (item[0] != "research_lead", item[0])
    ):
        actor_type = "RESEARCH_LEAD" if actor_id == "research_lead" else "SPECIALIST"
        owned_task_ids = {item.task_id for item in actor_outputs}
        owned_events = [item for item in events if item.task_id in owned_task_ids]
        actors.append(
            ExecutionActorSummaryV1(
                run_id=expected_run_id,
                actor_id=actor_id,
                actor_type=actor_type,
                display_role=_safe(
                    _ACTOR_LABELS.get(actor_id, actor_id), context="Execution actor role"
                )
                or "",
                status=(
                    "SUCCESS"
                    if all(item.status == "SUCCESS" for item in actor_outputs)
                    else "FAILED"
                ),
                event_count=len(owned_events),
                record_count=len(actor_outputs),
            )
        )
        exact_inputs = sorted(
            {ref for output in actor_outputs for ref in output.input_refs if ref in safe_known_refs}
        )
        quarantined = sum(
            ref not in safe_known_refs for output in actor_outputs for ref in output.input_refs
        )
        completed_events: list[RuntimeEvent] = []
        for output in actor_outputs:
            success = output.status == "SUCCESS"
            terminal_type = (
                RuntimeEventType.TASK_COMPLETED if success else RuntimeEventType.TASK_FAILED
            )
            matches = [
                item
                for item in owned_events
                if item.type is terminal_type
                and item.task_id == output.task_id
                and (not success or item.payload.get("result_ref") == output.artifact_ref)
            ]
            failed_binding_ambiguous = not success and (
                sum(item.task_id == output.task_id for item in agent_outputs) != 1
                or next(item for item in tasks if item.task_id == output.task_id).status.value
                != "FAILED"
            )
            if len(matches) != 1 or failed_binding_ambiguous:
                raise ResultsIntegrityError(
                    "AgentOutput requires exactly one matching terminal Task event"
                )
            completed_events.append(matches[0])
        for contribution in report_contributions:
            if contribution.actor_id != actor_id or contribution.agent_output_id is not None:
                continue
            matches = [
                item
                for item in owned_events
                if item.type is RuntimeEventType.CALCULATION_COMPLETED
                and item.event_id == contribution.execution_event_id
                and item.task_id == contribution.task_id
                and item.payload.get("calculation_id") == contribution.calculation_id
            ]
            if len(matches) != 1:
                raise ResultsIntegrityError("Native contribution lacks exact calculation event")
            completed_events.append(matches[0])
        details.append(
            ExecutionActorDetailV1(
                run_id=expected_run_id,
                actor_id=actor_id,
                actor_type=actor_type,
                input_refs=tuple(
                    ExecutionInputRefV1(run_id=expected_run_id, ref_id=item)
                    for item in exact_inputs
                ),
                observable_process=tuple(
                    ExecutionObservableRecordV1(
                        run_id=expected_run_id,
                        event_id=event.event_id,
                        task_id=event.task_id,
                        event_type=event.type.value,
                        status="FAILED"
                        if event.type is RuntimeEventType.TASK_FAILED
                        else "COMPLETED",
                    )
                    for event in sorted(completed_events, key=lambda item: item.sequence)
                ),
                outputs=tuple(
                    ExecutionOutputRecordV1(
                        run_id=expected_run_id,
                        output_id=output.output_id,
                        task_id=output.task_id,
                        status=output.status,
                        summary=_safe(
                            output.structured_output.summary if output.structured_output else None,
                            context="Agent output summary",
                        ),
                        key_findings=tuple(
                            _safe(item, context="Agent output finding") or ""
                            for item in (
                                output.structured_output.key_findings
                                if output.structured_output
                                else ()
                            )
                        ),
                        risks=tuple(
                            _safe(item, context="Agent output risk") or ""
                            for item in (
                                output.structured_output.risks if output.structured_output else ()
                            )
                        ),
                        limitations=tuple(
                            _safe(item, context="Agent output limitation") or ""
                            for item in (
                                output.structured_output.limitations
                                if output.structured_output
                                else ()
                            )
                        ),
                    )
                    for output in actor_outputs
                ),
                report_contributions=tuple(
                    item for item in report_contributions if item.actor_id == actor_id
                ),
                quarantined_input_ref_count=quarantined,
            )
        )
    for actor_id, label, event_types in _SUPPORTING_EVENTS:
        supporting_events = [item for item in events if item.type in event_types]
        if not supporting_events:
            continue
        actors.append(
            ExecutionActorSummaryV1(
                run_id=expected_run_id,
                actor_id=actor_id,
                actor_type="SUPPORTING_EXECUTION",
                display_role=label,
                status="COMPLETED",
                event_count=len(supporting_events),
                record_count=len(supporting_events),
            )
        )
    complete_contributions = {item.actor_id for item in report_contributions} == set(
        outputs_by_actor
    )
    return ExecutionRecordSurfaceV1(
        run_id=expected_run_id,
        object_id=expected_object_id,
        released_result_id=released_result.result_id,
        canonical_execution_record_id=canonical_record.record_id,
        actors=tuple(actors),
        actor_details=tuple(details),
        availability=ResultsSurfaceAvailabilityV1(
            status="READY" if complete_contributions else "PARTIAL",
            reason_code=None if complete_contributions else "REPORT_CONTRIBUTIONS_PARTIAL",
        ),
    )


def build_results_workspace(
    *,
    run: ResearchRun,
    report: ReportSurfaceV1,
    review: FinancialReviewSurfaceV1,
    execution: ExecutionRecordSurfaceV1,
) -> ResultsWorkspaceV1:
    run_id = run.run_id
    object_id = run.research_object_id
    result_id = report.released_result_id
    canonical_id = report.canonical_execution_record_id
    for surface in (review, execution):
        if (
            surface.run_id != run_id
            or surface.object_id != object_id
            or surface.released_result_id != result_id
            or surface.canonical_execution_record_id != canonical_id
        ):
            raise ResultsIdentityError("Results child surface crossed workspace identity")
    report_endpoint = CrossViewEndpointV1(
        surface="A_REPORT",
        run_id=run_id,
        identity_id=report.report_id,
        artifact_id=report.artifact_id,
    )
    review_endpoint = CrossViewEndpointV1(
        surface="B_FINANCIAL_REVIEW",
        run_id=run_id,
        identity_id=review.review_id,
    )
    execution_endpoint = CrossViewEndpointV1(
        surface="C_EXECUTION_RECORD",
        run_id=run_id,
        identity_id=execution.canonical_execution_record_id,
    )
    hero = report.source_contributions[0] if report.source_contributions else None
    hero_report_endpoint = (
        CrossViewEndpointV1(
            surface="A_REPORT",
            run_id=run_id,
            identity_id=report.report_id,
            artifact_id=report.artifact_id,
            target_anchor=hero.report_anchor,
        )
        if hero is not None
        else report_endpoint
    )
    report_review_available = any(
        item.review_id == review.review_id for item in report.source_contributions
    )
    cross_view_refs = (
        CrossViewRefV1(
            run_id=run_id,
            source=report_endpoint,
            target=review_endpoint,
            status="AVAILABLE" if report_review_available else "UNAVAILABLE",
            reason_code=None if report_review_available else "REPORT_REVIEW_RELATION_NOT_OBSERVED",
        ),
        CrossViewRefV1(
            run_id=run_id,
            source=hero_report_endpoint,
            target=execution_endpoint,
            status="AVAILABLE" if hero is not None else "UNAVAILABLE",
            reason_code=None if hero is not None else "REPORT_EXECUTION_RELATION_NOT_OBSERVED",
        ),
        CrossViewRefV1(
            run_id=run_id,
            source=review_endpoint,
            target=execution_endpoint,
            status="UNAVAILABLE",
            reason_code="EXACT_REVIEW_EXECUTION_RELATION_NOT_OBSERVED",
        ),
        CrossViewRefV1(
            run_id=run_id,
            source=execution_endpoint,
            target=hero_report_endpoint,
            status="AVAILABLE" if hero is not None else "UNAVAILABLE",
            reason_code=None if hero is not None else "EXECUTION_REPORT_RELATION_NOT_OBSERVED",
        ),
    )
    return ResultsWorkspaceV1(
        run_id=run_id,
        object_id=object_id,
        as_of=run.as_of,
        run_status=_enum_value(run.status),
        released_result_id=result_id,
        canonical_execution_record_id=canonical_id,
        report_surface=ResultsSurfaceRefV1(
            surface="A_REPORT",
            run_id=run_id,
            object_id=object_id,
            released_result_id=result_id,
            canonical_execution_record_id=canonical_id,
            surface_id=report.report_id,
            href=f"/api/research-runs/{run_id}/report-view",
            availability=report.availability,
        ),
        review_surface=ResultsSurfaceRefV1(
            surface="B_FINANCIAL_REVIEW",
            run_id=run_id,
            object_id=object_id,
            released_result_id=result_id,
            canonical_execution_record_id=canonical_id,
            surface_id=review.review_id,
            href=f"/api/research-runs/{run_id}/review-view",
            availability=review.availability,
        ),
        execution_surface=ResultsSurfaceRefV1(
            surface="C_EXECUTION_RECORD",
            run_id=run_id,
            object_id=object_id,
            released_result_id=result_id,
            canonical_execution_record_id=canonical_id,
            surface_id=execution.canonical_execution_record_id,
            href=f"/api/research-runs/{run_id}/execution-view",
            availability=execution.availability,
        ),
        cross_view_refs=cross_view_refs,
    )


__all__ = [
    "ResultsIdentityError",
    "ResultsIntegrityError",
    "ResultsNotFoundError",
    "build_execution_record_surface",
    "build_financial_review_surface",
    "build_report_surface",
    "build_results_workspace",
    "resolve_review_check_selector",
]
