"""Historical serialization, generated isolation, and unchanged assurance gates."""
import ast
import inspect
import subprocess
import sys
import types
from decimal import Decimal, localcontext
from copy import deepcopy

import pytest

from src.application.models import CompletedRunArtifacts
from src.assurance.independent_financial_review import IndependentFinancialReviewer
from src.assurance.proof_policy import ProofPolicy
from src.assurance.release_gate import ReleaseGate
from src.capabilities.financial.growth import RevenueGrowthCapability, calculate_revenue_growth, _growth_observer
from src.domain.capability import CapabilityContext, ScopedCapabilityRegistration
from src.domain.enums import CapabilityBackend, CapabilityScope, CapabilityLifecycle
from src.domain.financial_validation import method_metadata_view
from src.domain.node_binding import task_fingerprint, graph_semantics, digest
from src.domain.task import Task
from tests.wp04.test_method_binding import setup, run_node, check, records, ROOT, no_network

BASELINE = '7b66941ce5449467e975b40c6ed8bdd665adb446'


def baseline_source(path):
    return subprocess.run(['git', 'show', BASELINE + ':' + path], cwd=ROOT,
                          check=True, capture_output=True, text=True).stdout


async def test_F03_legacy_hash_roundtrip(tmp_path):
    service, aggregate = await setup(tmp_path, enabled=False)
    task = aggregate.runtime.actual_graph.tasks[0]
    raw = task.model_dump_json()
    assert 'wp04_method_requirement' not in raw
    assert Task.model_validate_json(raw).model_dump_json() == raw
    assert 'wp04_method_observations' not in CompletedRunArtifacts().model_dump()
    # Execute only the accepted baseline's serialization module as a read-only oracle.
    module = types.ModuleType('_wp04_baseline_binding')
    sys.modules[module.__name__] = module
    try:
        exec(compile(baseline_source('src/domain/node_binding.py'), '<accepted-baseline>', 'exec'), vars(module))
        assert module.task_fingerprint(task) == task_fingerprint(task)
        assert module.graph_semantics(aggregate.runtime.actual_graph) == graph_semantics(aggregate.runtime.actual_graph)
        fresh, _ = await run_node(service, aggregate)
        for calc in fresh.artifacts.calculations:
            from src.domain.node_binding import calculation_core
            assert module.calculation_core(calc) == calculation_core(calc)
            assert method_metadata_view(calc) == {'status':'LEGACY_UNKNOWN'}
    finally: sys.modules.pop(module.__name__, None)


async def test_F04_generated_shadow_cannot_become_native(tmp_path):
    from src.capabilities.generated.scoped_registry import ScopedCapabilityRegistry
    service, aggregate = await setup(tmp_path)
    native = check(service)[0]
    class Generated:
        definition = native.definition.model_copy(update={'backend': CapabilityBackend.GENERATED})
        async def execute(self, *args, **kwargs): raise AssertionError('generated fallback forbidden')
    scoped = ScopedCapabilityRegistry(service.capability_registry)
    registration = ScopedCapabilityRegistration(registration_id='REG', generated_capability_ref='GEN',
        capability_id='revenue_growth', capability_version='1.1.0', scope=CapabilityScope.TASK,
        run_id=aggregate.run.run_id, task_id=aggregate.runtime.actual_graph.tasks[0].task_id,
        approved_by='fixture-authorization', lifecycle=CapabilityLifecycle.TASK_APPROVED)
    await scoped.register(registration, Generated())
    assert await scoped.lookup('revenue_growth', version='1.1.0', run_id=registration.run_id, task_id=registration.task_id) is not native
    assert await scoped.lookup('revenue_growth', version='1.1.0', run_id='FOREIGN', task_id='FOREIGN') is native
    fresh, _ = await run_node(service, aggregate)
    assert not fresh.artifacts.generated_capability_refs
    assert check(service)[0] is native
    assert service.capability_registry.get('revenue_growth', '1.1.0') is native


