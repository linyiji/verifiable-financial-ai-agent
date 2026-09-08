"""Versioned input contracts for the current qualitative research task profiles."""

from src.domain.output_dependency import OutputOutcome, OutputRequirements, OutputStatus


def configure_output_contracts(state):
    actors = {
        "valuation_analysis": "valuation_analyst",
        "risk_analysis": "risk_analyst",
        "report_synthesis": "research_lead",
    }
    for task in state.actual_graph.tasks:
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
            for key in state.task(pending.pop()).dependencies:
                if key not in ancestors:
                    ancestors.add(key)
                    pending.append(key)
        fundamental = [
            key for key in ancestors if state.task(key).task_type == "fundamental_analysis"
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


def publish_output(task, output_id, status, *, refs=(), reason=None):
    value = OutputOutcome(output_id=output_id, status=status, refs=list(refs), reason_code=reason)
    previous = next((item for item in task.output_outcomes if item.output_id == output_id), None)
    if previous is not None:
        if previous != value:
            raise ValueError("Output identity is immutable")
        return
    task.output_outcomes.append(value)


def availability_map(aggregate, task=None):
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
    return {
        "available_findings": [
            item.model_dump(mode="json")
            for item in aggregate.artifacts.agent_outputs
            if item.status == "SUCCESS" and item.task_id in scope
        ],
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
