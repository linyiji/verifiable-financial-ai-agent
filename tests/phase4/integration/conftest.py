from __future__ import annotations

import asyncio
import os

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture(autouse=True)
def offline_provider_boundary(monkeypatch: pytest.MonkeyPatch):
    """Admission/reopen fixtures never need a real external research result.

    Preserve the production composition and scheduler, but hold external HTTP
    at a cancellable fake boundary. ASGI/TestClient traffic is not intercepted.
    No successful financial/model output is invented by this fixture.
    """
    for name in ("FMP_API_KEY", "TEAMOROUTER_API_KEY", "MIMO_API_KEY"):
        monkeypatch.setenv(name, "offline-test-only-not-a-credential")

    async def pending_fake_response(self, request):
        await asyncio.Event().wait()
        raise AssertionError("fake pending provider cannot return an output")

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", pending_fake_response
    )


async def _reset_isolated_database(url: str) -> None:
    parsed = make_url(url)
    marker = os.environ.get("VFA_ISOLATED_TEST_DATABASE")
    if (
        not marker
        or not marker.startswith("recovery_v1_")
        or parsed.database != marker
        or parsed.host != "postgres"
    ):
        raise RuntimeError("explicit isolated recovery test database identity required")
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                )
            )
            for table_name in sorted(result.scalars()):
                if not table_name.replace("_", "").isalnum():
                    raise RuntimeError("unexpected test table name")
                await connection.execute(
                    text(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE')
                )
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def isolated_postgresql_state():
    url = os.environ.get("TEST_POSTGRESQL_URL")
    if url:
        asyncio.run(_reset_isolated_database(url))
    yield
