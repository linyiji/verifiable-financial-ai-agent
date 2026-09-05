from dataclasses import dataclass
from enum import StrEnum

from src.domain.enums import TaskStatus
from src.domain.task import Task


class InvalidTaskTransition(RuntimeError):
    pass


class TaskProjectionStage(StrEnum):
    """Frozen Phase 4 task-stage vocabulary exposed by Run projections."""

    QUEUED = "QUEUED"
    READY = "READY"
    ACTIVE = "ACTIVE"
    WAITING_SUPPORT = "WAITING_SUPPORT"
    CORRECTING = "CORRECTING"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class TaskLifecycleProjection:
    """Lossless raw Task status plus its frozen display stage and terminal bit."""

    status: TaskStatus
    stage: TaskProjectionStage
    terminal: bool


_TASK_STAGE_BY_STATUS: dict[TaskStatus, TaskProjectionStage] = {
    TaskStatus.CREATED: TaskProjectionStage.QUEUED,
    TaskStatus.WAITING: TaskProjectionStage.QUEUED,
    TaskStatus.READY: TaskProjectionStage.READY,
    TaskStatus.RUNNING: TaskProjectionStage.ACTIVE,
    TaskStatus.WAITING_FOR_CAPABILITY: TaskProjectionStage.WAITING_SUPPORT,
    TaskStatus.SELF_CORRECTING: TaskProjectionStage.CORRECTING,
    TaskStatus.BLOCKED: TaskProjectionStage.BLOCKED,
    TaskStatus.REVIEW: TaskProjectionStage.REVIEW,
    TaskStatus.COMPLETED: TaskProjectionStage.COMPLETE,
    TaskStatus.FAILED: TaskProjectionStage.FAILED,
    TaskStatus.CAPABILITY_BUILD_FAILED: TaskProjectionStage.FAILED,
    TaskStatus.CANCELLED: TaskProjectionStage.CANCELLED,
}

_TERMINAL_TASK_STATUSES = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CAPABILITY_BUILD_FAILED,
        TaskStatus.CANCELLED,
    }
)


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


def project_task_lifecycle(status: TaskStatus) -> TaskLifecycleProjection:
    """Project the exact raw status without creating a second lifecycle authority."""

    return TaskLifecycleProjection(
        status=status,
        stage=_TASK_STAGE_BY_STATUS[status],
        terminal=status in _TERMINAL_TASK_STATUSES,
    )


def transition_task(task: Task, target: TaskStatus) -> None:
    if target == task.status:
        return
    if target not in _ALLOWED_TRANSITIONS[task.status]:
        raise InvalidTaskTransition(f"cannot transition {task.task_id}: {task.status} -> {target}")
    task.status = target
