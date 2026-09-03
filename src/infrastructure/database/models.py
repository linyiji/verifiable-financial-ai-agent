"""Durable row models not already owned by Phase-1 application/data persistence."""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Integer, String, UniqueConstraint
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


class TaskDependencyRow(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "graph_kind",
            "task_id",
            "position",
            name="uq_task_dependencies_position",
        ),
        CheckConstraint(
            "graph_kind IN ('PLANNED', 'ACTUAL')",
            name="ck_task_dependencies_graph_kind",
        ),
        CheckConstraint("position >= 0", name="ck_task_dependencies_position"),
        CheckConstraint(
            "task_id <> dependency_task_id",
            name="ck_task_dependencies_not_self",
        ),
    )

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    graph_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    dependency_task_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
