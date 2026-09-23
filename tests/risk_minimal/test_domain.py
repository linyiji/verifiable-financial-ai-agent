from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domain.agent_output import (
    RiskAdmissionDecisionV1,
    RiskBusinessOutcomeV1,
)
from src.domain.agent_output import (
    RiskResearchAgentStructuredOutputMinimalV1 as Output,
)
from src.domain.evidence import risk_input_consistency_guard_v1 as guard
from src.domain.node_binding import BindingDenied, OutputRecord, canonical_value, digest
from src.domain.risk_admission import POLICY


def payload():
    return dict(
        summary="need more evidence",
        key_findings=["EVIDENCE_INSUFFICIENT"],
        risks=[],
        limitations=[],
        requires_follow_up=False,
        business_outcome="SUFFICIENT",
        outcome_reason_codes=[],
        evidence_gap_refs=[],
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"business_outcome": "CONFLICTING_EVIDENCE"},
        {"business_outcome": None},
        {"conflict_refs": []},
        {"admission": "FINAL_SUCCESS"},
        {"requires_follow_up": 0},
        {"requires_follow_up": "false"},
        {"outcome_reason_codes": ["UNKNOWN"]},
        {"business_outcome": "INSUFFICIENT_EVIDENCE"},
        {"evidence_gap_refs": [{"requirement_ref": "r", "reason_code": "UNKNOWN"}]},
    ],
)
def test_m01_closed_shape(patch):
    with pytest.raises(ValidationError):
        Output.model_validate({**payload(), **patch})


def test_m01_m11_no_defaults_or_prose_oracle():
    assert len(RiskBusinessOutcomeV1) == 2
    assert len(RiskAdmissionDecisionV1) == 4
    for key in ("business_outcome", "outcome_reason_codes", "evidence_gap_refs"):
        value = payload()
        value.pop(key)
        with pytest.raises(ValidationError):
            Output.model_validate(value)
    assert Output.model_validate(payload()).business_outcome == "SUFFICIENT"


def material(identity, value, **patch):
    row = dict(
        evidence_id=identity,
        object_id="object",
        run_id="run",
        normalized_field="revenue",
        normalized_value=canonical_value(value),
        period="FY2026",
        period_basis="FY",
        as_of="2026-09-04",
        actuality="ACTUAL",
        statement_series="fmp:series",
        statement_cohort="fmp:cohort",
        unit="CURRENCY",
        currency="USD",
        technical_price_basis=None,
        corporate_action_status=None,
        cash_flow_sign_convention=None,
        cash_flow_normalization_applied=False,
        snapshot_hash="sha256:" + identity * 64,
        **{},
    )
    row.update(patch)
    return OutputRecord(
        kind="EVIDENCE",
        record_id=identity,
        content_digest=digest(row, "evidence-record/v1"),
        location="/unused",
        record_schema="evidence-record/v1",
        payload_snapshot=row,
    )


def evaluate(records, **kwargs):
    return guard(
        materials=records,
        binding_id="binding",
        input_digest="input",
        policy=kwargs.get("policy", POLICY),
        scope={"run_id": "run", "cycle": "INITIAL"},
    )


@pytest.mark.parametrize("equal", [100, "100.00", Decimal("100.000")])
def test_m07_exact_equality_permutation(equal):
    a, b = material("a", 100), material("b", equal)
    assert evaluate([a, b]) == evaluate([b, a]) == evaluate([a, a, b])
    assert evaluate([a, b])["equal_pair_count"] == 1
    assert evaluate([a, b])["input_consistency"] == "PASS"


@pytest.mark.parametrize(
    "patch",
    [
        {"period": "FY2025"},
        {"currency": "EUR"},
        {"as_of": "2026-09-03"},
        {"statement_cohort": "other"},
        {"statement_series": "other"},
    ],
)
def test_m07_distinct_keys(patch):
    assert (
        evaluate([material("a", 100), material("b", 101, **patch)])["input_consistency"] == "PASS"
    )


