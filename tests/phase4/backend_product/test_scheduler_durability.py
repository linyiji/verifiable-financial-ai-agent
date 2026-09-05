"""Pure scheduler-fence tests plus the explicit parent-migration boundary.

No Phase 4 tables are created here.  The preflight assertions make the absent
parent-owned migration a tested fail-closed state rather than a skipped/xfail
integration scenario.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.phase4_product.admission import RunSchedulerAdmissionV1, SchedulerAdmissionState
from src.phase4_product.contracts import ErrorCodeV1
from src.phase4_product.durability import (
    REQUIRED_PHASE4_DURABILITY_CAPABILITIES,
    SchedulerLeaseFence,
    acknowledge_scheduler_admission,
    fail_scheduler_admission,
    lease_scheduler_admission,
    phase3_postgresql_preflight,
    record_scheduler_run_start,
    release_scheduler_admission,
    require_current_scheduler_fence,
)
from src.phase4_product.errors import ProductError

NOW = datetime(2026, 9, 5, 11, tzinfo=UTC)
LEASE = timedelta(minutes=2)


def _pending(*, attempts: int = 0, maximum: int = 3) -> RunSchedulerAdmissionV1:
    return RunSchedulerAdmissionV1(
        admission_id="ADMISSION-A",
        run_id="RUN-A",
        idempotency_outcome_id="IDEMPOTENCY-A",
        state=SchedulerAdmissionState.PENDING,
        delivery_attempt_count=attempts,
        max_delivery_attempts=maximum,
        next_attempt_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _lease(
    admission: RunSchedulerAdmissionV1 | None = None,
    *,
    at: datetime = NOW,
) -> tuple[RunSchedulerAdmissionV1, SchedulerLeaseFence]:
    return lease_scheduler_admission(
        admission or _pending(),
        worker_id="worker-a",
        leased_at=at,
        lease_duration=LEASE,
    )


def _assert_error(
    exc_info: pytest.ExceptionInfo[ProductError],
    code: ErrorCodeV1,
    reason: str,
) -> None:
    assert exc_info.value.code is code
    assert exc_info.value.details == {"reason_code": reason}


def test_lease_increments_attempt_and_generation_and_returns_exact_fence() -> None:
    pending = _pending()
    leased, fence = _lease(pending)

    assert pending.state is SchedulerAdmissionState.PENDING
    assert leased.state is SchedulerAdmissionState.LEASED
    assert leased.delivery_attempt_count == 1
    assert leased.lease_generation == 1
    assert leased.lease_owner == "worker-a"
    assert leased.lease_expires_at == NOW + LEASE
    assert fence == SchedulerLeaseFence(
        admission_id="ADMISSION-A",
        run_id="RUN-A",
        owner="worker-a",
        generation=1,
        expires_at=NOW + LEASE,
    )
    assert require_current_scheduler_fence(leased, fence, at=NOW + timedelta(seconds=1)) is leased


def test_live_lease_cannot_be_stolen_and_expired_lease_gets_new_generation() -> None:
    leased, old_fence = _lease()
    with pytest.raises(ProductError) as held:
        _lease(leased, at=NOW + timedelta(seconds=30))
    _assert_error(held, ErrorCodeV1.CONFLICT, "ADMISSION_LEASE_HELD")

    re_leased, new_fence = _lease(leased, at=NOW + LEASE)
    assert re_leased.delivery_attempt_count == 2
    assert new_fence.generation == old_fence.generation + 1
    with pytest.raises(ProductError) as stale:
        require_current_scheduler_fence(
            re_leased,
            old_fence,
            at=NOW + LEASE + timedelta(seconds=1),
        )
    _assert_error(stale, ErrorCodeV1.CONFLICT, "STALE_ADMISSION_FENCE")


def test_expired_current_fence_is_rejected_at_the_boundary() -> None:
    leased, fence = _lease()
    with pytest.raises(ProductError) as expired:
        require_current_scheduler_fence(leased, fence, at=fence.expires_at)
    _assert_error(expired, ErrorCodeV1.CONFLICT, "ADMISSION_LEASE_EXPIRED")


def test_run_start_is_one_idempotent_identity_under_the_current_fence() -> None:
    leased, fence = _lease()
    started_at = NOW + timedelta(seconds=10)
    started = record_scheduler_run_start(
        leased,
        fence,
        started_at=started_at,
        run_started_event_id="EVENT-START-A",
        run_started_sequence=3,
    )

    replay = record_scheduler_run_start(
        started,
        fence,
        started_at=started_at,
        run_started_event_id="EVENT-START-A",
        run_started_sequence=3,
    )
    assert replay is started

    with pytest.raises(ProductError) as mismatch:
        record_scheduler_run_start(
            started,
            fence,
            started_at=started_at,
            run_started_event_id="EVENT-START-B",
            run_started_sequence=3,
        )
    _assert_error(mismatch, ErrorCodeV1.INTEGRITY_FAILURE, "RUN_START_IDENTITY_MISMATCH")


def test_ack_requires_committed_start_then_clears_lease_and_is_idempotent() -> None:
    leased, fence = _lease()
    with pytest.raises(ProductError) as premature:
        acknowledge_scheduler_admission(
            leased,
            fence,
            acknowledged_at=NOW + timedelta(seconds=10),
        )
    _assert_error(premature, ErrorCodeV1.CONFLICT, "RUN_START_NOT_COMMITTED")

    started = record_scheduler_run_start(
        leased,
        fence,
        started_at=NOW + timedelta(seconds=10),
        run_started_event_id="EVENT-START-A",
        run_started_sequence=3,
    )
    acknowledged = acknowledge_scheduler_admission(
        started,
        fence,
        acknowledged_at=NOW + timedelta(seconds=20),
    )
    assert acknowledged.state is SchedulerAdmissionState.ACKNOWLEDGED
    assert acknowledged.lease_owner is None
    assert acknowledged.lease_expires_at is None
    assert acknowledged.start_committed_at == NOW + timedelta(seconds=10)
    assert (
        acknowledge_scheduler_admission(
            acknowledged,
            fence,
            acknowledged_at=NOW + timedelta(seconds=30),
        )
        is acknowledged
    )


def test_release_preserves_run_identity_and_old_fence_cannot_write_after_redelivery() -> None:
    leased, first_fence = _lease()
    due = NOW + timedelta(minutes=3)
    pending = release_scheduler_admission(
        leased,
        first_fence,
        released_at=NOW + timedelta(seconds=30),
        next_attempt_at=due,
    )
    assert pending.state is SchedulerAdmissionState.PENDING
    assert pending.next_attempt_at == due
    assert pending.admission_id == leased.admission_id
    assert pending.run_id == leased.run_id

    redelivered, second_fence = _lease(pending, at=due)
    assert second_fence.generation == 2
    with pytest.raises(ProductError) as stale:
        record_scheduler_run_start(
            redelivered,
            first_fence,
            started_at=due + timedelta(seconds=1),
            run_started_event_id="EVENT-START-A",
            run_started_sequence=3,
        )
    _assert_error(stale, ErrorCodeV1.CONFLICT, "STALE_ADMISSION_FENCE")


def test_failure_requires_current_fence_and_is_same_code_idempotent() -> None:
    leased, fence = _lease()
    with pytest.raises(ProductError) as missing_fence:
        fail_scheduler_admission(
            leased,
            failed_at=NOW + timedelta(seconds=10),
            failure_code="DELIVERY_FAILED",
        )
    _assert_error(missing_fence, ErrorCodeV1.CONFLICT, "ADMISSION_FENCE_REQUIRED")

    failed = fail_scheduler_admission(
        leased,
        fence=fence,
        failed_at=NOW + timedelta(seconds=10),
        failure_code="DELIVERY_FAILED",
    )
    assert failed.state is SchedulerAdmissionState.FAILED
    assert (
        fail_scheduler_admission(
            failed,
            failed_at=NOW + timedelta(seconds=20),
            failure_code="DELIVERY_FAILED",
        )
        is failed
    )

    with pytest.raises(ProductError) as mismatch:
        fail_scheduler_admission(
            failed,
            failed_at=NOW + timedelta(seconds=20),
            failure_code="ANOTHER_FAILURE",
        )
    _assert_error(
        mismatch,
        ErrorCodeV1.INTEGRITY_FAILURE,
        "ADMISSION_FAILURE_IDENTITY_MISMATCH",
    )


def test_attempt_exhaustion_is_terminal_not_an_unfenced_retry() -> None:
    leased, fence = _lease(_pending(attempts=0, maximum=1))
    with pytest.raises(ProductError) as exhausted:
        release_scheduler_admission(
            leased,
            fence,
            released_at=NOW + timedelta(seconds=10),
            next_attempt_at=NOW + timedelta(minutes=3),
        )
    _assert_error(exhausted, ErrorCodeV1.TERMINAL, "ADMISSION_DELIVERY_EXHAUSTED")


def test_phase3_schema_is_explicitly_not_phase4_ready_without_parent_migration() -> None:
    preflight = phase3_postgresql_preflight()

    assert preflight.postgresql is True
    assert preflight.ready is False
    assert preflight.migration_required is True
    assert set(preflight.missing_capabilities) == set(REQUIRED_PHASE4_DURABILITY_CAPABILITIES)
    assert {gap.capability for gap in preflight.migration_gaps} == set(
        REQUIRED_PHASE4_DURABILITY_CAPABILITIES
    )
    assert all(
        gap.schema_delta and gap.why_phase3_is_insufficient for gap in preflight.migration_gaps
    )

    with pytest.raises(ProductError) as exc_info:
        preflight.require_ready()
    _assert_error(exc_info, ErrorCodeV1.UNAVAILABLE, "PHASE4_MIGRATION_REQUIRED")
