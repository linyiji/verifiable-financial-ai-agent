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


class CapabilityGapRecordRow(Base):
    __tablename__ = "capability_gap_records"

    gap_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class CapabilityBuildRecordRow(Base):
    __tablename__ = "capability_build_records"

    build_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class GeneratedCapabilityRecordRow(Base):
    __tablename__ = "generated_capability_records"

    generated_capability_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class SandboxExecutionRecordRow(Base):
    __tablename__ = "sandbox_execution_records"

    execution_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class CapabilityValidationRecordRow(Base):
    __tablename__ = "capability_validation_records"

    validation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ScopedCapabilityRegistrationRow(Base):
    __tablename__ = "scoped_capability_registrations"

    registration_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ProofPolicyDecisionRow(Base):
    __tablename__ = "proof_policy_decisions"

    decision_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ProofInputCommitmentRow(Base):
    __tablename__ = "proof_input_commitments"

    commitment_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ProofRecordRow(Base):
    __tablename__ = "proof_records"

    proof_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ProofArtifactReferenceRow(Base):
    __tablename__ = "proof_artifact_references"

    artifact_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ProofVerificationRecordRow(Base):
    __tablename__ = "proof_verification_records"

    verification_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ReportArtifactRecordRow(Base):
    __tablename__ = "report_artifact_records"

    artifact_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
