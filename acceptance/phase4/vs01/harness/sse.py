"""Contract-first SSE and recovery acceptance helpers for Phase 4 VS01.

This module is deliberately independent of the product implementation.  It consumes
HTTP metadata, SSE bytes, and JSON projections exactly as an external client would.
It never imports the runtime, reducer, database models, or frontend store.

Authority (revision qualified):

* ``p4-ig00-contract-freeze`` / ``764d7613...``
* ``docs/integration/FINAL_CONTRACT_FREEZE_PROMOTION.json``
* ``docs/integration/PHASE4_BACKEND_EVENT_CONTRACT_DRAFT.md``
* ``docs/integration/PHASE4_BACKEND_FINAL_FREEZE_DECISION_DRAFT.md`` §§13-14
* ``docs/integration/PHASE4_BACKEND_API_SCHEMA_DRAFT.md``
* ``docs/integration/PHASE4_BACKEND_IDENTITY_ERROR_AVAILABILITY_CONTRACT.md``
* ``docs/integration/V17_PHASE4_CONTRACT_INPUT_PACKAGE_R2.json``

The older documents retain historical ``DRAFT`` labels, but the append-only final
promotion binds their exact hashes plus the manifest addenda as the frozen contract.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections.abc import AsyncIterable, Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, TypeAlias
from urllib.parse import unquote, urlsplit

CORE_CONTRACT_VERSION = "phase4-core/v1"
EVENT_CONTRACT_VERSION = "phase4-runtime-event/v1"
PAYLOAD_SCHEMA_VERSION = 1
RUN_PROJECTION_VERSION = "phase4-run-projection/v1"
ERROR_SCHEMA_VERSION = "phase4-error/v1"
MAX_SIGNED_64 = 9_223_372_036_854_775_807

RUN_STATUS_VALUES = frozenset(
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
TASK_STATUS_VALUES = frozenset(
    {
        "CREATED",
        "WAITING",
        "READY",
        "RUNNING",
        "WAITING_FOR_CAPABILITY",
        "SELF_CORRECTING",
        "BLOCKED",
        "REVIEW",
        "COMPLETED",
        "FAILED",
        "CAPABILITY_BUILD_FAILED",
        "CANCELLED",
    }
)
REVIEW_STATUS_VALUES = frozenset({"PASS", "REVIEW", "BLOCK"})
PROOF_STATUS_VALUES = frozenset(
    {
        "NOT_REQUIRED",
        "REQUIRED_PENDING",
        "PENDING",
        "PROVING",
        "VALID",
        "VERIFIED",
        "INVALID",
        "FAILED",
        "ERROR",
        "UNSUPPORTED",
        "NOT_IMPLEMENTED",
    }
)
CONNECTION_STATE_VALUES = frozenset(
    {"IDLE", "CONNECTING", "OPEN", "RECOVERING", "BACKOFF", "TERMINAL", "FAILED"}
)
PATH_CHANGE_VALUES = frozenset({"SELF_CORRECTION", "ADD_TASK", "CHANGE_DEPENDENCY"})
GRAPH_OPERATION_VALUES = frozenset({"add_node", "add_edge", "remove_edge"})
FAILURE_STAGE_VALUES = frozenset(
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


PATCH_PROJECTION_EVENTS = frozenset(
    {
        "run.started",
        "run.status_changed",
        "task.ready",
        "task.started",
        "task.progress",
        "task.waiting_for_capability",
        "task.resumed",
        "task.self_correcting",
        "task.completed",
        "task.failed",
    }
)
REFRESH_PROJECTION_EVENTS = frozenset(
    {
        "run.created",
        "scheme.generated",
        "scheme.confirmed",
        "plan.generated",
        "task.created",
        "task.correction_resolved",
        "replan.requested",
        "replan.approved",
        "graph.task_added",
        "graph.edge_added",
        "graph.edge_removed",
        "graph.version_changed",
        "review.started",
        "review.resolved",
        "proof.required",
        "proof.started",
        "proof.generated",
        "proof.verified",
        "proof.failed",
        "release.completed",
    }
)
OBSERVATION_ONLY_EVENTS = frozenset(
    {
        "evidence.accepted",
        "calculation.started",
        "calculation.completed",
        "capability.gap_detected",
        "capability.build_requested",
        "capability.build_started",
        "capability.generated",
        "capability.static_validated",
        "capability.sandbox_started",
        "capability.test_passed",
        "capability.test_failed",
        "capability.financial_validated",
        "capability.approved",
        "capability.registered",
        "capability.build_failed",
    }
)
TERMINAL_EVENTS = frozenset({"run.completed", "run.failed"})
UNSUPPORTED_V1_EVENTS = frozenset(
    {
        "scheme.generation_started",
        "replan.rejected",
        "evidence.conflict",
        "workspace.created",
        "capability.generation_started",
        "capability.tested",
        "capability.validated",
        "review.required",
    }
)
SUPPORTED_V1_EVENTS = frozenset(
    PATCH_PROJECTION_EVENTS | REFRESH_PROJECTION_EVENTS | OBSERVATION_ONLY_EVENTS | TERMINAL_EVENTS
)
RAW_EVENT_TYPES = frozenset(SUPPORTED_V1_EVENTS | UNSUPPORTED_V1_EVENTS)

EVENT_EFFECT: Mapping[str, str] = {
    **dict.fromkeys(PATCH_PROJECTION_EVENTS, "PATCH_PROJECTION"),
    **dict.fromkeys(REFRESH_PROJECTION_EVENTS, "REFRESH_PROJECTION"),
    **dict.fromkeys(OBSERVATION_ONLY_EVENTS, "OBSERVATION_ONLY"),
    **dict.fromkeys(TERMINAL_EVENTS, "TERMINAL"),
}


ERROR_HTTP_MAP: Mapping[str, tuple[int, bool, str]] = {
    "INVALID_CURSOR": (400, False, "SNAPSHOT_RELOAD"),
    "UNAUTHENTICATED": (401, False, "REAUTHENTICATE"),
    "FORBIDDEN": (403, False, "NONE"),
    "NOT_FOUND": (404, False, "NONE"),
    "IDENTITY_MISMATCH": (404, False, "NONE"),
    "UNAVAILABLE": (409, False, "NONE"),
    "NOT_GENERATED": (409, False, "NONE"),
    "NOT_RELEASED": (409, False, "SNAPSHOT_RELOAD"),
    "CONFLICT": (409, False, "NONE"),
    "CURSOR_AHEAD": (409, False, "SNAPSHOT_RELOAD"),
    "SCHEMA_INCOMPATIBLE": (409, False, "NONE"),
    "UNSUPPORTED_EVENT": (409, False, "SNAPSHOT_RELOAD"),
    "TERMINAL": (409, False, "NONE"),
    "REQUEST_VALIDATION_ERROR": (422, False, "NONE"),
    "INTEGRITY_FAILURE": (500, False, "SNAPSHOT_RELOAD"),
    "INTERNAL_ERROR": (500, False, "NONE"),
    "TRANSIENT_BACKEND_ERROR": (503, True, "RETRY"),
}


class SSEAcceptanceError(AssertionError):
    """A stable acceptance-oracle failure, not a product exception."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        recovery: str = "SNAPSHOT_RELOAD",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.recovery = recovery
        self.details = dict(details or {})


class EventDisposition(StrEnum):
    APPLIED = "APPLIED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
    REFRESH_REQUIRED = "REFRESH_REQUIRED"
    QUARANTINED = "QUARANTINED"


class CursorDisposition(StrEnum):
    RESUME = "RESUME"
    INVALID_CURSOR = "INVALID_CURSOR"
    CURSOR_AHEAD = "CURSOR_AHEAD"


@dataclass(frozen=True, slots=True)
class SSECommentFrame:
    comments: tuple[str, ...]
    raw_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class SSEBusinessFrame:
    wire_id: str | None
    wire_event: str
    data: str
    raw_bytes: bytes
    sha256: str
    unknown_fields: tuple[str, ...] = ()


SSEFrame: TypeAlias = SSECommentFrame | SSEBusinessFrame


@dataclass(frozen=True, slots=True)
class ValidatedRuntimeEvent:
    event_contract_version: str
    event_id: str
    run_id: str
    task_id: str | None
    type: str
    timestamp: str
    sequence: int
    payload_schema_version: int
    payload: Mapping[str, Any]
    graph_version: int | None
    effect: str
    projection_refresh_required: bool
    canonical_content_sha256: str
    wire_sha256: str
    raw: Mapping[str, Any] = field(repr=False)


@dataclass(frozen=True, slots=True)
class CursorResolution:
    disposition: CursorDisposition
    sequence: int | None
    code: str | None


