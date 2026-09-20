"""Task edges retain ordering; explicit output contracts determine satisfaction."""

from src.domain.enums import TaskStatus
from src.domain.output_dependency import OutputStatus, evidence_sufficiency

SETTLED = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CAPABILITY_BUILD_FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.BLOCKED,
}


class ExecutionContinuationGate:
    """Scheduler exhaustion is not a Release decision; fatal errors never enter here."""

    @staticmethod
    def settled_for_review(state):
        return all(task.status in SETTLED for task in state.actual_graph.tasks) and any(
            task.output_requirements is not None for task in state.actual_graph.tasks
        )


def resolve_outputs(state, task, *, committed_results=None, require_current=False,
                    candidate_dependency=None):
    candidate_parent = None
    if candidate_dependency is not None:
        from src.domain.risk_replan import CandidateDependency

        CandidateDependency.model_validate(candidate_dependency)
        if (task.task_type != "risk_follow_up" or not task.parent_task_id
                or task.dependencies != [task.parent_task_id]
                or state.task(task.parent_task_id).task_type != "risk_analysis"):
            raise ValueError("Candidate dependency is restricted to the exact Risk child")
        candidate_parent = task.parent_task_id
    # With a binding marker, local outputs are navigation hints only. The caller
    # must supply the freshly resolved root pointers (admission revalidates bytes).
    if (
        require_current
        and state.binding_ref is not None
        and task.dependencies
        and (
            committed_results is None
            or any(key not in committed_results and key != candidate_parent
                   for key in task.dependencies)
        )
    ):
        return "WAITING", list(task.dependencies)
    predecessors = [state.task(key) for key in task.dependencies if key != candidate_parent]
    if task.output_requirements is None:
        missing = [item.task_id for item in predecessors if item.status is not TaskStatus.COMPLETED]
        return (
            "READY"
            if not missing
            else "BLOCKED"
            if any(
                item.status in SETTLED and item.status is not TaskStatus.COMPLETED
                for item in predecessors
            )
            else "WAITING",
            missing,
        )
    if any(item.status not in SETTLED for item in predecessors):
        return "WAITING", []
    # Only ancestors, never unrelated/future tasks, can satisfy an input contract.
    ancestors = set(task.dependencies)
    pending = list(ancestors)
    while pending:
        for key in state.task(pending.pop()).dependencies:
            if key not in ancestors:
                ancestors.add(key)
                pending.append(key)
    available = {
        f"{key}/{output.output_id}"
        for key in ancestors
        for output in state.task(key).output_outcomes
        if output.status is OutputStatus.COMPLETED and output.refs
    }
    result = evidence_sufficiency(task.output_requirements, available)
    return ("BLOCKED" if result.missing_required else "READY", result.missing_required)
