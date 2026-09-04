import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application import persistence as application_persistence  # noqa: F401
from src.capabilities.generated.artifacts import (
    GeneratedCapabilityArtifactStore,
    generated_text_sha256,
)
from src.capabilities.generated.models import CodeBuilderOutput, GeneratedCapabilityCandidate
from src.data import persistence as data_persistence  # noqa: F401
from src.domain.capability import (
    CapabilityBuildRecord,
    CapabilityValidationRecord,
    GeneratedCapabilityArtifactRecord,
    GeneratedCapabilityRecord,
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
        runtime_image_identity="python:3.11-test@sha256:test",
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
    recorder = PostgreSQLCapabilityWorkflowRecorder(SQLAlchemyPhase3RecordRepository(sessions))
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
        runtime_image_identity="python:3.11-test@sha256:test",
        input_fixture_hash="sha256:fixture",
        network_disabled=True,
        read_only_root=True,
        non_root_user=True,
        resource_limits={},
    )

    with pytest.raises(ValueError, match="unknown build"):
        await recorder.record_validation(validation, sandbox)
    await engine.dispose()


@pytest.mark.asyncio
async def test_generated_artifact_binding_and_exact_bytes_survive_restart(tmp_path) -> None:
    database_path = tmp_path / "retention.db"
    artifact_root = tmp_path / "generated-artifacts"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    records = SQLAlchemyPhase3RecordRepository(sessions)
    store = GeneratedCapabilityArtifactStore(artifact_root)
    recorder = PostgreSQLCapabilityWorkflowRecorder(records, artifact_store=store)
    source = "# π exact\r\ndef execute(inputs):\r\n    return inputs"
    tests = "# 雪 exact\ndef run_tests(execute, fixture):\n    assert execute(fixture) == fixture"
    output = CodeBuilderOutput(
        capability_id="restart_exact",
        version="1.0.0-generated",
        purpose="Audit restart retention.",
        input_schema={"value": "decimal"},
        output_schema={"value": "decimal"},
        formula_id="restart_exact_v1",
        formula_description="identity",
        source_code=source,
        unit_tests=tests,
        financial_invariants=[],
        allowed_imports=[],
    )
    candidate = GeneratedCapabilityCandidate(
        build_id="BUILD-RESTART",
        output=output,
        implementation_hash=generated_text_sha256(source),
        provider="teamorouter",
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        attempted_models=("gpt-5.6-sol",),
        input_tokens=1,
        output_tokens=1,
        latency_ms=1.0,
    )
    build = CapabilityBuildRecord(
        build_id=candidate.build_id,
        gap_id="GAP-RESTART",
        run_id="RUN-RESTART",
        task_id="TASK-RESTART",
        requested_by="specialist",
        approved_by="research-lead",
        lifecycle=CapabilityLifecycle.FINANCIAL_VALIDATED,
    )
    generated = GeneratedCapabilityRecord(
        generated_capability_id="GEN-RESTART",
        run_id=build.run_id,
        task_id=build.task_id,
        gap_id=build.gap_id,
        capability_id=output.capability_id,
        capability_version=output.version,
        formula_id=output.formula_id,
        purpose=output.purpose,
        input_schema=output.input_schema,
        output_schema=output.output_schema,
        formula_description=output.formula_description,
        implementation_hash=candidate.implementation_hash,
        source_ref=f"generated://{build.build_id}/source.py",
        unit_test_ref=f"generated://{build.build_id}/tests.py",
        runtime_version="Python 3.11",
        lifecycle=CapabilityLifecycle.FINANCIAL_VALIDATED,
    )
    sandbox = SandboxExecutionRecord(
        execution_id="SANDBOX-RESTART",
        build_id=build.build_id,
        backend="docker",
        implementation_hash=candidate.implementation_hash,
        runtime_version="Python 3.11",
        runtime_image_identity="python:3.11-test@sha256:test",
        input_fixture_hash="sha256:fixture",
        network_disabled=True,
        read_only_root=True,
        non_root_user=True,
        resource_limits={"memory": "128m"},
        passed=True,
    )
    await recorder.record_build(build)
    await recorder.record_generated(generated)
    retained = await recorder.retain_generated_artifacts(
        generated=generated,
        candidate=candidate,
        sandbox_execution=sandbox,
    )
    await engine.dispose()

    restarted_engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    restarted_sessions = async_sessionmaker(restarted_engine, expire_on_commit=False)
    restarted_records = SQLAlchemyPhase3RecordRepository(restarted_sessions)
    restored = await restarted_records.list(GeneratedCapabilityArtifactRecord, build.run_id)
    restarted_store = GeneratedCapabilityArtifactStore(artifact_root)
    reconstructed = restarted_store.reconstruct(restored[0])

    assert restored == [retained]
    assert reconstructed.source_bytes == source.encode("utf-8")
    assert reconstructed.test_bytes == tests.encode("utf-8")
    assert reconstructed.sandbox_request({"value": "1"}).source == source

    tampered = retained.model_copy(update={"runtime_image_identity": "tampered"})
    with pytest.raises(ValueError, match="bindings are immutable"):
        await restarted_records.save(tampered)
    await restarted_engine.dispose()
