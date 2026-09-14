"""Real local method lineage and actual inner Decimal evidence, DF01–DF06."""
import asyncio
from copy import deepcopy
from decimal import Decimal, getcontext, localcontext

import pytest

from src.application.execution import IntegratedTaskExecutor
from src.application.repository import node_invocation
from src.application.research_context import ContextProjection
from src.assurance.independent_financial_review import review_wp04_bindings, IndependentFinancialReviewer
from src.capabilities.financial.growth import (
    RevenueGrowthCapability, calculate_revenue_growth, capture_revenue_growth_decimal_observation,
    _growth_observer,
)
from src.domain.capability import CapabilityContext
from src.domain.financial_validation import MethodDenied, wp04_decimal_context, validate_decimal_observation
from src.domain.node_binding import BindingDenied
from src.runtime.scheduler import TaskExecutionContext
from tests.wp04.test_method_binding import setup, arm, run_node, records, no_network


def review(service, aggregate):
    review_wp04_bindings(context=service._wp04_context(aggregate), calculations=aggregate.artifacts.calculations,
                         evidence=aggregate.artifacts.evidence, run_as_of=aggregate.run.as_of)


async def test_F01_service_R_context_review(tmp_path):
    service, aggregate = await setup(tmp_path, extra_tasks=True)
    fresh, result = await run_node(service, aggregate)
    review(service, fresh)
    assert result.result_binding_id == fresh.node_binding.current_results[fresh.runtime.actual_graph.tasks[0].task_id]
    calc = fresh.artifacts.calculations[0]
    metadata = calc.parameters['wp04_method_binding']
    b = fresh.node_binding.resolved_inputs[metadata['B_ref']]
    assert b.payload_snapshot['wp04']['expected_capture_count'] == 1
    assert 'resulting_decimal_flags' not in b.payload_snapshot['wp04']
    assert any(o.numeric_outcome == 'SUCCEEDED' and o.calculation_ref == calc.calculation_id
               for o in fresh.artifacts.wp04_method_observations.values())
    service.valuation_context_enabled = True
    task = fresh.runtime.actual_graph.tasks[1]
    executor = IntegratedTaskExecutor(service, fresh)
    owner = next(iter(fresh.node_binding.attempts.values())).admission.owner
    admission = await service.repository.reserve_node(owner, task, executor.admission_requirements(task))
    await service.repository.dispatch_node(admission)
    fresh = await service.repository.enter_node_execution(admission)
    executor = IntegratedTaskExecutor(service, fresh)
    token = node_invocation.set(admission)
    try:
        projection = ContextProjection(executor, task, admission, 'fixture-model', 'fixture-route')
        package = await projection.build()
    finally: node_invocation.reset(token)
    projected = next(section['calculation'] for section in package.sections
                     if section.get('source_id') == calc.calculation_id)
    assert projected['parameters']['wp04_method_binding'] == metadata


@pytest.mark.parametrize('mutation', ['strip', 'formula', 'flags', 'current', 'B', 'no_context'])
async def test_F02_forged_correct_value_rejected(tmp_path, mutation):
    service, aggregate = await setup(tmp_path)
    fresh, _ = await run_node(service, aggregate)
    review(service, fresh)
    context = service._wp04_context(fresh)
    calc = fresh.artifacts.calculations[0]
    if mutation == 'strip': del calc.parameters['wp04_method_binding']
    elif mutation == 'formula': calc.parameters['wp04_method_binding']['formula_version'] = '9.0.0'
    elif mutation == 'flags': calc.parameters['wp04_method_binding']['resulting_decimal_flags']['Inexact'] = False
    elif mutation == 'current': context['entries'][0]['current_result_id'] = 'changed'
    elif mutation == 'B': next(b for b in context['entries'][0]['B'] if 'wp04' in b['payload_snapshot'])['payload_snapshot']['wp04']['expected_capture_count'] = 0
    else: context = None
    with pytest.raises((ValueError, KeyError, StopIteration)):
        review_wp04_bindings(context=context, calculations=fresh.artifacts.calculations,
                             evidence=fresh.artifacts.evidence, run_as_of=fresh.run.as_of)


@pytest.mark.parametrize('prior,current,inexact,expected', [('3','4',True,'0.3333333333333333333333333333'),
                                                         ('2','3',False,'0.5')], ids=['DF01','DF02'])
