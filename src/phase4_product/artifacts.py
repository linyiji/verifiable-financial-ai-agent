"""Pure report-artifact projection and verified-byte delivery primitives."""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel

from src.phase4_product.contracts import (
    AvailabilityStatus,
    AvailabilityV1,
    ErrorCodeV1,
    ExecutionEventAnchorV1,
    RendererIdentityV1,
    ReportArtifactGroupV1,
    ReportArtifactRepresentationV1,
    RepresentationClaimAnchorV1,
    ReviewCheckAnchorV1,
    TaskAnchorV1,
)
from src.phase4_product.hashing import canonical_json_bytes, require_sha256_identity
from src.phase4_product.safety import UnsafeProjectionData, safe_json_object, safe_text

_MISSING = object()
_SHA256 = re.compile(r"^sha256:(?P<hex>[0-9a-f]{64})$")
_SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")

_AVAILABILITY_KEYS = {
    "status": None,
    "reason_code": None,
    "retryable": None,
}
_REPRESENTATION_ANCHOR_KEYS = {
    "anchor_id": None,
    "anchor_kind": None,
    "object_id": None,
    "run_id": None,
    "claim_id": None,
    "availability": _AVAILABILITY_KEYS,
    "metric_id": None,
    "report_id": None,
    "released_result_id": None,
    "canonical_record_id": None,
    "format": None,
    "artifact_id": None,
}
_REVIEW_ANCHOR_KEYS = {
    "anchor_id": None,
    "anchor_kind": None,
    "object_id": None,
    "run_id": None,
    "claim_id": None,
    "availability": _AVAILABILITY_KEYS,
    "review_id": None,
    "check_id": None,
}
_TASK_ANCHOR_KEYS = {
    "anchor_id": None,
    "anchor_kind": None,
    "object_id": None,
    "run_id": None,
    "claim_id": None,
    "availability": _AVAILABILITY_KEYS,
    "task_id": None,
}
_EXECUTION_ANCHOR_KEYS = {
    "anchor_id": None,
    "anchor_kind": None,
    "object_id": None,
    "run_id": None,
    "claim_id": None,
    "availability": _AVAILABILITY_KEYS,
    "canonical_record_id": None,
    "task_id": None,
    "event_refs": None,
}
_MANIFEST_KEYS = {
    "schema_version": None,
    "anchor_manifest_id": None,
    "anchor_manifest_sha256": None,
    "object_id": None,
    "run_id": None,
    "claim_id": None,
    "metric_id": None,
    "canonical_record_id": None,
    "released_result_id": None,
    "report_id": None,
    "representations": _REPRESENTATION_ANCHOR_KEYS,
    "review_anchors": _REVIEW_ANCHOR_KEYS,
    "task_anchors": _TASK_ANCHOR_KEYS,
    "execution_anchors": _EXECUTION_ANCHOR_KEYS,
    "created_at": None,
}


class ArtifactProjectionError(ValueError):
    """Raised when retained artifact facts do not form one exact released closure."""


@dataclass(frozen=True, slots=True)
class ArtifactRepresentationSource:
    """Explicit durable inputs for one independent HTML or PDF slot.

    ``artifact`` is present only after a successful committed generation.
    ``generation_attempt`` is the exact current/successful append-only attempt.
    No state is inferred from the absence of either record.
    """

    format: Literal["HTML", "PDF"]
    availability: AvailabilityV1
    generation_attempt_count: int
    artifact: object | None = None
    generation_attempt: object | None = None
    safe_failure_code: str | None = None
    authorized: bool = False


@dataclass(frozen=True, slots=True)
class ValidatedAnchorManifest:
    anchor_manifest_id: str
    anchor_manifest_sha256: str
    object_id: str
    run_id: str
    claim_id: str
    metric_id: str
    canonical_record_id: str
    released_result_id: str
    report_id: str
    representations: tuple[RepresentationClaimAnchorV1, RepresentationClaimAnchorV1]
    review_anchors: tuple[ReviewCheckAnchorV1, ...]
    task_anchors: tuple[TaskAnchorV1, ...]
    execution_anchors: tuple[ExecutionEventAnchorV1, ...]
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ArtifactByteIntegrityResult:
    """A verified success or a byte-empty typed failure for the HTTP adapter."""

    ok: bool
    status_code: int
    body: bytes
    headers: Mapping[str, str]
    error_code: ErrorCodeV1 | None
    reason_code: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))
        if self.ok:
            if (
                self.status_code != 200
                or self.error_code is not None
                or self.reason_code is not None
            ):
                raise ValueError("successful byte result has inconsistent status")
            if not self.body:
                raise ValueError("successful artifact bytes must not be empty")
        elif self.body or self.headers:
            raise ValueError("failed artifact delivery must expose zero protected bytes/headers")
        elif self.error_code is None or self.reason_code is None:
            raise ValueError("failed artifact delivery requires a typed safe reason")


