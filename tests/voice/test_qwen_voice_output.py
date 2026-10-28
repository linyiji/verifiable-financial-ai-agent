import asyncio
import base64
import json
from contextlib import asynccontextmanager

import pytest

from src.adapters.qwen_voice_output import QwenRealtimeVoiceOutput


def config():
    return {'provider':'qwen_beijing','model':'qwen3-tts-flash-realtime','voice':'Kiki',
        'language_type':'Auto','sample_rate':16000,'completion_seconds':20,'connect_seconds':5,'api_key':'offline-secret'}


class Socket:
    def __init__(self):self.messages=asyncio.Queue();self.sent=[];self.closed=False
    async def send(self,raw):
        obj=json.loads(raw);self.sent.append(obj)
        if obj['type']=='session.update':
            assert 'instructions' not in obj['session'] and obj['session']['language_type']=='Auto'
            await self.messages.put({'type':'session.updated','session':obj['session']})
        if obj['type']=='input_text_buffer.commit':
            pcm=b'\x00\x00'*16+b'\x00\x20'*200
            for c in [pcm[:3],pcm[3:]]:await self.messages.put({'type':'response.audio.delta','delta':base64.b64encode(c).decode()})
            await self.messages.put({'type':'response.audio.done'})
            await self.messages.put({'type':'response.done','response':{'status':'completed','usage':{'characters':3},'id':'offline'}})
        if obj['type']=='session.finish':await self.messages.put({'type':'session.finished'})
    def __aiter__(self):return self
    async def __anext__(self):
        value=await self.messages.get();return json.dumps(value)


@pytest.mark.asyncio
async def test_real_pcm_contract_odd_chunk_boundary_and_completion():
    ws=Socket();captures=[]
    @asynccontextmanager
    async def connector(url,**kwargs):
        assert kwargs['proxy'] is None and kwargs['ssl'].check_hostname
        await ws.messages.put({'type':'session.created','session':{'id':'offline','model':'qwen3-tts-flash-realtime'}})
        try:yield ws
        finally:ws.closed=True
    adapter=QwenRealtimeVoiceOutput(config(),connector=connector,audio_observer=lambda raw,**meta:captures.append((raw,meta)))
    state={};received=[]
    async for pcm,rate in adapter.stream('測試。',language='yue-HK',state=state):received.append(pcm);assert rate==16000
    assert b''.join(received)==captures[0][0] and len(captures[0][0])==432
    assert state['provider_complete'] and state['complete'] and ws.closed
    assert state['first_audio_byte_ms']<=state['first_valid_pcm_ms']<=state['synthesis_complete_ms']


@pytest.mark.asyncio
async def test_cancel_closes_without_false_complete_or_retry():
    ws=Socket()
    @asynccontextmanager
    async def connector(url,**kwargs):
        try:yield ws
        finally:ws.closed=True
    adapter=QwenRealtimeVoiceOutput(config(),connector=connector);state={}
    async def consume():
        async for _ in adapter.stream('測試。',language='yue-HK',state=state):pass
    task=asyncio.create_task(consume());await asyncio.sleep(.01);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert state['cancelled'] and not state['provider_complete'] and not state.get('complete') and ws.closed


@pytest.mark.asyncio
async def test_explicit_replay_never_regenerates_missing_audio():
    from src.adapters.voice_output import VoiceOutput
    output=VoiceOutput(configuration={**config(),'replay_only':True},audio_reuse=lambda *_:None)
    with pytest.raises(RuntimeError,match='EXPLICIT_REPLAY_AUDIO_MISSING'):
        async for _ in output.stream('測試。',language='yue-HK'):pass
    await output.aclose()


def test_sealed_budget_cannot_charge(tmp_path,monkeypatch):
    from src.adapters.voice_call_budget import charge
    p=tmp_path/'ledger.json';p.write_text(json.dumps({'state':'CLOSED','limits':{'TTS':16,'TOTAL':58},'attempts':[]}))
    monkeypatch.setenv('VEFIN_VOICE_CALL_LEDGER',str(p))
    with pytest.raises(RuntimeError,match='VOICE_CALL_BUDGET_CLOSED'):charge('TTS','qwen_beijing','qwen3-tts-flash-realtime')
    assert json.loads(p.read_text())['attempts']==[]


class ReuseSocket(Socket):
    def __init__(self, wrong_id=False):
        super().__init__(); self.counter=0; self.wrong_id=wrong_id
    async def send(self, raw):
        obj=json.loads(raw)
        if obj['type']!='input_text_buffer.commit':
            await super().send(raw);return
        self.sent.append(obj);self.counter+=1;rid=f'response-{self.counter}';item=f'item-{self.counter}'
        # A delayed old response must never become the next segment's PCM.
        if self.counter>1:
            await self.messages.put({'type':'response.audio.delta','response_id':'response-1','item_id':'item-1',
                'delta':base64.b64encode(b'\xff\x7f'*32).decode()})
        await self.messages.put({'type':'response.created','response':{'id':rid}})
        await self.messages.put({'type':'response.audio.delta','response_id':'wrong' if self.wrong_id else rid,
            'item_id':item,'delta':base64.b64encode(b'\x00\x20'*200).decode()})
        await self.messages.put({'type':'response.audio.done','response_id':rid,'item_id':item})
        await self.messages.put({'type':'response.done','response':{'id':rid,'status':'completed','usage':{'characters':3}}})


