import copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tests.voice.test_skill_partial_handoff import api,no_network,mock_budget,install3,Q,END,I
from tests.voice.test_skill_plan_v2 import understanding,expression,upd,send,A,events,work
from src.application.voice_skill import prepare,SkillError
from src.application.voice_skill_plan import plan,PendingUnderstanding,Expression,ReplyPlan,accept_expression,summary_materials




def test_original_entry_quoted_pending_partial_stop(api):
 text='入口係myPrudential繳費設定。你之前提到：「月份我仲未决定」。呢項資料尚未整理確認。已記低人工意願，未有真人接收；唔會提交，亦唔會話已經改好。'
 c,s,l,m,_=install3(api,[understanding(),expression(),understanding([upd('followup','YES','我希望人工跟進')],I,1),expression(text)])
 a=send(c,s,l,1,Q);assert a.status_code==200,a.text
 b=send(c,s,l,2,END);assert b.status_code==200,b.text
 st=b.json()['skill_state'];assert st['status']=='PARTIAL' and 'month' not in st['fields']
 assert st['fields']['followup']['value']=='YES' and st['handoff_status']=='REQUEST_RECORDED_NO_RECEIVER'
 assert st['reply_plan']['question_target'] is None and st['pending'][0]['recovery_attempts']==1
 ctx=json.loads(m.requests[-1]['messages'][-1].content)
 assert 'history' not in ctx and 'pending_sources' not in ctx['runtime_handoff']
 assert ctx['summary_materials']['user_statements'][0]['source_ref']['session_id']==s
 assert 'pending' not in ctx['communication_skill']['accepted_snapshot']
 assert send(c,s,l,2,END).json()['replayed'] and len(m.requests)==4
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

@pytest.mark.parametrize('body',[
 '你之前提到：「月份12月」。',
 '月份未決定，已經確認。',
 '月份2027年12月，會生效。',
 '我已提交更改。',
 '你之前提到：「月份我仲未决定」。所以已經改好。',
 '你之前提到：「月份我仲未决定」。我已安排人工跟進。',
 '保誠確認月份未決定。',
 '你之前提到：「月份我仲未决定」，所以生效月份暫時未定。',
])
def test_false_quote_or_authority_no_commit(api,body):
 c,s,l,m,_=install3(api,[understanding(),expression(),understanding([upd('followup','YES','我希望人工跟進')],I,1),expression(body)])
 assert send(c,s,l,1,Q).status_code==200
 b=send(c,s,l,2,END);assert b.status_code>=400,b.text
 assert len([e for e in events(c,s) if e['kind']=='assistant_response'])==1
 c.post(f'/api/voice-sessions/{s}/end',headers=A)


def test_quote_requires_matching_event_and_current_scope():
 w=work(Q,version='0.3.0');st,_=plan(w,PendingUnderstanding.model_validate(understanding()),{})
 p=st['pending'][0];w2={'turn_id':'next','raw_utterance':'整理','user_event_sources':{}}
 with pytest.raises(SkillError,match='SOURCE_INVALID'):summary_materials(w2,st,{})
 forged=copy.deepcopy(p);forged['source_ref']['session_id']='foreign';w2['user_event_sources']={'t':forged}
 with pytest.raises(SkillError,match='SOURCE_INVALID'):summary_materials(w2,st,{})
 st['pending'][0]['status']='SUPERSEDED';st['fields']['month']={'value':'12月'}
 assert not summary_materials(w2,st,{})['user_statements']


def test_user_operation_claim_not_receipt_material():
 w=work('月份未決定，我已辦理提交。',version='0.3.0');st,_=plan(w,PendingUnderstanding.model_validate(understanding()),{})
 assert all('已辦理' not in r['quote'] for r in st['summary_materials']['user_statements'])
 assert st['summary_materials']['capabilities']['business_write'] is False


def test_verbatim_excerpt_preserves_object_and_polarity():
 w=work('月份我仲未諗好。',version='0.3.0');st,p=plan(w,PendingUnderstanding.model_validate(understanding()),{})
 accept_expression(Expression(kind='answer',text='月份你之前講「仲未諗好」，我唔當已定。',plan_id=p.plan_id),p,st)
 for text in ['月份你之前講「諗好」。','月份你之前講「12月」。','你之前講「仲未諗好」。']:
  with pytest.raises(SkillError,match='QUOTE_UNSUPPORTED'):accept_expression(Expression(kind='answer',text=text,plan_id=p.plan_id),p,st)
 st['summary_materials']['user_statements'][0]['quote']='月份唔係12月'
 with pytest.raises(SkillError):accept_expression(Expression(kind='answer',text='月份你之前講「12月」。',plan_id=p.plan_id),p,st)

def test_active_accepted_month_quote_not_lost_when_pending_resolved():
 from src.application.voice_skill_plan import attributed_pending_text
 st={'summary_materials':{'accepted_fields':{'month':{'source':'current_user','turn_id':'t1','value':'UNKNOWN','evidence':'月份我仲未諗好'}},'user_statements':[]}}
 assert '有来源的用户陈述' in attributed_pending_text('月份你講過「仲未諗好」，暫時當未定。',st)
 for quote in ['十二月','已經辦理']:
  with pytest.raises(SkillError,match='QUOTE_UNSUPPORTED'):
   attributed_pending_text('月份你講過「'+quote+'」。',st)
 for bad in [{'source':'third_party'},{'value':'12月'},{'turn_id':None}]:
  changed=copy.deepcopy(st);changed['summary_materials']['accepted_fields']['month'].update(bad)
  with pytest.raises(SkillError,match='QUOTE_UNSUPPORTED'):
   attributed_pending_text('月份你講過「仲未諗好」。',changed)
