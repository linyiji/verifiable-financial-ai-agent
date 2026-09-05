from __future__ import annotations

import hashlib
import json
import math

import pytest

from src.phase4_product.hashing import (
    CanonicalJSONError,
    canonical_json_bytes,
    canonical_request_hash,
    draft_payload_hash,
    idempotency_key_digest,
    is_sha256_identity,
    normalize_http_method,
    normalize_route_template,
)


def _qualified_sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def test_canonical_json_is_order_independent_and_uses_compact_utf8() -> None:
    first = {"z": [True, None, "研究"], "a": {"two": 2, "one": 1}}
    second = {"a": {"one": 1, "two": 2}, "z": [True, None, "研究"]}
    expected = '{"a":{"one":1,"two":2},"z":[true,null,"研究"]}'.encode()

    assert canonical_json_bytes(first) == expected
    assert canonical_json_bytes(second) == expected


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, {"x": object()}])
def test_canonical_json_rejects_values_that_cannot_be_hashed_portably(bad: object) -> None:
    with pytest.raises(CanonicalJSONError):
        canonical_json_bytes(bad)  # type: ignore[arg-type]


def test_request_hash_binds_exact_contract_scope_method_route_and_body() -> None:
    body = {
        "draft_id": "DRAFT-A",
        "draft_version": 1,
        "draft_hash": "sha256:" + "1" * 64,
        "research_object_id": "OBJ-A",
        "confirm_scheme": True,
    }
    canonical_payload = {
        "body": body,
        "contract_version": "phase4-core/v1",
        "effective_access_scope_key": "LOCAL_SINGLE_USER",
        "method": "POST",
        "route_template": "/api/research-runs",
    }
    expected_bytes = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

    assert canonical_request_hash(
        method="post",
        route_template="/api/research-runs/",
        body=body,
    ) == _qualified_sha256(expected_bytes)


def test_idempotency_key_is_not_part_of_confirmation_request_hash() -> None:
    body = {
        "draft_id": "DRAFT-A",
        "draft_version": 1,
        "draft_hash": "sha256:" + "2" * 64,
        "research_object_id": "OBJ-A",
        "confirm_scheme": True,
    }
    request_hash = canonical_request_hash(
        method="POST",
        route_template="/api/research-runs",
        body=body,
    )
    key_a = idempotency_key_digest(
        "client-attempt-a",
        method="POST",
        route_template="/api/research-runs",
    )
    key_b = idempotency_key_digest(
        "client-attempt-b",
        method="POST",
        route_template="/api/research-runs",
    )

    assert key_a != key_b
    assert request_hash == canonical_request_hash(
        method="POST",
        route_template="/api/research-runs",
        body=body,
    )


def test_draft_hash_excludes_only_its_own_hash_field() -> None:
    payload = {
        "schema_version": "phase4-run-draft/v1",
        "draft_id": "DRAFT-A",
        "draft_version": 1,
        "object_id": "OBJ-A",
        "draft_hash": "sha256:" + "0" * 64,
    }
    without_hash = {key: value for key, value in payload.items() if key != "draft_hash"}

    assert draft_payload_hash(payload) == draft_payload_hash(without_hash)
    assert draft_payload_hash(payload) == _qualified_sha256(canonical_json_bytes(without_hash))
    assert draft_payload_hash({**payload, "draft_version": 2}) != draft_payload_hash(payload)


@pytest.mark.parametrize(
    ("method", "expected"),
    [("post", "POST"), ("GET", "GET")],
)
def test_http_method_normalization_is_exact(method: str, expected: str) -> None:
    assert normalize_http_method(method) == expected


@pytest.mark.parametrize("bad", [" POST", "POST ", "", "P0ST", "P/OST"])
def test_invalid_http_method_is_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        normalize_http_method(bad)


def test_route_normalization_removes_only_terminal_slashes() -> None:
    assert normalize_route_template("/api/research-runs/") == "/api/research-runs"
    for bad in ("api/research-runs", "/api//research-runs", "/api/runs?q=1", " /api/runs"):
        with pytest.raises(ValueError):
            normalize_route_template(bad)


@pytest.mark.parametrize(
    ("candidate", "valid"),
    [
        ("sha256:" + "a" * 64, True),
        ("sha256:" + "A" * 64, False),
        ("sha256:" + "a" * 63, False),
        ("a" * 64, False),
        (None, False),
    ],
)
def test_sha256_identity_format_is_closed(candidate: object, valid: bool) -> None:
    assert is_sha256_identity(candidate) is valid