@pytest.mark.parametrize("value", [True, None, 100.0, "1e2", "NaN", "0" * 129, "0." + "1" * 65])
def test_m07_unsupported_value(value):
    result = evaluate([material("a", value)])
    assert result["input_consistency"] == "UNSATISFIED"
    assert result["reason_codes"] == ["STRUCTURED_COMPARISON_UNESTABLISHED"]


def test_m07_conflict_unknown_unsupported_bounds_and_digest():
    a, b = material("a", 100), material("b", 101)
    result = evaluate([a, b])
    assert result["reason_codes"] == ["UNRESOLVED_STRUCTURED_CONFLICT"]
    assert result == evaluate([b, a])
    assert (
        evaluate([a, material("b", 101, statement_series=None)])["input_consistency"]
        == "UNSATISFIED"
    )
    other = material("b", "narrative", normalized_field="news")
    assert evaluate([other])["input_consistency"] == "PASS"
    policy = deepcopy(POLICY)
    policy["required_comparisons"] = ["narrative"]
    assert "REQUIRED_COMPARISON_UNSUPPORTED" in evaluate([other], policy=policy)["reason_codes"]
    policy["max_materials"] = 1
    with pytest.raises(BindingDenied, match="BOUND"):
        evaluate([a, b], policy=policy)
    with pytest.raises(BindingDenied, match="COLLISION"):
        evaluate([a, material("a", 101)])
    assert (
        guard(
            materials=[a, b],
            binding_id="other",
            input_digest="input",
            policy=POLICY,
            scope={"run_id": "run", "cycle": "INITIAL"},
        )["guard_digest"]
        != result["guard_digest"]
    )


@pytest.mark.parametrize(
    "dimension",
    [
        "object_id",
        "period",
        "as_of",
        "period_basis",
        "actuality",
        "statement_series",
        "statement_cohort",
        "unit",
        "currency",
    ],
)
def test_m07_unknown_dimension_is_not_pass(dimension):
    assert evaluate([material("a", 100, **{dimension: ""})])["input_consistency"] == "UNSATISFIED"


def test_m01_m14_mixed_contract_rejected():
    from src.domain.output_dependency import OutputRequirements
    from src.domain.risk_admission import freeze_contract, validate_contract
    from src.domain.task import Task

    contract = freeze_contract(
        [
            Task(
                task_id="risk",
                run_id="run",
                task_type="risk_analysis",
                goal="risk",
                assigned_agent="risk_analyst",
                skill_id="risk_analysis_v1",
                output_requirements=OutputRequirements(
                    hard_required=["fundamental/revenue_growth"]
                ),
            )
        ]
    )
    for field, wrong in [
        ("policy", {"profile": "old-three-state"}),
        ("schema_digest", "legacy"),
        ("contract_digest", "stale"),
    ]:
        with pytest.raises(BindingDenied):
            validate_contract({**contract, field: wrong})
    for patch in [
        {"business_outcome": "INSUFFICIENT_EVIDENCE", "outcome_reason_codes": []},
        {
            "business_outcome": "SUFFICIENT",
            "evidence_gap_refs": [
                {"requirement_ref": "x", "reason_code": "EVIDENCE_COVERAGE_LIMITED"}
            ],
        },
    ]:
        with pytest.raises(ValidationError):
            Output.model_validate({**payload(), **patch})


def test_m07_signed_zero_exact_digits_and_pair_bound():
    assert evaluate([material("a", "-0.000"), material("b", 0)])["equal_pair_count"] == 1
    assert (
        evaluate([material("a", "1" * 128), material("b", "1" * 127 + "2")])[
            "conflicting_pair_count"
        ]
        == 1
    )
    policy = deepcopy(POLICY)
    policy["max_pairs"] = 0
    with pytest.raises(BindingDenied, match="BOUND"):
        evaluate([material("a", 1), material("b", 2)], policy=policy)
