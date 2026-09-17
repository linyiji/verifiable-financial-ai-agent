import json
from datetime import date
from pathlib import Path

import pytest

from src.data.artifacts import LocalRawArtifactStore
from src.data.fixtures import FixtureProvider
from src.data.freshness import FreshnessPolicy
from src.data.ingestion import EvidenceIngestionService
from src.data.provider import ProviderRequest
from src.data.repository import InMemoryEvidenceRepository
from src.data.validation import ValidationCode
from src.domain.enums import EvidenceStatus

FIXTURE = Path("tests/fixtures/nvda_financials.json")


def _request(**overrides: object) -> ProviderRequest:
    values = {
        "symbol": "NVDA",
        "dataset": "annual_financials",
        "as_of": date(2026, 9, 3),
        "expected_period": "FY2026",
    }
    values.update(overrides)
    return ProviderRequest(**values)


async def _ingest(
    fixture: Path = FIXTURE,
    *,
    artifact_root: Path | None = None,
    freshness_policy: FreshnessPolicy | None = None,
):
    repository = InMemoryEvidenceRepository()
    service = EvidenceIngestionService(
        repository=repository,
        artifact_store=LocalRawArtifactStore(artifact_root) if artifact_root else None,
        freshness_policy=freshness_policy,
    )
    result = await service.ingest(
        provider=FixtureProvider(fixture),
        request=_request(),
        run_id="RUN-1",
        object_id="OBJ-NVDA",
    )
    return result, repository


@pytest.mark.asyncio
async def test_valid_evidence_only_enters_accepted_bundle() -> None:
    result, repository = await _ingest()

    normalized = [
        (record.normalized_field, record.normalized_value) for record in result.accepted.records
    ]
    assert normalized == [
        ("revenue", "215900000000"),
        ("ebitda", "142500000000"),
    ]
    assert all(record.status is EvidenceStatus.ACCEPTED for record in result.accepted.records)
    assert len(await repository.list_by_run("RUN-1")) == 4


