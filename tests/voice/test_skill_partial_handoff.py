import copy,json
import pytest
from tests.voice.test_skill_plan_v2 import api,no_network,mock_budget,install,understanding,expression,events,work,upd,send,A,QUESTION
from src.application.voice_skill_plan import PendingUnderstanding,plan
from src.application.voice_skill import SkillError

Q=QUESTION+'亦唔好話已經改好。'
END='我希望人工跟進，先整理，今次到此為止，不要繼續問。'
I=[dict(name='summary',evidence='先整理'),dict(name='stop_questions',evidence='今次到此為止，不要繼續問')]

def install3(api,answers):
 c,s,l,m,raw=install(api,answers)
 api[1].state.voice_sessions.dialogue.skill_config={**api[1].state.voice_sessions.dialogue.skill_config,'version':'0.3.0'}
 return c,s,l,m,raw

def recovered(ctx):
 h=ctx['runtime_handoff'];p=next(iter(h['pending_sources'].values()))
 return understanding([{**upd('month','UNKNOWN','月份我仲未决定'),'source_turn_id':p['source_ref']['turn_id']},upd('followup','YES','我希望人工跟進')],I,h['revision'])

def test_journal_pending_recovery_and_replay(api):
 c,s,l,m,raw=install3(api,[understanding(),expression(),recovered,expression('入口係myPrudential繳費設定；月份未定，期限及生效未能確認。只記錄人工需要，未有真人接收；唔提交，亦唔會話已經改好。')])
 a=send(c,s,l,1,Q);assert a.status_code==200,a.text
 st=a.json()['skill_state'];assert 'month' not in st['fields']
 assert st['pending'][0]['status']=='PENDING_EXTRACTION' and st['reply_plan']['question_target']=='followup'
 assert len(st['restrictions'])==2
 b=send(c,s,l,2,END);assert b.status_code==200,b.text
 st=b.json()['skill_state'];assert st['fields']['month']['source']=='historical_user_pending'
 assert st['pending'][0]['status']=='ACCEPTED' and st['status']=='COMPLETED'
 assert st['handoff_status']=='REQUEST_RECORDED_NO_RECEIVER'
 assert send(c,s,l,2,END).json()['replayed'] and len(m.requests)==4
 assert all('runtime_handoff' in json.loads(r['messages'][-1].content) for r in m.requests)
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

def test_unresolved_stop_is_partial_not_unknown(api):
 c,s,l,m,_=install3(api,[understanding(),expression(),understanding([upd('followup','YES','我希望人工跟進')],I,1),expression('入口係myPrudential繳費設定；月份資料尚未整理確認。只記錄人工需要，未有真人接收；期限及生效未能確認。唔會提交，亦唔會話已經改好。')])
 assert send(c,s,l,1,Q).status_code==200
 r=send(c,s,l,2,END);assert r.status_code==200,r.text
 st=r.json()['skill_state'];assert st['status']=='PARTIAL' and 'month' not in st['fields']
 assert st['pending'][0]['recovery_attempts']==1 and st['reply_plan']['question_target'] is None
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

def test_current_correction_wins(api):
 def correct(ctx):
  h=ctx['runtime_handoff'];p=next(iter(h['pending_sources'].values()))
  return understanding([{**upd('month','UNKNOWN','月份我仲未决定'),'source_turn_id':p['source_ref']['turn_id']},upd('month','12月','十二月')],revision=h['revision'])
 c,s,l,m,_=install3(api,[understanding(),expression(),correct,expression('月份更正為12月；入口仍係myPrudential繳費設定。')])
 assert send(c,s,l,1,Q).status_code==200
 r=send(c,s,l,2,'我更正月份係十二月。');assert r.status_code==200,r.text
 st=r.json()['skill_state'];assert st['fields']['month']['value']=='12月' and st['pending'][0]['status']=='SUPERSEDED'
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

