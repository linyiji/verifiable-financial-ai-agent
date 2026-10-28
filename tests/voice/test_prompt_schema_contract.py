"""Request-contract regressions only; MockTransport is not provider acceptance."""
import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from src.adapters.llm.provider import LLMMessage
from src.adapters.voice_dialogue_model import DeepSeekVoiceDialogueModel
from src.application.voice_dialogue import DialogueReply
from src.application.voice_dispatcher import CVCAnswer
from src.infrastructure.config.settings import VoiceLLMSettings


@pytest.mark.parametrize('schema,kind,allowed', [
    (CVCAnswer, 'conversation', {'conversation', 'clarification'}),
    (DialogueReply, 'progress', {
        'conversation', 'clarification', 'progress', 'business_action_request',
    }),
])
def test_endpoint_hint_retains_product_intents(schema, kind, allowed):
    def respond(request):
        body = json.loads(request.content)
        instruction = body['messages'][0]['content']
        actual = set(instruction.split('kind只能是')[1].split('之一')[0].split('、'))
        assert actual == allowed
        assert body['max_tokens'] == 256
        assert body['response_format'] == {'type': 'json_object'}
        return httpx.Response(200, json={
            'model': 'deepseek-flash', 'choices': [{'finish_reason': 'stop',
                'message': {'content': json.dumps({
                    'kind': kind, 'text': 'synthetic contract reply',
                })}}],
        })

    async def run():
        settings = VoiceLLMSettings(
            provider='deepseek_official', api_key=SecretStr('contract-test-only'),
            base_url='https://contract.invalid', model='deepseek-flash', model_deadline_seconds=5,
            dialogue_deadline_seconds=8)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await DeepSeekVoiceDialogueModel(settings, client).complete_structured(
                messages=[LLMMessage(role='system', content='synthetic contract request')],
                response_model=schema, schema_name='contract')
            assert result.output.kind == kind

    asyncio.run(run())
