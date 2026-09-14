"""C2/C3 semantics, precedence, and append-only failure ownership."""
import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, getcontext, localcontext

import pytest

from src.application.execution import IntegratedTaskExecutor, wp04_bind_inputs, wp04_candidate_snapshot
from src.application.repository import node_invocation
from src.application.closure_policy import classify_execution_closure
from src.domain.financial_validation import MethodDenied, MethodObservation
from src.domain.node_binding import BindingDenied, canonical_value, digest, task_fingerprint
from src.runtime.scheduler import TaskExecutionContext
from tests.wp04.test_method_binding import setup, arm, run_node, no_network


def candidates(aggregate):
    return wp04_candidate_snapshot(aggregate, aggregate.runtime.actual_graph.tasks[0])


def bind(aggregate, values=None):
    task = aggregate.runtime.actual_graph.tasks[0]
    return wp04_bind_inputs(task.wp04_method_requirement,
                           values if values is not None else candidates(aggregate), aggregate.run.as_of)


def mutate(values, **updates):
    values = deepcopy(values)
    values[0]['snapshot'].update(updates)
    values[0]['content_digest'] = digest(values[0]['snapshot'], 'evidence-record/v1')
    return values


async def test_S01_exact_equal_scale(tmp_path):
    _, aggregate = await setup(tmp_path, prior='2', current='3')
    p, c, binding = bind(aggregate)
    assert binding['input_evidence_ids'] == ['E0', 'E1']
    assert all(w['original_scale'] == w['normalized_scale'] == 1 for w in binding['raw_witnesses'])
    assert Decimal(c.normalized_value) / Decimal(p.normalized_value) - 1 == Decimal('0.5')


@pytest.mark.parametrize('case', ['different_scale', 'unknown_unit', 'unknown_shape', 'ambiguous'])
async def test_S02_raw_scale_rejects(tmp_path, case):
    import json, hashlib
    _, aggregate = await setup(tmp_path)
    values = candidates(aggregate)
    path = tmp_path / 'raw.json'
    raw = json.loads(path.read_bytes())
    if case == 'different_scale':
        raw['records'][0].update(unit='USD_THOUSAND', value='0.003')
    elif case == 'unknown_unit': raw['records'][0]['unit'] = 'unknown'
    elif case == 'unknown_shape': raw = {'data': raw['records']}
    else: raw['records'].append(deepcopy(raw['records'][0]))
    encoded = json.dumps(raw).encode()
    path.write_bytes(encoded)
    for v in values:
        v['snapshot']['snapshot_hash'] = 'sha256:' + hashlib.sha256(encoded).hexdigest()
        v['content_digest'] = digest(v['snapshot'], 'evidence-record/v1')
    with pytest.raises(MethodDenied) as exc: bind(aggregate, values)
    assert exc.value.support == 'UNSUPPORTED'


@pytest.mark.parametrize('case,expected', [('record', 'MISSING_INPUT'), ('value', 'MISSING_INPUT'),
    ('actuality', 'UNSUPPORTED'), ('bool', 'UNSUPPORTED'), ('nonfinite', 'UNSUPPORTED')])
async def test_S03_missing_vs_invalid(tmp_path, case, expected):
    _, aggregate = await setup(tmp_path)
    values = candidates(aggregate)
    if case == 'record': values = values[1:]
    else:
        changes = {'value': {'normalized_value': None}, 'actuality': {'actuality': 'UNKNOWN', 'provider': 'test'},
                   'bool': {'normalized_value': True}, 'nonfinite': {'normalized_value': 'NaN'}}
        values = mutate(values, **changes[case])
    with pytest.raises(MethodDenied) as exc: bind(aggregate, values)
    assert exc.value.support == expected


@pytest.mark.parametrize('case', ['nonadjacent', 'foreign', 'multiple', 'currency', 'series', 'future'])
async def test_S04_comparable_pair(tmp_path, case):
    _, aggregate = await setup(tmp_path)
    values = candidates(aggregate)
    changes = {'nonadjacent': {'period': 'FY2020'}, 'foreign': {'object_id': 'FOREIGN'},
               'currency': {'currency': 'usd'}, 'series': {'statement_series': 'OTHER'},
               'future': {'as_of': '2027-01-01'}}
    if case == 'multiple':
        v = deepcopy(values[0]); v['evidence_id'] = 'E99'; v['snapshot']['evidence_id'] = 'E99'
        v['content_digest'] = digest(v['snapshot'], 'evidence-record/v1'); values.append(v)
    else: values = mutate(values, **changes[case])
    with pytest.raises(MethodDenied) as exc: bind(aggregate, values)
    assert exc.value.support == 'UNSUPPORTED'


