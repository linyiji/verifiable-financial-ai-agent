"""Real Docker + registry + fundamental task seam, using retained source bytes.

Financial numbers match the incident. The 200-day history is explicitly synthetic
positive-control evidence; it must not be presented as missing live evidence.
"""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.execution import IntegratedTaskExecutor
from src.application.phase3_financial import (
    FreeCashFlowMarginValidationPlanProvider,
    Phase3FinancialCapabilityExtension,
    Phase3ResearchLeadCapabilityAuthority,
    free_cash_flow_margin_requirement,
)
from src.application.service import ResearchApplicationService
from src.capabilities.generated.artifacts import GeneratedCapabilityArtifactStore
from src.capabilities.generated.models import CodeBuilderOutput, GeneratedCapabilityCandidate
from src.capabilities.generated.orchestration import GeneratedCapabilityOrchestrator
from src.capabilities.generated.scoped_registry import ScopedCapabilityRegistry
from src.capabilities.generated.validation import GeneratedCapabilityValidator, source_sha256
from src.capabilities.registry import CapabilityRegistry
from src.domain.calculation import CalculationRecord
from src.domain.enums import TaskStatus
from src.infrastructure.database.base import Base
from src.infrastructure.database.generated_workflow import PostgreSQLCapabilityWorkflowRecorder
from src.infrastructure.database.phase3_records import SQLAlchemyPhase3RecordRepository
from src.runtime.scheduler import DependencyScheduler
from src.tooling.generated_sandbox import DEFAULT_SANDBOX_IMAGE, DockerSandboxBackend
from tests.integration.test_generated_validation_pipeline import _docker_image_available
from tests.unit.test_phase3_financial_extension import _evidence, _state, _task


@pytest.mark.skipif(
    not _docker_image_available(DEFAULT_SANDBOX_IMAGE), reason="Docker image required"
)
@pytest.mark.asyncio
async def test_saved_generated_fcf_through_real_fundamental_task_runtime(tmp_path):
    task = _task()
    state = _state(task)
    fixtures = Path(__file__).parents[1] / "fixtures/generated_fcf"
    source = (fixtures / "source.txt").read_text()
    tests = (fixtures / "tests.txt").read_text()
    assert source_sha256(source) == (
        "sha256:d8551c1df602f65ce0a06e2dc3d5d31cbe82cb674b8e9d3ae83832bf09dc2df2"
    )
    assert source_sha256(tests) == (
        "sha256:07b836ebb2d9febc8818dde1a4186756bca9e67bec4e55643bb6ee340f79f128"
    )
    requirement = free_cash_flow_margin_requirement(task)

    class SavedBuilder:
        calls = 0

        async def generate(self, request):
            self.calls += 1
            return GeneratedCapabilityCandidate(
                build_id=request.build_id,
                output=CodeBuilderOutput(
                    capability_id=requirement.capability_id,
                    version="1.0.0-generated",
                    purpose=requirement.purpose,
                    input_schema=requirement.input_schema,
                    output_schema=requirement.output_schema,
                    formula_id=requirement.formula_id,
                    formula_description="(operating cash flow + signed capex) / revenue",
                    financial_invariants=requirement.financial_invariants,
                    allowed_imports=requirement.allowed_imports,
                    source_code=source,
                    unit_tests=tests,
                ),
                implementation_hash=source_sha256(source),
                provider="offline-retained-artifact",
                requested_model="none",
                actual_model="none",
                attempted_models=(),
                input_tokens=0,
                output_tokens=0,
                latency_ms=0,
            )

    builder = SavedBuilder()
    registry = ScopedCapabilityRegistry(CapabilityRegistry())
    service = ResearchApplicationService()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'contract.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    orchestrator = GeneratedCapabilityOrchestrator(
        registry=registry,
        research_lead=Phase3ResearchLeadCapabilityAuthority(),
        code_builder=builder,
        validator=GeneratedCapabilityValidator(
            sandbox=DockerSandboxBackend(), plans=FreeCashFlowMarginValidationPlanProvider()
        ),
        event_store=service.event_store,
        recorder=PostgreSQLCapabilityWorkflowRecorder(SQLAlchemyPhase3RecordRepository(sessions),
            artifact_store=GeneratedCapabilityArtifactStore(tmp_path / "generated")),
    )
    service.add_calculation_extension(
        Phase3FinancialCapabilityExtension(
            generated=orchestrator,
            event_store=service.event_store,
            instrumentation=service.instrumentation,
        )
    )
    values = {"E-OCF": "102718000000", "E-CAPEX": "-6042000000", "E-REV": "215938000000"}
    evidence = [
        e.model_copy(update={"normalized_value": values[e.evidence_id]})
        if e.evidence_id in values
        else e
        for e in _evidence()
    ]
    state.task(task.task_id).task_input_evidence_ids = [e.evidence_id for e in evidence]
    artifacts = SimpleNamespace(
        evidence=evidence,
        calculations=[],
        corrections=[],
        generated_capability_refs=[],
        judgments=[],
        task_outputs={},
    )
    aggregate = SimpleNamespace(runtime=state, artifacts=artifacts)

    class OfflineTaskExecutor(IntegratedTaskExecutor):
        async def execute(self, task, context):
            # Bypass only data collection / model narrative, never calculation dispatch.
            return await self._execute_fundamental_analysis(task)

        async def _invoke_research_agent(self, *args, **kwargs):
            return None

    state.task(task.task_id).status = TaskStatus.READY
    await DependencyScheduler(
        event_store=service.event_store, checkpoint_store=service.checkpoint_store
    )._execute_task(state, state.task(task.task_id), OfflineTaskExecutor(service, aggregate))
    assert builder.calls == 1
    assert len(registry.registrations()) == 1
    assert state.task(task.task_id).status is TaskStatus.COMPLETED
    fcf = next(c for c in artifacts.calculations if c.capability_id == requirement.capability_id)
    assert isinstance(fcf, CalculationRecord)
    persisted = CalculationRecord.model_validate_json(fcf.model_dump_json())
    assert persisted.model_dump(mode="json") == fcf.model_dump(mode="json")
    assert Decimal(str(persisted.output_value)) == fcf.output_value
    assert fcf.output_value == Decimal("0.4477025812964832498217080829")
    assert fcf.input_evidence_ids == ["E-OCF", "E-CAPEX", "E-REV"]
    assert fcf.parameters["financial_validation_result"] == "PASS"
    assert fcf.implementation_hash == source_sha256(source)
    events = await service.event_store.replay(task.run_id)
    fcf_events = [
        e.type.value for e in events if e.payload.get("capability_id") == requirement.capability_id
    ]
    assert "calculation.started" in fcf_events
    assert "calculation.completed" in fcf_events
    await engine.dispose()
