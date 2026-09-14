from __future__ import annotations

import hashlib
import platform
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CalculationSourceProvenance:
    """Stable implementation identity fields for a CalculationRecord."""

    code_hash: str
    source_ref: str
    runtime_version: str


def sha256_source_bytes(source: bytes) -> str:
    """Hash implementation bytes without run-specific values or filesystem metadata."""

    return f"sha256:{hashlib.sha256(source).hexdigest()}"


def calculation_source_provenance(
    source_path: str | Path,
    *,
    source_ref: str,
) -> CalculationSourceProvenance:
    """Fingerprint the checked-in capability source used to produce a calculation."""

    path = Path(source_path)
    if not source_ref.strip():
        raise ValueError("source_ref must not be empty")
    source = path.read_bytes()
    return CalculationSourceProvenance(
        code_hash=sha256_source_bytes(source),
        source_ref=source_ref,
        runtime_version=f"Python {platform.python_version()}",
    )

# WP04 bounded source/load binding. Expected manifest-file hash is supplied by
# the composition owner; observed bytes never become their own authorization.
import ast
import decimal
import importlib
import inspect
import json
import sys
import types

from src.domain.financial_validation import (
    MethodDenied, MethodDescriptor, WP04_DECIMAL_POLICY, WP04_SEMANTIC_POLICY,
)
from src.domain.node_binding import digest

WP04_MANIFEST_PATHS = (
    'src/capabilities/financial/common.py',
    'src/capabilities/financial/growth.py',
    'src/capabilities/provenance.py',
    'src/domain/financial_semantics.py',
    'src/domain/financial_validation.py',
)
WP04_SCOPE = {
    'fixed_initial': True, 'new_bound': True, 'execution_mode': 'DEFAULT',
    'task_type': 'fundamental_analysis', 'assigned_agent': 'fundamental_analyst',
    'skill_id': 'fundamental_analysis_v1', 'explicit_opt_in': True,
    'calculation_id': 'revenue_growth', 'generated': False, 'recovery': False,
}


def wp04_descriptor(expected_manifest_hash):
    root = Path(__file__).resolve().parents[2]
    manifest_file = root / 'src/capabilities/financial/revenue_growth_wp04_manifest.json'
    try:
        raw = manifest_file.read_bytes()
        if not expected_manifest_hash or sha256_source_bytes(raw) != expected_manifest_hash:
            raise MethodDenied('METHOD_MANIFEST_IDENTITY_MISMATCH')
        manifest = json.loads(raw)
        if (manifest['schema_version'] != 'wp04-source-manifest/v1' or
                [entry['path'] for entry in manifest['entries']] != list(WP04_MANIFEST_PATHS)):
            raise MethodDenied('METHOD_MANIFEST_IDENTITY_MISMATCH')
        for entry in manifest['entries']:
            if set(entry) != {'path', 'sha256'} or sha256_source_bytes((root / entry['path']).read_bytes()) != entry['sha256']:
                raise MethodDenied('METHOD_SOURCE_IDENTITY_MISMATCH')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, MethodDenied):
            raise
        raise MethodDenied('METHOD_MANIFEST_IDENTITY_MISMATCH') from exc
    descriptor = MethodDescriptor(
        source_manifest=manifest['entries'],
        source_manifest_digest=digest(manifest['entries'], 'wp04-source-manifest/v1'),
        semantic_policy_digest=digest(WP04_SEMANTIC_POLICY, 'wp04-input-semantics/v1'),
        decimal_policy_digest=digest(WP04_DECIMAL_POLICY, 'wp04-decimal-policy/v1'),
        effective_scope=dict(WP04_SCOPE),
    )
    return descriptor.model_copy(update={'descriptor_digest': digest(
        descriptor.model_dump(exclude={'descriptor_digest'}), descriptor.method_schema_version)})


def _code_shape(code):
    def constant(value):
        if isinstance(value, types.CodeType):
            return _code_shape(value)
        return value
    return (code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount,
            code.co_nlocals, code.co_stacksize, code.co_flags, code.co_code,
            code.co_names, code.co_varnames, code.co_freevars, code.co_cellvars,
            code.co_exceptiontable, tuple(constant(v) for v in code.co_consts))


def _compiled_codes(code):
    result = {code.co_qualname: code}
    for item in code.co_consts:
        if isinstance(item, types.CodeType):
            result.update(_compiled_codes(item))
    return result


