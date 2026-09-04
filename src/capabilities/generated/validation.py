"""Validation pipeline and executable wrapper for generated capabilities."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import math
import platform
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from src.capabilities.generated.models import GeneratedCapabilityCandidate, ValidationHandoff
from src.capabilities.generated.ports import CapabilityValidationProgressPort
from src.domain.base import JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.capability import (
    CapabilityContext,
    CapabilityDefinition,
    CapabilityValidationRecord,
    SandboxExecutionRecord,
)
from src.domain.enums import CalculationStatus, CapabilityBackend, CapabilityLifecycle
from src.tooling.generated_sandbox import (
    ALLOWED_IMPORTS,
    DockerSandboxBackend,
    GeneratedCodeASTPreflight,
    SandboxBackend,
    SandboxRequest,
    SandboxResult,
)

VALIDATION_SCHEMA_VERSION = "generated-capability-validation/v1"


class GeneratedCapabilityValidationError(ValueError):
    """A terminal, explicitly staged validation failure."""

    def __init__(self, stage: str, detail: str):
        self.stage = stage
        self.detail = detail
        super().__init__(f"{stage}: {detail}")


class GeneratedCapabilityExecutionError(RuntimeError):
    pass


@runtime_checkable
class FinancialValidationPolicy(Protocol):
    """Trusted, owned financial oracle; generated source cannot implement this policy."""

    def validate(
        self,
        candidate: GeneratedCapabilityCandidate,
        inputs: JsonObject,
        output: Any,
    ) -> JsonObject | None: ...


@dataclass(frozen=True, slots=True)
class CallableFinancialValidationPolicy:
    callback: Callable[[GeneratedCapabilityCandidate, JsonObject, Any], JsonObject | None]

    def validate(
        self,
        candidate: GeneratedCapabilityCandidate,
        inputs: JsonObject,
        output: Any,
    ) -> JsonObject | None:
        return self.callback(candidate, inputs, output)


@dataclass(frozen=True, slots=True)
class CapabilityValidationPlan:
    primary_fixture: JsonObject
    edge_case_fixtures: tuple[JsonObject, ...]
    financial_policy: FinancialValidationPolicy
    schema_version: str = VALIDATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.edge_case_fixtures:
            raise ValueError("at least one deterministic edge-case fixture is required")
        if not self.schema_version.strip():
            raise ValueError("schema_version must not be blank")


@runtime_checkable
class CapabilityValidationPlanProvider(Protocol):
    def plan_for(self, candidate: GeneratedCapabilityCandidate) -> CapabilityValidationPlan: ...


@dataclass(frozen=True, slots=True)
class StaticCapabilityValidationPlanProvider:
    plan: CapabilityValidationPlan

    def plan_for(self, candidate: GeneratedCapabilityCandidate) -> CapabilityValidationPlan:
        del candidate
        return self.plan


class GeneratedCapabilityValidator:
    """U1 validation port implemented with U2's real sandbox boundary."""

    def __init__(
        self,
        *,
        sandbox: SandboxBackend,
        plans: CapabilityValidationPlanProvider,
        preflight: GeneratedCodeASTPreflight | None = None,
    ) -> None:
        if not isinstance(sandbox, SandboxBackend):
            raise TypeError("sandbox must implement SandboxBackend")
        if not isinstance(plans, CapabilityValidationPlanProvider):
            raise TypeError("plans must implement CapabilityValidationPlanProvider")
        self._sandbox = sandbox
        self._plans = plans
        self._preflight = preflight or GeneratedCodeASTPreflight()

    async def validate(
        self,
        candidate: GeneratedCapabilityCandidate,
        *,
        progress: CapabilityValidationProgressPort,
    ) -> ValidationHandoff:
        output = candidate.output
        findings: list[JsonObject] = []
        plan = self._plans.plan_for(candidate)

        self._static_validate(candidate)
        findings.append({"stage": "static_validation", "passed": True})

        self._syntax_compile(output.source_code, "generated_capability.py")
        self._syntax_compile(output.unit_tests, "test_generated.py")
        findings.append({"stage": "syntax_compile", "passed": True})
        await progress.static_validated(candidate.implementation_hash)

        await progress.sandbox_started(candidate.implementation_hash)
        primary = await self._run_sandbox(candidate, plan.primary_fixture)
        self._require_sandbox_passed(primary, "unit_tests")
        self._require_security_profile(primary)
        findings.append({"stage": "unit_tests", "passed": True})

        edge_results: list[tuple[JsonObject, SandboxResult]] = []
        for fixture in plan.edge_case_fixtures:
            result = await self._run_sandbox(candidate, fixture)
            self._require_sandbox_passed(result, "edge_cases")
            self._require_security_profile(result)
            edge_results.append((fixture, result))
        findings.append({"stage": "edge_cases", "passed": True, "case_count": len(edge_results)})

        evaluated = [(plan.primary_fixture, primary), *edge_results]
        for fixture, result in evaluated:
            self._validate_invariants(output.financial_invariants, fixture, result.output["result"])
        findings.append(
            {
                "stage": "financial_invariants",
                "passed": True,
                "invariants": list(output.financial_invariants),
            }
        )

        deterministic_first = await self._run_sandbox(candidate, plan.primary_fixture)
        deterministic_second = await self._run_sandbox(candidate, plan.primary_fixture)
        self._require_sandbox_passed(deterministic_first, "deterministic_double_run")
        self._require_sandbox_passed(deterministic_second, "deterministic_double_run")
        self._require_security_profile(deterministic_first)
        self._require_security_profile(deterministic_second)
        canonical_outputs = {
            _canonical_json(primary.output["result"]),
            _canonical_json(deterministic_first.output["result"]),
            _canonical_json(deterministic_second.output["result"]),
        }
        if len(canonical_outputs) != 1:
            raise GeneratedCapabilityValidationError(
                "deterministic_double_run", "canonical outputs differ across identical runs"
            )
        findings.append({"stage": "deterministic_double_run", "passed": True, "runs": 2})

        for _, result in evaluated:
            _validate_schema(result.output["result"], output.output_schema)
        findings.append(
            {
                "stage": "output_schema",
                "passed": True,
                "schema_version": plan.schema_version,
            }
        )

        expected_unit = _expected_unit(output.output_schema)
        for _, result in evaluated:
            _validate_unit(result.output["result"], expected_unit)
        findings.append({"stage": "unit_validation", "passed": True, "unit": expected_unit})

        source_hash = source_sha256(output.source_code)
        if candidate.implementation_hash != source_hash:
            raise GeneratedCapabilityValidationError(
                "implementation_hash",
                "candidate implementation hash does not match normalized generated source",
            )
        runtime_version = _runtime_version(primary, self._sandbox)
        if not runtime_version.startswith("Python 3.11."):
            raise GeneratedCapabilityValidationError(
                "runtime_version",
                f"sandbox runtime is outside Python 3.11 baseline: {runtime_version}",
            )
        findings.append(
            {
                "stage": "identity",
                "passed": True,
                "source_hash": source_hash,
                "implementation_hash": candidate.implementation_hash,
                "python_version": runtime_version,
                "capability_version": output.version,
                "formula_id": output.formula_id,
                "schema_version": plan.schema_version,
            }
        )
        await progress.tests_passed(candidate.implementation_hash)

        oracle_results: list[JsonObject] = []
        runtime_results: list[JsonObject] = []
        for fixture, result in evaluated:
            try:
                oracle = plan.financial_policy.validate(candidate, fixture, result.output["result"])
            except Exception as exc:
                raise GeneratedCapabilityValidationError(
                    "financial_validation", f"trusted financial policy rejected output: {exc}"
                ) from exc
            oracle_results.append(_json_clone(oracle or {}))
            runtime_results.append(_json_clone(result.output["result"]))
        findings.append(
            {
                "stage": "financial_validation",
                "passed": True,
                "source_hash": source_hash,
                "tests_hash": source_sha256(output.unit_tests),
                "oracle_results": oracle_results,
                "runtime_results": runtime_results,
            }
        )
        await progress.financial_validated(candidate.implementation_hash)

        validation = CapabilityValidationRecord(
            validation_id=f"VAL-{uuid4()}",
            build_id=candidate.build_id,
            implementation_hash=candidate.implementation_hash,
            static_validation_passed=True,
            syntax_compile_passed=True,
            unit_tests_passed=True,
            edge_cases_passed=True,
            financial_invariants_passed=True,
            deterministic_double_run_passed=True,
            output_schema_passed=True,
            unit_validation_passed=True,
            financial_validation_passed=True,
            lifecycle=CapabilityLifecycle.FINANCIAL_VALIDATED,
            findings=findings,
            source_hash=source_hash,
            tests_hash=source_sha256(output.unit_tests),
            oracle_result={"cases": oracle_results},
            runtime_result={"cases": runtime_results},
            validation_result="PASS",
        )
        sandbox_execution = _sandbox_record(
            candidate,
            plan.primary_fixture,
            primary,
            runtime_version,
            backend=self._sandbox,
        )
        capability = SandboxValidatedGeneratedCapability(
            candidate=candidate,
            sandbox=self._sandbox,
            source_ref=f"generated://{candidate.build_id}/source.py",
            runtime_version=runtime_version,
            schema_version=plan.schema_version,
            financial_policy=plan.financial_policy,
        )
        return ValidationHandoff(
            validation=validation,
            sandbox_execution=sandbox_execution,
            capability=capability,
        )

    def _static_validate(self, candidate: GeneratedCapabilityCandidate) -> None:
        output = candidate.output
        disallowed_declarations = set(output.allowed_imports) - ALLOWED_IMPORTS
        if disallowed_declarations:
            raise GeneratedCapabilityValidationError(
                "static_validation",
                "candidate declares imports outside sandbox policy: "
                + ", ".join(sorted(disallowed_declarations)),
            )
        for filename, source in (
            ("generated_capability.py", output.source_code),
            ("test_generated.py", output.unit_tests),
        ):
            result = self._preflight.validate(source, filename=filename)
            if not result.accepted:
                codes = ", ".join(item.code for item in result.violations)
                raise GeneratedCapabilityValidationError(
                    "static_validation", f"{filename} rejected: {codes}"
                )
        actual_imports = _source_imports(output.source_code) | _source_imports(output.unit_tests)
        undeclared = actual_imports - set(output.allowed_imports)
        if undeclared:
            raise GeneratedCapabilityValidationError(
                "static_validation",
                "source uses imports absent from approved candidate declaration: "
                + ", ".join(sorted(undeclared)),
            )
        _require_function(output.source_code, "execute", positional_args=1)
        _require_function(output.unit_tests, "run_tests", positional_args=2)

    @staticmethod
    def _syntax_compile(source: str, filename: str) -> None:
        try:
            compile(source, filename, "exec", dont_inherit=True, optimize=2)
        except (SyntaxError, ValueError, TypeError) as exc:
            raise GeneratedCapabilityValidationError("syntax_compile", str(exc)) from exc

    async def _run_sandbox(
        self, candidate: GeneratedCapabilityCandidate, fixture: JsonObject
    ) -> SandboxResult:
        request = SandboxRequest(
            source=candidate.output.source_code,
            test_source=candidate.output.unit_tests,
            fixture=fixture,
        )
        return await asyncio.to_thread(self._sandbox.execute, request)

    @staticmethod
    def _require_sandbox_passed(result: SandboxResult, stage: str) -> None:
        if result.passed and result.exit_code == 0 and result.output.get("ok") is True:
            return
        error = result.output.get("error", {})
        code = error.get("code", "SANDBOX_FAILED") if isinstance(error, dict) else "SANDBOX_FAILED"
        raise GeneratedCapabilityValidationError(stage, f"sandbox rejected execution: {code}")

    @staticmethod
    def _require_security_profile(result: SandboxResult) -> None:
        profile = result.security
        required = {
            "network": "none",
            "read_only_root": True,
            "cap_drop": "ALL",
            "no_new_privileges": True,
            "host_mounts": [],
            "python_dont_write_bytecode": True,
        }
        mismatches = [key for key, expected in required.items() if profile.get(key) != expected]
        user = profile.get("user")
        if user in (None, "0", "0:0", "root"):
            mismatches.append("user")
        for limit in ("memory", "cpus", "pids", "wall_timeout_seconds"):
            if profile.get(limit) in (None, 0, ""):
                mismatches.append(limit)
        if mismatches:
            raise GeneratedCapabilityValidationError(
                "sandbox_security",
                "sandbox security profile is incomplete: " + ", ".join(sorted(set(mismatches))),
            )

    @staticmethod
    def _validate_invariants(invariants: Sequence[str], inputs: JsonObject, output: Any) -> None:
        if not invariants:
            raise GeneratedCapabilityValidationError(
                "financial_invariants", "at least one approved invariant is required"
            )
        for invariant in invariants:
            try:
                _run_invariant(invariant, inputs, output)
            except Exception as exc:
                raise GeneratedCapabilityValidationError(
                    "financial_invariants", f"{invariant}: {exc}"
                ) from exc


