"""Operator-selected self-test node factories, never a product default route."""
import json
import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import SecretStr

from src.infrastructure.config.settings import VoiceLLMSettings


PRIVATE_ROOT=Path(os.getenv('VEFIN_VOICE_PRIVATE_CONFIG_DIR', str(Path.home()/'.config/vefin'))).expanduser().resolve()

def qwen_credentials(profile):
    ref=profile.get('credential_references',{}).get('qwen',str(PRIVATE_ROOT/'asr-eval/candidates-20261024-214423-988696.json'))
    path=Path(ref).expanduser().resolve()
    if not path.is_relative_to(PRIVATE_ROOT):raise ValueError('ASR_PRIVATE_CONFIG_UNSUPPORTED')
    return path,json.loads(path.read_text())['providers']['qwen']


def validate_profile(profile):
    """Reject unsupported contracts before reading credentials or calling a model."""
    if profile.get('communication_revision') not in (None, 'voice.communication.v1', 'voice.communication.v2'):
        raise ValueError('COMMUNICATION_CONTRACT_UNSUPPORTED')
    if profile.get('communication_revision') and profile.get('instruction_revision') != 'procedure-provenance-v3-consultation-v1':
        raise ValueError('COMMUNICATION_REQUIRES_CONSULTATION_SCOPE')
    if profile.get('isolation') != 'SELF_TEST_ONLY_NOT_PRODUCT_DEFAULT':
        raise ValueError('EXPLICIT_TEST_PROFILE_REQUIRED')
    if profile.get('max_tokens', 256) != 256 or profile.get('json_mode', True) is not True:
        raise ValueError('PRODUCT_LLM_CONTRACT_UNSUPPORTED')
    if profile.get('automatic_retries', 0) != 0:
        raise ValueError('AUTOMATIC_RETRY_UNSUPPORTED')
    if profile.get('model_deadline_seconds', 5) > 5 or profile.get('dialogue_deadline_seconds', 8) > 8:
        raise ValueError('PRODUCT_LLM_BUDGET_EXCEEDED')
    if profile.get('turn_deadline_seconds', 120) <= 0 or profile.get('turn_deadline_seconds', 120) > 120:
        raise ValueError('PRODUCT_TURN_BUDGET_UNSUPPORTED')
    if profile.get("communication_skill"):
        from src.application.voice_skill import load
        load(profile["communication_skill"])
    return profile


def candidate_node(profile,node,*,client=None,llm_id=None,observer=None,audio_observer=None,audio_reuse=None):
    validate_profile(profile)
    if node=='asr':
        from src.adapters.speech import candidate_speech_recognizer
        from src.adapters.candidate_asr import ASRTestBudget
        from src.adapters.voice_call_budget import charge
        config=profile['nodes']['asr'];allowed,private=qwen_credentials(profile)
        if Path(config['configuration_file']).expanduser().resolve()!=allowed:raise ValueError('ASR_PRIVATE_CONFIG_UNSUPPORTED')
        if (config['provider'],config['model'],config['region'])!=('qwen',private['model'],private['region']):
            raise ValueError('ASR_PROFILE_MISMATCH')
        return candidate_speech_recognizer('qwen',private,observer=observer,
            budget=ASRTestBudget(connect_seconds=5,file_total_seconds=12),
            on_attempt=lambda:charge('ASR','qwen',config['model']),
            wire_format=config.get('wire_format','opus'),wire_bitrate=config.get('wire_bitrate',16000))
    if node=='llm':
        from src.adapters.voice_dialogue_model import configured_voice_dialogue_model
        config=next(x for x in profile['nodes']['llm'] if x['id']==llm_id)
        if config['provider'] not in {'qwen_beijing', 'mimo_official', 'deepseek_official'}:
            raise ValueError('LLM_PROVIDER_CAPABILITY_UNSUPPORTED')
        if config['provider']=='qwen_beijing':
            key=qwen_credentials(profile)[1]['api_key']
        else:
            name,field=('mimo.env','MIMO_API_KEY') if config['provider']=='mimo_official' else ('deepseek.env','DEEPSEEK_API_KEY')
            key=dotenv_values(PRIVATE_ROOT/name)[field]
        settings=VoiceLLMSettings(provider=config['provider'],model=config['model'],base_url=config['base_url'],
            api_key=SecretStr(key),model_deadline_seconds=profile.get('model_deadline_seconds',5),
            dialogue_deadline_seconds=profile.get('dialogue_deadline_seconds',8))
        return configured_voice_dialogue_model(settings,client,observer=observer)
    if node=='tts':
        from src.adapters.voice_output import VoiceOutput
        config=dict(profile['nodes']['tts'])
        config['api_key']=qwen_credentials(profile)[1]['api_key']
        return VoiceOutput(configuration=config,observer=observer,audio_observer=audio_observer,audio_reuse=audio_reuse)
    raise ValueError('VOICE_NODE_UNSUPPORTED')
