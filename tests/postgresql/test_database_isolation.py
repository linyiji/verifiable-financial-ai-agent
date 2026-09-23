"""Failure-path regressions: the Legacy fixture must never discover an ambient DB."""

import hashlib
import json
import os
from types import SimpleNamespace

import asyncpg
import pytest

from tests.postgresql import test_postgresql_runtime as runtime


@pytest.fixture
def no_connections(monkeypatch):
    attempts = []

    async def denied(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("driver reached before ownership validation")

    monkeypatch.setattr(asyncpg, "connect", denied)
    yield attempts
    assert attempts == []


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "postgresql+asyncpg://mac@localhost:5432/vefin_phase4_local",
        "postgresql+asyncpg://mac@127.0.0.1:55555/vefin_phase4_local",
        "postgresql+asyncpg://mac@127.0.0.1:5432/vefin_test_probe",
        "postgresql+asyncpg://mac@localhost:55555/vefin_test_probe",
        "sqlite+aiosqlite:///ambient.db",
        "not a URL",
        "postgresql+asyncpg://mac@127.0.0.1:55555/vefin_test_probe?host=localhost",
        "postgresql+asyncpg://mac@127.0.0.1:55555/vefin_test_probe",
    ],
)
async def test_legacy_fails_before_connect_without_owned_url(monkeypatch, no_connections, url):
    monkeypatch.delenv("VEFIN_TEST_POSTGRESQL_OWNERSHIP", raising=False)
    monkeypatch.setenv("TEST_POSTGRESQL_URL", "postgresql+asyncpg://mac@127.0.0.1:55555/test")
    if url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(RuntimeError, match="task-owned DATABASE_URL required"):
        await runtime.test_real_postgresql_atomic_event_sequence_and_sse_replay()


@pytest.fixture
def ownership(tmp_path, monkeypatch):
    # Model local process metadata only. Real owned-process proofs run separately.
    url = "postgresql+asyncpg://mac@127.0.0.1:55555/vefin_test_probe"
    data = tmp_path / "pgdata"
    data.mkdir(mode=0o700)
    state = ["12345", str(data), "1234567890", "55555", str(tmp_path), "127.0.0.1", "0 0", "ready"]
    (data / "postmaster.pid").write_text("\n".join(state))
    owner = dict(
        task_id="regression",
        database_url_sha256=hashlib.sha256(url.encode()).hexdigest(),
        postmaster_pid=12345,
        started_at="1234567890",
    )
    receipt = tmp_path / "ownership.json"
    receipt.write_text(json.dumps(owner))
    receipt.chmod(0o600)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("VEFIN_TEST_POSTGRESQL_OWNERSHIP", str(receipt))
    monkeypatch.setattr(
        runtime.subprocess,
        "check_output",
        lambda *a, **k: f"{os.getuid()} /local/bin/postgres -D {data}",
    )
    return SimpleNamespace(url=url, data=data, owner=owner, receipt=receipt, state=state)


@pytest.mark.parametrize(
    "damage",
    [
        "url_hash",
        "pid",
        "started_at",
        "port",
        "address",
        "status",
        "missing_pid",
        "invalid_receipt",
        "public_receipt",
        "public_data",
        "wrong_process",
        "settings_mismatch",
    ],
)
async def test_setup_failure_never_falls_back(monkeypatch, no_connections, ownership, damage):
    o = ownership
    if damage in {"url_hash", "pid", "started_at"}:
        key = {
            "url_hash": "database_url_sha256",
            "pid": "postmaster_pid",
            "started_at": "started_at",
        }[damage]
        o.owner[key] = "mismatch"
        o.receipt.write_text(json.dumps(o.owner))
    elif damage in {"port", "address", "status"}:
        o.state[{"port": 3, "address": 5, "status": 7}[damage]] = "invalid"
        (o.data / "postmaster.pid").write_text("\n".join(o.state))
    elif damage == "missing_pid":
        (o.data / "postmaster.pid").unlink()
    elif damage == "invalid_receipt":
        o.receipt.write_text("not JSON")
    elif damage == "public_receipt":
        o.receipt.chmod(0o644)
    elif damage == "public_data":
        o.data.chmod(0o755)
    elif damage == "wrong_process":
        monkeypatch.setattr(
            runtime.subprocess, "check_output", lambda *a, **k: f"{os.getuid()} /bin/sleep 100"
        )
    else:
        monkeypatch.setattr(
            runtime,
            "Settings",
            lambda: SimpleNamespace(
                database=SimpleNamespace(
                    url="postgresql+asyncpg://mac@localhost/vefin_phase4_local"
                )
            ),
        )
    with pytest.raises(RuntimeError, match="task-owned DATABASE_URL required"):
        await runtime.test_real_postgresql_atomic_event_sequence_and_sse_replay()


async def test_guard_rechecks_ownership_before_pool_connect(monkeypatch, no_connections, ownership):
    async with runtime._isolated_persistence() as (persistence, _, _):
        monkeypatch.delenv("DATABASE_URL")
        with pytest.raises(RuntimeError, match="task-owned DATABASE_URL required"):
            async with persistence.engine.connect():
                raise AssertionError("connection unexpectedly opened")


def test_settings_reads_explicit_owned_url_on_each_invocation(ownership):
    assert runtime._owned_database_settings().url == ownership.url
    assert runtime._owned_database_settings().url == ownership.url
