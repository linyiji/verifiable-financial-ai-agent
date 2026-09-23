"""Versioned input contracts for the current qualitative research task profiles."""

from copy import deepcopy
from typing import TYPE_CHECKING, Protocol

from src.domain.execution_profile import ExecutionSnapshot
from src.domain.node_binding import BindingDenied
from src.domain.output_dependency import OutputOutcome, OutputRequirements, OutputStatus
from src.domain.task import Task

if TYPE_CHECKING:
    from src.application.models import CompletedRunArtifacts, RunAggregate
    from src.runtime.state import RuntimeState


class LegacyResearchProjection(Protocol):
    runtime: "RuntimeState"
    artifacts: "CompletedRunArtifacts"


def configure_output_contracts(state):
    for task, canonical in zip(
        state.actual_graph.tasks,
        canonical_output_contract_tasks(state.actual_graph.tasks),
        strict=True,
    ):
        if task.output_requirements is None:
            task.output_requirements = canonical.output_requirements


def canonical_output_contract_tasks(tasks: list[Task]) -> list[Task]:
    """Return enriched Task copies without changing the source graph or runtime."""
    tasks = [task.model_copy(deep=True) for task in tasks]
    by_id = {task.task_id: task for task in tasks}
    actors = {
        "valuation_analysis": "valuation_analyst",
        "risk_analysis": "risk_analyst",
        "report_synthesis": "research_lead",
    }
    for task in tasks:
        if task.output_requirements is not None:
            continue
        if (
            task.task_type not in actors
            or task.assigned_agent != actors[task.task_type]
            or task.skill_id != task.task_type + "_v1"
        ):
            continue
        # Preserve exact graph ancestry and ordering. Unknown/new task profiles keep
        # strict task dependencies; no speculative relaxation of custom work.
        ancestors = set(task.dependencies)
        pending = list(ancestors)
        while pending:
            for key in by_id[pending.pop()].dependencies:
                if key not in ancestors:
                    ancestors.add(key)
                    pending.append(key)
        fundamental = [
            key for key in ancestors if by_id[key].task_type == "fundamental_analysis"
        ]
        if len(fundamental) != 1:
            continue
        producer = fundamental[0]
        financial = [f"{producer}/revenue_growth", f"{producer}/ebitda_margin"]
        optional = [f"{key}/agent_output" for key in sorted(ancestors)]
        if task.task_type in {"valuation_analysis", "risk_analysis", "report_synthesis"}:
            # Valuation currently offers a qualitative assessment, NOT a priced
            # valuation model. These two financial anchors are the minimum input;
            # no DCF/price/FCF-specific conclusion is authorized by this contract.
            task.output_requirements = OutputRequirements(
                hard_required=financial,
                supporting=optional,
            )
    return tasks


def publish_output(task, output_id, status, *, refs=(), reason=None):
    value = OutputOutcome(output_id=output_id, status=status, refs=list(refs), reason_code=reason)
    previous = next((item for item in task.output_outcomes if item.output_id == output_id), None)
    if previous is not None:
        if previous != value:
            raise ValueError("Output identity is immutable")
        return
    task.output_outcomes.append(value)


def availability_map_for_run(aggregate: "RunAggregate", task=None):
    from src.application.models import RunAggregate

    if not isinstance(aggregate, RunAggregate):
        raise BindingDenied("CONFIRMED_AUTHORITY_CORRUPT", "full Run required")
    return _availability_map(aggregate, task, execution_snapshot=None, from_confirmed_run=True)


def availability_map(
    aggregate: "RunAggregate | LegacyResearchProjection", task=None, *,
    execution_snapshot: ExecutionSnapshot | None = None,
):
    """Project legacy inputs or validate the full Run's frozen D01 authority."""
    return _availability_map(
        aggregate, task, execution_snapshot=execution_snapshot, from_confirmed_run=False
    )


