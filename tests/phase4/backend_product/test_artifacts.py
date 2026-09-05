from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime

import pytest

from src.phase4_product.artifacts import ArtifactByteIntegrityResult, verify_artifact_bytes
from src.phase4_product.contracts import (
    AvailabilityStatus,
    AvailabilityV1,
    ErrorCodeV1,
    RendererIdentityV1,
    ReportArtifactRepresentationV1,
)

NOW = datetime(2026, 9, 5, 10, tzinfo=UTC)
HTML = b"<!doctype html><html><body>Verified report</body></html>"


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _representation(
    *,
    availability: AvailabilityV1 | None = None,
    authorized_ref: str | None = "/api/research-runs/RUN-A/artifacts/ART-HTML-A/content",
) -> ReportArtifactRepresentationV1:
    return ReportArtifactRepresentationV1(
        format="HTML",
        required_for_release=True,
        content_type="text/html; charset=utf-8",
        availability=availability or AvailabilityV1.available(),
        artifact_id="ART-HTML-A",
        safe_failure_code=None,
        generation_attempt_id="ATTEMPT-HTML-A",
        generation_attempt_count=1,
        sha256=_sha256(HTML),
        size_bytes=len(HTML),
        renderer=RendererIdentityV1(renderer_id="report-renderer", renderer_version="v1"),
        generated_at=NOW,
        authorized_ref=authorized_ref,
    )


def _anchor(
    *,
    format_: str,
    artifact_id: str | None,
    available: bool,
) -> dict[str, object]:
    return {
        "anchor_id": f"ANCHOR-{format_}-A" if available else None,
        "anchor_kind": "REPORT_CLAIM",
        "object_id": "OBJ-A",
        "run_id": "RUN-A",
        "claim_id": "CLAIM-A",
        "availability": (
            AvailabilityV1.available().model_dump(mode="json")
            if available
            else AvailabilityV1.unavailable(
                AvailabilityStatus.NOT_GENERATED,
                "PDF_NOT_GENERATED_BY_POLICY",
            ).model_dump(mode="json")
        ),
        "metric_id": "METRIC-A",
        "report_id": "RESULT-A",
        "released_result_id": "RESULT-A",
        "canonical_record_id": "CER-A",
        "format": format_,
        "artifact_id": artifact_id,
    }


def _manifest() -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema_version": "phase4-claim-anchor-manifest/v1",
        "anchor_manifest_id": "ANCHOR-MANIFEST-A",
        "object_id": "OBJ-A",
        "run_id": "RUN-A",
        "claim_id": "CLAIM-A",
        "metric_id": "METRIC-A",
        "canonical_record_id": "CER-A",
        "released_result_id": "RESULT-A",
        "report_id": "RESULT-A",
        "representations": [
            _anchor(format_="HTML", artifact_id="ART-HTML-A", available=True),
            _anchor(format_="PDF", artifact_id=None, available=False),
        ],
        "review_anchors": [],
        "task_anchors": [],
        "execution_anchors": [],
        "created_at": "2026-09-05T10:00:00Z",
    }
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    manifest["anchor_manifest_sha256"] = _sha256(canonical)
    return manifest


def _records() -> dict[str, object]:
    return {
        "research_object": {"object_id": "OBJ-A"},
        "run": {
            "run_id": "RUN-A",
            "research_object_id": "OBJ-A",
            "status": "RELEASED",
        },
        "canonical_record": {
            "record_id": "CER-A",
            "run_id": "RUN-A",
            "object_snapshot_ref": "OBJ-A",
        },
        "released_result": {
            "result_id": "RESULT-A",
            "run_id": "RUN-A",
            "canonical_record_id": "CER-A",
        },
        "artifact": {
            "artifact_id": "ART-HTML-A",
            "run_id": "RUN-A",
            "canonical_record_id": "CER-A",
            "released_result_id": "RESULT-A",
            "artifact_type": "text/html; charset=utf-8",
            "content_hash": _sha256(HTML),
            "size_bytes": len(HTML),
        },
        "representation": _representation(),
        "anchor_manifest": _manifest(),
        "payload": HTML,
    }


