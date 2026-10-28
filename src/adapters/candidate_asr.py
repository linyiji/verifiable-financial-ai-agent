"""Optional ASR implementations behind AudioInput -> literal text.

Credentials are injected by the caller, never loaded from a repository file.
No fallback, model substitution, product deadline mutation, or business logic.
Official contracts checked 2026-10-24; see the evaluation evidence references.
"""
from __future__ import annotations

import asyncio
import base64
import contextvars
from contextlib import AsyncExitStack
import hashlib
import hmac
import io
import json
import logging
import math
import re
import ssl
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime, UTC
from email.utils import format_datetime
from urllib.parse import urlencode, urlsplit

import httpx

from src.application.speech_service import AudioInput, SpeechError

QWEN_BEIJING_URL = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'
XFYUN_DIALECT_URL = 'wss://iat.cn-huabei-1.xf-yun.com/v1'


@dataclass(frozen=True)
class ASRTestBudget:
    """Independent bounded evaluation budgets, never the Worker's 12/6s policy."""
    connect_seconds: float = 15
    file_total_seconds: float = 90
    final_after_eos_seconds: float = 15
    websocket_overhead_seconds: float = 35

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in vars(self).values()):
            raise ValueError('INVALID_ASR_EVALUATION_BUDGET')


@dataclass(frozen=True)
class QwenASRConfig:
    model: str
    region: str
    api_key: str = field(repr=False)

    def __post_init__(self):
        # This adapter implements the synchronous Flash contract, not streaming
        # or Filetrans. Unknown families are a capability error, never rerouted.
        if self.region != 'cn-beijing' or self.model not in {
            'qwen-audio-3.1-asr-flash', 'qwen-audio-3.0-asr-flash'
        } or not self.api_key:
            raise ValueError('QWEN_CONFIGURATION_OR_CAPABILITY_MISMATCH')


@dataclass(frozen=True)
class XfyunASRConfig:
    endpoint: str
    app_id: str = field(repr=False)
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    domain: str = 'slm'
    language: str = 'zh_cn'
    accent: str = 'mulacc'

    def __post_init__(self):
        if (self.endpoint != XFYUN_DIALECT_URL or not all((self.app_id,self.api_key,self.api_secret))
            or (self.domain,self.language,self.accent) != ('slm','zh_cn','mulacc')):
            raise ValueError('XFYUN_DIALECT_CONFIGURATION_MISMATCH')


def pcm_wav(audio: AudioInput, max_seconds: float):
    if audio.media_type not in {'audio/wav','audio/x-wav'}:
        raise SpeechError('ASR_CAPABILITY_UNSUPPORTED','此ASR适配器需要PCM WAV输入。',415)
    try:
        with wave.open(io.BytesIO(audio.content)) as w:
            if (w.getframerate(),w.getnchannels(),w.getsampwidth(),w.getcomptype()) != (16000,1,2,'NONE'):
                raise SpeechError('ASR_CAPABILITY_UNSUPPORTED','此ASR适配器需要16kHz单声道16bit PCM WAV。',415)
            n=w.getnframes(); pcm=w.readframes(n)
    except (wave.Error,EOFError,ValueError):
        raise SpeechError('AUDIO_INVALID','WAV无法解码。',422) from None
    if not n or len(pcm)!=n*2:
        raise SpeechError('AUDIO_INVALID','WAV音频为空或不完整。',422)
    if n/16000>max_seconds:
        raise SpeechError('AUDIO_TOO_LONG','音频超过本适配器支持时长。',422)
    return pcm, n/16000


def language_family(language):
    if language in {None,'auto'}: return None
    if language in {'yue-HK','yue','cantonese','zh','zh-CN','zh-HK','zh-TW'}:return 'zh'
    if language in {'en','en-US','en-GB'}:return 'en'
    raise SpeechError('ASR_LANGUAGE_UNSUPPORTED','此候选未实现该语言映射。',422)


