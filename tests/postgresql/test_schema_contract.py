import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint

from src.application import persistence as application_persistence  # noqa: F401
from src.data import persistence as data_persistence  # noqa: F401
from src.infrastructure.config.settings import DatabaseSettings
from src.infrastructure.database import models as durable_models  # noqa: F401
from src.infrastructure.database.base import Base
from src.infrastructure.database.composition import create_postgresql_persistence
from src.infrastructure.database.migrations import upgrade_postgresql_database
from src.infrastructure.database.postgresql_events import (
    POSTGRES_EVENT_SEQUENCE_FUNCTION_SQL,
    POSTGRES_EVENT_SEQUENCE_TRIGGER_SQL,
)


def test_durable_metadata_contains_every_required_record_table() -> None:
    assert {
        "research_objects",
        "research_runs",
        "tasks",
        "task_dependencies",
        "runtime_events",
        "evidence_records",
        "calculation_records",
        "correction_records",
        "replan_records",
        "review_records",
        "canonical_execution_records",
        "released_research_results",
        "runtime_checkpoints",
        "runtime_event_counters",
        "capability_gap_records",
        "capability_build_records",
        "generated_capability_records",
        "generated_capability_artifact_records",
        "sandbox_execution_records",
        "capability_validation_records",
        "scoped_capability_registrations",
        "proof_policy_decisions",
        "proof_input_commitments",
        "proof_records",
        "proof_artifact_references",
        "proof_verification_records",
        "report_artifact_records",
    } <= set(Base.metadata.tables)


def test_runtime_event_metadata_and_trigger_enforce_sequence_contract() -> None:
    table = Base.metadata.tables["runtime_events"]
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    checks = {
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert ("run_id", "sequence") in unique_columns
    assert "sequence > 0" in checks
    assert "ON CONFLICT (run_id) DO UPDATE" in POSTGRES_EVENT_SEQUENCE_FUNCTION_SQL
    assert "last_sequence = runtime_event_counters.last_sequence + 1" in (
        POSTGRES_EVENT_SEQUENCE_FUNCTION_SQL
    )
    assert "last_sequence = NEW.sequence - 1" in POSTGRES_EVENT_SEQUENCE_FUNCTION_SQL
    assert "BEFORE INSERT ON runtime_events" in POSTGRES_EVENT_SEQUENCE_TRIGGER_SQL


def test_postgresql_composition_and_migrations_reject_non_postgresql_urls() -> None:
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")

    with pytest.raises(ValueError, match="PostgreSQL persistence"):
        create_postgresql_persistence(settings)
    with pytest.raises(ValueError, match="PostgreSQL migrations"):
        upgrade_postgresql_database(settings)


def test_task_dependency_metadata_separates_planned_and_actual_edges() -> None:
    table = Base.metadata.tables["task_dependencies"]
    checks = {
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "graph_kind IN ('PLANNED', 'ACTUAL')" in checks
    assert "task_id <> dependency_task_id" in checks
    assert ("run_id", "graph_kind", "task_id", "position") in unique_columns


def test_generated_artifact_metadata_enforces_required_content_bindings() -> None:
    table = Base.metadata.tables["generated_capability_artifact_records"]
    assert {
        "build_id",
        "run_id",
        "generated_capability_id",
        "capability_id",
        "capability_version",
        "source_artifact_id",
        "source_artifact_ref",
        "source_sha256",
        "source_size_bytes",
        "test_artifact_id",
        "test_artifact_ref",
        "test_sha256",
        "test_size_bytes",
        "implementation_hash",
        "runtime_image_identity",
        "created_at",
    } <= set(table.columns.keys())
    checks = {
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "source_artifact_id = source_sha256" in checks
    assert "test_artifact_id = test_sha256" in checks
    assert "implementation_hash = source_sha256" in checks
