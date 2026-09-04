from __future__ import annotations

import pytest

from src.capabilities.generated.contract import (
    GeneratedCapabilityBundleV1,
    GeneratedCapabilityBundleValidationError,
    GeneratedCapabilityBundleValidator,
    GeneratedCapabilityRequestV1,
    decode_generated_capability_bundle,
)
from src.capabilities.generated.models import (
    CapabilityBuildRequest,
    ResearchLeadCapabilityApproval,
)
from src.domain.capability import CapabilityGapRecord, CapabilityRequirement


def build_request() -> CapabilityBuildRequest:
    requirement = CapabilityRequirement(
        requirement_id="REQ-FCF",
        capability_id="free_cash_flow_margin",
        purpose="Calculate free cash flow margin from signed capital expenditure.",
        input_schema={
            "operating_cash_flow": "decimal",
            "capital_expenditure": "decimal",
            "revenue": "decimal",
        },
        output_schema={"value": "decimal", "unit": "RATIO"},
        formula_id="operating_cash_flow_plus_signed_capex_divided_by_revenue_v1",
        allowed_imports=["decimal"],
        financial_invariants=["revenue_non_zero", "result_is_finite"],
    )
    gap = CapabilityGapRecord(
        gap_id="GAP-FCF",
        run_id="RUN-1",
        task_id="TASK-1",
        requirement=requirement,
        requested_by="fundamental_analyst",
    )
    return CapabilityBuildRequest(
        build_id="BUILD-1",
        gap=gap,
        approval=ResearchLeadCapabilityApproval(
            decision_id="DEC-1",
            run_id="RUN-1",
            task_id="TASK-1",
            gap_id="GAP-FCF",
            phase="SPEC",
            approved=True,
            approved_by="research_lead",
            reason_code="APPROVED",
            summary="approved",
        ),
        attempt=1,
        max_attempts=2,
    )


def valid_bundle(**updates: object) -> GeneratedCapabilityBundleV1:
    value: dict[str, object] = {
        "schema_version": "generated-capability-bundle/v1",
        "capability_id": "free_cash_flow_margin",
        "formula_id": "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1",
        "entrypoint": "execute",
        "source": (
            "from decimal import Decimal\n\n"
            "def execute(inputs):\n"
            "    operating_cash_flow = Decimal(str(inputs['operating_cash_flow']))\n"
            "    capital_expenditure = Decimal(str(inputs['capital_expenditure']))\n"
            "    revenue = Decimal(str(inputs['revenue']))\n"
            "    value = (operating_cash_flow + capital_expenditure) / revenue\n"
            "    return {'value': str(value), 'unit': 'RATIO'}\n"
        ),
        "tests": (
            "def run_tests(execute, fixture):\n"
            "    result = execute(fixture)\n"
            "    cash = Decimal(str(fixture['operating_cash_flow']))\n"
            "    capex = Decimal(str(fixture['capital_expenditure']))\n"
            "    revenue = Decimal(str(fixture['revenue']))\n"
            "    expected = (cash + capex) / revenue\n"
            "    assert Decimal(str(result['value'])) == expected\n"
            "    assert result['unit'] == 'RATIO'\n"
            "    return True\n"
        ),
        "input_schema": [
            {"name": "operating_cash_flow", "type": "decimal"},
            {"name": "capital_expenditure", "type": "decimal"},
            {"name": "revenue", "type": "decimal"},
        ],
        "output_schema": [
            {"name": "value", "type": "decimal"},
            {"name": "unit", "type": "RATIO"},
        ],
        "methodology": "Add signed capex to operating cash flow, then divide by revenue.",
        "declared_dependencies": ["decimal"],
    }
    value.update(updates)
    return GeneratedCapabilityBundleV1.model_validate(value)


def validation_codes(bundle: GeneratedCapabilityBundleV1) -> tuple[str, ...]:
    request = GeneratedCapabilityRequestV1.from_build_request(build_request())
    with pytest.raises(GeneratedCapabilityBundleValidationError) as captured:
        GeneratedCapabilityBundleValidator().validate(request, bundle)
    return captured.value.codes


def test_owned_request_contains_complete_policy_contract() -> None:
    request = GeneratedCapabilityRequestV1.from_build_request(build_request())

    assert request.gap_id == "GAP-FCF"
    assert request.entrypoint == "execute"
    assert "signed" in request.formula
    assert request.decimal_requirements
    assert request.forbidden_operations
    assert request.required_edge_cases
    assert request.required_test_categories
    assert request.financial_invariants == ["revenue_non_zero", "result_is_finite"]
    assert request.runtime_constraints


@pytest.mark.parametrize("field", ["source", "tests", "output_schema"])
def test_malformed_or_missing_bundle_fields_fail_with_stable_schema_code(field: str) -> None:
    value = valid_bundle().model_dump(mode="json")
    value.pop(field)

    with pytest.raises(GeneratedCapabilityBundleValidationError) as captured:
        decode_generated_capability_bundle(value)

    assert captured.value.codes == ("GC_SCHEMA_INVALID",)