class _ObservedASR:
    def __init__(self, *, budget=None, observer=None, on_attempt=None, secrets=()):
        self.budget=budget or ASRTestBudget()
        self.observer=observer;self.on_attempt=on_attempt
        self._secrets=tuple(s for s in secrets if s)
        self._state=contextvars.ContextVar('asr_candidate_observation',default=None)
        self._lock=asyncio.Lock()

    def observation(self):return self._state.get()

    def _redact(self,value):
        if isinstance(value,dict):
            return {k:('[REDACTED]' if any(x in k.lower() for x in ('secret','api_key','authorization','app_id','signature')) else self._redact(v)) for k,v in value.items()}
        if isinstance(value,list):return [self._redact(v) for v in value]
        if isinstance(value,str):
            for secret in self._secrets:value=value.replace(secret,'[REDACTED]')
            value=re.sub(r'(?:https?|wss?)://[^\s"<>]+\?[^\s"<>]+','[REDACTED_QUERY_URL]',value)
        return value

    def _event(self,stage,**detail):
        state=self._state.get()
        event=self._redact({'stage':stage,'elapsed_ms':round((time.monotonic()-state['_started'])*1000,3),**detail})
        state['events'].append(event)
        if self.observer:self.observer(event)

    def _begin(self, audio, duration, **detail):
        if self._lock.locked():
            raise SpeechError('ASR_PROVIDER_BUSY','同一供应商已有识别在途。',503)
        self._state.set({'_started':time.monotonic(),'state':'RUNNING','provider':self.provider_name,
            'input_sha256':hashlib.sha256(audio.content).hexdigest(),'input_duration_s':duration,
            'session_language':audio.language,'events':[],**detail})

    def _charge(self):
        if self.on_attempt:self.on_attempt()
        self._event('attempt_started')

    def _finish(self,state):
        current=self._state.get();current['state']=state
        current['total_ms']=round((time.monotonic()-current['_started'])*1000,3)
        current.pop('_started',None)

    def _error(self,code,provider_code=None,status=503):
        self._event('failed',error_code=code,provider_code=provider_code)
        raise SpeechError(code,'ASR候选未完成识别；已保留错误阶段，无自动重试或回退。',status)


def qwen_parameters(language, model):
    family=language_family(language)
    parameters={'format':'wav','sample_rate':'16000'}
    if family:parameters['language_hints']=[family]
    if model=='qwen-audio-3.1-asr-flash':
        parameters.update(keep_dialect=True,speaker_diarization_enabled=False)
    return parameters