@pytest.mark.asyncio
async def test_answer_session_reuse_single_reader_ids_and_late_audio():
    ws=ReuseSocket();opened=[];events=[];captures=[]
    @asynccontextmanager
    async def connector(url,**kwargs):
        opened.append(kwargs);assert kwargs['open_timeout']==5 and kwargs['proxy'] is None
        await ws.messages.put({'type':'session.created','session':{'id':'same-session','model':'qwen3-tts-flash-realtime'}})
        try:yield ws
        finally:ws.closed=True
    adapter=QwenRealtimeVoiceOutput({**config(),'reuse_session':True},connector=connector,
        observer=events.append,audio_observer=lambda data,**meta:captures.append(data))
    states=[];readers=[]
    for text in ['原第三段。','原第四段。']:
        state={};frames=[pcm async for pcm,_ in adapter.stream(text,language='yue-HK',state=state)]
        assert b''.join(frames)==b'\x00\x20'*200
        assert state['complete'] and state['provider_complete'];states.append(state);readers.append(adapter._reader)
    assert len(opened)==1 and readers[0] is readers[1] and not ws.closed
    assert [x['type'] for x in ws.sent].count('session.update')==1
    assert [x['type'] for x in ws.sent].count('input_text_buffer.commit')==2
    assert 'session.finish' not in [x['type'] for x in ws.sent]
    assert captures==[b'\x00\x20'*200]*2
    assert any(x['stage']=='stale_response_discarded' for x in events)
    assert states[0]['provider_request_id']!=states[1]['provider_request_id']
    await adapter.finish_response()
    assert ws.closed and adapter._reader is None and adapter.active is None
    assert [x['type'] for x in ws.sent].count('session.finish')==1
    await adapter.aclose()


@pytest.mark.asyncio
async def test_wrong_response_id_fails_and_closes_without_reconnect():
    ws=ReuseSocket(wrong_id=True);opened=[]
    @asynccontextmanager
    async def connector(url,**kwargs):
        opened.append(True)
        await ws.messages.put({'type':'session.created','session':{'id':'one','model':'qwen3-tts-flash-realtime'}})
        try:yield ws
        finally:ws.closed=True
    adapter=QwenRealtimeVoiceOutput({**config(),'reuse_session':True},connector=connector);state={}
    with pytest.raises(RuntimeError,match='RESPONSE_ID_MISMATCH'):
        async for _ in adapter.stream('測試。',language='yue-HK',state=state):pass
    assert len(opened)==1 and ws.closed and not state.get('complete') and not state['provider_complete']
    assert adapter._unusable and adapter._reader is None
    await adapter.aclose()


@pytest.mark.asyncio
async def test_cancel_after_pcm_closes_reusable_socket_and_no_false_delivery():
    ws=ReuseSocket()
    @asynccontextmanager
    async def connector(url,**kwargs):
        await ws.messages.put({'type':'session.created','session':{'id':'one','model':'qwen3-tts-flash-realtime'}})
        try:yield ws
        finally:ws.closed=True
    adapter=QwenRealtimeVoiceOutput({**config(),'reuse_session':True},connector=connector);state={}
    stream=adapter.stream('測試。',language='yue-HK',state=state)
    await anext(stream);await stream.aclose()
    assert not state.get('complete') and ws.closed and adapter._reader is None
    await adapter.aclose()


@pytest.mark.asyncio
async def test_connect_exception_phase_and_redaction_no_headers_dump():
    events=[]
    @asynccontextmanager
    async def connector(url,**kwargs):
        raise OSError('Authorization: Bearer offline-secret wss://user:pass@example.invalid/private')
        yield
    adapter=QwenRealtimeVoiceOutput({**config(),'reuse_session':True},connector=connector,observer=events.append);state={}
    with pytest.raises(OSError):
        async for _ in adapter.stream('測試。',language='yue-HK',state=state):pass
    diagnostic=next(x for x in events if x['stage']=='request_error')
    encoded=json.dumps(events)
    assert 'offline-secret' not in encoded and 'user:pass' not in encoded and 'Authorization:' not in encoded
    assert diagnostic['phase']=='connection_open' and diagnostic['stack'] and diagnostic['error_type']=='OSError'
    assert not state['provider_complete'] and adapter._reader is None


@pytest.mark.asyncio
async def test_worker_finishes_session_after_segments_and_on_failure():
    from types import SimpleNamespace
    from tests.voice.test_delivery_progress import call
    for fail in [False,True]:
        c=call();order=[]
        async def synth(text,*args,**kwargs):
            order.append(text)
            if fail:raise RuntimeError('original-failure')
        async def finish():order.append('FINISH')
        c.output=SimpleNamespace(finish_response=finish);c.speak_segment=synth
        if fail:
            with pytest.raises(RuntimeError,match='original-failure'):
                await c.speak('原第三段。原第四段。',reason='test')
            assert order==['原第三段。','FINISH']
            assert next(iter(c.delivery_progress.values()))['delivery_termination']=='failed'
        else:
            await c.speak('原第三段。原第四段。',reason='test')
            assert order==['原第三段。','原第四段。','FINISH']
