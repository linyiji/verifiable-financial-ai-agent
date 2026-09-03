from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from src.domain.base import JsonObject

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "credential",
    "password",
    "private_key",
    "public_key",
    "refresh_token",
    "secret",
    "access_token",
)


def sanitize_trace_attributes(attributes: JsonObject | None) -> JsonObject:
    """Return JSON-safe metadata without credential-shaped fields or values."""

    return _sanitize_mapping(attributes or {})


def _sanitize_mapping(value: dict[str, Any]) -> JsonObject:
    output: JsonObject = {}
    for key, item in value.items():
        normalized = key.lower().replace("-", "_")
        if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
            output[key] = "[REDACTED]"
        else:
            output[key] = _sanitize_value(item)
    return output


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, SecretStr):
        return "[REDACTED]"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return _sanitize_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value]
    return f"[{type(value).__name__}]"
