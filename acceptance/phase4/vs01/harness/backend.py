"""Black-box Phase 4 VS01 backend acceptance checks.

This module deliberately imports no product code.  Its only authority is the frozen
``phase4-core/v1`` HTTP contract, and its observations are restricted to public HTTP
responses plus restart evidence supplied by the parent orchestrator.
"""

from __future__ import annotations

import hashlib
import json
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
AUTO_STARTED_RUN_STATUSES = frozenset({"RUNNING", "REVIEW", "PROVING", "RELEASED"})
AVAILABILITY_STATUSES = frozenset(
    {"PENDING", "AVAILABLE", "NOT_GENERATED", "NOT_RELEASED", "UNAVAILABLE", "FAILED"}
)
PATH_CHANGE_KINDS = frozenset({"SELF_CORRECTION", "ADD_TASK", "CHANGE_DEPENDENCY"})

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
            value = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
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
            payload = json.dumps(
                dict(json_body), ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
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
            if not isinstance(self.object_request[name], str) or not str(
                self.object_request[name]
            ).strip():
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


def _text(value: Any, path: str, *, prefix: str | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise ContractViolation(f"{path} must be a non-empty string")
    if prefix is not None and not value.startswith(prefix):
        raise ContractViolation(f"{path} must use canonical prefix {prefix}")
    return value


def _integer(value: Any, path: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractViolation(f"{path} must be an integer >= {minimum}")
    return value


def _number(value: Any, path: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractViolation(f"{path} must be numeric")
    result = float(value)
    if result < minimum or result > maximum:
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


def _expect(value: Any, expected: Any, path: str) -> None:
    if value != expected:
        raise ContractViolation(f"{path} must equal the frozen contract value")


def _absent(payload: Mapping[str, Any], names: set[str], path: str) -> None:
    present = names.intersection(payload)
    if present:
        raise ContractViolation(f"{path} contains excluded fields: {sorted(present)}")


def validate_availability(value: Any, path: str) -> JsonObject:
    availability = _mapping(value, path)
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


def validate_research_object_detail(
    body: JsonObject,
    *,
    expected_request: Mapping[str, Any] | None = None,
    expected_object_id: str | None = None,
) -> str:
    object_id = _text(body.get("object_id"), "object.object_id", prefix="OBJ-")
    if expected_object_id is not None:
        _expect(object_id, expected_object_id, "object.object_id")
    _expect(body.get("object_type"), "public_company", "object.object_type")
    _text(body.get("symbol"), "object.symbol")
    _text(body.get("company_name"), "object.company_name")
    _text(body.get("exchange"), "object.exchange")
    _text(body.get("currency"), "object.currency")
    _integer(body.get("identity_version"), "object.identity_version", minimum=1)
    _timestamp(body.get("created_at"), "object.created_at")
    _timestamp(body.get("updated_at"), "object.updated_at")
    _absent(
        body,
        {
            "research_object_version",
            "research_view_version",
            "research_memory",
            "comparison_dataset",
            "incremental_research_seed",
        },
        "object",
    )
    if expected_request is not None:
        _expect(body["symbol"], str(expected_request["symbol"]).strip().upper(), "object.symbol")
        for name in ("company_name", "exchange", "currency"):
            _expect(body.get(name), expected_request[name], f"object.{name}")
        _expect(body.get("sector"), expected_request.get("sector"), "object.sector")
    return object_id


def _validate_projection_object(body: JsonObject, *, expected_object_id: str) -> None:
    """Validate the smaller NormalizedObjectIdentity embedded in a Run projection."""

    _expect(body.get("object_id"), expected_object_id, "projection.object.object_id")
    _expect(body.get("object_type"), "public_company", "projection.object.object_type")
    _text(body.get("symbol"), "projection.object.symbol")
    _text(body.get("company_name"), "projection.object.company_name")
    _text(body.get("exchange"), "projection.object.exchange")
    _text(body.get("currency"), "projection.object.currency")
    _integer(body.get("identity_version"), "projection.object.identity_version", minimum=1)


def validate_run_collection(body: JsonObject, *, expected_object_id: str) -> tuple[str, ...]:
    _expect(body.get("schema_version"), "phase4-run-collection/v1", "collection.schema_version")
    items = _list(body.get("items"), "collection.items")
    cursor = body.get("next_cursor")
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise ContractViolation("collection.next_cursor must be null or a non-empty opaque string")
    run_ids: list[str] = []
    for index, raw_item in enumerate(items):
        path = f"collection.items[{index}]"
        item = _mapping(raw_item, path)
        run_id = _text(item.get("run_id"), f"{path}.run_id", prefix="RUN-")
        object_summary = _mapping(item.get("object"), f"{path}.object")
        _expect(object_summary.get("object_id"), expected_object_id, f"{path}.object.object_id")
        _text(object_summary.get("symbol"), f"{path}.object.symbol")
        _text(object_summary.get("company_name"), f"{path}.object.company_name")
        status = item.get("status")
        if status not in RUN_STAGE:
            raise ContractViolation(f"{path}.status is unsupported")
        _expect(item.get("stage"), RUN_STAGE[status], f"{path}.stage")
        progress = _mapping(item.get("progress"), f"{path}.progress")
        _expect(progress.get("method"), "ACTUAL_TASK_MEAN_V1", f"{path}.progress.method")
        _integer(progress.get("completed_tasks"), f"{path}.progress.completed_tasks", minimum=0)
        _integer(progress.get("total_tasks"), f"{path}.progress.total_tasks", minimum=0)
        _number(progress.get("fraction"), f"{path}.progress.fraction", minimum=0, maximum=1)
        _integer(item.get("projection_revision"), f"{path}.projection_revision", minimum=1)
        _integer(item.get("projection_sequence"), f"{path}.projection_sequence", minimum=0)
        terminal = item.get("terminal")
        if not isinstance(terminal, bool) or terminal != (status in TERMINAL_RUN_STATUSES):
            raise ContractViolation(f"{path}.terminal is inconsistent with status")
        validate_availability(item.get("result_availability"), f"{path}.result_availability")
        run_ids.append(run_id)
    if len(run_ids) != len(set(run_ids)):
        raise ContractViolation("collection contains duplicate Run identities")
    return tuple(run_ids)


def validate_research_run_draft(
    body: JsonObject,
    *,
    expected_object_id: str,
    expected_goal_text: str,
    expected_as_of: str,
    expected_preferences: Mapping[str, Any],
) -> DraftEvidence:
    _expect(body.get("schema_version"), "phase4-run-draft/v1", "draft.schema_version")
    draft_id = _text(body.get("draft_id"), "draft.draft_id", prefix="DRAFT-")
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
    goal_id = _text(goal.get("goal_id"), "draft.goal.goal_id", prefix="GOAL-")
    _expect(goal.get("research_object_id"), expected_object_id, "draft.goal.research_object_id")
    _expect(
        goal.get("goal_type"),
        "comprehensive_equity_research",
        "draft.goal.goal_type",
    )
    _expect(goal.get("goal_text"), expected_goal_text, "draft.goal.goal_text")
    _expect(goal.get("as_of"), expected_as_of, "draft.goal.as_of")
    _expect(goal.get("preferences"), dict(expected_preferences), "draft.goal.preferences")
    _timestamp(goal.get("created_at"), "draft.goal.created_at")

    scheme = _mapping(body.get("scheme_snapshot"), "draft.scheme_snapshot")
    scheme_id = _text(scheme.get("scheme_id"), "draft.scheme_snapshot.scheme_id", prefix="SCHEME-")
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
        _list(scheme.get(name), f"draft.scheme_snapshot.{name}")
    _mapping(scheme.get("assurance_requirements"), "draft.scheme_snapshot.assurance_requirements")
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
    _expect(
        admission.get("schema_version"),
        "phase4-run-admission/v1",
        "confirm.admission.schema_version",
    )
    _text(admission.get("admission_id"), "confirm.admission.admission_id", prefix="ADMISSION-")
    _text(admission.get("run_id"), "confirm.admission.run_id", prefix="RUN-")
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
    _text(
        admission.get("planned_graph_id"),
        "confirm.admission.planned_graph_id",
        prefix="GRAPH-",
    )
    _expect(admission.get("status"), "PLANNING", "confirm.admission.status")
    auto_start = _mapping(admission.get("auto_start"), "confirm.admission.auto_start")
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
    _expect(body.get("run_id"), run_id, "run.run_id")
    _expect(body.get("research_object_id"), object_id, "run.research_object_id")
    _expect(body.get("goal_id"), goal_id, "run.goal_id")
    _expect(body.get("scheme_id"), scheme_id, "run.scheme_id")
    _expect(body.get("planned_graph_id"), planned_graph_id, "run.planned_graph_id")
    status = body.get("status")
    if status not in RUN_STAGE:
        raise ContractViolation("run.status is unsupported")
    as_of = _text(body.get("as_of"), "run.as_of")
    try:
        date.fromisoformat(as_of)
    except ValueError as exc:
        raise ContractViolation("run.as_of must be an ISO date") from exc
    _expect(as_of, expected_as_of, "run.as_of")
    _timestamp(body.get("created_at"), "run.created_at")
    for name in ("updated_at", "started_at", "completed_at"):
        value = body.get(name)
        if value is not None:
            _timestamp(value, f"run.{name}")


def _validate_progress(value: Any, path: str) -> None:
    progress = _mapping(value, path)
    _expect(progress.get("method"), "ACTUAL_TASK_MEAN_V1", f"{path}.method")
    completed = _integer(progress.get("completed_tasks"), f"{path}.completed_tasks", minimum=0)
    total = _integer(progress.get("total_tasks"), f"{path}.total_tasks", minimum=0)
    if completed > total:
        raise ContractViolation(f"{path}.completed_tasks cannot exceed total_tasks")
    _number(progress.get("fraction"), f"{path}.fraction", minimum=0, maximum=1)


def _validate_graph(value: Any, path: str, *, run_id: str) -> str:
    graph = _mapping(value, path)
    graph_id = _text(graph.get("graph_id"), f"{path}.graph_id", prefix="GRAPH-")
    _expect(graph.get("run_id"), run_id, f"{path}.run_id")
    _integer(graph.get("version"), f"{path}.version", minimum=1)
    if "tasks" in graph:
        _list(graph["tasks"], f"{path}.tasks")
    return graph_id


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

    goal = _mapping(body.get("goal"), "projection.goal")
    _expect(goal.get("goal_id"), expected_goal_id, "projection.goal.goal_id")
    _expect(
        goal.get("research_object_id"),
        expected_object_id,
        "projection.goal.research_object_id",
    )
    scheme = _mapping(body.get("confirmed_scheme"), "projection.confirmed_scheme")
    _expect(scheme.get("scheme_id"), expected_scheme_id, "projection.confirmed_scheme.scheme_id")
    _expect(
        scheme.get("research_object_id"),
        expected_object_id,
        "projection.confirmed_scheme.research_object_id",
    )
    _expect(scheme.get("goal_id"), expected_goal_id, "projection.confirmed_scheme.goal_id")
    _timestamp(scheme.get("confirmed_at"), "projection.confirmed_scheme.confirmed_at")

    planned_graph_id = _validate_graph(
        body.get("planned_graph"),
        "projection.planned_graph",
        run_id=expected_run_id,
    )
    _expect(planned_graph_id, expected_planned_graph_id, "projection.planned_graph.graph_id")
    actual_graph = body.get("actual_graph")
    graph_version = body.get("graph_version")
    if actual_graph is None:
        if graph_version is not None:
            raise ContractViolation("projection.graph_version must be null without actual_graph")
    else:
        actual = _mapping(actual_graph, "projection.actual_graph")
        actual_graph_id = _validate_graph(actual, "projection.actual_graph", run_id=expected_run_id)
        _expect(run.get("actual_graph_id"), actual_graph_id, "projection.run.actual_graph_id")
        version = _integer(graph_version, "projection.graph_version", minimum=1)
        _expect(actual.get("version"), version, "projection.actual_graph.version")

    tasks = _list(body.get("tasks"), "projection.tasks")
    task_ids: set[str] = set()
    for index, raw_task in enumerate(tasks):
        path = f"projection.tasks[{index}]"
        task = _mapping(raw_task, path)
        task_id = _text(task.get("task_id"), f"{path}.task_id", prefix="TASK-")
        _expect(task.get("run_id"), expected_run_id, f"{path}.run_id")
        if task_id in task_ids:
            raise ContractViolation("projection contains duplicate Task identities")
        task_ids.add(task_id)

    path_changes = _list(body.get("path_changes"), "projection.path_changes")
    path_change_ids: set[str] = set()
    for index, raw_change in enumerate(path_changes):
        path = f"projection.path_changes[{index}]"
        change = _mapping(raw_change, path)
        identity = _text(change.get("path_change_id"), f"{path}.path_change_id")
        if identity in path_change_ids:
            raise ContractViolation("projection contains duplicate path-change identities")
        path_change_ids.add(identity)
        if change.get("source_kind") not in {"CORRECTION", "REPLAN"}:
            raise ContractViolation(f"{path}.source_kind is unsupported")
        _text(change.get("source_id"), f"{path}.source_id")
        if change.get("change_kind") not in PATH_CHANGE_KINDS:
            raise ContractViolation(f"{path}.change_kind is unsupported")
        for task_id in _list(change.get("task_refs"), f"{path}.task_refs"):
            if task_id not in task_ids:
                raise ContractViolation(f"{path}.task_refs contains a foreign Task")
        _list(change.get("operations"), f"{path}.operations")
        _timestamp(change.get("created_at"), f"{path}.created_at")
        if change.get("resolved_at") is not None:
            _timestamp(change["resolved_at"], f"{path}.resolved_at")

    _list(body.get("activity"), "projection.activity")
    lifecycle = _mapping(body.get("lifecycle"), "projection.lifecycle")
    _expect(lifecycle.get("status"), status, "projection.lifecycle.status")
    _expect(lifecycle.get("stage"), RUN_STAGE[status], "projection.lifecycle.stage")
    _validate_progress(lifecycle.get("progress"), "projection.lifecycle.progress")
    expected_terminal = status in TERMINAL_RUN_STATUSES
    _expect(lifecycle.get("terminal"), expected_terminal, "projection.lifecycle.terminal")

    for name in ("review", "result", "artifacts", "execution"):
        summary = _mapping(body.get(name), f"projection.{name}")
        validate_availability(summary.get("availability"), f"projection.{name}.availability")
    proof = _mapping(body.get("proof"), "projection.proof")
    validate_availability(proof.get("availability"), "projection.proof.availability")
    _list(proof.get("proof_refs"), "projection.proof.proof_refs")

    terminal = _mapping(body.get("terminal"), "projection.terminal")
    _expect(terminal.get("is_terminal"), expected_terminal, "projection.terminal.is_terminal")
    if not expected_terminal:
        for name in ("outcome", "event_id", "sequence"):
            _expect(terminal.get(name), None, f"projection.terminal.{name}")
    else:
        _text(terminal.get("outcome"), "projection.terminal.outcome")
        _text(terminal.get("event_id"), "projection.terminal.event_id", prefix="EVT-")
        _integer(terminal.get("sequence"), "projection.terminal.sequence", minimum=1)
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
    _expect(body.get("schema_version"), "phase4-error/v1", "error.schema_version")
    _absent(body, {"admission", "run_id", "result", "success"}, "error response")
    error = _mapping(body.get("error"), "error.error")
    _expect(error.get("code"), expected_code, "error.error.code")
    _text(error.get("message"), "error.error.message")
    _expect(error.get("retryable"), expected_retryable, "error.error.retryable")
    _expect(error.get("recovery"), expected_recovery, "error.error.recovery")
    request_id = error.get("request_id")
    if request_id is not None and (not isinstance(request_id, str) or not request_id):
        raise ContractViolation("error.error.request_id must be null or non-empty")
    resource = error.get("resource")
    if expected_resource_type is not None or expected_resource_id is not None:
        resource_body = _mapping(resource, "error.error.resource")
        if expected_resource_type is not None:
            _expect(resource_body.get("type"), expected_resource_type, "error.error.resource.type")
        if expected_resource_id is not None:
            _expect(resource_body.get("id"), expected_resource_id, "error.error.resource.id")
    elif resource is not None:
        resource_body = _mapping(resource, "error.error.resource")
        _text(resource_body.get("type"), "error.error.resource.type")
        _text(resource_body.get("id"), "error.error.resource.id")
    details = _mapping(error.get("details"), "error.error.details")
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
    create = transport.request(
        "POST",
        "/api/objects",
        headers=_contract_headers(idempotency_key=config.object_idempotency_key),
        json_body=config.object_request,
    )
    created_body = _success_json(create, allowed_statuses=frozenset({200, 201}))
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
        "created_at",
    )
    for name in immutable_names:
        _expect(exact_body.get(name), created_body.get(name), f"object round trip.{name}")
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
    first = transport.request(
        "POST",
        "/api/research-runs/prepare",
        headers=headers,
        json_body=prepare_body,
    )
    first_body = _success_json(first, allowed_statuses=frozenset({200, 201}))
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
    replay_body = _success_json(replay, allowed_statuses=frozenset({200, 201}))
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
    validate_run_detail(
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
                "Research Object create/read uses one exact canonical identity",
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
                "same-key replay returns the same admission and creates no second Run",
                evidence={"run_id": admitted.run_id},
            )
        )
        controls.append(
            _pass(
                "VS01-BE-009",
                "same-key changed Confirm fails with typed idempotency conflict",
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
            name: object_evidence.object_body.get(name)
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
        for name, expected in checkpoint.object_identity.items():
            _expect(object_body.get(name), expected, f"restart.object.{name}")

        run_response = active_transport.request(
            "GET",
            f"/api/research-runs/{_path_id(checkpoint.run_id)}",
            headers=_contract_headers(),
        )
        run_body = _success_json(run_response, allowed_statuses=frozenset({200}))
        validate_run_detail(
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
    "verify_restart_checkpoint",
]