class QwenSpeechRecognizer(_ObservedASR):
    provider_name='qwen'

    def __init__(self,config:QwenASRConfig,*,transport=None,http_client=None,wire_format='wav',wire_bitrate=16000,**kwargs):
        super().__init__(secrets=(config.api_key,),**kwargs)
        self.config=config;self.transport=transport;self.http_client=http_client
        if wire_format not in {'wav','flac','opus'}:
            raise ValueError('QWEN_WIRE_FORMAT_UNSUPPORTED')
        self.wire_format=wire_format;self.wire_bitrate=wire_bitrate

    def _response_error(self, response, data, *, body_bytes, truncated=False):
        """Whitelist diagnostics, never a raw error dump or reflected audio.

        A malformed provider error or failing audit observer must not replace
        the original HTTP failure with a local parsing/transport error.
        """
        state=self._state.get()
        def safe_text(value, limit):
            if not isinstance(value,(str,int,float)):return 'UNKNOWN'
            value=self._redact(str(value)[:8192])
            value=re.sub(r'(?:https?|wss?)://[^\s"<>]+','[REDACTED_URL]',value)
            value=re.sub(r'data:[^\s,;]+(?:;base64)?,[^\s"<>]*','[REDACTED_AUDIO]',value,flags=re.I)
            value=re.sub(r'(?i)\bBearer\s+[^\s,;"<>]+','Bearer [REDACTED]',value)
            value=re.sub(r'''(?i)\b(?:api[_-]?key|authorization|signature|token|secret|password)["']?\s*[:=]\s*["']?[^\s,;"'<>]+''','[REDACTED_CREDENTIAL]',value)
            value=re.sub(r'[A-Za-z0-9+/=_-]{80,}','[REDACTED_BLOB]',value)
            return ''.join(c if c.isprintable() else ' ' for c in value)[:limit]
        try:
            obj=data if isinstance(data,dict) else {}
            fields={k:safe_text(obj.get(k),limit) for k,limit in [('code',128),('message',512)]}
            request_id=obj.get('request_id') or response.headers.get('x-request-id') or response.headers.get('x-dashscope-request-id')
            fields['request_id']=safe_text(request_id,128)
            summary={'http_status':response.status_code,
                'response_type':safe_text(response.headers.get('content-type'),80),
                **fields,'body_bytes_observed':body_bytes,'body_truncated':truncated,
                'body_summary':json.dumps(fields,ensure_ascii=False,separators=(',',':'))[:1024],
                'body_policy':'JSON_CODE_MESSAGE_REQUEST_ID_ONLY' if isinstance(data,dict) else 'NON_JSON_BODY_OMITTED'}
        except Exception:
            summary={'http_status':response.status_code,'code':'UNKNOWN','message':'UNKNOWN',
                     'request_id':'UNKNOWN','body_policy':'DIAGNOSTIC_PARSE_FAILED_BODY_OMITTED'}
        state['provider_error']=summary
        state['request_id']=summary['request_id']
        try:self._event('supplier_error_response',**summary)
        except Exception:state['error_audit_failed']=True
        return summary

    def _reject_response(self, category, provider_code, status):
        try:self._event('failed',error_code=category,provider_code=provider_code)
        except Exception:self._state.get()['error_audit_failed']=True
        raise SpeechError(category,'ASR供应商拒绝请求；已保留脱敏错误，无自动重试或回退。',status)

    async def recognize(self,audio):
        pcm,duration=pcm_wav(audio,300)
        parameters=qwen_parameters(audio.language,self.config.model)
        parameters['format']=self.wire_format
        self._begin(audio,duration,requested_model=self.config.model,actual_model='UNKNOWN',region=self.config.region,
            effective_parameters=parameters,mode='HTTP_SYNCHRONOUS_FILE_NO_SSE',
            native_polishing_control='NOT_DOCUMENTED_FOR_THIS_MODEL;no polishing/context/hotword instruction added')
        async with self._lock:
            try:
                async with asyncio.timeout(self.budget.file_total_seconds):
                    if self.wire_format == 'wav':
                        wire=audio.content
                        wire_meta={'wire_format':'wav','wire_mime':'audio/wav',
                            'wire_bytes':len(wire),'wire_sha256':hashlib.sha256(wire).hexdigest(),
                            'input_pcm_bytes':len(pcm),'lossy':False}
                    else:
                        from src.adapters.asr_audio_encoding import encode_asr_pcm
                        wire,wire_meta=encode_asr_pcm(pcm,wire_format=self.wire_format,bitrate=self.wire_bitrate)
                    self._state.get().update(wire_meta)
                    self._event('audio_encoding_complete',**wire_meta)
                    body={'model':self.config.model,'input':{'messages':[{'role':'user','content':[{
                        'type':'input_audio','input_audio':{'data':'data:'+wire_meta['wire_mime']+';base64,'+base64.b64encode(wire).decode()}}]}]},'parameters':parameters}
                    serialized=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
                    if len(serialized)>10_000_000:self._error('ASR_REQUEST_BODY_LIMIT')
                    self._state.get()['request_body_bytes']=len(serialized)
                    self._event('request_body_constructed',bytes=len(serialized),
                        sha256=hashlib.sha256(serialized).hexdigest(),
                        base64_bytes=4*((len(wire)+2)//3))
                    self._charge()
                    async def trace(event,info):
                        if event.endswith(('.started','.complete','.failed')):
                            self._event(event)
                        state=self._state.get()
                        if event=='connection.connect_tcp.started':state['connection_started_ms']=(time.monotonic()-state['_started'])*1000
                        if event=='connection.start_tls.complete':
                            state['connection_ms']=(time.monotonic()-state['_started'])*1000-state.get('connection_started_ms',0)
                        if event.endswith('send_request_body.started'):
                            state['send_audio_started_ms']=(time.monotonic()-state['_started'])*1000
                        if event.endswith('send_request_body.complete'):
                            state['send_audio_completed_ms']=(time.monotonic()-state['_started'])*1000
                            state['send_audio_duration_ms']=state['send_audio_completed_ms']-state.get('send_audio_started_ms',state['send_audio_completed_ms'])
                    async with AsyncExitStack() as stack:
                        client=self.http_client or await stack.enter_async_context(httpx.AsyncClient(
                            transport=self.transport or httpx.AsyncHTTPTransport(retries=0,verify=True),
                            trust_env=False,follow_redirects=False))
                        async with client.stream('POST',QWEN_BEIJING_URL,headers={'Authorization':'Bearer '+self.config.api_key,
                            'X-DashScope-SSE':'disable','Content-Type':'application/json'},
                            content=serialized,extensions={'trace':trace},
                            timeout=httpx.Timeout(self.budget.file_total_seconds,connect=self.budget.connect_seconds)) as response:
                            self._event('response_headers',http_status=response.status_code)
                            self._state.get()['response_headers_ms']=(time.monotonic()-self._state.get()['_started'])*1000
                            payload=bytearray()
                            error_body_truncated=False
                            async for chunk in response.aiter_bytes():
                                if not response.is_success and len(payload)+len(chunk)>16384:
                                    payload.extend(chunk[:16384-len(payload)])
                                    error_body_truncated=True
                                    break
                                if len(payload)+len(chunk)>4_000_000:self._error('ASR_RESPONSE_LIMIT')
                                payload.extend(chunk)
                            self._event('response_body_capped' if error_body_truncated else 'response_body_complete',bytes=len(payload))
                            self._state.get()['response_body_ms']=(time.monotonic()-self._state.get()['_started'])*1000
                            try:data=json.loads(payload)
                            except (ValueError,UnicodeError):data=None
                            if not response.is_success or isinstance(data,dict) and data.get('code'):
                                diagnostic=self._response_error(response,data,body_bytes=len(payload),truncated=error_body_truncated)
                                code=diagnostic['code']
                                category=('ASR_PROVIDER_UNAUTHORIZED' if response.status_code==401 or 'apikey' in code.lower()
                                    else 'ASR_PROVIDER_FORBIDDEN' if response.status_code==403 or any(x in code.lower() for x in ('access','permission','purchased','modelnotfound'))
                                    else 'ASR_PROVIDER_QUOTA' if response.status_code==429 or any(x in code.lower() for x in ('quota','arrear','balance','freeallocated','allocation'))
                                    else 'ASR_PROVIDER_NO_WORDS' if 'ASR_RESPONSE_HAVE_NO_WORDS' in diagnostic.get('message','')
                                    else 'ASR_PROVIDER_FORMAT_ERROR' if code in {'InvalidParameter','InvalidParameterValue','UnsupportedFormat','AudioFormatError'}
                                    else 'ASR_PROVIDER_REJECTED')
                                self._reject_response(category,code,response.status_code if not response.is_success else 502)
                            if not isinstance(data,dict):
                                self._response_error(response,data,body_bytes=len(payload))
                                self._error('ASR_INVALID_RESPONSE')
                            self._event('supplier_response',response=data)
                            state=self._state.get();state['request_id']=data.get('request_id')
                            state['usage']=self._redact(data.get('usage'))
                            state['actual_model']=data.get('model','UNKNOWN')
                            output=data.get('output') or {};text=output.get('text')
                            if not isinstance(text,str) or not text.strip():self._error('ASR_INVALID_RESPONSE')
                            if output.get('sentence',{}).get('sentence_end') is False:self._error('ASR_INCOMPLETE_RESPONSE')
                            now=(time.monotonic()-state['_started'])*1000
                            state['first_text_ms']=now;state['final_ms']=now
                            sent=state.get('send_audio_completed_ms')
                            state['eos_to_final_ms']=now-sent if sent is not None else None
                            self._event('final_transcript',text=text)
                self._finish('SUCCESS');return text
            except asyncio.CancelledError:
                self._event('cancelled');self._finish('CANCELLED');raise
            except (TimeoutError,httpx.TimeoutException) as exc:
                code='ASR_CONNECT_TIMEOUT' if isinstance(exc,httpx.ConnectTimeout) else 'ASR_TEST_DEADLINE_EXCEEDED'
                self._event('failed',error_code=code,exception_type=type(exc).__name__);self._finish('FAILED')
                raise SpeechError(code,'ASR候选连接或整体截止已到；阶段见脱敏日志。',503) from None
            except SpeechError:
                self._finish('FAILED');raise
            except httpx.HTTPError:
                self._event('failed',error_code='ASR_TRANSPORT_ERROR');self._finish('FAILED')
                raise SpeechError('ASR_TRANSPORT_ERROR','ASR候选连接失败。',503) from None
            except Exception:
                self._event('failed',error_code='ASR_INVALID_RESPONSE');self._finish('FAILED')
                raise SpeechError('ASR_INVALID_RESPONSE','ASR候选返回格式异常。',502) from None


class XfyunResultAssembler:
    """Protocol-level sn/rg revisions; never linguistic deduplication.

    Intermediate and final results replace the same sn. rpl removes the declared
    inclusive range before storing its new sn; apd appends a new serial slot.
    Complete session status remains the caller's responsibility.
    """
    def __init__(self):self.slots={};self.final_slots=set();self.history=[]

    def apply(self,result):
        sn=result.get('sn');mode=result.get('pgs','apd')
        if not isinstance(sn,int) or isinstance(sn,bool) or sn<0 or mode not in {'apd','rpl'}:
            raise ValueError('INVALID_XFYUN_REVISION')
        text=''
        for word in result.get('ws',[]):
            choices=word.get('cw') or []
            if not choices or not isinstance(choices[0].get('w'),str):raise ValueError('INVALID_XFYUN_WORD')
            text+=choices[0]['w']  # Top hypothesis only; alternatives are not additional speech.
        if mode=='rpl':
            rg=result.get('rg')
            if not isinstance(rg,list) or len(rg)!=2 or not all(isinstance(x,int) and x>=0 for x in rg) or rg[0]>rg[1]:
                raise ValueError('INVALID_XFYUN_REPLACEMENT_RANGE')
            for key in list(self.slots):
                if rg[0]<=key<=rg[1]:self.slots.pop(key);self.final_slots.discard(key)
        self.slots[sn]=text
        if result.get('rst')=='rlt' or result.get('ls') is True:self.final_slots.add(sn)
        else:self.final_slots.discard(sn)
        self.history.append({'sn':sn,'pgs':mode,'rst':result.get('rst'),'rg':result.get('rg'),'text':text})
        return ''.join(self.slots[k] for k in sorted(self.slots))


def xfyun_parameters(config,language):
    family=language_family(language)
    if family not in {None,'zh','en'}:
        raise SpeechError('ASR_LANGUAGE_UNSUPPORTED','方言免切接口不支持该语言。',422)
    # BCP47 is retained at SpeechService. The dialect API has no yue token.
    return {'domain':config.domain,'language':config.language,'accent':config.accent,
        'dwa':'wpgs','eos':10000,'ptt':1,'smth':0,'nunum':0,'ltc':1,
        'result':{'encoding':'utf8','compress':'raw','format':'json'}}


def xfyun_signed_url(config,now=None):
    target=urlsplit(config.endpoint)
    date=format_datetime(now or datetime.now(UTC),usegmt=True)
    origin=f'host: {target.hostname}\ndate: {date}\nGET {target.path} HTTP/1.1'
    signature=base64.b64encode(hmac.new(config.api_secret.encode(),origin.encode(),hashlib.sha256).digest()).decode()
    value=f'api_key="{config.api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'
    return config.endpoint+'?'+urlencode({'authorization':base64.b64encode(value.encode()).decode(),'date':date,'host':target.hostname})


class XfyunDialectRecognizer(_ObservedASR):
    provider_name='xfyun'

    def __init__(self,config:XfyunASRConfig,*,connector=None,pacing_sleep=asyncio.sleep,**kwargs):
        super().__init__(secrets=(config.app_id,config.api_key,config.api_secret),**kwargs)
        self.config=config;self.connector=connector;self.sleep=pacing_sleep

    async def recognize(self,audio):
        from websockets.asyncio.client import connect
        from websockets.exceptions import InvalidStatus,ConnectionClosed,WebSocketException
        pcm,duration=pcm_wav(audio,60);parameters=xfyun_parameters(self.config,audio.language)
        total_deadline=duration+self.budget.websocket_overhead_seconds
        self._begin(audio,duration,requested_model='dialect_asr/domain=slm',actual_model='UNKNOWN',
            effective_parameters=parameters,mode='REALTIME_PACED_PCM',
            total_deadline_seconds=total_deadline,frame_bytes=1280,frame_interval_ms=40)
        async with self._lock:
            try:
                async with asyncio.timeout(total_deadline):
                    url=xfyun_signed_url(self.config)
                    # A private disabled logger prevents signed request targets from
                    # appearing even if the application's global log level is DEBUG.
                    logger=logging.Logger('vefin-private-asr-websocket');logger.disabled=True
                    self._charge();self._event('connection_started')
                    factory=self.connector or connect
                    async with factory(url,proxy=None,ssl=ssl.create_default_context(),open_timeout=self.budget.connect_seconds,
                        close_timeout=1,ping_interval=None,max_size=2_000_000,logger=logger) as ws:
                        state=self._state.get();state['connection_ms']=(time.monotonic()-state['_started'])*1000
                        ssl_obj=ws.transport.get_extra_info('ssl_object') if getattr(ws,'transport',None) else None
                        self._event('connection_complete',certificate_verification=True,
                            TLS_version=ssl_obj.version() if ssl_obj else 'UNKNOWN')
                        assembler=XfyunResultAssembler();sent_all=asyncio.Event();sender=None
                        async def send_audio():
                            send_start=time.monotonic();state['send_audio_started_ms']=(send_start-state['_started'])*1000
                            self._event('send_audio_started');sequence=0;sent=0
                            while sent<len(pcm):
                                part=pcm[sent:sent+1280];status=0 if sequence==0 else 1
                                frame={'header':{'app_id':self.config.app_id,'status':status},'payload':{'audio':{
                                    'encoding':'raw','sample_rate':16000,'channels':1,'bit_depth':16,
                                    'status':status,'seq':sequence,'audio':base64.b64encode(part).decode()}}}
                                if sequence==0:frame['parameter']={'iat':parameters}
                                await ws.send(json.dumps(frame));sent+=len(part);sequence+=1
                                state['sent_pcm_bytes']=sent
                                # No catch-up bursts: network stalls only slow the
                                # pacing, and final partial frames use their true duration.
                                await self.sleep(len(part)/32000)
                            await ws.send(json.dumps({'header':{'app_id':self.config.app_id,'status':2},
                                'payload':{'audio':{'encoding':'raw','sample_rate':16000,'channels':1,'bit_depth':16,
                                    'status':2,'seq':sequence,'audio':''}}}))
                            state['eos_sent_ms']=(time.monotonic()-state['_started'])*1000
                            state['send_audio_duration_ms']=(time.monotonic()-send_start)*1000
                            self._event('eos_sent',sent_pcm_bytes=sent,frames=sequence);sent_all.set()
                        sender=asyncio.create_task(send_audio())
                        final=False
                        try:
                            while not final:
                                if sender.done():
                                    await sender
                                    remaining=(state['eos_sent_ms']/1000+state['_started']+self.budget.final_after_eos_seconds)-time.monotonic()
                                    raw=await asyncio.wait_for(ws.recv(),max(0,remaining))
                                else:
                                    # Wake on sender failure or EOS as well as on
                                    # receiving data, so EOS+15 is a real deadline.
                                    receive=asyncio.create_task(ws.recv())
                                    try:
                                        done,_=await asyncio.wait({receive,sender},return_when=asyncio.FIRST_COMPLETED)
                                        if sender in done:
                                            await sender
                                            remaining=(state['_started']+state['eos_sent_ms']/1000+self.budget.final_after_eos_seconds)-time.monotonic()
                                            raw=await asyncio.wait_for(receive,max(0,remaining))
                                        else:raw=await receive
                                    finally:
                                        if not receive.done():receive.cancel();await asyncio.gather(receive,return_exceptions=True)
                                try:message=json.loads(raw)
                                except (ValueError,UnicodeError):self._error('ASR_INVALID_RESPONSE')
                                if not isinstance(message,dict) or not isinstance(message.get('header'),dict):self._error('ASR_INVALID_RESPONSE')
                                self._event('supplier_response',response=message)
                                header=message['header'];state['request_id']=header.get('sid')
                                code=header.get('code')
                                if code!=0:
                                    category=('ASR_PROVIDER_UNAUTHORIZED' if code in {10313,11200,10700}
                                        else 'ASR_PROVIDER_QUOTA' if code in {10010,11201,11202,11203,11204}
                                        else 'ASR_PROVIDER_REJECTED')
                                    self._error(category,code)
                                result=(message.get('payload') or {}).get('result')
                                if result:
                                    try:
                                        if result.get('compress','raw')!='raw' or result.get('format','json')!='json':raise ValueError()
                                        decoded=json.loads(base64.b64decode(result['text'],validate=True).decode('utf8'))
                                        text=assembler.apply(decoded)
                                    except (ValueError,KeyError,TypeError,UnicodeError):self._error('ASR_INVALID_RESPONSE')
                                    self._event('decoded_result',result=decoded,merged_text=text)
                                    if text and 'first_text_ms' not in state:state['first_text_ms']=(time.monotonic()-state['_started'])*1000
                                final=header.get('status')==2
                            if not sent_all.is_set():
                                self._error('ASR_EARLY_FINAL_INPUT_INCOMPLETE')
                            await sender
                            text=''.join(assembler.slots[k] for k in sorted(assembler.slots))
                            if not text.strip():self._error('ASR_INVALID_RESPONSE')
                            state['final_ms']=(time.monotonic()-state['_started'])*1000
                            state['eos_to_final_ms']=state['final_ms']-state['eos_sent_ms']
                            state['usage']='UNKNOWN';state['revision_history']=assembler.history
                            self._event('final_transcript',text=text)
                        finally:
                            if sender and not sender.done():sender.cancel()
                            if sender:await asyncio.gather(sender,return_exceptions=True)
                self._finish('SUCCESS');return text
            except asyncio.CancelledError:
                self._event('cancelled');self._finish('CANCELLED');raise
            except TimeoutError:
                self._event('failed',error_code='ASR_TEST_DEADLINE_EXCEEDED');self._finish('FAILED')
                raise SpeechError('ASR_TEST_DEADLINE_EXCEEDED','方言ASR独立测试截止已到。',503) from None
            except SpeechError:
                self._finish('FAILED');raise
            except InvalidStatus as exc:
                status=exc.response.status_code
                self._event('failed',http_status=status,error_code='ASR_WEBSOCKET_HANDSHAKE_REJECTED')
                self._finish('FAILED')
                raise SpeechError('ASR_PROVIDER_UNAUTHORIZED' if status in {401,403} else 'ASR_TRANSPORT_ERROR',
                    '方言ASR握手未成功；签名地址已脱敏。',status) from None
            except (ConnectionClosed,WebSocketException,OSError):
                self._event('failed',error_code='ASR_TRANSPORT_ERROR');self._finish('FAILED')
                raise SpeechError('ASR_TRANSPORT_ERROR','方言ASR连接关闭或传输失败。',503) from None
            except Exception:
                self._event('failed',error_code='ASR_INVALID_RESPONSE');self._finish('FAILED')
                raise SpeechError('ASR_INVALID_RESPONSE','方言ASR响应格式异常。',502) from None
