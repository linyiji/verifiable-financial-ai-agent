"""V04 authority/journal contracts; never audio or human qualification."""
import asyncio,json
from types import SimpleNamespace

from src.application.voice_dialogue import DialogueReply,VoiceDialogue,negated_business_only
from tests.voice.test_continuous_voice_backend import api,A,B

W={'Authorization':'Bearer '+'w'*32}

class Model:
    def __init__(self):
        self.calls=[]
        self.kind='conversation'
    async def complete_structured(self,**kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output=DialogueReply(kind=self.kind,text='请先明确期间和计价单位。'),provider='UNIT_ONLY',actual_model='UNIT_ONLY')


def begin(client,key='ordinary'):
    r=client.post('/api/voice-sessions',json={'interaction_mode':'conversation'},headers={**A,'Idempotency-Key':key});assert r.status_code==201
    sid=r.json()['id'];claim=client.post(f'/internal/voice/{sid}/claim',headers=W,json={'worker_id':'unit-v04'});assert claim.status_code==200
    return sid,claim.json()['lease_id']


def payload(lease,n,text,generate=True):
    return {'lease_id':lease,'turn_id':f'connection:{n}','text':text,'generate':generate,
            'metadata':{'turn_id':f'connection:{n}','connection_id':'connection','track_sid':'track', 'turn':n,'input_epoch':n}}


def test_journal_context_immutable_idempotent_no_business_actions(api):
    client,app,application=api;model=Model();app.state.voice_sessions.dialogue=VoiceDialogue(app.state.voice_sessions,model)
    sid,lease=begin(client);route=f'/internal/voice/{sid}/dialogue'
    first=payload(lease,1,'研究可口可乐，金额八十万欧元，先讨论。')
    assert client.post(route,headers=W,json=first).status_code==200
    second=payload(lease,2,'不是八十万，改成十八万，保留现金流问题。')
    assert client.post(route,headers=W,json=second).status_code==200
    context=json.loads(model.calls[-1]['messages'][-1].content)
    assert any('八十万欧元' in h['content'] for h in context['voice_history'])
    assert '十八万' in context['current_utterance']
    duplicate=client.post(route,headers=W,json=first);assert duplicate.status_code==200 and duplicate.json()['replayed']
    assert len(model.calls)==2
    assert client.post(route,headers=W,json={**first,'text':'改写原文'}).json()['error']['code']=='VOICE_TURN_CONFLICT'
    model.kind='business_action_request'
    for n,text in enumerate(['好','可以','不要启动','确认发布'],3):
        r=client.post(route,headers=W,json=payload(lease,n,text))
        assert r.status_code==200
        if text=='不要启动':
            assert r.json()['reply_kind']=='conversation'
        else:
            assert '尚未执行' in r.json()['text']
    events=client.get(f'/api/voice-sessions/{sid}/events',headers=A,params={'limit':500}).json()['events']
    assert len([e for e in events if e['kind']=='conversation_turn'])==6
    assert all(e['data']['actions_executed']==[] for e in events if e['kind']=='assistant_response')
    assert application.repository._runs=={} and getattr(app.state, "research_task_service", None) is None
    assert client.get(f'/api/voice-sessions/{sid}/events',headers=B).status_code==404
    client.post(f'/api/voice-sessions/{sid}/end',headers=A)
    assert client.post(route,headers=W,json=payload(lease,7,'晚到结果')).status_code==410


def test_default_preview_and_modes_conflict(api):
    client,app,_=api
    old=client.post('/api/voice-sessions',headers={**A,'Idempotency-Key':'old'},json={}).json()
    assert old['interaction_mode']=='preview'
    assert client.post('/api/voice-sessions',headers={**A,'Idempotency-Key':'old'},json={'interaction_mode':'conversation'}).status_code==409
    claim=client.post(f"/internal/voice/{old['id']}/claim",headers=W,json={'worker_id':'unit-v04'}).json()
    assert client.post(f"/internal/voice/{old['id']}/dialogue",headers=W,json=payload(claim['lease_id'],1,'普通问题')).json()['error']['code']=='VOICE_CONVERSATION_DISABLED'


def test_progress_no_bound_task_is_truthful(api):
    client,app,_=api;model=Model();model.kind='progress';app.state.voice_sessions.dialogue=VoiceDialogue(app.state.voice_sessions,model)
    sid,lease=begin(client,'progress')
    r=client.post(f'/internal/voice/{sid}/dialogue',headers=W,json=payload(lease,1,'进度呢？'))
    assert r.status_code==200 and r.json()['text']=='当前没有绑定研究任务，无法查询研究进度。'


def test_release_fences_old_worker_without_extending_deadline(api):
    client,_,_=api;sid,lease=begin(client,'release')
    before=client.get(f'/api/voice-sessions/{sid}',headers=A).json()
    r=client.post(f'/internal/voice/{sid}/release',headers=W,json={'lease_id':lease})
    assert r.status_code==200 and r.json()['released']
    claimed=client.post(f'/internal/voice/{sid}/claim',headers=W,json={'worker_id':'replacement'})
    assert claimed.status_code==200 and claimed.json()['lease_id']!=lease
    assert claimed.json()['session']['expires_at']==before['expires_at']
    assert client.post(f'/internal/voice/{sid}/poll',headers=W,json={'lease_id':lease}).json()['error']['code']=='VOICE_LEASE_LOST'
    assert client.post(f'/internal/voice/{sid}/dialogue',headers=W,json=payload(lease,1,'迟到旧Worker')).status_code==409
    client.post(f'/api/voice-sessions/{sid}/end',headers=A)
    assert client.post(f'/internal/voice/{sid}/release',headers=W,json={'lease_id':claimed.json()['lease_id']}).status_code==410


