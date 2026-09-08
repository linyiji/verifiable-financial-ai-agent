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


def resolve_outputs(state, task):
    predecessors = [state.task(key) for key in task.dependencies]
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