@dataclass(frozen=True, slots=True)
class TaskView:
    task_id: str
    run_id: str
    status: str
    dependencies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SnapshotView:
    run_id: str
    object_id: str
    projection_revision: int
    projection_sequence: int
    run_status: str
    graph_version: int | None
    planned_graph_id: str
    actual_graph_id: str | None
    tasks: tuple[TaskView, ...]
    path_changes: tuple[Mapping[str, Any], ...]
    terminal: Mapping[str, Any]
    planned_graph_sha256: str
    actual_topology_sha256: str | None
    raw: Mapping[str, Any] = field(repr=False)

    @property
    def task_ids(self) -> frozenset[str]:
        return frozenset(task.task_id for task in self.tasks)


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    disposition: EventDisposition
    event: ValidatedRuntimeEvent | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class LiveStreamObservation:
    requested_run_id: str
    requested_cursor: str | None
    status_code: int
    headers: Mapping[str, str]
    frames: tuple[SSEFrame, ...]
    events: tuple[ValidatedRuntimeEvent, ...]
    dispositions: tuple[AdmissionResult, ...]
    stream_exhausted: bool

    @property
    def business_sequences(self) -> tuple[int, ...]:
        return tuple(event.sequence for event in self.events)

    @property
    def last_sequence(self) -> int | None:
        return self.business_sequences[-1] if self.events else None


class StreamingResponseLike(Protocol):
    status_code: int
    headers: Mapping[str, str]

    def aiter_bytes(self) -> AsyncIterable[bytes]: ...


@dataclass(frozen=True, slots=True)
class _PayloadRule:
    required: frozenset[str]
    optional: frozenset[str] = frozenset()
    literals: Mapping[str, frozenset[Any]] = field(default_factory=dict)


def _rule(
    required: Iterable[str] = (),
    optional: Iterable[str] = (),
    literals: Mapping[str, Iterable[Any]] | None = None,
) -> _PayloadRule:
    return _PayloadRule(
        frozenset(required),
        frozenset(optional),
        {key: frozenset(values) for key, values in (literals or {}).items()},
    )


PAYLOAD_RULES: Mapping[str, _PayloadRule] = {
    "run.created": _rule(["object_id"]),
    "run.started": _rule(),
    "run.status_changed": _rule(["status"], literals={"status": RUN_STATUS_VALUES}),
    "run.completed": _rule(["status"], literals={"status": ["RELEASED"]}),
    "run.failed": _rule(
        ["status", "failure_stage", "failure_code"],
        ["safe_message"],
        {
            "status": ["FAILED", "CANCELLED"],
            "failure_stage": FAILURE_STAGE_VALUES,
        },
    ),
    "scheme.generated": _rule(
        ["scheme_id", "generated_by", "generated_at", "generation_stage", "retrospective"]
    ),
    "scheme.confirmed": _rule(["scheme_id"]),
    "plan.generated": _rule(["graph_id", "task_count"]),
    "task.created": _rule(["task_type"]),
    "task.ready": _rule(),
    "task.started": _rule(["attempt"]),
    "task.waiting_for_capability": _rule(["gap_id"]),
    "task.resumed": _rule(
        ["gap_id", "registration_id", "status"], literals={"status": ["RUNNING"]}
    ),
    "task.self_correcting": _rule(["problem_code"]),
    "task.correction_resolved": _rule(["correction_id"]),
    "task.completed": _rule(["attempt"], ["result_ref"]),
    "task.failed": _rule(
        ["attempt", "failure_code"],
        ["status", "retry_suppressed"],
        {"status": TASK_STATUS_VALUES},
    ),
    "replan.requested": _rule(
        ["replan_id", "decision"], literals={"decision": ["PENDING", "APPROVED", "REJECTED"]}
    ),
    "replan.approved": _rule(["replan_id", "decided_by"]),
    "graph.task_added": _rule(["replan_id"]),
    "graph.edge_added": _rule(["replan_id", "source_task_id", "target_task_id"]),
    "graph.edge_removed": _rule(["replan_id", "source_task_id", "target_task_id"]),
    "graph.version_changed": _rule(["replan_id", "version_before"]),
    "evidence.accepted": _rule(
        ["evidence_id", "field"],
        [
            "producer_task_id",
            "source_endpoint",
            "evidence_purpose",
            "evidence_category",
        ],
    ),
    "calculation.started": _rule(["capability_id"]),
    "calculation.completed": _rule(["calculation_id"], ["capability_id"]),
    "capability.gap_detected": _rule(["gap_id", "capability_id", "skill_id", "requested_by"]),
    "capability.build_requested": _rule(
        ["gap_id", "build_id", "attempt", "max_attempts", "approved_by"]
    ),
    "capability.build_started": _rule(["build_id", "attempt"]),
    "capability.generated": _rule(["build_id", "generated_capability_id", "implementation_hash"]),
    "capability.static_validated": _rule(["build_id", "implementation_hash"]),
    "capability.sandbox_started": _rule(["build_id", "implementation_hash"]),
    "capability.test_passed": _rule(["build_id", "implementation_hash"]),
    "capability.test_failed": _rule(["build_id", "attempt", "failure_code"]),
    "capability.financial_validated": _rule(["build_id", "implementation_hash"]),
    "capability.approved": _rule(["build_id", "registration_id", "approved_by", "scope"]),
    "capability.registered": _rule(
        ["registration_id", "capability_id", "capability_version", "scope"]
    ),
    "capability.build_failed": _rule(
        ["failure_code", "terminal"],
        ["gap_id", "build_id", "attempt", "max_attempts"],
    ),
    "review.started": _rule(),
    "review.resolved": _rule(["review_id", "status"], literals={"status": REVIEW_STATUS_VALUES}),
    "proof.required": _rule(["proof_id", "calculation_id", "formula_id", "policy_id"]),
    "proof.started": _rule(["proof_id", "backend"]),
    "proof.generated": _rule(["proof_id", "backend"]),
    "proof.verified": _rule(
        ["proof_id", "image_id", "receipt_hash", "journal_hash", "verified", "dev_mode"]
    ),
    "proof.failed": _rule(
        ["proof_id", "failure_code", "status"], literals={"status": PROOF_STATUS_VALUES}
    ),
    "release.completed": _rule(["canonical_record_id", "result_id"]),
}

_INTEGER_FIELDS = frozenset(
    {"attempt", "max_attempts", "task_count", "version_before", "payload_schema_version"}
)
_BOOLEAN_FIELDS = frozenset(
    {"retrospective", "retry_suppressed", "terminal", "verified", "dev_mode"}
)
_OPTIONAL_NULLABLE_FIELDS = frozenset(
    {"safe_message", "result_ref", "producer_task_id", "source_endpoint"}
)
_SENSITIVE_KEY_TOKENS = frozenset(
    {
        "authorization",
        "api_key",
        "secret",
        "bearer",
        "prompt",
        "chain_of_thought",
        "hidden_reasoning",
        "stack_trace",
        "traceback",
        "raw_provider_payload",
    }
)
_OPAQUE_CURSOR = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_CANONICAL_DECIMAL_CURSOR = re.compile(r"^(?:0|[1-9][0-9]*)$")


def _fail(
    code: str,
    message: str,
    *,
    recovery: str = "SNAPSHOT_RELOAD",
    details: Mapping[str, Any] | None = None,
) -> None:
    raise SSEAcceptanceError(code, message, recovery=recovery, details=details)


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("SCHEMA_INCOMPATIBLE", f"value is not canonical safe JSON: {exc}")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("SCHEMA_INCOMPATIBLE", f"{field_name} must be a non-empty string")
    return value


