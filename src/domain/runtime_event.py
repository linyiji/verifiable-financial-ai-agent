from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal

from pydantic import Field, model_validator

from src.domain.base import DomainModel, JsonObject, utc_now


class RuntimeEventType(StrEnum):
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_STATUS_CHANGED = "run.status_changed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    SCHEME_GENERATION_STARTED = "scheme.generation_started"
    SCHEME_GENERATED = "scheme.generated"
    SCHEME_CONFIRMED = "scheme.confirmed"
    PLAN_GENERATED = "plan.generated"
    TASK_CREATED = "task.created"
    TASK_READY = "task.ready"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_WAITING_FOR_CAPABILITY = "task.waiting_for_capability"
    TASK_RESUMED = "task.resumed"
    TASK_SELF_CORRECTING = "task.self_correcting"
    TASK_CORRECTION_RESOLVED = "task.correction_resolved"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    REPLAN_REQUESTED = "replan.requested"
    REPLAN_APPROVED = "replan.approved"
    REPLAN_REJECTED = "replan.rejected"
    GRAPH_TASK_ADDED = "graph.task_added"
    GRAPH_EDGE_ADDED = "graph.edge_added"
    GRAPH_EDGE_REMOVED = "graph.edge_removed"
    GRAPH_VERSION_CHANGED = "graph.version_changed"
    EVIDENCE_ACCEPTED = "evidence.accepted"
    EVIDENCE_CONFLICT = "evidence.conflict"
    CALCULATION_STARTED = "calculation.started"
    CALCULATION_COMPLETED = "calculation.completed"
    CAPABILITY_GAP_DETECTED = "capability.gap_detected"
    CAPABILITY_BUILD_REQUESTED = "capability.build_requested"
    CAPABILITY_BUILD_STARTED = "capability.build_started"
    CAPABILITY_GENERATED = "capability.generated"
    CAPABILITY_STATIC_VALIDATED = "capability.static_validated"
    CAPABILITY_SANDBOX_STARTED = "capability.sandbox_started"
    CAPABILITY_TEST_PASSED = "capability.test_passed"
    CAPABILITY_TEST_FAILED = "capability.test_failed"
    CAPABILITY_FINANCIAL_VALIDATED = "capability.financial_validated"
    CAPABILITY_APPROVED = "capability.approved"
    CAPABILITY_REGISTERED = "capability.registered"
    CAPABILITY_BUILD_FAILED = "capability.build_failed"
    WORKSPACE_CREATED = "workspace.created"
    CAPABILITY_GENERATION_STARTED = "capability.generation_started"
    CAPABILITY_TESTED = "capability.tested"
    CAPABILITY_VALIDATED = "capability.validated"
    REVIEW_STARTED = "review.started"
    REVIEW_REQUIRED = "review.required"
    REVIEW_RESOLVED = "review.resolved"
    PROOF_STARTED = "proof.started"
    PROOF_REQUIRED = "proof.required"
    PROOF_GENERATED = "proof.generated"
    PROOF_VERIFIED = "proof.verified"
    PROOF_FAILED = "proof.failed"
    RELEASE_COMPLETED = "release.completed"


EVENT_CONTRACT_VERSION = "phase4-runtime-event/v1"
PAYLOAD_SCHEMA_VERSION = 1


class RuntimeEventEffect(StrEnum):
    PATCH_PROJECTION = "PATCH_PROJECTION"
    REFRESH_PROJECTION = "REFRESH_PROJECTION"
    OBSERVATION_ONLY = "OBSERVATION_ONLY"
    TERMINAL = "TERMINAL"


