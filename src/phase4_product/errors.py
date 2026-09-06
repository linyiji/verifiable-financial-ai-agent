"""Typed Phase 4 product errors and safe envelope construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.phase4_product.contracts import (
    ErrorBodyV1,
    ErrorCodeV1,
    ErrorEnvelopeV1,
    ErrorResourceV1,
    RecoveryV1,
)
from src.phase4_product.safety import safe_json_object, safe_text

_PUBLIC_RESOURCE_TYPES = frozenset(
    {
        "anchor_manifest",
        "calculation",
        "canonical_execution",
        "claim",
        "evidence",
        "graph",
        "idempotency_outcome",
        "projection",
        "proof",
        "released_result",
        "report",
        "report_artifact",
        "research_goal",
        "research_object",
        "research_run",
        "research_run_draft",
        "research_scheme",
        "results_workspace",
        "review",
        "scheduler_admission",
        "task",
        "trace_bundle",
    }
)

# Complete positive allowlist for detail shapes emitted by this isolated
# surface. Extending it is a public-contract decision, not a serializer
# convenience.
_PUBLIC_DETAIL_ALLOWLIST = {
    "errors": {"location": None, "type": None},
    "field": None,
    "reason_code": None,
    "supported_version": None,
}

_ERROR_POLICY: dict[ErrorCodeV1, tuple[int, bool, RecoveryV1]] = {
    ErrorCodeV1.INVALID_CURSOR: (400, False, RecoveryV1.SNAPSHOT_RELOAD),
    ErrorCodeV1.UNAUTHENTICATED: (401, False, RecoveryV1.REAUTHENTICATE),
    ErrorCodeV1.FORBIDDEN: (403, False, RecoveryV1.NONE),
    ErrorCodeV1.NOT_FOUND: (404, False, RecoveryV1.NONE),
    ErrorCodeV1.IDENTITY_MISMATCH: (404, False, RecoveryV1.NONE),
    ErrorCodeV1.UNAVAILABLE: (409, False, RecoveryV1.NONE),
    ErrorCodeV1.NOT_GENERATED: (409, False, RecoveryV1.NONE),
    ErrorCodeV1.NOT_RELEASED: (409, False, RecoveryV1.SNAPSHOT_RELOAD),
    ErrorCodeV1.CONFLICT: (409, False, RecoveryV1.NONE),
    ErrorCodeV1.CURSOR_AHEAD: (409, False, RecoveryV1.SNAPSHOT_RELOAD),
    ErrorCodeV1.SCHEMA_INCOMPATIBLE: (409, False, RecoveryV1.NONE),
    ErrorCodeV1.UNSUPPORTED_EVENT: (409, False, RecoveryV1.SNAPSHOT_RELOAD),
    ErrorCodeV1.TERMINAL: (409, False, RecoveryV1.NONE),
    ErrorCodeV1.REQUEST_VALIDATION_ERROR: (422, False, RecoveryV1.NONE),
    ErrorCodeV1.INTEGRITY_FAILURE: (500, False, RecoveryV1.SNAPSHOT_RELOAD),
    ErrorCodeV1.INTERNAL_ERROR: (500, False, RecoveryV1.NONE),
    ErrorCodeV1.TRANSIENT_BACKEND_ERROR: (503, True, RecoveryV1.RETRY),
}


@dataclass(slots=True)
class ProductError(Exception):
    code: ErrorCodeV1
    message: str
    resource_type: str | None = None
    resource_id: str | None = None
    details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)
        if not self.message.strip():
            raise ValueError("ProductError message must not be blank")
        if (self.resource_type is None) != (self.resource_id is None):
            raise ValueError("resource type and id must be supplied together")
        safe_text(self.message, context="error.message")
        if self.resource_type is not None:
            if self.resource_type not in _PUBLIC_RESOURCE_TYPES:
                raise ValueError("resource type is not public-contract allowlisted")
            safe_text(self.resource_id, context="error.resource.id")
        if self.details is not None:
            self.details = safe_json_object(
                self.details,
                allowed_keys=_PUBLIC_DETAIL_ALLOWLIST,
                context="error.details",
                max_depth=4,
                max_items=100,
                max_string_length=512,
            )

    @property
    def status_code(self) -> int:
        return _ERROR_POLICY[self.code][0]

    def envelope(self, *, request_id: str | None = None) -> ErrorEnvelopeV1:
        _, retryable, recovery = _ERROR_POLICY[self.code]
        resource = None
        if self.resource_type is not None and self.resource_id is not None:
            resource = ErrorResourceV1(type=self.resource_type, id=self.resource_id)
        return ErrorEnvelopeV1(
            error=ErrorBodyV1(
                code=self.code,
                message=self.message,
                retryable=retryable,
                recovery=recovery,
                request_id=request_id,
                resource=resource,
                details=self.details or {},
            )
        )


def product_error(
    code: ErrorCodeV1 | str,
    message: str,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> ProductError:
    """Create a typed error while accepting only the frozen vocabulary."""

    return ProductError(
        code=ErrorCodeV1(code),
        message=message,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )


def error_policy(code: ErrorCodeV1 | str) -> tuple[int, bool, RecoveryV1]:
    return _ERROR_POLICY[ErrorCodeV1(code)]