def validate_anchor_manifest(
    manifest: object,
    *,
    expected_object_id: str,
    expected_run_id: str,
    expected_canonical_record_id: str,
    expected_released_result_id: str,
    expected_claim_id: str | None = None,
    expected_metric_id: str | None = None,
) -> ValidatedAnchorManifest:
    """Validate an immutable persisted Claim anchor manifest and its hash.

    The manifest is never generated here.  Its reviewed JSON payload, stable ID,
    and stored SHA-256 are mandatory inputs.
    """

    raw = _json_mapping(manifest, context="anchor manifest")
    try:
        payload = safe_json_object(
            raw,
            allowed_keys=_MANIFEST_KEYS,
            context="anchor manifest",
        )
    except UnsafeProjectionData as exc:
        raise ArtifactProjectionError(str(exc)) from exc

    if payload.get("schema_version") != "phase4-claim-anchor-manifest/v1":
        raise ArtifactProjectionError("anchor manifest schema version is incompatible")

    manifest_id = _required_string(payload, "anchor_manifest_id", "anchor manifest")
    manifest_hash = _required_sha256(payload, "anchor_manifest_sha256", "anchor manifest")
    object_id = _required_string(payload, "object_id", "anchor manifest")
    run_id = _required_string(payload, "run_id", "anchor manifest")
    claim_id = _required_string(payload, "claim_id", "anchor manifest")
    metric_id = _required_string(payload, "metric_id", "anchor manifest")
    canonical_id = _required_string(payload, "canonical_record_id", "anchor manifest")
    result_id = _required_string(payload, "released_result_id", "anchor manifest")
    report_id = _required_string(payload, "report_id", "anchor manifest")
    if (
        object_id != expected_object_id
        or run_id != expected_run_id
        or canonical_id != expected_canonical_record_id
        or result_id != expected_released_result_id
        or report_id != result_id
    ):
        raise ArtifactProjectionError("anchor manifest identity closure failed")
    if expected_claim_id is not None and claim_id != expected_claim_id:
        raise ArtifactProjectionError("anchor manifest belongs to another Claim")
    if expected_metric_id is not None and metric_id != expected_metric_id:
        raise ArtifactProjectionError("anchor manifest belongs to another metric")
    _coerce_datetime(payload.get("created_at"), context="anchor manifest.created_at")

    representations_raw = payload.get("representations")
    if not isinstance(representations_raw, list) or len(representations_raw) != 2:
        raise ArtifactProjectionError("anchor manifest requires exactly HTML and PDF anchors")
    representations = tuple(
        RepresentationClaimAnchorV1.model_validate(item) for item in representations_raw
    )
    if tuple(item.format for item in representations) != ("HTML", "PDF"):
        raise ArtifactProjectionError("anchor manifest representations are out of order")

    review_anchors = tuple(
        ReviewCheckAnchorV1.model_validate(item)
        for item in _required_list(payload, "review_anchors", "anchor manifest")
    )
    task_anchors = tuple(
        TaskAnchorV1.model_validate(item)
        for item in _required_list(payload, "task_anchors", "anchor manifest")
    )
    execution_anchors = tuple(
        ExecutionEventAnchorV1.model_validate(item)
        for item in _required_list(payload, "execution_anchors", "anchor manifest")
    )

    all_anchors: tuple[object, ...] = (
        *representations,
        *review_anchors,
        *task_anchors,
        *execution_anchors,
    )
    for anchor in all_anchors:
        _validate_availability(
            _field(anchor, "availability"),
            context=f"anchor {_field(anchor, 'anchor_kind')}",
        )
        if (
            _field(anchor, "object_id") != object_id
            or _field(anchor, "run_id") != run_id
            or _field(anchor, "claim_id") != claim_id
        ):
            raise ArtifactProjectionError("anchor carries a foreign object/run/Claim identity")
    for anchor in representations:
        if (
            anchor.anchor_kind != "REPORT_CLAIM"
            or anchor.metric_id != metric_id
            or anchor.report_id != report_id
            or anchor.released_result_id != result_id
            or anchor.canonical_record_id != canonical_id
        ):
            raise ArtifactProjectionError("representation Claim anchor closure failed")
    if any(anchor.anchor_kind != "REVIEW_CHECK" for anchor in review_anchors):
        raise ArtifactProjectionError("review anchor kind is invalid")
    if any(anchor.anchor_kind != "TASK" for anchor in task_anchors):
        raise ArtifactProjectionError("task anchor kind is invalid")
    if any(
        anchor.anchor_kind != "EXECUTION_EVENT" or anchor.canonical_record_id != canonical_id
        for anchor in execution_anchors
    ):
        raise ArtifactProjectionError("execution anchor closure failed")

    canonical_payload = dict(payload)
    canonical_payload.pop("anchor_manifest_sha256", None)
    actual_hash = f"sha256:{hashlib.sha256(_canonical_json(canonical_payload)).hexdigest()}"
    if actual_hash != manifest_hash:
        raise ArtifactProjectionError("anchor manifest SHA-256 does not match its payload")

    return ValidatedAnchorManifest(
        anchor_manifest_id=manifest_id,
        anchor_manifest_sha256=manifest_hash,
        object_id=object_id,
        run_id=run_id,
        claim_id=claim_id,
        metric_id=metric_id,
        canonical_record_id=canonical_id,
        released_result_id=result_id,
        report_id=report_id,
        representations=(representations[0], representations[1]),
        review_anchors=review_anchors,
        task_anchors=task_anchors,
        execution_anchors=execution_anchors,
        payload=payload,
    )


