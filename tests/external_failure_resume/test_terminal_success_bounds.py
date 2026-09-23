"""D1 production repository proofs on a verified, lawful RMC1 PostgreSQL seed.

D1_TEST_ADMIN_URL must target a task-owned disposable cluster. D1_TEST_TEMPLATE
is a restored RMC1 preterminal dump; D1_RMC1_FIXTURE is its proof_fixtures path.
Every test clones that seed into its own database. No domain rows are fabricated
except explicitly named negative corruption fixtures.
"""

import asyncio
import hashlib
import json
import os
import sys
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import select, text

from src.adapters.finrobot.professional_reporting import ControlledArtifactStore
from src.application.persistence import (
    ResearchRunAggregateRow,
    SQLAlchemyApplicationRepository,
    TerminalSettlementBudget,
)
from src.application.repository import compare_whole, validate_root
from src.domain.node_binding import BindingDenied, OwnerToken
from src.infrastructure.config.settings import DatabaseSettings
from src.infrastructure.database.composition import create_postgresql_persistence

pytestmark = pytest.mark.skipif(
    not os.environ.get("D1_TEST_ADMIN_URL"), reason="explicit disposable D1 PostgreSQL required"
)


def budget(seconds=300):
    return TerminalSettlementBudget(asyncio.get_running_loop().time() + seconds)


@pytest.fixture
async def case():
    base = Path(os.environ["D1_RMC1_FIXTURE"])
    receipt = json.loads((base.parent / "RUN.json").read_text())
    for item in receipt["proof_file_manifest"]:
        assert (
            hashlib.sha256((base.parent / item["path"]).read_bytes()).hexdigest() == item["sha256"]
        )
    admin = await asyncpg.connect(os.environ["D1_TEST_ADMIN_URL"])
    name = "d1_" + uuid4().hex
    template = os.environ["D1_TEST_TEMPLATE"]
    assert template.replace("_", "").isalnum()
    await admin.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
    url = os.environ["D1_TEST_ADMIN_URL"].rsplit("/", 1)[0] + "/" + name
    p = create_postgresql_persistence(
        DatabaseSettings(url=url.replace("postgresql://", "postgresql+asyncpg://"))
    )
    repo = p.application_repository
    data = json.loads((base / "legal_proposal.json").read_text())
    proposed = repo._to_aggregate(data, data.get("aggregate_schema_version", 1))
    owner = OwnerToken.model_validate_json((base / "execution_owner.json").read_text())
    current = await repo.get_run_fresh(owner.run_id)
    validate_root(current, owner)
    compare_whole(current, proposed)
    store = None
    # The artifact URI includes reports/, so use the recorded publisher root.
    artifact = proposed.artifacts.report_artifacts[0]
    for root in (base / "product", base / "product" / "report", base / "product" / "reports"):
        if not root.is_dir():
            continue
        candidate = ControlledArtifactStore(root)
        if candidate.resolve(artifact.artifact_ref).is_file():
            store = candidate
            break
    assert store is not None, "verified report artifact root is required"
    store.read_verified(artifact)
    c = dict(
        p=p,
        repo=repo,
        owner=owner,
        proposed=proposed,
        released_at=datetime.now(UTC),
        report_store=store,
        url=url,
        base=base,
    )
    try:
        yield c
    finally:
        await p.close()
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


async def settle(c, seconds=300, *, repo=None, context=None):
    return await (repo or c["repo"]).finalize_success(
        c["owner"],
        c["proposed"],
        released_at=c["released_at"],
        budget=context or budget(seconds),
        report_store=c["report_store"],
    )


async def read(c, *, repo=None, seconds=300):
    return await (repo or c["repo"]).read_terminal_success(
        c["owner"].run_id, budget=budget(seconds), report_store=c["report_store"]
    )


