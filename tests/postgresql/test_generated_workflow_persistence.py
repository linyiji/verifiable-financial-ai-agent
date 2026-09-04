import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application import persistence as application_persistence  # noqa: F401
from src.data import persistence as data_persistence  # noqa: F401
from src.domain.capability import (
    CapabilityBuildRecord,
    CapabilityValidationRecord,
    SandboxExecutionRecord,
)
from src.domain.enums import CapabilityLifecycle
from src.infrastructure.database.base import Base
from src.infrastructure.database.generated_workflow import (
    PostgreSQLCapabilityWorkflowRecorder,
)
from src.infrastructure.database.phase3_records import SQLAlchemyPhase3RecordRepository


@pytest.mark.asyncio
async def test_generated_validation_and_sandbox_resolve_run_from_build(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workflow.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    records = SQLAlchemyPhase3RecordRepository(sessions)
    recorder = PostgreSQLCapabilityWorkflowRecorder(records)
    build = CapabilityBuildRecord(
        build_id="BUILD-1",
        gap_id="GAP-1",
        run_id="RUN-1",
        task_id="TASK-1",
        requested_by="specialist",
        approved_by="research-lead",
        lifecycle=CapabilityLifecycle.SPEC_APPROVED,
    )
    validation = CapabilityValidationRecord(
        validation_id="VALID-1",
        build_id=build.build_id,
        implementation_hash="sha256:implementation",
        lifecycle=CapabilityLifecycle.FINANCIAL_VALIDATED,
    )
    sandbox = SandboxExecutionRecord(
        execution_id="SANDBOX-1",
        build_id=build.build_id,
        backend="docker",
        implementation_hash="sha256:implementation",
        runtime_version="Python 3.11",
        input_fixture_hash="sha256:fixture",
        network_disabled=True,
        read_only_root=True,
        non_root_user=True,
        resource_limits={"memory": "128m"},
        exit_code=0,
        output_hash="sha256:output",
        passed=True,
    )

    await recorder.record_build(build)
    await recorder.record_validation(validation, sandbox)

    assert await records.list(CapabilityValidationRecord, build.run_id) == [validation]
    assert await records.list(SandboxExecutionRecord, build.run_id) == [sandbox]
    await engine.dispose()


@pytest.mark.asyncio
async def test_generated_validation_rejects_unknown_build(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'unknown.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    recorder = PostgreSQLCapabilityWorkflowRecorder(
        SQLAlchemyPhase3RecordRepository(sessions)
    )
    validation = CapabilityValidationRecord(
        validation_id="VALID-1",
        build_id="BUILD-MISSING",
        implementation_hash="sha256:implementation",
        lifecycle=CapabilityLifecycle.FINANCIAL_VALIDATED,
    )
    sandbox = SandboxExecutionRecord(
        execution_id="SANDBOX-1",
        build_id="BUILD-MISSING",
        backend="docker",
        implementation_hash="sha256:implementation",
        runtime_version="Python 3.11",
        input_fixture_hash="sha256:fixture",
        network_disabled=True,
        read_only_root=True,
        non_root_user=True,
        resource_limits={},
    )

    with pytest.raises(ValueError, match="unknown build"):
        await recorder.record_validation(validation, sandbox)
    await engine.dispose()