async def test_F05_original_assurance_and_companion(tmp_path):
    service, aggregate = await setup(tmp_path)
    fresh, _ = await run_node(service, aggregate)
    calculations = fresh.artifacts.calculations
    assert {c.capability_id for c in calculations} == {'revenue_growth', 'ebitda_margin'}
    assert len(fresh.artifacts.corrections) == 1
    margin = next(c for c in calculations if c.capability_id == 'ebitda_margin')
    assert 'wp04_method_binding' not in margin.parameters
    requirements = {c.calculation_id: ProofPolicy().requirement_for(c) for c in calculations}
    review = IndependentFinancialReviewer().review(review_id='REVIEW', run_id=fresh.run.run_id,
        run_as_of=fresh.run.as_of, evidence=fresh.artifacts.evidence, calculations=calculations,
        metrics=(), claims=(), judgments=(), proof_requirements=requirements,
        requirement_context=service._review_requirement_context(fresh, False))
    assert next(c for c in review.checks if c.code == 'FIN_WP04_EXACT_METHOD_LINEAGE').status.value == 'PASS'
    assert review.status.value == 'BLOCK'  # growth success cannot waive material/claim closure
    decision = ReleaseGate().evaluate(review=review, proof_requirements=requirements, proofs={},
        calculations={c.calculation_id:c for c in calculations}, evidence=fresh.artifacts.evidence,
        metrics=(), claims=(), judgments=(), run_as_of=fresh.run.as_of,
        requirement_context=service._review_requirement_context(fresh, False))
    assert not decision.allowed
    forged_context = deepcopy(service._review_requirement_context(fresh, False))
    forged_context['wp04_method_context']['entries'][0]['current_result_id'] = 'changed'
    changed = ReleaseGate().evaluate(review=review, proof_requirements=requirements, proofs={},
        calculations={c.calculation_id:c for c in calculations}, evidence=fresh.artifacts.evidence,
        metrics=(), claims=(), judgments=(), run_as_of=fresh.run.as_of, requirement_context=forged_context)
    assert 'REVIEW_REQUIREMENT_CONTEXT_MISMATCH' in changed.reason_codes
    assert 'REVIEW_INPUT_SNAPSHOT_MISMATCH' in changed.reason_codes


async def test_DF04_legacy_observer_inactive(tmp_path):
    from src.capabilities.financial.common import NonPositivePriorRevenueError
    from src.domain.financial_validation import REVENUE_GROWTH_VALIDATION_REASON
    tree = ast.parse(baseline_source('src/capabilities/financial/growth.py'))
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'calculate_revenue_growth')
    namespace = {'Decimal': Decimal, 'localcontext': localcontext,
                 'NonPositivePriorRevenueError': NonPositivePriorRevenueError,
                 'REVENUE_GROWTH_VALIDATION_REASON': REVENUE_GROWTH_VALIDATION_REASON}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), '<accepted-helper>', 'exec'), namespace)
    for precision in (3, 28, 45):
        with localcontext() as ambient:
            ambient.prec = precision; ambient.rounding = 'ROUND_UP'
            assert calculate_revenue_growth(Decimal(3), Decimal(4)) == namespace['calculate_revenue_growth'](Decimal(3),Decimal(4))
    assert list(inspect.signature(calculate_revenue_growth).parameters) == ['prior_revenue','current_revenue']
    assert list(inspect.signature(RevenueGrowthCapability.execute).parameters) == ['self','inputs','context']
    p,c = records(tmp_path)[:2]
    record = await RevenueGrowthCapability().execute({'prior':p,'current':c,'calculation_id':'LEGACY'},
        CapabilityContext(run_id=p.run_id,task_id='legacy',accepted_evidence_ids=[p.evidence_id,c.evidence_id]))
    assert set(record.parameters) == {'formula_expression','semantic_precondition','financial_validation_reason'}
    assert _growth_observer.get() is None