async def snapshot(c):
    tables = (
        "research_runs",
        "runtime_events",
        "runtime_event_counters",
        "tasks",
        "task_dependencies",
        "calculation_records",
        "review_records",
        "canonical_execution_records",
        "released_research_results",
        "report_artifact_records",
        "correction_records",
        "replan_records",
    )
    async with c["p"].sessions() as session:
        settings = (
            await session.execute(
                text("SELECT current_setting('lock_timeout'),current_setting('statement_timeout')")
            )
        ).one()
        assert settings == ("0", "0")
        await session.execute(text("SELECT pg_sleep(0.001)"))
        result = {}
        for table in tables:
            rows = await session.execute(
                text(f"SELECT row_to_json(t)::text FROM {table} t WHERE run_id=:run_id ORDER BY 1"),
                {"run_id": c["owner"].run_id},
            )
            result[table] = list(rows.scalars())
        return result


def watch(c, monkeypatch):
    repo = c["repo"]
    original = repo._inspect_success
    records = []

    async def inspect(session, row, value, command):
        settings = (
            await session.execute(
                text(
                    "SELECT current_setting('lock_timeout'),"
                    "current_setting('statement_timeout'),pg_backend_pid()"
                )
            )
        ).one()
        assert settings[:2] == ("30s", "2min")
        outcome = await original(session, row, value, command)
        records.append(
            dict(
                pid=settings[2],
                deadline=command["attempt_deadline"],
                outcome=command.get("outcome"),
                command=command,
            )
        )
        return outcome

    async def forbidden(*args, **kwargs):
        raise AssertionError("failure finalization is forbidden")

    monkeypatch.setattr(repo, "_inspect_success", inspect)
    monkeypatch.setattr(repo, "finalize_failure", forbidden)
    return records


async def test_db01_db06_full_commit_ack(case, monkeypatch):
    c = case
    records = watch(c, monkeypatch)
    initial = await snapshot(c)
    start = time.monotonic()
    value, events = await settle(c)
    assert time.monotonic() - start < 180
    assert records[-1]["command"]["phase"] == "COMMIT_ACKNOWLEDGED"
    assert records[-1]["command"]["outcome"] == "COMMITTED"
    assert [e.type.value for e in events] == ["release.completed", "run.completed"]
    assert value.node_binding.owner_generation == c["owner"].owner_generation + 1
    assert value.node_binding.binding_revision == c["proposed"].node_binding.binding_revision + 1
    assert value.runtime.binding_ref == value.node_binding.reference()
    committed = await snapshot(c)
    assert initial != committed
    fresh = SQLAlchemyApplicationRepository(c["p"].sessions)
    replay = await read(c, repo=fresh)
    assert c["repo"]._payload(replay[0]) == c["repo"]._payload(value)
    assert replay[1] == events
    assert await snapshot(c) == committed
    print("DB01_DB06", time.monotonic() - start, records[-1]["command"]["phase"])


async def test_db02_db03_default_lock(case, monkeypatch):
    c = case
    watch(c, monkeypatch)
    initial = await snapshot(c)
    errors = []
    original = c["repo"]._success_transaction

    async def transaction(*args, **kwargs):
        try:
            return await original(*args, **kwargs)
        except Exception as exc:
            errors.append(str(exc))
            raise

    monkeypatch.setattr(c["repo"], "_success_transaction", transaction)
    async with c["p"].sessions() as blocker:
        await blocker.scalar(select(ResearchRunAggregateRow).with_for_update())
        started = time.monotonic()
        with pytest.raises(BindingDenied, match="RESULT_UNKNOWN"):
            await settle(c, 32)
        elapsed = time.monotonic() - started
        assert 30 <= elapsed < 35
        assert any("lock timeout" in e for e in errors)
        await blocker.rollback()
    assert await snapshot(c) == initial
    print("DB02_DB03", elapsed, errors)


