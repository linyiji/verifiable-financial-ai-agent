"""Network forbidden. Independent v2 mocks; historical responses never rewritten."""
import asyncio
import copy
import json
from types import SimpleNamespace
from pathlib import Path
import pytest
from tests.voice.test_natural_dialogue import api,no_network,setup,send,A
from tests.voice.test_communication_skill import CFG,REG,upd,reply
from src.application.voice_skill import prepare,accept_proposals,SkillReply,SkillError
from src.application.voice_skill_plan import Understanding,Expression,plan,generate,accept_expression
from src.adapters.voice_knowledge import PublicKnowledge

@pytest.fixture(autouse=True)
def mock_budget(tmp_path,monkeypatch):
 p=tmp_path/'offline-mock-ledger.json'
 p.write_text(json.dumps({'state':'OPEN','limits':{'LLM':100,'TOTAL':100},'attempts':[]}))
 monkeypatch.setenv('VEFIN_VOICE_CALL_LEDGER',str(p))

CFG2={**CFG,'version':'0.2.0'}
QUESTION='保誠香港人壽扣款戶口網上入口係邊？月份我仲未决定，暫時唔好提交。'
BASE_TEXT='登入myPrudential，揀繳費設定。截止同生效未能確認；暫時唔提交。'

class Model:
 def __init__(self,answers):self.answers=list(answers);self.requests=[]
 async def complete_structured(self,**kw):
  self.requests.append(kw)
  from src.adapters.voice_call_budget import charge
  charge('LLM','OFFLINE_MOCK','NONE')
  answer=self.answers.pop(0)
  if isinstance(answer,BaseException):raise answer
  ctx=json.loads(kw['messages'][-1].content)
  if callable(answer):answer=answer(ctx)
  return SimpleNamespace(output=kw['response_model'].model_validate(answer),provider='OFFLINE_MOCK',actual_model='NONE',request_id=f'mock-{len(self.requests)}',input_tokens=None,output_tokens=None)

def understanding(updates=(),intents=(),revision=0):
 return {'revision':revision,'updates':list(updates),'intents':list(intents)}
def expression(text=BASE_TEXT,**extra):
 return lambda ctx:dict(kind='answer',text=text,plan_id=ctx['communication_skill']['reply_plan']['plan_id'],**extra)
def install(api,answers):
 c,s,l,_,raw=setup(api,[]);d=api[1].state.voice_sessions.dialogue;m=Model(answers);d.model=m;d.skill_config=CFG2
 d.knowledge_port=PublicKnowledge(REG,scope=json.load(open(REG))['sources'][0]['scope'])
 return c,s,l,m,raw

def work(text,**config):return prepare({**CFG2,**config},[],session_id='s',turn_id='t',utterance=text)
def events(c,s):return c.get(f'/api/voice-sessions/{s}/events',headers=A,params={'limit':100}).json()['events']


def test_original_entry_new_accepted_snapshot_then_expression_and_replay(api):
 c,s,l,m,raw=install(api,[understanding([upd('month','UNKNOWN','月份我仲未决定')]),expression()])
 r=send(c,s,l,1,QUESTION);assert r.status_code==200,r.text
 st=r.json()['skill_state'];assert st['fields']['month']['value']=='UNKNOWN'
 assert st['reply_plan']['question_target']=='followup' and st['status']=='WAITING_USER'
 ctx=json.loads(m.requests[1]['messages'][-1].content)
 assert ctx['communication_skill']['accepted_snapshot']['fields']['month']['value']=='UNKNOWN'
 assert ctx['communication_skill']['reply_plan']['based_on_task_revision']==1
 assert st['asked']=={} # API generated, not a real text or media delivery receipt.
 assert '人工' in r.json()['text']
 e=next(e for e in events(c,s) if e['kind']=='assistant_response')
 assert e['data']['model_contract']=='voice_skill_consultation_v2'
 assert [p['generator'] for p in e['data']['skill_parts']]==['MODEL','APPLICATION']
 assert 'next' not in next(x['raw'] for x in raw if x.get('event')=='skill_expression_raw')
 assert send(c,s,l,1,QUESTION).json()['replayed'] and len(m.requests)==2
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