async def test_DF01_DF02_actual_inner_context(tmp_path, prior, current, inexact, expected):
    service, aggregate = await setup(tmp_path, prior=prior, current=current)
    with localcontext() as outer:
        outer.clear_flags()
        isolated, isolated_receipt = await direct_capture(aggregate.artifacts.evidence, 'ISO', 'ISO:t', 'ISO:c')
        assert not any(outer.flags.values())
    fresh, _ = await run_node(service, aggregate)
    calc = fresh.artifacts.calculations[0]
    assert isolated.output_value == calc.output_value
    assert isolated_receipt == calc.parameters['wp04_method_binding']['decimal_flags_observation']
    receipt = calc.parameters['wp04_method_binding']['decimal_flags_observation']
    flags = validate_decimal_observation(receipt)
    assert receipt['capture_count'] == 1
    assert flags['Inexact'] is flags['Rounded'] is inexact
    assert sum(flags.values()) == (2 if inexact else 0)
    assert calc.output_value == Decimal(expected)
    review(service, fresh)


@pytest.mark.parametrize('failure', ['cancel', 'timeout', 'arithmetic'])
async def test_DF03_error_restores_ambient(tmp_path, monkeypatch, failure):
    service, aggregate = await setup(tmp_path,
        prior='1e-999999' if failure == 'arithmetic' else '3',
        current='1e999999' if failure == 'arithmetic' else '4')
    original = service.repository.check_invocation
    calls = 0
    async def interrupt(admission):
        nonlocal calls
        calls += 1
        if calls == 2:
            if failure == 'cancel': raise asyncio.CancelledError()
            if failure == 'timeout': raise TimeoutError()
        return await original(admission)
    monkeypatch.setattr(service.repository, 'check_invocation', interrupt)
    with localcontext() as ambient:
        ambient.prec = 7; ambient.rounding = 'ROUND_DOWN'; ambient.clear_flags()
        before = str(ambient), dict(ambient.flags), dict(ambient.traps)
        with pytest.raises(BaseException): await run_node(service, aggregate)
        assert (str(ambient), dict(ambient.flags), dict(ambient.traps)) == before
    assert _growth_observer.get() is None
    assert not service.repository._calculations
    fresh = await service.repository.get_run_fresh(aggregate.run.run_id)
    finish = list(fresh.artifacts.wp04_method_observations.values())[-1]
    assert finish.numeric_outcome == {'cancel':'CANCELLED','timeout':'TIMED_OUT','arithmetic':'FAILED'}[failure]
    assert not finish.diagnostic_code.startswith('DECIMAL_FLAGS_OBSERVATION')


async def direct_capture(evidence, run, task, calculation):
    p, c = [e.model_copy(update={'run_id': run}) for e in evidence[:2]]
    inputs = {'prior': p, 'current': c, 'calculation_id': calculation}
    context = CapabilityContext(run_id=run, task_id=task, accepted_evidence_ids=[p.evidence_id,c.evidence_id])
    identity = (run, task, calculation, p.evidence_id,c.evidence_id,str(p.normalized_value),str(c.normalized_value),'B','reservation')
    with localcontext(wp04_decimal_context()):
        with capture_revenue_growth_decimal_observation(identity) as collector:
            await asyncio.sleep(0)
            result = await RevenueGrowthCapability().execute(inputs, context)
            await asyncio.sleep(0)
            receipt = collector.seal()
    return result, receipt


