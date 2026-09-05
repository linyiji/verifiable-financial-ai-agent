"""Fail-closed JSON safety primitives for Phase 4 product projections.

Product DTOs use closed, positive allowlists.  These helpers deliberately do
not behave like a generic serializer: unknown keys, internal locator keys,
non-JSON values, non-finite numbers, and path-like string values are rejected.
Callers must choose an allowlist for each public JSON field.
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias, cast

from pydantic import JsonValue

from src.phase4_product.contracts import SafeJsonObject


class UnsafeProjectionData(ValueError):
    """Raised when data cannot be placed on the public product surface safely."""


@dataclass(frozen=True, slots=True)
class JsonKeyPattern:
    """A reviewed positive pattern for otherwise data-defined JSON object keys.

    This is intended for bounded public identifiers such as ticker symbols in
    a peer-value map.  It is not a wildcard: every key must match ``pattern``
    and still passes the unconditional protected-key check.
    """

    pattern: str
    child_allowlist: JsonAllowlist | None = None

    def __post_init__(self) -> None:
        try:
            re.compile(self.pattern)
        except re.error as exc:
            raise ValueError("invalid JSON key allowlist pattern") from exc


JsonAllowlist: TypeAlias = Collection[str] | Mapping[str, "JsonAllowlist | None"] | JsonKeyPattern

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[a-zA-Z]:[\\/]")
_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WINDOWS_PATH_ANYWHERE = re.compile(r"(?i)(?:^|[\s\"'(=])(?:[a-z]:[\\/])")
_BEARER_VALUE = re.compile(r"(?i)\b(?:authorization\s*:\s*)?bearer\s+\S+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password)"
    r"\s*[:=]\s*\S+"
)
_COMMON_CREDENTIAL_VALUE = re.compile(
    r"(?i)(?:"
    r"\bsk-[a-z0-9_-]{16,}"
    r"|\bsk_(?:live|test)_[a-z0-9]{16,}"
    r"|\bgh[pousr]_[a-z0-9]{20,}"
    r"|\bgithub_pat_[a-z0-9_]{20,}"
    r"|\bglpat-[a-z0-9_-]{16,}"
    r"|\bhf_[a-z0-9]{20,}"
    r"|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"
    r"|\bAIza[0-9A-Za-z_-]{20,}"
    r"|\bxox[baprs]-[0-9A-Za-z-]{16,}"
    r"|\beyJ[0-9A-Za-z_-]{5,}\.[0-9A-Za-z_-]{5,}\.[0-9A-Za-z_-]{5,}\b"
    r")"
)

# Exact normalized keys and key fragments that can carry secrets, private
# execution context, raw provider material, or internal storage locations.
# Public identity fields such as ``proof_refs`` and ``artifact_refs`` are not
# blanket-rejected; only internal/locator variants are prohibited.
_PROTECTED_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "id_token",
        "auth_token",
        "token",
        "api_token",
        "provider_token",
        "session_token",
        "bearer_token",
        "authorization",
        "cookie",
        "set_cookie",
        "password",
        "passwd",
        "secret",
        "secrets",
        "client_secret",
        "private_key",
        "credentials",
        "credential",
        "path",
        "file_path",
        "filepath",
        "directory",
        "working_directory",
        "cwd",
        "home_directory",
        "temp_path",
        "source_locator",
        "storage_locator",
        "raw_artifact_ref",
        "artifact_ref",
        "receipt_artifact_ref",
        "internal_ref",
        "internal_reference",
        "source_ref",
        "storage_ref",
        "blob_ref",
        "file_ref",
        "receipt_ref",
        "proof_input_ref",
        "prompt",
        "prompts",
        "system_prompt",
        "user_prompt",
        "developer_prompt",
        "prompt_template",
        "messages",
        "chat_messages",
        "conversation",
        "chain_of_thought",
        "chainofthought",
        "cot",
        "scratchpad",
        "model_scratch",
        "hidden_reasoning",
        "reasoning",
        "reasoning_trace",
        "thought",
        "analysis_trace",
        "thoughts",
        "raw_provider",
        "raw_provider_payload",
        "provider_payload",
        "provider_body",
        "provider_request",
        "provider_response",
        "raw_payload",
        "raw_response",
        "response_body",
        "request_body",
        "sql",
        "sql_query",
        "stack",
        "stack_trace",
        "stacktrace",
        "traceback",
        "exception_detail",
    }
)

_INTERNAL_LOCATOR_SCHEMES = (
    "artifact://",
    "blob://",
    "file://",
    "gs://",
    "postgres://",
    "postgresql://",
    "s3://",
    "sqlite://",
)


def normalized_key(key: str) -> str:
    """Return a stable key spelling for allowlist and protected-key checks."""

    separated = _CAMEL_BOUNDARY.sub("_", key.strip())
    return _NON_ALNUM.sub("_", separated.lower()).strip("_")


def is_protected_key(key: str) -> bool:
    """Return whether *key* names a class of data forbidden on Product DTOs."""

    normalized = normalized_key(key)
    if normalized in _PROTECTED_KEYS:
        return True
    parts = tuple(part for part in normalized.split("_") if part)
    if {"secret", "secrets", "password", "passwords", "credential", "credentials"} & set(parts):
        return True
    if "prompt" in parts:
        return True
    if "scratchpad" in parts:
        return True
    if "traceback" in parts or ("stack" in parts and "trace" in parts):
        return True
    if "raw" in parts and ({"provider", "payload", "response", "artifact"} & set(parts)):
        return True
    if "internal" in parts and ({"ref", "reference", "path", "locator"} & set(parts)):
        return True
    if "locator" in parts:
        return True
    if "path" in parts and normalized not in {"path_change_id", "path_changes"}:
        return True
    return False


def safe_text(
    value: object,
    *,
    context: str = "projection text",
    allow_empty: bool = False,
    max_length: int = 65_536,
) -> str:
    """Validate public text without interpreting or redacting it.

    Redaction can silently change business meaning.  A suspicious value is
    therefore rejected and the caller must publish typed unavailability.
    """

    if not isinstance(value, str):
        raise UnsafeProjectionData(f"{context} must be a string")
    if not allow_empty and not value.strip():
        raise UnsafeProjectionData(f"{context} must not be blank")
    if len(value) > max_length:
        raise UnsafeProjectionData(f"{context} exceeds the public size limit")
    if _CONTROL_CHARACTER.search(value):
        raise UnsafeProjectionData(f"{context} contains a control character")

    stripped = value.strip()
    lowered = stripped.lower()
    if (
        any(scheme in lowered for scheme in _INTERNAL_LOCATOR_SCHEMES)
        or any(
            path_prefix in lowered
            for path_prefix in ("/users/", "/home/", "/private/", "/tmp/", "/var/")
        )
        or _WINDOWS_ABSOLUTE_PATH.match(stripped) is not None
        or _WINDOWS_PATH_ANYWHERE.search(stripped) is not None
        or stripped.startswith(("../", "..\\"))
        or "-----begin private key-----" in lowered
        or "traceback (most recent call last)" in lowered
        or _BEARER_VALUE.search(stripped) is not None
        or _SECRET_ASSIGNMENT.search(stripped) is not None
        or _COMMON_CREDENTIAL_VALUE.search(stripped) is not None
    ):
        raise UnsafeProjectionData(f"{context} resembles protected internal data")
    return value


def safe_json(
    value: object,
    *,
    allowed_keys: JsonAllowlist,
    context: str = "projection",
    max_depth: int = 16,
    max_items: int = 10_000,
    max_string_length: int = 65_536,
) -> JsonValue:
    """Copy a JSON value through a recursive positive allowlist.

    ``allowed_keys`` may be a collection, applied to every mapping encountered,
    or a nested mapping whose values define the child schema.  A ``None`` child
    schema permits only a scalar or a sequence of scalars; it never permits an
    unreviewed nested object.
    """

    item_counter = [0]
    active: set[int] = set()
    result = _safe_json(
        value,
        allowed_keys=allowed_keys,
        context=context,
        depth=0,
        max_depth=max_depth,
        max_items=max_items,
        max_string_length=max_string_length,
        item_counter=item_counter,
        active=active,
    )
    return cast(JsonValue, result)


def safe_json_object(
    value: object,
    *,
    allowed_keys: JsonAllowlist,
    context: str = "projection",
    max_depth: int = 16,
    max_items: int = 10_000,
    max_string_length: int = 65_536,
) -> SafeJsonObject:
    """Validate and copy a public JSON object through a positive allowlist."""

    if not isinstance(value, Mapping):
        raise UnsafeProjectionData(f"{context} must be a JSON object")
    copied = safe_json(
        value,
        allowed_keys=allowed_keys,
        context=context,
        max_depth=max_depth,
        max_items=max_items,
        max_string_length=max_string_length,
    )
    if not isinstance(copied, dict):  # pragma: no cover - guarded above
        raise UnsafeProjectionData(f"{context} must be a JSON object")
    return copied


def _safe_json(
    value: object,
    *,
    allowed_keys: JsonAllowlist | None,
    context: str,
    depth: int,
    max_depth: int,
    max_items: int,
    max_string_length: int,
    item_counter: list[int],
    active: set[int],
) -> object:
    if depth > max_depth:
        raise UnsafeProjectionData(f"{context} exceeds maximum nesting depth")
    item_counter[0] += 1
    if item_counter[0] > max_items:
        raise UnsafeProjectionData(f"{context} exceeds maximum item count")

    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UnsafeProjectionData(f"{context} contains a non-finite number")
        return value
    if isinstance(value, str):
        return safe_text(
            value,
            context=context,
            allow_empty=True,
            max_length=max_string_length,
        )
    if isinstance(value, Mapping):
        if allowed_keys is None:
            raise UnsafeProjectionData(f"{context} contains an unreviewed nested object")
        marker = id(value)
        if marker in active:
            raise UnsafeProjectionData(f"{context} contains a recursive object")
        active.add(marker)
        try:
            result: dict[str, object] = {}
            for raw_key, item in value.items():
                if not isinstance(raw_key, str):
                    raise UnsafeProjectionData(f"{context} contains a non-string key")
                if is_protected_key(raw_key):
                    raise UnsafeProjectionData(f"{context} contains protected key {raw_key!r}")
                child_allowlist = _child_allowlist(allowed_keys, raw_key, context=context)
                result[raw_key] = _safe_json(
                    item,
                    allowed_keys=child_allowlist,
                    context=f"{context}.{raw_key}",
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_items=max_items,
                    max_string_length=max_string_length,
                    item_counter=item_counter,
                    active=active,
                )
            return result
        finally:
            active.remove(marker)
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | memoryview):
        marker = id(value)
        if marker in active:
            raise UnsafeProjectionData(f"{context} contains a recursive sequence")
        active.add(marker)
        try:
            return [
                _safe_json(
                    item,
                    allowed_keys=allowed_keys,
                    context=f"{context}[{index}]",
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_items=max_items,
                    max_string_length=max_string_length,
                    item_counter=item_counter,
                    active=active,
                )
                for index, item in enumerate(value)
            ]
        finally:
            active.remove(marker)
    raise UnsafeProjectionData(f"{context} contains non-JSON value {type(value).__name__}")


def _child_allowlist(
    allowed_keys: JsonAllowlist,
    key: str,
    *,
    context: str,
) -> JsonAllowlist | None:
    if isinstance(allowed_keys, JsonKeyPattern):
        if re.fullmatch(allowed_keys.pattern, key) is None:
            raise UnsafeProjectionData(f"{context} contains unapproved key {key!r}")
        return allowed_keys.child_allowlist
    if isinstance(allowed_keys, Mapping):
        if key not in allowed_keys:
            raise UnsafeProjectionData(f"{context} contains unapproved key {key!r}")
        return allowed_keys[key]
    if key not in allowed_keys:
        raise UnsafeProjectionData(f"{context} contains unapproved key {key!r}")
    return allowed_keys


__all__ = [
    "JsonAllowlist",
    "JsonKeyPattern",
    "UnsafeProjectionData",
    "is_protected_key",
    "normalized_key",
    "safe_json",
    "safe_json_object",
    "safe_text",
]
