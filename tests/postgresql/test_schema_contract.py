from sqlalchemy import CheckConstraint, UniqueConstraint

from src.application import persistence as application_persistence  # noqa: F401
from src.data import persistence as data_persistence  # noqa: F401
from src.infrastructure.database import models as durable_models  # noqa: F401
from src.infrastructure.database.base import Base
from src.infrastructure.database.postgresql_events import (
    POSTGRES_EVENT_SEQUENCE_FUNCTION_SQL,
    POSTGRES_EVENT_SEQUENCE_TRIGGER_SQL,
)


def test_durable_metadata_contains_every_required_record_table() -> None:
    assert {
        "research_objects",
        "research_runs",
        "tasks",
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
