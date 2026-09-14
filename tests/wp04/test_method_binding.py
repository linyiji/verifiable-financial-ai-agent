"""WP04 R1: exact method identity; all fixtures are local and retained."""
import asyncio
import hashlib
import json
import socket
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.application.execution import IntegratedTaskExecutor, wp04_candidate_snapshot
from src.application.models import ResearchRunDraft
from src.application.service import ResearchApplicationService
from src.capabilities.financial.growth import RevenueGrowthCapability
from src.capabilities.provenance import wp04_descriptor, verify_wp04_method, WP04_MANIFEST_PATHS
from src.domain.enums import EvidenceStatus
from src.domain.evidence import EvidenceRecord
from src.domain.node_binding import BindingDenied, digest
from src.application.repository import node_invocation
from src.domain.research_goal import ResearchGoal
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.domain.task import PlannedTaskGraph, Task
from src.runtime.scheduler import TaskExecutionContext

# Explicit composition expectation, never inferred from the bytes under test.
MANIFEST_HASH = 'sha256:85334af911261170da6b461532e3bf6bb5693bd8f1e42977c3f96efa2f6c8e51'
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('WP04_LOCAL_FIXTURE_NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', denied)


def records(tmp_path, run='RUN-WP04', obj='OBJECT-WP04', prior='3', current='4'):
    raw_records = [
        {'field': 'revenue', 'period': 'FY2025', 'as_of': '2026-09-01', 'value': prior, 'unit': 'USD'},
        {'field': 'revenue', 'period': 'FY2026', 'as_of': '2026-09-01', 'value': current, 'unit': 'USD'},
        {'field': 'revenue', 'period': 'Q1FY2026', 'as_of': '2026-09-01', 'value': '1', 'unit': 'USD'},
        {'field': 'ebitda', 'period': 'FY2026', 'as_of': '2026-09-01', 'value': '1', 'unit': 'USD'},
    ]
    raw = json.dumps({'object': {'currency': 'USD'}, 'records': raw_records}).encode()
    path = tmp_path / 'raw.json'
    path.write_bytes(raw)
    return [EvidenceRecord(evidence_id='E' + str(i), run_id=run, object_id=obj,
        evidence_category='FINANCIAL_STATEMENT', provider='fixture', retrieved_at=datetime.now(UTC), period=row['period'],
        as_of=date(2026, 9, 1), raw_artifact_ref=str(path), normalized_field=row['field'],
        normalized_value=row['value'], unit='CURRENCY', currency='USD',
        snapshot_hash='sha256:' + hashlib.sha256(raw).hexdigest(), status=EvidenceStatus.ACCEPTED)
        for i, row in enumerate(raw_records)]


