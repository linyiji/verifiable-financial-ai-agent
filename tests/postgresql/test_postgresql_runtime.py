from __future__ import annotations

import asyncio
import os
from importlib.util import find_spec
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application import persistence as application_persistence  # noqa: F401
from src.data import persistence as data_persistence  # noqa: F401
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.infrastructure.database import models as durable_models  # noqa: F401
from src.infrastructure.database.base import Base
from src.infrastructure.database.postgresql_events import (
    PostgresRuntimeEventStore,
    install_postgresql_runtime_event_sequence,
)
from src.runtime.events import EventSequenceError
from src.runtime.sse import runtime_event_stream

POSTGRESQL_TEST_URL = os.getenv("TEST_POSTGRESQL_URL")
POSTGRES_AVAILABLE = bool(POSTGRESQL_TEST_URL) and find_spec("asyncpg") is not None

pytestmark = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="TEST_POSTGRESQL_URL and asyncpg are required for real PostgreSQL tests",
)


@pytest.mark.asyncio
async def test_real_postgresql_atomic_event_sequence_and_sse_replay() -> None:
    assert POSTGRESQL_TEST_URL is not None
    schema = f"ws_j_{uuid4().hex}"
    admin_engine = create_async_engine(POSTGRESQL_TEST_URL)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_async_engine(
        POSTGRESQL_TEST_URL,
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await install_postgresql_runtime_event_sequence(connection)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        store = PostgresRuntimeEventStore(sessions, poll_interval_seconds=0.01)

        emitted = await asyncio.gather(
            *(
                store.emit(run_id="RUN-PG", event_type=RuntimeEventType.TASK_PROGRESS)
                for _ in range(30)
            )
        )
        assert sorted(event.sequence for event in emitted) == list(range(1, 31))
        assert [event.sequence for event in await store.replay("RUN-PG")] == list(range(1, 31))

        with pytest.raises(EventSequenceError, match="database rejected"):
            await store.append(
                RuntimeEvent(
                    event_id="EVT-OUT-OF-ORDER",
                    run_id="RUN-PG",
                    type=RuntimeEventType.TASK_PROGRESS,
                    sequence=32,
                )
            )

        stream = runtime_event_stream(store=store, run_id="RUN-PG", last_event_id="29")
        payload = await anext(stream)
        await stream.aclose()
        assert payload.startswith("id: 30\n")
        assert await store.resolve_resume_sequence("RUN-PG", emitted[0].event_id) == (
            emitted[0].sequence
        )
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()