def _verify_source_objects(module, path):
    source = path.read_bytes()
    codes = _compiled_codes(compile(source, str(path), 'exec', dont_inherit=True))
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            obj = getattr(module, node.name, None)
            pairs = [(node.name, obj)]
            if isinstance(node, ast.ClassDef):
                if (not isinstance(obj, type) or obj.__module__ != module.__name__
                        or obj.__qualname__ != node.name):
                    raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
                pairs = [(node.name + '.' + child.name, getattr(obj, child.name, None))
                         for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for qualified, function in pairs:
                if hasattr(function, '__wrapped__'):
                    from contextlib import contextmanager
                    if qualified != 'capture_revenue_growth_decimal_observation' or (
                            function.__code__ is not contextmanager(lambda: None).__code__
                            or function.__closure__ is None or len(function.__closure__) != 1
                            or function.__closure__[0].cell_contents is not function.__wrapped__):
                        raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
                    function = function.__wrapped__
                if inspect.ismethod(function):
                    function = function.__func__
                if (not isinstance(function, types.FunctionType) or function.__globals__ is not vars(module)
                        or function.__module__ != module.__name__ or function.__qualname__ != qualified
                        or qualified not in codes or _code_shape(function.__code__) != _code_shape(codes[qualified])):
                    raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
        elif isinstance(node, ast.ImportFrom) and node.module and node.module != '__future__':
            imported = importlib.import_module(node.module)
            for alias in node.names:
                if alias.name != '*' and getattr(module, alias.asname or alias.name, None) is not getattr(imported, alias.name):
                    raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
        elif isinstance(node, ast.Import):
            for alias in node.names:
                expected = importlib.import_module(alias.name if alias.asname else alias.name.split('.')[0])
                if getattr(module, alias.asname or alias.name.split('.')[0], None) is not expected:
                    raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            try:
                expected = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                        and isinstance(node.value.func.value, ast.Name)
                        and node.value.func.value.id == 're' and node.value.func.attr == 'compile'):
                    import re
                    expected_pattern = ast.literal_eval(node.value.args[0])
                    for target in targets:
                        observed = getattr(module, target.id, None)
                        if (not isinstance(observed, re.Pattern) or observed.pattern != expected_pattern
                                or observed.flags != re.compile(expected_pattern).flags):
                            raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
                continue
            for target in targets:
                if isinstance(target, ast.Name) and getattr(module, target.id, object()) != expected:
                    raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')


@dataclass(frozen=True, slots=True)
class _WP04LoadExpectation:
    registry: object
    runtime: object
    backend: object
    capability: object
    descriptor_json: str
    definition_json: str
    bindings: tuple


def _load_object_state(value):
    if isinstance(value, types.FunctionType):
        return repr((value.__module__, value.__qualname__, _code_shape(value.__code__),
                     value.__defaults__, value.__kwdefaults__))
    return repr(value)


def _loaded_bindings(descriptor):
    bindings = []
    root = Path(__file__).resolve().parents[2]
    for entry in descriptor.source_manifest:
        module = importlib.import_module(entry['path'][:-3].replace('/', '.'))
        # Freeze referenced globals as objects AND values; no mutable alias snapshot.
        for name, value in sorted(vars(module).items()):
            if not name.startswith('__'):
                bindings.append((module, name, value, _load_object_state(value)))
        for node in ast.parse((root / entry['path']).read_bytes()).body:
            if isinstance(node, ast.ClassDef):
                cls = getattr(module, node.name)
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        value = getattr(cls, child.name)
                        if inspect.ismethod(value):
                            value = value.__func__
                        bindings.append((cls, child.name, value, _load_object_state(value)))
    return tuple(bindings)


def capture_wp04_load_expectation(registry, runtime, manifest_hash):
    """Composition initialization only; never used by dispatch to refresh trust."""
    descriptor = wp04_descriptor(manifest_hash)
    capability, _ = verify_wp04_method(registry, runtime, descriptor, manifest_hash, _capture=True)
    from src.domain.enums import CapabilityBackend
    backend = runtime._backends[CapabilityBackend.NATIVE]
    composition_methods = tuple((cls, name, getattr(cls, name), _load_object_state(getattr(cls, name)))
                                for cls, name in ((type(registry), 'get'),
                                                  (type(runtime), 'execute'), (type(backend), 'execute')))
    expectation = _WP04LoadExpectation(
        registry, runtime, runtime._backends[CapabilityBackend.NATIVE], capability,
        descriptor.model_dump_json(),
        capability.definition.model_dump_json(exclude={'created_at'}),
        _loaded_bindings(descriptor) + composition_methods)
    return expectation