async def test_DF05_concurrent_and_inherited_isolation(tmp_path):
    one = records(tmp_path, prior='3', current='4')
    other_root = tmp_path / 'other'; other_root.mkdir()
    two = records(other_root, prior='2', current='3')
    a, b = await asyncio.gather(direct_capture(one,'A','A:t','A:c'), direct_capture(two,'B','B:t','B:c'))
    assert a[1]['flags']['Inexact'] is True and b[1]['flags']['Inexact'] is False
    assert a[1]['capture_count'] == b[1]['capture_count'] == 1
    identity = ('A','A:t','A:c','E0','E1','3','4','B','reservation')
    gate = asyncio.Event()
    with capture_revenue_growth_decimal_observation(identity) as parent:
        async def inherited():
            with pytest.raises(MethodDenied): calculate_revenue_growth(Decimal(3),Decimal(4))
            await gate.wait()
            with pytest.raises(MethodDenied): calculate_revenue_growth(Decimal(3),Decimal(4))
        child = asyncio.create_task(inherited())
        await asyncio.sleep(0)
        assert parent.count == 0 and parent.invalid is False
    gate.set(); await child
    assert _growth_observer.get() is None
    with capture_revenue_growth_decimal_observation(identity) as parent:
        with pytest.raises(MethodDenied):
            with capture_revenue_growth_decimal_observation(identity): pass
        with pytest.raises(MethodDenied): parent.seal()
    with capture_revenue_growth_decimal_observation(identity) as parent:
        with pytest.raises(MethodDenied): calculate_revenue_growth(Decimal(3),Decimal(4))
        with pytest.raises(MethodDenied): parent.seal()


@pytest.mark.parametrize('mode,code', [('zero','MISSING'),('duplicate','AMBIGUOUS'),('malformed','ERROR'),('invalid','ERROR')])
async def test_DF06_capture_failure_prevents_commit(tmp_path, monkeypatch, mode, code):
    service, aggregate = await setup(tmp_path)
    original = service.repository.check_invocation
    calls = 0
    async def corrupt(admission):
        nonlocal calls
        calls += 1
        if calls == 2:
            capture = _growth_observer.get()
            assert capture.count == 1
            if mode == 'zero': capture.count = 0
            elif mode == 'duplicate': capture.count = 2
            elif mode == 'malformed': capture.flags = {'Inexact': 'true'}
            else: capture.invalid = True
        return await original(admission)
    monkeypatch.setattr(service.repository, 'check_invocation', corrupt)
    with pytest.raises(MethodDenied, match='DECIMAL_FLAGS_OBSERVATION_' + code):
        await run_node(service, aggregate)
    fresh = await service.repository.get_run_fresh(aggregate.run.run_id)
    assert not service.repository._calculations and not fresh.node_binding.current_results
    last = list(fresh.artifacts.wp04_method_observations.values())[-1]
    assert last.support_status == 'SUPPORTED' and last.numeric_outcome == 'FAILED'
    assert last.dispatch_count == 1


async def test_DF06_reviewer_oracle_rejects_coherent_forged_flags(tmp_path):
    from src.domain.node_binding import ResultBinding, OutputRecord, calculation_core, digest, value_identity, canonical_value
    service, aggregate = await setup(tmp_path)
    fresh, _ = await run_node(service, aggregate)
    context = service._wp04_context(fresh)
    calc = fresh.artifacts.calculations[0]
    metadata = calc.parameters['wp04_method_binding']
    for flags in (metadata['resulting_decimal_flags'], metadata['decimal_flags_observation']['flags']):
        flags['Inexact'] = flags['Rounded'] = False
    entry = context['entries'][0]
    result = ResultBinding.model_validate(entry['R'])
    payload = calculation_core(calc)
    outputs = [record.model_copy(update={'payload_snapshot':payload,
               'content_digest':digest(payload, record.record_schema)})
               if record.record_id == calc.calculation_id else record for record in result.output_records]
    result = result.model_copy(update={'output_records':tuple(outputs)})
    identity = value_identity(result, 'result_id', 'result_digest')
    result = result.model_copy(update={'result_id':identity,'result_digest':identity})
    entry['R'] = canonical_value(result); entry['current_result_id'] = identity
    with pytest.raises(ValueError, match='WP04_INDEPENDENT_NUMERIC_OR_FLAGS_MISMATCH'):
        review_wp04_bindings(context=context, calculations=fresh.artifacts.calculations,
                             evidence=fresh.artifacts.evidence, run_as_of=fresh.run.as_of)


async def test_DF06_stale_owner_after_capture(tmp_path, monkeypatch):
    service, aggregate = await setup(tmp_path)
    original = service.repository.check_invocation
    calls = 0
    async def stale(admission):
        nonlocal calls
        calls += 1
        if calls == 2:
            assert _growth_observer.get().count == 1
            service.repository._runs[admission.run_id].node_binding.lifecycle = 'CLOSED'
        return await original(admission)
    monkeypatch.setattr(service.repository, 'check_invocation', stale)
    with pytest.raises(BindingDenied): await run_node(service, aggregate)
    assert not service.repository._calculations
    fresh = await service.repository.get_run_fresh(aggregate.run.run_id)
    assert not fresh.node_binding.current_results
    assert all(o.phase == 'PREPARED' for o in fresh.artifacts.wp04_method_observations.values())