async def setup(tmp_path, prior='3', current='4', enabled=True, extra_tasks=False):
    class Planner:
        def plan(self, *, run_id, goal, scheme):
            tasks = [Task(task_id=run_id + ':fundamental', run_id=run_id,
                          task_type='fundamental_analysis', goal='local method test',
                          assigned_agent='fundamental_analyst', skill_id='fundamental_analysis_v1')]
            if extra_tasks:
                tasks.append(Task(task_id=run_id + ':valuation', run_id=run_id,
                    task_type='valuation_analysis', goal='project committed growth',
                    assigned_agent='valuation_analyst', skill_id='valuation_analysis_v1',
                    dependencies=[tasks[0].task_id]))
            return PlannedTaskGraph(graph_id='PLAN-WP04', run_id=run_id, tasks=tasks)
    service = ResearchApplicationService(planner=Planner(), run_id_factory=lambda: 'RUN-WP04',
        wp04_method_binding_enabled=enabled, wp04_manifest_sha256=MANIFEST_HASH,
        wp04_diagnostic_store=ResearchAgentOutputArtifactStore(tmp_path / 'diagnostics'))
    obj = await service.create_object(symbol='TEST', company_name='Local', exchange='LOCAL')
    goal = ResearchGoal(goal_id='GOAL-WP04', research_object_id=obj.object_id,
                        goal_text='exact method', as_of=date(2026, 9, 14))
    scheme = ResearchSchemeSnapshot(scheme_id='SCHEME-WP04', goal_id=goal.goal_id,
        research_object_id=obj.object_id, generated_by='local-fixture',
        calculation_requirements=['revenue_growth', 'ebitda_margin'])
    draft = ResearchRunDraft(draft_id='DRAFT-WP04', goal=goal, scheme_snapshot=scheme)
    await service.repository.add_draft(draft)
    aggregate = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    evidence = records(tmp_path, obj=obj.object_id, prior=prior, current=current)
    # Preexisting accepted input fixture is installed before execution authority exists.
    stored = service.repository._runs[aggregate.run.run_id]
    stored.artifacts.evidence = evidence
    stored.runtime.actual_graph.tasks[0].task_input_evidence_ids = [e.evidence_id for e in evidence]
    from src.application.evidence_routing import RunEvidenceStore
    store = RunEvidenceStore(aggregate.run.run_id)
    service._evidence_stores[aggregate.run.run_id] = store
    for e in evidence:
        store._register_record(e)
        await service.evidence_repository.add(e)
    return service, await service.repository.get_run_fresh(aggregate.run.run_id)


async def arm(service, aggregate):
    repo = service.repository
    owner = await repo.claim_execution(aggregate.run.run_id)
    await repo.begin_scheduler(owner)
    fresh = await repo.get_run_fresh(aggregate.run.run_id)
    task = fresh.runtime.actual_graph.tasks[0]
    executor = IntegratedTaskExecutor(service, fresh)
    admission = await repo.reserve_node(owner, task, executor.admission_requirements(task))
    await repo.dispatch_node(admission)
    return executor, task, admission


async def run_node(service, aggregate):
    executor, task, admission = await arm(service, aggregate)
    result = await executor.execute(task, TaskExecutionContext(task.run_id, 1, admission))
    return await service.repository.get_run_fresh(task.run_id), result


def check(service, descriptor=None):
    return verify_wp04_method(service.capability_registry, service.tool_runtime,
                             descriptor or wp04_descriptor(MANIFEST_HASH), MANIFEST_HASH)


async def test_M01_exact_version(tmp_path):
    service, aggregate = await setup(tmp_path)
    exact = service.capability_registry.get('revenue_growth', '1.1.0')
    for version in ('1.2.0', '1.9.0', '1.10.0', '9.0.0'):
        class Newer:
            definition = exact.definition.model_copy(update={'version': version})
            async def execute(self, *args):
                raise AssertionError('newer version dispatched')
        service.capability_registry.register(Newer())
    assert check(service)[0] is exact
    fresh, _ = await run_node(service, aggregate)
    calc = next(c for c in fresh.artifacts.calculations if c.capability_id == 'revenue_growth')
    assert calc.capability_version == '1.1.0'
    assert calc.parameters['wp04_method_binding']['formula_version'] == '1.0.0'


async def test_M02_missing_exact(tmp_path):
    service, aggregate = await setup(tmp_path)
    exact = service.capability_registry._capabilities.pop(('revenue_growth', '1.1.0'))
    service.capability_registry._capabilities['revenue_growth', '9.0.0'] = exact
    with pytest.raises(BindingDenied, match='MISSING_EXACT_METHOD'):
        await run_node(service, aggregate)
    fresh = await service.repository.get_run_fresh(aggregate.run.run_id)
    assert not fresh.artifacts.calculations and not fresh.node_binding.current_results
    denial = list(fresh.artifacts.wp04_method_observations.values())[-1]
    assert denial.support_status == 'MISSING_METHOD' and denial.dispatch_count == 0