@pytest.mark.parametrize('text,updates,policy,intents,target,status',[
 ('網上入口？',[], 'goal-led',[], 'month','WAITING_USER'),
 ('月份未諗好。',[upd('month','UNKNOWN','月份未諗好')],'goal-led',[], 'followup','WAITING_USER'),
 ('月份未決定，希望人工跟進，先整理。',[upd('month','UNKNOWN','月份未決定'),upd('followup','YES','希望人工跟進')],'goal-led',[dict(name='summary',evidence='先整理')],None,'COMPLETED'),
 ('月份不想說。',[upd('month','REFUSED','月份不想說')],'goal-led',[], 'followup','WAITING_USER'),
 ('只回答入口，簡短點。',[], 'responsive',[],None,'IN_PROGRESS'),
 ('先整理，不要繼續問。',[], 'goal-led',[dict(name='summary',evidence='先整理'),dict(name='stop_questions',evidence='不要繼續問')],None,'PARTIAL'),
 ('月份12月，先整理。',[upd('month','12月','12月')],'goal-led',[dict(name='summary',evidence='先整理')],'followup','WAITING_USER'),
])
def test_state_table(text,updates,policy,intents,target,status):
 w=work(text,policy=policy);st,p=plan(w,Understanding.model_validate(understanding(updates,intents)),{})
 assert p.question_target==target and p.after_delivery==status
 if '先整理' in text and updates:assert p.summary_scope
 if '不想說' in text:assert st['fields']['month']['status']=='DECLINED'
 assert not p.allowed_actions

@pytest.mark.parametrize('variant',['omitted','false_quote','third_person','wrong_value','stale','authority','intent'])
def test_understanding_failure_prevents_expression(api,variant):
 q=QUESTION;u=upd('month','UNKNOWN','月份我仲未决定');d=understanding([u])
 if variant=='omitted':d['updates']=[]
 if variant=='false_quote':u['evidence']='月份我仲未決定'
 if variant=='third_person':q='朋友話月份我仲未决定。'
 if variant=='wrong_value':u['value']='12月'
 if variant=='stale':d['revision']=99
 if variant=='authority':d['next']='SUMMARIZE'
 if variant=='intent':d['intents']=[{'name':'summary','evidence':'暫時唔好提交'}]
 c,s,l,m,_=install(api,[d]);r=send(c,s,l,1,q);assert r.status_code>=400,r.text
 assert len(m.requests)==1 and not any(e['kind']=='assistant_response' for e in events(c,s))
 assert send(c,s,l,1,q).status_code==409 and len(m.requests)==1
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

@pytest.mark.parametrize('bad',[
 expression('你預計幾月考慮？'),expression('你預計12月考慮。'),
 expression('保誠規定三日生效。'),expression('我已經安排人工跟進。'),
 lambda ctx:dict(kind='answer',text='明白。',plan_id='old'),
 lambda ctx:dict(kind='answer',text='明白。',plan_id=ctx['communication_skill']['reply_plan']['plan_id'],next='CLOSE'),
])
def test_expression_failure_atomic_no_retry_then_new_turn_allowed(api,bad):
 c,s,l,m,_=install(api,[understanding([upd('month','UNKNOWN','月份我仲未决定')]),bad,
   understanding([upd('month','12月','12月')]),expression('按你講嘅12月先考慮；截止未有資料。')])
 assert send(c,s,l,1,QUESTION).status_code>=400
 assert not any(e['kind']=='assistant_response' for e in events(c,s))
 assert any(e['kind']=='skill_attempt_finished' and e['data']['status']=='NOT_DELIVERED' for e in events(c,s))
 assert send(c,s,l,1,QUESTION).status_code==409 and len(m.requests)==2
 r=send(c,s,l,2,'我打算12月先考慮。');assert r.status_code==200,r.text
 assert r.json()['skill_state']['revision']==1 # failed tentative unknown never committed
 assert len(m.requests)==4
 c.post(f'/api/voice-sessions/{s}/end',headers=A)