_PATCH_TYPES = frozenset(
    {
        RuntimeEventType.RUN_STARTED,
        RuntimeEventType.RUN_STATUS_CHANGED,
        RuntimeEventType.TASK_READY,
        RuntimeEventType.TASK_STARTED,
        RuntimeEventType.TASK_PROGRESS,
        RuntimeEventType.TASK_WAITING_FOR_CAPABILITY,
        RuntimeEventType.TASK_RESUMED,
        RuntimeEventType.TASK_SELF_CORRECTING,
        RuntimeEventType.TASK_COMPLETED,
        RuntimeEventType.TASK_FAILED,
    }
)
_REFRESH_TYPES = frozenset(
    {
        RuntimeEventType.RUN_CREATED,
        RuntimeEventType.SCHEME_GENERATED,
        RuntimeEventType.SCHEME_CONFIRMED,
        RuntimeEventType.PLAN_GENERATED,
        RuntimeEventType.TASK_CREATED,
        RuntimeEventType.TASK_CORRECTION_RESOLVED,
        RuntimeEventType.REPLAN_REQUESTED,
        RuntimeEventType.REPLAN_APPROVED,
        RuntimeEventType.GRAPH_TASK_ADDED,
        RuntimeEventType.GRAPH_EDGE_ADDED,
        RuntimeEventType.GRAPH_EDGE_REMOVED,
        RuntimeEventType.GRAPH_VERSION_CHANGED,
        RuntimeEventType.REVIEW_STARTED,
        RuntimeEventType.REVIEW_RESOLVED,
        RuntimeEventType.PROOF_REQUIRED,
        RuntimeEventType.PROOF_STARTED,
        RuntimeEventType.PROOF_GENERATED,
        RuntimeEventType.PROOF_VERIFIED,
        RuntimeEventType.PROOF_FAILED,
        RuntimeEventType.RELEASE_COMPLETED,
    }
)
_OBSERVATION_TYPES = frozenset(
    {
        RuntimeEventType.EVIDENCE_ACCEPTED,
        RuntimeEventType.CALCULATION_STARTED,
        RuntimeEventType.CALCULATION_COMPLETED,
        RuntimeEventType.CAPABILITY_GAP_DETECTED,
        RuntimeEventType.CAPABILITY_BUILD_REQUESTED,
        RuntimeEventType.CAPABILITY_BUILD_STARTED,
        RuntimeEventType.CAPABILITY_GENERATED,
        RuntimeEventType.CAPABILITY_STATIC_VALIDATED,
        RuntimeEventType.CAPABILITY_SANDBOX_STARTED,
        RuntimeEventType.CAPABILITY_TEST_PASSED,
        RuntimeEventType.CAPABILITY_TEST_FAILED,
        RuntimeEventType.CAPABILITY_FINANCIAL_VALIDATED,
        RuntimeEventType.CAPABILITY_APPROVED,
        RuntimeEventType.CAPABILITY_REGISTERED,
        RuntimeEventType.CAPABILITY_BUILD_FAILED,
    }
)
_TERMINAL_TYPES = frozenset({RuntimeEventType.RUN_COMPLETED, RuntimeEventType.RUN_FAILED})

UNSUPPORTED_RUNTIME_EVENT_TYPES = frozenset(
    {
        RuntimeEventType.SCHEME_GENERATION_STARTED,
        RuntimeEventType.REPLAN_REJECTED,
        RuntimeEventType.EVIDENCE_CONFLICT,
        RuntimeEventType.WORKSPACE_CREATED,
        RuntimeEventType.CAPABILITY_GENERATION_STARTED,
        RuntimeEventType.CAPABILITY_TESTED,
        RuntimeEventType.CAPABILITY_VALIDATED,
        RuntimeEventType.REVIEW_REQUIRED,
    }
)
SUPPORTED_RUNTIME_EVENT_TYPES = frozenset(RuntimeEventType) - UNSUPPORTED_RUNTIME_EVENT_TYPES

EVENT_EFFECT_BY_TYPE: Mapping[RuntimeEventType, RuntimeEventEffect] = MappingProxyType(
    {
        **{event_type: RuntimeEventEffect.PATCH_PROJECTION for event_type in _PATCH_TYPES},
        **{event_type: RuntimeEventEffect.REFRESH_PROJECTION for event_type in _REFRESH_TYPES},
        **{event_type: RuntimeEventEffect.OBSERVATION_ONLY for event_type in _OBSERVATION_TYPES},
        **{event_type: RuntimeEventEffect.TERMINAL for event_type in _TERMINAL_TYPES},
    }
)

