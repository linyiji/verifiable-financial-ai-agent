from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.observability.identity_evidence import build_langfuse_identity_set_evidence
from src.observability.langfuse_adapter import LangfuseTraceAuditReader


def _identities(count: int = 88) -> tuple[str, ...]:
    return tuple(f"OBS-{index:03d}" for index in range(count))


def _audit(
    observed: tuple[str, ...],
    *,
    expected: tuple[str, ...] | None = None,
    named_sensitive_values: dict[str, str] | None = None,
):
    payload = {
        "id": "TRACE-1",
        "observations": [
            {"id": identity, "traceId": "TRACE-1", "name": "vfas.test"} for identity in observed
        ],
    }
    sdk = SimpleNamespace(api=SimpleNamespace(trace=SimpleNamespace(get=lambda trace_id: payload)))
    return LangfuseTraceAuditReader(
        sdk,
        named_sensitive_values=named_sensitive_values or {},
    ).audit(
        "TRACE-1",
        attempts=1,
        expected_observation_identities=expected or _identities(),
    )


def _evidence(observed: tuple[str, ...], *, expected: tuple[str, ...] | None = None):
    return build_langfuse_identity_set_evidence(
        run_id="RUN-1",
        trace_id="TRACE-1",
        audit=_audit(observed, expected=expected),
    )


def test_retains_exact_88_by_88_identity_set_pass() -> None:
    evidence = _evidence(_identities())
    assert evidence["identity_set_equal"] is True
    assert evidence["expected_count"] == 88
    assert evidence["observed_count"] == 88
    assert evidence["unique_observed_count"] == 88
    assert evidence["root_trace_count"] == 1
    assert evidence["run_id"] == "RUN-1"
    assert evidence["trace_id"] == "TRACE-1"


def test_same_count_with_one_substituted_identity_fails() -> None:
    evidence = _evidence((*_identities()[:-1], "OBS-SUBSTITUTED"))
    assert evidence["identity_set_equal"] is False
    assert evidence["missing_observation_identities"] == ["OBS-087"]
    assert evidence["unexpected_observation_identities"] == ["OBS-SUBSTITUTED"]


def test_one_missing_identity_fails() -> None:
    evidence = _evidence(_identities()[:-1])
    assert evidence["identity_set_equal"] is False
    assert evidence["missing_observation_identities"] == ["OBS-087"]


def test_one_unexpected_identity_fails() -> None:
    evidence = _evidence((*_identities(), "OBS-UNEXPECTED"))
    assert evidence["identity_set_equal"] is False
    assert evidence["unexpected_observation_identities"] == ["OBS-UNEXPECTED"]


def test_duplicate_identity_fails_and_remains_independently_derivable() -> None:
    evidence = _evidence((*_identities()[:-1], "OBS-000"))
    assert evidence["identity_set_equal"] is False
    assert evidence["duplicate_observation_identities"] == ["OBS-000"]
    assert evidence["observed_count"] == 88
    assert evidence["unique_observed_count"] == 87
    assert Counter(evidence["observed_observation_identities"])["OBS-000"] == 2


def test_different_input_order_has_the_same_stable_serialization() -> None:
    forward = _evidence(_identities())
    reverse = _evidence(tuple(reversed(_identities())))
    assert json.dumps(forward, sort_keys=True, separators=(",", ":")) == json.dumps(
        reverse, sort_keys=True, separators=(",", ":")
    )


def test_retained_bundle_independently_reconstructs_all_set_results() -> None:
    evidence = json.loads(json.dumps(_evidence(_identities())))
    expected = set(evidence["expected_observation_identities"])
    observed_values = evidence["observed_observation_identities"]
    observed = set(observed_values)
    assert expected == observed
    assert sorted(expected - observed) == evidence["missing_observation_identities"]
    assert sorted(observed - expected) == evidence["unexpected_observation_identities"]
    assert (
        sorted(identity for identity, count in Counter(observed_values).items() if count > 1)
        == evidence["duplicate_observation_identities"]
    )


def test_retained_identity_evidence_preserves_zero_credential_occurrences() -> None:
    sentinels = {
        "LANGFUSE_PUBLIC_KEY": "credential-public-sentinel",
        "LANGFUSE_SECRET_KEY": "credential-secret-sentinel",
    }
    audit = _audit(_identities(), named_sensitive_values=sentinels)
    evidence = build_langfuse_identity_set_evidence(run_id="RUN-1", trace_id="TRACE-1", audit=audit)
    serialized = json.dumps(evidence, sort_keys=True)
    assert audit.occurrence_count == 0
    assert all(sentinel not in serialized for sentinel in sentinels.values())


def test_builder_rejects_inconsistent_derived_fields() -> None:
    audit = _audit(_identities())
    with pytest.raises(ValueError, match="missing identities do not recompute"):
        build_langfuse_identity_set_evidence(
            run_id="RUN-1",
            trace_id="TRACE-1",
            audit=replace(audit, missing_observation_identities=("FOREIGN",)),
        )