def _require_int(value: Any, field_name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail("SCHEMA_INCOMPATIBLE", f"{field_name} must be an integer >= {minimum}")
    return value


def _require_rfc3339_utc(value: Any, field_name: str) -> str:
    text = _require_nonempty_string(value, field_name)
    if "T" not in text:
        _fail("SCHEMA_INCOMPATIBLE", f"{field_name} must be an RFC 3339 UTC instant")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail("SCHEMA_INCOMPATIBLE", f"{field_name} must be an RFC 3339 UTC instant")
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        _fail("SCHEMA_INCOMPATIBLE", f"{field_name} must use UTC")
    return text


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("SCHEMA_INCOMPATIBLE", f"{field_name} must be an object")
    if not all(isinstance(key, str) for key in value):
        _fail("SCHEMA_INCOMPATIBLE", f"{field_name} keys must be strings")
    return value


def _list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("SCHEMA_INCOMPATIBLE", f"{field_name} must be an array")
    return value


def _assert_safe_payload(value: Any, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _SENSITIVE_KEY_TOKENS:
                _fail("SCHEMA_INCOMPATIBLE", f"unsafe field {path}.{key} is forbidden")
            _assert_safe_payload(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_safe_payload(child, f"{path}[{index}]")


class IncrementalSSEParser:
    """Incremental UTF-8 SSE parser that preserves exact complete-frame bytes.

    It supports LF, CRLF, CR, arbitrary chunk/UTF-8 splits, comments, named events,
    IDs, and multi-line data.  A truncated frame fails closed at ``finish``.
    """

    def __init__(self, *, max_buffer_bytes: int = 2 * 1024 * 1024) -> None:
        if max_buffer_bytes <= 0:
            raise ValueError("max_buffer_bytes must be positive")
        self._max_buffer_bytes = max_buffer_bytes
        self._buffer = bytearray()
        self._frame_raw = bytearray()
        self._data_lines: list[str] = []
        self._comments: list[str] = []
        self._wire_id: str | None = None
        self._wire_event: str | None = None
        self._unknown_fields: list[str] = []
        self._first_line = True

    def feed(self, chunk: bytes) -> list[SSEFrame]:
        if not isinstance(chunk, bytes):
            raise TypeError("SSE chunks must be bytes")
        self._buffer.extend(chunk)
        if len(self._buffer) + len(self._frame_raw) > self._max_buffer_bytes:
            _fail("SCHEMA_INCOMPATIBLE", "SSE frame exceeds acceptance buffer limit")
        frames: list[SSEFrame] = []
        while True:
            extracted = self._extract_line(final=False)
            if extracted is None:
                break
            line_bytes, raw_line = extracted
            self._frame_raw.extend(raw_line)
            try:
                line = line_bytes.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                _fail("SCHEMA_INCOMPATIBLE", f"SSE line is not valid UTF-8: {exc}")
            if self._first_line:
                line = line.removeprefix("\ufeff")
                self._first_line = False
            if line == "":
                frame = self._dispatch()
                if frame is not None:
                    frames.append(frame)
                continue
            self._consume_line(line)
        return frames

    def finish(self) -> list[SSEFrame]:
        if self._buffer:
            extracted = self._extract_line(final=True)
            assert extracted is not None
            line_bytes, raw_line = extracted
            self._frame_raw.extend(raw_line)
            try:
                line = line_bytes.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                _fail("SCHEMA_INCOMPATIBLE", f"SSE tail is not valid UTF-8: {exc}")
            if line:
                self._consume_line(line)
        if self._frame_raw or self._data_lines or self._comments:
            _fail("SCHEMA_INCOMPATIBLE", "stream ended with an incomplete SSE frame")
        return []

    def _extract_line(self, *, final: bool) -> tuple[bytes, bytes] | None:
        for index, value in enumerate(self._buffer):
            if value not in {10, 13}:
                continue
            if value == 13 and index + 1 == len(self._buffer) and not final:
                return None
            terminator_length = (
                2
                if value == 13 and index + 1 < len(self._buffer) and self._buffer[index + 1] == 10
                else 1
            )
            end = index + terminator_length
            content = bytes(self._buffer[:index])
            raw = bytes(self._buffer[:end])
            del self._buffer[:end]
            return content, raw
        if final and self._buffer:
            content = bytes(self._buffer)
            self._buffer.clear()
            return content, content
        return None

    def _consume_line(self, line: str) -> None:
        if line.startswith(":"):
            self._comments.append(line[1:])
            return
        field_name, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field_name == "data":
            self._data_lines.append(value)
        elif field_name == "event":
            self._wire_event = value
        elif field_name == "id":
            if "\x00" in value:
                _fail("SCHEMA_INCOMPATIBLE", "SSE id contains a null character")
            self._wire_id = value
        elif field_name == "retry":
            if value and not value.isdecimal():
                self._unknown_fields.append("retry")
        else:
            self._unknown_fields.append(field_name)

    def _dispatch(self) -> SSEFrame | None:
        raw = bytes(self._frame_raw)
        digest = hashlib.sha256(raw).hexdigest()
        if self._data_lines:
            frame: SSEFrame = SSEBusinessFrame(
                wire_id=self._wire_id,
                wire_event=self._wire_event or "message",
                data="\n".join(self._data_lines),
                raw_bytes=raw,
                sha256=digest,
                unknown_fields=tuple(self._unknown_fields),
            )
        elif self._comments:
            frame = SSECommentFrame(tuple(self._comments), raw, digest)
        else:
            frame = None
        self._frame_raw.clear()
        self._data_lines.clear()
        self._comments.clear()
        self._wire_id = None
        self._wire_event = None
        self._unknown_fields.clear()
        return frame


def parse_sse_bytes(chunks: Iterable[bytes]) -> tuple[SSEFrame, ...]:
    parser = IncrementalSSEParser()
    frames: list[SSEFrame] = []
    for chunk in chunks:
        frames.extend(parser.feed(chunk))
    frames.extend(parser.finish())
    return tuple(frames)


def _validate_task_progress(payload: Mapping[str, Any]) -> None:
    keys = frozenset(payload)
    progress_keys = frozenset({"progress", "progress_scale", "stage", "message_code"})
    retry_keys = frozenset({"attempt", "error_code"})
    if "progress" in payload:
        if not {"progress", "progress_scale"}.issubset(keys) or not keys <= progress_keys:
            _fail("UNSUPPORTED_EVENT", "task.progress PROGRESS payload has invalid fields")
        progress = payload["progress"]
        if isinstance(progress, bool) or not isinstance(progress, (int, float)):
            _fail("UNSUPPORTED_EVENT", "task.progress progress must be numeric")
        if not 0 <= progress <= 1:
            _fail("UNSUPPORTED_EVENT", "task.progress progress must be in 0..1")
        if payload["progress_scale"] != "RATIO_0_1":
            _fail("UNSUPPORTED_EVENT", "task.progress scale must be RATIO_0_1")
        for field_name in keys & {"stage", "message_code"}:
            _require_nonempty_string(payload[field_name], f"payload.{field_name}")
        return
    if keys != retry_keys:
        _fail("UNSUPPORTED_EVENT", "task.progress RETRY_SCHEDULED payload has invalid fields")
    _require_int(payload["attempt"], "payload.attempt", minimum=1)
    _require_nonempty_string(payload["error_code"], "payload.error_code")


def validate_event_payload(event_type: str, payload: Any, graph_version: int | None) -> None:
    payload_map = _mapping(payload, "payload")
    _assert_safe_payload(payload_map)
    if event_type == "task.progress":
        _validate_task_progress(payload_map)
        return
    rule = PAYLOAD_RULES.get(event_type)
    if rule is None:
        _fail("UNSUPPORTED_EVENT", f"{event_type} has no admitted V1 payload schema")
    keys = frozenset(payload_map)
    if not rule.required <= keys:
        _fail(
            "UNSUPPORTED_EVENT",
            f"{event_type} payload is missing {sorted(rule.required - keys)}",
        )
    allowed = rule.required | rule.optional
    if not keys <= allowed:
        _fail(
            "UNSUPPORTED_EVENT",
            f"{event_type} payload has unknown fields {sorted(keys - allowed)}",
        )
    for field_name, values in rule.literals.items():
        if field_name in payload_map and payload_map[field_name] not in values:
            _fail("UNSUPPORTED_EVENT", f"{event_type}.{field_name} has an unsupported value")
    for field_name, value in payload_map.items():
        if value is None and field_name in _OPTIONAL_NULLABLE_FIELDS:
            continue
        if field_name in _INTEGER_FIELDS:
            _require_int(value, f"payload.{field_name}", minimum=0)
        elif field_name in _BOOLEAN_FIELDS:
            if not isinstance(value, bool):
                _fail("UNSUPPORTED_EVENT", f"payload.{field_name} must be boolean")
        elif not isinstance(value, str) or not value:
            _fail("UNSUPPORTED_EVENT", f"payload.{field_name} must be a non-empty string")
    if "attempt" in payload_map:
        _require_int(payload_map["attempt"], "payload.attempt", minimum=1)
    if "max_attempts" in payload_map:
        maximum = _require_int(payload_map["max_attempts"], "payload.max_attempts", minimum=1)
        if "attempt" in payload_map and payload_map["attempt"] > maximum:
            _fail("UNSUPPORTED_EVENT", "payload.attempt exceeds payload.max_attempts")
    if "task_count" in payload_map:
        _require_int(payload_map["task_count"], "payload.task_count", minimum=0)
    if "version_before" in payload_map:
        before = _require_int(payload_map["version_before"], "payload.version_before", minimum=1)
        if graph_version is None or graph_version != before + 1:
            _fail("UNSUPPORTED_EVENT", "graph.version_changed must advance exactly one version")
    if "generated_at" in payload_map:
        _require_rfc3339_utc(payload_map["generated_at"], "payload.generated_at")
    if event_type == "run.failed" and payload_map["status"] == "CANCELLED":
        if (
            payload_map["failure_stage"] != "CANCELLATION"
            or payload_map["failure_code"] != "RUN_CANCELLED"
        ):
            _fail(
                "UNSUPPORTED_EVENT",
                "cancelled Run must use CANCELLATION/RUN_CANCELLED",
            )


def validate_runtime_event(
    frame: SSEBusinessFrame,
    *,
    expected_run_id: str,
    known_task_ids: AbstractSetLike | None = None,
) -> ValidatedRuntimeEvent:
    if frame.unknown_fields:
        _fail("SCHEMA_INCOMPATIBLE", f"unexpected SSE fields: {frame.unknown_fields}")
    try:
        raw = json.loads(frame.data)
    except json.JSONDecodeError as exc:
        _fail("SCHEMA_INCOMPATIBLE", f"SSE data is not valid JSON: {exc}")
    event = _mapping(raw, "event")
    required = frozenset(
        {
            "event_contract_version",
            "event_id",
            "run_id",
            "task_id",
            "type",
            "timestamp",
            "sequence",
            "payload_schema_version",
            "payload",
            "graph_version",
            "effect",
            "projection_refresh_required",
        }
    )
    if frozenset(event) != required:
        _fail(
            "SCHEMA_INCOMPATIBLE",
            "event envelope fields do not equal RuntimeEventNormalizedV1",
            details={
                "missing": sorted(required - frozenset(event)),
                "extra": sorted(frozenset(event) - required),
            },
        )
    if event["event_contract_version"] != EVENT_CONTRACT_VERSION:
        _fail("UNSUPPORTED_EVENT", "event contract version is not phase4-runtime-event/v1")
    event_id = _require_nonempty_string(event["event_id"], "event_id")
    run_id = _require_nonempty_string(event["run_id"], "run_id")
    if run_id != expected_run_id:
        _fail("IDENTITY_MISMATCH", "event belongs to another Run")
    task_id = event["task_id"]
    if task_id is not None:
        task_id = _require_nonempty_string(task_id, "task_id")
    event_type = _require_nonempty_string(event["type"], "type")
    if event_type not in RAW_EVENT_TYPES or event_type in UNSUPPORTED_V1_EVENTS:
        _fail("UNSUPPORTED_EVENT", f"event type is not admitted in V1: {event_type}")
    if event_type.startswith("task.") and task_id is None:
        _fail("IDENTITY_MISMATCH", f"{event_type} requires an exact task_id")
    if (
        task_id is not None
        and known_task_ids is not None
        and task_id not in known_task_ids
        and not event_type.startswith("graph.")
    ):
        _fail("IDENTITY_MISMATCH", "event Task is absent from the authoritative snapshot")
    timestamp = _require_rfc3339_utc(event["timestamp"], "timestamp")
    sequence = _require_int(event["sequence"], "sequence", minimum=1)
    if frame.wire_id != str(sequence):
        _fail("SCHEMA_INCOMPATIBLE", "wire id does not equal data.sequence")
    if frame.wire_event != event_type:
        _fail("SCHEMA_INCOMPATIBLE", "wire event does not equal data.type")
    if event["payload_schema_version"] != PAYLOAD_SCHEMA_VERSION:
        _fail("UNSUPPORTED_EVENT", "payload_schema_version is not 1")
    graph_version = event["graph_version"]
    if graph_version is not None:
        graph_version = _require_int(graph_version, "graph_version", minimum=1)
    if (event_type == "run.started" or event_type.startswith("graph.")) and graph_version is None:
        _fail("UNSUPPORTED_EVENT", f"{event_type} requires graph_version")
    expected_effect = EVENT_EFFECT[event_type]
    if event["effect"] != expected_effect:
        _fail("UNSUPPORTED_EVENT", f"{event_type} has the wrong effect")
    refresh_required = expected_effect in {"REFRESH_PROJECTION", "TERMINAL"}
    if event["projection_refresh_required"] is not refresh_required:
        _fail("UNSUPPORTED_EVENT", f"{event_type} has inconsistent refresh metadata")
    validate_event_payload(event_type, event["payload"], graph_version)
    return ValidatedRuntimeEvent(
        event_contract_version=EVENT_CONTRACT_VERSION,
        event_id=event_id,
        run_id=run_id,
        task_id=task_id,
        type=event_type,
        timestamp=timestamp,
        sequence=sequence,
        payload_schema_version=PAYLOAD_SCHEMA_VERSION,
        payload=event["payload"],
        graph_version=graph_version,
        effect=expected_effect,
        projection_refresh_required=refresh_required,
        canonical_content_sha256=canonical_sha256(event),
        wire_sha256=frame.sha256,
        raw=event,
    )


AbstractSetLike: TypeAlias = frozenset[str] | set[str] | Sequence[str]


def resolve_cursor(
    cursor: str | None,
    *,
    tail_sequence: int,
    same_run_event_ids: Mapping[str, int],
) -> CursorResolution:
    _require_int(tail_sequence, "tail_sequence", minimum=0)
    if cursor is None:
        return CursorResolution(CursorDisposition.RESUME, 0, None)
    if not isinstance(cursor, str) or cursor == "":
        return CursorResolution(CursorDisposition.INVALID_CURSOR, None, "INVALID_CURSOR")
    if _CANONICAL_DECIMAL_CURSOR.fullmatch(cursor):
        value = int(cursor)
        if value > MAX_SIGNED_64:
            return CursorResolution(CursorDisposition.INVALID_CURSOR, None, "INVALID_CURSOR")
        if value > tail_sequence:
            return CursorResolution(CursorDisposition.CURSOR_AHEAD, None, "CURSOR_AHEAD")
        return CursorResolution(CursorDisposition.RESUME, value, None)
    if cursor.isdecimal() or cursor.strip() != cursor or cursor[:1] in {"+", "-"}:
        return CursorResolution(CursorDisposition.INVALID_CURSOR, None, "INVALID_CURSOR")
    if not _OPAQUE_CURSOR.fullmatch(cursor):
        return CursorResolution(CursorDisposition.INVALID_CURSOR, None, "INVALID_CURSOR")
    sequence = same_run_event_ids.get(cursor)
    if sequence is None:
        return CursorResolution(CursorDisposition.INVALID_CURSOR, None, "INVALID_CURSOR")
    if sequence > tail_sequence:
        _fail("INTEGRITY_FAILURE", "same-Run event ID resolves beyond the durable tail")
    return CursorResolution(CursorDisposition.RESUME, sequence, None)


def _validate_operation(value: Any, index: int) -> Mapping[str, Any]:
    operation = _mapping(value, f"path_changes.operations[{index}]")
    kind = operation.get("operation")
    if kind not in GRAPH_OPERATION_VALUES:
        _fail("SCHEMA_INCOMPATIBLE", f"unsupported graph operation {kind!r}")
    required = (
        {"operation", "task_id"}
        if kind == "add_node"
        else {"operation", "task_id", "dependency_task_id"}
    )
    if set(operation) != required:
        _fail("SCHEMA_INCOMPATIBLE", f"graph operation {kind} has non-contract fields")
    for field_name in required - {"operation"}:
        _require_nonempty_string(operation[field_name], f"operation.{field_name}")
    return operation


def _task_topology(tasks: Sequence[TaskView]) -> list[dict[str, Any]]:
    return [
        {"task_id": task.task_id, "dependencies": sorted(task.dependencies)}
        for task in sorted(tasks, key=lambda item: item.task_id)
    ]


def validate_run_projection(
    raw: Any,
    *,
    expected_run_id: str | None = None,
    expected_object_id: str | None = None,
) -> SnapshotView:
    projection = _mapping(raw, "projection")
    required = frozenset(
        {
            "projection_schema_version",
            "projection_revision",
            "projection_sequence",
            "generated_at",
            "object",
            "run",
            "goal",
            "confirmed_scheme",
            "planned_graph",
            "actual_graph",
            "graph_version",
            "tasks",
            "path_changes",
            "activity",
            "lifecycle",
            "review",
            "result",
            "artifacts",
            "proof",
            "execution",
            "terminal",
        }
    )
    if frozenset(projection) != required:
        _fail("SCHEMA_INCOMPATIBLE", "projection fields do not equal AtomicRunProjectionV1")
    if projection["projection_schema_version"] != RUN_PROJECTION_VERSION:
        _fail("SCHEMA_INCOMPATIBLE", "projection schema version is unsupported")
    revision = _require_int(projection["projection_revision"], "projection_revision", minimum=1)
    sequence = _require_int(projection["projection_sequence"], "projection_sequence", minimum=0)
    _require_rfc3339_utc(projection["generated_at"], "generated_at")
    object_record = _mapping(projection["object"], "object")
    run = _mapping(projection["run"], "run")
    object_id = _require_nonempty_string(object_record.get("object_id"), "object.object_id")
    run_id = _require_nonempty_string(run.get("run_id"), "run.run_id")
    if expected_run_id is not None and run_id != expected_run_id:
        _fail("IDENTITY_MISMATCH", "snapshot belongs to another Run")
    if expected_object_id is not None and object_id != expected_object_id:
        _fail("IDENTITY_MISMATCH", "snapshot belongs to another Object")
    if run.get("research_object_id") != object_id:
        _fail("IDENTITY_MISMATCH", "Run and Object identity do not close")
    run_status = run.get("status")
    if run_status not in RUN_STATUS_VALUES:
        _fail("SCHEMA_INCOMPATIBLE", "snapshot Run status is unsupported")
    goal = _mapping(projection["goal"], "goal")
    scheme = _mapping(projection["confirmed_scheme"], "confirmed_scheme")
    if goal.get("goal_id") != run.get("goal_id") or goal.get("research_object_id") != object_id:
        _fail("IDENTITY_MISMATCH", "Goal does not close to exact Run/Object")
    if (
        scheme.get("scheme_id") != run.get("scheme_id")
        or scheme.get("research_object_id") != object_id
        or scheme.get("goal_id") != goal.get("goal_id")
    ):
        _fail("IDENTITY_MISMATCH", "Scheme does not close to exact Run/Object/Goal")
    planned = _mapping(projection["planned_graph"], "planned_graph")
    planned_graph_id = _require_nonempty_string(planned.get("graph_id"), "planned_graph.graph_id")
    if planned.get("run_id") != run_id or planned_graph_id != run.get("planned_graph_id"):
        _fail("INTEGRITY_FAILURE", "planned graph does not close to exact Run")
    actual_raw = projection["actual_graph"]
    actual: Mapping[str, Any] | None = None
    actual_graph_id: str | None = None
    graph_version = projection["graph_version"]
    if graph_version is not None:
        graph_version = _require_int(graph_version, "graph_version", minimum=1)
    if actual_raw is not None:
        actual = _mapping(actual_raw, "actual_graph")
        actual_graph_id = _require_nonempty_string(actual.get("graph_id"), "actual_graph.graph_id")
        if actual.get("run_id") != run_id or actual_graph_id != run.get("actual_graph_id"):
            _fail("INTEGRITY_FAILURE", "actual graph does not close to exact Run")
        if graph_version is None or actual.get("version") != graph_version:
            _fail("INTEGRITY_FAILURE", "actual graph version does not match projection")
    elif graph_version is not None:
        _fail("INTEGRITY_FAILURE", "graph_version exists without actual graph")
    task_records = _list(projection["tasks"], "tasks")
    tasks: list[TaskView] = []
    for index, value in enumerate(task_records):
        task = _mapping(value, f"tasks[{index}]")
        task_id = _require_nonempty_string(task.get("task_id"), f"tasks[{index}].task_id")
        task_run_id = _require_nonempty_string(task.get("run_id"), f"tasks[{index}].run_id")
        if task_run_id != run_id:
            _fail("IDENTITY_MISMATCH", f"Task {task_id} belongs to another Run")
        status = task.get("status")
        if status not in TASK_STATUS_VALUES:
            _fail("SCHEMA_INCOMPATIBLE", f"Task {task_id} has unsupported status")
        dependencies = _list(task.get("dependencies"), f"tasks[{index}].dependencies")
        if not all(isinstance(item, str) and item for item in dependencies):
            _fail("SCHEMA_INCOMPATIBLE", f"Task {task_id} dependencies are invalid")
        if len(set(dependencies)) != len(dependencies):
            _fail("INTEGRITY_FAILURE", f"Task {task_id} has duplicate dependencies")
        tasks.append(TaskView(task_id, task_run_id, status, tuple(dependencies)))
    task_ids = [task.task_id for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        _fail("INTEGRITY_FAILURE", "snapshot contains duplicate Task IDs")
    known_tasks = set(task_ids)
    unknown_dependencies = {
        dependency
        for task in tasks
        for dependency in task.dependencies
        if dependency not in known_tasks
    }
    if unknown_dependencies:
        _fail("INTEGRITY_FAILURE", "Task dependencies cross or escape the exact Run")
    if actual is not None and "tasks" in actual:
        actual_task_ids = {
            _require_nonempty_string(
                _mapping(item, "actual_graph.tasks[]").get("task_id"),
                "actual_graph.tasks[].task_id",
            )
            for item in _list(actual["tasks"], "actual_graph.tasks")
        }
        if actual_task_ids != known_tasks:
            _fail("INTEGRITY_FAILURE", "root Tasks and actual graph Tasks disagree")
    path_changes_raw = _list(projection["path_changes"], "path_changes")
    path_changes: list[Mapping[str, Any]] = []
    path_ids: set[str] = set()
    path_required = {
        "path_change_id",
        "source_kind",
        "source_id",
        "change_kind",
        "status",
        "decision",
        "reason_code",
        "task_refs",
        "operations",
        "graph_version_before",
        "graph_version_after",
        "created_at",
        "resolved_at",
    }
    for index, value in enumerate(path_changes_raw):
        change = _mapping(value, f"path_changes[{index}]")
        if set(change) != path_required:
            _fail("SCHEMA_INCOMPATIBLE", "path change fields are not the frozen exact shape")
        path_id = _require_nonempty_string(change["path_change_id"], "path_change_id")
        source_id = _require_nonempty_string(change["source_id"], "source_id")
        if path_id != source_id or path_id in path_ids:
            _fail("INTEGRITY_FAILURE", "path change identity is duplicated or not source-exact")
        path_ids.add(path_id)
        if change["source_kind"] not in {"CORRECTION", "REPLAN"}:
            _fail("SCHEMA_INCOMPATIBLE", "path change source_kind is unsupported")
        if change["change_kind"] not in PATH_CHANGE_VALUES:
            _fail("SCHEMA_INCOMPATIBLE", "path change change_kind is unsupported")
        if change["source_kind"] == "CORRECTION" and change["change_kind"] != "SELF_CORRECTION":
            _fail("INTEGRITY_FAILURE", "Correction cannot claim a Replan change kind")
        if change["source_kind"] == "REPLAN" and change["change_kind"] == "SELF_CORRECTION":
            _fail("INTEGRITY_FAILURE", "Replan cannot claim a Correction change kind")
        task_refs = _list(change["task_refs"], "path_change.task_refs")
        if not task_refs or any(task_id not in known_tasks for task_id in task_refs):
            _fail("IDENTITY_MISMATCH", "path change Task refs do not close to the Run")
        operations = _list(change["operations"], "path_change.operations")
        for operation_index, operation in enumerate(operations):
            _validate_operation(operation, operation_index)
        for version_field in ("graph_version_before", "graph_version_after"):
            version = change[version_field]
            if version is not None:
                _require_int(version, f"path_change.{version_field}", minimum=1)
        _require_rfc3339_utc(change["created_at"], "path_change.created_at")
        if change["resolved_at"] is not None:
            _require_rfc3339_utc(change["resolved_at"], "path_change.resolved_at")
        path_changes.append(change)
    terminal = _mapping(projection["terminal"], "terminal")
    terminal_required = {"is_terminal", "outcome", "event_id", "sequence"}
    if set(terminal) != terminal_required or not isinstance(terminal["is_terminal"], bool):
        _fail("SCHEMA_INCOMPATIBLE", "terminal projection has invalid fields")
    if terminal["is_terminal"]:
        if run_status not in {"RELEASED", "FAILED", "CANCELLED"}:
            _fail("INTEGRITY_FAILURE", "terminal projection has a nonterminal Run status")
        expected_outcome = {
            "RELEASED": "SUCCESS",
            "FAILED": "FAILURE",
            "CANCELLED": "CANCELLED",
        }[run_status]
        if terminal["outcome"] != expected_outcome:
            _fail("INTEGRITY_FAILURE", "terminal outcome disagrees with Run status")
        _require_nonempty_string(terminal["event_id"], "terminal.event_id")
        terminal_sequence = _require_int(terminal["sequence"], "terminal.sequence", minimum=1)
        if terminal_sequence > sequence:
            _fail("INTEGRITY_FAILURE", "terminal event is beyond the projection watermark")
    elif any(
        terminal[field_name] is not None for field_name in ("outcome", "event_id", "sequence")
    ):
        _fail("INTEGRITY_FAILURE", "nonterminal projection carries terminal metadata")
    # Reuse the HTTP projection validator for the complete frozen DTO surface
    # (object/run fields, graph edges, Task progress/parent closure, lifecycle,
    # availability summaries, activity and terminal exactness).  This module adds
    # SSE-specific recovery semantics; it must not maintain a weaker second
    # projection decoder.
    from acceptance.phase4.vs01.harness.backend import (
        ContractViolation as BackendContractViolation,
    )
    from acceptance.phase4.vs01.harness.backend import validate_atomic_run_projection

    try:
        validate_atomic_run_projection(
            dict(projection),
            expected_object_id=object_id,
            expected_goal_id=str(run.get("goal_id")),
            expected_scheme_id=str(run.get("scheme_id")),
            expected_as_of=str(run.get("as_of")),
            expected_run_id=run_id,
            expected_planned_graph_id=planned_graph_id,
            etag=f'"p4:{run_id}:{revision}:{sequence}"',
        )
    except BackendContractViolation as exc:
        _fail("SCHEMA_INCOMPATIBLE", f"projection DTO failed frozen validation: {exc}")
    return SnapshotView(
        run_id=run_id,
        object_id=object_id,
        projection_revision=revision,
        projection_sequence=sequence,
        run_status=run_status,
        graph_version=graph_version,
        planned_graph_id=planned_graph_id,
        actual_graph_id=actual_graph_id,
        tasks=tuple(tasks),
        path_changes=tuple(path_changes),
        terminal=terminal,
        planned_graph_sha256=canonical_sha256(planned),
        actual_topology_sha256=(canonical_sha256(_task_topology(tasks)) if actual else None),
        raw=projection,
    )


class SSEProjectionOracle:
    """Reference admission/recovery oracle around authoritative snapshots.

    The oracle intentionally never fabricates Tasks or graph edges from events.  It
    advances a cursor for safe patch/observation events and requires a new atomic
    projection for refresh/terminal events or any integrity failure.
    """

    def __init__(self, snapshot: Mapping[str, Any], *, expected_run_id: str | None = None) -> None:
        self.snapshot = validate_run_projection(snapshot, expected_run_id=expected_run_id)
        self.expected_run_id = self.snapshot.run_id
        self.committed_sequence = self.snapshot.projection_sequence
        self.connection_state = "TERMINAL" if self.snapshot.terminal["is_terminal"] else "OPEN"
        self._seen_by_sequence: dict[int, tuple[str, str]] = {}
        self._sequence_by_event_id: dict[str, int] = {}
        self._pending_refresh: ValidatedRuntimeEvent | None = None

    @property
    def task_ids(self) -> frozenset[str]:
        return self.snapshot.task_ids

    def admit(self, frame: SSEBusinessFrame) -> AdmissionResult:
        try:
            event = validate_runtime_event(
                frame,
                expected_run_id=self.expected_run_id,
                known_task_ids=self.task_ids,
            )
        except SSEAcceptanceError as exc:
            self.connection_state = "RECOVERING"
            return AdmissionResult(EventDisposition.QUARANTINED, None, exc.code)
        prior_sequence = self._sequence_by_event_id.get(event.event_id)
        if prior_sequence is not None and prior_sequence != event.sequence:
            self.connection_state = "RECOVERING"
            return AdmissionResult(
                EventDisposition.QUARANTINED,
                event,
                "EVENT_ID_REUSED_AT_DIFFERENT_SEQUENCE",
            )
        prior = self._seen_by_sequence.get(event.sequence)
        signature = (event.event_id, event.canonical_content_sha256)
        if event.sequence <= self.committed_sequence:
            if prior == signature:
                return AdmissionResult(EventDisposition.DUPLICATE_IGNORED, event)
            self.connection_state = "RECOVERING"
            return AdmissionResult(
                EventDisposition.QUARANTINED, event, "STALE_OR_CONFLICTING_EVENT"
            )
        if self.connection_state == "RECOVERING":
            return AdmissionResult(EventDisposition.QUARANTINED, event, "RECOVERY_REQUIRED")
        if event.sequence != self.committed_sequence + 1:
            self.connection_state = "RECOVERING"
            return AdmissionResult(EventDisposition.QUARANTINED, event, "SEQUENCE_GAP")
        self._seen_by_sequence[event.sequence] = signature
        self._sequence_by_event_id[event.event_id] = event.sequence
        if event.projection_refresh_required:
            self._pending_refresh = event
            self.connection_state = "RECOVERING"
            return AdmissionResult(EventDisposition.REFRESH_REQUIRED, event)
        self.committed_sequence = event.sequence
        return AdmissionResult(EventDisposition.APPLIED, event)

    def reconcile(self, raw_snapshot: Mapping[str, Any]) -> SnapshotView:
        candidate = validate_run_projection(raw_snapshot, expected_run_id=self.expected_run_id)
        if candidate.projection_revision < self.snapshot.projection_revision:
            _fail("INTEGRITY_FAILURE", "snapshot recovery regressed projection_revision")
        if candidate.projection_sequence < self.committed_sequence:
            _fail("INTEGRITY_FAILURE", "snapshot recovery regressed projection_sequence")
        if self._pending_refresh and candidate.projection_sequence < self._pending_refresh.sequence:
            _fail("INTEGRITY_FAILURE", "snapshot does not cover the refresh-triggering event")
        if candidate.planned_graph_sha256 != self.snapshot.planned_graph_sha256:
            _fail("INTEGRITY_FAILURE", "immutable planned graph changed during recovery")
        self.snapshot = candidate
        self.committed_sequence = candidate.projection_sequence
        self._pending_refresh = None
        self.connection_state = "TERMINAL" if candidate.terminal["is_terminal"] else "OPEN"
        return candidate


def assert_exact_run_event_url(url: str, expected_run_id: str) -> None:
    path = urlsplit(url).path.rstrip("/")
    expected = f"/api/research-runs/{expected_run_id}/events"
    if unquote(path) != expected:
        _fail("IDENTITY_MISMATCH", f"SSE URL is not the exact Run endpoint: {path}")


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value).strip() for key, value in headers.items()}


def assert_sse_success_headers(status_code: int, headers: Mapping[str, str]) -> None:
    normalized = _normalized_headers(headers)
    if status_code != 200:
        _fail("SCHEMA_INCOMPATIBLE", f"SSE response status must be 200, got {status_code}")
    if not normalized.get("content-type", "").lower().startswith("text/event-stream"):
        _fail("SCHEMA_INCOMPATIBLE", "SSE response is not text/event-stream")
    if "no-cache" not in normalized.get("cache-control", "").lower():
        _fail("SCHEMA_INCOMPATIBLE", "SSE response must be no-cache")
    if normalized.get("x-phase4-contract-version") != CORE_CONTRACT_VERSION:
        _fail("SCHEMA_INCOMPATIBLE", "SSE core contract response header is missing or wrong")
    if normalized.get("x-phase4-event-contract-version") != EVENT_CONTRACT_VERSION:
        _fail("SCHEMA_INCOMPATIBLE", "SSE event contract response header is missing or wrong")


def validate_error_envelope(
    status_code: int,
    body: Any,
    *,
    expected_code: str | None = None,
) -> Mapping[str, Any]:
    envelope = _mapping(body, "error envelope")
    if set(envelope) != {"schema_version", "error"}:
        _fail("SCHEMA_INCOMPATIBLE", "error envelope has non-contract fields", recovery="NONE")
    if envelope["schema_version"] != ERROR_SCHEMA_VERSION:
        _fail("SCHEMA_INCOMPATIBLE", "error schema version is unsupported", recovery="NONE")
    error = _mapping(envelope["error"], "error")
    required = {"code", "message", "retryable", "recovery", "request_id", "resource", "details"}
    if set(error) != required:
        _fail("SCHEMA_INCOMPATIBLE", "error object has non-contract fields", recovery="NONE")
    code = error["code"]
    if code not in ERROR_HTTP_MAP:
        _fail("SCHEMA_INCOMPATIBLE", "error code is unsupported", recovery="NONE")
    expected_http, expected_retryable, expected_recovery = ERROR_HTTP_MAP[code]
    if (status_code, error["retryable"], error["recovery"]) != (
        expected_http,
        expected_retryable,
        expected_recovery,
    ):
        _fail("SCHEMA_INCOMPATIBLE", "error HTTP/retry/recovery tuple is invalid", recovery="NONE")
    if expected_code is not None and code != expected_code:
        _fail("SCHEMA_INCOMPATIBLE", f"expected {expected_code}, got {code}", recovery="NONE")
    _require_nonempty_string(error["message"], "error.message")
    if error["request_id"] is not None:
        _require_nonempty_string(error["request_id"], "error.request_id")
    if error["resource"] is not None:
        resource = _mapping(error["resource"], "error.resource")
        if set(resource) != {"type", "id"}:
            _fail("SCHEMA_INCOMPATIBLE", "error.resource has invalid fields", recovery="NONE")
        _require_nonempty_string(resource["type"], "error.resource.type")
        _require_nonempty_string(resource["id"], "error.resource.id")
    details = _mapping(error["details"], "error.details")
    _assert_safe_payload(details, "error.details")
    return error


def assert_cursor_error_response(
    status_code: int,
    headers: Mapping[str, str],
    body: Any,
    *,
    expected_code: str,
) -> None:
    if expected_code not in {"INVALID_CURSOR", "CURSOR_AHEAD"}:
        raise ValueError("cursor error must be INVALID_CURSOR or CURSOR_AHEAD")
    normalized = _normalized_headers(headers)
    if normalized.get("content-type", "").lower().startswith("text/event-stream"):
        _fail("SCHEMA_INCOMPATIBLE", "cursor error committed SSE headers")
    validate_error_envelope(status_code, body, expected_code=expected_code)


def assert_terminal_cursor_response(
    observation: LiveStreamObservation,
    *,
    expected_sequence: int,
) -> None:
    assert_sse_success_headers(observation.status_code, observation.headers)
    headers = _normalized_headers(observation.headers)
    if headers.get("x-run-terminal", "").lower() not in {"true", "1", "yes"}:
        _fail("SCHEMA_INCOMPATIBLE", "terminal-at-cursor response lacks X-Run-Terminal")
    if headers.get("x-terminal-sequence") != str(expected_sequence):
        _fail("SCHEMA_INCOMPATIBLE", "terminal-at-cursor sequence header is wrong")
    if observation.frames or not observation.stream_exhausted:
        _fail("INTEGRITY_FAILURE", "terminal-at-cursor must close immediately with zero frames")


async def collect_live_sse(
    response: StreamingResponseLike,
    *,
    expected_run_id: str,
    requested_cursor: str | None,
    oracle: SSEProjectionOracle | None = None,
    max_frames: int | None = None,
    max_business_events: int | None = None,
    snapshot_loader: Callable[[], Mapping[str, Any] | Awaitable[Mapping[str, Any]]] | None = None,
) -> LiveStreamObservation:
    """Capture and validate a finite/caller-time-bounded live streaming response.

    The caller owns the HTTP timeout and response context.  ``max_frames`` and
    ``max_business_events`` are collection limits, not pass conditions.  The latter
    ignores comment heartbeats.  Terminal-close proof requires natural iterator
    exhaustion (``stream_exhausted`` true).
    """

    assert_sse_success_headers(response.status_code, response.headers)
    if max_frames is not None and max_frames <= 0:
        raise ValueError("max_frames must be positive")
    if max_business_events is not None and max_business_events <= 0:
        raise ValueError("max_business_events must be positive")
    parser = IncrementalSSEParser()
    frames: list[SSEFrame] = []
    events: list[ValidatedRuntimeEvent] = []
    dispositions: list[AdmissionResult] = []
    exhausted = True
    async for chunk in response.aiter_bytes():
        for frame in parser.feed(chunk):
            frames.append(frame)
            if isinstance(frame, SSEBusinessFrame):
                if oracle is None:
                    event = validate_runtime_event(frame, expected_run_id=expected_run_id)
                    result = AdmissionResult(EventDisposition.APPLIED, event)
                else:
                    result = oracle.admit(frame)
                    event = result.event
                dispositions.append(result)
                if event is not None:
                    events.append(event)
                if (
                    result.disposition
                    in {
                        EventDisposition.REFRESH_REQUIRED,
                        EventDisposition.QUARANTINED,
                    }
                    and snapshot_loader is not None
                ):
                    loaded = snapshot_loader()
                    snapshot = await loaded if inspect.isawaitable(loaded) else loaded
                    if oracle is None:
                        _fail("INTEGRITY_FAILURE", "snapshot loader requires a projection oracle")
                    oracle.reconcile(snapshot)
            if max_frames is not None and len(frames) >= max_frames:
                exhausted = False
                break
            if max_business_events is not None and len(events) >= max_business_events:
                exhausted = False
                break
        if not exhausted:
            break
    if exhausted:
        parser.finish()
    return LiveStreamObservation(
        requested_run_id=expected_run_id,
        requested_cursor=requested_cursor,
        status_code=response.status_code,
        headers=dict(response.headers),
        frames=tuple(frames),
        events=tuple(events),
        dispositions=tuple(dispositions),
        stream_exhausted=exhausted,
    )


def assert_numeric_resume(
    before_disconnect: LiveStreamObservation,
    resumed: LiveStreamObservation,
    *,
    committed_sequence: int,
    durable_tail: int,
    full_baseline: LiveStreamObservation | None = None,
) -> None:
    if resumed.requested_run_id != before_disconnect.requested_run_id:
        _fail("IDENTITY_MISMATCH", "reconnect changed Run identity")
    if resumed.requested_cursor != str(committed_sequence):
        _fail("INVALID_CURSOR", "reconnect did not use the last committed numeric cursor")
    sequences = resumed.business_sequences
    if sequences and sequences[0] != committed_sequence + 1:
        _fail("INTEGRITY_FAILURE", "numeric replay did not begin at N+1")
    if sequences and sequences != tuple(range(committed_sequence + 1, sequences[-1] + 1)):
        _fail("INTEGRITY_FAILURE", "numeric replay suffix is not contiguous")
    if resumed.stream_exhausted and sequences and sequences[-1] != durable_tail:
        _fail("INTEGRITY_FAILURE", "exhausted replay did not reach durable tail")
    if full_baseline is not None:
        assert_replay_suffix_matches_baseline(
            full_baseline,
            resumed,
            committed_sequence=committed_sequence,
        )


def _replay_identity(
    event: ValidatedRuntimeEvent,
) -> tuple[int, str, str]:
    return (
        event.sequence,
        event.event_id,
        event.canonical_content_sha256,
    )


def assert_replay_suffix_matches_baseline(
    full_baseline: LiveStreamObservation,
    observed_suffix: LiveStreamObservation,
    *,
    committed_sequence: int,
) -> None:
    """Bind a replay suffix to exact identities captured in a full-stream baseline."""

    if committed_sequence < 0:
        raise ValueError("committed_sequence must be non-negative")
    if full_baseline.requested_run_id != observed_suffix.requested_run_id:
        _fail("IDENTITY_MISMATCH", "replay and full baseline target different Runs")
    baseline_identities = tuple(_replay_identity(event) for event in full_baseline.events)
    baseline_sequences = tuple(identity[0] for identity in baseline_identities)
    if baseline_sequences and baseline_sequences != tuple(
        range(baseline_sequences[0], baseline_sequences[-1] + 1)
    ):
        _fail("INTEGRITY_FAILURE", "full replay baseline is not contiguous")
    expected = tuple(
        identity for identity in baseline_identities if identity[0] > committed_sequence
    )
    observed = tuple(_replay_identity(event) for event in observed_suffix.events)
    if expected != observed:
        _fail(
            "INTEGRITY_FAILURE",
            "replay event identity/content differs from captured baseline suffix",
        )


def assert_numeric_opaque_suffix_equal(
    numeric: LiveStreamObservation,
    opaque: LiveStreamObservation,
) -> None:
    if numeric.requested_run_id != opaque.requested_run_id:
        _fail("IDENTITY_MISMATCH", "paired cursor probes target different Runs")
    numeric_identities = tuple(_replay_identity(event) for event in numeric.events)
    opaque_identities = tuple(_replay_identity(event) for event in opaque.events)
    if numeric_identities != opaque_identities:
        _fail("INTEGRITY_FAILURE", "numeric and opaque cursors returned different suffixes")


def assert_terminal_stream(observation: LiveStreamObservation, *, outcome: str) -> None:
    if outcome not in {"SUCCESS", "FAILURE", "CANCELLED"}:
        raise ValueError("outcome must be SUCCESS, FAILURE, or CANCELLED")
    terminal = [event for event in observation.events if event.type in TERMINAL_EVENTS]
    if len(terminal) != 1 or observation.events[-1] is not terminal[0]:
        _fail("INTEGRITY_FAILURE", "stream must end with exactly one terminal business event")
    terminal_event = terminal[0]
    if outcome == "SUCCESS":
        if terminal_event.type != "run.completed":
            _fail("INTEGRITY_FAILURE", "successful stream did not end in run.completed")
        releases = [event for event in observation.events if event.type == "release.completed"]
        if len(releases) != 1 or releases[0].sequence >= terminal_event.sequence:
            _fail("INTEGRITY_FAILURE", "release.completed must precede success terminal")
    else:
        if terminal_event.type != "run.failed" or terminal_event.payload["status"] not in {
            "FAILED",
            "CANCELLED",
        }:
            _fail("INTEGRITY_FAILURE", "unsuccessful stream did not end in run.failed")
    if not observation.stream_exhausted:
        _fail("INTEGRITY_FAILURE", "terminal frame was observed without intentional stream close")


def assert_disconnect_retains_business_snapshot(
    before: Mapping[str, Any],
    retained: Mapping[str, Any],
    *,
    connection_state: str,
) -> None:
    if connection_state not in {"CONNECTING", "RECOVERING", "BACKOFF"}:
        _fail("SCHEMA_INCOMPATIBLE", "disconnect did not enter a recovery transport state")
    before_view = validate_run_projection(before)
    retained_view = validate_run_projection(retained, expected_run_id=before_view.run_id)
    if canonical_sha256(before_view.raw) != canonical_sha256(retained_view.raw):
        _fail("INTEGRITY_FAILURE", "transport disconnect changed authoritative business state")


def _read_alias(record: Mapping[str, Any], *names: str) -> Any:
    present = [name for name in names if name in record]
    if len(present) != 1:
        _fail("SCHEMA_INCOMPATIBLE", f"expected exactly one of {names}")
    return record[present[0]]


def assert_research_path_projection(
    snapshot: Mapping[str, Any],
    rendered_nodes: Sequence[Mapping[str, Any]],
) -> None:
    view = validate_run_projection(snapshot)
    rendered: dict[str, tuple[str, tuple[str, ...]]] = {}
    for index, raw_node in enumerate(rendered_nodes):
        node = _mapping(raw_node, f"rendered_nodes[{index}]")
        task_id = _require_nonempty_string(
            _read_alias(node, "task_id", "taskId"), f"rendered_nodes[{index}].task_id"
        )
        status = _read_alias(node, "status", "backend_status", "backendStatus")
        if status not in TASK_STATUS_VALUES:
            _fail("SCHEMA_INCOMPATIBLE", f"rendered Task {task_id} has unsupported status")
        dependencies = _list(
            _read_alias(node, "dependencies", "dependencyIds"),
            f"rendered_nodes[{index}].dependencies",
        )
        if task_id in rendered:
            _fail("INTEGRITY_FAILURE", f"Research Path duplicates Task {task_id}")
        rendered[task_id] = (status, tuple(dependencies))
    expected = {task.task_id: (task.status, task.dependencies) for task in view.tasks}
    if rendered != expected:
        _fail(
            "INTEGRITY_FAILURE",
            "Research Path is not an exact authoritative Task projection",
            details={"expected": expected, "actual": rendered},
        )


def _validated_events(
    events: Sequence[ValidatedRuntimeEvent],
    *,
    run_id: str,
) -> list[ValidatedRuntimeEvent]:
    result = list(events)
    if any(event.run_id != run_id for event in result):
        _fail("IDENTITY_MISMATCH", "dynamic-path events cross Run identity")
    if [event.sequence for event in result] != sorted(event.sequence for event in result):
        _fail("INTEGRITY_FAILURE", "dynamic-path event evidence is not ordered")
    return result


def assert_self_correction_same_task_same_graph(
    before: Mapping[str, Any],
    events: Sequence[ValidatedRuntimeEvent],
    after: Mapping[str, Any],
) -> None:
    initial = validate_run_projection(before)
    final = validate_run_projection(after, expected_run_id=initial.run_id)
    evidence = _validated_events(events, run_id=initial.run_id)
    started = [event for event in evidence if event.type == "task.self_correcting"]
    resolved = [event for event in evidence if event.type == "task.correction_resolved"]
    if len(started) != 1 or len(resolved) != 1:
        _fail("INTEGRITY_FAILURE", "self-correction requires one start and one resolution")
    if started[0].task_id != resolved[0].task_id or started[0].sequence >= resolved[0].sequence:
        _fail("INTEGRITY_FAILURE", "self-correction did not resolve on the same ordered Task")
    if initial.task_ids != final.task_ids:
        _fail("INTEGRITY_FAILURE", "self-correction created or removed a Task")
    if (
        initial.actual_graph_id != final.actual_graph_id
        or initial.graph_version != final.graph_version
    ):
        _fail("INTEGRITY_FAILURE", "self-correction changed graph identity/version")
    if initial.actual_topology_sha256 != final.actual_topology_sha256:
        _fail("INTEGRITY_FAILURE", "self-correction changed graph topology")
    if initial.planned_graph_sha256 != final.planned_graph_sha256:
        _fail("INTEGRITY_FAILURE", "self-correction changed the immutable planned graph")
    correction_id = resolved[0].payload["correction_id"]
    matching = [
        change
        for change in final.path_changes
        if change["source_kind"] == "CORRECTION" and change["source_id"] == correction_id
    ]
    if len(matching) != 1:
        _fail("INTEGRITY_FAILURE", "Correction is absent or duplicated in path-change history")
    change = matching[0]
    if (
        change["change_kind"] != "SELF_CORRECTION"
        or started[0].task_id not in change["task_refs"]
        or change["operations"]
        or change["graph_version_before"] is not None
        or change["graph_version_after"] is not None
    ):
        _fail("INTEGRITY_FAILURE", "Correction path change violates same-Task/same-Graph semantics")


def _apply_operations(
    initial: SnapshotView,
    operations: Sequence[Mapping[str, Any]],
) -> dict[str, set[str]]:
    topology = {task.task_id: set(task.dependencies) for task in initial.tasks}
    for index, raw_operation in enumerate(operations):
        operation = _validate_operation(raw_operation, index)
        kind = operation["operation"]
        if kind == "add_node":
            task_id = operation["task_id"]
            if task_id in topology:
                _fail("INTEGRITY_FAILURE", "replan add_node duplicates an existing Task")
            topology[task_id] = set()
        elif kind == "add_edge":
            source = operation["dependency_task_id"]
            target = operation["task_id"]
            if source not in topology or target not in topology:
                _fail("INTEGRITY_FAILURE", "replan add_edge references an unknown Task")
            topology[target].add(source)
        else:
            source = operation["dependency_task_id"]
            target = operation["task_id"]
            if target not in topology or source not in topology[target]:
                _fail("INTEGRITY_FAILURE", "replan remove_edge references a missing edge")
            topology[target].remove(source)
    return topology


def assert_controlled_replan(
    before: Mapping[str, Any],
    events: Sequence[ValidatedRuntimeEvent],
    after: Mapping[str, Any],
    *,
    expected_decision: str,
) -> None:
    if expected_decision not in {"PENDING", "REJECTED", "APPROVED"}:
        raise ValueError("expected_decision must be PENDING, REJECTED, or APPROVED")
    initial = validate_run_projection(before)
    final = validate_run_projection(after, expected_run_id=initial.run_id)
    evidence = _validated_events(events, run_id=initial.run_id)
    requested = [event for event in evidence if event.type == "replan.requested"]
    if len(requested) != 1 or requested[0].payload["decision"] != "PENDING":
        _fail("INTEGRITY_FAILURE", "Replan must begin as one pending request")
    replan_id = requested[0].payload["replan_id"]
    matching = [
        change
        for change in final.path_changes
        if change["source_kind"] == "REPLAN" and change["source_id"] == replan_id
    ]
    if len(matching) != 1 or matching[0]["decision"] != expected_decision:
        _fail("INTEGRITY_FAILURE", "Replan projection decision is absent, duplicated, or wrong")
    change = matching[0]
    if initial.planned_graph_sha256 != final.planned_graph_sha256:
        _fail("INTEGRITY_FAILURE", "Replan changed the immutable planned graph")
    graph_events = [event for event in evidence if event.type.startswith("graph.")]
    approved = [event for event in evidence if event.type == "replan.approved"]
    if expected_decision != "APPROVED":
        if approved or graph_events:
            _fail("INTEGRITY_FAILURE", "unapproved Replan emitted graph mutation evidence")
        if (
            initial.actual_graph_id != final.actual_graph_id
            or initial.graph_version != final.graph_version
            or initial.actual_topology_sha256 != final.actual_topology_sha256
            or change["operations"]
            or change["graph_version_before"] is not None
            or change["graph_version_after"] is not None
        ):
            _fail("INTEGRITY_FAILURE", "pending/rejected Replan mutated the graph")
        return
    if len(approved) != 1 or approved[0].payload["replan_id"] != replan_id:
        _fail("INTEGRITY_FAILURE", "approved Replan lacks one exact Lead approval event")
    if approved[0].sequence <= requested[0].sequence:
        _fail("INTEGRITY_FAILURE", "Replan approval did not follow its request")
    if any(event.sequence <= approved[0].sequence for event in graph_events):
        _fail("INTEGRITY_FAILURE", "graph mutation occurred before Lead approval")
    version_events = [event for event in graph_events if event.type == "graph.version_changed"]
    if len(version_events) != 1 or version_events[-1] is not graph_events[-1]:
        _fail("INTEGRITY_FAILURE", "approved Replan lacks one final graph.version_changed")
    if any(event.payload.get("replan_id") != replan_id for event in graph_events):
        _fail("IDENTITY_MISMATCH", "graph event belongs to another Replan")
    if initial.graph_version is None or final.graph_version != initial.graph_version + 1:
        _fail("INTEGRITY_FAILURE", "approved Replan did not advance graph version exactly once")
    if (
        change["graph_version_before"] != initial.graph_version
        or change["graph_version_after"] != final.graph_version
        or version_events[0].payload["version_before"] != initial.graph_version
        or version_events[0].graph_version != final.graph_version
    ):
        _fail("INTEGRITY_FAILURE", "Replan graph versions do not close")
    expected_topology = _apply_operations(initial, change["operations"])
    actual_topology = {task.task_id: set(task.dependencies) for task in final.tasks}
    if expected_topology != actual_topology:
        _fail("INTEGRITY_FAILURE", "approved operations do not equal the authoritative graph delta")
    if change["change_kind"] == "ADD_TASK" and final.task_ids <= initial.task_ids:
        _fail("INTEGRITY_FAILURE", "ADD_TASK Replan did not add an authoritative Task")


__all__ = [
    "CONNECTION_STATE_VALUES",
    "CORE_CONTRACT_VERSION",
    "CursorDisposition",
    "CursorResolution",
    "ERROR_HTTP_MAP",
    "ERROR_SCHEMA_VERSION",
    "EVENT_CONTRACT_VERSION",
    "EVENT_EFFECT",
    "FAILURE_STAGE_VALUES",
    "EventDisposition",
    "IncrementalSSEParser",
    "LiveStreamObservation",
    "PATCH_PROJECTION_EVENTS",
    "RAW_EVENT_TYPES",
    "REFRESH_PROJECTION_EVENTS",
    "RUN_PROJECTION_VERSION",
    "RUN_STATUS_VALUES",
    "SSEAcceptanceError",
    "SSEBusinessFrame",
    "SSECommentFrame",
    "SSEProjectionOracle",
    "SUPPORTED_V1_EVENTS",
    "SnapshotView",
    "TASK_STATUS_VALUES",
    "TERMINAL_EVENTS",
    "UNSUPPORTED_V1_EVENTS",
    "ValidatedRuntimeEvent",
    "assert_controlled_replan",
    "assert_cursor_error_response",
    "assert_disconnect_retains_business_snapshot",
    "assert_exact_run_event_url",
    "assert_numeric_opaque_suffix_equal",
    "assert_numeric_resume",
    "assert_replay_suffix_matches_baseline",
    "assert_research_path_projection",
    "assert_self_correction_same_task_same_graph",
    "assert_sse_success_headers",
    "assert_terminal_cursor_response",
    "assert_terminal_stream",
    "canonical_sha256",
    "collect_live_sse",
    "parse_sse_bytes",
    "resolve_cursor",
    "validate_error_envelope",
    "validate_event_payload",
    "validate_run_projection",
    "validate_runtime_event",
]
