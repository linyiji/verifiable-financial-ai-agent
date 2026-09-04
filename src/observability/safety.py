from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import SecretStr

from src.domain.base import JsonObject

_SENSITIVE_KEY_PARTS = (
    "apikey",
    "authorization",
    "credential",
    "password",
    "privatekey",
    "publickey",
    "refreshtoken",
    "secret",
    "accesstoken",
    "requestbody",
    "responsebody",
    "prompt",
    "messages",
    "rawpayload",
    "normalizedvalue",
)

_SENSITIVE_EXACT_KEYS = {"content", "input", "output", "rawvalue", "token", "value"}


def sanitize_trace_attributes(
    attributes: JsonObject | None,
    *,
    sensitive_values: Sequence[SecretStr | str | None] = (),
) -> JsonObject:
    """Return JSON-safe metadata without credential-shaped fields or values."""

    return _sanitize_mapping(attributes or {}, _raw_sensitive_values(sensitive_values))


def sanitize_trace_value(
    value: Any,
    *,
    sensitive_values: Sequence[SecretStr | str | None] = (),
    drop_sensitive_fields: bool = False,
    sanitize_json_strings: bool = False,
) -> Any:
    """Sanitize any outbound trace value, including known credentials under safe keys."""

    return _sanitize_value(
        value,
        _raw_sensitive_values(sensitive_values),
        drop_sensitive_fields=drop_sensitive_fields,
        sanitize_json_strings=sanitize_json_strings,
    )


def _sanitize_mapping(
    value: Mapping[str, Any],
    sensitive_values: tuple[str, ...],
    *,
    drop_sensitive_fields: bool = False,
    sanitize_json_strings: bool = False,
) -> JsonObject:
    output: JsonObject = {}
    for key, item in value.items():
        normalized = "".join(character for character in key.casefold() if character.isalnum())
        sensitive_key = (
            normalized in _SENSITIVE_EXACT_KEYS
            or normalized.endswith("token")
            or (
                "token" in normalized
                and not normalized.endswith(("tokens", "tokencount", "tokencounts"))
            )
            or any(part in normalized for part in _SENSITIVE_KEY_PARTS)
        )
        numeric_usage_value = (
            normalized in {"input", "output"}
            and isinstance(item, (int, float))
            and not isinstance(item, bool)
        )
        if sensitive_key and not numeric_usage_value:
            if drop_sensitive_fields:
                continue
            output[key] = "[REDACTED]"
        else:
            output[key] = _sanitize_value(
                item,
                sensitive_values,
                drop_sensitive_fields=drop_sensitive_fields,
                sanitize_json_strings=sanitize_json_strings,
            )
    return output


def _sanitize_value(
    value: Any,
    sensitive_values: tuple[str, ...],
    *,
    drop_sensitive_fields: bool = False,
    sanitize_json_strings: bool = False,
) -> Any:
    if isinstance(value, SecretStr):
        return "[REDACTED]"
    if isinstance(value, str):
        if any(secret in value for secret in sensitive_values):
            return "[REDACTED]"
        if sanitize_json_strings and value.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                pass
            else:
                if isinstance(parsed, (Mapping, list)):
                    sanitized = _sanitize_value(
                        parsed,
                        sensitive_values,
                        drop_sensitive_fields=drop_sensitive_fields,
                        sanitize_json_strings=True,
                    )
                    return json.dumps(
                        sanitized,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
        return value
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return _sanitize_mapping(
            value,
            sensitive_values,
            drop_sensitive_fields=drop_sensitive_fields,
            sanitize_json_strings=sanitize_json_strings,
        )
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_value(
                item,
                sensitive_values,
                drop_sensitive_fields=drop_sensitive_fields,
                sanitize_json_strings=sanitize_json_strings,
            )
            for item in value
        ]
    return f"[{type(value).__name__}]"


def _raw_sensitive_values(values: Sequence[SecretStr | str | None]) -> tuple[str, ...]:
    raw: set[str] = set()
    for value in values:
        if isinstance(value, SecretStr):
            candidate = value.get_secret_value()
        else:
            candidate = value
        if candidate:
            raw.add(candidate)
    return tuple(sorted(raw))
