"""Apply the repository Alembic chain using Unified Settings."""

from src.infrastructure.config.settings import get_settings
from src.infrastructure.database.migrations import upgrade_postgresql_database


def main() -> None:
    upgrade_postgresql_database(get_settings().database)
    print("PostgreSQL migration completed")


if __name__ == "__main__":
    main()