class SandboxValidatedGeneratedCapability:
    """A generated Capability that remains behind Docker for every runtime call."""

    def __init__(
        self,
        *,
        candidate: GeneratedCapabilityCandidate,
        sandbox: SandboxBackend,
        source_ref: str,
        runtime_version: str,
        schema_version: str,
        financial_policy: FinancialValidationPolicy,
    ) -> None:
        output = candidate.output
        self.definition = CapabilityDefinition(
            capability_id=output.capability_id,
            version=output.version,
            name=f"Generated {output.capability_id}",
            category="financial_calculation",
            backend=CapabilityBackend.GENERATED,
            input_schema=output.input_schema,
            output_schema=output.output_schema,
            deterministic=True,
            proof_eligible=False,
            lifecycle=CapabilityLifecycle.FINANCIAL_VALIDATED.value,
            implementation_ref=source_ref,
            owner="generated-capability-runtime",
        )
        self.formula_id = output.formula_id
        self.implementation_hash = candidate.implementation_hash
        self.tests_hash = source_sha256(output.unit_tests)
        self.source_ref = source_ref
        self.runtime_version = runtime_version
        self.schema_version = schema_version
        self._source = output.source_code
        self._tests = output.unit_tests
        self._invariants = tuple(output.financial_invariants)
        self._candidate = candidate
        self._financial_policy = financial_policy
        self._sandbox = sandbox

    async def execute(self, inputs: JsonObject, context: CapabilityContext) -> CalculationRecord:
        sandbox_inputs = {key: value for key, value in inputs.items() if key != "calculation_id"}
        _validate_schema(sandbox_inputs, self.definition.input_schema)
        result = await asyncio.to_thread(
            self._sandbox.execute,
            SandboxRequest(
                source=self._source,
                test_source=self._tests,
                fixture=sandbox_inputs,
            ),
        )
        if not result.passed or result.exit_code != 0 or result.output.get("ok") is not True:
            raise GeneratedCapabilityExecutionError("generated capability sandbox execution failed")
        output = result.output["result"]
        _validate_schema(output, self.definition.output_schema)
        unit = _expected_unit(self.definition.output_schema)
        _validate_unit(output, unit)
        for invariant in self._invariants:
            _run_invariant(invariant, sandbox_inputs, output)
        try:
            oracle_result = self._financial_policy.validate(self._candidate, sandbox_inputs, output)
        except Exception as exc:
            raise GeneratedCapabilityExecutionError(
                f"owned live financial oracle rejected generated output: {exc}"
            ) from exc
        actual_runtime = _runtime_version(result, self._sandbox)
        if not actual_runtime.startswith("Python 3.11."):
            raise GeneratedCapabilityExecutionError(
                f"generated capability runtime left Python 3.11 baseline: {actual_runtime}"
            )
        output_value = output.get("value") if isinstance(output, dict) else output
        if _schema_value_descriptor(self.definition.output_schema) == "decimal":
            output_value = Decimal(str(output_value))
        return CalculationRecord(
            calculation_id=str(inputs.get("calculation_id") or f"CALC-{uuid4()}"),
            run_id=context.run_id,
            task_id=context.task_id,
            capability_id=self.definition.capability_id,
            capability_version=self.definition.version,
            formula_id=self.formula_id,
            input_evidence_ids=list(context.accepted_evidence_ids),
            input_values_snapshot=_json_clone(sandbox_inputs),
            parameters={
                "validation_schema_version": self.schema_version,
                "validation_scope": "LIVE_RUNTIME",
                "generated_source_hash": self.implementation_hash,
                "generated_tests_hash": source_sha256(self._tests),
                "live_input_commitment": (
                    "sha256:"
                    + hashlib.sha256(_canonical_json(sandbox_inputs).encode("utf-8")).hexdigest()
                ),
                "owned_oracle_result": _json_clone(oracle_result or {}),
                "runtime_result": _json_clone(output),
                "financial_validation_result": "PASS",
            },
            output_value=output_value,
            output_unit=unit,
            status=CalculationStatus.PASS,
            implementation_hash=self.implementation_hash,
            code_hash=self.implementation_hash,
            source_ref=self.source_ref,
            runtime_version=actual_runtime,
        )