def build_report_artifact_group(
    *,
    expected_object_id: str,
    expected_run_id: str,
    run: object,
    canonical_record: object,
    released_result: object,
    anchor_manifest: object,
    html: ArtifactRepresentationSource,
    pdf: ArtifactRepresentationSource,
    availability: AvailabilityV1,
) -> ReportArtifactGroupV1:
    """Build the fixed HTML/PDF report group from explicit durable slot state."""

    run_id = _required_record_string(run, "run_id", "Run")
    object_id = _required_record_string(run, "research_object_id", "Run")
    if run_id != expected_run_id or object_id != expected_object_id:
        raise ArtifactProjectionError("Run does not match the requested object/run tuple")
    if _enum_text(_field(run, "status")) != "RELEASED":
        raise ArtifactProjectionError("report artifacts require an exact RELEASED Run")

    canonical_id = _required_record_string(canonical_record, "record_id", "canonical record")
    result_id = _required_record_string(released_result, "result_id", "released result")
    if (
        _required_record_string(canonical_record, "run_id", "canonical record") != run_id
        or _required_record_string(canonical_record, "object_snapshot_ref", "canonical record")
        != object_id
        or _required_record_string(released_result, "run_id", "released result") != run_id
        or _required_record_string(
            released_result,
            "canonical_record_id",
            "released result",
        )
        != canonical_id
    ):
        raise ArtifactProjectionError("report canonical/result identity closure failed")
    if availability.status not in {
        AvailabilityStatus.AVAILABLE,
        AvailabilityStatus.UNAVAILABLE,
    }:
        raise ArtifactProjectionError(
            "a released report group must be AVAILABLE or retained UNAVAILABLE"
        )
    _validate_availability(availability, context="report group")
    if html.format != "HTML" or pdf.format != "PDF":
        raise ArtifactProjectionError("artifact slots must be supplied as HTML then PDF")

    validated_manifest = validate_anchor_manifest(
        anchor_manifest,
        expected_object_id=object_id,
        expected_run_id=run_id,
        expected_canonical_record_id=canonical_id,
        expected_released_result_id=result_id,
    )
    html_projection = _build_representation(
        html,
        object_id=object_id,
        run_id=run_id,
        canonical_id=canonical_id,
        result_id=result_id,
    )
    pdf_projection = _build_representation(
        pdf,
        object_id=object_id,
        run_id=run_id,
        canonical_id=canonical_id,
        result_id=result_id,
    )
    html_status = html_projection.availability.status
    if html_status not in {
        AvailabilityStatus.AVAILABLE,
        AvailabilityStatus.UNAVAILABLE,
    }:
        raise ArtifactProjectionError(
            "released report must retain a successful HTML representation"
        )
    expected_group_status = (
        AvailabilityStatus.AVAILABLE
        if html_status is AvailabilityStatus.AVAILABLE
        else AvailabilityStatus.UNAVAILABLE
    )
    if availability.status is not expected_group_status:
        raise ArtifactProjectionError("report group availability disagrees with required HTML")
    if pdf_projection.availability.status is AvailabilityStatus.PENDING:
        raise ArtifactProjectionError("a terminal RELEASED Run cannot retain a PENDING PDF slot")

    html_semantic_hash = _attempt_semantic_input_sha256(html.generation_attempt)
    pdf_semantic_hash = _attempt_semantic_input_sha256(pdf.generation_attempt)
    if pdf_semantic_hash is not None and pdf_semantic_hash != html_semantic_hash:
        raise ArtifactProjectionError("HTML and PDF attempts use different semantic inputs")

    for slot, anchor in zip(
        (html_projection, pdf_projection),
        validated_manifest.representations,
        strict=True,
    ):
        if anchor.format != slot.format:
            raise ArtifactProjectionError("artifact/anchor representation format mismatch")
        if slot.availability.status in {
            AvailabilityStatus.AVAILABLE,
            AvailabilityStatus.UNAVAILABLE,
        }:
            if (
                anchor.availability.status is not AvailabilityStatus.AVAILABLE
                or anchor.artifact_id != slot.artifact_id
            ):
                raise ArtifactProjectionError(
                    "successful artifact lacks its immutable exact Claim anchor"
                )
        elif anchor.availability != slot.availability or anchor.artifact_id is not None:
            raise ArtifactProjectionError(
                "unsuccessful representation does not match its unavailable Claim anchor"
            )

    return ReportArtifactGroupV1(
        object_id=object_id,
        run_id=run_id,
        report_id=result_id,
        canonical_record_id=canonical_id,
        released_result_id=result_id,
        anchor_manifest_id=validated_manifest.anchor_manifest_id,
        anchor_manifest_sha256=validated_manifest.anchor_manifest_sha256,
        availability=availability,
        representations=(html_projection, pdf_projection),
    )


