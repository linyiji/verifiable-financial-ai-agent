"""Offline candidate contract tests. Credentials and network calls are synthetic."""
import asyncio
import base64
import io
import json
import ssl
import wave
from contextlib import asynccontextmanager
from datetime import datetime, UTC
from urllib.parse import parse_qs,urlsplit

import httpx
import pytest

from src.application.speech_service import AudioInput,SpeechService,SpeechError
from src.adapters.speech import candidate_speech_recognizer
from src.adapters.candidate_asr import (
    ASRTestBudget,QwenASRConfig,QwenSpeechRecognizer,XfyunASRConfig,
    XfyunDialectRecognizer,XfyunResultAssembler,xfyun_signed_url,
)


def audio(frames=640):
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x01\x00'*frames)
    return AudioInput(out.getvalue(),'audio/wav','yue-HK')


def config():return XfyunASRConfig('wss://iat.cn-huabei-1.xf-yun.com/v1','offline-app','offline-key','offline-secret')


def result(sn,text,**extra):
    return {'sn':sn,'ws':[{'cw':[{'w':text},{'w':'alternative-not-speech'}]}],**extra}


def message(r=None,status=1,code=0):
    m={'header':{'code':code,'status':status,'sid':'offline-session'}}
    if r is not None:m['payload']={'result':{'text':base64.b64encode(json.dumps(r).encode()).decode(),
        'encoding':'utf8','compress':'raw','format':'json'}}
    return json.dumps(m)


class FakeWS:
    def __init__(self, *, emit_final=True,error=None):
        self.sent=[];self.queue=asyncio.Queue();self.closed=False;self.emit_final=emit_final;self.error=error
    async def send(self,raw):
        frame=json.loads(raw);self.sent.append(frame)
        if len(self.sent)==1:
            if self.error:self.queue.put_nowait(message(code=self.error));return
            self.queue.put_nowait(message(result(0,'不要',rst='pgs',pgs='apd')))
        if frame['header']['status']==2 and self.emit_final:
            self.queue.put_nowait(message(result(1,'不要說已完成',pgs='rpl',rg=[0,0],rst='rlt',ls=True),status=2))
    async def recv(self):return await self.queue.get()


def connector_for(ws,seen=None):
    @asynccontextmanager
    async def connector(url,**options):
        if seen is not None:seen.append((url,options))
        try:yield ws
        finally:ws.closed=True
    return connector


@pytest.mark.asyncio
async def test_qwen_existing_boundary_language_model_and_literal_text():
    seen=[];attempts=[];records=[];a=audio()
    async def handle(req):
        body=json.loads(req.content);seen.append(body)
        assert base64.b64decode(body['input']['messages'][0]['content'][0]['input_audio']['data'].split(',',1)[1])==a.content
        return httpx.Response(200,json={'request_id':'qwen-offline','output':{'text':'不要說已經完成操作操作。','sentence':{'sentence_end':True}},'usage':{'duration':1}})
    recognizer=QwenSpeechRecognizer(QwenASRConfig('qwen-audio-3.1-asr-flash','cn-beijing','offline-key'),
        transport=httpx.MockTransport(handle),observer=records.append,on_attempt=lambda:attempts.append(1))
    answer=await SpeechService(recognizer).transcribe(AudioInput(a.content,'audio/wav;codecs=pcm','yue-HK'))
    assert answer.text=='不要說已經完成操作操作。' and len(attempts)==1
    assert seen[0]['model']=='qwen-audio-3.1-asr-flash'
    assert seen[0]['parameters']=={'format':'wav','sample_rate':'16000','language_hints':['zh'],'keep_dialect':True,'speaker_diarization_enabled':False}
    assert len(seen[0]['input']['messages'])==1 and recognizer.observation()['session_language']=='yue-HK'
    assert any(x['stage']=='supplier_response' for x in records)


