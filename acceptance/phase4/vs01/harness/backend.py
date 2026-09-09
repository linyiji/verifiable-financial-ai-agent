"""Black-box Phase 4 VS01 backend acceptance checks.

This module deliberately imports no product code.  Its only authority is the frozen
``phase4-core/v1`` HTTP contract, and its observations are restricted to public HTTP
responses plus restart evidence supplied by the parent orchestrator.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

CONTRACT_VERSION = "phase4-core/v1"
EVENT_CONTRACT_VERSION = "phase4-runtime-event/v1"
CONTRACT_HEADER = "X-Phase4-Contract-Version"
CONTRACT_RESPONSE_HEADER = "X-Phase4-Contract-Version"
CONTRACT_AUTHORITY_REVISION = "764d76132cfac13d47125e031b280b7894eb249f"
CONTRACT_SET_SHA256 = "0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741"
V17_R2_CANONICAL_SHA256 = "fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19"

RUN_STAGE = {
    "DRAFT": "PREPARE",
    "SCHEME_GENERATING": "PREPARE",
    "AWAITING_CONFIRMATION": "CONFIRM",
    "PLANNING": "PLANNING",
    "RUNNING": "RESEARCH",
    "REVIEW": "REVIEW",
    "PROVING": "PROVING",
    "RELEASED": "COMPLETE",
    "FAILED": "FAILED",
    "CANCELLED": "CANCELLED",
}
TERMINAL_RUN_STATUSES = frozenset({"RELEASED", "FAILED", "CANCELLED"})
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
PROOF_POLICY_VALUES = frozenset({"NOT_REQUIRED", "MUST_PROVE", "MIXED", "UNKNOWN"})
PROOF_STATUS_VALUES = frozenset(
    {
        "NOT_REQUIRED",
        "PENDING",
        "PROVING",
        "GENERATED_UNVERIFIED",
        "VERIFIED",
        "INVALID",
        "ERROR",
        "UNSUPPORTED",
    }
)
AUTO_STARTED_RUN_STATUSES = frozenset({"RUNNING", "REVIEW", "PROVING", "RELEASED"})
AVAILABILITY_STATUSES = frozenset(
    {"PENDING", "AVAILABLE", "NOT_GENERATED", "NOT_RELEASED", "UNAVAILABLE", "FAILED"}
)
PATH_CHANGE_KINDS = frozenset({"SELF_CORRECTION", "ADD_TASK", "CHANGE_DEPENDENCY"})
TASK_ORIGINS = frozenset({"PLAN", "REPLAN", "REVIEW_FIX"})
TASK_REQUIRED_FIELDS = frozenset(
    {
        "task_id",
        "run_id",
        "parent_task_id",
        "task_type",
        "goal",
        "assigned_agent",
        "skill_id",
        "dependencies",
        "origin",
        "reason_code",
        "status",
        "progress",
        "attempt_count",
        "task_input_evidence_ids",
        "task_output_evidence_ids",
        "evidence_acquisition_status",
        "evidence_source_coverage",
        "created_at",
    }
)
TASK_APPROVED_OPTIONAL_FIELDS = frozenset()
ACTIVITY_FIELDS = frozenset(
    {"event_id", "type", "sequence", "timestamp", "task_id", "message_code"}
)
ACTIVITY_PROJECTION_OPTIONAL_FIELDS = frozenset(
    {
        "status",
        "actor_id",
        "actor_type",
        "duration_ms",
        "input_refs",
        "output_refs",
        "evidence_refs",
        "calculation_refs",
        "claim_refs",
        "judgment_refs",
        "review_refs",
        "proof_refs",
        "artifact_refs",
        "trace_bundle_refs",
    }
)
RELEASED_RESULT_FIELDS = frozenset(
    {
        "object_id",
        "run_id",
        "released_result_id",
        "canonical_record_id",
        "released_at",
        "metrics",
        "claims",
        "material_calculation_dispositions",
        "research_source_coverage",
        "limitations",
        "availability",
    }
)
RELEASED_METRIC_FIELDS = frozenset(
    {
        "run_id", "metric_id", "name", "canonical_value", "canonical_unit",
        "display_value", "display_unit", "period", "period_basis", "actuality", "as_of",
        "currency", "formula_id", "capability_id", "calculation_id", "evidence_refs",
        "claim_refs", "proof", "method_metadata", "technical_price_basis",
        "corporate_action_status", "corporate_action_guard_refs", "limitations",
    }
)
TERMINAL_TASK_STATUSES = frozenset({"COMPLETED", "FAILED", "CAPABILITY_BUILD_FAILED", "CANCELLED"})
EVIDENCE_ACQUISITION_STATUSES = frozenset({"COMPLETED", "PARTIAL", "ENTITLEMENT_BLOCKED", "FAILED"})
FAILURE_STAGE_CODES: dict[str, frozenset[str]] = {
    "PLANNING": frozenset({"PLANNING_FAILED"}),
    "DATA_EVIDENCE": frozenset({"DATA_EVIDENCE_FAILED"}),
    "TASK_EXECUTION": frozenset({"TASK_EXECUTION_FAILED"}),
    "GENERATED_CAPABILITY": frozenset({"GENERATED_CAPABILITY_FAILED"}),
    "FINANCIAL_REVIEW": frozenset({"FINANCIAL_REVIEW_BLOCKED", "FINANCIAL_REVIEW_FAILED"}),
    "PROOF": frozenset({"PROOF_INVALID", "PROOF_FAILED"}),
    "ARTIFACT_GENERATION": frozenset({"REQUIRED_ARTIFACT_GENERATION_FAILED"}),
    "RELEASE": frozenset({"RELEASE_GATE_BLOCKED", "RELEASE_FAILED"}),
    "POST_SCHEDULER": frozenset({"POST_SCHEDULER_FAILED"}),
    "PERSISTENCE": frozenset({"PERSISTENCE_FINALIZATION_FAILED"}),
}

ERROR_TUPLES: dict[str, tuple[int, bool, str]] = {
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

CONTROL_ORDER = (
    "VS01-BE-001",
    "VS01-BE-002",
    "VS01-BE-003",
    "VS01-BE-004",
    "VS01-BE-005",
    "VS01-BE-006",
    "VS01-BE-007",
    "VS01-BE-008",
    "VS01-BE-009",
    "VS01-BE-010",
    "VS01-BE-011",
    "VS01-BE-012",
    "VS01-BE-013",
    "VS01-BE-014",
)

JsonObject = dict[str, Any]
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
FORBIDDEN_PUBLIC_KEY = re.compile(
    r"authorization|api[_-]?key|bearer|secret|prompt|chain[_-]?of[_-]?thought|"
    r"scratch[_-]?reasoning|raw[_-]?provider|filesystem[_-]?path",
    re.IGNORECASE,
)
FORBIDDEN_PUBLIC_TEXT = re.compile(
    r"(?:\bBearer\s+[A-Za-z0-9._~+\-/]+=*|\bsk-[A-Za-z0-9_-]{16,}|"
    r"postgres(?:ql)?://|(?:^|\s)/(?:Users|home)/|[A-Za-z]:\\|"
    r"chain[- ]of[- ]thought|system prompt|scratch reasoning)",
    re.IGNORECASE,
)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> JsonObject:
    result: JsonObject = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON member: {name}")
        result[name] = value
    return result


def _strict_json_loads(value: str) -> Any:
    """Decode I-JSON-compatible input and reject duplicate members/non-finite constants."""

    return json.loads(
        value,
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )


def _canonical_json_string(value: str) -> str:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ContractViolation("canonical JSON strings cannot contain lone surrogates") from exc
    escaped: list[str] = ['"']
    short_escapes = {
        "\b": "\\b",
        "\t": "\\t",
        "\n": "\\n",
        "\f": "\\f",
        "\r": "\\r",
        '"': '\\"',
        "\\": "\\\\",
    }
    for character in value:
        replacement = short_escapes.get(character)
        if replacement is not None:
            escaped.append(replacement)
        elif ord(character) < 0x20:
            escaped.append(f"\\u{ord(character):04x}")
        else:
            escaped.append(character)
    escaped.append('"')
    return "".join(escaped)


def _canonical_float(value: float) -> str:
    if not math.isfinite(value):
        raise ContractViolation("canonical JSON forbids non-finite numbers")
    if value == 0:
        return "0"
    negative = value < 0
    raw = repr(abs(value)).lower()
    if "e" in raw:
        mantissa, raw_exponent = raw.split("e", 1)
        exponent = int(raw_exponent)
    else:
        mantissa = raw
        exponent = 0
    if "." in mantissa:
        integer_part, fractional_part = mantissa.split(".", 1)
    else:
        integer_part, fractional_part = mantissa, ""
    digits = integer_part + fractional_part
    leading = len(digits) - len(digits.lstrip("0"))
    decimal_point = len(integer_part) + exponent - leading
    digits = digits[leading:].rstrip("0") or "0"
    scientific_exponent = decimal_point - 1
    if -6 <= scientific_exponent < 21:
        if decimal_point <= 0:
            rendered = "0." + ("0" * -decimal_point) + digits
        elif decimal_point >= len(digits):
            rendered = digits + ("0" * (decimal_point - len(digits)))
        else:
            rendered = f"{digits[:decimal_point]}.{digits[decimal_point:]}"
    else:
        coefficient = digits[0]
        if len(digits) > 1:
            coefficient += f".{digits[1:]}"
        sign = "+" if scientific_exponent >= 0 else ""
        rendered = f"{coefficient}e{sign}{scientific_exponent}"
    return f"-{rendered}" if negative else rendered


def _canonical_json(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _canonical_json_string(value)
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_JSON_INTEGER:
            raise ContractViolation("canonical JSON integer exceeds IEEE-754 safe range")
        return str(value)
    if isinstance(value, float):
        return _canonical_float(value)
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        try:
            names = sorted(value, key=lambda name: name.encode("utf-16-be", errors="strict"))
        except (AttributeError, UnicodeEncodeError) as exc:
            raise ContractViolation("canonical JSON object keys must be Unicode strings") from exc
        return (
            "{"
            + ",".join(
                f"{_canonical_json_string(name)}:{_canonical_json(value[name])}" for name in names
            )
            + "}"
        )
    raise ContractViolation(f"canonical JSON cannot encode {type(value).__name__}")


def draft_payload_sha256(value: Mapping[str, Any]) -> str:
    """Compute the frozen RFC 8785 immutable draft hash, excluding only draft_hash."""

    payload = dict(value)
    payload.pop("draft_hash", None)
    canonical = _canonical_json(payload).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


class ContractViolation(AssertionError):
    """An observed public response violates the frozen contract."""


class TransportUnavailable(RuntimeError):
    """The configured backend could not be reached."""


@dataclass(frozen=True)
class HttpObservation:
    """A transport-neutral HTTP observation used by live and scripted transports."""

    status_code: int
    headers: Mapping[str, str]
    body: bytes

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "headers",
            {str(name).lower(): str(value) for name, value in self.headers.items()},
        )

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())

    def json_object(self) -> JsonObject:
        try:
            decoded = self.body.decode("utf-8")
            value = _strict_json_loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ContractViolation("response is not valid UTF-8 JSON") from exc
        if not isinstance(value, dict):
            raise ContractViolation("response JSON root must be an object")
        return value


class JsonTransport(Protocol):
    """Minimal request boundary that keeps the harness independent of FastAPI internals."""

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> HttpObservation: ...


class UrllibJsonTransport:
    """Small standard-library transport for an already running integrated backend."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 10.0) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute http(s) URL")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> HttpObservation:
        if not path.startswith("/"):
            raise ValueError("request path must be absolute")
        request_headers = {"Accept": "application/json", **dict(headers or {})}
        payload: bytes | None = None
        if json_body is not None:
            payload = json.dumps(dict(json_body), ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            request_headers["Content-Type"] = "application/json; charset=utf-8"
        request = Request(
            f"{self.base_url}{path}",
            data=payload,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                return HttpObservation(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except HTTPError as exc:
            return HttpObservation(
                status_code=exc.code,
                headers=dict(exc.headers.items()),
                body=exc.read(),
            )
        except (URLError, TimeoutError, OSError) as exc:
            raise TransportUnavailable("backend transport unavailable") from exc


def _new_idempotency_key(prefix: str) -> str:
    return f"vs01-{prefix}-{secrets.token_urlsafe(24)}"


@dataclass(frozen=True)
class BackendHarnessConfig:
    """Inputs controlled by the parent isolated-environment orchestrator."""

    base_url: str
    object_request: Mapping[str, Any]
    research_goal: str
    as_of: str
    preferences: Mapping[str, Any] = field(default_factory=dict)
    object_idempotency_key: str = field(default_factory=lambda: _new_idempotency_key("object"))
    prepare_idempotency_key: str = field(default_factory=lambda: _new_idempotency_key("prepare"))
    confirm_idempotency_key: str = field(default_factory=lambda: _new_idempotency_key("confirm"))
    request_timeout_seconds: float = 10.0
    auto_start_timeout_seconds: float = 30.0
    poll_interval_seconds: float = 0.25

    def __post_init__(self) -> None:
        required = {"symbol", "company_name", "exchange", "currency"}
        missing = required - set(self.object_request)
        if missing:
            raise ValueError(f"object_request is missing fields: {sorted(missing)}")
        for name in required:
            if (
                not isinstance(self.object_request[name], str)
                or not str(self.object_request[name]).strip()
            ):
                raise ValueError(f"object_request.{name} must be a non-empty string")
        if not self.research_goal.strip():
            raise ValueError("research_goal must be non-empty")
        date.fromisoformat(self.as_of)
        for name in (
            "object_idempotency_key",
            "prepare_idempotency_key",
            "confirm_idempotency_key",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.auto_start_timeout_seconds < 0:
            raise ValueError("auto_start_timeout_seconds cannot be negative")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")


@dataclass(frozen=True)
class ObjectEvidence:
    object_id: str
    object_body: JsonObject
    initial_run_ids: tuple[str, ...]


@dataclass(frozen=True)
class DraftEvidence:
    body: JsonObject
    draft_id: str
    draft_version: int
    draft_hash: str
    goal_id: str
    scheme_id: str
    run_ids_before_confirm: tuple[str, ...]


@dataclass(frozen=True)
class AdmissionEvidence:
    response: JsonObject
    admission: JsonObject
    confirm_body: JsonObject
    run_id: str
    planned_graph_id: str
    run_ids_after_confirm: tuple[str, ...]


@dataclass(frozen=True)
class RunProjectionEvidence:
    run_detail: JsonObject
    projection: JsonObject
    etag: str


@dataclass(frozen=True)
class RestartCheckpoint:
    """In-memory continuation token; public serialization redacts idempotency keys."""

    object_id: str
    object_identity: JsonObject
    draft_id: str
    draft_version: int
    draft_hash: str
    goal_id: str
    scheme_id: str
    as_of: str
    run_id: str
    planned_graph_id: str
    admission: JsonObject
    confirm_body: JsonObject
    confirm_idempotency_key: str
    projection_revision: int
    projection_sequence: int

    def public_evidence(self) -> JsonObject:
        return {
            "object_id": self.object_id,
            "draft_id": self.draft_id,
            "draft_version": self.draft_version,
            "draft_hash": self.draft_hash,
            "goal_id": self.goal_id,
            "scheme_id": self.scheme_id,
            "as_of": self.as_of,
            "run_id": self.run_id,
            "planned_graph_id": self.planned_graph_id,
            "admission_id": self.admission["admission_id"],
            "projection_revision": self.projection_revision,
            "projection_sequence": self.projection_sequence,
            "confirm_key_sha256": hashlib.sha256(
                self.confirm_idempotency_key.encode("utf-8")
            ).hexdigest(),
        }


@dataclass(frozen=True)
class RestartEvidence:
    """Parent-owned process/storage facts that cannot be proven by an HTTP client alone."""

    process_boundary_id: str
    api_process_restarted: bool
    persistence_backend: str
    storage_preserved: bool
    restart_count: int = 1


@dataclass(frozen=True)
class ControlResult:
    control_id: str
    status: str
    summary: str
    owner_dependency: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "control_id": self.control_id,
            "status": self.status,
            "summary": self.summary,
            "owner_dependency": self.owner_dependency,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class BackendHarnessReport:
    phase: str
    controls: tuple[ControlResult, ...]
    checkpoint: RestartCheckpoint | None = None

    @property
    def passed(self) -> bool:
        return bool(self.controls) and all(control.status == "PASS" for control in self.controls)

    def to_dict(self) -> JsonObject:
        return {
            "schema_version": "phase4-vs01-backend-harness-result/v1",
            "contract_version": CONTRACT_VERSION,
            "contract_set_sha256": CONTRACT_SET_SHA256,
            "phase": self.phase,
            "status": "PASS" if self.passed else "FAIL",
            "controls": [control.to_dict() for control in self.controls],
            "restart_checkpoint": self.checkpoint.public_evidence()
            if self.checkpoint is not None
            else None,
        }


def _contract_headers(*, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {CONTRACT_HEADER: CONTRACT_VERSION}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _path_id(identifier: str) -> str:
    return quote(identifier, safe="")


def _success_json(
    observation: HttpObservation,
    *,
    allowed_statuses: frozenset[int],
) -> JsonObject:
    if observation.status_code not in allowed_statuses:
        raise ContractViolation(
            f"expected HTTP {sorted(allowed_statuses)}, observed {observation.status_code}"
        )
    media_type = (observation.header("content-type") or "").lower()
    if not media_type.startswith("application/json"):
        raise ContractViolation("successful JSON response has the wrong Content-Type")
    if observation.header(CONTRACT_RESPONSE_HEADER) != CONTRACT_VERSION:
        raise ContractViolation("successful JSON response lacks the selected contract header")
    return observation.json_object()


def _mapping(value: Any, path: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ContractViolation(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractViolation(f"{path} must be an array")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation(f"{path} must be a non-empty string")
    return value


def _integer(value: Any, path: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractViolation(f"{path} must be an integer >= {minimum}")
    return value


def _number(value: Any, path: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractViolation(f"{path} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < minimum or result > maximum:
        raise ContractViolation(f"{path} must be in {minimum}..{maximum}")
    return result


def _timestamp(value: Any, path: str) -> datetime:
    text = _text(value, path)
    if not (text.endswith("Z") or text.endswith("+00:00")):
        raise ContractViolation(f"{path} must be RFC 3339 UTC")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractViolation(f"{path} must be RFC 3339 UTC") from exc


def _sha256(value: Any, path: str) -> str:
    text = _text(value, path)
    if len(text) != 71 or not text.startswith("sha256:"):
        raise ContractViolation(f"{path} must be sha256:<64 lowercase hex>")
    digest = text[7:]
    if any(character not in "0123456789abcdef" for character in digest):
        raise ContractViolation(f"{path} must be sha256:<64 lowercase hex>")
    return text


def _string_array(value: Any, path: str) -> tuple[str, ...]:
    items = _list(value, path)
    for index, item in enumerate(items):
        _text(item, f"{path}[{index}]")
    return tuple(items)


def _expect(value: Any, expected: Any, path: str) -> None:
    if value != expected:
        raise ContractViolation(f"{path} must equal the frozen contract value")


def _absent(payload: Mapping[str, Any], names: set[str], path: str) -> None:
    present = names.intersection(payload)
    if present:
        raise ContractViolation(f"{path} contains excluded fields: {sorted(present)}")


def _exact_fields(payload: Mapping[str, Any], names: set[str], path: str) -> None:
    observed = set(payload)
    if observed != names:
        missing = sorted(names - observed)
        extra = sorted(observed - names)
        raise ContractViolation(f"{path} fields differ; missing={missing}, extra={extra}")


def _required_approved_fields(
    payload: Mapping[str, Any],
    required: frozenset[str],
    optional: frozenset[str],
    path: str,
) -> None:
    missing = sorted(required - set(payload))
    extra = sorted(set(payload) - required - optional)
    if missing or extra:
        raise ContractViolation(f"{path} fields differ; missing={missing}, extra={extra}")


def _assert_safe_public_json(value: Any, path: str) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if FORBIDDEN_PUBLIC_TEXT.search(value):
            raise ContractViolation(f"{path} contains forbidden public diagnostic content")
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise ContractViolation(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_safe_public_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for name, item in value.items():
            if FORBIDDEN_PUBLIC_KEY.search(name):
                raise ContractViolation(f"{path}.{name} is forbidden on the public surface")
            _assert_safe_public_json(item, f"{path}.{name}")
        return
    raise ContractViolation(f"{path} is not safe JSON")


def validate_availability(value: Any, path: str) -> JsonObject:
    availability = _mapping(value, path)
    _exact_fields(availability, {"status", "reason_code", "retryable"}, path)
    status = availability.get("status")
    if status not in AVAILABILITY_STATUSES:
        raise ContractViolation(f"{path}.status is unsupported")
    reason = availability.get("reason_code")
    if status == "AVAILABLE":
        if reason is not None:
            raise ContractViolation(f"{path}.reason_code must be null when AVAILABLE")
    elif not isinstance(reason, str) or not reason:
        raise ContractViolation(f"{path}.reason_code is required when not AVAILABLE")
    if not isinstance(availability.get("retryable"), bool):
        raise ContractViolation(f"{path}.retryable must be boolean")
    return availability


def validate_released_result_projection(
    body: JsonObject,
    *,
    expected_object_id: str,
    expected_run_id: str,
) -> tuple[JsonObject, ...]:
    _exact_fields(body, set(RELEASED_RESULT_FIELDS), "released result")
    _expect(body.get("object_id"), expected_object_id, "released result.object_id")
    _expect(body.get("run_id"), expected_run_id, "released result.run_id")
    _text(body.get("released_result_id"), "released result.released_result_id")
    _text(body.get("canonical_record_id"), "released result.canonical_record_id")
    _timestamp(body.get("released_at"), "released result.released_at")
    availability = validate_availability(body.get("availability"), "released result.availability")
    _expect(availability.get("status"), "AVAILABLE", "released result.availability.status")
    metrics: list[JsonObject] = []
    for index, value in enumerate(_list(body.get("metrics"), "released result.metrics")):
        path = f"released result.metrics[{index}]"
        metric = _mapping(value, path)
        _exact_fields(metric, set(RELEASED_METRIC_FIELDS), path)
        _expect(metric.get("run_id"), expected_run_id, f"{path}.run_id")
        _text(metric.get("metric_id"), f"{path}.metric_id")
        _text(metric.get("canonical_value"), f"{path}.canonical_value")
        _assert_safe_public_json(metric, path)
        metrics.append(metric)
    for name in ("claims", "material_calculation_dispositions", "limitations"):
        values = _list(body.get(name), f"released result.{name}")
        _assert_safe_public_json(values, f"released result.{name}")
    coverage = body.get("research_source_coverage")
    if coverage is not None:
        _assert_safe_public_json(
            _mapping(coverage, "released result.research_source_coverage"),
            "released result.research_source_coverage",
        )
    return tuple(metrics)


def validate_research_object_detail(
    body: JsonObject,
    *,
    expected_request: Mapping[str, Any] | None = None,
    expected_object_id: str | None = None,
) -> str:
    _exact_fields(
        body,
        {
            "object",
            "latest_released_run_id",
            "released_result_availability",
            "run_count",
            "last_activity",
            "created_at",
            "updated_at",
        },
        "object detail",
    )
    object_body = _mapping(body.get("object"), "object detail.object")
    _validate_projection_object(
        object_body,
        expected_object_id=(
            expected_object_id
            if expected_object_id is not None
            else _text(object_body.get("object_id"), "object detail.object.object_id")
        ),
    )
    object_id = _text(object_body.get("object_id"), "object detail.object.object_id")
    if expected_object_id is not None:
        _expect(object_id, expected_object_id, "object detail.object.object_id")
    created_at = _timestamp(body.get("created_at"), "object detail.created_at")
    updated_at = _timestamp(body.get("updated_at"), "object detail.updated_at")
    if updated_at < created_at:
        raise ContractViolation("object detail.updated_at precedes created_at")
    run_count = _integer(body.get("run_count"), "object detail.run_count", minimum=0)
    latest_run_id = body.get("latest_released_run_id")
    if latest_run_id is not None:
        _text(latest_run_id, "object detail.latest_released_run_id")
    availability = validate_availability(
        body.get("released_result_availability"),
        "object detail.released_result_availability",
    )
    expected_release = (
        ("NOT_RELEASED", "NO_RELEASED_RUN", False)
        if latest_run_id is None
        else ("AVAILABLE", None, False)
    )
    actual_release = (
        availability.get("status"),
        availability.get("reason_code"),
        availability.get("retryable"),
    )
    if actual_release != expected_release:
        raise ContractViolation(
            "object detail released availability does not close to latest_released_run_id"
        )
    activity = body.get("last_activity")
    if activity is not None:
        activity_body = _mapping(activity, "object detail.last_activity")
        _required_approved_fields(
            activity_body,
            ACTIVITY_FIELDS,
            ACTIVITY_PROJECTION_OPTIONAL_FIELDS,
            "object detail.last_activity",
        )
        _text(activity_body.get("event_id"), "object detail.last_activity.event_id")
        _text(activity_body.get("type"), "object detail.last_activity.type")
        _integer(activity_body.get("sequence"), "object detail.last_activity.sequence", minimum=1)
        _timestamp(activity_body.get("timestamp"), "object detail.last_activity.timestamp")
        if activity_body.get("task_id") is not None:
            _text(activity_body.get("task_id"), "object detail.last_activity.task_id")
        _text(activity_body.get("message_code"), "object detail.last_activity.message_code")
        _assert_safe_public_json(activity_body, "object detail.last_activity")
    if run_count == 0 and activity is not None:
        raise ContractViolation("object detail without Runs cannot carry last_activity")
    _absent(
        body,
        {
            "research_object_version",
            "research_view_version",
            "research_memory",
            "comparison_dataset",
            "incremental_research_seed",
        },
        "object detail",
    )
    if expected_request is not None:
        _expect(
            object_body["symbol"],
            str(expected_request["symbol"]).strip().upper(),
            "object detail.object.symbol",
        )
        for name in ("company_name", "exchange", "currency"):
            _expect(
                object_body.get(name),
                expected_request[name],
                f"object detail.object.{name}",
            )
        _expect(
            object_body.get("sector"),
            expected_request.get("sector"),
            "object detail.object.sector",
        )
    return object_id


def _validate_projection_object(body: JsonObject, *, expected_object_id: str) -> None:
    """Validate the smaller NormalizedObjectIdentity embedded in a Run projection."""

    _exact_fields(
        body,
        {
            "object_id",
            "symbol",
            "company_name",
            "object_type",
            "exchange",
            "sector",
            "currency",
            "identity_version",
        },
        "projection.object",
    )
    _expect(body.get("object_id"), expected_object_id, "projection.object.object_id")
    _expect(body.get("object_type"), "public_company", "projection.object.object_type")
    _text(body.get("symbol"), "projection.object.symbol")
    _text(body.get("company_name"), "projection.object.company_name")
    _text(body.get("exchange"), "projection.object.exchange")
    sector = body.get("sector")
    if sector is not None and (not isinstance(sector, str) or not sector.strip()):
        raise ContractViolation("projection.object.sector must be null or non-empty")
    _text(body.get("currency"), "projection.object.currency")
    _integer(body.get("identity_version"), "projection.object.identity_version", minimum=1)


def validate_run_collection(body: JsonObject, *, expected_object_id: str) -> tuple[str, ...]:
    _exact_fields(body, {"schema_version", "items", "next_cursor"}, "collection")
    _expect(body.get("schema_version"), "phase4-run-collection/v1", "collection.schema_version")
    items = _list(body.get("items"), "collection.items")
    cursor = body.get("next_cursor")
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise ContractViolation("collection.next_cursor must be null or a non-empty opaque string")
    run_ids: list[str] = []
    sort_keys: list[tuple[datetime, str]] = []
    for index, raw_item in enumerate(items):
        path = f"collection.items[{index}]"
        item = _mapping(raw_item, path)
        _exact_fields(
            item,
            {
                "run_id",
                "object",
                "status",
                "stage",
                "progress",
                "activity",
                "graph_version",
                "projection_revision",
                "projection_sequence",
                "as_of",
                "created_at",
                "updated_at",
                "started_at",
                "completed_at",
                "terminal",
                "result_availability",
            },
            path,
        )
        run_id = _text(item.get("run_id"), f"{path}.run_id")
        object_summary = _mapping(item.get("object"), f"{path}.object")
        _exact_fields(
            object_summary,
            {"object_id", "symbol", "company_name"},
            f"{path}.object",
        )
        _expect(object_summary.get("object_id"), expected_object_id, f"{path}.object.object_id")
        _text(object_summary.get("symbol"), f"{path}.object.symbol")
        _text(object_summary.get("company_name"), f"{path}.object.company_name")
        status = item.get("status")
        if status not in RUN_STAGE:
            raise ContractViolation(f"{path}.status is unsupported")
        _expect(item.get("stage"), RUN_STAGE[status], f"{path}.stage")
        progress = _mapping(item.get("progress"), f"{path}.progress")
        _exact_fields(
            progress,
            {"method", "completed_tasks", "total_tasks", "fraction"},
            f"{path}.progress",
        )
        _expect(progress.get("method"), "ACTUAL_TASK_MEAN_V1", f"{path}.progress.method")
        completed = _integer(
            progress.get("completed_tasks"), f"{path}.progress.completed_tasks", minimum=0
        )
        total = _integer(progress.get("total_tasks"), f"{path}.progress.total_tasks", minimum=0)
        if completed > total:
            raise ContractViolation(f"{path}.progress.completed_tasks exceeds total_tasks")
        fraction = _number(
            progress.get("fraction"), f"{path}.progress.fraction", minimum=0, maximum=1
        )
        graph_version = item.get("graph_version")
        if graph_version is not None:
            _integer(graph_version, f"{path}.graph_version", minimum=1)
        _integer(item.get("projection_revision"), f"{path}.projection_revision", minimum=1)
        projection_sequence = _integer(
            item.get("projection_sequence"), f"{path}.projection_sequence", minimum=0
        )
        terminal = item.get("terminal")
        if not isinstance(terminal, bool) or terminal != (status in TERMINAL_RUN_STATUSES):
            raise ContractViolation(f"{path}.terminal is inconsistent with status")
        as_of = _text(item.get("as_of"), f"{path}.as_of")
        try:
            date.fromisoformat(as_of)
        except ValueError as exc:
            raise ContractViolation(f"{path}.as_of must be an ISO date") from exc
        created_at = _timestamp(item.get("created_at"), f"{path}.created_at")
        updated_at = _timestamp(item.get("updated_at"), f"{path}.updated_at")
        if updated_at < created_at:
            raise ContractViolation(f"{path}.updated_at precedes created_at")
        started_at = item.get("started_at")
        completed_at = item.get("completed_at")
        if started_at is not None:
            started_at = _timestamp(started_at, f"{path}.started_at")
            if started_at < created_at:
                raise ContractViolation(f"{path}.started_at precedes created_at")
        if completed_at is not None:
            completed_at = _timestamp(completed_at, f"{path}.completed_at")
        if terminal != (completed_at is not None):
            raise ContractViolation(f"{path}.completed_at nullability disagrees with terminal")
        if started_at is not None and started_at > updated_at:
            raise ContractViolation(f"{path}.started_at follows updated_at")
        if completed_at is not None and (
            completed_at < (started_at or created_at) or completed_at > updated_at
        ):
            raise ContractViolation(f"{path}.completed_at is outside Run time bounds")
        activity = item.get("activity")
        if (projection_sequence == 0) != (activity is None):
            raise ContractViolation(f"{path}.activity presence disagrees with projection watermark")
        if activity is not None:
            activity_body = _mapping(activity, f"{path}.activity")
            _exact_fields(activity_body, set(ACTIVITY_FIELDS), f"{path}.activity")
            _text(activity_body.get("event_id"), f"{path}.activity.event_id")
            _text(activity_body.get("type"), f"{path}.activity.type")
            activity_sequence = _integer(
                activity_body.get("sequence"), f"{path}.activity.sequence", minimum=1
            )
            if activity_sequence != projection_sequence:
                raise ContractViolation(f"{path}.activity.sequence must equal projection watermark")
            activity_timestamp = _timestamp(
                activity_body.get("timestamp"), f"{path}.activity.timestamp"
            )
            if activity_timestamp < created_at or activity_timestamp > updated_at:
                raise ContractViolation(f"{path}.activity.timestamp is outside Run time bounds")
            if activity_body.get("task_id") is not None:
                _text(activity_body.get("task_id"), f"{path}.activity.task_id")
            _text(activity_body.get("message_code"), f"{path}.activity.message_code")
            activity_type = activity_body.get("type")
            if status == "RELEASED":
                _expect(activity_type, "run.completed", f"{path}.activity.type")
            elif status in {"FAILED", "CANCELLED"}:
                _expect(activity_type, "run.failed", f"{path}.activity.type")
            elif activity_type in {"run.completed", "run.failed"}:
                raise ContractViolation(f"{path}.activity.type contradicts nonterminal status")
            if activity_type == "run.started" and (
                status != "RUNNING" or started_at is None or activity_timestamp != started_at
            ):
                raise ContractViolation(f"{path}.activity run.started does not close to Run state")
        if status != "RELEASED" and total == 0 and fraction != 0:
            raise ContractViolation(f"{path}.progress.fraction must be zero without Tasks")
        if status in {"FAILED", "CANCELLED"} and total > 0 and completed == total and fraction != 1:
            raise ContractViolation(
                f"{path}.progress.fraction must be complete when all Tasks completed"
            )
        if not terminal and fraction == 1:
            raise ContractViolation(
                f"{path}.progress.fraction cannot be complete for nonterminal Run"
            )
        if status == "RELEASED" and fraction != 1:
            raise ContractViolation(f"{path}.progress.fraction must be complete for RELEASED Run")
        availability = validate_availability(
            item.get("result_availability"), f"{path}.result_availability"
        )
        availability_status = availability.get("status")
        if terminal and availability_status == "PENDING":
            raise ContractViolation(
                f"{path}.result_availability cannot remain PENDING when terminal"
            )
        if not terminal and availability_status != "PENDING":
            raise ContractViolation(
                f"{path}.result_availability must remain PENDING when nonterminal"
            )
        if (status == "RELEASED") != (availability_status == "AVAILABLE"):
            raise ContractViolation(
                f"{path}.result_availability must match RELEASED status exactly"
            )
        run_ids.append(run_id)
        sort_keys.append((updated_at, run_id))
    if len(run_ids) != len(set(run_ids)):
        raise ContractViolation("collection contains duplicate Run identities")
    if sort_keys != sorted(sort_keys, reverse=True):
        raise ContractViolation("collection is not stably ordered by updated_at/run_id descending")
    return tuple(run_ids)


def validate_research_run_draft(
    body: JsonObject,
    *,
    expected_object_id: str,
    expected_goal_text: str,
    expected_as_of: str,
    expected_preferences: Mapping[str, Any],
) -> DraftEvidence:
    _exact_fields(
        body,
        {
            "schema_version",
            "draft_id",
            "draft_version",
            "status",
            "preview_kind",
            "planned_graph_availability",
            "object_id",
            "goal",
            "scheme_snapshot",
            "prepare_request_hash",
            "draft_hash",
            "created_at",
            "expires_at",
        },
        "draft",
    )
    _expect(body.get("schema_version"), "phase4-run-draft/v1", "draft.schema_version")
    draft_id = _text(body.get("draft_id"), "draft.draft_id")
    draft_version = _integer(body.get("draft_version"), "draft.draft_version", minimum=1)
    _expect(body.get("status"), "AWAITING_CONFIRMATION", "draft.status")
    _expect(body.get("preview_kind"), "SCHEME_ONLY", "draft.preview_kind")
    planned = validate_availability(
        body.get("planned_graph_availability"), "draft.planned_graph_availability"
    )
    _expect(planned["status"], "NOT_GENERATED", "draft.planned_graph_availability.status")
    _expect(
        planned["reason_code"],
        "PLAN_CREATED_ON_CONFIRM",
        "draft.planned_graph_availability.reason_code",
    )
    _expect(body.get("object_id"), expected_object_id, "draft.object_id")

    goal = _mapping(body.get("goal"), "draft.goal")
    _exact_fields(
        goal,
        {
            "goal_id",
            "research_object_id",
            "goal_type",
            "goal_text",
            "as_of",
            "preferences",
            "created_at",
        },
        "draft.goal",
    )
    goal_id = _text(goal.get("goal_id"), "draft.goal.goal_id")
    _expect(goal.get("research_object_id"), expected_object_id, "draft.goal.research_object_id")
    _expect(
        goal.get("goal_type"),
        "comprehensive_equity_research",
        "draft.goal.goal_type",
    )
    _expect(goal.get("goal_text"), expected_goal_text, "draft.goal.goal_text")
    _expect(goal.get("as_of"), expected_as_of, "draft.goal.as_of")
    _expect(goal.get("preferences"), dict(expected_preferences), "draft.goal.preferences")
    _assert_safe_public_json(goal.get("preferences"), "draft.goal.preferences")
    _timestamp(goal.get("created_at"), "draft.goal.created_at")

    scheme = _mapping(body.get("scheme_snapshot"), "draft.scheme_snapshot")
    _exact_fields(
        scheme,
        {
            "scheme_id",
            "research_object_id",
            "goal_id",
            "research_scope",
            "data_requirements",
            "agent_requirements",
            "skill_requirements",
            "calculation_requirements",
            "assurance_requirements",
            "report_requirements",
            "limitations",
            "generated_by",
            "generated_model",
            "created_at",
            "confirmed_at",
        },
        "draft.scheme_snapshot",
    )
    scheme_id = _text(scheme.get("scheme_id"), "draft.scheme_snapshot.scheme_id")
    _expect(
        scheme.get("research_object_id"),
        expected_object_id,
        "draft.scheme_snapshot.research_object_id",
    )
    _expect(scheme.get("goal_id"), goal_id, "draft.scheme_snapshot.goal_id")
    for name in (
        "research_scope",
        "data_requirements",
        "agent_requirements",
        "skill_requirements",
        "calculation_requirements",
        "report_requirements",
        "limitations",
    ):
        _string_array(scheme.get(name), f"draft.scheme_snapshot.{name}")
    assurance = _mapping(
        scheme.get("assurance_requirements"), "draft.scheme_snapshot.assurance_requirements"
    )
    _assert_safe_public_json(assurance, "draft.scheme_snapshot.assurance_requirements")
    _text(scheme.get("generated_by"), "draft.scheme_snapshot.generated_by")
    generated_model = scheme.get("generated_model")
    if generated_model is not None and (
        not isinstance(generated_model, str) or not generated_model
    ):
        raise ContractViolation("draft.scheme_snapshot.generated_model must be null or non-empty")
    _timestamp(scheme.get("created_at"), "draft.scheme_snapshot.created_at")
    _expect(scheme.get("confirmed_at"), None, "draft.scheme_snapshot.confirmed_at")

    _sha256(body.get("prepare_request_hash"), "draft.prepare_request_hash")
    draft_hash = _sha256(body.get("draft_hash"), "draft.draft_hash")
    _expect(draft_hash, draft_payload_sha256(body), "draft.draft_hash")
    created_at = _timestamp(body.get("created_at"), "draft.created_at")
    expires_at = _timestamp(body.get("expires_at"), "draft.expires_at")
    if expires_at <= created_at:
        raise ContractViolation("draft.expires_at must follow draft.created_at")
    _absent(
        body,
        {"mode", "goal_template_id", "planned_graph", "tasks", "run_id"},
        "draft",
    )
    return DraftEvidence(
        body=body,
        draft_id=draft_id,
        draft_version=draft_version,
        draft_hash=draft_hash,
        goal_id=goal_id,
        scheme_id=scheme_id,
        run_ids_before_confirm=(),
    )


def validate_confirm_response(
    body: JsonObject,
    *,
    expected_draft: DraftEvidence,
    expected_object_id: str,
    expected_replayed: bool,
) -> JsonObject:
    _exact_fields(body, {"schema_version", "admission", "response_meta"}, "confirm")
    _expect(body.get("schema_version"), "phase4-confirm-response/v1", "confirm.schema_version")
    _absent(
        body,
        {
            "run_id",
            "object_id",
            "goal_id",
            "scheme_id",
            "planned_graph_id",
            "status",
            "auto_start",
            "idempotency_replayed",
        },
        "confirm",
    )
    admission = _mapping(body.get("admission"), "confirm.admission")
    _exact_fields(
        admission,
        {
            "schema_version",
            "admission_id",
            "run_id",
            "object_id",
            "draft_id",
            "draft_version",
            "draft_hash",
            "goal_id",
            "scheme_id",
            "planned_graph_id",
            "status",
            "auto_start",
            "confirmation_request_hash",
            "admitted_at",
            "projection_ref",
            "events_ref",
        },
        "confirm.admission",
    )
    _expect(
        admission.get("schema_version"),
        "phase4-run-admission/v1",
        "confirm.admission.schema_version",
    )
    _text(admission.get("admission_id"), "confirm.admission.admission_id")
    _text(admission.get("run_id"), "confirm.admission.run_id")
    _expect(admission.get("object_id"), expected_object_id, "confirm.admission.object_id")
    _expect(admission.get("draft_id"), expected_draft.draft_id, "confirm.admission.draft_id")
    _expect(
        admission.get("draft_version"),
        expected_draft.draft_version,
        "confirm.admission.draft_version",
    )
    _expect(admission.get("draft_hash"), expected_draft.draft_hash, "confirm.admission.draft_hash")
    _expect(admission.get("goal_id"), expected_draft.goal_id, "confirm.admission.goal_id")
    _expect(admission.get("scheme_id"), expected_draft.scheme_id, "confirm.admission.scheme_id")
    _text(admission.get("planned_graph_id"), "confirm.admission.planned_graph_id")
    _expect(admission.get("status"), "PLANNING", "confirm.admission.status")
    auto_start = _mapping(admission.get("auto_start"), "confirm.admission.auto_start")
    _exact_fields(auto_start, {"required", "admitted"}, "confirm.admission.auto_start")
    _expect(auto_start, {"required": True, "admitted": True}, "confirm.admission.auto_start")
    _sha256(
        admission.get("confirmation_request_hash"),
        "confirm.admission.confirmation_request_hash",
    )
    _timestamp(admission.get("admitted_at"), "confirm.admission.admitted_at")
    run_id = admission["run_id"]
    _expect(
        admission.get("projection_ref"),
        f"/api/research-runs/{run_id}/projection",
        "confirm.admission.projection_ref",
    )
    _expect(
        admission.get("events_ref"),
        f"/api/research-runs/{run_id}/events",
        "confirm.admission.events_ref",
    )
    response_meta = _mapping(body.get("response_meta"), "confirm.response_meta")
    _exact_fields(
        response_meta,
        {"schema_version", "request_id", "idempotency_replayed"},
        "confirm.response_meta",
    )
    _expect(
        response_meta.get("schema_version"),
        "phase4-response-meta/v1",
        "confirm.response_meta.schema_version",
    )
    request_id = response_meta.get("request_id")
    if request_id is not None and (not isinstance(request_id, str) or not request_id):
        raise ContractViolation("confirm.response_meta.request_id must be null or non-empty")
    _expect(
        response_meta.get("idempotency_replayed"),
        expected_replayed,
        "confirm.response_meta.idempotency_replayed",
    )
    return admission


def _validate_projection_goal(
    value: Any,
    *,
    expected_goal_id: str,
    expected_object_id: str,
    expected_as_of: str,
) -> None:
    goal = _mapping(value, "projection.goal")
    _exact_fields(
        goal,
        {
            "goal_id",
            "research_object_id",
            "goal_type",
            "goal_text",
            "as_of",
            "preferences",
            "created_at",
        },
        "projection.goal",
    )
    _expect(goal.get("goal_id"), expected_goal_id, "projection.goal.goal_id")
    _expect(
        goal.get("research_object_id"),
        expected_object_id,
        "projection.goal.research_object_id",
    )
    _expect(
        goal.get("goal_type"),
        "comprehensive_equity_research",
        "projection.goal.goal_type",
    )
    _text(goal.get("goal_text"), "projection.goal.goal_text")
    _expect(goal.get("as_of"), expected_as_of, "projection.goal.as_of")
    preferences = _mapping(goal.get("preferences"), "projection.goal.preferences")
    _assert_safe_public_json(preferences, "projection.goal.preferences")
    _timestamp(goal.get("created_at"), "projection.goal.created_at")


def _validate_projection_scheme(
    value: Any,
    *,
    expected_scheme_id: str,
    expected_goal_id: str,
    expected_object_id: str,
) -> None:
    scheme = _mapping(value, "projection.confirmed_scheme")
    _exact_fields(
        scheme,
        {
            "scheme_id",
            "research_object_id",
            "goal_id",
            "research_scope",
            "data_requirements",
            "agent_requirements",
            "skill_requirements",
            "calculation_requirements",
            "assurance_requirements",
            "report_requirements",
            "limitations",
            "generated_by",
            "generated_model",
            "created_at",
            "confirmed_at",
        },
        "projection.confirmed_scheme",
    )
    _expect(scheme.get("scheme_id"), expected_scheme_id, "projection.confirmed_scheme.scheme_id")
    _expect(
        scheme.get("research_object_id"),
        expected_object_id,
        "projection.confirmed_scheme.research_object_id",
    )
    _expect(scheme.get("goal_id"), expected_goal_id, "projection.confirmed_scheme.goal_id")
    for name in (
        "research_scope",
        "data_requirements",
        "agent_requirements",
        "skill_requirements",
        "calculation_requirements",
        "report_requirements",
        "limitations",
    ):
        _string_array(scheme.get(name), f"projection.confirmed_scheme.{name}")
    assurance = _mapping(
        scheme.get("assurance_requirements"),
        "projection.confirmed_scheme.assurance_requirements",
    )
    _assert_safe_public_json(assurance, "projection.confirmed_scheme.assurance_requirements")
    _text(scheme.get("generated_by"), "projection.confirmed_scheme.generated_by")
    generated_model = scheme.get("generated_model")
    if generated_model is not None:
        _text(generated_model, "projection.confirmed_scheme.generated_model")
    created_at = _timestamp(scheme.get("created_at"), "projection.confirmed_scheme.created_at")
    confirmed_at = _timestamp(
        scheme.get("confirmed_at"), "projection.confirmed_scheme.confirmed_at"
    )
    if confirmed_at < created_at:
        raise ContractViolation("projection.confirmed_scheme.confirmed_at precedes created_at")


def _validate_run_detail_values(
    body: JsonObject,
    *,
    object_id: str,
    goal_id: str,
    scheme_id: str,
    expected_as_of: str,
    run_id: str,
    planned_graph_id: str,
) -> None:
    _expect(body.get("run_id"), run_id, "run.run_id")
    _expect(body.get("research_object_id"), object_id, "run.research_object_id")
    _expect(body.get("goal_id"), goal_id, "run.goal_id")
    _expect(body.get("scheme_id"), scheme_id, "run.scheme_id")
    _expect(body.get("planned_graph_id"), planned_graph_id, "run.planned_graph_id")
    status = body.get("status")
    if status not in RUN_STAGE:
        raise ContractViolation("run.status is unsupported")
    _expect(body.get("stage"), RUN_STAGE[status], "run.stage")
    actual_graph_id = body.get("actual_graph_id")
    if actual_graph_id is not None:
        _text(actual_graph_id, "run.actual_graph_id")
    _text(body.get("execution_target"), "run.execution_target")
    as_of = _text(body.get("as_of"), "run.as_of")
    try:
        date.fromisoformat(as_of)
    except ValueError as exc:
        raise ContractViolation("run.as_of must be an ISO date") from exc
    _expect(as_of, expected_as_of, "run.as_of")
    created_at = _timestamp(body.get("created_at"), "run.created_at")
    updated_at = _timestamp(body.get("updated_at"), "run.updated_at")
    if updated_at < created_at:
        raise ContractViolation("run.updated_at precedes run.created_at")
    started_at = body.get("started_at")
    completed_at = body.get("completed_at")
    if started_at is not None:
        started_at = _timestamp(started_at, "run.started_at")
        if started_at < created_at or started_at > updated_at:
            raise ContractViolation("run.started_at is outside created_at..updated_at")
    if completed_at is not None:
        completed_at = _timestamp(completed_at, "run.completed_at")
        if started_at is None or completed_at < started_at or completed_at > updated_at:
            raise ContractViolation("run.completed_at is outside started_at..updated_at")
    is_terminal = status in TERMINAL_RUN_STATUSES
    if is_terminal != (completed_at is not None):
        raise ContractViolation("run.completed_at must be present exactly for terminal status")
    if status in AUTO_STARTED_RUN_STATUSES and started_at is None:
        raise ContractViolation("an auto-started Run requires run.started_at")


def validate_run_detail(
    body: JsonObject,
    *,
    object_id: str,
    goal_id: str,
    scheme_id: str,
    expected_as_of: str,
    run_id: str,
    planned_graph_id: str,
) -> None:
    """Validate the 14-field Run embedded by frozen AtomicRunProjectionV1."""

    _exact_fields(
        body,
        {
            "run_id",
            "research_object_id",
            "goal_id",
            "scheme_id",
            "status",
            "stage",
            "as_of",
            "planned_graph_id",
            "actual_graph_id",
            "execution_target",
            "created_at",
            "started_at",
            "completed_at",
            "updated_at",
        },
        "run",
    )
    _validate_run_detail_values(
        body,
        object_id=object_id,
        goal_id=goal_id,
        scheme_id=scheme_id,
        expected_as_of=expected_as_of,
        run_id=run_id,
        planned_graph_id=planned_graph_id,
    )


def validate_standalone_run_detail(
    body: JsonObject,
    *,
    object_id: str,
    goal_id: str,
    scheme_id: str,
    expected_as_of: str,
    run_id: str,
    planned_graph_id: str,
) -> tuple[int, int]:
    """Validate the public Run-detail form, including its required watermarks."""

    _exact_fields(
        body,
        {
            "run_id",
            "research_object_id",
            "goal_id",
            "scheme_id",
            "status",
            "stage",
            "as_of",
            "planned_graph_id",
            "actual_graph_id",
            "execution_target",
            "created_at",
            "started_at",
            "completed_at",
            "updated_at",
            "terminal",
            "projection_revision",
            "projection_sequence",
        },
        "standalone run",
    )
    _validate_run_detail_values(
        body,
        object_id=object_id,
        goal_id=goal_id,
        scheme_id=scheme_id,
        expected_as_of=expected_as_of,
        run_id=run_id,
        planned_graph_id=planned_graph_id,
    )
    status = body["status"]
    _expect(body.get("terminal"), status in TERMINAL_RUN_STATUSES, "standalone run.terminal")
    revision = _integer(
        body.get("projection_revision"), "standalone run.projection_revision", minimum=1
    )
    sequence = _integer(
        body.get("projection_sequence"), "standalone run.projection_sequence", minimum=0
    )
    return revision, sequence


def _validate_progress(value: Any, path: str) -> tuple[int, int, float]:
    progress = _mapping(value, path)
    _exact_fields(progress, {"method", "completed_tasks", "total_tasks", "fraction"}, path)
    _expect(progress.get("method"), "ACTUAL_TASK_MEAN_V1", f"{path}.method")
    completed = _integer(progress.get("completed_tasks"), f"{path}.completed_tasks", minimum=0)
    total = _integer(progress.get("total_tasks"), f"{path}.total_tasks", minimum=0)
    if completed > total:
        raise ContractViolation(f"{path}.completed_tasks cannot exceed total_tasks")
    fraction = _number(progress.get("fraction"), f"{path}.fraction", minimum=0, maximum=1)
    return completed, total, fraction


def _validate_task(value: Any, path: str, *, run_id: str) -> dict[str, Any]:
    task = _mapping(value, path)
    _required_approved_fields(
        task,
        TASK_REQUIRED_FIELDS,
        TASK_APPROVED_OPTIONAL_FIELDS,
        path,
    )
    task_id = _text(task.get("task_id"), f"{path}.task_id")
    _expect(task.get("run_id"), run_id, f"{path}.run_id")
    task_type = _text(task.get("task_type"), f"{path}.task_type")
    goal = _text(task.get("goal"), f"{path}.goal")
    assigned_agent = _text(task.get("assigned_agent"), f"{path}.assigned_agent")
    skill_id = _text(task.get("skill_id"), f"{path}.skill_id")
    origin = task.get("origin")
    if origin not in TASK_ORIGINS:
        raise ContractViolation(f"{path}.origin is unsupported")
    reason_code = task.get("reason_code")
    if reason_code is not None:
        _text(reason_code, f"{path}.reason_code")
    status = task.get("status")
    if status not in TASK_STATUS_VALUES:
        raise ContractViolation(f"{path}.status is unsupported")
    progress = _number(task.get("progress"), f"{path}.progress", minimum=0, maximum=1)
    dependencies = _list(task.get("dependencies"), f"{path}.dependencies")
    if not all(isinstance(item, str) and item.strip() for item in dependencies):
        raise ContractViolation(f"{path}.dependencies must contain Task IDs")
    if len(dependencies) != len(set(dependencies)) or task_id in dependencies:
        raise ContractViolation(f"{path}.dependencies are duplicated or self-referential")
    parent = task.get("parent_task_id")
    if parent is not None:
        _text(parent, f"{path}.parent_task_id")
        if parent == task_id:
            raise ContractViolation(f"{path}.parent_task_id cannot reference itself")
    normalized: dict[str, Any] = {
        "task_id": task_id,
        "run_id": run_id,
        "task_type": task_type,
        "goal": goal,
        "assigned_agent": assigned_agent,
        "skill_id": skill_id,
        "origin": origin,
        "reason_code": reason_code,
        "status": status,
        "progress": progress,
        "dependencies": tuple(dependencies),
        "parent_task_id": parent,
    }
    if "attempt_count" in task:
        normalized["attempt_count"] = _integer(
            task.get("attempt_count"), f"{path}.attempt_count", minimum=0
        )
    for name in ("task_input_evidence_ids", "task_output_evidence_ids"):
        if name in task:
            identifiers = _list(task.get(name), f"{path}.{name}")
            if not all(isinstance(item, str) and item.strip() for item in identifiers):
                raise ContractViolation(f"{path}.{name} must contain non-empty identities")
            if len(identifiers) != len(set(identifiers)):
                raise ContractViolation(f"{path}.{name} contains duplicate identities")
            normalized[name] = tuple(identifiers)
    if "evidence_acquisition_status" in task:
        evidence_status = task.get("evidence_acquisition_status")
        if evidence_status is not None and evidence_status not in EVIDENCE_ACQUISITION_STATUSES:
            raise ContractViolation(f"{path}.evidence_acquisition_status is unsupported")
        normalized["evidence_acquisition_status"] = evidence_status
    if "evidence_source_coverage" in task:
        normalized["evidence_source_coverage"] = _mapping(
            task.get("evidence_source_coverage"), f"{path}.evidence_source_coverage"
        )
    if "created_at" in task:
        normalized["created_at"] = _timestamp(task.get("created_at"), f"{path}.created_at")
    _assert_safe_public_json(task, path)
    return normalized


def _validate_task_graph_acyclic(tasks: Mapping[str, Mapping[str, Any]], path: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ContractViolation(f"{path} contains a dependency cycle")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in tasks[task_id]["dependencies"]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id)


def _validate_graph(
    value: Any,
    path: str,
    *,
    run_id: str,
) -> tuple[str, dict[str, dict[str, Any]]]:
    graph = _mapping(value, path)
    _exact_fields(graph, {"graph_id", "run_id", "version", "tasks"}, path)
    graph_id = _text(graph.get("graph_id"), f"{path}.graph_id")
    _expect(graph.get("run_id"), run_id, f"{path}.run_id")
    _integer(graph.get("version"), f"{path}.version", minimum=1)
    tasks: dict[str, dict[str, Any]] = {}
    for index, raw_task in enumerate(_list(graph.get("tasks"), f"{path}.tasks")):
        task = _validate_task(raw_task, f"{path}.tasks[{index}]", run_id=run_id)
        if task["task_id"] in tasks:
            raise ContractViolation(f"{path}.tasks contains duplicate Task identities")
        tasks[task["task_id"]] = task
    known = set(tasks)
    for task in tasks.values():
        related = set(task["dependencies"])
        if task["parent_task_id"] is not None:
            related.add(task["parent_task_id"])
        if not related <= known:
            raise ContractViolation(f"{path}.tasks references a Task outside the graph")
    _validate_task_graph_acyclic(tasks, f"{path}.tasks")
    return graph_id, tasks


def validate_atomic_run_projection(
    body: JsonObject,
    *,
    expected_object_id: str,
    expected_goal_id: str,
    expected_scheme_id: str,
    expected_as_of: str,
    expected_run_id: str,
    expected_planned_graph_id: str,
    etag: str | None,
) -> tuple[int, int, str]:
    _exact_fields(
        body,
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
        },
        "projection",
    )
    _expect(
        body.get("projection_schema_version"),
        "phase4-run-projection/v1",
        "projection.projection_schema_version",
    )
    revision = _integer(
        body.get("projection_revision"), "projection.projection_revision", minimum=1
    )
    sequence = _integer(
        body.get("projection_sequence"), "projection.projection_sequence", minimum=0
    )
    _timestamp(body.get("generated_at"), "projection.generated_at")
    expected_etag = f'"p4:{expected_run_id}:{revision}:{sequence}"'
    _expect(etag, expected_etag, "projection.ETag")

    object_body = _mapping(body.get("object"), "projection.object")
    _validate_projection_object(object_body, expected_object_id=expected_object_id)
    run = _mapping(body.get("run"), "projection.run")
    validate_run_detail(
        run,
        object_id=expected_object_id,
        goal_id=expected_goal_id,
        scheme_id=expected_scheme_id,
        expected_as_of=expected_as_of,
        run_id=expected_run_id,
        planned_graph_id=expected_planned_graph_id,
    )
    status = run["status"]
    _expect(run.get("stage"), RUN_STAGE[status], "projection.run.stage")

    _validate_projection_goal(
        body.get("goal"),
        expected_goal_id=expected_goal_id,
        expected_object_id=expected_object_id,
        expected_as_of=expected_as_of,
    )
    _validate_projection_scheme(
        body.get("confirmed_scheme"),
        expected_scheme_id=expected_scheme_id,
        expected_goal_id=expected_goal_id,
        expected_object_id=expected_object_id,
    )

    planned_graph_id, planned_tasks = _validate_graph(
        body.get("planned_graph"),
        "projection.planned_graph",
        run_id=expected_run_id,
    )
    _expect(planned_graph_id, expected_planned_graph_id, "projection.planned_graph.graph_id")
    actual_graph = body.get("actual_graph")
    graph_version = body.get("graph_version")
    if actual_graph is None:
        if graph_version is not None or run.get("actual_graph_id") is not None:
            raise ContractViolation(
                "projection actual_graph/run.actual_graph_id/graph_version must be jointly null"
            )
    else:
        actual = _mapping(actual_graph, "projection.actual_graph")
        actual_graph_id, actual_tasks = _validate_graph(
            actual,
            "projection.actual_graph",
            run_id=expected_run_id,
        )
        _expect(run.get("actual_graph_id"), actual_graph_id, "projection.run.actual_graph_id")
        version = _integer(graph_version, "projection.graph_version", minimum=1)
        _expect(actual.get("version"), version, "projection.actual_graph.version")
        if not set(planned_tasks) <= set(actual_tasks):
            raise ContractViolation("projection.actual_graph omits a planned Task")

    tasks = _list(body.get("tasks"), "projection.tasks")
    task_records: dict[str, dict[str, Any]] = {}
    for index, raw_task in enumerate(tasks):
        path = f"projection.tasks[{index}]"
        task = _validate_task(raw_task, path, run_id=expected_run_id)
        task_id = task["task_id"]
        if task_id in task_records:
            raise ContractViolation("projection contains duplicate Task identities")
        task_records[task_id] = task
    task_ids = set(task_records)
    for task in task_records.values():
        related = set(task["dependencies"])
        if task["parent_task_id"] is not None:
            related.add(task["parent_task_id"])
        if not related <= task_ids:
            raise ContractViolation("projection Task relationships escape the exact Run")
    active_tasks = actual_tasks if actual_graph is not None else planned_tasks
    if task_records != active_tasks:
        raise ContractViolation("projection Tasks disagree with the active graph")

    path_changes = _list(body.get("path_changes"), "projection.path_changes")
    path_change_ids: set[str] = set()
    for index, raw_change in enumerate(path_changes):
        path = f"projection.path_changes[{index}]"
        change = _mapping(raw_change, path)
        _exact_fields(
            change,
            {
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
            },
            path,
        )
        identity = _text(change.get("path_change_id"), f"{path}.path_change_id")
        if identity in path_change_ids:
            raise ContractViolation("projection contains duplicate path-change identities")
        path_change_ids.add(identity)
        if change.get("source_kind") not in {"CORRECTION", "REPLAN"}:
            raise ContractViolation(f"{path}.source_kind is unsupported")
        _text(change.get("source_id"), f"{path}.source_id")
        _expect(change.get("source_id"), identity, f"{path}.source_id")
        if change.get("change_kind") not in PATH_CHANGE_KINDS:
            raise ContractViolation(f"{path}.change_kind is unsupported")
        source_kind = change["source_kind"]
        change_kind = change["change_kind"]
        if (source_kind == "CORRECTION") != (change_kind == "SELF_CORRECTION"):
            raise ContractViolation(f"{path} has an impossible source/change kind combination")
        task_refs = _list(change.get("task_refs"), f"{path}.task_refs")
        for task_id in task_refs:
            _text(task_id, f"{path}.task_refs")
            if task_id not in task_ids:
                raise ContractViolation(f"{path}.task_refs contains a foreign Task")
        if len(task_refs) != len(set(task_refs)):
            raise ContractViolation(f"{path}.task_refs contains duplicate Task identities")
        status_value = change.get("status")
        _text(status_value, f"{path}.status")
        for nullable_name in ("decision", "reason_code"):
            nullable = change.get(nullable_name)
            if nullable is not None and (not isinstance(nullable, str) or not nullable):
                raise ContractViolation(f"{path}.{nullable_name} must be null or non-empty")
        operations = _list(change.get("operations"), f"{path}.operations")
        for operation_index, raw_operation in enumerate(operations):
            operation_path = f"{path}.operations[{operation_index}]"
            operation = _mapping(raw_operation, operation_path)
            operation_kind = operation.get("operation")
            if operation_kind == "add_node":
                required = {"operation", "task_id"}
            elif operation_kind in {"add_edge", "remove_edge"}:
                required = {"operation", "task_id", "dependency_task_id"}
            else:
                raise ContractViolation(f"{operation_path}.operation is unsupported")
            _exact_fields(operation, required, operation_path)
            for field_name in required - {"operation"}:
                reference = _text(operation.get(field_name), f"{operation_path}.{field_name}")
                if reference not in task_ids or reference not in task_refs:
                    raise ContractViolation(f"{operation_path}.{field_name} is a foreign Task")
        before = change.get("graph_version_before")
        after = change.get("graph_version_after")
        if before is not None:
            before = _integer(before, f"{path}.graph_version_before", minimum=1)
        if after is not None:
            after = _integer(after, f"{path}.graph_version_after", minimum=1)
            if graph_version is None or after > graph_version:
                raise ContractViolation(f"{path}.graph_version_after exceeds active graph version")
        created_at = _timestamp(change.get("created_at"), f"{path}.created_at")
        resolved_at = change.get("resolved_at")
        if resolved_at is not None:
            resolved_at = _timestamp(resolved_at, f"{path}.resolved_at")
            if resolved_at < created_at:
                raise ContractViolation(f"{path}.resolved_at precedes created_at")

        decision = change.get("decision")
        if source_kind == "CORRECTION":
            if status_value not in {"RESOLVED", "FAILED", "ESCALATED"}:
                raise ContractViolation(f"{path}.status is not a Correction status")
            if decision is not None or len(task_refs) != 1 or operations:
                raise ContractViolation(
                    f"{path} Self-Correction must remain one-Task and topology-neutral"
                )
            if change.get("reason_code") is None:
                raise ContractViolation(f"{path} Correction requires reason_code")
            if before is not None or after is not None:
                raise ContractViolation(
                    f"{path} topology-neutral Self-Correction requires null graph versions"
                )
        else:
            if decision not in {"PENDING", "APPROVED", "REJECTED"} or status_value != decision:
                raise ContractViolation(f"{path} Replan status/decision are inconsistent")
            if decision == "PENDING":
                if resolved_at is not None or after is not None:
                    raise ContractViolation(
                        f"{path} pending Replan cannot be resolved or mutate graph"
                    )
            elif decision == "REJECTED":
                if after is not None:
                    raise ContractViolation(f"{path} rejected Replan cannot mutate graph")
            else:
                if not operations or before is None or after is None:
                    raise ContractViolation(
                        f"{path} approved Replan requires operations and versions"
                    )
                if after != before + 1:
                    raise ContractViolation(f"{path} approved Replan must advance graph once")
                if change_kind == "ADD_TASK" and not any(
                    operation.get("operation") == "add_node" for operation in operations
                ):
                    raise ContractViolation(f"{path} ADD_TASK requires an add_node operation")

    activity = _list(body.get("activity"), "projection.activity")
    activity_ids: set[str] = set()
    activity_sequences: list[int] = []
    for index, raw_activity in enumerate(activity):
        activity_path = f"projection.activity[{index}]"
        item = _mapping(raw_activity, activity_path)
        _required_approved_fields(
            item,
            ACTIVITY_FIELDS,
            ACTIVITY_PROJECTION_OPTIONAL_FIELDS,
            activity_path,
        )
        event_id = _text(item.get("event_id"), f"{activity_path}.event_id")
        if event_id in activity_ids:
            raise ContractViolation("projection.activity contains duplicate Event identities")
        activity_ids.add(event_id)
        _text(item.get("type"), f"{activity_path}.type")
        activity_sequence = _integer(item.get("sequence"), f"{activity_path}.sequence", minimum=1)
        if activity_sequence > sequence:
            raise ContractViolation(f"{activity_path}.sequence exceeds projection watermark")
        activity_sequences.append(activity_sequence)
        _timestamp(item.get("timestamp"), f"{activity_path}.timestamp")
        activity_task_id = item.get("task_id")
        if activity_task_id is not None and activity_task_id not in task_ids:
            raise ContractViolation(f"{activity_path}.task_id is a foreign Task")
        _text(item.get("message_code"), f"{activity_path}.message_code")
        status_field = item.get("status")
        if status_field is not None:
            _text(status_field, f"{activity_path}.status")
        actor_id = item.get("actor_id")
        actor_type = item.get("actor_type")
        if (actor_id is None) != (actor_type is None):
            raise ContractViolation(f"{activity_path} actor identity/type must be jointly present")
        if actor_id is not None:
            _text(actor_id, f"{activity_path}.actor_id")
            _text(actor_type, f"{activity_path}.actor_type")
        duration_ms = item.get("duration_ms")
        if duration_ms is not None:
            _integer(duration_ms, f"{activity_path}.duration_ms", minimum=0)
        for refs_name in (
            "input_refs",
            "output_refs",
            "evidence_refs",
            "calculation_refs",
            "claim_refs",
            "judgment_refs",
            "review_refs",
            "proof_refs",
            "artifact_refs",
            "trace_bundle_refs",
        ):
            if refs_name not in item:
                continue
            refs = _list(item.get(refs_name), f"{activity_path}.{refs_name}")
            if not all(isinstance(ref, str) and ref.strip() for ref in refs):
                raise ContractViolation(f"{activity_path}.{refs_name} contains an invalid identity")
            if len(refs) != len(set(refs)):
                raise ContractViolation(f"{activity_path}.{refs_name} contains duplicates")
        _assert_safe_public_json(item, activity_path)
    if activity_sequences != sorted(activity_sequences) or len(activity_sequences) != len(
        set(activity_sequences)
    ):
        raise ContractViolation("projection.activity sequences must be unique and ascending")
    lifecycle = _mapping(body.get("lifecycle"), "projection.lifecycle")
    _expect(lifecycle.get("status"), status, "projection.lifecycle.status")
    _expect(lifecycle.get("stage"), RUN_STAGE[status], "projection.lifecycle.stage")
    completed_tasks, total_tasks, fraction = _validate_progress(
        lifecycle.get("progress"), "projection.lifecycle.progress"
    )
    _expect(total_tasks, len(task_records), "projection.lifecycle.progress.total_tasks")
    _expect(
        completed_tasks,
        sum(task["status"] == "COMPLETED" for task in task_records.values()),
        "projection.lifecycle.progress.completed_tasks",
    )
    all_tasks_terminal = all(
        task["status"] in TERMINAL_TASK_STATUSES for task in task_records.values()
    )
    if status == "RELEASED" or (status in {"FAILED", "CANCELLED"} and all_tasks_terminal):
        expected_fraction = 1.0
    elif not task_records:
        expected_fraction = 0.0
    else:
        expected_fraction = sum(task["progress"] for task in task_records.values()) / len(
            task_records
        )
    if not math.isclose(fraction, expected_fraction, rel_tol=0.0, abs_tol=1e-12):
        raise ContractViolation(
            "projection.lifecycle.progress.fraction is not the unweighted actual Task mean"
        )
    expected_terminal = status in TERMINAL_RUN_STATUSES
    _expect(lifecycle.get("terminal"), expected_terminal, "projection.lifecycle.terminal")
    _exact_fields(
        lifecycle,
        {"status", "stage", "progress", "terminal", "terminal_outcome", "safe_failure"},
        "projection.lifecycle",
    )
    expected_outcome = {
        "RELEASED": "SUCCESS",
        "FAILED": "FAILURE",
        "CANCELLED": "CANCELLED",
    }.get(status)
    _expect(
        lifecycle.get("terminal_outcome"), expected_outcome, "projection.lifecycle.terminal_outcome"
    )
    safe_failure = lifecycle.get("safe_failure")
    if status in {"FAILED", "CANCELLED"}:
        failure = _mapping(safe_failure, "projection.lifecycle.safe_failure")
        _exact_fields(
            failure,
            {"status", "failure_stage", "failure_code", "safe_message"},
            "projection.lifecycle.safe_failure",
        )
        _expect(failure.get("status"), status, "projection.lifecycle.safe_failure.status")
        failure_stage = _text(
            failure.get("failure_stage"), "projection.lifecycle.safe_failure.failure_stage"
        )
        failure_code = _text(
            failure.get("failure_code"), "projection.lifecycle.safe_failure.failure_code"
        )
        if status == "CANCELLED":
            _expect(
                failure_stage,
                "CANCELLATION",
                "projection.lifecycle.safe_failure.failure_stage",
            )
            _expect(
                failure_code,
                "RUN_CANCELLED",
                "projection.lifecycle.safe_failure.failure_code",
            )
        elif (
            failure_stage not in FAILURE_STAGE_CODES
            or failure_code not in FAILURE_STAGE_CODES[failure_stage]
        ):
            raise ContractViolation(
                "projection.lifecycle.safe_failure has an unsupported failure stage/code pair"
            )
        safe_message = failure.get("safe_message")
        if safe_message is not None:
            _text(safe_message, "projection.lifecycle.safe_failure.safe_message")
    elif safe_failure is not None:
        raise ContractViolation(
            "projection.lifecycle.safe_failure requires FAILED or CANCELLED status"
        )

    summary_fields = {
        "review": {"availability", "review_id", "status"},
        "result": {"availability", "released_result_id", "canonical_record_id", "released_at"},
        "artifacts": {"availability", "report_id", "representation_ids"},
        "execution": {"availability", "canonical_record_id"},
    }
    for name, fields in summary_fields.items():
        summary = _mapping(body.get(name), f"projection.{name}")
        _exact_fields(summary, fields, f"projection.{name}")
        availability = validate_availability(
            summary.get("availability"), f"projection.{name}.availability"
        )
        for field_name in fields - {
            "availability",
            "status",
            "released_at",
            "representation_ids",
        }:
            reference = summary.get(field_name)
            if reference is not None and (not isinstance(reference, str) or not reference):
                raise ContractViolation(f"projection.{name}.{field_name} must be null or non-empty")
        if availability["status"] == "AVAILABLE":
            required_reference = {
                "review": "review_id",
                "result": "released_result_id",
                "artifacts": "report_id",
                "execution": "canonical_record_id",
            }[name]
            if summary.get(required_reference) is None:
                raise ContractViolation(
                    f"projection.{name}.{required_reference} is required when AVAILABLE"
                )
        if name == "review":
            review_status = summary.get("status")
            if review_status is not None and review_status not in REVIEW_STATUS_VALUES:
                raise ContractViolation("projection.review.status is unsupported")
            review_tuple = (summary.get("review_id"), review_status)
            if (review_tuple[0] is None) != (review_tuple[1] is None):
                raise ContractViolation("projection.review identity/status must be jointly present")
            if availability["status"] == "AVAILABLE" and any(item is None for item in review_tuple):
                raise ContractViolation("projection.review AVAILABLE requires identity and status")
            if (availability["status"] == "AVAILABLE") != (review_tuple[0] is not None):
                raise ContractViolation(
                    "projection.review identity/status must be present exactly when AVAILABLE"
                )
        elif name == "result":
            released_at = summary.get("released_at")
            if released_at is not None:
                _timestamp(released_at, "projection.result.released_at")
            result_tuple = (
                summary.get("released_result_id"),
                summary.get("canonical_record_id"),
                released_at,
            )
            present = sum(item is not None for item in result_tuple)
            if present not in {0, 3}:
                raise ContractViolation("projection.result identity/time tuple is partial")
            if availability["status"] == "AVAILABLE" and present != 3:
                raise ContractViolation("projection.result AVAILABLE requires full identity/time")
            if (availability["status"] == "AVAILABLE") != (present == 3):
                raise ContractViolation(
                    "projection.result identity/time must be present exactly when AVAILABLE"
                )
        elif name == "artifacts":
            representations = _list(
                summary.get("representation_ids"),
                "projection.artifacts.representation_ids",
            )
            if not all(isinstance(item, str) and item.strip() for item in representations):
                raise ContractViolation("projection.artifacts.representation_ids are invalid")
            if len(representations) != len(set(representations)):
                raise ContractViolation(
                    "projection.artifacts.representation_ids contain duplicates"
                )
            if availability["status"] == "AVAILABLE" and (
                summary.get("report_id") is None or not representations
            ):
                raise ContractViolation(
                    "projection.artifacts AVAILABLE requires report and representation identities"
                )
            if (summary.get("report_id") is None) != (not representations):
                raise ContractViolation(
                    "projection.artifacts report and representation identities are partial"
                )
            if (availability["status"] == "AVAILABLE") != (
                summary.get("report_id") is not None
            ):
                raise ContractViolation(
                    "projection.artifacts identities must be present exactly when AVAILABLE"
                )
        elif name == "execution" and (availability["status"] == "AVAILABLE") != (
            summary.get("canonical_record_id") is not None
        ):
            raise ContractViolation(
                "projection.execution identity must be present exactly when AVAILABLE"
            )
    proof = _mapping(body.get("proof"), "projection.proof")
    _exact_fields(proof, {"availability", "policy", "status", "proof_refs"}, "projection.proof")
    validate_availability(proof.get("availability"), "projection.proof.availability")
    if proof.get("policy") not in PROOF_POLICY_VALUES:
        raise ContractViolation("projection.proof.policy is unsupported")
    proof_status = proof.get("status")
    if proof_status is not None and proof_status not in PROOF_STATUS_VALUES:
        raise ContractViolation("projection.proof.status is unsupported")
    proof_refs = _list(proof.get("proof_refs"), "projection.proof.proof_refs")
    if not all(isinstance(item, str) and item.strip() for item in proof_refs):
        raise ContractViolation("projection.proof.proof_refs contain invalid identities")
    if len(proof_refs) != len(set(proof_refs)):
        raise ContractViolation("projection.proof.proof_refs contain duplicates")
    proof_availability = validate_availability(
        proof.get("availability"), "projection.proof.availability"
    )
    if proof_availability["status"] == "AVAILABLE" and proof_status is None:
        raise ContractViolation("projection.proof AVAILABLE requires an explicit status")
    if proof.get("policy") == "NOT_REQUIRED" and (
        proof_status not in {None, "NOT_REQUIRED"} or proof_refs
    ):
        raise ContractViolation("projection.proof NOT_REQUIRED policy has proof output")

    result = _mapping(body.get("result"), "projection.result")
    execution = _mapping(body.get("execution"), "projection.execution")
    if (
        result.get("canonical_record_id") is not None
        and execution.get("canonical_record_id") is not None
    ):
        _expect(
            execution.get("canonical_record_id"),
            result.get("canonical_record_id"),
            "projection.execution.canonical_record_id",
        )
    if expected_terminal:
        for name in ("review", "result", "artifacts", "proof", "execution"):
            summary = _mapping(body.get(name), f"projection.{name}")
            availability = validate_availability(
                summary.get("availability"), f"projection.{name}.availability"
            )
            if availability["status"] == "PENDING":
                raise ContractViolation(f"terminal Run retains PENDING {name} availability")
    if status == "RELEASED":
        for name in ("review", "result", "artifacts", "execution"):
            summary = _mapping(body.get(name), f"projection.{name}")
            availability = validate_availability(
                summary.get("availability"), f"projection.{name}.availability"
            )
            if availability["status"] != "AVAILABLE":
                raise ContractViolation(f"RELEASED Run requires AVAILABLE {name}")
        if _mapping(body.get("review"), "projection.review").get("status") != "PASS":
            raise ContractViolation("RELEASED Run requires PASS Review status")
        policy = proof.get("policy")
        if policy == "UNKNOWN" or proof_status in {None, "PENDING", "PROVING"}:
            raise ContractViolation("RELEASED Run requires a resolved Proof disposition")
        if policy == "MUST_PROVE" and (proof_status != "VERIFIED" or not proof_refs):
            raise ContractViolation("MUST_PROVE release requires VERIFIED proof references")
    elif (
        validate_availability(result.get("availability"), "projection.result.availability")[
            "status"
        ]
        == "AVAILABLE"
    ):
        raise ContractViolation("non-RELEASED Run cannot expose an AVAILABLE result")

    terminal = _mapping(body.get("terminal"), "projection.terminal")
    _exact_fields(
        terminal, {"is_terminal", "outcome", "event_id", "sequence"}, "projection.terminal"
    )
    _expect(terminal.get("is_terminal"), expected_terminal, "projection.terminal.is_terminal")
    if not expected_terminal:
        for name in ("outcome", "event_id", "sequence"):
            _expect(terminal.get(name), None, f"projection.terminal.{name}")
    else:
        _expect(terminal.get("outcome"), expected_outcome, "projection.terminal.outcome")
        terminal_event_id = _text(terminal.get("event_id"), "projection.terminal.event_id")
        terminal_sequence = _integer(
            terminal.get("sequence"), "projection.terminal.sequence", minimum=1
        )
        _expect(terminal_sequence, sequence, "projection.terminal.sequence")
        if not activity or activity[-1].get("event_id") != terminal_event_id:
            raise ContractViolation("projection terminal Event must be final in activity")
    return revision, sequence, status


def validate_error_envelope(
    observation: HttpObservation,
    *,
    expected_code: str,
    expected_resource_type: str | None = None,
    expected_resource_id: str | None = None,
    expected_reason_code: str | None = None,
) -> JsonObject:
    if expected_code not in ERROR_TUPLES:
        raise ValueError(f"unsupported expected error code: {expected_code}")
    expected_http, expected_retryable, expected_recovery = ERROR_TUPLES[expected_code]
    if observation.status_code != expected_http:
        raise ContractViolation(
            f"{expected_code} must use HTTP {expected_http}, observed {observation.status_code}"
        )
    media_type = (observation.header("content-type") or "").lower()
    if not media_type.startswith("application/json"):
        raise ContractViolation("error response has the wrong Content-Type")
    body = observation.json_object()
    _exact_fields(body, {"schema_version", "error"}, "error response")
    _expect(body.get("schema_version"), "phase4-error/v1", "error.schema_version")
    _absent(body, {"admission", "run_id", "result", "success"}, "error response")
    error = _mapping(body.get("error"), "error.error")
    _exact_fields(
        error,
        {"code", "message", "retryable", "recovery", "request_id", "resource", "details"},
        "error.error",
    )
    _expect(error.get("code"), expected_code, "error.error.code")
    message = _text(error.get("message"), "error.error.message")
    _assert_safe_public_json(message, "error.error.message")
    _expect(error.get("retryable"), expected_retryable, "error.error.retryable")
    _expect(error.get("recovery"), expected_recovery, "error.error.recovery")
    request_id = error.get("request_id")
    if request_id is not None and (not isinstance(request_id, str) or not request_id):
        raise ContractViolation("error.error.request_id must be null or non-empty")
    resource = error.get("resource")
    if expected_resource_type is not None or expected_resource_id is not None:
        resource_body = _mapping(resource, "error.error.resource")
        _exact_fields(resource_body, {"type", "id"}, "error.error.resource")
        if expected_resource_type is not None:
            _expect(resource_body.get("type"), expected_resource_type, "error.error.resource.type")
        if expected_resource_id is not None:
            _expect(resource_body.get("id"), expected_resource_id, "error.error.resource.id")
    elif resource is not None:
        resource_body = _mapping(resource, "error.error.resource")
        _exact_fields(resource_body, {"type", "id"}, "error.error.resource")
        _text(resource_body.get("type"), "error.error.resource.type")
        _text(resource_body.get("id"), "error.error.resource.id")
    details = _mapping(error.get("details"), "error.error.details")
    _assert_safe_public_json(details, "error.error.details")
    if expected_reason_code is not None:
        _expect(details.get("reason_code"), expected_reason_code, "error.error.details.reason_code")
    return body


def _object_runs(
    transport: JsonTransport,
    object_id: str,
) -> tuple[str, ...]:
    response = transport.request(
        "GET",
        f"/api/objects/{_path_id(object_id)}/runs",
        headers=_contract_headers(),
    )
    body = _success_json(response, allowed_statuses=frozenset({200}))
    return validate_run_collection(body, expected_object_id=object_id)


def check_object_and_initial_runs(
    transport: JsonTransport,
    config: BackendHarnessConfig,
) -> ObjectEvidence:
    invalid = transport.request(
        "POST",
        "/api/objects",
        headers=_contract_headers(idempotency_key=f"{config.object_idempotency_key}-invalid"),
        json_body={**config.object_request, "symbol": ""},
    )
    validate_error_envelope(invalid, expected_code="REQUEST_VALIDATION_ERROR")
    missing_object_id = f"OBJ-MISSING-{secrets.token_hex(12).upper()}"
    missing = transport.request(
        "GET",
        f"/api/objects/{_path_id(missing_object_id)}",
        headers=_contract_headers(),
    )
    validate_error_envelope(
        missing,
        expected_code="NOT_FOUND",
        expected_resource_type="research_object",
        expected_resource_id=missing_object_id,
    )
    create = transport.request(
        "POST",
        "/api/objects",
        headers=_contract_headers(idempotency_key=config.object_idempotency_key),
        json_body=config.object_request,
    )
    created_body = _success_json(create, allowed_statuses=frozenset({201}))
    object_id = validate_research_object_detail(
        created_body,
        expected_request=config.object_request,
    )
    exact = transport.request(
        "GET",
        f"/api/objects/{_path_id(object_id)}",
        headers=_contract_headers(),
    )
    exact_body = _success_json(exact, allowed_statuses=frozenset({200}))
    validate_research_object_detail(
        exact_body,
        expected_request=config.object_request,
        expected_object_id=object_id,
    )
    immutable_names = (
        "object_id",
        "object_type",
        "symbol",
        "company_name",
        "exchange",
        "sector",
        "currency",
        "identity_version",
    )
    created_object = _mapping(created_body.get("object"), "created object detail.object")
    exact_object = _mapping(exact_body.get("object"), "exact object detail.object")
    for name in immutable_names:
        _expect(exact_object.get(name), created_object.get(name), f"object round trip.{name}")
    _expect(
        exact_body.get("created_at"),
        created_body.get("created_at"),
        "object round trip.created_at",
    )
    return ObjectEvidence(
        object_id=object_id,
        object_body=exact_body,
        initial_run_ids=_object_runs(transport, object_id),
    )


def check_prepare_goal_scheme(
    transport: JsonTransport,
    config: BackendHarnessConfig,
    object_evidence: ObjectEvidence,
) -> DraftEvidence:
    prepare_body: JsonObject = {
        "research_object_id": object_evidence.object_id,
        "research_goal": config.research_goal,
        "as_of": config.as_of,
        "preferences": dict(config.preferences),
    }
    headers = _contract_headers(idempotency_key=config.prepare_idempotency_key)
    missing_object_id = f"OBJ-MISSING-{secrets.token_hex(12).upper()}"
    missing_object = transport.request(
        "POST",
        "/api/research-runs/prepare",
        headers=_contract_headers(
            idempotency_key=f"{config.prepare_idempotency_key}-missing-object"
        ),
        json_body={**prepare_body, "research_object_id": missing_object_id},
    )
    validate_error_envelope(
        missing_object,
        expected_code="NOT_FOUND",
        expected_resource_type="research_object",
        expected_resource_id=missing_object_id,
    )
    first = transport.request(
        "POST",
        "/api/research-runs/prepare",
        headers=headers,
        json_body=prepare_body,
    )
    first_body = _success_json(first, allowed_statuses=frozenset({201}))
    draft = validate_research_run_draft(
        first_body,
        expected_object_id=object_evidence.object_id,
        expected_goal_text=config.research_goal,
        expected_as_of=config.as_of,
        expected_preferences=config.preferences,
    )
    replay = transport.request(
        "POST",
        "/api/research-runs/prepare",
        headers=headers,
        json_body=prepare_body,
    )
    replay_body = _success_json(replay, allowed_statuses=frozenset({201}))
    validate_research_run_draft(
        replay_body,
        expected_object_id=object_evidence.object_id,
        expected_goal_text=config.research_goal,
        expected_as_of=config.as_of,
        expected_preferences=config.preferences,
    )
    _expect(replay_body, first_body, "prepare idempotent replay")

    mismatched_body = {**prepare_body, "research_goal": f"{config.research_goal} changed"}
    mismatch = transport.request(
        "POST",
        "/api/research-runs/prepare",
        headers=headers,
        json_body=mismatched_body,
    )
    validate_error_envelope(
        mismatch,
        expected_code="CONFLICT",
        expected_reason_code="IDEMPOTENCY_REQUEST_MISMATCH",
    )
    run_ids = _object_runs(transport, object_evidence.object_id)
    _expect(run_ids, object_evidence.initial_run_ids, "prepare must not create a Run")
    return DraftEvidence(
        body=draft.body,
        draft_id=draft.draft_id,
        draft_version=draft.draft_version,
        draft_hash=draft.draft_hash,
        goal_id=draft.goal_id,
        scheme_id=draft.scheme_id,
        run_ids_before_confirm=run_ids,
    )


def check_confirm_admission_and_replay(
    transport: JsonTransport,
    config: BackendHarnessConfig,
    object_evidence: ObjectEvidence,
    draft: DraftEvidence,
) -> AdmissionEvidence:
    confirm_body: JsonObject = {
        "draft_id": draft.draft_id,
        "draft_version": draft.draft_version,
        "draft_hash": draft.draft_hash,
        "research_object_id": object_evidence.object_id,
        "confirm_scheme": True,
    }
    headers = _contract_headers(idempotency_key=config.confirm_idempotency_key)
    version_mismatch = transport.request(
        "POST",
        "/api/research-runs",
        headers=_contract_headers(
            idempotency_key=f"{config.confirm_idempotency_key}-version-negative"
        ),
        json_body={**confirm_body, "draft_version": draft.draft_version + 1},
    )
    validate_error_envelope(
        version_mismatch,
        expected_code="CONFLICT",
        expected_reason_code="DRAFT_VERSION_MISMATCH",
    )
    _expect(
        _object_runs(transport, object_evidence.object_id),
        draft.run_ids_before_confirm,
        "version-mismatched Confirm must not create a Run",
    )
    first = transport.request(
        "POST",
        "/api/research-runs",
        headers=headers,
        json_body=confirm_body,
    )
    first_body = _success_json(first, allowed_statuses=frozenset({201}))
    admission = validate_confirm_response(
        first_body,
        expected_draft=draft,
        expected_object_id=object_evidence.object_id,
        expected_replayed=False,
    )
    run_id = admission["run_id"]
    after_first = _object_runs(transport, object_evidence.object_id)
    new_ids = set(after_first) - set(draft.run_ids_before_confirm)
    _expect(new_ids, {run_id}, "one confirmation must create exactly one Run identity")
    if after_first.count(run_id) != 1:
        raise ContractViolation("confirmed Run must occur exactly once in the Object history")

    replay = transport.request(
        "POST",
        "/api/research-runs",
        headers=headers,
        json_body=confirm_body,
    )
    replay_body = _success_json(replay, allowed_statuses=frozenset({200}))
    replay_admission = validate_confirm_response(
        replay_body,
        expected_draft=draft,
        expected_object_id=object_evidence.object_id,
        expected_replayed=True,
    )
    _expect(replay_admission, admission, "confirm immutable admission replay")
    after_replay = _object_runs(transport, object_evidence.object_id)
    _expect(after_replay, after_first, "confirm replay Run cardinality")

    consumed = transport.request(
        "POST",
        "/api/research-runs",
        headers=_contract_headers(
            idempotency_key=f"{config.confirm_idempotency_key}-consumed-negative"
        ),
        json_body=confirm_body,
    )
    validate_error_envelope(
        consumed,
        expected_code="CONFLICT",
        expected_reason_code="DRAFT_CONSUMED",
    )
    _expect(
        _object_runs(transport, object_evidence.object_id),
        after_first,
        "new-key consumed-draft Confirm must not create a Run",
    )

    changed_body = {**confirm_body, "research_object_id": f"{object_evidence.object_id}-FOREIGN"}
    mismatch = transport.request(
        "POST",
        "/api/research-runs",
        headers=headers,
        json_body=changed_body,
    )
    validate_error_envelope(
        mismatch,
        expected_code="CONFLICT",
        expected_reason_code="IDEMPOTENCY_REQUEST_MISMATCH",
    )
    after_mismatch = _object_runs(transport, object_evidence.object_id)
    _expect(after_mismatch, after_first, "confirm conflict Run cardinality")
    return AdmissionEvidence(
        response=first_body,
        admission=admission,
        confirm_body=confirm_body,
        run_id=run_id,
        planned_graph_id=admission["planned_graph_id"],
        run_ids_after_confirm=after_first,
    )


def _projection_request(transport: JsonTransport, run_id: str) -> tuple[JsonObject, str | None]:
    response = transport.request(
        "GET",
        f"/api/research-runs/{_path_id(run_id)}/projection",
        headers=_contract_headers(),
    )
    body = _success_json(response, allowed_statuses=frozenset({200}))
    return body, response.header("etag")


def check_exact_run_and_projection(
    transport: JsonTransport,
    config: BackendHarnessConfig,
    object_evidence: ObjectEvidence,
    draft: DraftEvidence,
    admission: AdmissionEvidence,
) -> RunProjectionEvidence:
    detail_response = transport.request(
        "GET",
        f"/api/research-runs/{_path_id(admission.run_id)}",
        headers=_contract_headers(),
    )
    detail = _success_json(detail_response, allowed_statuses=frozenset({200}))
    validate_standalone_run_detail(
        detail,
        object_id=object_evidence.object_id,
        goal_id=draft.goal_id,
        scheme_id=draft.scheme_id,
        expected_as_of=config.as_of,
        run_id=admission.run_id,
        planned_graph_id=admission.planned_graph_id,
    )

    deadline = time.monotonic() + config.auto_start_timeout_seconds
    while True:
        projection, etag = _projection_request(transport, admission.run_id)
        _, _, status = validate_atomic_run_projection(
            projection,
            expected_object_id=object_evidence.object_id,
            expected_goal_id=draft.goal_id,
            expected_scheme_id=draft.scheme_id,
            expected_as_of=config.as_of,
            expected_run_id=admission.run_id,
            expected_planned_graph_id=admission.planned_graph_id,
            etag=etag,
        )
        if status in AUTO_STARTED_RUN_STATUSES:
            return RunProjectionEvidence(
                run_detail=detail,
                projection=projection,
                etag=_text(etag, "projection.ETag"),
            )
        if status in {"FAILED", "CANCELLED"}:
            raise ContractViolation("auto-start reached an unsuccessful terminal state")
        if time.monotonic() >= deadline:
            raise ContractViolation("confirmation did not auto-start the Run before the deadline")
        time.sleep(min(config.poll_interval_seconds, max(0.0, deadline - time.monotonic())))


def check_typed_error_contract(
    transport: JsonTransport,
    run_id: str,
) -> None:
    missing_run_id = f"RUN-MISSING-{secrets.token_hex(12).upper()}"
    missing = transport.request(
        "GET",
        f"/api/research-runs/{_path_id(missing_run_id)}",
        headers=_contract_headers(),
    )
    validate_error_envelope(
        missing,
        expected_code="NOT_FOUND",
        expected_resource_type="research_run",
        expected_resource_id=missing_run_id,
    )
    incompatible = transport.request(
        "GET",
        f"/api/research-runs/{_path_id(run_id)}",
        headers={CONTRACT_HEADER: "phase4-core/v999"},
    )
    validate_error_envelope(incompatible, expected_code="SCHEMA_INCOMPATIBLE")


def _pass(
    control_id: str,
    summary: str,
    *,
    owner_dependency: str = "A",
    evidence: Mapping[str, Any] | None = None,
) -> ControlResult:
    return ControlResult(
        control_id=control_id,
        status="PASS",
        summary=summary,
        owner_dependency=owner_dependency,
        evidence=evidence or {},
    )


def _failure(control_id: str, exc: Exception, *, owner_dependency: str = "A") -> ControlResult:
    if isinstance(exc, (ContractViolation, TransportUnavailable)):
        summary = str(exc)
    else:
        summary = f"internal harness error ({type(exc).__name__})"
    return ControlResult(
        control_id=control_id,
        status="FAIL",
        summary=summary,
        owner_dependency=owner_dependency,
        evidence={},
    )


def run_backend_vs01(
    config: BackendHarnessConfig,
    *,
    transport: JsonTransport | None = None,
) -> BackendHarnessReport:
    """Run the pre-restart X1 journey and return a redaction-safe result/checkpoint."""

    active_transport = transport or UrllibJsonTransport(
        config.base_url,
        timeout_seconds=config.request_timeout_seconds,
    )
    controls: list[ControlResult] = []
    try:
        current = "VS01-BE-001"
        object_evidence = check_object_and_initial_runs(active_transport, config)
        controls.append(
            _pass(
                current,
                "invalid/missing Objects fail closed; valid create/read uses one exact identity",
                evidence={"object_id": object_evidence.object_id},
            )
        )

        current = "VS01-BE-002"
        draft = check_prepare_goal_scheme(active_transport, config, object_evidence)
        controls.append(
            _pass(
                current,
                "prepare binds exact Object, Goal, and immutable Scheme identities",
                evidence={
                    "draft_id": draft.draft_id,
                    "goal_id": draft.goal_id,
                    "scheme_id": draft.scheme_id,
                },
            )
        )
        controls.append(
            _pass(
                "VS01-BE-003",
                "prepare replay is immutable and prepare creates no Run/Task graph",
                evidence={"run_count_before_confirm": len(draft.run_ids_before_confirm)},
            )
        )

        current = "VS01-BE-004"
        admitted = check_confirm_admission_and_replay(
            active_transport,
            config,
            object_evidence,
            draft,
        )
        controls.append(
            _pass(
                current,
                "Confirm returns one immutable versioned RunAdmissionV1",
                evidence={
                    "admission_id": admitted.admission["admission_id"],
                    "run_id": admitted.run_id,
                },
            )
        )
        controls.append(
            _pass(
                "VS01-BE-005",
                "same-key replay and new-key consumed-draft conflict create no second Run",
                evidence={"run_id": admitted.run_id},
            )
        )
        controls.append(
            _pass(
                "VS01-BE-009",
                "version, consumed-draft and changed same-key Confirm conflicts are typed",
            )
        )

        current = "VS01-BE-007"
        projection = check_exact_run_and_projection(
            active_transport,
            config,
            object_evidence,
            draft,
            admitted,
        )
        controls.append(
            _pass(
                current,
                "exact Run read preserves Object/Goal/Scheme/graph identity",
                evidence={"run_id": admitted.run_id},
            )
        )
        controls.append(
            _pass(
                "VS01-BE-008",
                "AtomicRunProjectionV1 is identity-closed, versioned, and ETag-bound",
                evidence={
                    "projection_revision": projection.projection["projection_revision"],
                    "projection_sequence": projection.projection["projection_sequence"],
                    "etag": projection.etag,
                },
            )
        )
        controls.append(
            _pass(
                "VS01-BE-006",
                "Confirm alone auto-starts the admitted Run without an execute request",
                evidence={"status": projection.projection["run"]["status"]},
            )
        )

        current = "VS01-BE-010"
        check_typed_error_contract(active_transport, admitted.run_id)
        controls.append(
            _pass(current, "missing exact Run returns the frozen typed NOT_FOUND envelope")
        )
        controls.append(
            _pass(
                "VS01-BE-011",
                "unsupported contract version fails closed with SCHEMA_INCOMPATIBLE",
            )
        )
    except Exception as exc:  # The report must remain machine-readable on a failed live gate.
        controls.append(_failure(current, exc))
        return BackendHarnessReport(phase="PRE_RESTART", controls=tuple(controls))

    checkpoint = RestartCheckpoint(
        object_id=object_evidence.object_id,
        object_identity={
            name: (
                object_evidence.object_body.get("created_at")
                if name == "created_at"
                else _mapping(
                    object_evidence.object_body.get("object"), "checkpoint.object"
                ).get(name)
            )
            for name in (
                "object_id",
                "object_type",
                "symbol",
                "company_name",
                "exchange",
                "sector",
                "currency",
                "identity_version",
                "created_at",
            )
        },
        draft_id=draft.draft_id,
        draft_version=draft.draft_version,
        draft_hash=draft.draft_hash,
        goal_id=draft.goal_id,
        scheme_id=draft.scheme_id,
        as_of=config.as_of,
        run_id=admitted.run_id,
        planned_graph_id=admitted.planned_graph_id,
        admission=dict(admitted.admission),
        confirm_body=dict(admitted.confirm_body),
        confirm_idempotency_key=config.confirm_idempotency_key,
        projection_revision=projection.projection["projection_revision"],
        projection_sequence=projection.projection["projection_sequence"],
    )
    return BackendHarnessReport(
        phase="PRE_RESTART",
        controls=tuple(controls),
        checkpoint=checkpoint,
    )


def verify_restart_checkpoint(
    config: BackendHarnessConfig,
    checkpoint: RestartCheckpoint,
    restart_evidence: RestartEvidence,
    *,
    transport: JsonTransport | None = None,
) -> BackendHarnessReport:
    """Verify the same resources and idempotent outcome after a parent-run restart."""

    controls: list[ControlResult] = []
    current = "VS01-BE-014"
    try:
        _text(restart_evidence.process_boundary_id, "restart.process_boundary_id")
        if not restart_evidence.api_process_restarted:
            raise ContractViolation("restart evidence does not prove an API process boundary")
        if restart_evidence.persistence_backend.strip().lower() not in {
            "postgresql",
            "postgresql 16",
            "postgresql16",
        }:
            raise ContractViolation("restart evidence does not identify PostgreSQL persistence")
        if not restart_evidence.storage_preserved:
            raise ContractViolation("restart evidence says durable storage was replaced or reset")
        _integer(restart_evidence.restart_count, "restart.restart_count", minimum=1)
        controls.append(
            _pass(
                current,
                "parent evidence binds the HTTP check to a PostgreSQL process restart",
                owner_dependency="PARENT",
                evidence={
                    "process_boundary_id": restart_evidence.process_boundary_id,
                    "persistence_backend": restart_evidence.persistence_backend,
                    "restart_count": restart_evidence.restart_count,
                },
            )
        )

        active_transport = transport or UrllibJsonTransport(
            config.base_url,
            timeout_seconds=config.request_timeout_seconds,
        )
        current = "VS01-BE-012"
        object_response = active_transport.request(
            "GET",
            f"/api/objects/{_path_id(checkpoint.object_id)}",
            headers=_contract_headers(),
        )
        object_body = _success_json(object_response, allowed_statuses=frozenset({200}))
        validate_research_object_detail(object_body, expected_object_id=checkpoint.object_id)
        restart_object = _mapping(object_body.get("object"), "restart.object detail.object")
        for name, expected in checkpoint.object_identity.items():
            actual = (
                object_body.get("created_at")
                if name == "created_at"
                else restart_object.get(name)
            )
            _expect(actual, expected, f"restart.object.{name}")

        run_response = active_transport.request(
            "GET",
            f"/api/research-runs/{_path_id(checkpoint.run_id)}",
            headers=_contract_headers(),
        )
        run_body = _success_json(run_response, allowed_statuses=frozenset({200}))
        validate_standalone_run_detail(
            run_body,
            object_id=checkpoint.object_id,
            goal_id=checkpoint.goal_id,
            scheme_id=checkpoint.scheme_id,
            expected_as_of=checkpoint.as_of,
            run_id=checkpoint.run_id,
            planned_graph_id=checkpoint.planned_graph_id,
        )
        projection_body, etag = _projection_request(active_transport, checkpoint.run_id)
        revision, sequence, _ = validate_atomic_run_projection(
            projection_body,
            expected_object_id=checkpoint.object_id,
            expected_goal_id=checkpoint.goal_id,
            expected_scheme_id=checkpoint.scheme_id,
            expected_as_of=checkpoint.as_of,
            expected_run_id=checkpoint.run_id,
            expected_planned_graph_id=checkpoint.planned_graph_id,
            etag=etag,
        )
        if revision < checkpoint.projection_revision:
            raise ContractViolation("projection_revision regressed across restart")
        if sequence < checkpoint.projection_sequence:
            raise ContractViolation("projection_sequence regressed across restart")
        controls.append(
            _pass(
                current,
                "exact Object/Run/projection identities survive restart without substitution",
                owner_dependency="A+PARENT",
                evidence={
                    "run_id": checkpoint.run_id,
                    "projection_revision": revision,
                    "projection_sequence": sequence,
                },
            )
        )

        current = "VS01-BE-013"
        before_replay = _object_runs(active_transport, checkpoint.object_id)
        replay_response = active_transport.request(
            "POST",
            "/api/research-runs",
            headers=_contract_headers(idempotency_key=checkpoint.confirm_idempotency_key),
            json_body=checkpoint.confirm_body,
        )
        replay_body = _success_json(replay_response, allowed_statuses=frozenset({200}))
        synthetic_draft = DraftEvidence(
            body={},
            draft_id=checkpoint.draft_id,
            draft_version=checkpoint.draft_version,
            draft_hash=checkpoint.draft_hash,
            goal_id=checkpoint.goal_id,
            scheme_id=checkpoint.scheme_id,
            run_ids_before_confirm=(),
        )
        replay_admission = validate_confirm_response(
            replay_body,
            expected_draft=synthetic_draft,
            expected_object_id=checkpoint.object_id,
            expected_replayed=True,
        )
        _expect(
            replay_admission,
            checkpoint.admission,
            "restart confirm immutable admission replay",
        )
        after_replay = _object_runs(active_transport, checkpoint.object_id)
        _expect(after_replay, before_replay, "restart confirm replay Run cardinality")
        if after_replay.count(checkpoint.run_id) != 1:
            raise ContractViolation("restart replay does not preserve exactly one admitted Run")
        controls.append(
            _pass(
                current,
                "durable Confirm replay returns the same admission and no second Run",
                owner_dependency="A+PARENT",
                evidence={
                    "run_id": checkpoint.run_id,
                    "confirm_key_sha256": hashlib.sha256(
                        checkpoint.confirm_idempotency_key.encode("utf-8")
                    ).hexdigest(),
                },
            )
        )
    except Exception as exc:
        owner = "PARENT" if current == "VS01-BE-014" else "A+PARENT"
        controls.append(_failure(current, exc, owner_dependency=owner))
    return BackendHarnessReport(phase="POST_RESTART", controls=tuple(controls))


__all__ = [
    "BackendHarnessConfig",
    "BackendHarnessReport",
    "ContractViolation",
    "ControlResult",
    "DraftEvidence",
    "HttpObservation",
    "JsonTransport",
    "RestartCheckpoint",
    "RestartEvidence",
    "TransportUnavailable",
    "UrllibJsonTransport",
    "check_confirm_admission_and_replay",
    "check_exact_run_and_projection",
    "check_object_and_initial_runs",
    "check_prepare_goal_scheme",
    "check_typed_error_contract",
    "run_backend_vs01",
    "validate_atomic_run_projection",
    "validate_availability",
    "validate_confirm_response",
    "validate_error_envelope",
    "validate_research_object_detail",
    "validate_research_run_draft",
    "validate_run_collection",
    "validate_run_detail",
    "validate_standalone_run_detail",
    "verify_restart_checkpoint",
]
