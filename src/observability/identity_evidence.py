"""Deterministic retained evidence for Langfuse observation identity closure."""

from __future__ import annotations

from collections import Counter

from src.domain.base import JsonObject
from src.observability.langfuse_adapter import LangfuseTraceRedactionAudit


def build_langfuse_identity_set_evidence(
    *,
    run_id: str,
    trace_id: str,
    audit: LangfuseTraceRedactionAudit,
) -> JsonObject:
    """Project an audit into stable, independently recomputable retained evidence."""

    if not run_id.strip():
        raise ValueError("run_id must not be blank")
    if not trace_id.strip():
        raise ValueError("trace_id must not be blank")
    if audit.expected_observation_identities is None:
        raise ValueError("exact expected observation identities are required")

    expected = tuple(sorted(audit.expected_observation_identities))
    observed = tuple(sorted(audit.observed_observation_identities))
    expected_set = set(expected)
    observed_set = set(observed)
    missing = tuple(sorted(expected_set - observed_set))
    unexpected = tuple(sorted(observed_set - expected_set))
    duplicates = tuple(
        sorted(identity for identity, count in Counter(observed).items() if count > 1)
    )
    unidentified_count = audit.observation_count - len(observed)

    if len(expected) != len(expected_set):
        raise ValueError("expected observation identities must be unique")
    if any(not identity for identity in (*expected, *observed)):
        raise ValueError("observation identities must not be blank")
    if unidentified_count < 0:
        raise ValueError("observed identities exceed the observation count")
    if audit.expected_observation_count != len(expected):
        raise ValueError("retained expected count does not match the exact identity set")
    if missing != tuple(audit.missing_observation_identities):
        raise ValueError("retained missing identities do not recompute")
    if unexpected != tuple(audit.unexpected_observation_identities):
        raise ValueError("retained unexpected identities do not recompute")
    if duplicates != tuple(audit.unexpected_duplicate_identities):
        raise ValueError("retained duplicate identities do not recompute")

    identity_set_equal = (
        not missing
        and not unexpected
        and not duplicates
        and unidentified_count == 0
        and audit.observation_count == len(expected)
    )
    return {
        "run_id": run_id,
        "trace_id": trace_id,
        "expected_observation_identities": list(expected),
        "observed_observation_identities": list(observed),
        "missing_observation_identities": list(missing),
        "unexpected_observation_identities": list(unexpected),
        "duplicate_observation_identities": list(duplicates),
        "expected_count": len(expected),
        "observed_count": audit.observation_count,
        "unique_observed_count": len(observed_set),
        "unidentified_observation_count": unidentified_count,
        "root_trace_count": audit.root_trace_count,
        "one_root_trace": audit.one_root_trace,
        "identity_set_equal": identity_set_equal,
    }
