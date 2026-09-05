from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.config import Settings, load_numbered_fmp_credentials


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
                "MIMO_API_KEY=mimo-test-secret",
                "MIMO_BASE_URL=https://api.xiaomimimo.com/v1",
                "MIMO_DATA_MODEL=mimo-v2.5",
                "MIMO_CHAT_MODEL=mimo-v2.5",
                "PLANNER_PREFERRED_PROVIDER=mimo",
                "PLANNER_FALLBACK_PROVIDERS=teamorouter",
            )
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=(base, local))

    assert settings.fmp.enabled is True
    assert len(settings.fmp.credentials) == 1
    assert settings.llm.enabled is True
    assert settings.llm.provider == "teamorouter"
    assert settings.llm.primary_model == "gpt-5.6-sol"
    assert settings.mimo.enabled is True
    assert settings.mimo.provider == "mimo"
    assert settings.mimo.primary_model == "mimo-v2.5"
    assert settings.planner_provider_order == ("mimo", "teamorouter")
    assert "fmp-test-secret" not in repr(settings)
    assert "router-test-secret" not in repr(settings)
    assert "fmp-test-secret" not in str(settings.safe_summary())
    assert "router-test-secret" not in str(settings.safe_summary())
    assert "mimo-test-secret" not in repr(settings)
    assert "mimo-test-secret" not in str(settings.safe_summary())


def test_safe_summary_contains_numbered_pool_presence_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FMP_API_KEY_1", "secret-a")
    monkeypatch.setenv("FMP_API_KEY_2", "secret-d")
    settings = Settings(
        fmp_api_key="legacy-secret",
        teamorouter_api_key="secret-b",
        mimo_api_key="secret-c",
        _env_file=None,
    )

    assert settings.safe_summary()["fmp_api_key_is_set"] is True
    assert settings.safe_summary()["fmp_key_pool_size"] == 2
    assert settings.safe_summary()["teamorouter_api_key_is_set"] is True
    assert settings.safe_summary()["mimo_api_key_is_set"] is True
    assert "secret-a" not in str(settings.safe_summary())
    assert "secret-d" not in repr(settings.fmp)
    assert "secret-d" not in str(settings.safe_summary())
    assert "legacy-secret" not in repr(settings)
    assert "secret-b" not in str(settings.safe_summary())
    assert "secret-c" not in str(settings.safe_summary())


def test_numbered_fmp_pool_requires_contiguous_distinct_slots() -> None:
    credentials = load_numbered_fmp_credentials(
        {"FMP_API_KEY_1": "secret-a", "FMP_API_KEY_2": "secret-b"}
    )
    assert [secret.get_secret_value() for secret in credentials] == ["secret-a", "secret-b"]

    with pytest.raises(ValueError, match="contiguous"):
        load_numbered_fmp_credentials({"FMP_API_KEY_1": "secret-a", "FMP_API_KEY_3": "secret-c"})
    with pytest.raises(ValueError, match="distinct"):
        load_numbered_fmp_credentials({"FMP_API_KEY_1": "secret-a", "FMP_API_KEY_2": "secret-a"})


def test_unknown_planner_provider_policy_fails_closed() -> None:
    settings = Settings(
        planner_preferred_provider="unknown",
        _env_file=None,
    )

    with pytest.raises(ValueError, match="unsupported provider"):
        _ = settings.planner_provider_order
