"""Original ingestion policy is durable evidence, never inferred on Resume."""

from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.data.fixtures import FixtureProvider
from src.data.freshness import FreshnessPolicy, FreshnessStatus, policy_for
from src.data.ingestion import EvidenceIngestionService
from src.data.provider import ProviderRequest
from src.data.repository import InMemoryEvidenceRepository
from src.domain.evidence import EvidenceRecord, EvidenceValidationProvenance
from src.domain.node_binding import digest

FIXTURE = Path("tests/fixtures/nvda_financials.json")


async def ingest(repository=None, *, age=800, request=None):
    return await EvidenceIngestionService(
        repository=repository if repository is not None else InMemoryEvidenceRepository(),
        freshness_policy=FreshnessPolicy(age),
    ).ingest(
        provider=FixtureProvider(FIXTURE),
        request=request or ProviderRequest(
            symbol="NVDA", dataset="annual_financials", as_of=date(2026, 9, 3),
            fields=("revenue", "ebitda"), limit=2,
        ),
        run_id="RUN-PROVENANCE", object_id="OBJ-NVDA",
    )


async def test_actual_policy_request_and_mapped_index_captured_before_first_add():
    class ObservingRepository(InMemoryEvidenceRepository):
        async def add(self, record):
            assert record.validation_provenance is not None
            return await super().add(record)

    result = await ingest(ObservingRepository())
    for record, diagnostic in zip(result.records, result.diagnostics, strict=True):
        provenance = record.validation_provenance
        assert provenance.mapped_record_index == diagnostic.raw_index
        assert provenance.freshness.max_age_days == 800
        assert provenance.request.fields == ("revenue", "ebitda")
        assert provenance.request.limit == 2
        assert provenance.request.as_of == date(2026, 9, 3)
        assert record.status == diagnostic.status
        assert EvidenceRecord.model_validate_json(record.model_dump_json()) == record
    assert policy_for("annual_financials").max_age_days == 550


@pytest.mark.parametrize("dataset,limit,age,elapsed", [
    ("annual_financials", 2, 800, 600),
    ("historical_prices", 250, 500, 450),
])
async def test_original_policy_differs_from_generic_defaults(dataset, limit, age, elapsed):
    request = ProviderRequest(
        symbol="NVDA", dataset=dataset, as_of=date(2026, 9, 3), limit=limit,
    )
    result = await ingest(age=age, request=request)
    saved = result.records[0].validation_provenance
    observed = request.as_of - timedelta(days=elapsed)
    assert policy_for(dataset).evaluate(observed, request.as_of) is FreshnessStatus.STALE
    assert FreshnessPolicy(saved.freshness.max_age_days).evaluate(
        observed, saved.request.as_of
    ) is FreshnessStatus.FRESH
    assert FreshnessPolicy(saved.freshness.max_age_days).evaluate(
        request.as_of + timedelta(days=1), saved.request.as_of
    ) is FreshnessStatus.FUTURE


async def test_null_legacy_serialization_and_collision_never_enroll_or_rewrite():
    result = await ingest()
    current = result.records[0]
    payload = current.model_dump(mode="json")
    payload.pop("validation_provenance")
    old = EvidenceRecord.model_validate(payload)
    assert old.model_dump(mode="json") == payload
    assert '"validation_provenance"' not in old.model_dump_json()
    repository = InMemoryEvidenceRepository()
    await repository.add(old)
    before = digest(old)
    with pytest.raises(ValueError, match="evidence identity collision"):
        await ingest(repository)
    assert digest(await repository.get(old.evidence_id)) == before
    assert (await repository.get(old.evidence_id)).validation_provenance is None


async def test_same_id_different_policy_denied_without_overwrite():
    repository = InMemoryEvidenceRepository()
    first = await ingest(repository)
    before = [r.model_dump(mode="json") for r in await repository.list()]
    again = await ingest(repository)
    assert again.records == first.records
    assert again.created_records == ()
    with pytest.raises(ValueError, match="evidence identity collision"):
        await ingest(repository, age=801)
    assert [r.model_dump(mode="json") for r in await repository.list()] == before


@pytest.mark.parametrize("path,value", [
    (("schema_version",), "evidence-validation/v2"),
    (("validator_version",), "unknown"),
    (("freshness", "rule_version"), "unknown"),
    (("freshness", "max_age_days"), True),
    (("freshness", "max_age_days"), -1),
    (("freshness", "max_age_days"), "800"),
    (("mapped_record_index",), -1),
    (("mapped_record_index",), True),
    (("request", "limit"), 501),
    (("request", "limit"), 0),
    (("request", "limit"), True),
    (("request", "extra_authority"), "grant"),
    (("extra_authority",), "grant"),
])
async def test_provenance_is_closed_and_strict(path, value):
    raw = (await ingest()).records[0].validation_provenance.model_dump(mode="json")
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        EvidenceValidationProvenance.model_validate(raw)
