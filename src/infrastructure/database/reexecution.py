"""One-shot authorization, distinct from the immutable consumed research draft."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base


class ReexecutionAuthorizationRow(Base):
    __tablename__ = "reexecution_authorizations"

    authorization_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    prior_run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.run_id"), index=True)
    key_digest: Mapped[str] = mapped_column(String(128), unique=True)
    request_hash: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON)
    consumed_by_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_runs.run_id"), unique=True, nullable=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admission_key_digest: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True
    )
    admission_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
