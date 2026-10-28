"""Voice state is independent of Task/Run lifetime and research record formats."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class VoiceBase(DeclarativeBase):
    pass


class VoiceSessionRow(VoiceBase):
    __tablename__ = "voice_sessions"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(256), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    room: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    task_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    chat_session_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    event_cursor: Mapped[int] = mapped_column(Integer, default=0)
    ended_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    warned: Mapped[int] = mapped_column(Integer, default=0)
    lease_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceEventRow(VoiceBase):
    __tablename__ = "voice_events"
    __table_args__ = (UniqueConstraint("session_id", "event_id"),)

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cursor: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(256))
    payload: Mapped[dict] = mapped_column(JSON)
    consumed: Mapped[int] = mapped_column(Integer, default=0)