def _verify(**updates: object) -> ArtifactByteIntegrityResult:
    values = _records()
    values.update(updates)
    return verify_artifact_bytes(
        requested_run_id="RUN-A",
        requested_artifact_id="ART-HTML-A",
        **values,
    )


def test_verified_artifact_returns_exact_bytes_and_security_headers() -> None:
    result = _verify()
    digest = hashlib.sha256(HTML).digest()
    digest_hex = digest.hex()

    assert result.ok is True
    assert result.status_code == 200
    assert result.body == HTML
    assert dict(result.headers) == {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Length": str(len(HTML)),
        "Digest": f"sha-256={base64.b64encode(digest).decode('ascii')}",
        "ETag": f'"sha256-{digest_hex}"',
        "Content-Disposition": 'inline; filename="report.html"',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    assert result.error_code is None
    assert result.reason_code is None


@pytest.mark.parametrize(
    ("updates", "status", "code", "reason"),
    [
        ({"artifact": None}, 404, ErrorCodeV1.NOT_FOUND, "ARTIFACT_NOT_FOUND"),
        ({"payload": None}, 500, ErrorCodeV1.INTEGRITY_FAILURE, "ARTIFACT_BYTES_UNAVAILABLE"),
        ({"payload": b""}, 500, ErrorCodeV1.INTEGRITY_FAILURE, "ARTIFACT_EMPTY"),
        (
            {"payload": HTML + b"tampered"},
            500,
            ErrorCodeV1.INTEGRITY_FAILURE,
            "ARTIFACT_BYTE_INTEGRITY_FAILURE",
        ),
        (
            {"payload": b"not html"},
            500,
            ErrorCodeV1.INTEGRITY_FAILURE,
            "ARTIFACT_BYTE_INTEGRITY_FAILURE",
        ),
    ],
)
def test_artifact_failures_release_zero_protected_bytes_or_headers(
    updates: dict[str, object],
    status: int,
    code: ErrorCodeV1,
    reason: str,
) -> None:
    result = _verify(**updates)
    assert result.ok is False
    assert result.status_code == status
    assert result.error_code is code
    assert result.reason_code == reason
    assert result.body == b""
    assert dict(result.headers) == {}


def test_cross_run_artifact_substitution_is_404_and_zero_bytes() -> None:
    records = _records()
    foreign = {**records["artifact"], "run_id": "RUN-B"}  # type: ignore[arg-type]
    result = _verify(artifact=foreign)

    assert (result.status_code, result.error_code, result.reason_code) == (
        404,
        ErrorCodeV1.IDENTITY_MISMATCH,
        "ARTIFACT_IDENTITY_MISMATCH",
    )
    assert result.body == b""
    assert dict(result.headers) == {}


def test_tampered_anchor_manifest_is_integrity_failure_and_zero_bytes() -> None:
    manifest = _manifest()
    manifest["claim_id"] = "CLAIM-TAMPERED"
    result = _verify(anchor_manifest=manifest)

    assert (result.status_code, result.error_code, result.reason_code) == (
        500,
        ErrorCodeV1.INTEGRITY_FAILURE,
        "ARTIFACT_METADATA_INTEGRITY_FAILURE",
    )
    assert result.body == b""
    assert dict(result.headers) == {}


def test_retained_but_unavailable_artifact_returns_typed_409_and_zero_bytes() -> None:
    unavailable = AvailabilityV1.unavailable(
        AvailabilityStatus.UNAVAILABLE,
        "RETENTION_EXPIRED",
    )
    result = _verify(
        representation=_representation(
            availability=unavailable,
            authorized_ref=None,
        )
    )

    assert (result.status_code, result.error_code, result.reason_code) == (
        409,
        ErrorCodeV1.UNAVAILABLE,
        "RETENTION_EXPIRED",
    )
    assert result.body == b""
    assert dict(result.headers) == {}


def test_failure_result_type_itself_forbids_accidental_byte_or_header_leakage() -> None:
    with pytest.raises(ValueError, match="zero protected bytes/headers"):
        ArtifactByteIntegrityResult(
            ok=False,
            status_code=500,
            body=b"partial protected bytes",
            headers={"X-Internal-Path": "/private/report.html"},
            error_code=ErrorCodeV1.INTEGRITY_FAILURE,
            reason_code="ARTIFACT_BYTE_INTEGRITY_FAILURE",
        )
