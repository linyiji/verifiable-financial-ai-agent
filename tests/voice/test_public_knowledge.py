"""Real saved official passages, original API/dialogue, no network/model calls."""
import json
from pathlib import Path

import pytest
from tests.voice.test_natural_dialogue import api, no_network, setup, send, A
from src.adapters.voice_knowledge import PublicKnowledge
from src.application.voice_natural_dialogue import accept_body

REGISTRY = Path('docs/voice/knowledge/prudential-hk-payment-demo.json')
QUESTION = '保誠香港人壽保單轉扣款戶口有咩網上入口？下個月先考慮，唔好提交。'
ANSWER = '保誠香港公開指引介紹，登入myPrudential後揀「繳費設定」，再揀想更改嘅人壽保單。今次只講入口，唔會提交。'


def install(api, tmp_path, answers, **kw):
    c,sid,lease,m,raw=setup(api,answers)
    path=tmp_path/'knowledge.json';path.write_bytes(REGISTRY.read_bytes())
    scope=json.loads(path.read_text())['sources'][0]['scope']
    port=PublicKnowledge(path,scope=kw.pop('scope',scope),**kw)
    api[1].state.voice_sessions.dialogue.knowledge_port=port
    return c,sid,lease,m,raw,path,port


def context(m):return json.loads(m.requests[-1]['messages'][-1].content)


def test_actual_passage_found_original_entry_and_replay(api,tmp_path):
    c,sid,l,m,raw,p,port=install(api,tmp_path,[{'kind':'answer','text':ANSWER}])
    r=send(c,sid,l,1,QUESTION);assert r.status_code==200,r.text
    ctx=context(m);assert ctx['information_status']['knowledge']=='FOUND'
    assert '繳費設定' in ctx['sources']['institution'][0]['text']
    assert r.json()['content_acceptance']['source_refs']
    replay=send(c,sid,l,1,QUESTION);assert replay.json()['replayed'] and len(m.requests)==1
    events=c.get(f'/api/voice-sessions/{sid}/events',headers=A,params={'limit':100}).json()['events']
    event=next(x for x in events if x['kind']=='assistant_response')
    assert event['data']['knowledge_result']['passages'][0]['url'].startswith('https://www.prudential.com.hk/')
    c.post(f'/api/voice-sessions/{sid}/end',headers=A)


@pytest.mark.parametrize('change,expected', [('disabled','STALE'),('scope','NOT_APPLICABLE'),('permission','UNAUTHORIZED'),('broken','UNAVAILABLE'),('foreign','NOT_APPLICABLE'),('deadline','NO_MATCH')])
def test_gap_states_do_not_leak_passages(api,tmp_path,change,expected):
    c,sid,l,m,raw,p,port=install(api,tmp_path,[{'kind':'answer','text':'今次資料未能確認你問嘅細節，可以向機構核對；未能確認唔代表冇規定。'}])
    q=QUESTION
    if change=='disabled':
        d=json.loads(p.read_text());d['sources'][0]['enabled']=False;p.write_text(json.dumps(d))
    if change=='scope':port.scope={**port.scope,'region':'MO'}
    if change=='permission':port.authorized=False
    if change=='broken':p.write_text('{broken')
    if change=='foreign':q='友邦香港轉扣款戶口有咩網上入口？'
    if change=='deadline':q='保誠香港最遲邊日提交先保證生效？'
    r=send(c,sid,l,1,q);assert r.status_code==200,r.text
    ctx=context(m);assert ctx['information_status']['knowledge']==expected
    assert not ctx['sources']['institution']
    c.post(f'/api/voice-sessions/{sid}/end',headers=A)


def test_disable_after_generation_fails_closed(api,tmp_path):
    c,sid,l,m,raw,p,port=install(api,tmp_path,[{'kind':'answer','text':ANSWER}])
    original=m.complete_structured
    async def disable(**kw):
        result=await original(**kw)
        d=json.loads(p.read_text());d['sources'][0]['enabled']=False;p.write_text(json.dumps(d))
        return result
    m.complete_structured=disable
    r=send(c,sid,l,1,QUESTION);assert r.status_code==409 and 'VOICE_KNOWLEDGE_CHANGED' in r.text
    c.post(f'/api/voice-sessions/{sid}/end',headers=A)


def test_disabled_source_cannot_reuse_prior_assistant_as_evidence(api,tmp_path):
    c,sid,l,m,raw,p,port=install(api,tmp_path,[{'kind':'answer','text':ANSWER},{'kind':'answer','text':ANSWER}])
    assert send(c,sid,l,1,QUESTION).status_code==200
    d=json.loads(p.read_text());d['sources'][0]['enabled']=False;p.write_text(json.dumps(d))
    replay=send(c,sid,l,1,QUESTION);assert replay.status_code==409 and len(m.requests)==1
    r=send(c,sid,l,2,'頭先講嘅入口仲適用嗎？');assert r.status_code==422,r.text
    assert not any(x['role']=='assistant' for x in context(m)['history'])
    assert any(x['role']=='user' for x in context(m)['history'])
    c.post(f'/api/voice-sessions/{sid}/end',headers=A)


