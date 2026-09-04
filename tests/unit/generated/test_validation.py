from __future__ import annotations

from decimal import Decimal

import pytest

from src.capabilities.generated.models import CodeBuilderOutput, GeneratedCapabilityCandidate
from src.capabilities.generated.validation import (
    CallableFinancialValidationPolicy,
    CapabilityValidationPlan,
    GeneratedCapabilityExecutionError,
    GeneratedCapabilityValidationError,
    GeneratedCapabilityValidator,
    StaticCapabilityValidationPlanProvider,
    source_sha256,
)
from src.domain.capability import CapabilityContext
from src.domain.enums import CapabilityLifecycle
from src.tooling.generated_sandbox import SandboxRequest, SandboxResult

SOURCE = """
from decimal import Decimal

def execute(inputs):
    revenue = Decimal(inputs["revenue"])
    if revenue == 0:
        raise ValueError("revenue must not be zero")
    value = Decimal(inputs["gross_profit"]) / revenue
    return {"value": str(value), "unit": "ratio"}
"""

TESTS = """
from decimal import Decimal

def run_tests(execute, fixture):
    result = execute({"gross_profit": "40", "revenue": "100"})
    assert Decimal(result["value"]) == Decimal("0.4")
    assert result["unit"] == "ratio"
    return {"passed": 2}
"""


def candidate(**updates: object) -> GeneratedCapabilityCandidate:
    source = str(updates.pop("source_code", SOURCE))
    output = CodeBuilderOutput(
        capability_id="gross_margin",
        version="1.0.0-generated",
        purpose="Calculate gross margin.",
        input_schema={"gross_profit": "decimal", "revenue": "decimal"},
        output_schema={"value": "decimal", "unit": "ratio"},
        formula_id="gross_margin_v1",
        formula_description="gross_profit / revenue",
        source_code=source,
        unit_tests=str(updates.pop("unit_tests", TESTS)),
        financial_invariants=list(
            updates.pop("financial_invariants", ["revenue_non_zero", "result_is_finite"])
        ),
        allowed_imports=list(updates.pop("allowed_imports", ["decimal"])),
    )
    implementation_hash = str(updates.pop("implementation_hash", source_sha256(source)))
    assert not updates
    return GeneratedCapabilityCandidate(
        build_id="BUILD-1",
        output=output,
        implementation_hash=implementation_hash,
        provider="teamorouter",
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        attempted_models=("gpt-5.6-sol",),
        input_tokens=10,
        output_tokens=20,
        latency_ms=1.0,
    )


def financial_policy() -> CallableFinancialValidationPolicy:
    def validate(candidate, inputs, output):
        assert candidate.output.formula_id == "gross_margin_v1"
        expected = Decimal(inputs["gross_profit"]) / Decimal(inputs["revenue"])
        if Decimal(output["value"]) != expected:
            raise ValueError("formula mismatch")

    return CallableFinancialValidationPolicy(validate)


def plan(policy=None) -> CapabilityValidationPlan:
    return CapabilityValidationPlan(
        primary_fixture={"gross_profit": "40", "revenue": "100"},
        edge_case_fixtures=(
            {"gross_profit": "0", "revenue": "100"},
            {"gross_profit": "125", "revenue": "100"},
        ),
        financial_policy=policy or financial_policy(),
    )


class ProgressSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def static_validated(self, implementation_hash: str) -> None:
        self.calls.append(("static", implementation_hash))

    async def sandbox_started(self, implementation_hash: str) -> None:
        self.calls.append(("sandbox", implementation_hash))

    async def tests_passed(self, implementation_hash: str) -> None:
        self.calls.append(("tests", implementation_hash))

    async def financial_validated(self, implementation_hash: str) -> None:
        self.calls.append(("financial", implementation_hash))


class FormulaSandbox:
    def __init__(self, *, mutate_run: int | None = None, fail: bool = False) -> None:
        self.calls: list[SandboxRequest] = []
        self.mutate_run = mutate_run
        self.fail = fail

    def execute(self, request: SandboxRequest) -> SandboxResult:
        self.calls.append(request)
        if self.fail:
            return sandbox_result({}, passed=False, exit_code=1)
        value = Decimal(request.fixture["gross_profit"]) / Decimal(request.fixture["revenue"])
        if self.mutate_run == len(self.calls):
            value += Decimal("0.01")
        return sandbox_result({"value": str(value), "unit": "ratio"})