async def test_db04_default_statement_rollback(case, monkeypatch):
    c = case
    watch(c, monkeypatch)
    initial = await snapshot(c)
    original = c["repo"]._persist_children
    errors = []

    async def slow(session, value):
        await original(session, value)
        await session.flush()
        try:
            await session.execute(text("SELECT pg_sleep(121)"))
        except Exception as exc:
            errors.append(str(exc))
            raise

    monkeypatch.setattr(c["repo"], "_persist_children", slow)
    start = time.monotonic()
    with pytest.raises(BindingDenied, match="RESULT_UNKNOWN"):
        await settle(c, 126)
    assert any("statement timeout" in error for error in errors)
    assert await snapshot(c) == initial
    print("DB04", time.monotonic() - start, errors)


async def test_db07_db09_commit_loss_after_authorized_retry(case, monkeypatch):
    c = case
    records = watch(c, monkeypatch)
    original = c["repo"]._commit_success
    writers = []

    async def loss(session):
        writers.append(await session.scalar(text("SELECT pg_backend_pid()")))
        if len(writers) == 1:
            await session.rollback()
        else:
            await original(session)
        raise ConnectionError("lost driver acknowledgement")

    monkeypatch.setattr(c["repo"], "_commit_success", loss)
    value, events = await settle(c)
    assert len(writers) == 2
    assert records[-1]["pid"] not in writers
    assert records[-1]["outcome"] == "COMMITTED"
    assert value.confirmed_risk_semantic_binding == c["proposed"].confirmed_risk_semantic_binding
    before = await snapshot(c)
    code = """import asyncio,json,sys
from pathlib import Path
from src.infrastructure.database.composition import create_postgresql_persistence
from src.infrastructure.config.settings import DatabaseSettings
from src.application.persistence import TerminalSettlementBudget
from src.adapters.finrobot.professional_reporting import ControlledArtifactStore
async def main():
 p=create_postgresql_persistence(DatabaseSettings(url=sys.argv[1]))
 try:
  r=await p.application_repository.read_terminal_success(sys.argv[2],
   budget=TerminalSettlementBudget(asyncio.get_running_loop().time()+300),
   report_store=ControlledArtifactStore(Path(sys.argv[3])))
  print(json.dumps({'aggregate':p.application_repository._payload(r[0]),
   'events':[e.model_dump(mode='json') for e in r[1]]}))
 finally: await p.close()
asyncio.run(main())"""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        code,
        c["url"].replace("postgresql://", "postgresql+asyncpg://"),
        c["owner"].run_id,
        str(c["report_store"].root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    assert proc.returncode == 0, err.decode()
    fresh = json.loads(out)
    assert fresh["aggregate"] == c["repo"]._payload(value)
    assert fresh["events"] == [e.model_dump(mode="json") for e in events]
    assert await snapshot(c) == before
    print("DB07_DB09", writers, records[-1]["pid"], "fresh process exact")


async def test_db08_db10_no_effect_two_attempts(case, monkeypatch):
    c = case
    records = watch(c, monkeypatch)
    initial = await snapshot(c)
    writes = []

    async def rollback(session):
        writes.append(await session.scalar(text("SELECT pg_backend_pid()")))
        await session.rollback()
        raise ConnectionError("rollback response lost")

    monkeypatch.setattr(c["repo"], "_commit_success", rollback)
    with pytest.raises(BindingDenied, match="RESULT_UNKNOWN"):
        await settle(c)
    assert len(writes) == 2
    assert len(records) == 4  # two write inspections plus two readbacks
    assert all(r["outcome"] == "KNOWN_NOT_COMMITTED" for r in records)
    assert len({r["pid"] for r in records}) == 4
    assert await snapshot(c) == initial
    print("DB08_DB10", writes, len(records))


async def test_db13_db14_db15_db16_concurrency_replay(case, monkeypatch):
    c = case
    watch(c, monkeypatch)
    repos = [SQLAlchemyApplicationRepository(c["p"].sessions) for _ in range(3)]
    results = await asyncio.gather(*(settle(c, repo=r) for r in repos))
    value, events = results[0]
    assert all(
        c["repo"]._payload(v) == c["repo"]._payload(value) and es == events for v, es in results
    )
    before = await snapshot(c)
    assert value.confirmed_risk_semantic_binding == c["proposed"].confirmed_risk_semantic_binding
    assert value.run.completed_at == c["proposed"].run.completed_at
    assert events[0].timestamp == c["released_at"]
    with pytest.raises(BindingDenied, match="STALE_WRITE_REJECTED"):
        await c["repo"].save_run(c["proposed"])
    for field in ("released_at", "completed_at", "owner"):
        changed = dict(c)
        if field == "released_at":
            changed[field] += timedelta(seconds=1)
        elif field == "owner":
            changed[field] = c[field].model_copy(update={"owner_generation": 999})
        else:
            changed["proposed"] = deepcopy(c["proposed"])
            changed["proposed"].run.completed_at += timedelta(seconds=1)
        with pytest.raises(BindingDenied):
            await settle(changed)
        assert await snapshot(c) == before
    print("DB13_DB16 exact concurrent results", [e.event_id for e in events])


@pytest.mark.parametrize(
    "corruption", ["event", "child", "counter", "watermark", "generation", "reference"]
)
async def test_db11_integrity_stop(case, corruption):
    c = case
    await settle(c)
    async with c["p"].sessions() as session, session.begin():
        if corruption == "event":
            await session.execute(
                text("DELETE FROM runtime_events WHERE payload->>'type'='release.completed'")
            )
        elif corruption == "child":
            await session.execute(text("DELETE FROM released_research_results"))
        elif corruption == "counter":
            await session.execute(
                text("UPDATE runtime_event_counters SET last_sequence=last_sequence+1")
            )
        elif corruption == "watermark":
            await session.execute(
                text("UPDATE research_runs SET projection_sequence=projection_sequence-1")
            )
        else:
            row = await session.scalar(select(ResearchRunAggregateRow).with_for_update())
            data = deepcopy(row.payload)
            if corruption == "generation":
                data["node_binding"]["owner_generation"] += 1
            else:
                data["runtime"]["binding_ref"]["binding_revision"] += 1
            row.payload = data
    before = await snapshot(c)
    with pytest.raises(BindingDenied):
        await read(c)
    assert await snapshot(c) == before


async def test_db17_local_settings(case, monkeypatch):
    c = case
    watch(c, monkeypatch)
    await settle(c)
    for factory in (
        c["p"],
        create_postgresql_persistence(
            DatabaseSettings(url=c["url"].replace("postgresql://", "postgresql+asyncpg://"))
        ),
    ):
        async with factory.sessions() as session:
            settings = (
                await session.execute(
                    text(
                        "SELECT current_setting('lock_timeout'),"
                        "current_setting('statement_timeout')"
                    )
                )
            ).one()
            assert settings == ("0", "0")
            await session.execute(text("SELECT pg_sleep(0.01)"))
        if factory is not c["p"]:
            await factory.close()


async def test_db05_db18_precommit_cancel_and_late_return(case, monkeypatch):
    c = case
    initial = await snapshot(c)
    original = c["repo"]._persist_children
    commits = []
    original_commit = c["repo"]._commit_success

    async def commit(session):
        commits.append(True)
        return await original_commit(session)

    async def late(session, value):
        await original(session, value)
        try:
            await session.execute(text("SELECT pg_sleep(10)"))
        except asyncio.CancelledError:
            # A cooperative caller may suppress cancellation; production must
            # still reject its late return before COMMIT.
            return

    monkeypatch.setattr(c["repo"], "_commit_success", commit)
    monkeypatch.setattr(c["repo"], "_persist_children", late)
    for seconds in (0, 1.5):
        start = time.monotonic()
        with pytest.raises(BindingDenied, match="RESULT_UNKNOWN") as exc:
            await settle(c, seconds)
        assert not exc.value.retryable
        assert time.monotonic() - start < seconds + 2
        assert await snapshot(c) == initial
    assert not commits
    print("DB05_DB18 late return denied", commits)


async def test_db05_default_attempt_deadline_driver_cancel(case, monkeypatch):
    c = case
    records = watch(c, monkeypatch)
    original = c["repo"]._commit_success
    writers = []
    elapsed = []

    async def delayed(session):
        writers.append(await session.scalar(text("SELECT pg_backend_pid()")))
        if len(writers) == 1:
            start = time.monotonic()
            try:
                # Two legal SQL operations each below statement120; their
                # cumulative driver await must still be bounded by attempt180.
                await session.execute(text("SELECT pg_sleep(100)"))
                await session.execute(text("SELECT pg_sleep(100)"))
            finally:
                elapsed.append(time.monotonic() - start)
        await original(session)

    monkeypatch.setattr(c["repo"], "_commit_success", delayed)
    start = time.monotonic()
    value, events = await settle(c)
    assert 175 < elapsed[0] < 182
    assert time.monotonic() - start < 190
    assert len(writers) == 2
    assert records[1]["pid"] not in writers
    assert records[1]["outcome"] == "KNOWN_NOT_COMMITTED"
    assert value.run.status.value == "RELEASED"
    assert len(events) == 2
    print("DB05_ATTEMPT180", elapsed, time.monotonic() - start, writers)


async def test_db12_default_outer_fuse_committed_but_read_unavailable(case, monkeypatch):
    c = case
    repo = c["repo"]
    original_commit = repo._commit_success
    original_inspect = repo._inspect_success
    original_transaction = repo._success_transaction
    reads = []
    writers = []

    async def lost(session):
        writers.append(await session.scalar(text("SELECT pg_backend_pid()")))
        await original_commit(session)
        raise ConnectionError("actual commit; reply lost")

    async def unavailable(session, row, value, command):
        if value.node_binding.lifecycle == "CLOSED":
            await session.execute(text("SELECT pg_sleep(110)"))
            await session.execute(text("SELECT pg_sleep(110)"))
        return await original_inspect(session, row, value, command)

    async def transaction(command, context, *, readback):
        if readback:
            reads.append((time.monotonic(), context.deadline))
        return await original_transaction(command, context, readback=readback)

    async def forbidden(*args, **kwargs):
        raise AssertionError("must not failure-finalize unknown committed outcome")

    monkeypatch.setattr(repo, "_commit_success", lost)
    monkeypatch.setattr(repo, "_inspect_success", unavailable)
    monkeypatch.setattr(repo, "_success_transaction", transaction)
    monkeypatch.setattr(repo, "finalize_failure", forbidden)
    context = budget()
    start = time.monotonic()
    with pytest.raises(BindingDenied, match="RESULT_UNKNOWN") as exc:
        await settle(c, context=context)
    elapsed = time.monotonic() - start
    assert 299 <= elapsed < 303
    assert not exc.value.retryable
    assert len(writers) == 1 and len(reads) == 2
    assert all(deadline == context.deadline for _, deadline in reads)
    committed = await snapshot(c)
    monkeypatch.setattr(repo, "_inspect_success", original_inspect)
    value, events = await read(c)
    assert value.run.status.value == "RELEASED"
    assert len(events) == 2
    assert await snapshot(c) == committed
    print("DB12_OUTER300", elapsed, reads, writers)


async def test_db08_live_writer_is_not_no_effect(case, monkeypatch):
    c = case
    entered, release = asyncio.Event(), asyncio.Event()
    original = c["repo"]._commit_success

    async def hold(session):
        entered.set()
        await release.wait()
        await original(session)

    monkeypatch.setattr(c["repo"], "_commit_success", hold)
    initial = await snapshot(c)
    writer = asyncio.create_task(settle(c))
    try:
        await asyncio.wait_for(entered.wait(), 15)
        assert await snapshot(c) == initial  # unlocked MVCC sees no effects
        contender = SQLAlchemyApplicationRepository(c["p"].sessions)
        with pytest.raises(BindingDenied, match="RESULT_UNKNOWN"):
            await settle(c, seconds=1, repo=contender)
    finally:
        release.set()
        result = await writer
    assert result[0].run.status.value == "RELEASED"
    assert (await read(c))[1] == result[1]


async def test_db18_consumed_context_retry_and_boundaries(case, monkeypatch):
    c = case
    records = watch(c, monkeypatch)
    initial = await snapshot(c)
    # Exactly 300 elapsed blocks entry; 299 elapsed gives at most one second.
    for remaining in (0, 1):
        context = budget(remaining)
        async with c["p"].sessions() as blocker:
            await blocker.scalar(select(ResearchRunAggregateRow).with_for_update())
            start = time.monotonic()
            with pytest.raises(BindingDenied, match="RESULT_UNKNOWN"):
                await settle(c, context=context)
            assert time.monotonic() - start < remaining + 1
            await blocker.rollback()
        assert await snapshot(c) == initial
    original = c["repo"]._commit_success
    count = 0

    async def rollback_once(session):
        nonlocal count
        count += 1
        if count == 1:
            await session.rollback()
            raise ConnectionError("lost rollback reply")
        await original(session)

    monkeypatch.setattr(c["repo"], "_commit_success", rollback_once)
    context = budget(30)  # 270 seconds already consumed by its orchestration owner.
    start = time.monotonic()
    value, _ = await settle(c, context=context)
    assert value.run.status.value == "RELEASED" and count == 2
    assert len(records) == 3
    assert all(r["deadline"] == context.deadline for r in records)
    assert 0 < context.remaining() < 30
    assert time.monotonic() - start < 30


async def test_db05_actual_commit_in_server_cancelled(case, monkeypatch):
    """A deferred server fault pauses the actual COMMIT, not a fake commit flag."""
    c = case
    initial = await snapshot(c)
    watch(c, monkeypatch)
    async with c["p"].sessions() as session, session.begin():
        await session.execute(
            text("""
            CREATE FUNCTION d1_commit_delay() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.status = 'RELEASED' THEN PERFORM pg_sleep(20); END IF;
              RETURN NEW;
            END $$
        """)
        )
        await session.execute(
            text("""
            CREATE CONSTRAINT TRIGGER d1_commit_delay
            AFTER UPDATE ON research_runs DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION d1_commit_delay()
        """)
        )
    operation = asyncio.create_task(settle(c, seconds=6))
    observed = None
    try:
        async with c["p"].sessions() as observer:
            for _ in range(500):
                observed = await observer.scalar(
                    text("""
                    SELECT pid FROM pg_stat_activity
                    WHERE datname=current_database() AND query ILIKE 'COMMIT%'
                      AND wait_event='PgSleep' AND state='active'
                """)
                )
                if observed:
                    break
                await asyncio.sleep(0.01)
                # pg_stat_activity statistics snapshots are transaction-local.
                await observer.rollback()
        assert observed is not None, "actual server COMMIT was not observed"
        start = time.monotonic()
        with pytest.raises(BindingDenied, match="RESULT_UNKNOWN"):
            await operation
        assert time.monotonic() - start < 6
    finally:
        if not operation.done():
            operation.cancel()
        try:
            await operation
        except (BindingDenied, asyncio.CancelledError):
            pass
    assert await snapshot(c) == initial
    async with c["p"].sessions() as observer:
        assert not await observer.scalar(
            text("SELECT count(*) FROM pg_stat_activity WHERE pid=:pid"), {"pid": observed}
        )
    print("DB05_ACTUAL_SERVER_COMMIT_CANCELLED", observed, "no surviving writer")
