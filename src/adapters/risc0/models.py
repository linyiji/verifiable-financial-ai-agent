from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

INPUT_SCHEMA_VERSION = "risc0_revenue_growth_input_v1"
JOURNAL_SCHEMA_VERSION = "risc0_revenue_growth_journal_v1"
FORMULA_ID = "revenue_growth_v1"
CAPABILITY_ID = "revenue_growth"


class _Hasher(Protocol):
    def update(self, value: bytes) -> None: ...

    def hexdigest(self) -> str: ...


class CanonicalRevenueInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prior_revenue_minor: int
    current_revenue_minor: int
    currency: str = Field(pattern=r"^[A-Z]{1,16}$")
    scale: int = Field(ge=0, le=18)

    @model_validator(mode="after")
    def validate_integer_domain(self) -> CanonicalRevenueInputs:
        minimum = -(2**63)
        maximum = 2**63 - 1
        if not minimum <= self.prior_revenue_minor <= maximum:
            raise ValueError("prior_revenue_minor must fit signed 64-bit integer")
        if not minimum <= self.current_revenue_minor <= maximum:
            raise ValueError("current_revenue_minor must fit signed 64-bit integer")
        if self.prior_revenue_minor == 0:
            raise ValueError("prior revenue must not be zero")
        return self


class CanonicalRevenueGrowthResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    growth_numerator: int
    growth_denominator: int = Field(gt=0)
    unit: str = Field(pattern=r"^ratio$")


class RiscZeroRevenueGrowthInput(BaseModel):
    """Adapter-owned proof input; shared domain contracts remain frozen."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=f"^{INPUT_SCHEMA_VERSION}$")
    run_id: str = Field(min_length=1)
    calculation_id: str = Field(min_length=1)
    formula_id: str = Field(pattern=f"^{FORMULA_ID}$")
    capability_id: str = Field(pattern=f"^{CAPABILITY_ID}$")
    implementation_hash: str = Field(min_length=1)
    input_evidence_refs: tuple[str, str]
    canonical_inputs: CanonicalRevenueInputs
    input_commitment: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    expected_output_commitment: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_bindings(self) -> RiscZeroRevenueGrowthInput:
        if any(not reference for reference in self.input_evidence_refs):
            raise ValueError("evidence references must not be empty")
        if len(set(self.input_evidence_refs)) != 2:
            raise ValueError("evidence references must be distinct")
        expected_result = calculate_revenue_growth(self.canonical_inputs)
        if output_commitment(self.formula_id, expected_result) != self.expected_output_commitment:
            raise ValueError("expected output commitment mismatch")
        if input_commitment(self) != self.input_commitment:
            raise ValueError("input commitment mismatch")
        return self


def _write_field(hasher: _Hasher, name: str, value: str | bytes) -> None:
    name_bytes = name.encode("utf-8")
    value_bytes = value.encode("utf-8") if isinstance(value, str) else value
    hasher.update(len(name_bytes).to_bytes(4, "big"))
    hasher.update(name_bytes)
    hasher.update(len(value_bytes).to_bytes(8, "big"))
    hasher.update(value_bytes)


def _finish_hash(hasher: _Hasher) -> str:
    return f"sha256:{hasher.hexdigest()}"


def calculate_revenue_growth(
    inputs: CanonicalRevenueInputs,
) -> CanonicalRevenueGrowthResult:
    numerator = inputs.current_revenue_minor - inputs.prior_revenue_minor
    denominator = abs(inputs.prior_revenue_minor)
    divisor = _greatest_common_divisor(numerator, denominator)
    return CanonicalRevenueGrowthResult(
        growth_numerator=numerator // divisor,
        growth_denominator=denominator // divisor,
        unit="ratio",
    )


def _greatest_common_divisor(left: int, right: int) -> int:
    left = abs(left)
    right = abs(right)
    while right:
        left, right = right, left % right
    return left


def output_commitment(formula_id: str, result: CanonicalRevenueGrowthResult) -> str:
    hasher = hashlib.sha256()
    _write_field(hasher, "domain", "verifiable-financial-agent/revenue-growth-output/v1")
    _write_field(hasher, "formula_id", formula_id)
    _write_field(hasher, "growth_numerator", str(result.growth_numerator))
    _write_field(hasher, "growth_denominator", str(result.growth_denominator))
    _write_field(hasher, "unit", result.unit)
    return _finish_hash(hasher)


def input_commitment(input_data: RiscZeroRevenueGrowthInput) -> str:
    hasher = hashlib.sha256()
    _write_field(hasher, "domain", "verifiable-financial-agent/revenue-growth-input/v1")
    _write_field(hasher, "schema_version", input_data.schema_version)
    _write_field(hasher, "run_id", input_data.run_id)
    _write_field(hasher, "calculation_id", input_data.calculation_id)
    _write_field(hasher, "formula_id", input_data.formula_id)
    _write_field(hasher, "capability_id", input_data.capability_id)
    _write_field(hasher, "implementation_hash", input_data.implementation_hash)
    _write_field(hasher, "input_evidence_ref_count", str(len(input_data.input_evidence_refs)))
    for evidence_ref in input_data.input_evidence_refs:
        _write_field(hasher, "input_evidence_ref", evidence_ref)
    _write_field(
        hasher, "prior_revenue_minor", str(input_data.canonical_inputs.prior_revenue_minor)
    )
    _write_field(
        hasher,
        "current_revenue_minor",
        str(input_data.canonical_inputs.current_revenue_minor),
    )
    _write_field(hasher, "currency", input_data.canonical_inputs.currency)
    _write_field(hasher, "scale", str(input_data.canonical_inputs.scale))
    _write_field(hasher, "expected_output_commitment", input_data.expected_output_commitment)
    return _finish_hash(hasher)


def build_proof_input(
    *,
    run_id: str,
    calculation_id: str,
    implementation_hash: str,
    input_evidence_refs: tuple[str, str],
    canonical_inputs: CanonicalRevenueInputs,
) -> RiscZeroRevenueGrowthInput:
    result = calculate_revenue_growth(canonical_inputs)
    output_hash = output_commitment(FORMULA_ID, result)
    provisional = RiscZeroRevenueGrowthInput.model_construct(
        schema_version=INPUT_SCHEMA_VERSION,
        run_id=run_id,
        calculation_id=calculation_id,
        formula_id=FORMULA_ID,
        capability_id=CAPABILITY_ID,
        implementation_hash=implementation_hash,
        input_evidence_refs=input_evidence_refs,
        canonical_inputs=canonical_inputs,
        input_commitment="sha256:" + "0" * 64,
        expected_output_commitment=output_hash,
    )
    return RiscZeroRevenueGrowthInput.model_validate(
        provisional.model_copy(update={"input_commitment": input_commitment(provisional)})
    )


def load_proof_input(path: str | Path) -> RiscZeroRevenueGrowthInput:
    return RiscZeroRevenueGrowthInput.model_validate_json(Path(path).read_text(encoding="utf-8"))


def write_proof_input(path: str | Path, proof_input: RiscZeroRevenueGrowthInput) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(proof_input.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(target, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
