from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class ProviderExecutionPolicyV1:
    """Owned wall-clock and transport budget for one structured provider call.

    HTTP read timeouts are inactivity limits: a peer can keep a response alive by
    periodically sending bytes.  ``per_attempt_deadline_seconds`` and
    ``overall_workload_deadline_seconds`` are therefore independent wall-clock
    limits and always dominate transport activity and retry/backoff work.
    """

    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 45.0
    write_timeout_seconds: float = 30.0
    pool_timeout_seconds: float = 10.0
    max_attempts: int = 2
    bounded_backoff_seconds: tuple[float, ...] = (1.0,)
    per_attempt_deadline_seconds: float = 90.0
    overall_workload_deadline_seconds: float = 180.0

    def __post_init__(self) -> None:
        timeout_values = (
            self.connect_timeout_seconds,
            self.read_timeout_seconds,
            self.write_timeout_seconds,
            self.pool_timeout_seconds,
            self.per_attempt_deadline_seconds,
            self.overall_workload_deadline_seconds,
        )
        if any(value <= 0 for value in timeout_values):
            raise ValueError("provider execution timeouts must be positive")
        if self.max_attempts < 1:
            raise ValueError("provider max_attempts must be positive")
        if any(value < 0 for value in self.bounded_backoff_seconds):
            raise ValueError("provider backoff values must not be negative")
        retry_backoff = sum(
            self.backoff_seconds(attempt) for attempt in range(1, self.max_attempts)
        )
        if self.overall_workload_deadline_seconds > (
            self.per_attempt_deadline_seconds * self.max_attempts + retry_backoff
        ):
            raise ValueError(
                "overall workload deadline must not exceed the owned attempt/backoff budget"
            )

    @property
    def httpx_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
            write=self.write_timeout_seconds,
            pool=self.pool_timeout_seconds,
        )

    def backoff_seconds(self, completed_attempt: int) -> float:
        if completed_attempt < 1 or not self.bounded_backoff_seconds:
            return 0.0
        index = min(completed_attempt - 1, len(self.bounded_backoff_seconds) - 1)
        return self.bounded_backoff_seconds[index]
