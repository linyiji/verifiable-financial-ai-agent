from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from src.phase4_product.artifacts import ArtifactByteIntegrityResult, verify_artifact_bytes
from src.phase4_product.contracts import (
    AvailabilityV1,
    ErrorCodeV1,
    RendererIdentityV1,
    ReportArtifactRepresentationV1,
)
from src.phase4_product.hashing import canonical_json_bytes

HTML = b"<!doctype html><html><body>Released report A</body></html>"
NOW = datetime(2026, 9, 5, 10, tzinfo=UTC)


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _manifest(*, artifact_id: str = "ART-HTML-A") -> dict[str, Any]:
    manifest: dict[str, Any] = {
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
            {
                "anchor_id": "ANCHOR-HTML-A",
                "anchor_kind": "REPORT_CLAIM",
                "object_id": "OBJ-A",
                "run_id": "RUN-A",
                "claim_id": "CLAIM-A",
                "availability": AvailabilityV1.available().model_dump(mode="json"),
                "metric_id": "METRIC-A",
                "report_id": "RESULT-A",
                "released_result_id": "RESULT-A",
                "canonical_record_id": "CER-A",
                "format": "HTML",
                "artifact_id": artifact_id,
            },
            {
                "anchor_id": None,
                "anchor_kind": "REPORT_CLAIM",
                "object_id": "OBJ-A",
                "run_id": "RUN-A",
                "claim_id": "CLAIM-A",
                "availability": {
                    "status": "NOT_GENERATED",
                    "reason_code": "PDF_NOT_GENERATED_BY_POLICY",
                    "retryable": False,
                },
                "metric_id": "METRIC-A",
                "report_id": "RESULT-A",
                "released_result_id": "RESULT-A",
                "canonical_record_id": "CER-A",
                "format": "PDF",
                "artifact_id": None,
            },
        ],
        "review_anchors": [],
        "task_anchors": [],
        "execution_anchors": [],
        "created_at": "2026-09-05T10:00:00Z",
    }
    manifest["anchor_manifest_sha256"] = _sha256(canonical_json_bytes(manifest))
    return manifest


def _representation(*, artifact_id: str = "ART-HTML-A") -> ReportArtifactRepresentationV1:
    return ReportArtifactRepresentationV1(
        format="HTML",
        required_for_release=True,
        content_type="text/html; charset=utf-8",
        availability=AvailabilityV1.available(),
        artifact_id=artifact_id,
        safe_failure_code=None,
        generation_attempt_id="ATTEMPT-HTML-A",
        generation_attempt_count=1,
        sha256=_sha256(HTML),
        size_bytes=len(HTML),
        renderer=RendererIdentityV1(renderer_id="report-renderer", renderer_version="v1"),
        generated_at=NOW,
        authorized_ref=f"/api/research-runs/RUN-A/artifacts/{artifact_id}/content",
    )


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


def _verify(
    *,
    requested_artifact_id: str | None = "ART-HTML-A",
    **updates: object,
) -> ArtifactByteIntegrityResult:
    records = _records()
    records.update(updates)
    return verify_artifact_bytes(
        requested_run_id="RUN-A",
        requested_artifact_id=requested_artifact_id,
        **records,
    )


def _assert_zero_byte_failure(
    result: ArtifactByteIntegrityResult,
    *,
    status_code: int,
    error_code: ErrorCodeV1,
    reason_code: str,
) -> None:
    assert (result.status_code, result.error_code, result.reason_code) == (
        status_code,
        error_code,
        reason_code,
    )
    assert result.ok is False
    assert result.body == b""
    assert dict(result.headers) == {}


def test_explicit_requested_artifact_identity_authorizes_exact_bytes() -> None:
    result = _verify()

    assert result.ok is True
    assert result.body == HTML


def test_omitted_requested_artifact_identity_fails_closed_with_typed_result() -> None:
    records = _records()

    result = verify_artifact_bytes(requested_run_id="RUN-A", **records)

    _assert_zero_byte_failure(
        result,
        status_code=500,
        error_code=ErrorCodeV1.INTEGRITY_FAILURE,
        reason_code="ARTIFACT_METADATA_INTEGRITY_FAILURE",
    )


