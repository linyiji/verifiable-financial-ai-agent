"""Append-only, explicit authorization renewal; never changes an immutable draft."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, mapped_column

from src.application.persistence import ResearchRunDraftRow
from src.infrastructure.database.base import Base
from src.phase4_product.admission import (
    DRAFT_EXPIRY,
    DraftLeaseAuthorizationV1,
    ResearchRunDraftRecordV1,
    draft_hash_is_valid,
)
from src.phase4_product.contracts import ResearchRunDraftV1
from src.phase4_product.errors import product_error
from src.phase4_product.hashing import canonical_json_sha256


class DraftLeaseAuthorizationRow(Base):
    __tablename__ = "draft_lease_authorizations"

    lease_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    draft_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("research_run_drafts.draft_id"), index=True
    )
    request_hash: Mapped[str] = mapped_column(String(128))
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)


async def latest_lease(session, draft_id):
    row = await session.scalar(
        select(DraftLeaseAuthorizationRow)
        .where(DraftLeaseAuthorizationRow.draft_id == draft_id)
        .order_by(DraftLeaseAuthorizationRow.authorized_at.desc())
        .limit(1)
    )
    return DraftLeaseAuthorizationV1.model_validate(row.payload) if row else None


async def load_record(session, draft_id, *, lock=False):
    query = select(ResearchRunDraftRow).where(ResearchRunDraftRow.draft_id == draft_id)
    row = await session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise product_error("NOT_FOUND", "exact research draft not found")
    draft = ResearchRunDraftV1.model_validate(row.payload)
    if not draft_hash_is_valid(draft):
        raise product_error("INTEGRITY_FAILURE", "draft hash integrity failure")
    return ResearchRunDraftRecordV1(
        draft=draft,
        consumed_at=row.consumed_at,
        consumed_admission_id=row.consumed_admission_id,
        consumed_run_id=row.consumed_run_id,
        lease_authorization=await latest_lease(session, draft_id),
    )


async def renew_exact_draft(sessions, draft_id, request, *, idempotency_key):
    """Serialize with confirmation on the same draft row. Replay never extends time."""
    fingerprint = canonical_json_sha256(request.model_dump(mode="json"))
    lease_id = (
        "LEASE-"
        + canonical_json_sha256({"draft_id": draft_id, "idempotency_key": idempotency_key}).split(
            ":", 1
        )[1]
    )
    async with sessions() as session, session.begin():
        record = await load_record(session, draft_id, lock=True)
        draft = record.draft
        context = draft.scheme_snapshot.incremental_context
        if context is None or (
            request.draft_hash,
            request.scheme_id,
            request.research_object_id,
            request.base_run_id,
            request.base_research_view_version,
        ) != (
            draft.draft_hash,
            draft.scheme_snapshot.scheme_id,
            draft.object_id,
            context.base_run_id,
            context.base_research_view_version,
        ):
            raise product_error("CONFLICT", "renewal requires exact draft and base identity")
        if record.consumed:
            raise product_error("CONFLICT", "consumed draft cannot be renewed")
        existing = await session.get(DraftLeaseAuthorizationRow, lease_id)
        if existing:
            if existing.request_hash != fingerprint:
                raise product_error("CONFLICT", "renewal replay request mismatch")
            return DraftLeaseAuthorizationV1.model_validate(existing.payload)
        now = datetime.now(UTC)
        if request.previous_expires_at != record.effective_expires_at:
            raise product_error("CONFLICT", "renewal predecessor mismatch")
        if now < record.effective_expires_at:
            raise product_error("CONFLICT", "draft authorization has not expired")
        lease = DraftLeaseAuthorizationV1(
            lease_id=lease_id,
            draft_id=draft_id,
            draft_hash=draft.draft_hash,
            scheme_id=request.scheme_id,
            base_run_id=request.base_run_id,
            base_research_view_version=request.base_research_view_version,
            previous_expires_at=record.effective_expires_at,
            authorized_at=now,
            expires_at=now + DRAFT_EXPIRY,
        )
        session.add(
            DraftLeaseAuthorizationRow(
                lease_id=lease_id,
                draft_id=draft_id,
                request_hash=fingerprint,
                authorized_at=now,
                payload=lease.model_dump(mode="json"),
            )
        )
        return lease
