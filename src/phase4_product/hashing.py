"""Deterministic hashes for the frozen Phase 4 product contract.

The public contract binds request and draft identities to RFC 8785 canonical
JSON.  Keeping the implementation here deliberately small makes the hashing
rule usable by HTTP, persistence, and worker adapters without giving any of
those layers authority to reinterpret a request.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from typing import Final, TypeAlias

from src.phase4_product.contracts import LOCAL_ACCESS_SCOPE, PHASE4_CONTRACT_VERSION

EFFECTIVE_ACCESS_SCOPE_KEY: Final = LOCAL_ACCESS_SCOPE
SHA256_PREFIX: Final = "sha256:"

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_MAX_SAFE_INTEGER: Final = 9_007_199_254_740_991
_HEX_DIGITS: Final = frozenset("0123456789abcdef")


class CanonicalJSONError(ValueError):
    """Raised when a value cannot be represented by the RFC 8785 profile."""


def sha256_bytes(value: bytes | bytearray | memoryview) -> str:
    """Return a lower-case, algorithm-qualified SHA-256 identity."""

    return f"{SHA256_PREFIX}{hashlib.sha256(bytes(value)).hexdigest()}"


def is_sha256_identity(value: object) -> bool:
    """Return whether *value* is exactly ``sha256:<64 lowercase hex>``."""

    if not isinstance(value, str) or len(value) != len(SHA256_PREFIX) + 64:
        return False
    if not value.startswith(SHA256_PREFIX):
        return False
    return all(character in _HEX_DIGITS for character in value[len(SHA256_PREFIX) :])


def require_sha256_identity(value: str, *, field_name: str = "hash") -> str:
    """Validate and return one canonical SHA-256 identity."""

    if not is_sha256_identity(value):
        raise ValueError(f"{field_name} must be sha256:<64 lowercase hex>")
    return value


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Serialize a strict JSON value using RFC 8785 ordering and escaping.

    Objects must have string keys, Unicode strings must not contain lone
    surrogates, integers must stay in the interoperable IEEE-754 safe range,
    and non-finite numbers are rejected.  These restrictions make hashes
    stable across the Python API process, PostgreSQL workers, and JavaScript
    consumers instead of relying on implementation-specific ``default=str``
    coercions.
    """

    return _serialize(value).encode("utf-8")


def canonical_json_sha256(value: JsonValue) -> str:
    """Hash one strict canonical JSON value."""

    return sha256_bytes(canonical_json_bytes(value))


def normalize_http_method(method: str) -> str:
    """Return the canonical upper-case HTTP method used by hash identities."""

    if not isinstance(method, str) or not method or method != method.strip():
        raise ValueError("method must be a non-empty token without surrounding whitespace")
    normalized = method.upper()
    if not normalized.isascii() or not normalized.isalpha():
        raise ValueError("method must contain ASCII letters only")
    return normalized


def normalize_route_template(route_template: str) -> str:
    """Normalize a route template without decoding or changing path identity."""

    if not isinstance(route_template, str) or not route_template:
        raise ValueError("route_template must be a non-empty path")
    if route_template != route_template.strip():
        raise ValueError("route_template must not contain surrounding whitespace")
    if not route_template.startswith("/"):
        raise ValueError("route_template must be root-relative")
    if "?" in route_template or "#" in route_template:
        raise ValueError("route_template must not contain a query or fragment")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in route_template):
        raise ValueError("route_template must not contain control characters")
    if "//" in route_template:
        raise ValueError("route_template must not contain empty path segments")
    if len(route_template) > 1 and route_template.endswith("/"):
        return route_template.rstrip("/")
    return route_template


def canonical_request_hash(
    *,
    method: str,
    route_template: str,
    body: JsonValue,
    contract_version: str = PHASE4_CONTRACT_VERSION,
    effective_access_scope_key: str = EFFECTIVE_ACCESS_SCOPE_KEY,
) -> str:
    """Hash the exact frozen request identity, excluding incidental metadata."""

    _require_contract_context(contract_version, effective_access_scope_key)
    payload: JsonValue = {
        "body": body,
        "contract_version": contract_version,
        "effective_access_scope_key": effective_access_scope_key,
        "method": normalize_http_method(method),
        "route_template": normalize_route_template(route_template),
    }
    return canonical_json_sha256(payload)


def idempotency_key_digest(
    idempotency_key: str,
    *,
    method: str,
    route_template: str,
    effective_access_scope_key: str = EFFECTIVE_ACCESS_SCOPE_KEY,
) -> str:
    """Return a non-reversible key digest scoped to method and route.

    The key is opaque: its exact UTF-8 bytes participate in the digest.  It is
    checked for a non-empty value but is never trimmed or returned from this
    helper.
    """

    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("Idempotency-Key is required and must be non-empty")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in idempotency_key):
        raise ValueError("Idempotency-Key must not contain control characters")
    _require_scope(effective_access_scope_key)
    payload: JsonValue = {
        "effective_access_scope_key": effective_access_scope_key,
        "idempotency_key": idempotency_key,
        "method": normalize_http_method(method),
        "route_template": normalize_route_template(route_template),
    }
    return canonical_json_sha256(payload)


def draft_payload_hash(payload: Mapping[str, JsonValue]) -> str:
    """Hash an immutable draft payload while excluding its ``draft_hash``."""

    if not isinstance(payload, Mapping):
        raise TypeError("draft payload must be a mapping")
    unhashed = dict(payload)
    unhashed.pop("draft_hash", None)
    return canonical_json_sha256(unhashed)


def _require_contract_context(contract_version: str, scope: str) -> None:
    if contract_version != PHASE4_CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {PHASE4_CONTRACT_VERSION}")
    _require_scope(scope)


def _require_scope(scope: str) -> None:
    if scope != EFFECTIVE_ACCESS_SCOPE_KEY:
        raise ValueError(f"effective_access_scope_key must be {EFFECTIVE_ACCESS_SCOPE_KEY}")


def _serialize(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _serialize_string(value)
    # bool is an int subclass and must be handled first.
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise CanonicalJSONError("integer exceeds the interoperable IEEE-754 safe range")
        return str(value)
    if isinstance(value, float):
        return _serialize_float(value)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalJSONError("JSON object keys must be strings")
        keys = sorted(value, key=_utf16_sort_key)
        return (
            "{"
            + ",".join(f"{_serialize_string(key)}:{_serialize(value[key])}" for key in keys)
            + "}"
        )
    raise CanonicalJSONError(f"unsupported JSON value type: {type(value).__name__}")


def _serialize_string(value: str) -> str:
    # Encoding performs the RFC 8785 requirement to reject lone surrogates.
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise CanonicalJSONError("JSON strings must not contain lone surrogates") from exc

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


def _utf16_sort_key(value: str) -> bytes:
    try:
        return value.encode("utf-16-be", errors="strict")
    except UnicodeEncodeError as exc:
        raise CanonicalJSONError("JSON object keys must not contain lone surrogates") from exc


def _serialize_float(value: float) -> str:
    if not math.isfinite(value):
        raise CanonicalJSONError("non-finite JSON numbers are forbidden")
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
    decimal_point = len(integer_part) + exponent

    leading = len(digits) - len(digits.lstrip("0"))
    if leading:
        digits = digits[leading:]
        decimal_point -= leading
    digits = digits.rstrip("0") or "0"
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
        exponent_sign = "+" if scientific_exponent >= 0 else ""
        rendered = f"{coefficient}e{exponent_sign}{scientific_exponent}"

    return f"-{rendered}" if negative else rendered