def verify_wp04_method(registry, runtime, descriptor, expected_manifest_hash, *,
                       expectation=None, _capture=False):
    from src.capabilities.registry import CapabilityRegistry
    from src.capabilities.financial.growth import RevenueGrowthCapability, _growth_observer
    from contextvars import ContextVar
    from src.domain.enums import CapabilityBackend
    from src.tooling.runtime import ToolRuntime, _WP04_RUNTIME_EXECUTE
    from src.tooling.native import NativeToolBackend, _WP04_NATIVE_EXECUTE

    if type(registry) is not CapabilityRegistry or 'get' in vars(registry):
        raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
    # Availability precedes input checks, including missing evidence.
    try:
        capability = registry.get('revenue_growth', '1.1.0')
    except (KeyError, ValueError) as exc:
        raise MethodDenied('MISSING_EXACT_METHOD', 'MISSING_METHOD') from exc
    if type(runtime) is not ToolRuntime or runtime._registry is not registry or 'execute' in vars(runtime) or ToolRuntime.execute is not _WP04_RUNTIME_EXECUTE:
        raise MethodDenied('METHOD_BACKEND_IDENTITY_MISMATCH')
    backend = runtime._backends.get(CapabilityBackend.NATIVE)
    if (type(backend) is not NativeToolBackend or backend._registry is not registry
            or 'execute' in vars(backend) or NativeToolBackend.execute is not _WP04_NATIVE_EXECUTE
            or capability.definition.backend is not CapabilityBackend.NATIVE):
        raise MethodDenied('METHOD_BACKEND_IDENTITY_MISMATCH')
    if type(capability) is not RevenueGrowthCapability or vars(capability):
        raise MethodDenied('METHOD_IMPLEMENTATION_IDENTITY_MISMATCH')
    d = capability.definition
    from src.domain.capability import CapabilityDefinition
    approved = CapabilityDefinition(
        capability_id='revenue_growth', version='1.1.0', name='Revenue Growth',
        category='financial_calculation', backend=CapabilityBackend.NATIVE,
        input_schema={'prior': 'EvidenceRecord', 'current': 'EvidenceRecord'},
        output_schema={'calculation': 'CalculationRecord'}, deterministic=True,
        proof_eligible=True, lifecycle='CERTIFIED', owner='system',
        implementation_ref='src.capabilities.financial.growth:RevenueGrowthCapability')
    if d.model_dump(exclude={'created_at'}) != approved.model_dump(exclude={'created_at'}):
        raise MethodDenied('METHOD_IMPLEMENTATION_IDENTITY_MISMATCH')
    if not isinstance(_growth_observer, ContextVar) or _growth_observer.name != 'wp04_growth_observer':
        raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
    from src.domain.financial_validation import WP04_SIGNALS
    if WP04_SIGNALS != tuple(getattr(decimal, name) for name in (
            'Clamped', 'DivisionByZero', 'FloatOperation', 'Inexact', 'InvalidOperation',
            'Overflow', 'Rounded', 'Subnormal', 'Underflow')):
        raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
    expected = wp04_descriptor(expected_manifest_hash)
    if descriptor != expected:
        raise MethodDenied('METHOD_DESCRIPTOR_IDENTITY_MISMATCH')
    if sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 11):
        raise MethodDenied('METHOD_LOAD_RUNTIME_UNSUPPORTED')
    root = Path(__file__).resolve().parents[2]
    for entry in expected.source_manifest:
        name = entry['path'][:-3].replace('/', '.')
        module = importlib.import_module(name)
        if Path(module.__file__).resolve() != root / entry['path']:
            raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
        _verify_source_objects(module, root / entry['path'])
    if not _capture:
        frozen = expectation if expectation is not None else getattr(runtime, '_wp04_load_expectation', None)
        if not isinstance(frozen, _WP04LoadExpectation):
            raise MethodDenied('METHOD_LOAD_EXPECTATION_MISSING')
        if (registry is not frozen.registry or runtime is not frozen.runtime
                or backend is not frozen.backend or capability is not frozen.capability
                or descriptor.model_dump_json() != frozen.descriptor_json
                or d.model_dump_json(exclude={'created_at'}) != frozen.definition_json):
            raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
        for owner, name, trusted, state in frozen.bindings:
            observed = getattr(owner, name, None)
            if inspect.ismethod(observed):
                observed = observed.__func__
            if observed is not trusted or _load_object_state(observed) != state:
                raise MethodDenied('METHOD_LOAD_IDENTITY_MISMATCH')
    return capability, {
        'load_policy_id': expected.load_policy_id,
        'descriptor_digest': expected.descriptor_digest,
        'implementation_class': expected.implementation_class,
        'source_manifest_digest': expected.source_manifest_digest,
        'implementation': sys.implementation.name, 'cache_tag': sys.implementation.cache_tag,
        'version_info': list(sys.version_info), 'optimization': sys.flags.optimize,
        'libmpdec_version': decimal.__libmpdec_version__, 'executable': sys.executable,
    }
