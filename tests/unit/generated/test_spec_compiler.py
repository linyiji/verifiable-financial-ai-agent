from __future__ import annotations

import hashlib

import pytest

from src.capabilities.generated.contract import GeneratedCapabilityRequestV1
from src.capabilities.generated.spec import (
    GENERATED_CAPABILITY_COMPILER_ID,
    GENERATED_CAPABILITY_COMPILER_VERSION,
    GeneratedCapabilityCompilerV1,
    GeneratedCapabilitySpecValidationError,
    GeneratedCapabilitySpecValidator,
    canonical_spec_bytes,
    decode_generated_capability_spec,
    expected_spec,
)
from tests.unit.generated.test_contract import build_request


def owned_request() -> GeneratedCapabilityRequestV1:
    return GeneratedCapabilityRequestV1.from_build_request(build_request())


def spec_dict() -> dict[str, object]:
    return expected_spec(owned_request()).model_dump(mode="json")


def validation_codes(**updates: object) -> tuple[str, ...]:
    value = spec_dict()
    value.update(updates)
    spec = decode_generated_capability_spec(value)
    with pytest.raises(GeneratedCapabilitySpecValidationError) as captured:
        GeneratedCapabilitySpecValidator().validate(owned_request(), spec)
    return captured.value.codes


def test_valid_spec_decodes_and_canonicalizes() -> None:
    spec = decode_generated_capability_spec(spec_dict())

    assert spec.schema_version == "generated-capability-spec/v1"
    assert spec.capability_id == "free_cash_flow_margin"
    assert canonical_spec_bytes(spec) == canonical_spec_bytes(spec)


@pytest.mark.parametrize(
    "value",
    (
        "not-json",
        {"schema_version": "generated-capability-spec/v1"},
        {**spec_dict(), "unexpected": True},
    ),
)
def test_malformed_spec_fails_closed(value: object) -> None:
    with pytest.raises(GeneratedCapabilitySpecValidationError) as captured:
        decode_generated_capability_spec(value)

    assert captured.value.codes == ("GC_SPEC_SCHEMA_INVALID",)


def test_unknown_operation_fails_schema_decode() -> None:
    value = spec_dict()
    formula = list(value["formula"])
    formula[-1] = {**formula[-1], "operation": "EXECUTE_PYTHON"}
    value["formula"] = formula

    with pytest.raises(GeneratedCapabilitySpecValidationError) as captured:
        decode_generated_capability_spec(value)

    assert captured.value.codes == ("GC_SPEC_SCHEMA_INVALID",)


@pytest.mark.parametrize(
    ("updates", "code"),
    (
        ({"capability_id": "wrong"}, "GC_SPEC_ID_MISMATCH"),
        ({"formula_id": "wrong"}, "GC_SPEC_ID_MISMATCH"),
        (
            {"output": {"value_type": "decimal", "unit": "PERCENT"}},
            "GC_SPEC_UNIT_MISMATCH",
        ),
        ({"financial_invariants": ["result_is_finite"]}, "GC_SPEC_INVARIANT_MISMATCH"),
    ),
)
def test_owned_financial_contract_mismatches_fail(
    updates: dict[str, object],
    code: str,
) -> None:
    assert code in validation_codes(**updates)


def test_illegal_abs_use_fails_with_explicit_code() -> None:
    value = spec_dict()
    formula = list(value["formula"])
    formula[-1] = {
        "step_id": "result",
        "operation": "ABS",
        "arguments": ["signed_free_cash_flow"],
    }

    assert "GC_SPEC_ABS_FORBIDDEN" in validation_codes(formula=formula)


def test_decimal_profile_mismatch_fails_with_explicit_code() -> None:
    profile = dict(spec_dict()["decimal_profile"])
    profile["precision"] = 34

    assert "GC_SPEC_DECIMAL_PROFILE_MISMATCH" in validation_codes(decimal_profile=profile)


def test_spec_compilation_is_byte_reproducible_and_version_bound() -> None:
    request = owned_request()
    spec = expected_spec(request)
    compiler = GeneratedCapabilityCompilerV1()

    first = compiler.compile(request, spec)
    second = compiler.compile(request, spec)

    assert first.spec_bytes == second.spec_bytes
    assert first.output.source_code.encode() == second.output.source_code.encode()
    assert first.output.unit_tests.encode() == second.output.unit_tests.encode()
    assert first.compiler_id == GENERATED_CAPABILITY_COMPILER_ID
    assert first.compiler_version == GENERATED_CAPABILITY_COMPILER_VERSION
    assert first.spec_sha256 == "sha256:" + hashlib.sha256(first.spec_bytes).hexdigest()
    assert (
        hashlib.sha256(first.output.source_code.encode()).digest()
        == hashlib.sha256(second.output.source_code.encode()).digest()
    )


def test_compiled_source_and_tests_are_valid_and_provider_source_is_absent() -> None:
    request = owned_request()
    compiled = GeneratedCapabilityCompilerV1().compile(request, expected_spec(request))

    compile(compiled.output.source_code, "generated_source.py", "exec")
    compile(compiled.output.unit_tests, "generated_tests.py", "exec")
    assert "def execute(inputs):" in compiled.output.source_code
    assert "def run_tests(execute, fixture):" in compiled.output.unit_tests
    assert "source" not in spec_dict()
    assert "tests" not in spec_dict()