GRAPH_VERSION_RUNTIME_EVENT_TYPES = frozenset(
    {
        RuntimeEventType.RUN_STARTED,
        RuntimeEventType.GRAPH_TASK_ADDED,
        RuntimeEventType.GRAPH_EDGE_ADDED,
        RuntimeEventType.GRAPH_EDGE_REMOVED,
        RuntimeEventType.GRAPH_VERSION_CHANGED,
    }
)
TASK_ID_REQUIRED_RUNTIME_EVENT_TYPES = frozenset(
    event_type
    for event_type in SUPPORTED_RUNTIME_EVENT_TYPES
    if event_type.value.startswith("task.") or event_type.value.startswith("capability.")
) | frozenset(
    {
        RuntimeEventType.CALCULATION_STARTED,
        RuntimeEventType.CALCULATION_COMPLETED,
        RuntimeEventType.REPLAN_REQUESTED,
        RuntimeEventType.REPLAN_APPROVED,
        RuntimeEventType.GRAPH_TASK_ADDED,
        RuntimeEventType.GRAPH_EDGE_ADDED,
        RuntimeEventType.GRAPH_EDGE_REMOVED,
    }
)

_RUN_STATUSES = frozenset(
    {
        "DRAFT",
        "SCHEME_GENERATING",
        "AWAITING_CONFIRMATION",
        "PLANNING",
        "RUNNING",
        "REVIEW",
        "PROVING",
        "RELEASED",
        "FAILED",
        "CANCELLED",
    }
)
_NONTERMINAL_RUN_STATUSES = _RUN_STATUSES - {"RELEASED", "FAILED", "CANCELLED"}
_TASK_FAILURE_STATUSES = frozenset({"FAILED", "CAPABILITY_BUILD_FAILED", "CANCELLED"})
_REVIEW_STATUSES = frozenset({"PASS", "REVIEW", "BLOCK"})
_REPLAN_DECISIONS = frozenset({"PENDING", "APPROVED", "REJECTED"})
_CAPABILITY_SCOPES = frozenset({"TASK", "RUN"})
_PROOF_FAILURE_STATUSES = frozenset(
    {"INVALID", "FAILED", "ERROR", "UNSUPPORTED", "NOT_IMPLEMENTED"}
)
_FAILURE_STAGES = frozenset(
    {
        "PLANNING",
        "DATA_EVIDENCE",
        "TASK_EXECUTION",
        "GENERATED_CAPABILITY",
        "FINANCIAL_REVIEW",
        "PROOF",
        "ARTIFACT_GENERATION",
        "RELEASE",
        "POST_SCHEDULER",
        "PERSISTENCE",
        "CANCELLATION",
    }
)

_PayloadPredicate = Callable[[Any], bool]


def _string(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= 4096
        and not any(ord(character) < 32 for character in value)
    )


def _nullable_string(value: Any) -> bool:
    return value is None or _string(value)


