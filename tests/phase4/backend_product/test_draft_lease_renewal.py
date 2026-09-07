"""No providers: exact renewal and production confirmation validation in isolated PostgreSQL."""

import importlib.util
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.persistence import ResearchRunDraftRow
from src.infrastructure.database.draft_leases import (
    DraftLeaseAuthorizationRow,
    load_record,
    renew_exact_draft,
)
from src.phase4_product.admission import DRAFT_EXPIRY, build_prepare_draft, validate_confirm_request
from src.phase4_product.contracts import ConfirmResearchRunRequestV1
from src.phase4_product.draft_review import RenewDraftLeaseRequest, read_exact_draft
from src.phase4_product.errors import ProductError
from tests.phase4.backend_product.test_admission import _prepare_values
from tests.phase4.backend_product.test_incremental import context


def draft_fixture():
    req, goal, scheme = _prepare_values()
    c = context()
    req = req.model_copy(
        update={
            "as_of": c.target_as_of,
            "base_run_id": c.base_run_id,
            "base_research_view_version": c.base_research_view_version,
        }
    )
    goal = goal.model_copy(update={"as_of": c.target_as_of})
    scheme = scheme.model_copy(update={"incremental_context": c})
    return build_prepare_draft(
        req,
        draft_id="DRAFT-LEASE",
        goal=goal,
        scheme_snapshot=scheme,
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )


def renewal_request(draft):
    c = draft.scheme_snapshot.incremental_context
    return RenewDraftLeaseRequest(
        research_object_id=draft.object_id,
        draft_hash=draft.draft_hash,
        scheme_id=draft.scheme_snapshot.scheme_id,
        base_run_id=c.base_run_id,
        base_research_view_version=c.base_research_view_version,
        previous_expires_at=draft.expires_at,
    )


def confirmation(draft):
    return ConfirmResearchRunRequestV1(
        research_object_id=draft.object_id,
        draft_id=draft.draft_id,
        draft_hash=draft.draft_hash,
        draft_version=draft.draft_version,
        confirm_scheme=True,
    )


