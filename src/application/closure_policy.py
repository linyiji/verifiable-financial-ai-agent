"""Requirement-aware closure; partial execution is neither release nor a crash."""

from src.assurance.requirements import required_capabilities
from src.domain.financial_branch import BranchRequirement, BranchStatus
from src.runtime.output_dependencies import resolve_outputs


def release_requirement_gaps(aggregate):
    gaps = []
    calculations = {
        c.capability_id for c in aggregate.artifacts.calculations if c.status.value == "PASS"
    }
    for requirement in required_capabilities(aggregate.scheme):
        if requirement not in calculations:
            gaps.append("REQUIRED_CALCULATION_UNAVAILABLE")
    for branch in aggregate.artifacts.financial_branches:
        if (
            branch.requirement is BranchRequirement.REQUIRED
            and branch.status is not BranchStatus.COMPLETED
        ):
            gaps.append("REQUIRED_CALCULATION_UNAVAILABLE")
    # Only these frozen qualitative profiles have optional narrative output.
    optional = {
        "fundamental_analysis": "fundamental_analyst",
        "valuation_analysis": "valuation_analyst",
        "risk_analysis": "risk_analyst",
        "peer_analysis": "peer_analyst",
        "research_news_analysis": "research_news_analyst",
    }
    for task in aggregate.runtime.actual_graph.tasks:
        if (
            task.output_requirements is not None
            and resolve_outputs(aggregate.runtime, task)[0] != "READY"
        ):
            gaps.append("REQUIRED_RESEARCH_OUTPUT_MISSING")
        if task.status.value == "COMPLETED":
            continue
        if (
            optional.get(task.task_type) != task.assigned_agent
            or task.skill_id != task.task_type + "_v1"
            or task.missing_output_dependencies
            or not any(
                other.output_requirements is not None
                and f"{task.task_id}/agent_output" in other.output_requirements.supporting
                for other in aggregate.runtime.actual_graph.tasks
            )
        ):
            gaps.append("REQUIRED_RESEARCH_OUTPUT_MISSING")
    return tuple(sorted(set(gaps)))


def closure_diagnostic(aggregate, exc, stage):
    """Allowlisted causal metadata only; never persist raw exception text."""
    from uuid import uuid4

    from src.application.errors import ApplicationError

    codes = {
        "REVIEW_BLOCKED",
        "RELEASE_GATE_BLOCKED",
        "REQUIRED_RESEARCH_OUTPUT_MISSING",
        "INCOMPLETE_RESEARCH_NOT_RELEASED",
        "PROOF_POLICY_CHANGED_AFTER_REVIEW",
        "MATERIAL_CALCULATION_TAXONOMY_MISMATCH",
        "REPORT_SOURCE_MAP_INCOMPLETE",
        "REPORT_SOURCE_IDENTITY_MISMATCH",
    }
    code = (
        exc.code
        if isinstance(exc, ApplicationError) and exc.code in codes
        else "UNEXPECTED_CLOSURE_FAILURE"
    )
    return {
        "diagnostic_id": "DIAG-" + str(uuid4()),
        "run_id": aggregate.run.run_id,
        "stage": stage,
        "code": code,
        "exception_class": "ApplicationError"
        if isinstance(exc, ApplicationError)
        else "RuntimeException",
        "seam": "src/application/service.py:_assure_and_release",
        "review_id": aggregate.artifacts.review.review_id if aggregate.artifacts.review else None,
        "review_status": aggregate.artifacts.review.status.value
        if aggregate.artifacts.review
        else None,
        "proofs": [
            {"proof_id": p.proof_id, "status": p.status.value} for p in aggregate.artifacts.proofs
        ],
        "report_exists": aggregate.artifacts.report is not None,
        "writeback_exists": aggregate.artifacts.writeback is not None,
    }