@pytest.mark.parametrize('path', WP04_MANIFEST_PATHS)
@pytest.mark.parametrize('stage', ['after_A', 'after_B'])
async def test_M03_source_manifest(tmp_path, monkeypatch, path, stage):
    service, aggregate = await setup(tmp_path)
    executor, task, admission = await arm(service, aggregate)
    target = ROOT / path
    original_read = Path.read_bytes
    active = stage == 'after_A'
    def read_bytes(self):
        data = original_read(self)
        return data + b'\n# mutation fixture\n' if active and self == target else data
    monkeypatch.setattr(Path, 'read_bytes', read_bytes)
    original_bind = IntegratedTaskExecutor._bind_step
    async def bind(self, *args, **kwargs):
        nonlocal active
        result = await original_bind(self, *args, **kwargs)
        active = True
        return result
    if stage == 'after_B':
        monkeypatch.setattr(IntegratedTaskExecutor, '_bind_step', bind)
    with pytest.raises(BindingDenied, match='METHOD_SOURCE_IDENTITY_MISMATCH'):
        await executor.execute(task, TaskExecutionContext(task.run_id, 1, admission))
    assert not service.repository._calculations
    assert not (await service.repository.get_run_fresh(task.run_id)).node_binding.current_results


@pytest.mark.parametrize('mutation', ['foreign', 'subclass', 'instance', 'helper', 'constant', 'code'])
async def test_M04_loaded_identity(tmp_path, monkeypatch, mutation):
    service, _ = await setup(tmp_path)
    import src.capabilities.financial.growth as growth
    exact = service.capability_registry.get('revenue_growth', '1.1.0')
    if mutation == 'foreign':
        service.capability_registry._capabilities['revenue_growth', '1.1.0'] = SimpleNamespace(definition=exact.definition)
    elif mutation == 'subclass':
        class Child(RevenueGrowthCapability): pass
        service.capability_registry._capabilities['revenue_growth', '1.1.0'] = Child()
    elif mutation == 'instance':
        exact.execute = lambda *a: None
    elif mutation == 'helper':
        monkeypatch.setattr(growth, 'calculate_revenue_growth', lambda *a: Decimal(1))
    elif mutation == 'constant':
        monkeypatch.setattr(growth, 'REVENUE_GROWTH_FORMULA_ID', 'other')
    else:
        monkeypatch.setattr(growth.calculate_revenue_growth, '__code__', (lambda a, b: Decimal(1)).__code__)
    with pytest.raises(BindingDenied): check(service)


@pytest.mark.parametrize('mutation', ['backend', 'runtime', 'backend_override', 'runtime_override'])
async def test_M05_native_composition(tmp_path, mutation):
    from src.domain.enums import CapabilityBackend
    service, _ = await setup(tmp_path)
    if mutation == 'runtime':
        service.tool_runtime = SimpleNamespace(_registry=service.capability_registry)
    elif mutation == 'backend':
        service.tool_runtime._backends[CapabilityBackend.NATIVE] = SimpleNamespace()
    elif mutation == 'backend_override':
        service.tool_runtime._backends[CapabilityBackend.NATIVE].execute = lambda *a: None
    else:
        service.tool_runtime.execute = lambda *a: None
    with pytest.raises(BindingDenied): check(service)


async def test_M06_descriptor_and_config(tmp_path):
    service, _ = await setup(tmp_path)
    desc = wp04_descriptor(MANIFEST_HASH)
    with pytest.raises(BindingDenied): check(service, desc.model_copy(update={'formula_version': '9.0.0'}))
    with pytest.raises(BindingDenied): wp04_descriptor('sha256:' + '0' * 64)


