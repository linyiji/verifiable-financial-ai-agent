"""Lossless bounded projection for structured financial identity/support only."""

import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

SEMANTIC_KEYS = frozenset(
    {
        "period",
        "period_end",
        "period_start",
        "fiscal_year",
        "fiscal_period",
        "as_of",
        "currency",
        "unit",
        "units",
        "symbol",
        "ticker",
        "support",
        "support_refs",
        "evidence_id",
        "evidence_ids",
        "input_evidence_ids",
        "calculation_id",
        "formula_id",
        "supporting_evidence_ids",
        "supporting_calculation_ids",
        "calculation_type",
        "capability_id",
        "formula_version",
        "schema_version",
        "normalized_field",
        "normalized_value",
        "value",
        "values",
        "sign",
    }
)
MAX_SEMANTIC_BYTES = 32768


def semantic_key(key):
    key = str(key)
    return key in SEMANTIC_KEYS or key.endswith(
        ("_id", "_ids", "_ref", "_refs", "_hash", "_hashes")
    )


def contains_semantics(value, *, depth=0):
    if depth > 64:
        raise ValueError("CONTEXT_SEMANTICS_DEPTH_EXCEEDED")
    if isinstance(value, dict):
        return any(semantic_key(k) for k in value) or any(
            contains_semantics(v, depth=depth + 1) for v in value.values()
        )
    if isinstance(value, (tuple, list)):
        return any(contains_semantics(v, depth=depth + 1) for v in value)
    return False


def normalize_semantics(value):
    """Preserve one semantic field/record, never the mixed outer context."""

    def normalize(item, depth=0):
        if depth > 64:
            raise ValueError("CONTEXT_SEMANTICS_DEPTH_EXCEEDED")
        if item is None or isinstance(item, (str, bool, int, float)):
            return item
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, Enum):
            return item.value
        if isinstance(item, dict):
            return {str(k): normalize(v, depth + 1) for k, v in item.items()}
        if isinstance(item, (tuple, list)):
            return [normalize(v, depth + 1) for v in item]
        raise ValueError("CONTEXT_SEMANTICS_UNSUPPORTED_TYPE")

    result = normalize(value)
    check_semantic_bound(result)
    return result


def check_semantic_bound(value):
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode()) > MAX_SEMANTIC_BYTES:
        raise ValueError("CONTEXT_SEMANTICS_EXCEED_BOUND")