@pytest.mark.parametrize('prior', ['0', '-3'])
async def test_S05_not_applicable_required(tmp_path, prior):
    service, aggregate = await setup(tmp_path, prior=prior)
    with pytest.raises(MethodDenied, match='NOT_APPLICABLE_PRECONDITION'): await run_node(service, aggregate)
    fresh = await service.repository.get_run_fresh(aggregate.run.run_id)
    assert not classify_execution_closure(fresh).reviewable
    obs = list(fresh.artifacts.wp04_method_observations.values())[-1]
    assert obs.support_status == 'NOT_APPLICABLE' and obs.numeric_outcome == 'NONE'


async def test_S05_current_negative_valid(tmp_path):
    service, aggregate = await setup(tmp_path, current='-4')
    fresh, _ = await run_node(service, aggregate)
    assert fresh.artifacts.calculations[0].output_value < -1


async def test_S06_precedence(tmp_path):
    service, aggregate = await setup(tmp_path, prior='0')
    service.capability_registry._capabilities.pop(('revenue_growth', '1.1.0'))
    with pytest.raises(MethodDenied) as exc: await run_node(service, aggregate)
    assert exc.value.support == 'MISSING_METHOD'
    assert not service.repository._calculations


async def test_S07_explicit_context(tmp_path):
    service, aggregate = await setup(tmp_path)
    before = getcontext().copy()
    with localcontext() as ambient:
        ambient.prec = 2; ambient.rounding = 'ROUND_UP'; ambient.Emin = -5; ambient.Emax = 5
        ambient.capitals = 0; ambient.clamp = 1
        for signal in ambient.traps: ambient.traps[signal] = False
        for signal in ambient.flags: ambient.flags[signal] = True
        saved = str(ambient), dict(ambient.flags), dict(ambient.traps)
        fresh, _ = await run_node(service, aggregate)
        assert fresh.artifacts.calculations[0].output_value == Decimal('0.3333333333333333333333333333')
        assert (str(ambient), dict(ambient.flags), dict(ambient.traps)) == saved
    assert str(getcontext()) == str(before)


async def test_D01_before_A_denial(tmp_path):
    service, aggregate = await setup(tmp_path)
    repo = service.repository
    owner = await repo.claim_execution(aggregate.run.run_id)
    await repo.begin_scheduler(owner)
    current = await repo.get_run_fresh(owner.run_id)
    task = current.runtime.actual_graph.tasks[0]
    reqs = IntegratedTaskExecutor(service, current).admission_requirements(task)
    reqs['wp04_candidates'] = []
    with pytest.raises(BindingDenied): await repo.reserve_node(owner, task, reqs)
    fresh = await repo.get_run_fresh(owner.run_id)
    obs = list(fresh.artifacts.wp04_method_observations.values())
    assert len(obs) == 1 and obs[0].phase == 'DENIED_BEFORE_A'
    assert not fresh.node_binding.attempts and not repo._calculations


async def prepared(tmp_path):
    service, aggregate = await setup(tmp_path)
    executor, task, admission = await arm(service, aggregate)
    fresh = await service.repository.enter_node_execution(admission)
    executor = IntegratedTaskExecutor(service, fresh)
    token = node_invocation.set(admission)
    try: await executor._prepare_wp04(task)
    finally: node_invocation.reset(token)
    fresh = await service.repository.get_run_fresh(task.run_id)
    return service, task, admission, executor, list(fresh.artifacts.wp04_method_observations.values())[0]


async def test_D02_immutable_observations(tmp_path):
    service, task, admission, executor, observation = await prepared(tmp_path)
    repo = service.repository
    await repo.record_method_observation(admission.owner, task.task_id, observation, admission)
    conflict = observation.model_copy(update={'diagnostic_code': 'CHANGED'}).identified()
    with pytest.raises(BindingDenied):
        await repo.record_method_observation(admission.owner, task.task_id, conflict, admission)
    fresh = await repo.get_run_fresh(task.run_id)
    fresh.artifacts.wp04_method_observations = {}
    with pytest.raises(BindingDenied): await repo.save_run(fresh)
    original = await repo.get_run_fresh(task.run_id)
    assert len(original.artifacts.wp04_method_observations) == 1


async def test_D03_crash_prepared_and_no_reentry(tmp_path):
    service, task, admission, executor, observation = await prepared(tmp_path)
    with pytest.raises(BindingDenied): await service.repository.enter_node_execution(admission)
    with pytest.raises(BindingDenied): await service.repository.reserve_node(admission.owner, task, executor.admission_requirements(task))
    current = await service.repository.get_run_fresh(task.run_id)
    assert list(current.artifacts.wp04_method_observations.values()) == [observation]
    assert observation.numeric_outcome == 'NONE' and observation.phase == 'PREPARED'
    assert not current.node_binding.current_results and not service.repository._calculations


