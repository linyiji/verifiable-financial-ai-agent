"""Consistent SQLite connection settings; PostgreSQL configuration is untouched."""

from sqlalchemy import event
from sqlalchemy.engine import Engine

SQLITE_BUSY_TIMEOUT_MS = 30_000


def configure_sqlite(engine: Engine, *, busy_timeout_ms: int = SQLITE_BUSY_TIMEOUT_MS) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def configure_connection(connection, _record):
        cursor = connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
            # WAL allows short readers while the sole SQLite writer commits.
            # In-memory SQLite keeps its supported journal mode.
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()
