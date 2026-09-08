"""BYOK composition only: no network, credentials, database or provider calls."""
import pytest

from src.adapters.llm.routes import configured_incremental_provider, load_mimo_authority
from src.infrastructure.config.settings import Settings


def settings(**changes):
    return Settings(_env_file=None, mimo_api_key="fixture-only-secret", **changes)


def test_byok_settings_construct_direct_route_without_private_path():
    provider = configured_incremental_provider(settings(), route_id="mimo-direct")
    assert provider.model_name == "mimo-v2.5"
    assert provider.provider_name == "mimo"


def test_explicit_external_file_remains_supported(tmp_path):
    authority = tmp_path / "authority.env"
    authority.write_text("MIMO_API_KEY=fixture-only-secret\n"
                         "MIMO_BASE_URL=https://api.xiaomimimo.com/v1\n"
                         "MIMO_CHAT_MODEL=mimo-v2.5-pro\n")
    config = load_mimo_authority(settings=settings(mimo_authority_file=str(authority)))
    assert config.primary_model == "mimo-v2.5-pro"


@pytest.mark.parametrize("changes", [
    {"mimo_api_key": None},
    {"mimo_base_url": "https://unregistered.invalid/v1"},
    {"mimo_chat_model": "unregistered-model"},
])
def test_byok_authority_still_fails_closed(changes):
    configured = Settings(_env_file=None, **{"mimo_api_key": "fixture-only-secret", **changes})
    with pytest.raises(ValueError):
        load_mimo_authority(settings=configured)
