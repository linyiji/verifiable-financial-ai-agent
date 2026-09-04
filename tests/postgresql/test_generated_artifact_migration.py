from io import StringIO
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command


def _render_upgrade(revision: str) -> str:
    output = StringIO()
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[2] / "alembic"),
    )
    config.set_main_option("sqlalchemy.url", "postgresql://audit:test@localhost/vfas")
    config.output_buffer = output
    command.upgrade(config, revision, sql=True)
    return output.getvalue()


def test_fresh_postgresql_upgrade_includes_generated_artifact_retention() -> None:
    sql = _render_upgrade("head")

    assert "CREATE TABLE generated_capability_artifact_records" in sql
    assert "ck_generated_implementation_binding" in sql
    assert "20260904_0006" in sql


def test_existing_0005_upgrade_has_one_forward_only_0006_step() -> None:
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[2] / "alembic"),
    )
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["20260904_0006"]
    assert scripts.get_revision("20260904_0006").down_revision == "20260904_0005"

    sql = _render_upgrade("20260904_0005:20260904_0006")
    assert sql.count("CREATE TABLE generated_capability_artifact_records") == 1
    assert "CREATE TABLE research_runs" not in sql
    assert "20260904_0006" in sql
