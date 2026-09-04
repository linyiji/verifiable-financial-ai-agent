from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from src.infrastructure.config.settings import DatabaseSettings


def upgrade_postgresql_database(
    settings: DatabaseSettings,
    *,
    revision: str = "head",
    script_location: Path | None = None,
) -> None:
    """Run Alembic with an injected URL without logging or persisting credentials."""

    url = make_url(settings.url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL migrations require a PostgreSQL database URL")
    location = script_location or Path(__file__).resolve().parents[3] / "alembic"
    config = Config()
    config.set_main_option("script_location", str(location))
    config.set_main_option("sqlalchemy.url", settings.url.replace("%", "%%"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"migration graph must have exactly one head; found {len(heads)}")
    command.upgrade(config, revision)
