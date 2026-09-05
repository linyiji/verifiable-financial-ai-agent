from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from src.phase4_product.contracts import (
    AvailabilityStatus,
    AvailabilityV1,
    ErrorCodeV1,
    ErrorEnvelopeV1,
    FinancialReviewProjectionV1,
    RecoveryV1,
)
from src.phase4_product.errors import error_policy, product_error
from src.phase4_product.safety import UnsafeProjectionData

ERROR_POLICY = {
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


def test_error_vocabulary_and_policy_are_exactly_frozen() -> None:
    assert {member.value for member in ErrorCodeV1} == set(ERROR_POLICY)
    for code, expected in ERROR_POLICY.items():
        status, retryable, recovery = error_policy(code)
        assert (status, retryable, recovery.value) == expected


def test_error_envelope_is_closed_and_carries_only_the_requested_resource() -> None:
    error = product_error(
        ErrorCodeV1.IDENTITY_MISMATCH,
        "The requested resource does not belong to this run.",
        resource_type="research_run",
        resource_id="RUN-requested",
        details={"reason_code": "RUN_OWNERSHIP_MISMATCH"},
    )

    assert error.status_code == 404
    assert error.envelope(request_id="REQ-opaque").model_dump(mode="json") == {
        "schema_version": "phase4-error/v1",
        "error": {
            "code": "IDENTITY_MISMATCH",
            "message": "The requested resource does not belong to this run.",
            "retryable": False,
            "recovery": "NONE",
            "request_id": "REQ-opaque",
            "resource": {"type": "research_run", "id": "RUN-requested"},
            "details": {"reason_code": "RUN_OWNERSHIP_MISMATCH"},
        },
    }


@pytest.mark.parametrize("legacy_code", ["RESOURCE_NOT_FOUND", "RESULT_NOT_RELEASED"])
def test_legacy_error_names_are_not_public_vocabulary(legacy_code: str) -> None:
    with pytest.raises(ValueError):
        product_error(legacy_code, "legacy names must be mapped before the product boundary")


def test_error_envelope_rejects_unknown_fields_and_non_json_details() -> None:
    valid = product_error(ErrorCodeV1.INTERNAL_ERROR, "Safe failure").envelope()
    payload = valid.model_dump(mode="python")
    payload["debug"] = "stack trace"
    with pytest.raises(ValidationError):
        ErrorEnvelopeV1.model_validate(payload)

    with pytest.raises((ValidationError, UnsafeProjectionData)):
        product_error(
            ErrorCodeV1.INTERNAL_ERROR,
            "Safe failure",
            details={"exception": object()},
        ).envelope()


@pytest.mark.parametrize(
    "unsafe_message",
    [
        "/Users/operator/.config/provider-secret.json",
        "artifact://private/report.html",
        "-----BEGIN PRIVATE KEY-----\nsecret",
        "Traceback (most recent call last):\ninternal.py:1",
    ],
)
def test_error_message_rejects_internal_paths_keys_and_stack_traces(
    unsafe_message: str,
) -> None:
    with pytest.raises(UnsafeProjectionData):
        product_error(ErrorCodeV1.INTERNAL_ERROR, unsafe_message)


@pytest.mark.parametrize(
    "protected_key",
    ["api_key", "providerCredentials", "authorization", "chainOfThought", "scratchpad"],
)
def test_error_details_reject_secret_and_hidden_reasoning_keys(protected_key: str) -> None:
    with pytest.raises(UnsafeProjectionData):
        product_error(
            ErrorCodeV1.INTERNAL_ERROR,
            "Safe failure",
            details={protected_key: "must-never-leak"},
        )


def test_error_resource_type_and_identifier_are_safely_allowlisted() -> None:
    with pytest.raises(ValueError, match="resource type"):
        product_error(
            ErrorCodeV1.NOT_FOUND,
            "Missing",
            resource_type="database_row",
            resource_id="ROW-1",
        )
    with pytest.raises(UnsafeProjectionData):
        product_error(
            ErrorCodeV1.NOT_FOUND,
            "Missing",
            resource_type="report_artifact",
            resource_id="/private/report.html",
        )


def test_availability_has_closed_vocabulary_and_reason_invariant() -> None:
    assert {member.value for member in AvailabilityStatus} == {
        "PENDING",
        "AVAILABLE",
        "NOT_GENERATED",
        "NOT_RELEASED",
        "UNAVAILABLE",
        "FAILED",
    }
    assert AvailabilityV1.available().model_dump(mode="json") == {
        "status": "AVAILABLE",
        "reason_code": None,
        "retryable": False,
    }

    with pytest.raises(ValidationError):
        AvailabilityV1(status="AVAILABLE", reason_code="SHOULD_BE_NULL")
    with pytest.raises(ValidationError):
        AvailabilityV1(status="UNAVAILABLE", reason_code=None)
    with pytest.raises(ValidationError):
        AvailabilityV1(status="UNKNOWN", reason_code="UNKNOWN")


def test_absent_review_stays_absent_and_old_verdict_is_rejected() -> None:
    unavailable = AvailabilityV1.unavailable(
        AvailabilityStatus.NOT_GENERATED,
        "REVIEW_NOT_GENERATED",
    )
    projection = FinancialReviewProjectionV1(
        projection_revision=1,
        projection_sequence=0,
        object_id="OBJ-A",
        run_id="RUN-A",
        canonical_record_id=None,
        released_result_id=None,
        review_id=None,
        status=None,
        reviewer=None,
        input_snapshot_hash=None,
        availability=unavailable,
    )
    assert projection.status is None
    assert projection.checks == ()

    bad = projection.model_dump(mode="python")
    bad.update(
        {
            "review_id": "REVIEW-A",
            "status": "PASS_WITH_UNCERTAINTY",
            "reviewer": "independent-financial-review-v2",
            "input_snapshot_hash": "sha256:" + "a" * 64,
            "availability": AvailabilityV1.available(),
        }
    )
    with pytest.raises(ValidationError):
        FinancialReviewProjectionV1.model_validate(bad)


def test_recovery_vocabulary_is_exact() -> None:
    assert {member.value for member in RecoveryV1} == {
        "NONE",
        "RETRY",
        "SNAPSHOT_RELOAD",
        "REAUTHENTICATE",
    }


def test_contract_models_are_immutable() -> None:
    availability = AvailabilityV1.available()
    with pytest.raises(ValidationError):
        availability.reason_code = "MUTATED"  # type: ignore[misc]


def test_review_nullability_pair_rejects_torn_release_identity() -> None:
    with pytest.raises(ValidationError, match="both null or both present"):
        FinancialReviewProjectionV1(
            projection_revision=3,
            projection_sequence=8,
            object_id="OBJ-A",
            run_id="RUN-A",
            canonical_record_id="CER-A",
            released_result_id=None,
            review_id=None,
            status=None,
            reviewer=None,
            input_snapshot_hash=None,
            availability=AvailabilityV1.unavailable(
                AvailabilityStatus.PENDING,
                "REVIEW_PENDING",
            ),
        )


def _unused_frozen_contract_examples() -> tuple[date, datetime]:
    """Keep type-checkers aware of the wire date/time types used by this suite."""

    return date(2026, 9, 5), datetime(2026, 9, 5, tzinfo=UTC)