@pytest.fixture
async def database():
    if not os.environ.get("TEST_POSTGRESQL_URL"):
        pytest.skip("requires isolated PostgreSQL")
    schema = "draft_lease_test_" + uuid4().hex
    admin = create_async_engine(os.environ["TEST_POSTGRESQL_URL"])
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        os.environ["TEST_POSTGRESQL_URL"], connect_args={"server_settings": {"search_path": schema}}
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    def migrate(conn):
        ResearchRunDraftRow.__table__.create(conn)
        spec = importlib.util.spec_from_file_location(
            "lease_migration", Path("alembic/versions/20260907_0010_draft_lease_authorizations.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
        draft = draft_fixture()
        async with sessions() as session, session.begin():
            session.add(
                ResearchRunDraftRow(
                    draft_id=draft.draft_id,
                    object_id=draft.object_id,
                    payload=draft.model_dump(mode="json"),
                    created_at=draft.created_at,
                    draft_version=draft.draft_version,
                    draft_hash=draft.draft_hash,
                    expires_at=draft.expires_at,
                )
            )
        yield sessions, draft
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def test_renewal_only_authorizes_time_and_replay_is_stable(database):
    sessions, draft = database
    with pytest.raises(ProductError):
        validate_confirm_request(draft, confirmation(draft))
    lease = await renew_exact_draft(
        sessions, draft.draft_id, renewal_request(draft), idempotency_key="renew-1"
    )
    assert lease.expires_at - lease.authorized_at == DRAFT_EXPIRY
    assert lease.previous_expires_at == draft.expires_at
    replay = await renew_exact_draft(
        sessions, draft.draft_id, renewal_request(draft), idempotency_key="renew-1"
    )
    assert replay == lease
    async with sessions() as session:
        record = await load_record(session, draft.draft_id)
        from src.infrastructure.database.phase4_product import SQLAlchemyPhase4AdmissionRepository

        confirmation_record = await SQLAlchemyPhase4AdmissionRepository(
            session
        ).get_draft_for_update(draft.draft_id)
        assert confirmation_record == record
        assert record.draft == draft and not record.consumed
        validate_confirm_request(record, confirmation(draft))
        with pytest.raises(ProductError):
            validate_confirm_request(record, confirmation(draft), now=lease.expires_at)
        rows = list((await session.scalars(select(DraftLeaseAuthorizationRow))).all())
        assert len(rows) == 1
    first = await read_exact_draft(sessions, draft.draft_id)
    reopened = await read_exact_draft(sessions, draft.draft_id)
    assert first == reopened and first.draft == draft and first.lease_valid
    assert first.effective_expires_at == lease.expires_at


@pytest.mark.parametrize(
    "field,value",
    [
        ("draft_hash", "sha256:" + "0" * 64),
        ("scheme_id", "SCHEME-OTHER"),
        ("research_object_id", "OBJ-OTHER"),
        ("base_run_id", "RUN-OTHER"),
        ("base_research_view_version", "RVV-OTHER"),
        ("previous_expires_at", datetime(2020, 1, 1, tzinfo=UTC)),
    ],
)
async def test_wrong_identity_or_predecessor_rejected(database, field, value):
    sessions, draft = database
    with pytest.raises(ProductError):
        await renew_exact_draft(
            sessions,
            draft.draft_id,
            renewal_request(draft).model_copy(update={field: value}),
            idempotency_key="bad",
        )


async def test_wrong_draft_rejected(database):
    sessions, draft = database
    with pytest.raises(ProductError):
        await renew_exact_draft(
            sessions, "DRAFT-OTHER", renewal_request(draft), idempotency_key="bad"
        )


async def test_consumed_rejected(database):
    sessions, draft = database
    async with sessions() as session, session.begin():
        row = await session.get(ResearchRunDraftRow, draft.draft_id)
        row.consumed_at, row.consumed_admission_id, row.consumed_run_id = (
            datetime.now(UTC),
            "ADM-A",
            "RUN-A",
        )
    with pytest.raises(ProductError):
        await renew_exact_draft(
            sessions, draft.draft_id, renewal_request(draft), idempotency_key="bad"
        )


async def test_active_lease_cannot_be_extended(database):
    sessions, draft = database
    lease = await renew_exact_draft(
        sessions, draft.draft_id, renewal_request(draft), idempotency_key="first"
    )
    with pytest.raises(ProductError):
        await renew_exact_draft(
            sessions,
            draft.draft_id,
            renewal_request(draft).model_copy(update={"previous_expires_at": lease.expires_at}),
            idempotency_key="second",
        )


async def test_audit_is_append_only(database):
    sessions, draft = database
    lease = await renew_exact_draft(
        sessions, draft.draft_id, renewal_request(draft), idempotency_key="first"
    )
    with pytest.raises(DBAPIError):
        async with sessions() as session, session.begin():
            row = await session.get(DraftLeaseAuthorizationRow, lease.lease_id)
            row.payload = {}
    with pytest.raises(DBAPIError):
        async with sessions() as session, session.begin():
            row = await session.get(DraftLeaseAuthorizationRow, lease.lease_id)
            await session.delete(row)


def test_no_model_graph_or_admission_dependencies():
    import inspect

    import src.infrastructure.database.draft_leases as module

    source = inspect.getsource(module)
    assert all(
        word not in source
        for word in (
            "complete_structured",
            "prepare_run(",
            "confirm_run(",
            "planner.plan(",
            "ResearchRunAggregateRow",
        )
    )


async def test_product_api_exact_read_renew_and_reopen(database):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from src.application.service import ResearchApplicationService
    from src.phase4_product.api import create_phase4_product_router, install_phase4_error_handlers
    from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

    sessions, draft = database
    app = FastAPI()
    app.state.phase4_product_backend = PostgreSQLPhase4ProductBackend(
        sessions=sessions, service=ResearchApplicationService()
    )
    install_phase4_error_handlers(app)
    app.include_router(create_phase4_product_router())
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1", "Idempotency-Key": "api-renew"}
    path = "/api/research-drafts/" + draft.draft_id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        expired = await client.get(path, headers=headers)
        assert expired.status_code == 200 and not expired.json()["lease_valid"]
        result = await client.post(
            path + "/lease-renewals",
            headers=headers,
            json=renewal_request(draft).model_dump(mode="json"),
        )
        assert result.status_code == 200
        for _ in range(2):
            reviewed = await client.get(path, headers=headers)
            assert reviewed.status_code == 200 and reviewed.json()["lease_valid"]
            assert reviewed.json()["draft"] == expired.json()["draft"]
        bad = renewal_request(draft).model_dump(mode="json") | {"system_prompt": "not-allowed"}
        rejected = await client.post(path + "/lease-renewals", headers=headers, json=bad)
        assert rejected.status_code == 422


async def test_corrupt_draft_fails_closed(database):
    sessions, draft = database
    async with sessions() as session, session.begin():
        row = await session.get(ResearchRunDraftRow, draft.draft_id)
        row.payload = row.payload | {"draft_hash": "sha256:" + "0" * 64}
    with pytest.raises(ProductError):
        await renew_exact_draft(
            sessions, draft.draft_id, renewal_request(draft), idempotency_key="bad"
        )