@pytest.mark.parametrize('diagnostic_also_fails', [False, True])
async def test_D04_persistence_fail_closed(tmp_path, monkeypatch, diagnostic_also_fails):
    service, aggregate = await setup(tmp_path)
    async def unavailable(*args, **kwargs): raise OSError('offline fixture')
    monkeypatch.setattr(service.repository, 'record_method_observation', unavailable)
    if diagnostic_also_fails:
        def no_store(**kwargs): raise OSError('offline diagnostic')
        monkeypatch.setattr(service.wp04_diagnostic_store, 'retain_method_diagnostic', no_store)
    with pytest.raises(MethodDenied, match='PERSISTENCE_UNAVAILABLE'): await run_node(service, aggregate)
    assert not service.repository._calculations
    if not diagnostic_also_fails:
        blobs = list(service.wp04_diagnostic_store._blob_root.iterdir())
        import json
        payloads = [json.loads(p.read_bytes()) for p in blobs]
        assert any(p['diagnostic_code'] == 'PERSISTENCE_UNAVAILABLE' and p['authority_status'] == 'UNCOMMITTED' for p in payloads)


async def test_D05_requirement_projection(tmp_path):
    service, aggregate = await setup(tmp_path)
    task = aggregate.runtime.actual_graph.tasks[0]
    for state in ('REQUIRED', 'SUPPORTING', 'NOT_REQUESTED'):
        req = task.wp04_method_requirement.model_copy(update={'requirement_state': state})
        task.wp04_method_requirement = req
        closure = classify_execution_closure(aggregate)
        bucket = closure.required_outputs if state == 'REQUIRED' else closure.supporting_outputs
        assert (req.requirement_id in bucket.missing) is (state != 'NOT_REQUESTED')
        # Other original Scheme/task gates continue to block every incomplete run.
        assert not closure.reviewable


async def test_D01_service_preflight_denial_is_committed(tmp_path, monkeypatch):
    service, aggregate = await setup(tmp_path)
    def denied(self, task): raise BindingDenied('METHOD_TEST_PREFLIGHT_DENIED')
    monkeypatch.setattr(IntegratedTaskExecutor, 'admission_requirements', denied)
    with pytest.raises(BindingDenied, match='METHOD_TEST_PREFLIGHT_DENIED'):
        await service.execute_run(aggregate.run.run_id)
    fresh = await service.repository.get_run_fresh(aggregate.run.run_id)
    observations = list(fresh.artifacts.wp04_method_observations.values())
    assert len(observations) == 1 and observations[0].phase == 'DENIED_BEFORE_A'
    assert fresh.run.status.value == 'FAILED'
    assert not fresh.artifacts.calculations and not fresh.node_binding.attempts


async def test_D02_other_task_merge_preserves_observations(tmp_path):
    service, aggregate = await setup(tmp_path, extra_tasks=True)
    fresh, _ = await run_node(service, aggregate)
    original = deepcopy(fresh.artifacts.wp04_method_observations)
    task = fresh.runtime.actual_graph.tasks[1]
    executor = IntegratedTaskExecutor(service, fresh)
    owner = next(iter(fresh.node_binding.attempts.values())).admission.owner
    admission = await service.repository.reserve_node(owner, task, executor.admission_requirements(task))
    await service.repository.dispatch_node(admission)
    await executor.execute(task, TaskExecutionContext(task.run_id, 1, admission))
    after = await service.repository.get_run_fresh(task.run_id)
    assert after.artifacts.wp04_method_observations == original
    assert len(after.node_binding.current_results) == 2


async def test_D04_calculation_store_failure(tmp_path, monkeypatch):
    service, aggregate = await setup(tmp_path)
    async def failed(calculation): raise OSError('fixture calculation persistence unavailable')
    monkeypatch.setattr(service.repository, 'save_calculation', failed)
    with pytest.raises(MethodDenied, match='PERSISTENCE_UNAVAILABLE'): await run_node(service, aggregate)
    fresh = await service.repository.get_run_fresh(aggregate.run.run_id)
    finish = list(fresh.artifacts.wp04_method_observations.values())[-1]
    assert finish.numeric_outcome == 'RESULT_UNKNOWN' and finish.calculation_ref is None
    assert not service.repository._calculations and not fresh.node_binding.current_results


