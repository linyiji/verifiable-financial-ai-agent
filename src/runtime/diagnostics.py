"""Bounded internal failure evidence; never serialize exception text or frame locals."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from src.domain.base import JsonObject
from src.domain.task import Task


class InsufficientTechnicalHistoryError(LookupError):
    """Owned precondition failure, distinct from deterministic FCF execution."""

    retryable = False

    def __init__(self, paired_observations: int) -> None:
        self.paired_observations = paired_observations
        super().__init__("at least 200 accepted paired historical observations are required")


def task_failure_diagnostic(error: Exception, *, task: Task, attempt: int) -> JsonObject:
    # Exact type matching prevents exception subclasses from injecting metadata.
    types = {
        ValueError: "ValueError",
        TypeError: "TypeError",
        LookupError: "LookupError",
        RuntimeError: "RuntimeError",
        TimeoutError: "TimeoutError",
        InsufficientTechnicalHistoryError: "InsufficientTechnicalHistoryError",
    }
    root = Path(__file__).resolve().parents[1]
    frames: list[JsonObject] = []
    traceback = error.__traceback__
    while traceback is not None:
        path = Path(traceback.tb_frame.f_code.co_filename).resolve()
        if path.is_relative_to(root):
            frames.append(
                {"file": "src/" + path.relative_to(root).as_posix(), "line": traceback.tb_lineno}
            )
        traceback = traceback.tb_next
    diagnostic: JsonObject = {
        "diagnostic_id": f"DIAG-{uuid4()}",
        "schema_version": "task-failure-diagnostic/v1",
        "run_id": task.run_id,
        "task_id": task.task_id,
        "attempt": attempt,
        "recorded_at": datetime.now(UTC).isoformat(),
        "exception_type": types.get(type(error), "UNCLASSIFIED_EXCEPTION"),
        "runtime_seam": "TASK_EXECUTION",
        "safe_message": "Task execution failed; inspect bounded owned stack locations.",
        "owned_frames": frames[-8:],
    }
    if type(error) is InsufficientTechnicalHistoryError:
        diagnostic.update(
            {
                "runtime_seam": "TECHNICAL_HISTORY_PREFLIGHT",
                "error_code": "INSUFFICIENT_TECHNICAL_HISTORY",
                "capability_id": "technical_sma_200",
                "required_paired_observations": 200,
                "available_paired_observations": error.paired_observations,
                "safe_message": "Technical analysis requires at least 200 paired observations.",
            }
        )
    return diagnostic