def source_sha256(source: str) -> str:
    normalized = source.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def _source_imports(source: str) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(ast.parse(source, mode="exec")):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _require_function(source: str, name: str, *, positional_args: int) -> None:
    tree = ast.parse(source, mode="exec")
    definitions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(definitions) != 1:
        raise GeneratedCapabilityValidationError(
            "static_validation", f"source must define exactly one {name} function"
        )
    definition = definitions[0]
    actual_args = len(definition.args.posonlyargs) + len(definition.args.args)
    if actual_args != positional_args or definition.args.vararg or definition.args.kwarg:
        raise GeneratedCapabilityValidationError(
            "static_validation",
            f"{name} must accept exactly {positional_args} positional arguments",
        )
    if isinstance(definition, ast.AsyncFunctionDef):
        raise GeneratedCapabilityValidationError(
            "static_validation", f"{name} must be synchronous inside the sandbox"
        )


def _run_invariant(invariant: str, inputs: JsonObject, output: Any) -> None:
    normalized = invariant.strip().lower()
    if normalized.endswith("_non_zero"):
        field = normalized.removesuffix("_non_zero")
        if field not in inputs:
            raise ValueError(f"input {field!r} is absent")
        if _decimal(inputs[field]) == 0:
            raise ValueError(f"input {field!r} is zero")
        return
    value = _output_decimal(output)
    if normalized in {"result_is_finite", "finite_output", "output_is_finite"}:
        if not value.is_finite():
            raise ValueError("result is not finite")
        return
    if normalized in {"result_non_negative", "output_non_negative"}:
        if value < 0:
            raise ValueError("result is negative")
        return
    if normalized in {"result_between_zero_and_one", "ratio_between_zero_and_one"}:
        if not Decimal("0") <= value <= Decimal("1"):
            raise ValueError("result is outside [0, 1]")
        return
    if normalized in {
        "result_between_minus_one_and_one",
        "ratio_between_minus_one_and_one",
    }:
        if not Decimal("-1") <= value <= Decimal("1"):
            raise ValueError("result is outside [-1, 1]")
        return
    raise ValueError("invariant is not implemented by the trusted validator")