async def _r1b02_bounded_negative(tmp_path, monkeypatch, changes, retained_original=False):
    import hashlib, json
    from datetime import date
    from pathlib import Path
    from src.domain.enums import FinancialActuality
    from src.domain.evidence import EvidenceRecord
    service, aggregate = await setup(tmp_path)
    stored = service.repository._runs[aggregate.run.run_id]
    originals = stored.artifacts.evidence
    if retained_original:
        # Exact Acceptor witness shape, from the unchanged checked-in fixture.
        path = Path('tests/fixtures/nvda_financials.json').resolve()
        raw = path.read_bytes()
        rows = json.loads(raw, parse_float=Decimal)['records'][:2]
        for i, row in enumerate(rows):
            originals[i] = originals[i].model_copy(update={
                'period': row['period'], 'as_of': date.fromisoformat(row['as_of']),
                'normalized_value': str(row['value'] * Decimal(10**9)),
                'raw_artifact_ref': str(path), 'snapshot_hash': 'sha256:' + hashlib.sha256(raw).hexdigest()})
    # Fixture installation occurs before A. model_copy intentionally preserves the
    # explicit missing/unknown bytes; no post-init can repair the authorized snapshot.
    for i in (0, 1):
        originals[i] = originals[i].model_copy(update=changes)
    fresh = await service.repository.get_run_fresh(aggregate.run.run_id)
    values = candidates(fresh)
    assert all(v['content_digest'] == digest(v['snapshot'], 'evidence-record/v1') for v in values)
    calls = []
    original_dispatch = IntegratedTaskExecutor._execute_wp04
    async def dispatch(self, *args):
        calls.append(1)
        return await original_dispatch(self, *args)
    monkeypatch.setattr(IntegratedTaskExecutor, '_execute_wp04', dispatch)
    with pytest.raises(MethodDenied) as failure:
        await run_node(service, fresh)
    assert failure.value.code == 'SEMANTIC_INPUT_MISMATCH'
    assert not calls and not service.repository._calculations
    fresh = await service.repository.get_run_fresh(aggregate.run.run_id)
    assert not fresh.node_binding.current_results and not fresh.node_binding.resolved_inputs
    observations = list(fresh.artifacts.wp04_method_observations.values())
    assert observations and all(o.phase == 'DENIED' and o.dispatch_count == 0 for o in observations)
    assert not any(o.phase == 'PREPARED' or o.numeric_outcome == 'SUCCEEDED' for o in observations)
    # Legacy inference is unchanged and still available outside the WP04 binder.
    legacy_snapshot = dict(values[0]['snapshot'])
    legacy_snapshot.update(period_basis=None, actuality='UNKNOWN', statement_series=None)
    legacy = EvidenceRecord.model_validate(legacy_snapshot)
    assert legacy.period_basis.value == 'FY' and legacy.actuality is FinancialActuality.ACTUAL
    assert legacy.statement_series


async def test_R1B02A_missing_explicit_period_basis(tmp_path, monkeypatch):
    from src.domain.enums import FinancialActuality
    await _r1b02_bounded_negative(tmp_path, monkeypatch,
        {'period_basis': None, 'actuality': FinancialActuality.UNKNOWN,
         'statement_series': None, 'statement_cohort': None}, retained_original=True)


async def test_R1B02B_unknown_actuality(tmp_path, monkeypatch):
    from src.domain.enums import FinancialActuality
    await _r1b02_bounded_negative(tmp_path, monkeypatch, {'actuality': FinancialActuality.UNKNOWN})


async def test_R1B02C_missing_statement_series(tmp_path, monkeypatch):
    await _r1b02_bounded_negative(tmp_path, monkeypatch, {'statement_series': None})


async def test_R1B02D_reconstructed_identity_must_equal_A(tmp_path, monkeypatch):
    # All required semantics remain explicit; reconstruction alone fills cohort.
    await _r1b02_bounded_negative(tmp_path, monkeypatch, {'statement_cohort': None})
    valid_root = tmp_path / 'valid'; valid_root.mkdir()
    service, aggregate = await setup(valid_root)
    fresh, _ = await run_node(service, aggregate)
    calc = next(c for c in fresh.artifacts.calculations if c.capability_id == 'revenue_growth')
    binding = calc.parameters['wp04_method_binding']['input_binding']
    admission = fresh.node_binding.attempts[calc.task_id].admission
    authorized = {v['evidence_id']: v for v in admission.authorized_input_requirements['wp04_candidates']}
    for identity, actual in zip(binding['input_evidence_ids'], binding['evidence_digests']):
        assert actual == authorized[identity]['content_digest']
        record = next(e for e in fresh.artifacts.evidence if e.evidence_id == identity)
        assert canonical_value(record) == authorized[identity]['snapshot']