def sandbox_result(result: object, *, passed: bool = True, exit_code: int = 0) -> SandboxResult:
    return SandboxResult(
        passed=passed,
        exit_code=exit_code,
        output={
            "ok": passed,
            "result": result,
            "runtime": {"implementation": "CPython", "python": "3.11.16"},
        },
        duration_ms=1,
        security={
            "network": "none",
            "read_only_root": True,
            "user": "65534:65534",
            "memory": "128m",
            "cpus": 0.5,
            "pids": 32,
            "wall_timeout_seconds": 10,
            "cap_drop": "ALL",
            "no_new_privileges": True,
            "host_mounts": [],
            "python_dont_write_bytecode": True,
        },
    )


def validator(sandbox, validation_plan=None) -> GeneratedCapabilityValidator:
    return GeneratedCapabilityValidator(
        sandbox=sandbox,
        plans=StaticCapabilityValidationPlanProvider(validation_plan or plan()),
    )


@pytest.mark.asyncio
async def test_complete_validation_order_metadata_and_calculation_record() -> None:
    generated = candidate()
    sandbox = FormulaSandbox()
    progress = ProgressSpy()

    handoff = await validator(sandbox).validate(generated, progress=progress)

    handoff.assert_ready_for_task_approval(generated)
    assert progress.calls == [
        ("static", generated.implementation_hash),
        ("sandbox", generated.implementation_hash),
        ("tests", generated.implementation_hash),
        ("financial", generated.implementation_hash),
    ]
    validation = handoff.validation
    assert validation.lifecycle is CapabilityLifecycle.FINANCIAL_VALIDATED
    assert [finding["stage"] for finding in validation.findings] == [
        "static_validation",
        "syntax_compile",
        "unit_tests",
        "edge_cases",
        "financial_invariants",
        "deterministic_double_run",
        "output_schema",
        "unit_validation",
        "identity",
        "financial_validation",
    ]
    identity = validation.findings[-2]
    assert identity["source_hash"] == generated.implementation_hash
    assert identity["python_version"].startswith("Python 3.11.16")
    assert identity["capability_version"] == "1.0.0-generated"
    assert identity["formula_id"] == "gross_margin_v1"
    assert identity["schema_version"] == "generated-capability-validation/v1"
    assert handoff.sandbox_execution.network_disabled
    assert handoff.sandbox_execution.read_only_root
    assert handoff.sandbox_execution.non_root_user

    calculation = await handoff.capability.execute(
        {"calculation_id": "CALC-1", "gross_profit": "40", "revenue": "100"},
        CapabilityContext(
            run_id="RUN-1",
            task_id="TASK-1",
            accepted_evidence_ids=["EVD-GROSS", "EVD-REVENUE"],
        ),
    )
    assert calculation.output_value == Decimal("0.4")
    assert calculation.output_unit == "ratio"
    assert calculation.implementation_hash == generated.implementation_hash
    assert calculation.source_ref == "generated://BUILD-1/source.py"
    assert calculation.input_evidence_ids == ["EVD-GROSS", "EVD-REVENUE"]
    assert calculation.runtime_version.startswith("Python 3.11.16")


@pytest.mark.asyncio
async def test_static_rejection_stops_before_sandbox_and_does_not_report_success() -> None:
    sandbox = FormulaSandbox()
    progress = ProgressSpy()
    rejected = candidate(source_code="import os\n\ndef execute(inputs):\n    return {}\n")

    with pytest.raises(GeneratedCapabilityValidationError, match="static_validation"):
        await validator(sandbox).validate(rejected, progress=progress)

    assert sandbox.calls == []
    assert progress.calls == []


@pytest.mark.asyncio
async def test_undeclared_allowed_import_is_still_rejected() -> None:
    sandbox = FormulaSandbox()
    progress = ProgressSpy()
    generated = candidate(allowed_imports=[])
    with pytest.raises(GeneratedCapabilityValidationError, match="absent from approved"):
        await validator(sandbox).validate(generated, progress=progress)


@pytest.mark.asyncio
async def test_decimal_contract_rejects_binary_float_implementation() -> None:
    generated = candidate(
        source_code=(
            "def execute(inputs):\n"
            "    value = float(inputs['gross_profit']) / float(inputs['revenue'])\n"
            "    return {'value': str(value), 'unit': 'ratio'}\n"
        ),
        allowed_imports=["decimal"],
    )

    with pytest.raises(GeneratedCapabilityValidationError, match="Decimal runtime"):
        await validator(FormulaSandbox()).validate(generated, progress=ProgressSpy())


@pytest.mark.asyncio
async def test_declared_import_outside_sandbox_policy_is_rejected() -> None:
    generated = candidate(allowed_imports=["decimal", "os"])
    with pytest.raises(GeneratedCapabilityValidationError, match="outside sandbox policy"):
        await validator(FormulaSandbox()).validate(generated, progress=ProgressSpy())


