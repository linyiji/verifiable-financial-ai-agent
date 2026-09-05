from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from src.observability.langfuse_adapter import (
    LangfuseTelemetryDrainBarrier,
    LangfuseTraceAuditReader,
)

RUN_ID = "RUN-authoritative"
TRACE_ID = "trace-authoritative"
EXPECTED = ("root", "tool")


class FakeClock:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.elapsed

    def now(self) -> datetime:
        return datetime(2026, 9, 5, tzinfo=UTC) + timedelta(seconds=self.elapsed)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.elapsed += seconds


class FakeTraceProvider:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.timeouts: list[int] = []

    def force_flush(self, *, timeout_millis: int) -> bool:
        self.timeouts.append(timeout_millis)
        return self.result


def payload(
    *identities: str,
    run_id: str = RUN_ID,
    trace_id: str = TRACE_ID,
    credential: str | None = None,
) -> dict:
    observations = []
    for identity in identities:
        metadata = {"run_id": run_id}
        if credential is not None:
            metadata["credential"] = credential
        observations.append(
            {
                "id": identity,
                "traceId": trace_id,
                "name": f"vfas.{identity}",
                "metadata": metadata,
            }
        )
    return {"id": trace_id, "observations": observations}


def reader_for(responses: list[dict] | None = None, *, error: bool = False):
    clock = FakeClock()
    queued = list(responses or [])

    def get(trace_id: str) -> dict:
        assert trace_id == TRACE_ID
        if error:
            raise TimeoutError("deterministic readback timeout")
        if len(queued) > 1:
            return queued.pop(0)
        return queued[0]

    sdk = SimpleNamespace(api=SimpleNamespace(trace=SimpleNamespace(get=get)))
    reader = LangfuseTraceAuditReader(
        sdk,
        named_sensitive_values={"LANGFUSE_PUBLIC_KEY": "credential-sentinel"},
        monotonic_clock=clock.monotonic,
        wall_clock=clock.now,
        sleeper=clock.sleep,
    )
    return reader, sdk, clock


def audit(reader: LangfuseTraceAuditReader, *, timeout: float = 0.0):
    return reader.audit(
        TRACE_ID,
        expected_observation_identities=EXPECTED,
        expected_run_id=RUN_ID,
        readback_timeout_seconds=timeout,
        readback_schedule_seconds=(0.0, 2.0, 5.0, 10.0),
        force_flush_succeeded=True,
    )


def test_immediate_exact_remote_identity_set_passes_and_retains_attempt() -> None:
    reader, _, clock = reader_for([payload(*EXPECTED)])

    result = audit(reader)

    assert result.passed is True
    assert result.attempts == 1
    assert clock.sleeps == []
    attempt = result.readback_attempts[0]
    assert attempt.attempt_number == 1
    assert attempt.timestamp == "2026-09-05T00:00:00Z"
    assert attempt.expected_count == 2
    assert attempt.observed_count == 2
    assert attempt.unique_observed_count == 2
    assert attempt.missing_observation_identities == ()
    assert attempt.unexpected_observation_identities == ()
    assert attempt.duplicate_observation_identities == ()
    assert attempt.root_trace_count == 1
    assert attempt.run_id == RUN_ID
    assert attempt.trace_id == TRACE_ID
    assert attempt.run_metadata_closure is True
    assert attempt.trace_metadata_closure is True


def test_partial_remote_set_converges_before_deadline() -> None:
    reader, _, clock = reader_for([payload("root"), payload(*EXPECTED)])

    result = audit(reader, timeout=5.0)

    assert result.passed is True
    assert result.attempts == 2
    assert clock.sleeps == [2.0]
    assert result.readback_attempts[0].missing_observation_identities == ("tool",)
    assert result.readback_attempts[1].missing_observation_identities == ()


def test_same_count_with_substituted_identity_fails() -> None:
    reader, _, _ = reader_for([payload("root", "substitute")])

    result = audit(reader)

    assert result.passed is False
    assert result.missing_observation_identities == ("tool",)
    assert result.unexpected_observation_identities == ("substitute",)


def test_missing_identity_until_deadline_fails_closed() -> None:
    reader, _, clock = reader_for([payload("root")])

    result = audit(reader, timeout=5.0)

    assert result.passed is False
    assert result.attempts == 3
    assert clock.sleeps == [2.0, 3.0]
    assert result.elapsed_seconds == 5.0
    assert result.missing_observation_identities == ("tool",)