def _output_decimal(output: Any) -> Decimal:
    value = output.get("value") if isinstance(output, dict) and "value" in output else output
    return _decimal(value)


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("value is not decimal-compatible") from exc
    if not result.is_finite():
        raise ValueError("value must be finite")
    return result


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    try:
        if _is_json_schema(schema):
            _validate_json_schema(value, schema, path)
        else:
            _validate_compact_schema(value, schema, path)
    except GeneratedCapabilityValidationError:
        raise
    except Exception as exc:
        raise GeneratedCapabilityValidationError("output_schema", str(exc)) from exc


def _is_json_schema(schema: Mapping[str, Any]) -> bool:
    return bool({"$schema", "$id", "type", "properties", "required"} & set(schema))


def _validate_compact_schema(value: Any, schema: Mapping[str, Any], path: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    expected = set(schema)
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{path} field mismatch; missing={missing}, extra={extra}")
    for key, descriptor in schema.items():
        _validate_descriptor(value[key], descriptor, f"{path}.{key}")


def _validate_descriptor(value: Any, descriptor: Any, path: str) -> None:
    if isinstance(descriptor, dict):
        _validate_json_schema(value, descriptor, path)
        return
    if descriptor == "decimal":
        _decimal(value)
    elif descriptor == "number":
        is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not is_number or not math.isfinite(value):
            raise ValueError(f"{path} must be a finite number")
    elif descriptor == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{path} must be an integer")
    elif descriptor == "string":
        if not isinstance(value, str):
            raise ValueError(f"{path} must be a string")
    elif descriptor == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{path} must be a boolean")
    elif descriptor == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
    elif descriptor == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path} must be an array")
    elif value != descriptor:
        raise ValueError(f"{path} must equal declared literal {descriptor!r}")


