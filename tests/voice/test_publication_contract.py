"""Offline checks for publication-only integration; no provider or RTC calls."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.adapters.voice_candidate_profile import qwen_credentials
from src.application.errors import ApplicationError
from src.application.voice_sessions import VoiceSessions
from src.application.voice_skill import load


def test_public_template_pins_the_tested_skill_without_enabling_execution():
    profile = json.loads(Path('examples/voice/profile.example.json').read_text())
    assert load(profile['communication_skill'])['sha256'] == profile['communication_skill']['sha256']
    assert 'limits' not in profile and 'state' not in profile
    assert profile['automatic_retries'] == 0
    assert profile['llm_calls_per_turn'] == 2


def test_private_reference_cannot_escape_selected_private_root(tmp_path, monkeypatch):
    import src.adapters.voice_candidate_profile as factory
    monkeypatch.setattr(factory, 'PRIVATE_ROOT', tmp_path / 'private')
    with pytest.raises(ValueError, match='PRIVATE_CONFIG_UNSUPPORTED'):
        qwen_credentials({'credential_references': {'qwen': str(tmp_path / 'outside.json')}})


@pytest.mark.asyncio
async def test_missing_business_binding_is_explicit_not_a_fake_receipt():
    async def authorize(*args):
        return None
    control = VoiceSessions.__new__(VoiceSessions)
    control.app = SimpleNamespace(state=SimpleNamespace(voice_task_authorizer=authorize))
    with pytest.raises(ApplicationError) as caught:
        await control.bind('session', 'user', 'task', None)
    assert caught.value.code == 'VOICE_BUSINESS_PORT_UNAVAILABLE'
    assert caught.value.status_code == 503