def _availability_map(aggregate, task, *, execution_snapshot, from_confirmed_run):
    # Both public routes always enter this gate. The flag selects snapshot source, never mode.
    from src.application.models import RunAggregate
    from src.application.repository import _validate_root
    from src.application.risk_admission import _final_current_results
    from src.domain.risk_admission import contract_for

    contract = contract_for(aggregate) if isinstance(aggregate, RunAggregate) else None
    current = None
    root = aggregate.node_binding if isinstance(aggregate, RunAggregate) else None
    if root is not None:
        _validate_root(aggregate)
    if from_confirmed_run:
        execution_snapshot = (ExecutionSnapshot.model_validate(root.execution_snapshot)
                              if root is not None else None)
    snapshot = None
    if execution_snapshot is not None:
        if not isinstance(execution_snapshot, ExecutionSnapshot):
            raise BindingDenied("PROFILE_BINDING_MISSING")
        # Reparse serialized content: model_copy/model_construct are not authority.
        snapshot = ExecutionSnapshot.model_validate(execution_snapshot.model_dump())
    if contract is not None or (
        snapshot is not None and snapshot.scenario.risk_semantic_contract is not None
    ):
        if snapshot is None or not isinstance(aggregate, RunAggregate):
            raise BindingDenied("PROFILE_BINDING_MISSING")
        if (snapshot != ExecutionSnapshot.model_validate(root.execution_snapshot)
                or snapshot.scenario_snapshot_digest != root.scenario_snapshot_digest
                or snapshot.execution_profile_snapshot_digest
                != root.execution_profile_snapshot_digest):
            raise BindingDenied("RISK_ADMISSION_SCOPE_MISMATCH")
        current = _final_current_results(aggregate, contract)
    scope = {item.task_id for item in aggregate.runtime.actual_graph.tasks}
    if task is not None:
        scope = {task.task_id}
        pending = [task.task_id]
        while pending:
            for key in aggregate.runtime.task(pending.pop()).dependencies:
                if key not in scope:
                    scope.add(key)
                    pending.append(key)
    tasks = [item for item in aggregate.runtime.actual_graph.tasks if item.task_id in scope]
    for item in (*aggregate.artifacts.calculations, *aggregate.artifacts.agent_outputs):
        if item.run_id != aggregate.runtime.run_id:
            raise ValueError("Research output has foreign Run identity")
    findings = [
        item.model_dump(mode="json")
        for item in aggregate.artifacts.agent_outputs
        if item.status == "SUCCESS" and item.task_id in scope
        and (contract is None or item.task_id != contract["task_id"])
        and ((root is None
              or item.task_id in root.current_results)
             if current is None else item.task_id in current)
    ]
    if contract is not None and contract["task_id"] in scope and contract["task_id"] in current:
        # final_current_results validated this exact result and its retained material.
        # The receipt selects content; aggregate artifact order/content is not authority.
        result = aggregate.node_binding.results[current[contract["task_id"]]]
        receipt = aggregate.node_binding.risk_admissions[result.admission_binding_id]
        records = [
            record for record in result.output_records
            if record.kind == "AGENT_OUTPUT"
            and record.record_id == receipt["candidate_output_id"]
            and record.content_digest == receipt["candidate_content_digest"]
            and record.payload_snapshot.get("artifact_sha256")
            == receipt["candidate_artifact_digest"]
        ]
        if len(records) != 1:
            raise BindingDenied("RISK_CANDIDATE_CARDINALITY")
        findings.append(deepcopy(records[0].payload_snapshot))
    return {
        "available_findings": findings,
        "financial_branches": [
            item.model_dump(mode="json")
            for item in aggregate.artifacts.financial_branches
            if item.task_id in scope
        ],
        "available_calculations": [
            item.model_dump(mode="json")
            for item in aggregate.artifacts.calculations
            if item.task_id in scope and item.status.value == "PASS"
        ],
        "output_availability": [
            {"task_id": task.task_id, **output.model_dump(mode="json")}
            for task in tasks
            for output in task.output_outcomes
        ],
        "blocked_claims": [
            {"task_id": task.task_id, "missing_outputs": task.missing_output_dependencies}
            for task in tasks
            if task.missing_output_dependencies
        ],
        "source_limitations": [
            {"task_id": task.task_id, "sources": task.evidence_source_coverage}
            for task in tasks
            if task.evidence_source_coverage
        ],
        "failed_branches": [
            {"task_id": task.task_id, **output.model_dump(mode="json")}
            for task in tasks
            for output in task.output_outcomes
            if output.status is not OutputStatus.COMPLETED
        ],
        "release_status": "NOT_RELEASED",
    }
