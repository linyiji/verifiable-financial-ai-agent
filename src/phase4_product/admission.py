"""Pure Phase 4 prepare/confirm and durable admission rules.

This module intentionally owns no database session, FastAPI request, background
task, or runtime executor.  It creates and validates immutable values that a
PostgreSQL unit of work can persist atomically and that a fenced worker can
later deliver at least once without creating a second logical Run start.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.phase4_product.contracts import (
    AvailabilityStatus,
    ConfirmResearchRunRequestV1,
    ConfirmRunResponseV1,
    CreateResearchObjectRequestV1,
    GoalProjectionV1,
    PrepareResearchRunRequestV1,
    ResearchRunDraftV1,
    ResponseMetaV1,
    RunAdmissionV1,
    SchemeProjectionV1,
)
from src.phase4_product.errors import ErrorCodeV1, ProductError, product_error
from src.phase4_product.hashing import (
    canonical_request_hash,
    draft_payload_hash,
    require_sha256_identity,
)

PREPARE_ROUTE_TEMPLATE = "/api/research-runs/prepare"
CONFIRM_ROUTE_TEMPLATE = "/api/research-runs"
CREATE_OBJECT_ROUTE_TEMPLATE = "/api/objects"
DRAFT_EXPIRY = timedelta(minutes=30)
RUN_ADMISSION_POLICY_VERSION = "phase4-run-admission-delivery/v1"


class FrozenRecordModel(BaseModel):
    """Closed immutable base for internal durable records."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)


class ResearchRunDraftRecordV1(FrozenRecordModel):
    """A public immutable draft plus its non-public consumption tombstone."""

    draft: ResearchRunDraftV1
    consumed_at: datetime | None = None
    consumed_admission_id: str | None = None
    consumed_run_id: str | None = None

    @property
    def consumed(self) -> bool:
        return self.consumed_at is not None

    @model_validator(mode="after")
    def consumption_is_all_or_nothing(self) -> ResearchRunDraftRecordV1:
        values = (self.consumed_at, self.consumed_admission_id, self.consumed_run_id)
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            raise ValueError("draft consumption identity must be recorded atomically")
        if self.consumed_at is not None:
            _require_utc(self.consumed_at, field_name="consumed_at")
            if self.consumed_at < self.draft.created_at:
                raise ValueError("draft cannot be consumed before it is created")
            _require_nonblank(self.consumed_admission_id, field_name="consumed_admission_id")
            _require_nonblank(self.consumed_run_id, field_name="consumed_run_id")
        return self


