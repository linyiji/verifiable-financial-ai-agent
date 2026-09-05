from __future__ import annotations

import math

import pytest

from src.phase4_product.safety import (
    UnsafeProjectionData,
    is_protected_key,
    safe_json,
    safe_json_object,
    safe_text,
)


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "apiKey",
        "Authorization",
        "bearer-token",
        "clientSecret",
        "providerCredentials",
        "raw_provider_payload",
        "rawResponse",
        "raw_artifact_ref",
        "storageLocator",
        "source_locator",
        "filePath",
        "systemPrompt",
        "chainOfThought",
        "scratchpad",
        "hiddenReasoning",
        "reasoningTrace",
        "sql_query",
        "stackTrace",
    ],
)
def test_protected_key_families_are_recognized_after_normalization(key: str) -> None:
    assert is_protected_key(key)


@pytest.mark.parametrize(
    "protected_key",
    [
        "apiKey",
        "authorization",
        "provider_secret",
        "rawProviderPayload",
        "chain_of_thought",
        "scratchpad",
        "hiddenReasoning",
        "artifactRef",
        "sourceLocator",
        "file_path",
        "stackTrace",
    ],
)
def test_recursive_projection_safety_rejects_secret_cot_and_internal_keys(
    protected_key: str,
) -> None:
    value = {
        "public": {
            "entries": [
                {"name": "safe"},
                {"name": "unsafe", protected_key: "must-never-leak"},
            ]
        }
    }
    allowlist = {
        "public": {
            "entries": {
                "name": None,
                # A protected key remains forbidden even if a caller mistakenly
                # places it in its positive allowlist.
                protected_key: None,
            }
        }
    }

    with pytest.raises(UnsafeProjectionData, match="protected key"):
        safe_json_object(value, allowed_keys=allowlist)


def test_safe_json_copies_reviewed_nested_data_without_aliasing() -> None:
    source = {
        "summary": "verified",
        "subjects": [
            {"subject_id": "CALC-A", "status": "PASS"},
            {"subject_id": "CLAIM-A", "status": "PASS"},
        ],
        "counts": [1, 2],
    }
    allowlist = {
        "summary": None,
        "subjects": {"subject_id": None, "status": None},
        "counts": None,
    }

    copied = safe_json_object(source, allowed_keys=allowlist)
    assert copied == source
    assert copied is not source
    assert copied["subjects"] is not source["subjects"]
    source["subjects"][0]["status"] = "BLOCK"  # type: ignore[index]
    assert copied["subjects"][0]["status"] == "PASS"  # type: ignore[index]


def test_positive_allowlist_rejects_unknown_nested_fields() -> None:
    with pytest.raises(UnsafeProjectionData, match="unapproved key 'debug'"):
        safe_json_object(
            {"result": {"value": "0.42", "debug": "internal"}},
            allowed_keys={"result": {"value": None}},
        )


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "artifact://reports/internal.html",
        "file:///private/report.html",
        "/Users/operator/.config/provider.json",
        "/tmp/provider-response.json",
        "../secrets/provider.env",
        "C:\\Users\\operator\\secret.txt",
        "-----BEGIN PRIVATE KEY-----\nsecret",
        "Traceback (most recent call last):\ninternal.py:1",
    ],
)
def test_safe_text_rejects_internal_locator_path_key_and_stack_values(
    unsafe_value: str,
) -> None:
    with pytest.raises(UnsafeProjectionData, match="protected internal data"):
        safe_text(unsafe_value)


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "  /Users/operator/.config/provider.json",
        "Provider result was loaded from /Users/operator/private/provider.json",
        "Temporary response retained at /tmp/provider-response.json",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret.signature",
        "Bearer top-secret-credential",
        "Provider returned Bearer top-secret-credential",
        "upstream api_key=must-never-leak",
        "sk-proj-dummycredentialvalue000000000000",
        "sk_" + "live_dummycredentialvalue000000000000",
        "ghp_dummycredentialvalue000000000000",
        "glpat-dummycredentialvalue000000000000",
        "hf_dummycredentialvalue000000000000",
        "AKIAIOSFODNN7EXAMPLE",
        "eyJhbGciOiJIUzI1NiJ9.c2Vuc2l0aXZlLWR1bW15.c2lnbmF0dXJlLWR1bW15",
    ],
)
def test_safe_text_rejects_embedded_paths_and_secret_assignments(unsafe_value: str) -> None:
    with pytest.raises(UnsafeProjectionData, match="protected internal data"):
        safe_text(unsafe_value)


def test_same_origin_authorized_resource_path_is_safe_text_not_a_bearer_locator() -> None:
    ref = "/api/research-runs/RUN-A/artifacts/ARTIFACT-A/content"
    assert safe_text(ref) == ref


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, b"raw", object()])
def test_non_json_or_non_finite_projection_values_fail_closed(value: object) -> None:
    with pytest.raises(UnsafeProjectionData):
        safe_json({"value": value}, allowed_keys={"value"})


def test_recursive_objects_and_depth_overflow_fail_closed() -> None:
    recursive: dict[str, object] = {}
    recursive["child"] = recursive
    with pytest.raises(UnsafeProjectionData, match="recursive object"):
        safe_json_object(recursive, allowed_keys={"child"})

    nested: object = "leaf"
    for _ in range(5):
        nested = [nested]
    with pytest.raises(UnsafeProjectionData, match="maximum nesting depth"):
        safe_json(nested, allowed_keys=set(), max_depth=2)


def test_none_child_allowlist_never_opens_an_unreviewed_object() -> None:
    with pytest.raises(UnsafeProjectionData, match="unreviewed nested object"):
        safe_json_object(
            {"metadata": {"surprise": "value"}},
            allowed_keys={"metadata": None},
        )
