"""Versioned financial formula policy metadata shared by independent boundaries."""

REVENUE_GROWTH_FORMULA_ID = "revenue_growth_v1"
REVENUE_GROWTH_FORMULA_EXPRESSION = "(current_revenue - prior_revenue) / prior_revenue"
REVENUE_GROWTH_PRECONDITION = "prior_revenue > 0"
REVENUE_GROWTH_VALIDATION_REASON = "REVENUE_GROWTH_PRIOR_REVENUE_MUST_BE_POSITIVE"

# These additive policies apply only to explicitly owned, new WP04 requirements.
import re
from datetime import datetime
from decimal import (
    Clamped, Context, Decimal, DivisionByZero, FloatOperation, Inexact,
    InvalidOperation, Overflow, ROUND_HALF_EVEN, Rounded, Subnormal, Underflow,
)
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.domain.node_binding import BindingDenied, canonical_value, digest

WP04_SIGNALS = (Clamped, DivisionByZero, FloatOperation, Inexact, InvalidOperation,
                Overflow, Rounded, Subnormal, Underflow)
WP04_FLAGS_SCHEMA = 'wp04-revenue-growth-decimal-observation/v1'
WP04_SEMANTIC_POLICY = {
    'policy_id': 'WP04_RG_INPUT_SEMANTICS_V1',
    'selection': 'EXACT_UNIQUE_ADJACENT_FY_PAIR_V1',
    'period_basis': 'FY', 'actuality': ['ACTUAL', 'ESTIMATE'],
    'currency': 'EXACT_UPPERCASE_3', 'normalized_unit': 'CURRENCY',
    'original_scale': 'KNOWN_EQUAL', 'normalized_scale': 1,
    'sign': 'PRIOR_POSITIVE_CURRENT_SIGNED', 'quantization': 'NONE',
}
WP04_DECIMAL_POLICY = {
    'policy_id': 'WP04_RG_DECIMAL28_HALF_EVEN_V1', 'prec': 28,
    'rounding': 'ROUND_HALF_EVEN', 'Emin': -999999, 'Emax': 999999,
    'capitals': 1, 'clamp': 0,
    'flags': {'Clamped': False, 'DivisionByZero': False, 'FloatOperation': False,
              'Inexact': False, 'InvalidOperation': False, 'Overflow': False,
              'Rounded': False, 'Subnormal': False, 'Underflow': False},
    'traps': {'Clamped': False, 'DivisionByZero': True, 'FloatOperation': True,
              'Inexact': False, 'InvalidOperation': True, 'Overflow': True,
              'Rounded': False, 'Subnormal': False, 'Underflow': False},
    'input_quantization': 'NONE', 'output_quantization': 'NONE',
    'finite_output_required': True,
}


class MethodDenied(BindingDenied):
    def __init__(self, code, support='UNKNOWN', numeric='NONE'):
        self.support, self.numeric = support, numeric
        super().__init__(code)


def wp04_decimal_context():
    return Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                   capitals=1, clamp=0, flags=[],
                   traps=[DivisionByZero, FloatOperation, InvalidOperation, Overflow])


def wp04_flags(context):
    return {s.__name__: bool(context.flags[s]) for s in WP04_SIGNALS}


def validate_decimal_observation(receipt):
    if not isinstance(receipt, dict) or receipt.get('schema_version') != WP04_FLAGS_SCHEMA:
        raise MethodDenied('DECIMAL_FLAGS_OBSERVATION_ERROR', 'SUPPORTED', 'FAILED')
    count = receipt.get('capture_count')
    if type(count) is not int or count < 0:
        raise MethodDenied('DECIMAL_FLAGS_OBSERVATION_ERROR', 'SUPPORTED', 'FAILED')
    if count != 1:
        raise MethodDenied('DECIMAL_FLAGS_OBSERVATION_MISSING' if count == 0 else
                           'DECIMAL_FLAGS_OBSERVATION_AMBIGUOUS', 'SUPPORTED', 'FAILED')
    flags = receipt.get('flags')
    if (not isinstance(flags, dict) or set(flags) != {s.__name__ for s in WP04_SIGNALS}
            or any(type(v) is not bool for v in flags.values())):
        raise MethodDenied('DECIMAL_FLAGS_OBSERVATION_ERROR', 'SUPPORTED', 'FAILED')
    return dict(flags)