async def test_M07_requirement_frozen_and_reload(tmp_path):
    service, aggregate = await setup(tmp_path)
    service.wp04_method_binding_enabled = False
    assert aggregate.runtime.actual_graph.tasks[0].wp04_method_requirement is not None
    executor, task, admission = await arm(service, aggregate)
    root = service.repository._runs[task.run_id]
    req = root.runtime.actual_graph.tasks[0].wp04_method_requirement
    root.runtime.actual_graph.tasks[0].wp04_method_requirement = req.model_copy(update={'requirement_digest': 'changed'})
    with pytest.raises(BindingDenied):
        await executor.execute(task, TaskExecutionContext(task.run_id, 1, admission))
    assert not service.repository._calculations


async def _r1b01_bounded_negative(tmp_path, monkeypatch, mutation, stage):
    import src.capabilities.financial.growth as growth
    from contextvars import ContextVar
    made = []

    def change():
        if mutation == 'qualname':
            growth.RevenueGrowthCapability.__qualname__ = 'ForeignRevenueGrowth'
        elif mutation == 'definition':
            monkeypatch.setattr(growth.RevenueGrowthCapability, 'definition',
                growth.RevenueGrowthCapability.definition.model_copy(update={'input_schema': {'foreign': 'schema'}}))
        else:
            monkeypatch.setattr(growth, '_growth_observer', ContextVar('wp04_growth_observer', default=None))

    if stage == 'pre_run':
        original = ResearchApplicationService.__init__
        def init(self, *args, **kwargs):
            original(self, *args, **kwargs)
            made.append(self)
            assert self._wp04_load_expectation is self.tool_runtime._wp04_load_expectation
            change()
        monkeypatch.setattr(ResearchApplicationService, '__init__', init)
        with pytest.raises(BindingDenied, match='METHOD_.*IDENTITY_MISMATCH'):
            await setup(tmp_path)
        assert not made[0].repository._runs and not made[0].repository._calculations
        return
    service, aggregate = await setup(tmp_path)
    frozen = service._wp04_load_expectation
    if stage == 'admission':
        change()
        with pytest.raises(BindingDenied, match='METHOD_.*IDENTITY_MISMATCH'):
            await arm(service, aggregate)
    else:
        executor, task, admission = await arm(service, aggregate)
        if stage == 'dispatch':
            change()
        else:
            original = IntegratedTaskExecutor._execute_wp04
            async def after_capture(self, *args):
                calculation = await original(self, *args)
                assert calculation.parameters['wp04_method_binding']['decimal_flags_observation']['capture_count'] == 1
                change()
                return calculation
            monkeypatch.setattr(IntegratedTaskExecutor, '_execute_wp04', after_capture)
        with pytest.raises(BindingDenied, match='METHOD_.*IDENTITY_MISMATCH'):
            await executor.execute(task, TaskExecutionContext(task.run_id, 1, admission))
    assert service._wp04_load_expectation is frozen
    fresh = await service.repository.get_run_fresh(aggregate.run.run_id)
    assert not service.repository._calculations and not fresh.node_binding.current_results
    assert not any(o.numeric_outcome == 'SUCCEEDED' for o in (fresh.artifacts.wp04_method_observations or {}).values())


@pytest.mark.parametrize('stage', ['pre_run', 'admission', 'dispatch', 'commit'])
async def test_R1B01A_class_qualname_mutation(tmp_path, monkeypatch, stage):
    original = RevenueGrowthCapability.__qualname__
    try:
        await _r1b01_bounded_negative(tmp_path, monkeypatch, 'qualname', stage)
    finally:
        RevenueGrowthCapability.__qualname__ = original


@pytest.mark.parametrize('stage', ['pre_run', 'admission', 'dispatch', 'commit'])
async def test_R1B01B_definition_schema_mutation(tmp_path, monkeypatch, stage):
    await _r1b01_bounded_negative(tmp_path, monkeypatch, 'definition', stage)


@pytest.mark.parametrize('stage', ['pre_run', 'admission', 'dispatch', 'commit'])
async def test_R1B01C_observer_handle_replacement(tmp_path, monkeypatch, stage):
    await _r1b01_bounded_negative(tmp_path, monkeypatch, 'observer', stage)