async def test_DF06_two_actual_helper_captures_are_ambiguous(tmp_path):
    p, c = records(tmp_path)[:2]
    inputs = {'prior':p,'current':c,'calculation_id':'C'}
    context = CapabilityContext(run_id=p.run_id, task_id='T', accepted_evidence_ids=['E0','E1'])
    identity = (p.run_id,'T','C','E0','E1','3','4','B','reservation')
    with capture_revenue_growth_decimal_observation(identity) as collector:
        collector.arm(context, inputs)
        calculate_revenue_growth(Decimal(3), Decimal(4))
        first = dict(collector.flags)
        calculate_revenue_growth(Decimal(3), Decimal(4))
        assert collector.count == 2 and collector.flags == first
        with pytest.raises(MethodDenied, match='DECIMAL_FLAGS_OBSERVATION_AMBIGUOUS'): collector.seal()


@pytest.mark.parametrize('safe_store_fails', [False, True])
async def test_R1B03_stale_after_actual_capture_preserves_primary_fencing_code(tmp_path, monkeypatch, safe_store_fails):
    import json
    service, aggregate = await setup(tmp_path)
    executor, task, admission = await arm(service, aggregate)
    calls = {'capture': 0, 'observation_rejected': 0, 'retention': 0}
    original_check = service.repository.check_invocation
    original_observe = service.repository.record_method_observation
    original_retain = service.wp04_diagnostic_store.retain_method_diagnostic
    async def after_capture(a):
        collector = _growth_observer.get()
        if collector is not None and collector.count == 1:
            assert collector.flags['Inexact'] is collector.flags['Rounded'] is True
            calls['capture'] += 1
            service.repository._runs[a.run_id].node_binding.owner_generation += 1
        return await original_check(a)
    async def observe(*args, **kwargs):
        try: return await original_observe(*args, **kwargs)
        except BindingDenied as e:
            assert e.code == 'STALE_WRITE_REJECTED'
            calls['observation_rejected'] += 1
            raise
    def retain(**kwargs):
        calls['retention'] += 1
        assert kwargs['diagnostic_code'] == 'STALE_WRITE_REJECTED'
        assert kwargs['secondary_diagnostic_code'] == 'PERSISTENCE_UNAVAILABLE'
        if safe_store_fails: raise OSError('bounded retention unavailable')
        return original_retain(**kwargs)
    async def no_reacquire(*args, **kwargs):
        raise AssertionError('owner reacquisition/retry is forbidden')
    monkeypatch.setattr(service.repository, 'check_invocation', after_capture)
    monkeypatch.setattr(service.repository, 'record_method_observation', observe)
    monkeypatch.setattr(service.wp04_diagnostic_store, 'retain_method_diagnostic', retain)
    monkeypatch.setattr(service.repository, 'claim_execution', no_reacquire)
    with pytest.raises(BindingDenied) as failure:
        await executor.execute(task, TaskExecutionContext(task.run_id, 1, admission))
    assert failure.value.code == 'STALE_WRITE_REJECTED'
    assert calls == {'capture': 1, 'observation_rejected': 1, 'retention': 1}
    fresh = await service.repository.get_run_fresh(task.run_id)
    assert not service.repository._calculations and not fresh.node_binding.current_results
    assert all(o.phase == 'PREPARED' for o in fresh.artifacts.wp04_method_observations.values())
    payloads = [json.loads(p.read_bytes()) for p in service.wp04_diagnostic_store._blob_root.iterdir()]
    retained = [p for p in payloads if p['diagnostic_code'] == 'STALE_WRITE_REJECTED']
    assert len(retained) == (0 if safe_store_fails else 1)
    if retained:
        assert retained[0]['secondary_diagnostic_code'] == 'PERSISTENCE_UNAVAILABLE'
        assert retained[0]['authority_status'] == 'UNCOMMITTED'
    assert _growth_observer.get() is None