@pytest.mark.parametrize('text',['保誠規定必須交銀行結單。','最遲28日提交就保證生效。','我已經幫你改好。','提交後就開始計處理時間。'])
def test_found_not_blanket_protected_claim_permission(api,tmp_path,text):
    c,sid,l,m,raw,p,port=install(api,tmp_path,[{'kind':'answer','text':text}])
    r=send(c,sid,l,1,QUESTION);assert r.status_code==422,r.text
    assert context(m)['sources']['institution']
    c.post(f'/api/voice-sessions/{sid}/end',headers=A)


def test_replace_source_and_general_question(api,tmp_path):
    c,sid,l,m,raw,p,port=install(api,tmp_path,[{'kind':'answer','text':'整理資料同發出申請係兩回事。'}])
    r=send(c,sid,l,1,'整理好資料是否就等於提出申請？');assert r.status_code==200
    assert not context(m)['sources']['institution']
    # Alternate official copy with a new registration identity is used on next lookup.
    d=json.loads(p.read_text());d['sources'][0]['id']='replacement-official-copy';p.write_text(json.dumps(d))
    import asyncio
    result=asyncio.run(port.lookup(question=QUESTION,session_id=sid))
    assert all(x.startswith('replacement-official-copy/') for x in result.source_refs)
    c.post(f'/api/voice-sessions/{sid}/end',headers=A)


def test_rtc_candidate_profile_injects_knowledge_at_original_route(api, monkeypatch):
    from apps.voice_worker.quality import TestTrace
    from src.adapters import voice_candidate_profile
    profile={'llm_selected':'offline', 'instruction_revision':'procedure-provenance-v3-consultation-v1',
             'communication_revision':'voice.communication.v2', 'knowledge':{'mode':'PUBLIC_DEMO_ONLY',
             'registry':str(REGISTRY.resolve()), 'scope':json.loads(REGISTRY.read_text())['sources'][0]['scope'], 'authorized':True}}
    # Only replace the supplier boundary; the actual configured RTC route builds
    # VoiceDialogue and KnowledgePort from the operator's profile.
    profile.pop('llm_trust_env',None)
    c,sid,l,m,raw=setup(api,[{'kind':'answer','text':ANSWER}])
    m.client=object()
    monkeypatch.setenv('VEFIN_VOICE_AUTH_MODE','local')
    monkeypatch.setattr(TestTrace,'node_profile',lambda self:profile)
    monkeypatch.setattr(TestTrace,'restored_context',lambda self:[])
    monkeypatch.setattr(TestTrace,'event',lambda *a,**kw:None)
    monkeypatch.setattr(voice_candidate_profile,'candidate_node',lambda *a,**kw:m)
    r=send(c,sid,l,1,QUESTION)
    assert r.status_code==200,r.text
    assert context(m)['information_status']['knowledge']=='FOUND'
    assert r.json()['content_acceptance']['source_refs']
    c.post(f'/api/voice-sessions/{sid}/end',headers=A)


def test_timing_question_is_not_effect_assertion_original_entry(api,tmp_path):
    answer='保誠香港人壽保單嘅自動轉賬資料，可以喺 myPrudential 入面辦理：登入後揀「繳費設定」，再按「請選擇保單」揀你想更改嘅保單。你話下個月先考慮轉扣款戶口、暫時未提交，咁本對話冇任何提交或更改；實際保單狀態我哋呢度查唔到。另外，具體遞交後幾時生效、截止安排，要睇機構公布或向保誠核對。'
    c,sid,l,m,raw,p,port=install(api,tmp_path,[{'kind':'answer','text':answer}])
    r=send(c,sid,l,1,QUESTION)
    assert r.status_code==200,r.text
    from opencc import OpenCC
    assert OpenCC('t2s').convert(r.json()['text'])==OpenCC('t2s').convert(answer)
    assert any((o.get('raw_reply') or {}).get('text')==answer for o in raw)
    c.post(f'/api/voice-sessions/{sid}/end',headers=A)

@pytest.mark.parametrize('text',[
    '遞交後就會生效。',
    '遞交後幾時生效要問機構；提交後就開始計處理。',
    '遞交後幾時生效要問機構，但最遲28日交就保證生效。',
    '未提交即代表未生效。',
])
def test_timing_question_does_not_license_other_assertions(text):
    assert accept_body(text)['candidate_status']=='REJECTED_PROTECTED_ASSERTION'
