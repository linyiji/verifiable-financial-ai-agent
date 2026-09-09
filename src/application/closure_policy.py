"""Requirement-aware closure; partial execution is neither release nor a crash."""

from pydantic import Field

from src.assurance.requirements import required_capabilities
from src.domain.base import DomainModel
from src.domain.financial_branch import BranchRequirement, BranchStatus
from src.runtime.output_dependencies import resolve_outputs


class ClosureOutputs(DomainModel):
    satisfied: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)


class ExecutionClosureState(DomainModel):
    """Read-only eligibility projection, never a Review or Release authorization."""

    required_outputs: ClosureOutputs = Field(default_factory=ClosureOutputs)
    supporting_outputs: ClosureOutputs = Field(default_factory=ClosureOutputs)
    limitations: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    fatal_reason: str | None = None

    @property
    def reviewable(self):
        return self.fatal_reason is None


def _ancestors(state, task):
    found = set(task.dependencies)
    pending = list(found)
    while pending:
        for key in state.task(pending.pop()).dependencies:
            if key not in found:
                found.add(key)
                pending.append(key)
    return found


def classify_execution_closure(aggregate):
    result = ExecutionClosureState()
    gaps = []
    calculations = {
        c.capability_id for c in aggregate.artifacts.calculations if c.status.value == "PASS"
    }
    for requirement in required_capabilities(aggregate.scheme):
        if requirement not in calculations:
            gaps.append("REQUIRED_CALCULATION_UNAVAILABLE")
            result.required_outputs.missing.append(requirement)
        else:
            result.required_outputs.satisfied.append(requirement)
    for branch in aggregate.artifacts.financial_branches:
        bucket = (
            result.required_outputs
            if branch.requirement is BranchRequirement.REQUIRED
            else result.supporting_outputs
        )
        if branch.status is BranchStatus.COMPLETED:
            bucket.satisfied.append(branch.branch_id)
        else:
            bucket.missing.append(branch.branch_id)
            if branch.status is BranchStatus.FAILED:
                bucket.failed.append(branch.branch_id)
            if branch.requirement is not BranchRequirement.REQUIRED:
                result.limitations.append(branch.branch_id + ":" + branch.status.value)
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
            result.required_outputs.missing.extend(resolve_outputs(aggregate.runtime, task)[1])
        legacy_supporting = not (
            optional.get(task.task_type) != task.assigned_agent
            or task.skill_id != task.task_type + "_v1"
            or task.missing_output_dependencies
            or not any(
                other.output_requirements is not None
                and task.task_id in _ancestors(aggregate.runtime, other)
                and f"{task.task_id}/agent_output" in other.output_requirements.supporting
                for other in aggregate.runtime.actual_graph.tasks
            )
        )
        # Explicit output contracts, not task names, can discharge a local failed
        # producer. Every declared output must be referenced; hard/ANY_OF inputs
        # remain enforced independently by resolve_outputs above.
        refs = {f"{task.task_id}/{o.output_id}" for o in task.output_outcomes}
        optional_refs = set()
        hard_refs = set()
        for consumer in aggregate.runtime.actual_graph.tasks:
            if task.task_id not in _ancestors(aggregate.runtime, consumer):
                continue
            contract = consumer.output_requirements
            if contract is None:
                if task.task_id in consumer.dependencies:
                    hard_refs.update(refs)
                continue
            hard_refs.update(contract.hard_required)
            optional_refs.update(contract.supporting + contract.enrichment)
            if resolve_outputs(aggregate.runtime, consumer)[0] == "READY":
                optional_refs.update(key for group in contract.any_of for key in group)
        explicit_supporting = bool(refs) and refs <= optional_refs and not refs & hard_refs
        if task.status.value == "COMPLETED":
            bucket = (
                result.supporting_outputs
                if legacy_supporting or explicit_supporting
                else result.required_outputs
            )
            bucket.satisfied.append(task.task_id)
            continue
        if not (legacy_supporting or explicit_supporting):
            gaps.append("REQUIRED_RESEARCH_OUTPUT_MISSING")
            result.required_outputs.missing.append(task.task_id)
            if task.status.value in {"FAILED", "CAPABILITY_BUILD_FAILED"}:
                result.required_outputs.failed.append(task.task_id)
        else:
            result.supporting_outputs.missing.append(task.task_id)
            if task.status.value == "FAILED":
                result.supporting_outputs.failed.append(task.task_id)
            result.limitations.append(task.task_id + ":" + task.status.value)
    result.reason_codes = sorted(set(gaps))
    result.fatal_reason = result.reason_codes[0] if gaps else None
    return result


def release_requirement_gaps(aggregate):
    return tuple(classify_execution_closure(aggregate).reason_codes)


def closure_diagnostic(aggregate, exc, stage):
    """Allowlisted causal metadata only; never persist raw exception text."""
    from uuid import uuid4

    from src.application.errors import ApplicationError

    codes = {
        "REVIEW_BLOCKED",
        "RELEASE_GATE_BLOCKED",
        "REQUIRED_RESEARCH_OUTPUT_MISSING",
        "REQUIRED_CALCULATION_UNAVAILABLE",
        "INCOMPLETE_RESEARCH_NOT_RELEASED",
        "PROOF_POLICY_CHANGED_AFTER_REVIEW",
        "MATERIAL_CALCULATION_TAXONOMY_MISMATCH",
        "REPORT_SOURCE_MAP_INCOMPLETE",
        "REPORT_SOURCE_IDENTITY_MISMATCH",
    }
    code = (
        exc.code
        if isinstance(exc, ApplicationError) and exc.code in codes
        else "UNEXPECTED_EXECUTION_FAILURE"
        if stage == "TASK_EXECUTION"
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
        "seam": "src/runtime/scheduler.py:execute"
        if stage == "TASK_EXECUTION"
        else "src/application/service.py:_assure_and_release",
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
