"""Closed Generated Capability Spec IR and deterministic owned compiler."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import Field, ValidationError, field_validator

from src.capabilities.generated.contract import (
    GCValidationFinding,
    GeneratedCapabilityBundleV1,
    GeneratedCapabilityBundleValidator,
    GeneratedCapabilityRequestV1,
)
from src.capabilities.generated.models import CodeBuilderOutput, CodeBuilderSchemaField
from src.domain.base import DomainModel

GENERATED_CAPABILITY_SPEC_SCHEMA_VERSION = "generated-capability-spec/v1"
GENERATED_CAPABILITY_SPEC_VERSION = "GeneratedCapabilitySpecV1"
GENERATED_CAPABILITY_COMPILER_ID = "vfas-generated-capability-compiler"
GENERATED_CAPABILITY_COMPILER_VERSION = "1"
GENERATED_CAPABILITY_RUNTIME_POLICY = "python3.11-decimal-sandbox-v1"
DECIMAL_PROFILE_ID = "DECIMAL_STR_EXACT_V1"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class FormulaOperationV1(StrEnum):
    REFERENCE = "REFERENCE"
    ADD = "ADD"
    SUBTRACT = "SUBTRACT"
    MULTIPLY = "MULTIPLY"
    DIVIDE = "DIVIDE"
    NEGATE = "NEGATE"
    ABS = "ABS"
    COMPARISON = "COMPARISON"
    GUARD = "GUARD"


class FormulaInstructionV1(DomainModel):
    step_id: str = Field(min_length=1, max_length=64)
    operation: FormulaOperationV1
    arguments: list[str] = Field(min_length=1, max_length=2)

    @field_validator("step_id")
    @classmethod
    def validate_step_id(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("step_id must be a safe owned identifier")
        return value


class DecimalProfileV1(DomainModel):
    profile_id: str = Field(min_length=1, max_length=64)
    precision: int = Field(ge=28, le=100)
    rounding: str = Field(min_length=1, max_length=32)
    input_conversion: str = Field(min_length=1, max_length=64)
    output_serialization: str = Field(min_length=1, max_length=64)


class GeneratedOutputContractV1(DomainModel):
    value_type: str = Field(min_length=1)
    unit: str = Field(min_length=1)


class GeneratedMethodologyMetadataV1(DomainModel):
    methodology_id: str = Field(min_length=1, max_length=160)


class GeneratedCapabilitySpecV1(DomainModel):
    """Small provider-produced IR with no arbitrary executable content."""

    schema_version: Literal["generated-capability-spec/v1"]
    capability_id: str = Field(min_length=1)
    formula_id: str = Field(min_length=1)
    entrypoint: Literal["execute"]
    input_fields: list[CodeBuilderSchemaField]
    output: GeneratedOutputContractV1
    formula: list[FormulaInstructionV1] = Field(min_length=1, max_length=16)
    financial_invariants: list[str]
    decimal_profile: DecimalProfileV1
    required_edge_cases: list[str]
    methodology: GeneratedMethodologyMetadataV1
    allowed_dependencies: list[str]


class GeneratedCapabilitySpecValidationError(ValueError):
    def __init__(self, findings: list[GCValidationFinding]):
        self.findings = tuple(findings)
        super().__init__(",".join(item.code for item in findings))

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.findings)


def decode_generated_capability_spec(value: object) -> GeneratedCapabilitySpecV1:
    try:
        return GeneratedCapabilitySpecV1.model_validate(value)
    except ValidationError as exc:
        fields = sorted({".".join(str(part) for part in item["loc"]) for item in exc.errors()})
        raise GeneratedCapabilitySpecValidationError(
            [
                GCValidationFinding(
                    "GC_SPEC_SCHEMA_INVALID",
                    fields[0] if fields else "spec",
                    "GeneratedCapabilitySpecV1",
                )
            ]
        ) from exc


class GeneratedCapabilitySpecValidator:
    """Bind every authoritative Spec field to owned application semantics."""

    def validate(
        self,
        request: GeneratedCapabilityRequestV1,
        spec: GeneratedCapabilitySpecV1,
    ) -> None:
        expected = expected_spec(request)
        findings: list[GCValidationFinding] = []
        for field in ("capability_id", "formula_id", "entrypoint"):
            if getattr(spec, field) != getattr(expected, field):
                findings.append(
                    GCValidationFinding("GC_SPEC_ID_MISMATCH", field, "exact owned value")
                )
        comparisons = (
            (
                spec.input_fields,
                expected.input_fields,
                "GC_SPEC_INPUT_SCHEMA_MISMATCH",
                "input_fields",
                "exact owned input fields",
            ),
            (
                spec.output.value_type,
                expected.output.value_type,
                "GC_SPEC_OUTPUT_TYPE_MISMATCH",
                "output.value_type",
                "exact owned type",
            ),
            (
                spec.output.unit,
                expected.output.unit,
                "GC_SPEC_UNIT_MISMATCH",
                "output.unit",
                "exact owned unit",
            ),
            (
                spec.financial_invariants,
                expected.financial_invariants,
                "GC_SPEC_INVARIANT_MISMATCH",
                "financial_invariants",
                "exact owned invariants",
            ),
            (
                spec.decimal_profile,
                expected.decimal_profile,
                "GC_SPEC_DECIMAL_PROFILE_MISMATCH",
                "decimal_profile",
                "owned Decimal profile",
            ),
            (
                spec.required_edge_cases,
                expected.required_edge_cases,
                "GC_SPEC_EDGE_CASE_MISMATCH",
                "required_edge_cases",
                "exact owned edge-case classes",
            ),
            (
                spec.allowed_dependencies,
                expected.allowed_dependencies,
                "GC_SPEC_DEPENDENCY_MISMATCH",
                "allowed_dependencies",
                "exact owned dependencies",
            ),
            (
                spec.methodology,
                expected.methodology,
                "GC_SPEC_METHODOLOGY_MISMATCH",
                "methodology",
                "owned methodology identity",
            ),
        )
        for actual, owned, code, field, rule in comparisons:
            if actual != owned:
                findings.append(GCValidationFinding(code, field, rule))
        if any(item.operation is FormulaOperationV1.ABS for item in spec.formula):
            findings.append(
                GCValidationFinding(
                    "GC_SPEC_ABS_FORBIDDEN",
                    "formula",
                    "ABS requires explicit owned formula permission",
                )
            )
        findings.extend(_validate_formula_ir(spec.formula, expected.formula))
        if findings:
            unique = list({(item.code, item.field): item for item in findings}.values())
            raise GeneratedCapabilitySpecValidationError(unique)


@dataclass(frozen=True, slots=True)
class CompiledGeneratedCapabilityV1:
    output: CodeBuilderOutput
    spec_bytes: bytes
    spec_sha256: str
    compiler_id: str = GENERATED_CAPABILITY_COMPILER_ID
    compiler_version: str = GENERATED_CAPABILITY_COMPILER_VERSION
    runtime_policy: str = GENERATED_CAPABILITY_RUNTIME_POLICY


class GeneratedCapabilityCompilerV1:
    compiler_id = GENERATED_CAPABILITY_COMPILER_ID
    compiler_version = GENERATED_CAPABILITY_COMPILER_VERSION
    runtime_policy = GENERATED_CAPABILITY_RUNTIME_POLICY

    def __init__(
        self,
        *,
        spec_validator: GeneratedCapabilitySpecValidator | None = None,
        output_validator: GeneratedCapabilityBundleValidator | None = None,
    ) -> None:
        self._spec_validator = spec_validator or GeneratedCapabilitySpecValidator()
        self._output_validator = output_validator or GeneratedCapabilityBundleValidator()

    def compile(
        self,
        request: GeneratedCapabilityRequestV1,
        spec: GeneratedCapabilitySpecV1,
    ) -> CompiledGeneratedCapabilityV1:
        self._spec_validator.validate(request, spec)
        spec_bytes = canonical_spec_bytes(spec)
        bundle = GeneratedCapabilityBundleV1(
            schema_version="generated-capability-bundle/v1",
            capability_id=spec.capability_id,
            formula_id=spec.formula_id,
            entrypoint=spec.entrypoint,
            source=_render_source(spec),
            tests=_render_tests(spec),
            input_schema=list(spec.input_fields),
            output_schema=[
                CodeBuilderSchemaField(name="value", type=spec.output.value_type),
                CodeBuilderSchemaField(name="unit", type=spec.output.unit),
            ],
            methodology=spec.methodology.methodology_id,
            declared_dependencies=list(spec.allowed_dependencies),
        )
        output = self._output_validator.validate(request, bundle)
        return CompiledGeneratedCapabilityV1(
            output=output,
            spec_bytes=spec_bytes,
            spec_sha256="sha256:" + hashlib.sha256(spec_bytes).hexdigest(),
        )


def canonical_spec_bytes(spec: GeneratedCapabilitySpecV1) -> bytes:
    return json.dumps(
        spec.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def expected_spec(request: GeneratedCapabilityRequestV1) -> GeneratedCapabilitySpecV1:
    output = {field.name: field.type for field in request.output_schema}
    return GeneratedCapabilitySpecV1(
        schema_version=GENERATED_CAPABILITY_SPEC_SCHEMA_VERSION,
        capability_id=request.capability_id,
        formula_id=request.formula_id,
        entrypoint=request.entrypoint,
        input_fields=list(request.input_schema),
        output=GeneratedOutputContractV1(value_type=output["value"], unit=output["unit"]),
        formula=_owned_formula_ir(request.formula_id),
        financial_invariants=list(request.financial_invariants),
        decimal_profile=DecimalProfileV1(
            profile_id=DECIMAL_PROFILE_ID,
            precision=28,
            rounding="ROUND_HALF_EVEN",
            input_conversion="Decimal(str(value))",
            output_serialization="str(value)",
        ),
        required_edge_cases=list(request.required_edge_cases),
        methodology=GeneratedMethodologyMetadataV1(
            methodology_id=f"OWNED_{request.formula_id.upper()}"
        ),
        allowed_dependencies=list(request.allowed_imports),
    )


def _owned_formula_ir(formula_id: str) -> list[FormulaInstructionV1]:
    if formula_id == "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1":
        definitions = (
            ("operating_cash_flow", FormulaOperationV1.REFERENCE, ["operating_cash_flow"]),
            ("capital_expenditure", FormulaOperationV1.REFERENCE, ["capital_expenditure"]),
            ("revenue", FormulaOperationV1.REFERENCE, ["revenue"]),
            (
                "signed_free_cash_flow",
                FormulaOperationV1.ADD,
                ["operating_cash_flow", "capital_expenditure"],
            ),
            ("result", FormulaOperationV1.DIVIDE, ["signed_free_cash_flow", "revenue"]),
        )
    elif formula_id == "gross_margin_v1":
        definitions = (
            ("gross_profit", FormulaOperationV1.REFERENCE, ["gross_profit"]),
            ("revenue", FormulaOperationV1.REFERENCE, ["revenue"]),
            ("result", FormulaOperationV1.DIVIDE, ["gross_profit", "revenue"]),
        )
    else:
        raise GeneratedCapabilitySpecValidationError(
            [
                GCValidationFinding(
                    "GC_SPEC_FORMULA_UNSUPPORTED",
                    "formula_id",
                    "owned formula IR registry entry",
                )
            ]
        )
    return [
        FormulaInstructionV1(step_id=step, operation=operation, arguments=arguments)
        for step, operation, arguments in definitions
    ]


def _validate_formula_ir(
    actual: list[FormulaInstructionV1],
    expected: list[FormulaInstructionV1],
) -> list[GCValidationFinding]:
    findings: list[GCValidationFinding] = []
    defined: set[str] = set()
    arity = {
        FormulaOperationV1.REFERENCE: 1,
        FormulaOperationV1.ADD: 2,
        FormulaOperationV1.SUBTRACT: 2,
        FormulaOperationV1.MULTIPLY: 2,
        FormulaOperationV1.DIVIDE: 2,
        FormulaOperationV1.NEGATE: 1,
        FormulaOperationV1.ABS: 1,
        FormulaOperationV1.COMPARISON: 2,
        FormulaOperationV1.GUARD: 1,
    }
    for item in actual:
        if len(item.arguments) != arity[item.operation]:
            findings.append(
                GCValidationFinding(
                    "GC_SPEC_OPERATION_ARITY_INVALID",
                    f"formula.{item.step_id}",
                    f"{arity[item.operation]} arguments",
                )
            )
        if item.operation is not FormulaOperationV1.REFERENCE and not set(item.arguments).issubset(
            defined
        ):
            findings.append(
                GCValidationFinding(
                    "GC_SPEC_REFERENCE_INVALID",
                    f"formula.{item.step_id}",
                    "references to prior IR steps only",
                )
            )
        if item.step_id in defined:
            findings.append(
                GCValidationFinding(
                    "GC_SPEC_STEP_DUPLICATE",
                    f"formula.{item.step_id}",
                    "unique step IDs",
                )
            )
        defined.add(item.step_id)
    if actual != expected:
        findings.append(
            GCValidationFinding(
                "GC_SPEC_FORMULA_MISMATCH",
                "formula",
                "exact owned closed formula IR",
            )
        )
    return findings


def _render_source(spec: GeneratedCapabilitySpecV1) -> str:
    lines = [
        "from decimal import Decimal, localcontext",
        "",
        "_DECIMAL_PRECISION = 28",
        "",
        "def execute(inputs):",
        "    with localcontext() as decimal_context:",
        "        decimal_context.prec = _DECIMAL_PRECISION",
    ]
    for field in spec.input_fields:
        lines.append(f'        {field.name} = Decimal(str(inputs["{field.name}"]))')
    for invariant in spec.financial_invariants:
        if invariant.endswith("_non_zero"):
            field = invariant.removesuffix("_non_zero")
            lines.extend(
                [
                    f'        if {field} == Decimal("0"):',
                    f'            raise ValueError("{invariant}")',
                ]
            )
    for item in spec.formula:
        if item.operation is not FormulaOperationV1.REFERENCE:
            lines.append(f"        {item.step_id} = {_render_operation(item)}")
    if "result_is_finite" in spec.financial_invariants:
        lines.extend(
            [
                "        if not result.is_finite():",
                '            raise ValueError("result_is_finite")',
            ]
        )
    lines.append(f'        return {{"value": str(result), "unit": "{spec.output.unit}"}}')
    return "\n".join(lines) + "\n"


def _render_operation(item: FormulaInstructionV1) -> str:
    binary = {
        FormulaOperationV1.ADD: "+",
        FormulaOperationV1.SUBTRACT: "-",
        FormulaOperationV1.MULTIPLY: "*",
        FormulaOperationV1.DIVIDE: "/",
    }
    if item.operation in binary:
        return f"({item.arguments[0]} {binary[item.operation]} {item.arguments[1]})"
    if item.operation is FormulaOperationV1.NEGATE:
        return f"(-{item.arguments[0]})"
    if item.operation is FormulaOperationV1.ABS:
        return f"abs({item.arguments[0]})"
    raise GeneratedCapabilitySpecValidationError(
        [
            GCValidationFinding(
                "GC_SPEC_OPERATION_NOT_COMPILABLE",
                f"formula.{item.step_id}",
                "governed arithmetic operation",
            )
        ]
    )


def _render_tests(spec: GeneratedCapabilitySpecV1) -> str:
    known_inputs, known_expected = _known_case(spec.formula_id)
    denominator = next(
        (
            invariant.removesuffix("_non_zero")
            for invariant in spec.financial_invariants
            if invariant.endswith("_non_zero")
        ),
        None,
    )
    lines = [
        "def run_tests(execute, fixture):",
        "    result = execute(fixture)",
        "    with localcontext() as decimal_context:",
        "        decimal_context.prec = _DECIMAL_PRECISION",
    ]
    for field in spec.input_fields:
        lines.append(f'        {field.name} = Decimal(str(fixture["{field.name}"]))')
    lines.extend(
        [
            f"        expected = {_formula_expression(spec)}",
            '    assert Decimal(str(result["value"])) == expected',
            f'    assert result["unit"] == "{spec.output.unit}"',
            f"    known_fixture = {known_inputs!r}",
            "    known_result = execute(known_fixture)",
            f'    assert Decimal(str(known_result["value"])) == Decimal("{known_expected}")',
            f'    assert known_result["unit"] == "{spec.output.unit}"',
        ]
    )
    if denominator is not None:
        lines.extend(
            [
                "    zero_denominator = dict(fixture)",
                f'    zero_denominator["{denominator}"] = "0"',
                "    denominator_rejected = False",
                "    try:",
                "        execute(zero_denominator)",
                "    except ValueError:",
                "        denominator_rejected = True",
                "    assert denominator_rejected",
            ]
        )
    lines.extend(["    return True", ""])
    return "\n".join(lines)


def _formula_expression(spec: GeneratedCapabilitySpecV1) -> str:
    expressions: dict[str, str] = {}
    binary = {
        FormulaOperationV1.ADD: "+",
        FormulaOperationV1.SUBTRACT: "-",
        FormulaOperationV1.MULTIPLY: "*",
        FormulaOperationV1.DIVIDE: "/",
    }
    for item in spec.formula:
        if item.operation is FormulaOperationV1.REFERENCE:
            expressions[item.step_id] = item.arguments[0]
        elif item.operation in binary:
            expressions[item.step_id] = (
                f"({expressions[item.arguments[0]]} {binary[item.operation]} "
                f"{expressions[item.arguments[1]]})"
            )
        elif item.operation is FormulaOperationV1.NEGATE:
            expressions[item.step_id] = f"(-{expressions[item.arguments[0]]})"
        elif item.operation is FormulaOperationV1.ABS:
            expressions[item.step_id] = f"abs({expressions[item.arguments[0]]})"
    return expressions[spec.formula[-1].step_id]


def _known_case(formula_id: str) -> tuple[dict[str, str], str]:
    if formula_id == "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1":
        return (
            {
                "operating_cash_flow": "125",
                "capital_expenditure": "-25",
                "revenue": "200",
            },
            "0.5",
        )
    if formula_id == "gross_margin_v1":
        return ({"gross_profit": "75", "revenue": "100"}, "0.75")
    raise GeneratedCapabilitySpecValidationError(
        [
            GCValidationFinding(
                "GC_SPEC_FORMULA_UNSUPPORTED",
                "formula_id",
                "owned known-output test case",
            )
        ]
    )