def test_negated_business_guard_does_not_authorize_positive_action():
    assert negated_business_only(
        '不是正3万元，是负3亿元；不要启动研究。',
    )
    assert not negated_business_only(
        '不要启动研究，改为发布报告。',
    )
    assert not negated_business_only(
        '不要启动研究并发布报告。',
    )
    assert not negated_business_only(
        '好，可以启动研究并发布报告。',
    )
    assert negated_business_only('不要启动研究，也不要发布报告。')


def test_negative_correction_survives_wrong_model_kind_but_positive_action_is_fenced(api):
    client,app,_=api
    class WrongKind:
        async def complete_structured(self,**kwargs):
            return SimpleNamespace(
                output=DialogueReply(kind='business_action_request',text='未启动研究；金额是负3亿元，不是正3万元。'),
                provider='UNIT_ONLY',actual_model='UNIT_ONLY',
            )
    app.state.voice_sessions.dialogue=VoiceDialogue(app.state.voice_sessions,WrongKind())
    sid,lease=begin(client,'wrong-kind')
    route=f'/internal/voice/{sid}/dialogue'
    negative=client.post(route,headers=W,json=payload(lease,1,'不是正3万元，是负3亿元；不要启动研究。'))
    assert negative.status_code==200
    assert negative.json()['reply_kind']=='conversation' and '负3亿元' in negative.json()['text']
    positive=client.post(route,headers=W,json=payload(lease,2,'好，可以启动研究并发布报告。'))
    assert positive.status_code==200
    assert positive.json()['reply_kind']=='business_action_request' and '尚未执行' in positive.json()['text']
    events=client.get(f'/api/voice-sessions/{sid}/events',headers=A).json()['events']
    answers=[e for e in events if e['kind']=='assistant_response']
    assert answers[0]['data']['raw_reply_kind']=='business_action_request'
    assert answers[0]['data']['semantic_guard']=='negated_business_request_preserves_correction'
    assert answers[1]['data']['semantic_guard']=='positive_business_verb_fenced'
    assert all(e['data']['actions_executed']==[] for e in answers)


def test_model_claim_of_execution_cannot_authorize_negated_request(api):
    client,app,_=api
    class FalseExecutionClaim:
        async def complete_structured(self,**kwargs):
            return SimpleNamespace(
                output=DialogueReply(kind='business_action_request',text='已启动研究，金额改为负3亿元。'),
                provider='UNIT_ONLY',actual_model='UNIT_ONLY',
            )
    app.state.voice_sessions.dialogue=VoiceDialogue(app.state.voice_sessions,FalseExecutionClaim())
    sid,lease=begin(client,'false-execution-claim')
    response=client.post(f'/internal/voice/{sid}/dialogue',headers=W,
                         json=payload(lease,1,'不是正3万元，是负3亿元；不要启动研究。'))
    assert response.status_code==200
    assert response.json()['reply_kind']=='business_action_request'
    assert response.json()['text']=='这项研究操作尚未执行，请在研究界面核对对象和参数并明确确认。'
    events=client.get(f'/api/voice-sessions/{sid}/events',headers=A).json()['events']
    answers=[e for e in events if e['kind']=='assistant_response']
    assert answers[0]['data']['semantic_guard']=='model_claimed_execution_fenced'
    assert answers[0]['data']['actions_executed']==[]


def test_each_negated_action_survives_and_mixed_request_is_fenced(api):
    client,app,_=api
    class Misclassified:
        async def complete_structured(self,**kwargs):
            return SimpleNamespace(
                output=DialogueReply(kind='conversation',text='已记下，不启动研究；继续讨论更正。'),
                provider='UNIT_ONLY',actual_model='UNIT_ONLY',
            )
    app.state.voice_sessions.dialogue=VoiceDialogue(app.state.voice_sessions,Misclassified())
    sid,lease=begin(client,'mixed-business')
    route=f'/internal/voice/{sid}/dialogue'
    negative=client.post(route,headers=W,json=payload(lease,1,'不要启动研究，也不要发布报告。'))
    assert negative.status_code==200
    assert '不启动研究' in negative.json()['text'] and '不会发布报告' in negative.json()['text']
    mixed=client.post(route,headers=W,json=payload(lease,2,'不要启动研究，但请发布报告。'))
    assert mixed.status_code==200
    assert mixed.json()['reply_kind']=='business_action_request'
    assert '尚未执行' in mixed.json()['text']
    events=client.get(f'/api/voice-sessions/{sid}/events',headers=A).json()['events']
    answers=[e for e in events if e['kind']=='assistant_response']
    assert answers[0]['data']['semantic_guard']=='explicit_negated_actions_completed'
    assert answers[1]['data']['semantic_guard']=='positive_business_verb_fenced'
    assert all(e['data']['actions_executed']==[] for e in answers)