@pytest.mark.parametrize('variant',['wrong_stop','fake_source','stale','bad_evidence','authority'])
def test_invalid_still_atomic(api,variant):
 u=understanding()
 if variant=='wrong_stop':u['intents']=[dict(name='stop_questions',evidence='暫時唔好提交')]
 if variant=='fake_source':u['updates']=[{**upd('month','UNKNOWN','月份我仲未决定'),'source_turn_id':'other-session'}]
 if variant=='stale':u['revision']=99
 if variant=='bad_evidence':u['updates']=[upd('month','12月','十二月')]
 if variant=='authority':u['permission']='execute'
 c,s,l,m,_=install3(api,[u]);r=send(c,s,l,1,Q);assert r.status_code>=400
 assert len(m.requests)==1 and not any(e['kind']=='assistant_response' for e in events(c,s))
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

@pytest.mark.parametrize('value,evidence', [('UNKNOWN','月份未諗好'),('REFUSED','月份唔想講'),('12月','12月')])
def test_actual_accepted_distinct_from_pending(value,evidence):
 st,p=plan(work(evidence,version='0.3.0'),PendingUnderstanding.model_validate(understanding([upd('month',value,evidence)])),{})
 assert st['fields']['month']['value']==value and not st.get('pending')

def test_missing_not_pending():
 st,p=plan(work('網上入口係邊？',version='0.3.0'),PendingUnderstanding.model_validate(understanding()),{})
 assert not st['pending'] and p.question_target=='month'




def test_disabled_source_rejects_pending_delivery(api,tmp_path):
 from pathlib import Path
 from tests.voice.test_skill_plan_v2 import REG
 c,s,l,m,_=install3(api,[understanding(),expression()]);d=api[1].state.voice_sessions.dialogue
 p=tmp_path/'registry.json';p.write_bytes(Path(REG).read_bytes());d.knowledge_port.registry=p
 def disable(ctx):
  data=json.loads(p.read_text());data['sources'][0]['enabled']=False;p.write_text(json.dumps(data))
  return expression()(ctx)
 m.answers[1]=disable
 assert send(c,s,l,1,Q).status_code>=400
 assert not any(e['kind']=='assistant_response' for e in events(c,s))
 c.post(f'/api/voice-sessions/{s}/end',headers=A)


def test_pending_cannot_be_spoken_as_accepted_unknown(api):
 c,s,l,m,_=install3(api,[understanding(),expression('月份未定，入口係myPrudential繳費設定。')])
 assert send(c,s,l,1,Q).status_code==422
 assert not any(e['kind']=='assistant_response' for e in events(c,s))
 c.post(f'/api/voice-sessions/{s}/end',headers=A)


def test_recovery_once_and_cross_session_reject():
 from src.application.voice_skill import prepare
 from types import SimpleNamespace
 w=work(Q,version='0.3.0');st,p=plan(w,PendingUnderstanding.model_validate(understanding()),{})
 def ev(state):return [SimpleNamespace(payload={'kind':'assistant_response','data':{'skill_state':state}}),SimpleNamespace(payload={'kind':'conversation_turn','event_id':'dialogue:input:t','text':Q})]
 with pytest.raises(SkillError,match='SESSION_MISMATCH'):prepare({'id':'consultation-dialogue','version':'0.3.0'},ev(st),session_id='foreign',turn_id='n',utterance='繼續')
 w2=prepare({'id':'consultation-dialogue','version':'0.3.0'},ev(st),session_id='s',turn_id='n',utterance='繼續')
 st2,_=plan(w2,PendingUnderstanding.model_validate(understanding(revision=1)),{})
 w3=prepare({'id':'consultation-dialogue','version':'0.3.0'},ev(st2),session_id='s',turn_id='o',utterance='繼續')
 assert not w3['pending_sources'] and st2['pending'][0]['recovery_attempts']==1


def test_followup_value_domain_not_free_prose():
 from pydantic import ValidationError
 with pytest.raises(ValidationError):PendingUnderstanding.model_validate(understanding([upd('followup','希望人工跟进','我希望人工跟進')]))
 for value,evidence in [('YES','我希望人工跟進'),('NO','不要人工跟進'),('UNKNOWN','人工跟進我未決定'),('REFUSED','人工跟進我拒絕回答')]:
  w=work(evidence,version='0.3.0');st,_=plan(w,PendingUnderstanding.model_validate(understanding([upd('followup',value,evidence)])),{})
  assert st['fields']['followup']['value']==value
 with pytest.raises(SkillError):plan(work('不要人工跟進',version='0.3.0'),PendingUnderstanding.model_validate(understanding([upd('followup','YES','不要人工跟進')])),{})