def test_three_turn_source_recheck_correction_switch_close(api):
 c,s,l,m,raw=install(api,[understanding([upd('month','UNKNOWN','月份我仲未决定')]),expression(),
  understanding([upd('month','12月','十二月')],revision=1),expression('按最新資料，12月先考慮；截止未有資料，唔會提交，亦唔會話已經改好。'),
  understanding([upd('followup','YES','我希望人工跟進')],[dict(name='summary',evidence='先整理')],revision=2),
  expression('入口仍係myPrudential繳費設定。12月先考慮；只記錄人工需要，未有真人接收；唔會提交，亦唔會話已經改好。')])
 assert send(c,s,l,1,QUESTION).status_code==200
 r=send(c,s,l,2,'更正做十二月，換成穩健顧問，簡短啲，只回答截止日，唔好話已經改好。');assert r.status_code==200,r.text
 st=r.json()['skill_state'];assert st['selection']['persona']=='steady-advisor' and st['reply_plan']['question_target'] is None
 r=send(c,s,l,3,'我希望人工跟進，先整理，不要繼續問。')
 # Preserve this original mock's omitted stop. R5 must now reject it, not
 # manufacture the missing model intent or commit its proposed followup.
 assert r.status_code==422 and 'OMITTED_EXPLICIT_QUESTION_STOP' in r.text
 assert len(m.requests)==5
 accepted=[e for e in events(c,s) if e['kind']=='assistant_response']
 assert len(accepted)==2
 c.post(f'/api/voice-sessions/{s}/end',headers=A)


def test_disabled_source_after_understanding_still_rejected(api,tmp_path):
 c,s,l,m,raw=install(api,[understanding(),expression()]);d=api[1].state.voice_sessions.dialogue
 p=tmp_path/'knowledge.json';p.write_bytes(Path(REG).read_bytes());d.knowledge_port.registry=p
 def disable(ctx):
  data=json.loads(p.read_text());data['sources'][0]['enabled']=False;p.write_text(json.dumps(data))
  return expression()(ctx)
 m.answers[1]=disable
 assert send(c,s,l,1,'保誠香港人壽網上入口？').status_code>=400
 assert not any(e['kind']=='assistant_response' for e in events(c,s))
 c.post(f'/api/voice-sessions/{s}/end',headers=A)


def test_two_calls_reserved_metered_and_unused_released(tmp_path,monkeypatch):
 p=tmp_path/'mock-ledger.json'
 def ledger(n):p.write_text(json.dumps({'state':'OPEN','limits':{'LLM':n,'TOTAL':n},'attempts':[]}))
 monkeypatch.setenv('VEFIN_VOICE_CALL_LEDGER',str(p))
 w=work('月份未決定。');ctx={'skill_knowledge':{}}
 ledger(1);m=Model([])
 with pytest.raises(RuntimeError,match='INSUFFICIENT'):asyncio.run(generate(m,w,ctx))
 assert not m.requests
 ledger(2);m=Model([understanding([upd('month','UNKNOWN','月份未決定')]),expression('月份仍未決定；時限未有資料。')])
 asyncio.run(generate(m,w,ctx));d=json.loads(p.read_text());assert len(d['attempts'])==2 and d['reservations'][0]['state']=='RELEASED'
 ledger(2);m=Model([understanding(revision=9)])
 with pytest.raises(SkillError):asyncio.run(generate(m,w,ctx))
 d=json.loads(p.read_text());assert len(d['attempts'])==1 and d['reservations'][0]['released_unused']==1


def test_shared_deadline_cancel_does_not_deliver_or_reset(tmp_path,monkeypatch):
 p=tmp_path/'ledger.json';p.write_text(json.dumps({'state':'OPEN','limits':{'LLM':2,'TOTAL':2},'attempts':[]}));monkeypatch.setenv('VEFIN_VOICE_CALL_LEDGER',str(p))
 class Slow(Model):
  async def complete_structured(self,**kw):
   result=await super().complete_structured(**kw);await asyncio.sleep(.04);return result
 m=Slow([understanding(),expression('一般整理同正式提交有分別。')]);seen=[]
 async def run():
  async with asyncio.timeout(.06):return await generate(m,work('一般整理係咩？'),{},observer=seen.append)
 with pytest.raises(TimeoutError):asyncio.run(run())
 assert len(m.requests)==2 and not any(x['event']=='skill_expression_accepted' for x in seen)
 assert json.loads(p.read_text())['reservations'][0]['state']=='RELEASED'


