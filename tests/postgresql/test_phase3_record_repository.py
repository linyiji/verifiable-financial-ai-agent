import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application import persistence as application_persistence  # noqa: F401
from src.data import persistence as data_persistence  # noqa: F401
from src.domain.enums import ProofStatus
from src.domain.proof import ProofArtifactReference, ProofRecord
from src.infrastructure.database.base import Base
from src.infrastructure.database.phase3_records import SQLAlchemyPhase3RecordRepository


@pytest.mark.asyncio
async def test_phase3_records_round_trip_without_receipt_bytes(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'phase3.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repository = SQLAlchemyPhase3RecordRepository(sessions)
    proof = ProofRecord(
        proof_id="PROOF-1",
        run_id="RUN-1",
        calculation_id="CALC-1",
        backend="risc0",
        program_id="revenue_growth_v1",
        image_id="IMAGE-1",
        implementation_hash="sha256:implementation",
        input_commitment="sha256:input",
        receipt_artifact_ref="artifact://proofs/PROOF-1.receipt",
        receipt_hash="sha256:receipt",
        journal_hash="sha256:journal",
        status=ProofStatus.VALID,
    )
    artifact = ProofArtifactReference(
        artifact_id="ART-1",
        proof_id=proof.proof_id,
        artifact_type="RISC0_RECEIPT",
        artifact_ref=proof.receipt_artifact_ref,
        content_hash=proof.receipt_hash,
        size_bytes=1024,
    )

    await repository.save(proof)
    await repository.save(artifact, run_id=proof.run_id)

    assert await repository.get(ProofRecord, proof.proof_id) == proof
    assert await repository.list(ProofRecord, proof.run_id) == [proof]
    assert await repository.get(ProofArtifactReference, artifact.artifact_id) == artifact
    assert "receipt" not in Base.metadata.tables["proof_records"].columns
    assert set(Base.metadata.tables["proof_records"].columns.keys()) == {
        "proof_id",
        "run_id",
        "payload",
    }
    await engine.dispose()


@pytest.mark.asyncio
async def test_phase3_record_cannot_move_between_runs(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repository = SQLAlchemyPhase3RecordRepository(sessions)
    artifact = ProofArtifactReference(
        artifact_id="ART-1",
        proof_id="PROOF-1",
        artifact_type="RISC0_RECEIPT",
        artifact_ref="artifact://proofs/PROOF-1.receipt",
        content_hash="sha256:receipt",
        size_bytes=1,
    )
    await repository.save(artifact, run_id="RUN-1")

    with pytest.raises(ValueError, match="cannot move between runs"):
        await repository.save(artifact, run_id="RUN-2")
    await engine.dispose()