@pytest.mark.asyncio
async def test_incomplete_sandbox_security_profile_is_rejected() -> None:
    class InsecureSandbox(FormulaSandbox):
        def execute(self, request: SandboxRequest) -> SandboxResult:
            result = super().execute(request)
            return SandboxResult(
                passed=result.passed,
                exit_code=result.exit_code,
                output=result.output,
                duration_ms=result.duration_ms,
                security={"network": "bridge"},
            )

    with pytest.raises(GeneratedCapabilityValidationError, match="security profile"):
        await validator(InsecureSandbox()).validate(candidate(), progress=ProgressSpy())


@pytest.mark.asyncio
async def test_sandbox_failure_is_not_reported_as_test_passed() -> None:
    progress = ProgressSpy()
    with pytest.raises(GeneratedCapabilityValidationError, match="unit_tests"):
        await validator(FormulaSandbox(fail=True)).validate(candidate(), progress=progress)
    assert [call[0] for call in progress.calls] == ["static", "sandbox"]


@pytest.mark.asyncio
async def test_deterministic_double_run_rejects_canonical_output_change() -> None:
    progress = ProgressSpy()
    # 1 primary + 2 edges, then the first deterministic repeat is call 4.
    with pytest.raises(GeneratedCapabilityValidationError, match="canonical outputs differ"):
        await validator(FormulaSandbox(mutate_run=4)).validate(candidate(), progress=progress)
    assert "tests" not in [call[0] for call in progress.calls]


@pytest.mark.asyncio
async def test_hash_mismatch_fails_before_financial_approval() -> None:
    progress = ProgressSpy()
    generated = candidate(implementation_hash="sha256:not-the-source")
    with pytest.raises(GeneratedCapabilityValidationError, match="implementation hash"):
        await validator(FormulaSandbox()).validate(generated, progress=progress)
    assert "financial" not in [call[0] for call in progress.calls]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bad_output", "expected_stage"),
    [
        ({"value": "0.4", "unit": "percent"}, "output_schema"),
        ({"value": "not-a-decimal", "unit": "ratio"}, "financial_invariants"),
    ],
)
async def test_output_contract_failure_is_explicit(bad_output: object, expected_stage: str) -> None:
    class BadOutputSandbox(FormulaSandbox):
        def execute(self, request: SandboxRequest) -> SandboxResult:
            self.calls.append(request)
            return sandbox_result(bad_output)

    with pytest.raises(GeneratedCapabilityValidationError) as caught:
        await validator(BadOutputSandbox()).validate(candidate(), progress=ProgressSpy())
    assert caught.value.stage == expected_stage


@pytest.mark.asyncio
async def test_non_python_311_sandbox_runtime_is_rejected() -> None:
    class WrongRuntimeSandbox(FormulaSandbox):
        def execute(self, request: SandboxRequest) -> SandboxResult:
            result = super().execute(request)
            result.output["runtime"]["python"] = "3.12.1"
            return result

    with pytest.raises(GeneratedCapabilityValidationError) as caught:
        await validator(WrongRuntimeSandbox()).validate(candidate(), progress=ProgressSpy())
    assert caught.value.stage == "runtime_version"


@pytest.mark.asyncio
async def test_unknown_financial_invariant_is_a_hard_failure() -> None:
    generated = candidate(financial_invariants=["generated_code_says_it_is_correct"])
    with pytest.raises(GeneratedCapabilityValidationError, match="not implemented"):
        await validator(FormulaSandbox()).validate(generated, progress=ProgressSpy())


@pytest.mark.asyncio
async def test_trusted_financial_policy_failure_is_a_hard_failure() -> None:
    def reject(candidate, inputs, output):
        del candidate, inputs, output
        raise ValueError("oracle mismatch")

    rejected_plan = plan(CallableFinancialValidationPolicy(reject))
    progress = ProgressSpy()
    with pytest.raises(GeneratedCapabilityValidationError, match="oracle mismatch"):
        await validator(FormulaSandbox(), rejected_plan).validate(candidate(), progress=progress)
    assert [call[0] for call in progress.calls] == ["static", "sandbox", "tests"]


@pytest.mark.asyncio
async def test_generated_runtime_failure_never_returns_failed_calculation_record() -> None:
    handoff = await validator(FormulaSandbox()).validate(candidate(), progress=ProgressSpy())
    handoff.capability._sandbox = FormulaSandbox(fail=True)
    with pytest.raises(GeneratedCapabilityExecutionError):
        await handoff.capability.execute(
            {"gross_profit": "40", "revenue": "100"},
            CapabilityContext(run_id="RUN-1", task_id="TASK-1"),
        )