def _validate_json_schema(value: Any, schema: Mapping[str, Any], path: str) -> None:
    supported = {
        "$id",
        "$schema",
        "additionalProperties",
        "const",
        "enum",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "items",
        "maximum",
        "minimum",
        "properties",
        "required",
        "type",
    }
    unsupported = set(schema) - supported
    if unsupported:
        raise ValueError(f"{path} uses unsupported schema keywords: {sorted(unsupported)}")
    expected_type = schema.get("type")
    if expected_type is not None:
        predicates = {
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
            "string": lambda item: isinstance(item, str),
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "boolean": lambda item: isinstance(item, bool),
            "null": lambda item: item is None,
        }
        if expected_type not in predicates:
            raise ValueError(f"{path} declares unsupported type {expected_type!r}")
        if not predicates[expected_type](value):
            raise ValueError(f"{path} is not of type {expected_type}")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path} does not match const")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} is not in enum")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be finite")
        for keyword, comparison in (
            ("minimum", lambda left, right: left >= right),
            ("maximum", lambda left, right: left <= right),
            ("exclusiveMinimum", lambda left, right: left > right),
            ("exclusiveMaximum", lambda left, right: left < right),
        ):
            if keyword in schema and not comparison(value, schema[keyword]):
                raise ValueError(f"{path} violates {keyword}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise ValueError(f"{path}.{key} is required")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            if extra:
                raise ValueError(f"{path} has additional properties: {sorted(extra)}")
        for key, child_schema in properties.items():
            if key in value:
                _validate_json_schema(value[key], child_schema, f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _validate_json_schema(item, schema["items"], f"{path}[{index}]")


def _expected_unit(schema: Mapping[str, Any]) -> str:
    if _is_json_schema(schema):
        unit_schema = schema.get("properties", {}).get("unit", {})
        expected = unit_schema.get("const")
        if expected is None and len(unit_schema.get("enum", [])) == 1:
            expected = unit_schema["enum"][0]
    else:
        expected = schema.get("unit")
    if (
        not isinstance(expected, str)
        or not expected.strip()
        or expected
        in {
            "string",
            "decimal",
            "number",
        }
    ):
        raise GeneratedCapabilityValidationError(
            "unit_validation", "output schema must declare one exact output unit"
        )
    return expected


def _validate_unit(output: Any, expected: str) -> None:
    if not isinstance(output, dict) or output.get("unit") != expected:
        raise GeneratedCapabilityValidationError(
            "unit_validation", f"output unit does not equal {expected!r}"
        )


def _schema_value_descriptor(schema: Mapping[str, Any]) -> Any:
    if _is_json_schema(schema):
        return schema.get("properties", {}).get("value", {}).get("type")
    return schema.get("value")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise GeneratedCapabilityValidationError(
            "deterministic_double_run", "output is not canonical JSON"
        ) from exc


def _json_hash(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"


def _json_clone(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _runtime_version(result: SandboxResult, sandbox: SandboxBackend) -> str:
    runtime = result.output.get("runtime", {})
    python = runtime.get("python") if isinstance(runtime, dict) else None
    if not isinstance(python, str):
        python = platform.python_version()
    image = sandbox.image if isinstance(sandbox, DockerSandboxBackend) else type(sandbox).__name__
    return f"Python {python} ({image})"


def _sandbox_record(
    candidate: GeneratedCapabilityCandidate,
    fixture: JsonObject,
    result: SandboxResult,
    runtime_version: str,
    *,
    backend: SandboxBackend,
) -> SandboxExecutionRecord:
    profile = result.security
    security_attestation = result.output.get("security_probe", {})
    if not isinstance(security_attestation, dict):
        security_attestation = {}
    return SandboxExecutionRecord(
        execution_id=f"SBX-{uuid4()}",
        build_id=candidate.build_id,
        backend="docker" if isinstance(backend, DockerSandboxBackend) else type(backend).__name__,
        implementation_hash=candidate.implementation_hash,
        runtime_version=runtime_version,
        input_fixture_hash=_json_hash(fixture),
        network_disabled=profile.get("network") == "none",
        read_only_root=profile.get("read_only_root") is True,
        non_root_user=profile.get("user") not in (None, "0", "0:0", "root"),
        resource_limits={
            key: profile[key]
            for key in ("memory", "cpus", "pids", "wall_timeout_seconds")
            if key in profile
        },
        security_attestation=_json_clone(security_attestation),
        exit_code=result.exit_code,
        output_hash=_json_hash(result.output["result"]),
        passed=result.passed,
        detail=(
            "Static, sandbox, edge, invariant, deterministic, schema, unit, "
            "and financial validation passed."
        ),
    )