def test_unexpected_identity_fails() -> None:
    reader, _, _ = reader_for([payload("root", "tool", "unexpected")])

    result = audit(reader)

    assert result.passed is False
    assert result.unexpected_observation_identities == ("unexpected",)


def test_duplicate_identity_fails() -> None:
    reader, _, _ = reader_for([payload("root", "tool", "tool")])

    result = audit(reader)

    assert result.passed is False
    assert result.unexpected_duplicate_identities == ("tool",)


def test_wrong_run_binding_fails() -> None:
    reader, _, _ = reader_for([payload(*EXPECTED, run_id="RUN-foreign")])

    result = audit(reader)

    assert result.passed is False
    assert result.run_metadata_closure is False


def test_wrong_trace_binding_fails() -> None:
    remote = payload(*EXPECTED)
    remote["observations"][1]["traceId"] = "trace-foreign"
    reader, _, _ = reader_for([remote])

    result = audit(reader)

    assert result.passed is False
    assert result.trace_metadata_closure is False
    assert result.root_trace_count == 2


def test_observation_order_does_not_change_set_semantics() -> None:
    reader, _, _ = reader_for([payload("tool", "root")])

    result = audit(reader)

    assert result.passed is True
    assert result.observed_observation_identities == EXPECTED


def test_force_flush_success_continues_bounded_polling_until_slow_convergence() -> None:
    reader, sdk, clock = reader_for([payload("root"), payload("root"), payload(*EXPECTED)])
    provider = FakeTraceProvider()
    sdk._resources = SimpleNamespace(tracer_provider=provider)

    result = LangfuseTelemetryDrainBarrier(sdk, audit_reader=reader).audit(
        TRACE_ID,
        expected_observation_identities=EXPECTED,
        expected_run_id=RUN_ID,
        flush_timeout_millis=25,
        readback_timeout_seconds=5.0,
        readback_schedule_seconds=(0.0, 2.0, 5.0),
    )

    assert result.passed is True
    assert result.force_flush_succeeded is True
    assert result.attempts == 3
    assert clock.sleeps == [2.0, 3.0]
    assert provider.timeouts == [25]


def test_acceptance_barrier_defaults_to_bounded_sixty_second_schedule() -> None:
    reader, sdk, clock = reader_for([payload("root")])
    provider = FakeTraceProvider()
    sdk._resources = SimpleNamespace(tracer_provider=provider)

    result = LangfuseTelemetryDrainBarrier(sdk, audit_reader=reader).audit(
        TRACE_ID,
        expected_observation_identities=EXPECTED,
        expected_run_id=RUN_ID,
    )

    assert result.passed is False
    assert result.attempts == 7
    assert clock.elapsed == 60.0
    assert clock.sleeps == [2.0, 3.0, 5.0, 10.0, 20.0, 20.0]


def test_read_errors_until_deadline_fail_closed_without_real_sleep() -> None:
    reader, _, clock = reader_for(error=True)

    result = audit(reader, timeout=2.0)

    assert result.passed is False
    assert result.read_succeeded is False
    assert result.attempts == 2
    assert result.elapsed_seconds == 2.0
    assert clock.sleeps == [2.0]
    assert all(not item.read_succeeded for item in result.readback_attempts)


def test_failed_tail_reads_remain_in_attempt_evidence_after_partial_success() -> None:
    clock = FakeClock()
    calls = 0

    def get(trace_id: str) -> dict:
        nonlocal calls
        assert trace_id == TRACE_ID
        calls += 1
        if calls == 1:
            return payload("root")
        raise TimeoutError("deterministic tail timeout")

    sdk = SimpleNamespace(api=SimpleNamespace(trace=SimpleNamespace(get=get)))
    reader = LangfuseTraceAuditReader(
        sdk,
        named_sensitive_values={},
        monotonic_clock=clock.monotonic,
        wall_clock=clock.now,
        sleeper=clock.sleep,
    )

    result = audit(reader, timeout=2.0)

    assert result.passed is False
    assert result.attempts == 2
    assert len(result.readback_attempts) == 2
    assert [item.read_succeeded for item in result.readback_attempts] == [True, False]
    assert result.missing_observation_identities == ("tool",)


def test_clean_exact_set_preserves_zero_credential_occurrences() -> None:
    reader, _, _ = reader_for([payload(*EXPECTED)])

    result = audit(reader)

    assert result.passed is True
    assert result.occurrence_count == 0
    assert dict(result.named_occurrence_counts) == {"LANGFUSE_PUBLIC_KEY": 0}