@pytest.mark.asyncio
async def test_qwen_auth_error_is_safe_and_no_retry():
    count=[];records=[];secret='offline-super-secret'
    async def handle(req):
        count.append(1)
        return httpx.Response(401,json={'code':'InvalidApiKey','message':secret+' https://example.com/?authorization=private'})
    r=QwenSpeechRecognizer(QwenASRConfig('qwen-audio-3.1-asr-flash','cn-beijing',secret),transport=httpx.MockTransport(handle),observer=records.append)
    with pytest.raises(SpeechError) as e:await SpeechService(r).transcribe(audio())
    assert e.value.code=='ASR_PROVIDER_UNAUTHORIZED' and count==[1]
    rendered=json.dumps(records)+repr(r.config)+str(e.value)
    assert secret not in rendered and 'authorization=private' not in rendered


@pytest.mark.asyncio
async def test_qwen_total_budget_cancels_inflight_and_does_not_retry():
    calls=[];closed=[]
    async def handle(req):
        calls.append(1)
        try:await asyncio.sleep(10)
        finally:closed.append(1)
    r=QwenSpeechRecognizer(QwenASRConfig('qwen-audio-3.1-asr-flash','cn-beijing','offline'),
        transport=httpx.MockTransport(handle),budget=ASRTestBudget(file_total_seconds=.02))
    with pytest.raises(SpeechError) as e:await r.recognize(audio())
    assert e.value.code=='ASR_TEST_DEADLINE_EXCEEDED' and calls==closed==[1]


@pytest.mark.asyncio
async def test_qwen_cancellation_propagates_and_one_inflight():
    entered=asyncio.Event();closed=[]
    async def handle(req):
        entered.set()
        try:await asyncio.sleep(10)
        finally:closed.append(1)
    r=QwenSpeechRecognizer(QwenASRConfig('qwen-audio-3.1-asr-flash','cn-beijing','offline'),transport=httpx.MockTransport(handle))
    task=asyncio.create_task(r.recognize(audio()));await entered.wait()
    with pytest.raises(SpeechError) as e:await r.recognize(audio())
    assert e.value.code=='ASR_PROVIDER_BUSY'
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert closed==[1]


def test_xfyun_revisions_replace_ranges_same_serial_and_keep_real_repetition():
    merge=XfyunResultAssembler()
    assert merge.apply(result(0,'不要',rst='pgs',pgs='apd'))=='不要'
    assert merge.apply(result(0,'不要說',rst='pgs',pgs='apd'))=='不要說'
    assert merge.apply(result(1,'已經',rst='pgs',pgs='apd'))=='不要說已經'
    assert merge.apply(result(2,'不要話已經完成',rst='rlt',pgs='rpl',rg=[0,1]))=='不要話已經完成'
    assert merge.apply(result(3,'操作操作',rst='rlt',pgs='apd',ls=True))=='不要話已經完成操作操作'
    # Duplicate protocol delivery updates its own serial instead of appending.
    assert merge.apply(result(3,'操作操作',rst='rlt',pgs='apd',ls=True))=='不要話已經完成操作操作'
    with pytest.raises(ValueError):merge.apply(result(4,'不合法',pgs='rpl',rg=[3,1]))


