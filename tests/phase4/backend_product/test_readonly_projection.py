"""Control-flow regression: read reconstruction must not consult/write the cache.

Model builders have their own validation tests; this seam test uses instrumented
sessions and builders to fail on any read-path DML/commit, including concurrent
reads and missing/stale cache conditions. No database or provider is contacted.
"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.selectable import Select

from src.domain.enums import RunStatus
from src.phase4_product import postgresql_backend as module


class Projection:
    generated_at = datetime(2026, 9, 8, tzinfo=UTC)

    def __init__(self, facts):
        self.facts = facts

    def model_dump(self, **kwargs):
        return self.facts

    def model_copy(self, *, update):
        assert not update
        return self


class Session:
    def __init__(self, owner):
        self.owner = owner

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, model, key):
        if model is module.ResearchRunAggregateRow:
            return self.owner.row
        if model is module.ResearchObjectRow:
            return SimpleNamespace(payload="object-authority")
        raise AssertionError("Read attempted to consult a cache as authority")

    async def scalars(self, statement):
        assert isinstance(statement, Select), "Read issued non-SELECT SQL"
        return SimpleNamespace(
            all=lambda: [SimpleNamespace(payload=SimpleNamespace(payload={"status": "FAILED"}))]
        )

    async def execute(self, statement):
        assert self.owner.allow_write, "Read issued cache DML"
        self.owner.writes.append(statement)

    async def commit(self):
        assert self.owner.allow_write, "Read committed a projection"
        self.owner.commits += 1


@pytest.fixture
def setup(monkeypatch):
    for name in (
        "ResearchObject",
        "ResearchRun",
        "ResearchGoal",
        "ResearchSchemeSnapshot",
        "PlannedTaskGraph",
        "ActualRuntimeGraph",
        "CompletedRunArtifacts",
        "RuntimeEvent",
    ):
        monkeypatch.setattr(module, name, SimpleNamespace(model_validate=lambda value: value))
    monkeypatch.setattr(module, "normalize_runtime_event_v1", lambda value: value)

    def build(**kwargs):
        run = kwargs["run"]
        return Projection(
            {
                "run_id": run.run_id,
                "status": run.status.value,
                "scheme": kwargs.get("confirmed_scheme", kwargs.get("scheme")),
                "revision": kwargs.get("projection_revision", kwargs.get("revision")),
                "sequence": kwargs.get("projection_sequence", kwargs.get("sequence")),
            }
        )

    monkeypatch.setattr(module, "build_atomic_run_projection", build)

    def make(status, cache):
        owner = SimpleNamespace(allow_write=False, commits=0, writes=[], cache=cache)
        owner.row = SimpleNamespace(
            object_id="OBJ-A",
            projection_revision=12,
            projection_sequence=17,
            payload={
                "run": SimpleNamespace(run_id="RUN-A", status=status),
                "goal": "goal-authority",
                "scheme": "scheme-authority",
                "runtime": {
                    "planned_graph": "planned-authority",
                    "actual_graph": "actual-authority",
                },
                "artifacts": SimpleNamespace(review=None, proofs=[]),
            },
        )
        backend = object.__new__(module.PostgreSQLPhase4ProductBackend)
        backend.sessions = lambda: Session(owner)
        backend._path_change_sources = lambda *args: ()
        backend._released_projection = build
        return backend, owner

    return make


@pytest.mark.parametrize("status", [RunStatus.RELEASED, RunStatus.FAILED, RunStatus.RUNNING])
@pytest.mark.parametrize(
    "cache", [None, {"revision": 0, "payload": "stale"}, {"revision": 12, "payload": "existing"}]
)
async def test_repeated_and_concurrent_reads_never_write(setup, status, cache):
    backend, owner = setup(status, cache)
    first = await backend.get_projection("RUN-A")
    concurrent = await asyncio.gather(*(backend.get_projection("RUN-A") for _ in range(8)))
    assert all(p.model_dump() == first.model_dump() for p in concurrent)
    assert first.facts == {
        "run_id": "RUN-A",
        "status": status.value,
        "scheme": "scheme-authority",
        "revision": 12,
        "sequence": 17,
    }
    assert owner.commits == 0 and owner.writes == [] and owner.cache == cache


async def test_explicit_materialization_retained(setup):
    backend, owner = setup(RunStatus.RELEASED, None)
    owner.allow_write = True
    projected = await backend.materialize_projection("RUN-A")
    assert projected.facts["scheme"] == "scheme-authority"
    assert owner.commits == 1 and len(owner.writes) == 1
    sql = str(owner.writes[0])
    assert "INSERT INTO phase4_run_projections" in sql and "ON CONFLICT" in sql


async def test_missing_run_fails_without_persistence(setup):
    backend, owner = setup(RunStatus.FAILED, None)
    owner.row = None
    with pytest.raises(module.ProductError):
        await backend.get_projection("RUN-MISSING")
    assert owner.commits == 0 and owner.writes == []