class SchedulerAdmissionState(StrEnum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"


class RunSchedulerAdmissionV1(FrozenRecordModel):
    """Durable, fenced delivery state for exactly one logical Run start."""

    admission_id: str
    run_id: str
    idempotency_outcome_id: str
    state: SchedulerAdmissionState = SchedulerAdmissionState.PENDING
    delivery_attempt_count: int = Field(default=0, ge=0)
    max_delivery_attempts: int = Field(default=3, ge=1)
    next_attempt_at: datetime | None = None
    lease_owner: str | None = None
    lease_generation: int = Field(default=0, ge=0)
    lease_expires_at: datetime | None = None
    start_committed_at: datetime | None = None
    run_started_event_id: str | None = None
    run_started_sequence: int | None = Field(default=None, ge=1)
    acknowledged_at: datetime | None = None
    failed_at: datetime | None = None
    failure_code: str | None = None
    policy_version: Literal["phase4-run-admission-delivery/v1"] = RUN_ADMISSION_POLICY_VERSION
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def state_fields_are_consistent(self) -> RunSchedulerAdmissionV1:
        for field_name in ("admission_id", "run_id", "idempotency_outcome_id"):
            _require_nonblank(getattr(self, field_name), field_name=field_name)
        for field_name in (
            "next_attempt_at",
            "lease_expires_at",
            "start_committed_at",
            "acknowledged_at",
            "failed_at",
            "created_at",
            "updated_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_utc(value, field_name=field_name)
        if self.updated_at < self.created_at:
            raise ValueError("scheduler admission updated_at cannot precede created_at")
        if self.delivery_attempt_count > self.max_delivery_attempts:
            raise ValueError("delivery attempts cannot exceed the configured maximum")

        start_values = (
            self.start_committed_at,
            self.run_started_event_id,
            self.run_started_sequence,
        )
        if any(value is not None for value in start_values) and not all(
            value is not None for value in start_values
        ):
            raise ValueError("Run start time, event identity, and sequence are one atomic fact")

        if self.state is SchedulerAdmissionState.PENDING:
            if self.lease_owner is not None or self.lease_expires_at is not None:
                raise ValueError("PENDING admission cannot hold a worker lease")
            if self.acknowledged_at is not None or self.failed_at is not None:
                raise ValueError("PENDING admission cannot be terminal")
        elif self.state is SchedulerAdmissionState.LEASED:
            _require_nonblank(self.lease_owner, field_name="lease_owner")
            if self.lease_generation < 1 or self.lease_expires_at is None:
                raise ValueError("LEASED admission requires a fenced, expiring lease")
            if self.lease_expires_at <= self.updated_at:
                raise ValueError("worker lease must expire after its update time")
            if self.next_attempt_at is not None:
                raise ValueError("LEASED admission cannot retain a pending delivery time")
            if self.acknowledged_at is not None or self.failed_at is not None:
                raise ValueError("LEASED admission cannot be terminal")
        elif self.state is SchedulerAdmissionState.ACKNOWLEDGED:
            if not all(value is not None for value in start_values):
                raise ValueError("ACKNOWLEDGED admission requires the committed Run start")
            if self.acknowledged_at is None:
                raise ValueError("ACKNOWLEDGED admission requires acknowledged_at")
            if self.failed_at is not None or self.failure_code is not None:
                raise ValueError("ACKNOWLEDGED admission cannot also be failed")
            if (
                self.next_attempt_at is not None
                or self.lease_owner is not None
                or self.lease_expires_at is not None
            ):
                raise ValueError("ACKNOWLEDGED admission cannot retain delivery or lease state")
        elif self.state is SchedulerAdmissionState.FAILED:
            if self.failed_at is None:
                raise ValueError("FAILED admission requires failed_at")
            _require_nonblank(self.failure_code, field_name="failure_code")
            if self.acknowledged_at is not None:
                raise ValueError("FAILED admission cannot also be acknowledged")
            if (
                self.next_attempt_at is not None
                or self.lease_owner is not None
                or self.lease_expires_at is not None
            ):
                raise ValueError("FAILED admission cannot retain delivery or lease state")

        if self.state is not SchedulerAdmissionState.FAILED and self.failure_code is not None:
            raise ValueError("failure_code is valid only for a FAILED admission")
        return self


class IdempotencyDecisionKind(StrEnum):
    CREATE = "CREATE"
    REPLAY = "REPLAY"
    CONFLICT = "CONFLICT"


class IdempotencyDecision(FrozenRecordModel):
    kind: IdempotencyDecisionKind
    incoming_request_hash: str
    stored_request_hash: str | None = None
    reason_code: Literal["IDEMPOTENCY_REQUEST_MISMATCH"] | None = None

    @model_validator(mode="after")
    def decision_is_consistent(self) -> IdempotencyDecision:
        require_sha256_identity(
            self.incoming_request_hash,
            field_name="incoming_request_hash",
        )
        if self.stored_request_hash is not None:
            require_sha256_identity(
                self.stored_request_hash,
                field_name="stored_request_hash",
            )
        if self.kind is IdempotencyDecisionKind.CREATE:
            if self.stored_request_hash is not None or self.reason_code is not None:
                raise ValueError("CREATE requires no stored idempotency outcome")
        elif self.kind is IdempotencyDecisionKind.REPLAY:
            if self.stored_request_hash is None or self.reason_code is not None:
                raise ValueError("REPLAY requires one matching stored request hash")
            if not hmac.compare_digest(self.incoming_request_hash, self.stored_request_hash):
                raise ValueError("REPLAY hashes must match")
        elif self.kind is IdempotencyDecisionKind.CONFLICT:
            if self.stored_request_hash is None:
                raise ValueError("CONFLICT requires a stored request hash")
            if hmac.compare_digest(self.incoming_request_hash, self.stored_request_hash):
                raise ValueError("CONFLICT hashes must differ")
            if self.reason_code != "IDEMPOTENCY_REQUEST_MISMATCH":
                raise ValueError("CONFLICT requires the frozen mismatch reason")
        return self


class ValidatedConfirmRequestV1(FrozenRecordModel):
    """A confirm request proven to name one live, exact immutable draft."""

    draft: ResearchRunDraftV1
    request: ConfirmResearchRunRequestV1
    confirmation_request_hash: str

    @model_validator(mode="after")
    def identities_match(self) -> ValidatedConfirmRequestV1:
        require_sha256_identity(
            self.confirmation_request_hash,
            field_name="confirmation_request_hash",
        )
        if self.request.draft_id != self.draft.draft_id:
            raise ValueError("validated request names another draft")
        if self.request.research_object_id != self.draft.object_id:
            raise ValueError("validated request names another object")
        if self.request.draft_version != self.draft.draft_version:
            raise ValueError("validated request names another draft version")
        if self.request.draft_hash != self.draft.draft_hash:
            raise ValueError("validated request carries another draft hash")
        return self


def build_prepare_draft(
    request: PrepareResearchRunRequestV1,
    *,
    draft_id: str,
    goal: GoalProjectionV1,
    scheme_snapshot: SchemeProjectionV1,
    created_at: datetime | None = None,
) -> ResearchRunDraftV1:
    """Create the exact 30-minute, Scheme-only immutable prepare result."""

    now = _as_utc(created_at or datetime.now(UTC), field_name="created_at")
    _validate_prepare_identity(request, goal=goal, scheme_snapshot=scheme_snapshot)
    _require_nonblank(draft_id, field_name="draft_id")
    prepare_hash = prepare_request_hash(request)
    payload = {
        "schema_version": "phase4-run-draft/v1",
        "draft_id": draft_id,
        "draft_version": 1,
        "status": "AWAITING_CONFIRMATION",
        "preview_kind": "SCHEME_ONLY",
        "planned_graph_availability": {
            "status": AvailabilityStatus.NOT_GENERATED.value,
            "reason_code": "PLAN_CREATED_ON_CONFIRM",
            "retryable": False,
        },
        "object_id": request.research_object_id,
        "goal": goal.model_dump(mode="json"),
        "scheme_snapshot": scheme_snapshot.model_dump(mode="json"),
        "prepare_request_hash": prepare_hash,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + DRAFT_EXPIRY).isoformat().replace("+00:00", "Z"),
    }
    draft = ResearchRunDraftV1.model_validate(
        {**payload, "draft_hash": draft_payload_hash(payload)}
    )
    if not draft_hash_is_valid(draft):  # defensive assertion at the ownership boundary
        raise AssertionError("constructed draft hash does not bind its immutable payload")
    return draft


def draft_hash_is_valid(draft: ResearchRunDraftV1) -> bool:
    """Verify the stored draft hash without mutating or repairing the draft."""

    payload = draft.model_dump(mode="json")
    expected = draft_payload_hash(payload)
    return hmac.compare_digest(draft.draft_hash, expected)


def validate_confirm_request(
    draft_or_record: ResearchRunDraftV1 | ResearchRunDraftRecordV1,
    request: ConfirmResearchRunRequestV1,
    *,
    now: datetime | None = None,
) -> ValidatedConfirmRequestV1:
    """Fail closed unless a new admission may consume this exact draft.

    Durable idempotency lookup must run before this function.  An exact replay
    returns its stored admission even though the draft is already consumed;
    this validator governs only creation of a new admission outcome.
    """

    record = (
        draft_or_record
        if isinstance(draft_or_record, ResearchRunDraftRecordV1)
        else ResearchRunDraftRecordV1(draft=draft_or_record)
    )
    draft = record.draft
    checked_at = _as_utc(now or datetime.now(UTC), field_name="now")

    if request.draft_id != draft.draft_id:
        raise _identity_error("draft", request.draft_id)
    if request.research_object_id != draft.object_id:
        raise _identity_error("research_object", request.research_object_id)
    _validate_draft_identity_closure(draft)
    if not draft_hash_is_valid(draft):
        raise product_error(
            ErrorCodeV1.INTEGRITY_FAILURE,
            "stored research draft failed its immutable hash check",
            resource_type="research_run_draft",
            resource_id=draft.draft_id,
            details={"reason_code": "DRAFT_HASH_INTEGRITY_FAILURE"},
        )
    if request.draft_version != draft.draft_version:
        raise _draft_conflict(draft, "DRAFT_VERSION_MISMATCH")
    if not hmac.compare_digest(request.draft_hash, draft.draft_hash):
        # The frozen conflict vocabulary treats a stale draft hash as the same
        # immutable-version conflict; a same-key changed request is rejected
        # earlier as IDEMPOTENCY_REQUEST_MISMATCH.
        raise _draft_conflict(draft, "DRAFT_VERSION_MISMATCH")
    if record.consumed:
        raise _draft_conflict(draft, "DRAFT_CONSUMED")
    if checked_at >= draft.expires_at:
        raise _draft_conflict(draft, "DRAFT_EXPIRED")

    return ValidatedConfirmRequestV1(
        draft=draft,
        request=request,
        confirmation_request_hash=confirmation_request_hash(request),
    )


def confirmation_request_hash(request: ConfirmResearchRunRequestV1) -> str:
    """Hash the exact V1 confirm body and frozen request context."""

    return canonical_request_hash(
        method="POST",
        route_template=CONFIRM_ROUTE_TEMPLATE,
        body=request.model_dump(mode="json"),
    )


def prepare_request_hash(request: PrepareResearchRunRequestV1) -> str:
    """Hash the exact V1 Prepare body and normalized mutation route."""

    return canonical_request_hash(
        method="POST",
        route_template=PREPARE_ROUTE_TEMPLATE,
        body=request.model_dump(mode="json"),
    )


def create_object_request_hash(request: CreateResearchObjectRequestV1) -> str:
    """Hash the exact V1 Object-creation body and normalized mutation route."""

    return canonical_request_hash(
        method="POST",
        route_template=CREATE_OBJECT_ROUTE_TEMPLATE,
        body=request.model_dump(mode="json"),
    )


def build_run_admission(
    validated: ValidatedConfirmRequestV1,
    *,
    admission_id: str,
    run_id: str,
    planned_graph_id: str,
    admitted_at: datetime | None = None,
) -> RunAdmissionV1:
    """Build the immutable outcome stored by the confirm transaction."""

    timestamp = _as_utc(admitted_at or datetime.now(UTC), field_name="admitted_at")
    draft = validated.draft
    return RunAdmissionV1(
        admission_id=admission_id,
        run_id=run_id,
        object_id=draft.object_id,
        draft_id=draft.draft_id,
        draft_version=draft.draft_version,
        draft_hash=draft.draft_hash,
        goal_id=draft.goal.goal_id,
        scheme_id=draft.scheme_snapshot.scheme_id,
        planned_graph_id=planned_graph_id,
        confirmation_request_hash=validated.confirmation_request_hash,
        admitted_at=timestamp,
        projection_ref=f"/api/research-runs/{run_id}/projection",
        events_ref=f"/api/research-runs/{run_id}/events",
    )


def mark_draft_consumed(
    draft_or_record: ResearchRunDraftV1 | ResearchRunDraftRecordV1,
    *,
    admission: RunAdmissionV1,
    consumed_at: datetime | None = None,
) -> ResearchRunDraftRecordV1:
    """Return a new tombstoned record; never mutate the public draft payload."""

    record = (
        draft_or_record
        if isinstance(draft_or_record, ResearchRunDraftRecordV1)
        else ResearchRunDraftRecordV1(draft=draft_or_record)
    )
    if record.consumed:
        raise _draft_conflict(record.draft, "DRAFT_CONSUMED")
    if (
        admission.draft_id != record.draft.draft_id
        or admission.draft_version != record.draft.draft_version
        or admission.draft_hash != record.draft.draft_hash
        or admission.object_id != record.draft.object_id
    ):
        raise product_error(
            ErrorCodeV1.IDENTITY_MISMATCH,
            "admission does not belong to the requested research draft",
            resource_type="research_run_draft",
            resource_id=record.draft.draft_id,
        )
    timestamp = _as_utc(consumed_at or admission.admitted_at, field_name="consumed_at")
    return ResearchRunDraftRecordV1(
        draft=record.draft,
        consumed_at=timestamp,
        consumed_admission_id=admission.admission_id,
        consumed_run_id=admission.run_id,
    )


def decide_idempotency(
    *,
    incoming_request_hash: str,
    stored_request_hash: str | None,
) -> IdempotencyDecision:
    """Classify one scoped key lookup without returning or mutating an outcome."""

    require_sha256_identity(incoming_request_hash, field_name="incoming_request_hash")
    if stored_request_hash is None:
        return IdempotencyDecision(
            kind=IdempotencyDecisionKind.CREATE,
            incoming_request_hash=incoming_request_hash,
        )
    require_sha256_identity(stored_request_hash, field_name="stored_request_hash")
    if hmac.compare_digest(incoming_request_hash, stored_request_hash):
        return IdempotencyDecision(
            kind=IdempotencyDecisionKind.REPLAY,
            incoming_request_hash=incoming_request_hash,
            stored_request_hash=stored_request_hash,
        )
    return IdempotencyDecision(
        kind=IdempotencyDecisionKind.CONFLICT,
        incoming_request_hash=incoming_request_hash,
        stored_request_hash=stored_request_hash,
        reason_code="IDEMPOTENCY_REQUEST_MISMATCH",
    )


def require_idempotency_match(decision: IdempotencyDecision) -> IdempotencyDecision:
    """Raise the frozen safe conflict for a same-key/different-request lookup."""

    if decision.kind is IdempotencyDecisionKind.CONFLICT:
        raise product_error(
            ErrorCodeV1.CONFLICT,
            "Idempotency-Key was already used for a different request",
            details={"reason_code": "IDEMPOTENCY_REQUEST_MISMATCH"},
        )
    return decision


def build_confirm_response(
    admission: RunAdmissionV1,
    *,
    request_id: str | None,
    idempotency_replayed: bool,
) -> ConfirmRunResponseV1:
    """Wrap an unchanged admission in per-attempt response metadata."""

    if request_id is not None and not request_id.strip():
        raise ValueError("request_id must be non-empty when supplied")
    return ConfirmRunResponseV1(
        admission=admission,
        response_meta=ResponseMetaV1(
            request_id=request_id,
            idempotency_replayed=idempotency_replayed,
        ),
    )


def build_scheduler_admission(
    admission: RunAdmissionV1,
    *,
    idempotency_outcome_id: str,
    max_delivery_attempts: int = 3,
    created_at: datetime | None = None,
) -> RunSchedulerAdmissionV1:
    """Create the one PENDING outbox record committed with the Run."""

    timestamp = _as_utc(created_at or admission.admitted_at, field_name="created_at")
    return RunSchedulerAdmissionV1(
        admission_id=admission.admission_id,
        run_id=admission.run_id,
        idempotency_outcome_id=idempotency_outcome_id,
        max_delivery_attempts=max_delivery_attempts,
        next_attempt_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _validate_prepare_identity(
    request: PrepareResearchRunRequestV1,
    *,
    goal: GoalProjectionV1,
    scheme_snapshot: SchemeProjectionV1,
) -> None:
    _require_utc(goal.created_at, field_name="goal.created_at")
    _require_utc(scheme_snapshot.created_at, field_name="scheme_snapshot.created_at")
    if request.research_object_id != goal.research_object_id:
        raise _identity_error("research_object", request.research_object_id)
    if scheme_snapshot.research_object_id != request.research_object_id:
        raise _identity_error("research_object", request.research_object_id)
    if scheme_snapshot.goal_id != goal.goal_id:
        raise product_error(
            ErrorCodeV1.IDENTITY_MISMATCH,
            "research scheme does not belong to the requested goal",
            resource_type="research_goal",
            resource_id=goal.goal_id,
        )
    if scheme_snapshot.confirmed_at is not None:
        raise product_error(
            ErrorCodeV1.INTEGRITY_FAILURE,
            "prepared research scheme is already confirmed",
            resource_type="research_scheme",
            resource_id=scheme_snapshot.scheme_id,
        )
    if request.research_goal != goal.goal_text:
        raise product_error(
            ErrorCodeV1.IDENTITY_MISMATCH,
            "research goal text does not match the generated goal",
            resource_type="research_goal",
            resource_id=goal.goal_id,
        )
    if request.as_of != goal.as_of or request.preferences != goal.preferences:
        raise product_error(
            ErrorCodeV1.IDENTITY_MISMATCH,
            "research goal does not match the exact prepare request",
            resource_type="research_goal",
            resource_id=goal.goal_id,
        )


def _validate_draft_identity_closure(draft: ResearchRunDraftV1) -> None:
    if (
        draft.goal.research_object_id != draft.object_id
        or draft.scheme_snapshot.research_object_id != draft.object_id
        or draft.scheme_snapshot.goal_id != draft.goal.goal_id
    ):
        raise product_error(
            ErrorCodeV1.INTEGRITY_FAILURE,
            "stored research draft has inconsistent Object, Goal, or Scheme identity",
            resource_type="research_run_draft",
            resource_id=draft.draft_id,
        )
    if draft.scheme_snapshot.confirmed_at is not None:
        raise product_error(
            ErrorCodeV1.INTEGRITY_FAILURE,
            "stored prepare draft unexpectedly contains a confirmed scheme",
            resource_type="research_run_draft",
            resource_id=draft.draft_id,
        )


def _identity_error(resource_type: str, resource_id: str) -> ProductError:
    return product_error(
        ErrorCodeV1.IDENTITY_MISMATCH,
        "requested resource does not belong to the exact research context",
        resource_type=resource_type,
        resource_id=resource_id,
    )


def _draft_conflict(draft: ResearchRunDraftV1, reason_code: str) -> ProductError:
    return product_error(
        ErrorCodeV1.CONFLICT,
        "research draft cannot be admitted in its current state",
        resource_type="research_run_draft",
        resource_id=draft.draft_id,
        details={"reason_code": reason_code},
    )


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    _require_utc(value, field_name=field_name)
    return value.astimezone(UTC)


def _require_utc(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be an RFC3339 UTC instant")


def _require_nonblank(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value
