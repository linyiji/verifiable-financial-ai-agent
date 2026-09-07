"""Exact retained draft review; lease metadata stays outside its immutable payload."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from src.phase4_product.contracts import ResearchRunDraftV1


class RenewDraftLeaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    research_object_id: str
    draft_hash: str
    scheme_id: str
    base_run_id: str
    base_research_view_version: str
    previous_expires_at: datetime


class ExactDraftReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    draft: ResearchRunDraftV1
    effective_expires_at: datetime
    lease_id: str | None
    consumed: bool
    lease_valid: bool


async def read_exact_draft(sessions, draft_id):
    from src.infrastructure.database.draft_leases import load_record

    async with sessions() as session:
        record = await load_record(session, draft_id)
        return ExactDraftReview(
            draft=record.draft,
            effective_expires_at=record.effective_expires_at,
            lease_id=record.lease_authorization.lease_id if record.lease_authorization else None,
            consumed=record.consumed,
            lease_valid=not record.consumed and datetime.now(UTC) < record.effective_expires_at,
        )
