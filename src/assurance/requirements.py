"""Exact Scheme and outcome preimage used independently at Review and Release."""

from src.phase4_product.hashing import canonical_json_sha256


def required_capabilities(scheme):
    # Frozen Scheme policy clauses are not names of missing calculators.
    clauses = {
        "deterministic_financial_calculations_only",
        "calculation_records_for_reported_values",
    }
    return set(scheme.calculation_requirements) - clauses


def requirement_context(scheme, branches):
    return {
        "version": "financial-requirements/v1",
        "scheme_id": scheme.scheme_id,
        "scheme_hash": canonical_json_sha256(scheme.model_dump(mode="json")),
        "required_calculations": sorted(required_capabilities(scheme)),
        "branches": [b.model_dump(mode="json") for b in branches],
    }