@pytest.mark.asyncio
async def test_missing_fields_are_rejected_before_materializing_evidence(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "missing.json"
    fixture.write_text(
        json.dumps(
            {
                "provider": "fixture",
                "object": {"symbol": "NVDA"},
                "records": [{"field": "revenue", "period": "FY2026", "as_of": "2026-01-25"}],
            }
        )
    )

    result, repository = await _ingest(fixture)

    assert result.records == ()
    assert result.accepted.records == []
    assert result.diagnostics[0].status is EvidenceStatus.REJECTED
    assert result.diagnostics[0].issues[0].code is ValidationCode.MISSING_FIELD
    assert await repository.list() == []


@pytest.mark.asyncio
async def test_period_mismatch_is_conflict_and_never_accepted() -> None:
    result, _ = await _ingest()

    mismatch = next(record for record in result.records if record.period == "Q1FY2026")
    assert mismatch.status is EvidenceStatus.CONFLICT
    assert mismatch.evidence_id not in {record.evidence_id for record in result.accepted.records}
    diagnostic = next(item for item in result.diagnostics if item.period == "Q1FY2026")
    assert ValidationCode.PERIOD_MISMATCH in {issue.code for issue in diagnostic.issues}


@pytest.mark.asyncio
async def test_currency_scale_is_normalized_to_canonical_base_units() -> None:
    result, _ = await _ingest()

    revenue = next(
        record for record in result.accepted.records if record.normalized_field == "revenue"
    )
    assert revenue.normalized_value == "215900000000"
    assert revenue.unit == "CURRENCY"
    assert revenue.currency == "USD"


@pytest.mark.asyncio
async def test_stale_record_is_persisted_as_rejected_but_not_accepted() -> None:
    result, repository = await _ingest(freshness_policy=FreshnessPolicy(max_age_days=1))

    assert result.accepted.records == []
    assert all(record.status is EvidenceStatus.REJECTED for record in result.records)
    assert all(record.status is EvidenceStatus.REJECTED for record in await repository.list())
    assert all(
        ValidationCode.STALE in {issue.code for issue in diagnostic.issues}
        for diagnostic in result.diagnostics
    )


@pytest.mark.asyncio
async def test_fixture_replay_is_deterministic() -> None:
    first, _ = await _ingest()
    second, _ = await _ingest()

    assert first.accepted.model_dump(mode="json") == second.accepted.model_dump(mode="json")
    assert [record.model_dump(mode="json") for record in first.records] == [
        record.model_dump(mode="json") for record in second.records
    ]


@pytest.mark.asyncio
async def test_raw_payload_is_written_to_artifact_store(tmp_path: Path) -> None:
    result, _ = await _ingest(artifact_root=tmp_path)

    artifact_refs = {Path(record.raw_artifact_ref) for record in result.records}
    assert len(artifact_refs) == 1
    artifact = artifact_refs.pop()
    _assert_artifact_matches_fixture(artifact)


def _assert_artifact_matches_fixture(artifact: Path) -> None:
    assert artifact.is_file()
    assert json.loads(artifact.read_text()) == json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("absolute", [False, True])
async def test_raw_store_reference_survives_cwd_changes(tmp_path, monkeypatch, absolute):
    import asyncio
    import hashlib

    from src.data.hashing import canonical_json, snapshot_hash

    origin, consumer = tmp_path / "origin", tmp_path / "consumer"
    origin.mkdir()
    consumer.mkdir()
    monkeypatch.chdir(origin)
    root = origin / "configured" if absolute else Path("configured")
    store = LocalRawArtifactStore(root)
    assert store._artifact_root == origin / "configured"
    # Even the first write must stay anchored to construction, not write-time cwd.
    monkeypatch.chdir(consumer)
    payload = {"source": "isolated test data", "values": [1, "原文", None]}
    expected = canonical_json(payload)
    identity = snapshot_hash(payload)
    target = origin / "configured" / "runs" / "RUN-STORE-TEST" / "evidence" / f"{identity}.json"
    promotions = []
    original_replace = Path.replace

    def observe_promotion(temporary, destination):
        assert temporary.parent == target.parent
        assert temporary.read_bytes() == expected
        assert not target.exists()
        promotions.append((temporary, destination))
        return original_replace(temporary, destination)

    monkeypatch.setattr(Path, "replace", observe_promotion)
    ref = await store.put_raw_snapshot(
        run_id="RUN-STORE-TEST", snapshot_hash=identity, payload=payload,
    )
    assert Path(ref).is_absolute() and Path(ref) == target
    assert (await asyncio.to_thread(Path(ref).read_bytes)) == expected
    assert hashlib.sha256(await asyncio.to_thread(Path(ref).read_bytes)).hexdigest() == identity
    assert len(promotions) == 1 and promotions[0][1] == target
    assert not promotions[0][0].exists()
    monkeypatch.chdir(origin)
    assert await store.put_raw_snapshot(
        run_id="RUN-STORE-TEST", snapshot_hash=identity, payload=payload,
    ) == ref
    assert len(promotions) == 1
    monkeypatch.chdir(consumer)
    assert (await asyncio.to_thread(Path(ref).read_bytes)) == expected
    with pytest.raises(ValueError, match="hash collision"):
        await store.put_raw_snapshot(
            run_id="RUN-STORE-TEST", snapshot_hash=identity, payload={"different": True},
        )
    assert (await asyncio.to_thread(Path(ref).read_bytes)) == expected


async def test_raw_store_does_not_publish_failed_atomic_promotion(tmp_path, monkeypatch):
    from src.data.hashing import snapshot_hash

    payload = {"source": "isolated atomic failure test"}
    identity = snapshot_hash(payload)
    store = LocalRawArtifactStore(tmp_path)
    target = tmp_path / "runs" / "RUN-ATOMIC" / "evidence" / f"{identity}.json"

    def fail_promotion(temporary, destination):
        assert temporary.is_file() and destination == target
        raise OSError("test promotion failure")

    monkeypatch.setattr(Path, "replace", fail_promotion)
    with pytest.raises(OSError, match="test promotion failure"):
        await store.put_raw_snapshot(run_id="RUN-ATOMIC", snapshot_hash=identity, payload=payload)
    assert not target.exists()