def test_old_contract_and_raw_still_reject():
 w=prepare(CFG,[],session_id='s',turn_id='t',utterance='月份我仲未决定。')
 old=SkillReply.model_validate(reply(0,'你想唔想有真人之後跟進？',[upd('month','UNKNOWN','月份我仲未决定')],'SUMMARIZE'))
 with pytest.raises(SkillError,match='PREMATURE_SUMMARY'):accept_proposals(w,old)
 assert old.next=='SUMMARIZE'




def test_style_only_does_not_increment_fact_revision_or_grant_authority():
 w=work('換成穩健顧問，簡短點，只回答。')
 st,p=plan(w,Understanding.model_validate(understanding()),{})
 assert st['communication_revision']==1 and st['revision']==0
 assert p.question_target is None and not p.allowed_actions
 assert st['selection']['persona']=='steady-advisor'


def test_generation_plan_is_not_reusable_cross_session():
 u=Understanding.model_validate(understanding())
 a=work('入口？');s,p=plan(a,u,{})
 b=prepare(CFG2,[],session_id='another',turn_id='t',utterance='入口？');s2,p2=plan(b,u,{})
 assert p.plan_id!=p2.plan_id
 with pytest.raises(SkillError,match='STALE_PLAN'):accept_expression(Expression(plan_id=p.plan_id,kind='answer',text='一般資料。'),p2,s2)


def test_cancel_understanding_does_not_start_expression(tmp_path,monkeypatch):
 p=tmp_path/'ledger.json';p.write_text(json.dumps({'state':'OPEN','limits':{'LLM':2,'TOTAL':2},'attempts':[]}));monkeypatch.setenv('VEFIN_VOICE_CALL_LEDGER',str(p))
 m=Model([asyncio.CancelledError()])
 with pytest.raises(asyncio.CancelledError):asyncio.run(generate(m,work('入口？'),{}))
 d=json.loads(p.read_text());assert len(m.requests)==1 and d['reservations'][0]['released_unused']==1


def test_offline_receipt_artifact(api):
 import os
 path=os.getenv('VEFIN_SKILL_OFFLINE_EVIDENCE')
 c,s,l,m,raw=install(api,[understanding([upd('month','UNKNOWN','月份我仲未决定')],[dict(name='summary',evidence='先整理')]),expression()])
 r=send(c,s,l,1,QUESTION+'先整理。');assert r.status_code==200,r.text
 assert r.json()['skill_state']['reply_plan']['summary_scope']==['month']
 assert r.json()['skill_state']['reply_plan']['question_target']=='followup'
 if path:
  Path(path).write_text(json.dumps({'type':'OFFLINE_MOCK_NOT_SUPPLIER_OR_MEDIA','user':QUESTION+'先整理。',
   'requests':[{'schema':x['schema_name'],'messages':[{'role':a.role,'content':a.content} for a in x['messages']]} for x in m.requests],
   'observations':raw,'result':r.json(),'journal':events(c,s)},ensure_ascii=False,indent=2))
 c.post(f'/api/voice-sessions/{s}/end',headers=A)


def test_explicit_budget_required(monkeypatch):
 monkeypatch.delenv('VEFIN_VOICE_CALL_LEDGER',raising=False)
 m=Model([])
 with pytest.raises(SkillError,match='EXPLICIT_BUDGET_REQUIRED'):asyncio.run(generate(m,work('入口？'),{}))
 assert not m.requests


def test_original_entry_absolute_deadline_cleanup(api,monkeypatch):
 import src.application.voice_dialogue as module
 c,s,l,m,_=install(api,[understanding(),expression('一般整理資料不等於提交。')])
 original=m.complete_structured
 async def slow(**kw):
  result=await original(**kw);await asyncio.sleep(.04);return result
 m.complete_structured=slow
 monkeypatch.setattr(module,'get_settings',lambda:SimpleNamespace(voice_llm=SimpleNamespace(dialogue_deadline_seconds=.06)))
 r=send(c,s,l,1,'一般整理係咩？');assert r.status_code>=400
 ev=events(c,s);assert not any(e['kind']=='assistant_response' for e in ev)
 assert any(e['kind']=='skill_attempt_finished' and e['data']['status']=='NOT_DELIVERED' for e in ev)
 assert len(m.requests)<=2
 c.post(f'/api/voice-sessions/{s}/end',headers=A)