@pytest.mark.asyncio
async def test_xfyun_service_language_pacing_final_and_signed_url_never_logged():
    ws=FakeWS();seen=[];sleeps=[];attempts=[];records=[]
    async def paced(delay):sleeps.append(delay);await asyncio.sleep(0)
    r=XfyunDialectRecognizer(config(),connector=connector_for(ws,seen),pacing_sleep=paced,
        on_attempt=lambda:attempts.append(1),observer=records.append)
    answer=await SpeechService(r).transcribe(audio(1600))
    assert answer.text=='不要說已完成' and attempts==[1] and ws.closed
    assert sleeps==[.04,.04,.02]
    assert [x['header']['status'] for x in ws.sent]==[0,1,1,2]
    parameters=ws.sent[0]['parameter']['iat']
    assert (parameters['domain'],parameters['language'],parameters['accent'])==('slm','zh_cn','mulacc')
    assert parameters['smth']==0 and parameters['nunum']==0
    assert len(ws.sent[0]['payload']['audio']['audio'])>0 and ws.sent[-1]['payload']['audio']['audio']==''
    assert r.observation()['session_language']=='yue-HK' and r.observation()['sent_pcm_bytes']==3200
    assert r.observation()['eos_to_final_ms']>=0
    assert seen[0][1]['proxy'] is None and seen[0][1]['ssl'].verify_mode==ssl.CERT_REQUIRED and seen[0][1]['ssl'].check_hostname
    assert 'authorization=' in seen[0][0]
    assert 'authorization=' not in json.dumps(records) and 'offline-secret' not in repr(r.config)


@pytest.mark.asyncio
async def test_xfyun_eos_deadline_closes_and_no_retry():
    ws=FakeWS(emit_final=False);attempts=[]
    async def paced(delay):await asyncio.sleep(0)
    r=XfyunDialectRecognizer(config(),connector=connector_for(ws),pacing_sleep=paced,
        budget=ASRTestBudget(final_after_eos_seconds=.02),on_attempt=lambda:attempts.append(1))
    with pytest.raises(SpeechError) as e:await r.recognize(audio())
    assert e.value.code=='ASR_TEST_DEADLINE_EXCEEDED' and ws.closed and attempts==[1]


@pytest.mark.asyncio
async def test_xfyun_cancellation_closes_and_stops_sending():
    ws=FakeWS();entered=asyncio.Event();closed=[]
    async def paced(delay):
        entered.set()
        try:await asyncio.sleep(10)
        finally:closed.append(1)
    r=XfyunDialectRecognizer(config(),connector=connector_for(ws),pacing_sleep=paced)
    task=asyncio.create_task(r.recognize(audio(1600)));await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert ws.closed and len(ws.sent)==1 and closed==[1]


@pytest.mark.asyncio
async def test_xfyun_auth_error_stops_partial_audio_and_never_returns_partial_text():
    ws=FakeWS(error=11200)
    r=XfyunDialectRecognizer(config(),connector=connector_for(ws))
    with pytest.raises(SpeechError) as e:await SpeechService(r).transcribe(audio(1600))
    assert e.value.code=='ASR_PROVIDER_UNAUTHORIZED' and ws.closed and len(ws.sent)==1
    assert r.observation()['state']=='FAILED'


@pytest.mark.parametrize('provider,cfg',[
    ('qwen',{'provider':'dashscope','region':'cn-beijing','model':'qwen-audio-3.1-asr-flash-streaming','api_key':'offline'}),
    ('qwen',{'provider':'dashscope','region':'ap-southeast-1','model':'qwen-audio-3.1-asr-flash','api_key':'offline'}),
    ('xfyun',{'provider':'xfyun','service':'real_time_transcription','endpoint':'wss://iat.cn-huabei-1.xf-yun.com/v1','app_id':'offline','api_key':'offline','api_secret':'offline','parameters':{}}),
])
def test_no_silent_product_model_or_region_substitution(provider,cfg):
    with pytest.raises(ValueError):candidate_speech_recognizer(provider,cfg)


def test_signature_targets_actual_dialect_host_and_normal_SNI():
    url=xfyun_signed_url(config(),datetime(2026,10,24,tzinfo=UTC))
    parts=urlsplit(url);q=parse_qs(parts.query)
    assert parts.hostname=='iat.cn-huabei-1.xf-yun.com' and parts.path=='/v1'
    assert q['host']==[parts.hostname] and q['date']==['Sat, 24 Oct 2026 00:00:00 GMT']
    assert 'hmac-sha256' in base64.b64decode(q['authorization'][0]).decode()