class MethodDescriptor(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    method_schema_version: Literal['wp04-method-descriptor/v1'] = 'wp04-method-descriptor/v1'
    policy_id: Literal['WP04_REVENUE_GROWTH_EXACT_V1'] = 'WP04_REVENUE_GROWTH_EXACT_V1'
    capability_id: Literal['revenue_growth'] = 'revenue_growth'
    capability_version: Literal['1.1.0'] = '1.1.0'
    formula_id: Literal['revenue_growth_v1'] = 'revenue_growth_v1'
    formula_version: Literal['1.0.0'] = '1.0.0'
    execution_backend: Literal['NATIVE'] = 'NATIVE'
    classification: Literal['NATIVE_EXISTING_METHOD'] = 'NATIVE_EXISTING_METHOD'
    implementation_ref: Literal['src.capabilities.financial.growth:RevenueGrowthCapability'] = 'src.capabilities.financial.growth:RevenueGrowthCapability'
    implementation_class: str = 'src.capabilities.financial.growth.RevenueGrowthCapability'
    load_policy_id: str = 'WP04_CPYTHON311_SOURCE_OBJECT_BINDING_V1'
    source_manifest: list[dict]
    source_manifest_digest: str
    semantic_policy_id: str = 'WP04_RG_INPUT_SEMANTICS_V1'
    semantic_policy_digest: str
    decimal_policy_id: str = 'WP04_RG_DECIMAL28_HALF_EVEN_V1'
    decimal_policy_digest: str
    effective_scope: dict
    descriptor_digest: str = ''


class MethodRequirement(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal['wp04-method-requirement/v1'] = 'wp04-method-requirement/v1'
    requirement_id: str = ''
    requirement_digest: str = ''
    scheme_id: str
    scheme_hash: str
    task_id: str
    run_id: str
    object_id: str
    requirement_state: Literal['REQUIRED', 'SUPPORTING', 'NOT_REQUESTED'] = 'REQUIRED'
    descriptor: MethodDescriptor
    input_selection_policy: Literal['EXACT_UNIQUE_ADJACENT_FY_PAIR_V1'] = 'EXACT_UNIQUE_ADJACENT_FY_PAIR_V1'

    def verify(self):
        try:
            type(self).model_validate(self.model_dump())
        except ValueError as exc:
            raise MethodDenied('METHOD_REQUIREMENT_IDENTITY_MISMATCH') from exc
        body = self.model_dump(exclude={'requirement_id', 'requirement_digest'})
        expected = digest(body, self.schema_version)
        if expected != self.requirement_digest or self.requirement_id != expected:
            raise MethodDenied('METHOD_REQUIREMENT_IDENTITY_MISMATCH')
        d = self.descriptor
        if d.descriptor_digest != digest(d.model_dump(exclude={'descriptor_digest'}), d.method_schema_version):
            raise MethodDenied('METHOD_DESCRIPTOR_IDENTITY_MISMATCH')


class MethodObservation(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal['wp04-method-observation/v1'] = 'wp04-method-observation/v1'
    observation_id: str = ''
    run_id: str
    object_id: str
    task_id: str
    owner_id: str
    owner_generation: int
    task_fingerprint: str
    requirement_id: str
    requirement_digest: str
    requirement_state: Literal['REQUIRED', 'SUPPORTING', 'NOT_REQUESTED']
    descriptor: MethodDescriptor | None = None
    descriptor_digest: str | None = None
    input_binding: dict | None = None
    input_identity_digest: str | None = None
    observed_input_refs: list[str] = []
    missing_fields: list[str] = []
    verification_state: str = 'UNVERIFIED'
    admission_binding_id: str | None = None
    reservation_id: str | None = None
    B_ref: str | None = None
    phase: Literal['DENIED_BEFORE_A', 'PREPARED', 'DENIED', 'EXECUTION_FINISHED']
    support_status: Literal['SUPPORTED', 'UNSUPPORTED', 'MISSING_METHOD', 'MISSING_INPUT', 'NOT_APPLICABLE', 'UNKNOWN']
    diagnostic_code: str
    numeric_outcome: Literal['NONE', 'STARTED', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'RESULT_UNKNOWN']
    calculation_ref: str | None = None
    source_manifest_digest: str | None = None
    semantic_policy_digest: str | None = None
    decimal_policy_digest: str | None = None
    dispatch_count: Literal[0, 1] = 0
    previous_observation_id: str | None = None
    observed_at: datetime
    audit_duration_ms: int | Literal['UNKNOWN'] = 'UNKNOWN'
    authority_status: Literal['COMMITTED'] = 'COMMITTED'

    def identified(self):
        return self.model_copy(update={'observation_id': digest(
            self.model_dump(exclude={'observation_id'}), self.schema_version)})


def wp04_decimal(value):
    if value is None:
        raise MethodDenied('MISSING_REQUIRED_INPUT', 'MISSING_INPUT')
    if not isinstance(value, (str, Decimal)) or isinstance(value, bool):
        raise MethodDenied('SEMANTIC_INPUT_MISMATCH', 'UNSUPPORTED')
    if isinstance(value, str) and not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?', value):
        raise MethodDenied('SEMANTIC_INPUT_MISMATCH', 'UNSUPPORTED')
    result = Decimal(value)
    if not result.is_finite():
        raise MethodDenied('SEMANTIC_INPUT_MISMATCH', 'UNSUPPORTED')
    return result


def method_metadata_view(calculation):
    return calculation.parameters.get('wp04_method_binding') or {'status': 'LEGACY_UNKNOWN'}