def _boolean(value: Any) -> bool:
    return isinstance(value, bool)


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _nonnegative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _ratio(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def _one_of(values: frozenset[str]) -> _PayloadPredicate:
    return lambda value: isinstance(value, str) and value in values


def _literal(expected: Any) -> _PayloadPredicate:
    return lambda value: value == expected


def _utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith(("Z", "+00:00")):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == UTC.utcoffset(parsed)


_EMPTY_PAYLOAD_TYPES = frozenset(
    {RuntimeEventType.RUN_STARTED, RuntimeEventType.TASK_READY, RuntimeEventType.REVIEW_STARTED}
)

_PAYLOAD_SPECS: Mapping[
    RuntimeEventType, tuple[Mapping[str, _PayloadPredicate], Mapping[str, _PayloadPredicate]]
] = MappingProxyType(
    {
        RuntimeEventType.RUN_CREATED: ({"object_id": _string}, {}),
        RuntimeEventType.RUN_STATUS_CHANGED: ({"status": _one_of(_NONTERMINAL_RUN_STATUSES)}, {}),
        RuntimeEventType.RUN_COMPLETED: ({"status": _literal("RELEASED")}, {}),
        RuntimeEventType.RUN_FAILED: (
            {
                "status": _one_of(frozenset({"FAILED", "CANCELLED"})),
                "failure_stage": _one_of(_FAILURE_STAGES),
                "failure_code": _string,
            },
            {"safe_message": _nullable_string},
        ),
        RuntimeEventType.SCHEME_GENERATED: (
            {
                "scheme_id": _string,
                "generated_by": _string,
                "generated_at": _utc_timestamp,
                "generation_stage": _string,
                "retrospective": _boolean,
            },
            {},
        ),
        RuntimeEventType.SCHEME_CONFIRMED: ({"scheme_id": _string}, {}),
        RuntimeEventType.PLAN_GENERATED: (
            {"graph_id": _string, "task_count": _nonnegative_integer},
            {},
        ),
        RuntimeEventType.TASK_CREATED: ({"task_type": _string}, {}),
        RuntimeEventType.TASK_STARTED: ({"attempt": _positive_integer}, {}),
        RuntimeEventType.TASK_WAITING_FOR_CAPABILITY: ({"gap_id": _string}, {}),
        RuntimeEventType.TASK_RESUMED: (
            {
                "gap_id": _string,
                "registration_id": _string,
                "status": _literal("RUNNING"),
            },
            {},
        ),
        RuntimeEventType.TASK_SELF_CORRECTING: ({"problem_code": _string}, {}),
        RuntimeEventType.TASK_CORRECTION_RESOLVED: ({"correction_id": _string}, {}),
        RuntimeEventType.TASK_COMPLETED: (
            {"attempt": _positive_integer},
            {"result_ref": _nullable_string},
        ),
        RuntimeEventType.TASK_FAILED: (
            {"attempt": _positive_integer, "failure_code": _string},
            {
                "status": _one_of(_TASK_FAILURE_STATUSES),
                "retry_suppressed": _boolean,
            },
        ),
        RuntimeEventType.REPLAN_REQUESTED: (
            {"replan_id": _string, "decision": _one_of(_REPLAN_DECISIONS)},
            {},
        ),
        RuntimeEventType.REPLAN_APPROVED: (
            {"replan_id": _string, "decided_by": _string},
            {},
        ),
        RuntimeEventType.GRAPH_TASK_ADDED: ({"replan_id": _string}, {}),
        RuntimeEventType.GRAPH_EDGE_ADDED: (
            {"replan_id": _string, "source_task_id": _string, "target_task_id": _string},
            {},
        ),
        RuntimeEventType.GRAPH_EDGE_REMOVED: (
            {"replan_id": _string, "source_task_id": _string, "target_task_id": _string},
            {},
        ),
        RuntimeEventType.GRAPH_VERSION_CHANGED: (
            {"replan_id": _string, "version_before": _positive_integer},
            {},
        ),
        RuntimeEventType.EVIDENCE_ACCEPTED: (
            {"evidence_id": _string, "field": _string},
            {
                "producer_task_id": _string,
                "source_endpoint": _string,
                "evidence_purpose": _string,
                "evidence_category": _string,
            },
        ),
        RuntimeEventType.CALCULATION_STARTED: ({"capability_id": _string}, {}),
        RuntimeEventType.CALCULATION_COMPLETED: (
            {"calculation_id": _string},
            {"capability_id": _string},
        ),
        RuntimeEventType.CAPABILITY_GAP_DETECTED: (
            {
                "gap_id": _string,
                "capability_id": _string,
                "skill_id": _string,
                "requested_by": _string,
            },
            {},
        ),
        RuntimeEventType.CAPABILITY_BUILD_REQUESTED: (
            {
                "gap_id": _string,
                "build_id": _string,
                "attempt": _positive_integer,
                "max_attempts": _positive_integer,
                "approved_by": _string,
            },
            {},
        ),
        RuntimeEventType.CAPABILITY_BUILD_STARTED: (
            {"build_id": _string, "attempt": _positive_integer},
            {},
        ),
        RuntimeEventType.CAPABILITY_GENERATED: (
            {
                "build_id": _string,
                "generated_capability_id": _string,
                "implementation_hash": _string,
            },
            {},
        ),
        RuntimeEventType.CAPABILITY_STATIC_VALIDATED: (
            {"build_id": _string, "implementation_hash": _string},
            {},
        ),
        RuntimeEventType.CAPABILITY_SANDBOX_STARTED: (
            {"build_id": _string, "implementation_hash": _string},
            {},
        ),
        RuntimeEventType.CAPABILITY_TEST_PASSED: (
            {"build_id": _string, "implementation_hash": _string},
            {},
        ),
        RuntimeEventType.CAPABILITY_TEST_FAILED: (
            {"build_id": _string, "attempt": _positive_integer, "failure_code": _string},
            {},
        ),
        RuntimeEventType.CAPABILITY_FINANCIAL_VALIDATED: (
            {"build_id": _string, "implementation_hash": _string},
            {},
        ),
        RuntimeEventType.CAPABILITY_APPROVED: (
            {
                "build_id": _string,
                "registration_id": _string,
                "approved_by": _string,
                "scope": _one_of(_CAPABILITY_SCOPES),
            },
            {},
        ),
        RuntimeEventType.CAPABILITY_REGISTERED: (
            {
                "registration_id": _string,
                "capability_id": _string,
                "capability_version": _string,
                "scope": _one_of(_CAPABILITY_SCOPES),
            },
            {},
        ),
        RuntimeEventType.CAPABILITY_BUILD_FAILED: (
            {"failure_code": _string, "terminal": _boolean},
            {
                "gap_id": _string,
                "build_id": _string,
                "attempt": _positive_integer,
                "max_attempts": _positive_integer,
            },
        ),
        RuntimeEventType.REVIEW_RESOLVED: (
            {"review_id": _string, "status": _one_of(_REVIEW_STATUSES)},
            {},
        ),
        RuntimeEventType.PROOF_REQUIRED: (
            {
                "proof_id": _string,
                "calculation_id": _string,
                "formula_id": _string,
                "policy_id": _string,
            },
            {},
        ),
        RuntimeEventType.PROOF_STARTED: ({"proof_id": _string, "backend": _string}, {}),
        RuntimeEventType.PROOF_GENERATED: ({"proof_id": _string, "backend": _string}, {}),
        RuntimeEventType.PROOF_VERIFIED: (
            {
                "proof_id": _string,
                "image_id": _string,
                "receipt_hash": _string,
                "journal_hash": _string,
                "verified": _literal(True),
                "dev_mode": _boolean,
            },
            {},
        ),
        RuntimeEventType.PROOF_FAILED: (
            {
                "proof_id": _string,
                "failure_code": _string,
                "status": _one_of(_PROOF_FAILURE_STATUSES),
            },
            {},
        ),
        RuntimeEventType.RELEASE_COMPLETED: (
            {"canonical_record_id": _string, "result_id": _string},
            {},
        ),
    }
)


def validate_runtime_event_payload(
    event_type: RuntimeEventType, payload: Mapping[str, Any]
) -> None:
    """Validate the frozen V1 public payload without inventing missing values."""

    if event_type in UNSUPPORTED_RUNTIME_EVENT_TYPES:
        raise ValueError(f"unsupported Phase 4 runtime event: {event_type.value}")
    if event_type is RuntimeEventType.TASK_PROGRESS:
        _validate_task_progress_payload(payload)
        return
    if event_type in _EMPTY_PAYLOAD_TYPES:
        if payload:
            raise ValueError(f"{event_type.value} payload must be empty")
        return
    required, optional = _PAYLOAD_SPECS[event_type]
    actual = set(payload)
    missing = set(required) - actual
    unknown = actual - set(required) - set(optional)
    if missing:
        raise ValueError(f"{event_type.value} payload missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"{event_type.value} payload has unsupported fields: {sorted(unknown)}")
    for field_name, predicate in {**required, **optional}.items():
        if field_name in payload and not predicate(payload[field_name]):
            raise ValueError(f"{event_type.value} payload field is invalid: {field_name}")
    if event_type is RuntimeEventType.CAPABILITY_BUILD_REQUESTED:
        if payload["attempt"] > payload["max_attempts"]:
            raise ValueError("capability.build_requested attempt exceeds max_attempts")
    if event_type is RuntimeEventType.CAPABILITY_BUILD_FAILED:
        attempt = payload.get("attempt")
        maximum = payload.get("max_attempts")
        if attempt is not None and maximum is not None and attempt > maximum:
            raise ValueError("capability.build_failed attempt exceeds max_attempts")


def _validate_task_progress_payload(payload: Mapping[str, Any]) -> None:
    progress_fields = {"progress", "progress_scale"}
    progress_optional = {"stage", "message_code"}
    retry_fields = {"attempt", "error_code"}
    actual = set(payload)
    if progress_fields <= actual and actual <= progress_fields | progress_optional:
        if not _ratio(payload["progress"]):
            raise ValueError("task.progress progress must be a ratio in [0,1]")
        if payload["progress_scale"] != "RATIO_0_1":
            raise ValueError("task.progress progress_scale must be RATIO_0_1")
        for field_name in progress_optional & actual:
            if not _string(payload[field_name]):
                raise ValueError(f"task.progress payload field is invalid: {field_name}")
        return
    if actual == retry_fields:
        if not _positive_integer(payload["attempt"]) or not _string(payload["error_code"]):
            raise ValueError("task.progress retry payload is invalid")
        return
    raise ValueError("task.progress payload is not a frozen PROGRESS or RETRY_SCHEDULED form")


class RuntimeEvent(DomainModel):
    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    task_id: str | None = Field(default=None, min_length=1)
    type: RuntimeEventType
    timestamp: datetime = Field(default_factory=utc_now)
    sequence: int = Field(ge=1, le=9_223_372_036_854_775_807)
    payload: JsonObject = Field(default_factory=dict)


class NormalizedRuntimeEventV1(DomainModel):
    """Safe, versioned public event emitted by the Phase 4 SSE adapter."""

    event_contract_version: Literal["phase4-runtime-event/v1"] = EVENT_CONTRACT_VERSION
    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    task_id: str | None = Field(default=None, min_length=1)
    type: RuntimeEventType
    timestamp: datetime
    sequence: int = Field(ge=1, le=9_223_372_036_854_775_807)
    payload_schema_version: Literal[1] = PAYLOAD_SCHEMA_VERSION
    payload: JsonObject
    graph_version: int | None = Field(default=None, ge=1)
    effect: RuntimeEventEffect
    projection_refresh_required: bool

    @model_validator(mode="after")
    def validate_frozen_contract(self) -> NormalizedRuntimeEventV1:
        for field_name, value in (
            ("event_id", self.event_id),
            ("run_id", self.run_id),
            ("task_id", self.task_id),
        ):
            if value is not None and not _string(value):
                raise ValueError(f"{field_name} must be a safe public identifier")
        if self.type in UNSUPPORTED_RUNTIME_EVENT_TYPES:
            raise ValueError(f"unsupported Phase 4 runtime event: {self.type.value}")
        expected_effect = EVENT_EFFECT_BY_TYPE[self.type]
        if self.effect is not expected_effect:
            raise ValueError(
                f"{self.type.value} requires effect {expected_effect.value}, "
                f"got {self.effect.value}"
            )
        expected_refresh = expected_effect in {
            RuntimeEventEffect.REFRESH_PROJECTION,
            RuntimeEventEffect.TERMINAL,
        }
        if self.projection_refresh_required is not expected_refresh:
            raise ValueError("projection_refresh_required conflicts with event effect")
        if (self.graph_version is not None) != (self.type in GRAPH_VERSION_RUNTIME_EVENT_TYPES):
            requirement = "non-null" if self.type in GRAPH_VERSION_RUNTIME_EVENT_TYPES else "null"
            raise ValueError(f"{self.type.value} graph_version must be {requirement}")
        if self.type in TASK_ID_REQUIRED_RUNTIME_EVENT_TYPES and self.task_id is None:
            raise ValueError(f"{self.type.value} requires task_id")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() != UTC.utcoffset(
            self.timestamp
        ):
            raise ValueError("timestamp must be an RFC 3339 UTC instant")
        validate_runtime_event_payload(self.type, self.payload)
        return self


def normalize_runtime_event_v1(
    event: RuntimeEvent, *, graph_version: int | None = None
) -> NormalizedRuntimeEventV1:
    """Project a stored event into the redacted, frozen public V1 envelope."""

    if event.type in UNSUPPORTED_RUNTIME_EVENT_TYPES:
        raise ValueError(f"unsupported Phase 4 runtime event: {event.type.value}")
    effect = EVENT_EFFECT_BY_TYPE[event.type]
    public_payload = project_runtime_event_payload_v1(event.type, event.payload)
    return NormalizedRuntimeEventV1(
        event_id=event.event_id,
        run_id=event.run_id,
        task_id=event.task_id,
        type=event.type,
        timestamp=event.timestamp,
        sequence=event.sequence,
        payload=public_payload,
        graph_version=(
            graph_version if graph_version is not None else graph_version_from_event_v1(event)
        ),
        effect=effect,
        projection_refresh_required=effect
        in {RuntimeEventEffect.REFRESH_PROJECTION, RuntimeEventEffect.TERMINAL},
    )


def graph_version_from_event_v1(event: RuntimeEvent) -> int | None:
    """Extract only the frozen graph watermark and never expose its legacy payload key."""

    key = {
        RuntimeEventType.RUN_STARTED: "actual_graph_version",
        RuntimeEventType.GRAPH_TASK_ADDED: "graph_version",
        RuntimeEventType.GRAPH_EDGE_ADDED: "graph_version",
        RuntimeEventType.GRAPH_EDGE_REMOVED: "graph_version",
        RuntimeEventType.GRAPH_VERSION_CHANGED: "version_after",
    }.get(event.type)
    if key is None:
        return None
    value = event.payload.get(key)
    return value if _positive_integer(value) else None


def project_runtime_event_payload_v1(
    event_type: RuntimeEventType, payload: Mapping[str, Any]
) -> JsonObject:
    """Allowlist public fields and mechanically normalize legacy internal payloads."""

    if event_type in UNSUPPORTED_RUNTIME_EVENT_TYPES:
        raise ValueError(f"unsupported Phase 4 runtime event: {event_type.value}")
    if event_type in _EMPTY_PAYLOAD_TYPES:
        projected: JsonObject = {}
    elif event_type is RuntimeEventType.TASK_PROGRESS:
        if "progress" in payload:
            projected = {
                "progress": payload["progress"],
                "progress_scale": "RATIO_0_1",
            }
            for field_name in ("stage", "message_code"):
                if field_name in payload:
                    projected[field_name] = payload[field_name]
        else:
            projected = {
                field_name: payload[field_name]
                for field_name in ("attempt", "error_code")
                if field_name in payload
            }
    else:
        required, optional = _PAYLOAD_SPECS[event_type]
        allowed = set(required) | set(optional)
        projected = {
            field_name: value for field_name, value in payload.items() if field_name in allowed
        }

    # Internal exception class names, provider telemetry, prompts, source bytes,
    # commitments and locator-like result refs never cross the public stream.
    if event_type is RuntimeEventType.TASK_COMPLETED:
        projected.pop("result_ref", None)
    if event_type is RuntimeEventType.CAPABILITY_TEST_FAILED:
        projected.setdefault("failure_code", "CAPABILITY_TEST_FAILED")
    if event_type is RuntimeEventType.CAPABILITY_BUILD_FAILED:
        projected.setdefault("failure_code", "CAPABILITY_BUILD_FAILED")
    if event_type is RuntimeEventType.PROOF_FAILED:
        projected.setdefault("failure_code", "PROOF_FAILED")

    validate_runtime_event_payload(event_type, projected)
    return projected
