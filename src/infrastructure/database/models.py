"""Durable row models not already owned by Phase-1 application/data persistence."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base


class CorrectionRecordRow(Base):
    __tablename__ = "correction_records"

    correction_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ReplanRecordRow(Base):
    __tablename__ = "replan_records"

    replan_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class RuntimeCheckpointRow(Base):
    __tablename__ = "runtime_checkpoints"
    __table_args__ = (UniqueConstraint("run_id", "checkpoint_id"),)

    checkpoint_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class RuntimeEventCounterRow(Base):
    __tablename__ = "runtime_event_counters"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