def test_same_run_wrong_artifact_substitution_is_bound_to_requested_artifact() -> None:
    artifact = {**_records()["artifact"], "artifact_id": "ART-HTML-B"}  # type: ignore[arg-type]

    result = _verify(
        artifact=artifact,
        representation=_representation(artifact_id="ART-HTML-B"),
        anchor_manifest=_manifest(artifact_id="ART-HTML-B"),
    )

    _assert_zero_byte_failure(
        result,
        status_code=404,
        error_code=ErrorCodeV1.IDENTITY_MISMATCH,
        reason_code="ARTIFACT_IDENTITY_MISMATCH",
    )


def test_nonreleased_run_cannot_authorize_retained_artifact_bytes() -> None:
    run = {**_records()["run"], "status": "RUNNING"}  # type: ignore[arg-type]

    result = _verify(run=run)

    _assert_zero_byte_failure(
        result,
        status_code=500,
        error_code=ErrorCodeV1.INTEGRITY_FAILURE,
        reason_code="ARTIFACT_METADATA_INTEGRITY_FAILURE",
    )


@pytest.mark.parametrize(
    ("field", "malformed_value"),
    [
        ("artifact_type", None),
        ("artifact_type", 7),
        ("content_hash", None),
        ("content_hash", "sha256:not-a-digest"),
        ("size_bytes", None),
        ("size_bytes", True),
        ("size_bytes", 0),
        ("size_bytes", "57"),
    ],
)
def test_malformed_required_artifact_metadata_is_typed_integrity_failure(
    field: str,
    malformed_value: object,
) -> None:
    artifact = deepcopy(_records()["artifact"])
    assert isinstance(artifact, dict)
    artifact[field] = malformed_value

    result = _verify(artifact=artifact)

    _assert_zero_byte_failure(
        result,
        status_code=500,
        error_code=ErrorCodeV1.INTEGRITY_FAILURE,
        reason_code="ARTIFACT_METADATA_INTEGRITY_FAILURE",
    )


@pytest.mark.parametrize("field", ["artifact_type", "content_hash", "size_bytes"])
def test_missing_required_artifact_metadata_is_typed_integrity_failure(field: str) -> None:
    artifact = deepcopy(_records()["artifact"])
    assert isinstance(artifact, dict)
    artifact.pop(field)

    result = _verify(artifact=artifact)

    _assert_zero_byte_failure(
        result,
        status_code=500,
        error_code=ErrorCodeV1.INTEGRITY_FAILURE,
        reason_code="ARTIFACT_METADATA_INTEGRITY_FAILURE",
    )


@pytest.mark.parametrize(
    ("record_name", "field"),
    [
        ("run", "research_object_id"),
        ("canonical_record", "run_id"),
        ("canonical_record", "object_snapshot_ref"),
        ("released_result", "run_id"),
        ("released_result", "canonical_record_id"),
        ("artifact", "run_id"),
        ("artifact", "canonical_record_id"),
        ("artifact", "released_result_id"),
    ],
)
def test_every_release_identity_link_rejects_foreign_identity(
    record_name: str,
    field: str,
) -> None:
    record = deepcopy(_records()[record_name])
    assert isinstance(record, dict)
    record[field] = "FOREIGN"

    result = _verify(**{record_name: record})

    _assert_zero_byte_failure(
        result,
        status_code=404,
        error_code=ErrorCodeV1.IDENTITY_MISMATCH,
        reason_code="ARTIFACT_IDENTITY_MISMATCH",
    )


@pytest.mark.parametrize(
    ("record_name", "field"),
    [
        ("research_object", "object_id"),
        ("run", "status"),
        ("canonical_record", "record_id"),
        ("released_result", "result_id"),
        ("artifact", "artifact_id"),
    ],
)
def test_missing_release_closure_metadata_never_raises(record_name: str, field: str) -> None:
    record = deepcopy(_records()[record_name])
    assert isinstance(record, dict)
    record.pop(field)

    result = _verify(**{record_name: record})

    _assert_zero_byte_failure(
        result,
        status_code=500,
        error_code=ErrorCodeV1.INTEGRITY_FAILURE,
        reason_code="ARTIFACT_METADATA_INTEGRITY_FAILURE",
    )
