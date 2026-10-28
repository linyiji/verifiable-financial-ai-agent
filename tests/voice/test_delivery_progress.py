"""Delivery state/cancellation tests. Real RTC acceptance is recorded separately."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from apps.voice_worker.main import Call
from tests.voice.test_continuous_voice_backend import api


def call():
    c=object.__new__(Call);c.trace=Mock();c.id='UNIT-ONLY';c.delivery_progress={};c.user_speaking=False
    c.turn_sequence=1;c.active_microphone_sid='track';c.input_epoch=1
    c.session={'task_id':None};c.playout_sid='output';c.alive=lambda:True;c.receipts=[]
    c.source=SimpleNamespace(clear_queue=lambda:None)
    async def receipt(kind,**kwargs):c.receipts.append({'kind':kind,**kwargs})
    c.receipt=receipt
    return c


@pytest.mark.asyncio
async def test_partial_publication_does_not_replay_completed_segments():
    c=call();attempted=[];fail=True
    async def segment(text,reason,metadata,index,**kwargs):
        attempted.append(index)
        if index==1 and fail:raise TimeoutError()
    c.speak_segment=segment
    with pytest.raises(TimeoutError):await c.speak('第一段。第二段。第三段。',reason='test')
    p=next(iter(c.delivery_progress.values()));assert p['delivery_state']=='PARTIAL' and p['published_segments']==[0]
    assert p['active_segment']==1 and p['delivery_termination']=='failed'
    assert c.receipts[-1]['status']=='error' and c.receipts[-1]['metadata']['published_segments']==[0]
    await c.speak('第一段。第二段。第三段。',reason='test');assert attempted==[0,1]
    fail=False
    await c.speak('第一段。第二段。第三段。',reason='test',resume=True)
    assert attempted==[0,1,1,2] and next(iter(c.delivery_progress.values()))['delivery_state']=='PUBLISHED'
    await c.speak('第一段。第二段。第三段。',reason='test');assert attempted==[0,1,1,2]


@pytest.mark.asyncio
async def test_cancellation_retains_published_boundary_and_termination():
    c=call();started=asyncio.Event()
    async def segment(text,reason,metadata,index,**kwargs):
        if index==1:started.set();await asyncio.Event().wait()
    c.speak_segment=segment
    task=asyncio.create_task(c.speak('第一段。第二段。第三段。',reason='test'))
    await started.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    p=next(iter(c.delivery_progress.values()));assert p['delivery_state']=='PARTIAL'
    assert p['delivery_termination']=='cancelled' and p['published_segments']==[0]
    assert not any(r.get('metadata',{}).get('delivery_state')=='PUBLISHED' for r in c.receipts)


@pytest.mark.asyncio
async def test_waiting_for_synthesis_never_emits_speaking(monkeypatch):
    c=call();started=asyncio.Event();c.output=SimpleNamespace(delivery_policy={"completion_seconds":12,"connect_seconds":5,"first_pcm_target_seconds":5})
    async def synth(*args,**kwargs):started.set();await asyncio.Event().wait()
    async def stream(*args,**kwargs):yield await synth(*args,**kwargs)
    c.output.stream=stream;c.delivery_progress['test-response']={'published_segments':[]}
    monkeypatch.setenv('VEFIN_TTS_PROVIDER','mimo')
    task=asyncio.create_task(c.speak_segment('测试。','test',{'response_id':'test-response'},0))
    await started.wait();assert not any(r.get('status')=='speaking' for r in c.receipts)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task

@pytest.mark.asyncio
async def test_mimo_full_wav_completion_can_exceed_first_pcm_target(monkeypatch):
    import numpy as np
    c=call();c.source=SimpleNamespace()
    async def capture(frame):pass
    async def drained():pass
    c.source.capture_frame=capture;c.source.wait_for_playout=drained
    async def synth(*args,**kwargs):
        await asyncio.sleep(5.1)
        return np.ones(2400,dtype='<i2').tobytes(),24000
    c.output=SimpleNamespace(synthesize=synth,delivery_policy={"completion_seconds":12,"connect_seconds":5,"first_pcm_target_seconds":5})
    async def stream(*args,**kwargs):yield await synth(*args,**kwargs)
    c.output.stream=stream;c.delivery_progress['test-response']={'published_segments':[]}
    monkeypatch.setenv('VEFIN_TTS_PROVIDER','mimo');monkeypatch.setenv('VEFIN_MIMO_TTS_COMPLETION_SECONDS','12')
    await c.speak_segment('合成预算测试。','UNIT_ONLY',{'response_id':'test-response'},0)
    valid=[c for c in c.trace.event.call_args_list if c.args[0]=='first_valid_pcm']
    assert valid and not valid[0].kwargs['first_pcm_target_met']
    assert valid[0].kwargs['elapsed_ms']>5000
    assert any(r.get('status')=='speaking' for r in c.receipts)


def test_claim_retains_publication_boundary_for_replacement_worker(api):
    from tests.voice.test_voice_dialogue_v04 import begin,payload,W
    client,app,_=api;sid,lease=begin(client,'delivery-recovery')
    meta=payload(lease,1,'unused')['metadata']
    meta.update(response_id='VP-recovery',delivery_state='PARTIAL',segment_count=3,published_segments=[0],active_segment=1,text_sha256='a'*64,phase='failed',delivery_termination='failed')
    assert client.post(f'/internal/voice/{sid}/receipt',headers=W,json={'lease_id':lease,'kind':'turn_result','receipt_id':'delivery-failure','metadata':meta}).status_code==200
    assert client.post(f'/internal/voice/{sid}/release',headers=W,json={'lease_id':lease}).status_code==200
    r=client.post(f'/internal/voice/{sid}/claim',headers=W,json={'worker_id':'replacement'})
    assert r.status_code==200
    recovered=r.json()['playback_progress']['VP-recovery'];assert recovered['published_segments']==[0] and recovered['active_segment']==1
    assert recovered['delivery_state']=='PARTIAL' and recovered['delivery_termination']=='failed'

@pytest.mark.parametrize('published,expected',[([], 'FAILED'),([0], 'PARTIAL')])
def test_worker_loss_closes_unfinished_publication_without_losing_boundary(api,published,expected):
    from tests.voice.test_voice_dialogue_v04 import begin,payload,W
    client,_,_=api;sid,lease=begin(client,'delivery-worker-loss')
    meta=payload(lease,1,'unused')['metadata'];meta.update(response_id='VP-lost',delivery_state='PARTIAL' if published else 'PENDING',segment_count=3,published_segments=published,active_segment=1,text_sha256='b'*64,phase='audio_progress')
    assert client.post(f'/internal/voice/{sid}/receipt',headers=W,json={'lease_id':lease,'kind':'turn_result','receipt_id':'in-flight','metadata':meta}).status_code==200
    client.post(f'/internal/voice/{sid}/release',headers=W,json={'lease_id':lease})
    restored=client.post(f'/internal/voice/{sid}/claim',headers=W,json={'worker_id':'replacement'}).json()['playback_progress']['VP-lost']
    assert restored['delivery_state']==expected and restored['published_segments']==published
    assert restored['delivery_termination']=='worker_lost'


@pytest.mark.asyncio
async def test_partial_stream_retains_started_segment_and_blocks_replay():
    c=call()
    async def stream(*args, **kwargs):
        yield (b"\x01\x00"*1600,16000)
        raise TimeoutError()
    async def capture(frame):pass
    c.source.capture_frame=capture
    c.output=SimpleNamespace(stream=stream,delivery_policy={"completion_seconds":20,"connect_seconds":15,"first_pcm_target_seconds":10})
    with pytest.raises(TimeoutError):await c.speak('原文。',reason='test')
    p=next(iter(c.delivery_progress.values()))
    assert p['delivery_state']=='PARTIAL' and p['started_segments']==[0] and p['published_segments']==[]
    assert p['published_pcm_samples_24000']['0']>0
    with pytest.raises(RuntimeError,match='PARTIAL_SEGMENT'):await c.speak('原文。',reason='test',resume=True)