def test_malformed_json_text_fails_without_extraction_or_guessing() -> None:
    with pytest.raises(GeneratedCapabilityBundleValidationError) as captured:
        decode_generated_capability_bundle("prefix {not-json}")

    assert captured.value.codes == ("GC_SCHEMA_INVALID",)


def test_unknown_bundle_field_is_rejected_without_heuristic_reconstruction() -> None:
    value = valid_bundle().model_dump(mode="json")
    value["source_code"] = value["source"]

    with pytest.raises(GeneratedCapabilityBundleValidationError) as captured:
        decode_generated_capability_bundle(value)

    assert captured.value.codes == ("GC_SCHEMA_INVALID",)


def test_valid_bundle_becomes_owned_output() -> None:
    request = GeneratedCapabilityRequestV1.from_build_request(build_request())
    output = GeneratedCapabilityBundleValidator().validate(request, valid_bundle())

    assert output.version == "1.0.0-generated"
    assert output.purpose == request.purpose
    assert output.financial_invariants == request.financial_invariants
    assert output.allowed_imports == ["decimal"]


@pytest.mark.parametrize(
    ("updates", "code"),
    (
        ({"capability_id": "wrong"}, "GC_SCHEMA_ID_MISMATCH"),
        ({"formula_id": "wrong"}, "GC_SCHEMA_ID_MISMATCH"),
    ),
)
def test_wrong_owned_identity_is_rejected(updates: dict[str, object], code: str) -> None:
    assert code in validation_codes(valid_bundle(**updates))


def test_invalid_entrypoint_and_signature_are_rejected() -> None:
    entrypoint = valid_bundle().source.replace("def execute(inputs):", "def execute(left, right):")

    assert "GC_SOURCE_SIGNATURE_INVALID" in validation_codes(valid_bundle(source=entrypoint))


def test_incorrect_signed_capex_formula_is_rejected() -> None:
    source = valid_bundle().source.replace(
        "operating_cash_flow + capital_expenditure",
        "operating_cash_flow - capital_expenditure",
    )

    assert "GC_FINANCIAL_FORMULA_MISMATCH" in validation_codes(valid_bundle(source=source))


@pytest.mark.parametrize(
    ("old", "new", "code"),
    (
        ("str(value)", "str(float(value))", "GC_SOURCE_FLOAT_FORBIDDEN"),
        ("str(value)", "str(round(value))", "GC_SOURCE_ROUND_FORBIDDEN"),
        ("str(value)", "str(value.quantize(Decimal('0.01')))", "GC_SOURCE_QUANTIZE_FORBIDDEN"),
    ),
)
def test_float_round_and_quantize_are_rejected(old: str, new: str, code: str) -> None:
    source = valid_bundle().source.replace(old, new)

    assert code in validation_codes(valid_bundle(source=source))


def test_forbidden_operation_and_import_are_rejected() -> None:
    source = "import os\n" + valid_bundle().source.replace(
        "def execute(inputs):", "def execute(inputs):\n    open('/tmp/x', 'w')"
    )
    codes = validation_codes(valid_bundle(source=source, declared_dependencies=["decimal", "os"]))

    assert "GC_SECURITY_POLICY_VIOLATION" in codes
    assert "GC_SCHEMA_DEPENDENCY_FORBIDDEN" in codes
    assert "GC_SECURITY_IMPORT_FORBIDDEN" in codes


def test_schema_and_unit_mismatch_are_rejected() -> None:
    output_schema = [
        {"name": "value", "type": "decimal"},
        {"name": "unit", "type": "PERCENT"},
    ]
    codes = validation_codes(valid_bundle(output_schema=output_schema))

    assert "GC_SCHEMA_OUTPUT_MISMATCH" in codes


def test_missing_fixture_derived_test_category_is_rejected() -> None:
    tests = (
        "def run_tests(execute, fixture):\n"
        "    result = execute(fixture)\n"
        "    expected = Decimal('0')\n"
        "    assert Decimal(str(result['value'])) == expected\n"
        "    assert result['unit'] == 'RATIO'\n"
    )
    codes = validation_codes(valid_bundle(tests=tests))

    assert "GC_TEST_CATEGORIES_INCOMPLETE" in codes
    assert "GC_TEST_FIXTURE_DERIVATION_MISSING" in codes


def test_invalid_test_syntax_is_rejected() -> None:
    assert "GC_TEST_SYNTAX_INVALID" in validation_codes(valid_bundle(tests="def run_tests("))


def test_utf8_byte_size_limit_is_enforced_locally() -> None:
    source = valid_bundle().source + "#" + ("é" * 9_000)

    assert "GC_SOURCE_SIZE_EXCEEDED" in validation_codes(valid_bundle(source=source))
