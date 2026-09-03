from __future__ import annotations

from pathlib import Path

from src.infrastructure.config import Settings


def test_unified_settings_load_env_local_and_redact_secrets(tmp_path: Path) -> None:
    base = tmp_path / ".env"
    local = tmp_path / ".env.local"
    base.write_text("LLM_PROVIDER=base-provider\n", encoding="utf-8")
    local.write_text(
        "\n".join(
            (
                "FMP_API_KEY=fmp-test-secret",
                "TEAMOROUTER_API_KEY=router-test-secret",
                "LLM_PROVIDER=teamorouter",
                "TEAMOROUTER_BASE_URL=https://api.teamorouter.com/v1",
                "TEAMOROUTER_MODEL=gpt-5.6-sol",
                "TEAMOROUTER_FALLBACK_MODEL=gpt-5.6-luna",
            )
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=(base, local))

    assert settings.fmp.enabled is True
    assert settings.llm.enabled is True
    assert settings.llm.provider == "teamorouter"
    assert settings.llm.primary_model == "gpt-5.6-sol"
    assert "fmp-test-secret" not in repr(settings)
    assert "router-test-secret" not in repr(settings)
    assert "fmp-test-secret" not in str(settings.safe_summary())
    assert "router-test-secret" not in str(settings.safe_summary())


def test_safe_summary_contains_presence_only() -> None:
    settings = Settings(
        fmp_api_key="secret-a",
        teamorouter_api_key="secret-b",
        _env_file=None,
    )

    assert settings.safe_summary()["fmp_api_key_is_set"] is True
    assert settings.safe_summary()["teamorouter_api_key_is_set"] is True
    assert "secret-a" not in str(settings.safe_summary())
    assert "secret-b" not in str(settings.safe_summary())
