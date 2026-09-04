"""Owned provider-neutral contract for generated financial capabilities.

The provider is asked for one deliberately small bundle.  Every policy-bearing
field lives in :class:`GeneratedCapabilityRequestV1` and is re-applied locally;
provider prose can never relax the executable or financial contract.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator

from src.capabilities.generated.models import (
    CapabilityBuildRequest,
    CodeBuilderOutput,
    CodeBuilderSchemaField,
)
from src.domain.base import DomainModel
from src.tooling.generated_sandbox import GeneratedCodeASTPreflight

GENERATED_CAPABILITY_REQUEST_SCHEMA_VERSION = "generated-capability-request/v1"
GENERATED_CAPABILITY_BUNDLE_SCHEMA_VERSION = "generated-capability-bundle/v1"
GENERATED_CAPABILITY_ENTRYPOINT = "execute"
GENERATED_CAPABILITY_VERSION = "1.0.0-generated"
MAX_GENERATED_SOURCE_BYTES = 16_384
MAX_GENERATED_TEST_BYTES = 16_384

_FCF_FORMULA_ID = "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1"
_FORMULA_EXPRESSIONS: dict[str, tuple[Any, ...]] = {
    _FCF_FORMULA_ID: (
        "div",
        ("add", ("var", "operating_cash_flow"), ("var", "capital_expenditure")),
        ("var", "revenue"),
    ),
    "gross_margin_v1": (
        "div",
        ("var", "gross_profit"),
        ("var", "revenue"),
    ),
}


class GeneratedCapabilityRequestV1(DomainModel):
    """Complete owned generation request; never sourced from provider output."""

    schema_version: Literal["generated-capability-request/v1"] = (
        GENERATED_CAPABILITY_REQUEST_SCHEMA_VERSION
    )
    gap_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    formula_id: str = Field(min_length=1)
    formula: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    entrypoint: Literal["execute"] = GENERATED_CAPABILITY_ENTRYPOINT
    input_schema: list[CodeBuilderSchemaField]
    output_schema: list[CodeBuilderSchemaField]
    decimal_requirements: list[str]
    allowed_imports: list[str]
    forbidden_operations: list[str]
    required_edge_cases: list[str]
    required_test_categories: list[str]
    financial_invariants: list[str]
    runtime_constraints: list[str]
    max_source_bytes: int = MAX_GENERATED_SOURCE_BYTES
    max_test_bytes: int = MAX_GENERATED_TEST_BYTES

    @classmethod
    def from_build_request(cls, request: CapabilityBuildRequest) -> GeneratedCapabilityRequestV1:
        requirement = request.gap.requirement
        formula = _owned_formula(requirement.formula_id)
        return cls(
            gap_id=request.gap.gap_id,
            capability_id=requirement.capability_id,
            formula_id=requirement.formula_id,
            formula=formula,
            purpose=requirement.purpose,
            input_schema=[
                CodeBuilderSchemaField(name=name, type=value)
                for name, value in requirement.input_schema.items()
            ],
            output_schema=[
                CodeBuilderSchemaField(name=name, type=value)
                for name, value in requirement.output_schema.items()
            ],
            decimal_requirements=[
                "parse every numeric input through Decimal(str(value))",
                "perform all financial arithmetic in Decimal",
                "serialize the result with str without rounding or quantization",
            ],
            allowed_imports=list(requirement.allowed_imports),
            forbidden_operations=[
                "float",
                "round",
                "quantize",
                "filesystem",
                "network",
                "process",
                "environment",
                "dynamic_import",
                "eval",
                "exec",
            ],
            required_edge_cases=[
                "positive_result",
                "zero_result",
                "negative_result",
                "high_precision_decimal",
            ],
            required_test_categories=[
                "formula_semantics",
                "output_schema",
                "output_unit",
                "fixture_derived_expectation",
            ],
            financial_invariants=list(requirement.financial_invariants),
            runtime_constraints=[
                "pure synchronous Python",
                "one execute(inputs) entrypoint",
                "one run_tests(execute, fixture) test entrypoint",
                "restricted Docker sandbox execution only",
                "deterministic for identical inputs",
            ],
        )


class GeneratedCapabilityBundleV1(DomainModel):
    """Only provider response accepted by either governed planner provider."""

    schema_version: Literal["generated-capability-bundle/v1"]
    capability_id: str = Field(min_length=1)
    formula_id: str = Field(min_length=1)
    entrypoint: Literal["execute"]
    source: str = Field(min_length=1, max_length=MAX_GENERATED_SOURCE_BYTES)
    tests: str = Field(min_length=1, max_length=MAX_GENERATED_TEST_BYTES)
    input_schema: list[CodeBuilderSchemaField]
    output_schema: list[CodeBuilderSchemaField]
    methodology: str = Field(min_length=1, max_length=2_048)
    declared_dependencies: list[str]

    @field_validator("capability_id", "formula_id", "source", "tests", "methodology")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text fields must not be blank")
        return value

    @field_validator("input_schema", "output_schema")
    @classmethod
    def reject_duplicate_schema_fields(
        cls, values: list[CodeBuilderSchemaField]
    ) -> list[CodeBuilderSchemaField]:
        names = [field.name for field in values]
        if len(names) != len(set(names)):
            raise ValueError("schema field names must be unique")
        return values

    @field_validator("declared_dependencies")
    @classmethod
    def reject_duplicate_dependencies(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("dependency names must not be blank")
        if len(values) != len(set(values)):
            raise ValueError("dependency names must be unique")
        return values


@dataclass(frozen=True, slots=True)
class GCValidationFinding:
    """Secret-safe, machine-readable corrective fact for same-model repair."""

    code: str
    field: str
    expected_rule: str
    description: str = "deterministic generated-capability requirement not satisfied"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "field": self.field,
            "expected_rule": self.expected_rule,
            "description": self.description,
        }


class GeneratedCapabilityBundleValidationError(ValueError):
    def __init__(self, findings: list[GCValidationFinding] | tuple[GCValidationFinding, ...]):
        self.findings = tuple(findings)
        super().__init__(",".join(finding.code for finding in self.findings))

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.findings)


def decode_generated_capability_bundle(value: object) -> GeneratedCapabilityBundleV1:
    """Strictly decode JSON-compatible provider data without reconstruction."""

    try:
        return GeneratedCapabilityBundleV1.model_validate(value)
    except ValidationError as exc:
        fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
        field = fields[0] if fields else "bundle"
        raise GeneratedCapabilityBundleValidationError(
            [GCValidationFinding("GC_SCHEMA_INVALID", field, "GeneratedCapabilityBundleV1")]
        ) from exc


class GeneratedCapabilityBundleValidator:
    """Deterministic pre-acceptance validation for one provider bundle."""

    def __init__(self, preflight: GeneratedCodeASTPreflight | None = None) -> None:
        self._preflight = preflight or GeneratedCodeASTPreflight()

    def validate(
        self,
        request: GeneratedCapabilityRequestV1,
        bundle: GeneratedCapabilityBundleV1,
    ) -> CodeBuilderOutput:
        findings: list[GCValidationFinding] = []
        self._validate_identity(request, bundle, findings)
        source_tree = self._parse(bundle.source, "source", findings)
        test_tree = self._parse(bundle.tests, "tests", findings)
        if source_tree is not None:
            self._validate_entrypoint(source_tree, request.entrypoint, "source", 1, findings)
            self._validate_decimal_policy(source_tree, "source", findings)
            self._validate_source_contract(request, source_tree, findings)
            self._validate_formula(request, source_tree, findings)
        if test_tree is not None:
            self._validate_entrypoint(test_tree, "run_tests", "tests", 2, findings)
            self._validate_decimal_policy(test_tree, "tests", findings)
            self._validate_tests(request, test_tree, findings)
        self._validate_sandbox(bundle.source, "source", findings)
        self._validate_sandbox(bundle.tests, "tests", findings)
        self._validate_imports(request, bundle, source_tree, test_tree, findings)
        if len(bundle.source.encode("utf-8")) > request.max_source_bytes:
            findings.append(
                GCValidationFinding("GC_SOURCE_SIZE_EXCEEDED", "source", "owned byte limit")
            )
        if len(bundle.tests.encode("utf-8")) > request.max_test_bytes:
            findings.append(
                GCValidationFinding("GC_TEST_SIZE_EXCEEDED", "tests", "owned byte limit")
            )
        if findings:
            raise GeneratedCapabilityBundleValidationError(_deduplicate_findings(findings))
        return CodeBuilderOutput(
            capability_id=request.capability_id,
            version=GENERATED_CAPABILITY_VERSION,
            purpose=request.purpose,
            input_schema={field.name: field.type for field in request.input_schema},
            output_schema={field.name: field.type for field in request.output_schema},
            formula_id=request.formula_id,
            formula_description=bundle.methodology,
            source_code=bundle.source,
            unit_tests=bundle.tests,
            financial_invariants=list(request.financial_invariants),
            allowed_imports=list(bundle.declared_dependencies),
        )

    @staticmethod
    def _validate_identity(
        request: GeneratedCapabilityRequestV1,
        bundle: GeneratedCapabilityBundleV1,
        findings: list[GCValidationFinding],
    ) -> None:
        for field in ("capability_id", "formula_id", "entrypoint"):
            if getattr(bundle, field) != getattr(request, field):
                findings.append(
                    GCValidationFinding("GC_SCHEMA_ID_MISMATCH", field, "exact request value")
                )
        if bundle.input_schema != request.input_schema:
            findings.append(
                GCValidationFinding(
                    "GC_SCHEMA_INPUT_MISMATCH", "input_schema", "exact request schema"
                )
            )
        if bundle.output_schema != request.output_schema:
            findings.append(
                GCValidationFinding(
                    "GC_SCHEMA_OUTPUT_MISMATCH", "output_schema", "exact request schema"
                )
            )

    @staticmethod
    def _parse(
        source: str,
        field: str,
        findings: list[GCValidationFinding],
    ) -> ast.Module | None:
        try:
            return ast.parse(source, filename=f"generated_{field}.py", mode="exec")
        except (SyntaxError, ValueError, TypeError):
            prefix = "GC_SOURCE" if field == "source" else "GC_TEST"
            findings.append(
                GCValidationFinding(f"{prefix}_SYNTAX_INVALID", field, "valid Python syntax")
            )
            return None

    @staticmethod
    def _validate_entrypoint(
        tree: ast.Module,
        name: str,
        field: str,
        positional_args: int,
        findings: list[GCValidationFinding],
    ) -> None:
        definitions = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ]
        prefix = "GC_SOURCE" if field == "source" else "GC_TEST"
        if len(definitions) != 1:
            findings.append(
                GCValidationFinding(f"{prefix}_ENTRYPOINT_INVALID", field, f"one {name} definition")
            )
            return
        definition = definitions[0]
        count = len(definition.args.posonlyargs) + len(definition.args.args)
        if (
            isinstance(definition, ast.AsyncFunctionDef)
            or count != positional_args
            or definition.args.vararg
            or definition.args.kwarg
            or definition.args.kwonlyargs
        ):
            findings.append(
                GCValidationFinding(
                    f"{prefix}_SIGNATURE_INVALID",
                    field,
                    f"synchronous {name} with {positional_args} positional arguments",
                )
            )

    @staticmethod
    def _validate_decimal_policy(
        tree: ast.Module,
        field: str,
        findings: list[GCValidationFinding],
    ) -> None:
        prefix = "GC_SOURCE" if field == "source" else "GC_TEST"
        if any(
            isinstance(node, ast.Constant) and isinstance(node.value, float)
            for node in ast.walk(tree)
        ):
            findings.append(GCValidationFinding(f"{prefix}_FLOAT_FORBIDDEN", field, "Decimal only"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            attr = node.func.attr if isinstance(node.func, ast.Attribute) else None
            if name == "float":
                findings.append(
                    GCValidationFinding(f"{prefix}_FLOAT_FORBIDDEN", field, "Decimal only")
                )
            if name == "round":
                findings.append(
                    GCValidationFinding(f"{prefix}_ROUND_FORBIDDEN", field, "no rounding")
                )
            if attr == "quantize":
                findings.append(
                    GCValidationFinding(f"{prefix}_QUANTIZE_FORBIDDEN", field, "no quantization")
                )

    @staticmethod
    def _validate_formula(
        request: GeneratedCapabilityRequestV1,
        tree: ast.Module,
        findings: list[GCValidationFinding],
    ) -> None:
        expected = _FORMULA_EXPRESSIONS.get(request.formula_id)
        if expected is None:
            findings.append(
                GCValidationFinding(
                    "GC_FINANCIAL_FORMULA_UNSUPPORTED", "formula_id", "owned formula registry entry"
                )
            )
            return
        actual = _execute_return_expression(tree, request.entrypoint)
        if actual != expected:
            findings.append(
                GCValidationFinding(
                    "GC_FINANCIAL_FORMULA_MISMATCH", "source", "exact owned formula semantics"
                )
            )

    @staticmethod
    def _validate_source_contract(
        request: GeneratedCapabilityRequestV1,
        tree: ast.Module,
        findings: list[GCValidationFinding],
    ) -> None:
        function = _function(tree, request.entrypoint)
        if function is None:
            return
        numeric_fields = {
            field.name for field in request.input_schema if field.type.strip().lower() == "decimal"
        }
        converted = _decimalized_subscript_fields(function, "inputs")
        if not numeric_fields.issubset(converted):
            findings.append(
                GCValidationFinding(
                    "GC_SOURCE_DECIMAL_CONVERSION_INCOMPLETE",
                    "source",
                    "Decimal(str(inputs[field])) for every decimal input",
                )
            )
        returned = _returned_mapping(function)
        expected_keys = {field.name for field in request.output_schema}
        if returned is None or set(returned) != expected_keys:
            findings.append(
                GCValidationFinding(
                    "GC_SOURCE_OUTPUT_SCHEMA_INVALID",
                    "source",
                    "return exactly the requested output fields",
                )
            )
            return
        expected_unit = next(
            (field.type for field in request.output_schema if field.name == "unit"), None
        )
        unit = returned.get("unit")
        if expected_unit is not None and not (
            isinstance(unit, ast.Constant) and unit.value == expected_unit
        ):
            findings.append(
                GCValidationFinding(
                    "GC_FINANCIAL_UNIT_MISMATCH",
                    "source",
                    "exact requested output unit",
                )
            )

    @staticmethod
    def _validate_tests(
        request: GeneratedCapabilityRequestV1,
        tree: ast.Module,
        findings: list[GCValidationFinding],
    ) -> None:
        text_literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        calls_execute = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "execute"
            for node in ast.walk(tree)
        )
        if not calls_execute:
            findings.append(
                GCValidationFinding("GC_TEST_EXECUTION_MISSING", "tests", "call execute(fixture)")
            )
        if sum(isinstance(node, ast.Assert) for node in ast.walk(tree)) < 2:
            findings.append(
                GCValidationFinding(
                    "GC_TEST_ASSERTIONS_INCOMPLETE", "tests", "value and unit assertions"
                )
            )
        required_literals = {field.name for field in request.input_schema} | {"value", "unit"}
        if not required_literals.issubset(text_literals):
            findings.append(
                GCValidationFinding(
                    "GC_TEST_CATEGORIES_INCOMPLETE",
                    "tests",
                    "fixture-derived formula, value, and unit coverage",
                )
            )
        fixture_fields = _subscript_fields(tree, "fixture")
        if not {field.name for field in request.input_schema}.issubset(fixture_fields):
            findings.append(
                GCValidationFinding(
                    "GC_TEST_FIXTURE_DERIVATION_MISSING",
                    "tests",
                    "derive expected formula from every fixture input",
                )
            )
        if not any(isinstance(node, ast.Name) and node.id == "Decimal" for node in ast.walk(tree)):
            findings.append(
                GCValidationFinding(
                    "GC_TEST_DECIMAL_MISSING", "tests", "Decimal expected calculation"
                )
            )

    def _validate_sandbox(
        self,
        source: str,
        field: str,
        findings: list[GCValidationFinding],
    ) -> None:
        result = self._preflight.validate(source, filename=f"generated_{field}.py")
        if not result.accepted:
            prefix = (
                "GC_SECURITY"
                if any(
                    violation.code in {"CALL_FORBIDDEN", "NAME_FORBIDDEN", "DUNDER_ACCESS"}
                    for violation in result.violations
                )
                else "GC_SANDBOX"
            )
            findings.append(
                GCValidationFinding(
                    f"{prefix}_POLICY_VIOLATION",
                    field,
                    "owned default-deny AST policy",
                )
            )

    @staticmethod
    def _validate_imports(
        request: GeneratedCapabilityRequestV1,
        bundle: GeneratedCapabilityBundleV1,
        source_tree: ast.Module | None,
        test_tree: ast.Module | None,
        findings: list[GCValidationFinding],
    ) -> None:
        allowed = set(request.allowed_imports)
        declared = set(bundle.declared_dependencies)
        if not declared.issubset(allowed):
            findings.append(
                GCValidationFinding(
                    "GC_SCHEMA_DEPENDENCY_FORBIDDEN", "declared_dependencies", "allowed imports"
                )
            )
        actual: set[str] = set()
        for tree in (source_tree, test_tree):
            if tree is not None:
                actual.update(_imports(tree))
        if not actual.issubset(allowed) or not actual.issubset(declared):
            findings.append(
                GCValidationFinding(
                    "GC_SECURITY_IMPORT_FORBIDDEN", "source/tests", "declared allowed imports"
                )
            )
        decimal_contract = any(
            field.type.strip().lower() == "decimal" for field in request.input_schema
        )
        if decimal_contract and ("decimal" not in actual or "decimal" not in declared):
            findings.append(
                GCValidationFinding(
                    "GC_SOURCE_DECIMAL_IMPORT_MISSING", "source/tests", "decimal dependency"
                )
            )


def _owned_formula(formula_id: str) -> str:
    if formula_id == _FCF_FORMULA_ID:
        return (
            "(operating_cash_flow + capital_expenditure) / revenue; capital_expenditure is signed"
        )
    if formula_id == "gross_margin_v1":
        return "gross_profit / revenue"
    return f"owned formula registry identifier: {formula_id}"


def _imports(tree: ast.Module) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    return next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name),
        None,
    )


def _subscript_fields(tree: ast.AST, mapping_name: str) -> set[str]:
    return {
        node.slice.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == mapping_name
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    }


def _decimalized_subscript_fields(tree: ast.AST, mapping_name: str) -> set[str]:
    fields: set[str] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Decimal"
            and len(node.args) == 1
        ):
            continue
        argument = node.args[0]
        if not (
            isinstance(argument, ast.Call)
            and isinstance(argument.func, ast.Name)
            and argument.func.id == "str"
            and len(argument.args) == 1
        ):
            continue
        fields.update(_subscript_fields(argument.args[0], mapping_name))
    return fields


def _returned_mapping(function: ast.FunctionDef) -> dict[str, ast.expr] | None:
    for node in ast.walk(function):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        result: dict[str, ast.expr] = {}
        for key, value in zip(node.value.keys, node.value.values, strict=True):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                return None
            result[key.value] = value
        return result
    return None


def _execute_return_expression(tree: ast.Module, entrypoint: str) -> tuple[Any, ...] | None:
    function = _function(tree, entrypoint)
    if function is None:
        return None
    assignments: dict[str, ast.expr] = {}
    for statement in function.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name):
                assignments[target.id] = statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            assignments[statement.target.id] = statement.value
        elif isinstance(statement, ast.Return) and isinstance(statement.value, ast.Dict):
            for key, value in zip(statement.value.keys, statement.value.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "value":
                    return _symbolic(value, assignments, set())
    return None


def _symbolic(
    node: ast.expr | None,
    assignments: dict[str, ast.expr],
    resolving: set[str],
) -> tuple[Any, ...] | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        if node.id in resolving:
            return None
        assigned = assignments.get(node.id)
        if assigned is None:
            return ("var", node.id)
        return _symbolic(assigned, assignments, resolving | {node.id})
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "inputs"
    ):
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            return ("var", node.slice.value)
    if isinstance(node, ast.Call) and len(node.args) == 1:
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name in {"Decimal", "str"}:
            return _symbolic(node.args[0], assignments, resolving)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _symbolic(node.operand, assignments, resolving)
        return ("neg", value) if value is not None else None
    if isinstance(node, ast.BinOp):
        operators: tuple[tuple[type[ast.operator], str], ...] = (
            (ast.Add, "add"),
            (ast.Sub, "sub"),
            (ast.Mult, "mul"),
            (ast.Div, "div"),
        )
        operator = next((name for kind, name in operators if isinstance(node.op, kind)), None)
        left = _symbolic(node.left, assignments, resolving)
        right = _symbolic(node.right, assignments, resolving)
        if operator and left is not None and right is not None:
            return (operator, left, right)
    return None


def _deduplicate_findings(findings: list[GCValidationFinding]) -> list[GCValidationFinding]:
    unique: dict[tuple[str, str], GCValidationFinding] = {}
    for finding in findings:
        unique.setdefault((finding.code, finding.field), finding)
    return list(unique.values())
