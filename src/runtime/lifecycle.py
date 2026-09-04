from src.domain.enums import TaskStatus
from src.domain.task import Task


class InvalidTaskTransition(RuntimeError):
    pass


_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.CREATED: frozenset({TaskStatus.WAITING, TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.WAITING: frozenset({TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLED}),
    TaskStatus.READY: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.READY,
            TaskStatus.WAITING_FOR_CAPABILITY,
            TaskStatus.SELF_CORRECTING,
            TaskStatus.REVIEW,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING_FOR_CAPABILITY: frozenset(
        {
            TaskStatus.READY,
            TaskStatus.BLOCKED,
            TaskStatus.CAPABILITY_BUILD_FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.SELF_CORRECTING: frozenset(
        {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.BLOCKED: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.REVIEW: frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CAPABILITY_BUILD_FAILED: frozenset(
        {
            TaskStatus.READY,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.CANCELLED: frozenset(),
}


def transition_task(task: Task, target: TaskStatus) -> None:
    if target == task.status:
        return
    if target not in _ALLOWED_TRANSITIONS[task.status]:
        raise InvalidTaskTransition(f"cannot transition {task.task_id}: {task.status} -> {target}")
    task.status = target
