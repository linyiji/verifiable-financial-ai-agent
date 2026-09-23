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


def validate_report_metrics(contract, *, run_id, run_as_of, evidence, calculations, metrics):
    """Frozen expectations are independent of the candidate being checked."""
    from src.assurance.independent_financial_review import _metric_matches, _snapshot_matches
    from src.domain.execution_profile import FrozenReportMetricRequirementsV1
    from src.domain.node_binding import BindingDenied

    contract = FrozenReportMetricRequirementsV1.model_validate(contract.model_dump())
    required = set(contract.resolved_required_metric_ids)
    allowed = required | set(contract.optional_metric_ids)
    selected = {m.formula_id for m in metrics}
    if not selected <= allowed:
        raise BindingDenied("CONTRACT_REJECTED", "unselected report metric")
    if not required <= selected:
        raise BindingDenied("REPORT_SOURCE_MAP_INCOMPLETE", "required report metric missing")
    evidence_by_id = {e.evidence_id: e for e in evidence}
    if len(evidence_by_id) != len(evidence):
        raise BindingDenied("CONTRACT_REJECTED", "duplicate report evidence")
    expectations = {e.metric_id: e for e in contract.metric_expectations}
    for formula in selected:
        ms = [m for m in metrics if m.formula_id == formula]
        cs = [c for c in calculations if c.formula_id == formula]
        if len(ms) != 1 or len(cs) != 1:
            raise BindingDenied("CONTRACT_REJECTED", "ambiguous report metric")
        m, c, e = ms[0], cs[0], expectations[formula]
        inputs = [evidence_by_id.get(ref) for ref in c.input_evidence_ids]
        expected_periods = {e.period} | ({e.prior_period} if e.prior_period else set())
        try:
            if (
                c.run_id != run_id
                or c.status.value != "PASS"
                or e.as_of != run_as_of
                or c.capability_id != e.capability_id
                or c.capability_version != e.capability_version
                or c.implementation_hash != e.implementation_hash
                or c.output_unit != e.unit
                or m.canonical_unit.value != e.unit.upper()
                or m.period != e.period
                or m.period_basis.value != e.period_basis
                or m.actuality.value != e.actuality
                or m.as_of > e.as_of
                or m.calculation_id != c.calculation_id
                or m.capability_id != e.capability_id
                or set(m.evidence_ids) != set(c.input_evidence_ids)
                or not inputs
                or any(i is None for i in inputs)
                or any(
                    i.object_id != e.object_id
                    or i.run_id != run_id
                    or i.status.value != "ACCEPTED"
                    or i.as_of > e.as_of
                    or i.period_basis.value != e.period_basis
                    or i.actuality.value != e.actuality
                    for i in inputs
                )
                or {i.period for i in inputs} != expected_periods
                or not _metric_matches(c, m, inputs)
                or not _snapshot_matches(c, inputs)
            ):
                raise BindingDenied("CONTRACT_REJECTED", "frozen report metric identity/lineage")
        except (ArithmeticError, ValueError, TypeError, AttributeError) as exc:
            raise BindingDenied("CONTRACT_REJECTED", "report metric integrity") from exc