def verify_artifact_bytes(
    *,
    requested_run_id: str,
    requested_artifact_id: str | None = None,
    research_object: object | None,
    run: object | None,
    canonical_record: object | None,
    released_result: object | None,
    artifact: object | None,
    representation: object | None,
    anchor_manifest: object | None,
    payload: bytes | bytearray | memoryview | None,
) -> ArtifactByteIntegrityResult:
    """Verify the requested artifact's complete release closure before bytes escape.

    ``requested_artifact_id`` is optional only as a fail-closed compatibility seam for
    callers compiled against the earlier signature.  Omitting it never authorizes bytes.
    """

    if any(
        item is None
        for item in (
            research_object,
            run,
            canonical_record,
            released_result,
            artifact,
            representation,
            anchor_manifest,
        )
    ):
        return _byte_failure(404, ErrorCodeV1.NOT_FOUND, "ARTIFACT_NOT_FOUND")

    assert research_object is not None
    assert run is not None
    assert canonical_record is not None
    assert released_result is not None
    assert artifact is not None
    assert representation is not None
    assert anchor_manifest is not None

    try:
        requested_run_id = _required_value_string(
            requested_run_id,
            context="requested Run ID",
        )
        requested_artifact_id = _required_value_string(
            requested_artifact_id,
            context="requested artifact ID",
        )
        representation = ReportArtifactRepresentationV1.model_validate(representation)
        object_id = _required_record_string(research_object, "object_id", "research object")
        run_id = _required_record_string(run, "run_id", "Run")
        run_object_id = _required_record_string(run, "research_object_id", "Run")
        run_status = _enum_text(_field(run, "status"))
        canonical_id = _required_record_string(canonical_record, "record_id", "canonical record")
        canonical_run_id = _required_record_string(
            canonical_record,
            "run_id",
            "canonical record",
        )
        canonical_object_id = _required_record_string(
            canonical_record,
            "object_snapshot_ref",
            "canonical record",
        )
        result_id = _required_record_string(released_result, "result_id", "released result")
        result_run_id = _required_record_string(released_result, "run_id", "released result")
        result_canonical_id = _required_record_string(
            released_result,
            "canonical_record_id",
            "released result",
        )
        artifact_id = _required_record_string(artifact, "artifact_id", "artifact")
        artifact_run_id = _required_record_string(artifact, "run_id", "artifact")
        artifact_canonical_id = _required_record_string(
            artifact,
            "canonical_record_id",
            "artifact",
        )
        artifact_result_id = _required_record_string(
            artifact,
            "released_result_id",
            "artifact",
        )
        stored_content_type = _required_record_string(artifact, "artifact_type", "artifact")
        stored_hash = _required_sha256_record(artifact, "content_hash", "artifact")
        stored_size = _required_positive_int(artifact, "size_bytes", "artifact")
        if (
            run_id != requested_run_id
            or artifact_id != requested_artifact_id
            or run_object_id != object_id
            or canonical_run_id != run_id
            or canonical_object_id != object_id
            or result_run_id != run_id
            or result_canonical_id != canonical_id
            or artifact_run_id != run_id
            or artifact_canonical_id != canonical_id
            or artifact_result_id != result_id
            or representation.artifact_id != artifact_id
        ):
            return _byte_failure(
                404,
                ErrorCodeV1.IDENTITY_MISMATCH,
                "ARTIFACT_IDENTITY_MISMATCH",
            )
        if run_status != "RELEASED":
            return _byte_failure(
                500,
                ErrorCodeV1.INTEGRITY_FAILURE,
                "ARTIFACT_METADATA_INTEGRITY_FAILURE",
            )
        if representation.availability.status is not AvailabilityStatus.AVAILABLE:
            reason_code = _required_safe_code(
                representation.availability.reason_code,
                context="artifact availability reason",
            )
            return _byte_failure(
                409,
                ErrorCodeV1.UNAVAILABLE,
                reason_code,
            )
        if representation.authorized_ref != (
            f"/api/research-runs/{run_id}/artifacts/{artifact_id}/content"
        ):
            return _byte_failure(
                404,
                ErrorCodeV1.IDENTITY_MISMATCH,
                "ARTIFACT_IDENTITY_MISMATCH",
            )

        validated_manifest = validate_anchor_manifest(
            anchor_manifest,
            expected_object_id=object_id,
            expected_run_id=run_id,
            expected_canonical_record_id=canonical_id,
            expected_released_result_id=result_id,
        )
        matching_anchor = next(
            (
                item
                for item in validated_manifest.representations
                if item.format == representation.format
            ),
            None,
        )
        if (
            matching_anchor is None
            or matching_anchor.availability.status is not AvailabilityStatus.AVAILABLE
            or matching_anchor.artifact_id != artifact_id
        ):
            return _byte_failure(
                500,
                ErrorCodeV1.INTEGRITY_FAILURE,
                "ARTIFACT_ANCHOR_INTEGRITY_FAILURE",
            )
    except (ArtifactProjectionError, AttributeError, KeyError, TypeError, ValueError):
        return _byte_failure(
            500,
            ErrorCodeV1.INTEGRITY_FAILURE,
            "ARTIFACT_METADATA_INTEGRITY_FAILURE",
        )

    if not isinstance(payload, bytes | bytearray | memoryview):
        return _byte_failure(
            500,
            ErrorCodeV1.INTEGRITY_FAILURE,
            "ARTIFACT_BYTES_UNAVAILABLE",
        )
    content = bytes(payload)
    if not content:
        return _byte_failure(
            500,
            ErrorCodeV1.INTEGRITY_FAILURE,
            "ARTIFACT_EMPTY",
        )

    expected_content_type = (
        "text/html; charset=utf-8" if representation.format == "HTML" else "application/pdf"
    )
    accepted_stored_types = (
        {"text/html", "text/html; charset=utf-8"}
        if representation.format == "HTML"
        else {"application/pdf"}
    )
    digest = hashlib.sha256(content).digest()
    digest_hex = digest.hex()
    expected_hash = f"sha256:{digest_hex}"
    if (
        representation.content_type != expected_content_type
        or stored_content_type not in accepted_stored_types
        or representation.sha256 != expected_hash
        or stored_hash != expected_hash
        or representation.size_bytes != len(content)
        or stored_size != len(content)
        or not _content_matches_format(content, representation.format)
    ):
        return _byte_failure(
            500,
            ErrorCodeV1.INTEGRITY_FAILURE,
            "ARTIFACT_BYTE_INTEGRITY_FAILURE",
        )

    disposition = (
        'inline; filename="report.html"'
        if representation.format == "HTML"
        else 'attachment; filename="report.pdf"'
    )
    return ArtifactByteIntegrityResult(
        ok=True,
        status_code=200,
        body=content,
        headers={
            "Content-Type": expected_content_type,
            "Content-Length": str(len(content)),
            "Digest": f"sha-256={base64.b64encode(digest).decode('ascii')}",
            "ETag": f'"sha256-{digest_hex}"',
            "Content-Disposition": disposition,
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
        error_code=None,
        reason_code=None,
    )


def _build_representation(
    source: ArtifactRepresentationSource,
    *,
    object_id: str,
    run_id: str,
    canonical_id: str,
    result_id: str,
) -> ReportArtifactRepresentationV1:
    availability = source.availability
    _validate_availability(availability, context=f"{source.format} representation")
    if source.generation_attempt_count < 0:
        raise ArtifactProjectionError("artifact attempt count cannot be negative")
    required = source.format == "HTML"
    content_type = "text/html; charset=utf-8" if required else "application/pdf"

    if availability.status is AvailabilityStatus.NOT_GENERATED:
        if (
            source.generation_attempt_count != 0
            or source.artifact is not None
            or source.generation_attempt is not None
            or source.safe_failure_code is not None
            or source.authorized
        ):
            raise ArtifactProjectionError("NOT_GENERATED slot contains generation facts")
        return ReportArtifactRepresentationV1(
            format=source.format,
            required_for_release=required,
            content_type=content_type,
            availability=availability,
            artifact_id=None,
            safe_failure_code=None,
            generation_attempt_id=None,
            generation_attempt_count=0,
            sha256=None,
            size_bytes=None,
            renderer=None,
            generated_at=None,
            authorized_ref=None,
        )

    attempt = source.generation_attempt
    if attempt is None or source.generation_attempt_count < 1:
        raise ArtifactProjectionError("artifact slot state requires a durable generation attempt")
    attempt_id, renderer, outcome, completed_at, attempt_failure = _validate_attempt(
        attempt,
        expected_format=source.format,
        object_id=object_id,
        run_id=run_id,
        canonical_id=canonical_id,
        result_id=result_id,
    )

    if availability.status is AvailabilityStatus.PENDING:
        if (
            outcome != "PENDING"
            or completed_at is not None
            or source.artifact is not None
            or source.safe_failure_code is not None
            or source.authorized
        ):
            raise ArtifactProjectionError("PENDING slot facts are inconsistent")
        return ReportArtifactRepresentationV1(
            format=source.format,
            required_for_release=required,
            content_type=content_type,
            availability=availability,
            artifact_id=None,
            safe_failure_code=None,
            generation_attempt_id=attempt_id,
            generation_attempt_count=source.generation_attempt_count,
            sha256=None,
            size_bytes=None,
            renderer=renderer,
            generated_at=None,
            authorized_ref=None,
        )

    if availability.status is AvailabilityStatus.FAILED:
        failure_code = source.safe_failure_code
        if (
            outcome != "FAILED"
            or completed_at is None
            or source.artifact is not None
            or failure_code is None
            or failure_code != attempt_failure
            or source.authorized
        ):
            raise ArtifactProjectionError("FAILED slot facts are inconsistent")
        _required_safe_code(failure_code, context="artifact safe_failure_code")
        return ReportArtifactRepresentationV1(
            format=source.format,
            required_for_release=required,
            content_type=content_type,
            availability=availability,
            artifact_id=None,
            safe_failure_code=failure_code,
            generation_attempt_id=attempt_id,
            generation_attempt_count=source.generation_attempt_count,
            sha256=None,
            size_bytes=None,
            renderer=renderer,
            generated_at=None,
            authorized_ref=None,
        )

    if availability.status not in {AvailabilityStatus.AVAILABLE, AvailabilityStatus.UNAVAILABLE}:
        raise ArtifactProjectionError("representation uses a group-only availability state")
    artifact = source.artifact
    if artifact is None or outcome != "AVAILABLE" or completed_at is None:
        raise ArtifactProjectionError("successful slot lacks its exact artifact/attempt")
    if source.safe_failure_code is not None:
        raise ArtifactProjectionError("successful artifact cannot carry a failure code")

    artifact_id = _required_record_string(artifact, "artifact_id", "artifact")
    if (
        _required_record_string(artifact, "run_id", "artifact") != run_id
        or _required_record_string(artifact, "canonical_record_id", "artifact") != canonical_id
        or _required_record_string(artifact, "released_result_id", "artifact") != result_id
    ):
        raise ArtifactProjectionError("artifact belongs to another release closure")
    stored_type = _enum_text(_field(artifact, "artifact_type"))
    if stored_type not in (
        {"text/html", "text/html; charset=utf-8"}
        if source.format == "HTML"
        else {"application/pdf"}
    ):
        raise ArtifactProjectionError("artifact MIME type does not match its slot")
    sha256 = _required_record_string(artifact, "content_hash", "artifact")
    if _SHA256.fullmatch(sha256) is None:
        raise ArtifactProjectionError("artifact content hash is not a canonical SHA-256")
    size = _field(artifact, "size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ArtifactProjectionError("artifact size must be a positive integer")
    renderer_version = _required_record_string(artifact, "renderer_version", "artifact")
    if renderer.renderer_version != renderer_version:
        raise ArtifactProjectionError("artifact renderer does not match its generation attempt")
    generated_at = _required_datetime(artifact, "created_at", "artifact")
    if generated_at != completed_at:
        raise ArtifactProjectionError(
            "artifact generation time must equal its AVAILABLE attempt completion"
        )

    available = availability.status is AvailabilityStatus.AVAILABLE
    if available != source.authorized:
        raise ArtifactProjectionError("artifact authorization and availability disagree")
    authorized_ref = (
        f"/api/research-runs/{run_id}/artifacts/{artifact_id}/content"
        if source.authorized
        else None
    )
    return ReportArtifactRepresentationV1(
        format=source.format,
        required_for_release=required,
        content_type=content_type,
        availability=availability,
        artifact_id=artifact_id,
        safe_failure_code=None,
        generation_attempt_id=attempt_id,
        generation_attempt_count=source.generation_attempt_count,
        sha256=sha256,
        size_bytes=size,
        renderer=renderer,
        generated_at=generated_at,
        authorized_ref=authorized_ref,
    )


def _validate_attempt(
    attempt: object,
    *,
    expected_format: str,
    object_id: str,
    run_id: str,
    canonical_id: str,
    result_id: str,
) -> tuple[str, RendererIdentityV1, str, datetime | None, str | None]:
    attempt_id = _required_record_string(attempt, "attempt_id", "artifact attempt")
    if (
        _required_record_string(attempt, "object_id", "artifact attempt") != object_id
        or _required_record_string(attempt, "run_id", "artifact attempt") != run_id
        or _required_record_string(attempt, "report_id", "artifact attempt") != result_id
        or _required_record_string(attempt, "canonical_record_id", "artifact attempt")
        != canonical_id
        or _required_record_string(attempt, "released_result_id", "artifact attempt") != result_id
        or _enum_text(_field(attempt, "format")) != expected_format
    ):
        raise ArtifactProjectionError("generation attempt identity closure failed")
    outcome = _enum_text(_field(attempt, "outcome"))
    if outcome not in {"PENDING", "AVAILABLE", "FAILED"}:
        raise ArtifactProjectionError("generation attempt outcome is incompatible")
    renderer = RendererIdentityV1.model_validate(
        _json_mapping(_field(attempt, "renderer"), context="renderer")
    )
    try:
        require_sha256_identity(
            _required_record_string(attempt, "semantic_input_sha256", "artifact attempt"),
            field_name="artifact attempt.semantic_input_sha256",
        )
    except ValueError as exc:
        raise ArtifactProjectionError(str(exc)) from exc
    _required_datetime(attempt, "started_at", "artifact attempt")
    completed_value = _field(attempt, "completed_at")
    completed_at = (
        None
        if completed_value is None
        else _coerce_datetime(completed_value, context="artifact attempt.completed_at")
    )
    failure_value = _field(attempt, "safe_failure_code")
    failure_code = (
        None
        if failure_value is None
        else _required_safe_code(
            failure_value,
            context="artifact attempt safe failure code",
        )
    )
    if outcome == "FAILED" and failure_code is None:
        raise ArtifactProjectionError("failed generation attempt requires a safe failure code")
    if outcome != "FAILED" and failure_code is not None:
        raise ArtifactProjectionError("non-failed generation attempt carries a failure code")
    return attempt_id, renderer, outcome, completed_at, failure_code


def _attempt_semantic_input_sha256(attempt: object | None) -> str | None:
    if attempt is None:
        return None
    value = _required_record_string(attempt, "semantic_input_sha256", "artifact attempt")
    try:
        require_sha256_identity(value, field_name="artifact attempt.semantic_input_sha256")
    except ValueError as exc:
        raise ArtifactProjectionError(str(exc)) from exc
    return value


def _validate_availability(availability: AvailabilityV1, *, context: str) -> None:
    if availability.status is AvailabilityStatus.AVAILABLE:
        return
    _required_safe_code(availability.reason_code, context=f"{context} availability reason")


def _required_safe_code(value: object, *, context: str) -> str:
    try:
        text = safe_text(value, context=context, max_length=128)
    except UnsafeProjectionData as exc:
        raise ArtifactProjectionError(str(exc)) from exc
    if _SAFE_CODE.fullmatch(text) is None:
        raise ArtifactProjectionError(f"{context} must be a stable uppercase code")
    return text


def _byte_failure(
    status_code: int,
    error_code: ErrorCodeV1,
    reason_code: str,
) -> ArtifactByteIntegrityResult:
    return ArtifactByteIntegrityResult(
        ok=False,
        status_code=status_code,
        body=b"",
        headers={},
        error_code=error_code,
        reason_code=reason_code,
    )


def _content_matches_format(content: bytes, format_: str) -> bool:
    if format_ == "PDF":
        return content.startswith(b"%PDF-")
    try:
        text = content.decode("utf-8").lstrip().lower()
    except UnicodeDecodeError:
        return False
    return text.startswith("<!doctype html") or text.startswith("<html")


def _canonical_json(value: object) -> bytes:
    normalized = _json_value(value)
    try:
        return canonical_json_bytes(normalized)
    except (TypeError, ValueError) as exc:
        raise ArtifactProjectionError("anchor manifest is not RFC 8785 JSON") from exc


def _json_mapping(value: object, *, context: str) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        result = value.model_dump(mode="json")
    elif isinstance(value, Mapping):
        result = dict(value)
    else:
        raise ArtifactProjectionError(f"{context} must be a retained JSON object")
    normalized = _json_value(result)
    if not isinstance(normalized, dict):  # pragma: no cover - guarded above
        raise ArtifactProjectionError(f"{context} must be a retained JSON object")
    return normalized


def _json_value(value: object) -> Any:
    if isinstance(value, BaseModel):
        return _json_value(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ArtifactProjectionError("manifest timestamps must be RFC3339 UTC instants")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        raise ArtifactProjectionError("anchor manifests must not contain floating-point facts")
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ArtifactProjectionError("manifest contains a non-string key")
            result[key] = _json_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | memoryview):
        return [_json_value(item) for item in value]
    raise ArtifactProjectionError(f"manifest contains non-JSON value {type(value).__name__}")


def _field(record: object, name: str, default: object = _MISSING) -> Any:
    if isinstance(record, Mapping):
        value = record.get(name, default)
    else:
        value = getattr(record, name, default)
    if value is _MISSING and default is _MISSING:
        raise ArtifactProjectionError(f"retained record is missing required field {name}")
    return value


def _required_record_string(record: object, name: str, context: str) -> str:
    value = _field(record, name)
    if not isinstance(value, str) or not value.strip():
        raise ArtifactProjectionError(f"{context}.{name} must be a nonblank string")
    return value


def _required_value_string(value: object, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactProjectionError(f"{context} must be a nonblank string")
    return value


def _required_sha256_record(record: object, name: str, context: str) -> str:
    value = _required_record_string(record, name, context)
    if _SHA256.fullmatch(value) is None:
        raise ArtifactProjectionError(f"{context}.{name} must be a canonical SHA-256")
    return value


def _required_positive_int(record: object, name: str, context: str) -> int:
    value = _field(record, name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ArtifactProjectionError(f"{context}.{name} must be a positive integer")
    return value


def _required_string(record: Mapping[str, Any], name: str, context: str) -> str:
    value = record.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ArtifactProjectionError(f"{context}.{name} must be a nonblank string")
    return value


def _required_sha256(record: Mapping[str, Any], name: str, context: str) -> str:
    value = _required_string(record, name, context)
    if _SHA256.fullmatch(value) is None:
        raise ArtifactProjectionError(f"{context}.{name} must be a canonical SHA-256")
    return value


def _required_list(record: Mapping[str, Any], name: str, context: str) -> list[Any]:
    value = record.get(name)
    if not isinstance(value, list):
        raise ArtifactProjectionError(f"{context}.{name} must be an array")
    return value


def _required_datetime(record: object, name: str, context: str) -> datetime:
    return _coerce_datetime(_field(record, name), context=f"{context}.{name}")


def _coerce_datetime(value: object, *, context: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ArtifactProjectionError(f"{context} is not RFC3339") from exc
    else:
        raise ArtifactProjectionError(f"{context} must be a datetime")
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise ArtifactProjectionError(f"{context} must be an RFC3339 UTC instant")
    return result


def _enum_text(value: object) -> str:
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str) or not value.strip():
        raise ArtifactProjectionError("expected a nonblank enum/string value")
    return value


__all__ = [
    "ArtifactByteIntegrityResult",
    "ArtifactProjectionError",
    "ArtifactRepresentationSource",
    "ValidatedAnchorManifest",
    "build_report_artifact_group",
    "validate_anchor_manifest",
    "verify_artifact_bytes",
]
