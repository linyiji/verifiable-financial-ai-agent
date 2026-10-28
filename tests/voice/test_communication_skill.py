import json,copy
from types import SimpleNamespace
import pytest
from tests.voice.test_natural_dialogue import api,no_network,setup,send,A
from src.application.voice_skill import load,prepare,accept_proposals,SkillReply,SkillError
from src.adapters.voice_knowledge import PublicKnowledge

CFG={'id':'consultation-dialogue','version':'0.1.0','persona':'efficient-partner','policy':'goal-led','depth':'core','verbosity':'concise'}
REG='docs/voice/knowledge/prudential-hk-payment-demo.json'
def reply(rev,text,updates=(),next='ANSWER'):
 return {'kind':'answer','text':text,'revision':rev,'updates':list(updates),'next':next}
def upd(field,value,evidence):return dict(field=field,value=value,evidence=evidence)
class Model:
 def __init__(self,answers):self.answers=list(answers);self.requests=[]
 async def complete_structured(self,**kw):
  self.requests.append(kw);assert kw['response_model'] is SkillReply
  return SimpleNamespace(output=SkillReply.model_validate(self.answers.pop(0)),provider='OFFLINE',actual_model='NONE',request_id='fixture')
def install(api,answers):
 c,sid,l,_,raw=setup(api,[]);d=api[1].state.voice_sessions.dialogue;m=Model(answers);d.model=m;d.skill_config=CFG
 scope=json.load(open(REG))['sources'][0]['scope'];d.knowledge_port=PublicKnowledge(REG,scope=scope)
 return c,sid,l,m,raw

def test_full_original_business_goal_and_no_match_inheritance(api):
 q1='保誠香港人壽扣款戶口網上入口係邊？唔好提交。'
 q2='我打算12月先考慮，唔需要人工跟進，唔好話已經改好。'
 a1='登入myPrudential揀繳費設定。你預計幾月考慮？'
 a2='按你意思12月先考慮，唔需要人工跟進；唔提交，亦唔會話已經改好。入口仍可參考myPrudential繳費設定。'
 c,s,l,m,raw=install(api,[reply(0,a1,next='ASK_MONTH'),reply(1,a2,[upd('month','12月','12月'),upd('followup','NO','唔需要人工跟進')],'SUMMARIZE')])
 assert send(c,s,l,1,q1).status_code==200
 r=send(c,s,l,2,q2);assert r.status_code==200,r.text
 st=r.json()['skill_state'];assert st['status']=='COMPLETED' and st['fields']['month']['year'] is None
 assert set(st['restrictions'])=={'prohibit_submission','prohibit_completion_claim'}
 ctx=json.loads(m.requests[1]['messages'][-1].content)
 assert ctx['knowledge_current']['status']=='NO_MATCH' and ctx['sources']['institution']
 assert 'consultation-dialogue' in m.requests[0]['messages'][0].content
 repeat=send(c,s,l,2,q2);assert repeat.json()['replayed'] and len(m.requests)==2
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

def test_persona_policy_and_stop_keeps_state_no_call(api):
 q1='保誠香港人壽網上入口？我打算下個月考慮。'
 c,s,l,m,_=install(api,[reply(0,'你是否想人工跟進？',[upd('month','下个月','下個月')],'ASK_FOLLOWUP'),reply(1,'已改為12月的諮詢意向；截止未能確認。',[upd('month','12月','十二月')])])
 assert send(c,s,l,1,q1).status_code==200
 r=send(c,s,l,2,'更正為十二月，換成穩健顧問，簡短啲，只回答截止日係幾時。');assert r.status_code==200,r.text
 st=r.json()['skill_state'];assert st['selection']==dict(persona='steady-advisor',policy='responsive',depth='core',verbosity='concise')
 assert st['history'][0]['superseded']['value']=='下个月'
 r=send(c,s,l,3,'停止諮詢。');assert r.status_code==200,r.text
 assert r.json()['skill_state']['status']=='CANCELLED' and len(m.requests)==2
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

@pytest.mark.parametrize('change', ['bad_revision','false_quote','wrong_value','third_person','already_answered','overreach'])
def test_bad_proposals_not_published(api,change):
 text='我打算12月考慮。';u=upd('month','12月','12月');r=reply(0,'只作諮詢。',[u])
 if change=='bad_revision':r['revision']=3
 if change=='false_quote':u['evidence']='十二月'
 if change=='wrong_value':u['value']='10月'
 if change=='third_person':text='職員話佢12月考慮。'
 if change=='already_answered':r['next']='ASK_MONTH'
 if change=='overreach':r['updates'][0]['field']='permission'
 c,s,l,m,_=install(api,[r]);res=send(c,s,l,1,text);assert res.status_code>=400
 ev=c.get(f'/api/voice-sessions/{s}/events',headers=A).json()['events'];assert not any(x['kind']=='assistant_response' for x in ev)
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

def test_bundle_pin_and_failed_switch_preserves_current():
 b=load(CFG);assert b['persona']['id']=='efficient-partner'
 with pytest.raises(SkillError):load({**CFG,'sha256':'wrong'})
 with pytest.raises(SkillError):load({**CFG,'id':'unregistered'})
 w=prepare(CFG,[],session_id='s',turn_id='1',utterance='換成神秘顧問');assert w['selection_errors'] and w['state']['selection']['persona']=='efficient-partner'
 w=prepare(CFG,[],session_id='s',turn_id='1',utterance='換成好奇訪談者，詳細解釋原因，簡短啲。');assert w['state']['selection']['persona']=='curious-interviewer' and w['state']['selection']['depth']=='detail' and w['state']['selection']['verbosity']=='concise'

def test_source_disabled_not_carried_and_generation_fenced(api,tmp_path):
 c,s,l,m,_=install(api,[reply(0,'登入myPrudential揀繳費設定。你預計幾月考慮？',next='ASK_MONTH'),reply(1,'登入myPrudential揀繳費設定。')]);d=api[1].state.voice_sessions.dialogue
 p=tmp_path/'source.json';p.write_bytes(open(REG,'rb').read());d.knowledge_port.registry=p
 assert send(c,s,l,1,'保誠香港人壽網上入口？').status_code==200
 data=json.loads(p.read_text());data['sources'][0]['enabled']=False;p.write_text(json.dumps(data))
 assert send(c,s,l,2,'咁截止日呢？').status_code==422
 assert send(c,s,l,1,'保誠香港人壽網上入口？').status_code>=400
 c.post(f'/api/voice-sessions/{s}/end',headers=A)
 assert send(c,s,l,3,'再講入口').status_code>=400


def test_normalize_month_separately_and_reject_unspoken_question():
 w=prepare(CFG,[],session_id='s',turn_id='t',utterance='我打算十二月先考慮。')
 r=SkillReply.model_validate(reply(0,'你想唔想人工跟進？',[upd('month','十二月','十二月')],'ASK_FOLLOWUP'))
 st=accept_proposals(w,r);assert st['fields']['month']['value']=='12月' and st['fields']['month']['evidence']=='十二月'
 r.text='收到，十二月先考慮。'
 with pytest.raises(SkillError,match='QUESTION_NOT_DELIVERABLE'):accept_proposals(w,r)


def test_rtc_budget_does_not_reset_or_consume_provider_total(tmp_path):
 from src.adapters.voice_call_budget import charge_rtc_input
 p=tmp_path/'ledger.json';p.write_text(json.dumps({'state':'OPEN','limits':{'RTC':2,'TOTAL':0},'attempts':[]}))
 charge_rtc_input(p,'s1',1,'a');charge_rtc_input(p,'s2',1,'b')
 with pytest.raises(RuntimeError):charge_rtc_input(p,'s3',1,'c')
 d=json.loads(p.read_text());assert len(d['rtc_inputs'])==2 and not d['attempts']


def test_cross_session_and_generation_not_inherited():
 w=prepare(CFG,[],session_id='s1',turn_id='g1',utterance='我打算12月。')
 st=accept_proposals(w,SkillReply.model_validate(reply(0,'收到。',[upd('month','12月','12月')])))
 ev=SimpleNamespace(payload={'kind':'assistant_response','data':{'skill_state':st}})
 with pytest.raises(SkillError,match='SESSION_MISMATCH'):prepare(CFG,[ev],session_id='s2',turn_id='g2',utterance='继续')
 newer=prepare(CFG,[ev],session_id='s1',turn_id='g2',utterance='继续')
 with pytest.raises(SkillError,match='STALE_REVISION'):accept_proposals(newer,SkillReply.model_validate(reply(0,'旧答案。')))


def test_no_submission_is_not_followup_refusal():
 w=prepare(CFG,[],session_id='s',turn_id='t',utterance='暫時唔好提交。')
 r=SkillReply.model_validate(reply(0,'你預計幾月？',[upd('followup','REFUSED','暫時唔好提交')],'ASK_MONTH'))
 with pytest.raises(SkillError,match='VALUE_EVIDENCE_MISMATCH'):accept_proposals(w,r)


@pytest.mark.parametrize('bad_summary',[False,True])
def test_three_turn_inherited_source_and_historical_summary(api,bad_summary):
    text='入口仍係myPrudential繳費設定。摘要：12月先考慮，希望人工跟進，只記錄需求，未有真人接收。'
    if bad_summary:text='「網上入口」具體位置同機構截止、生效安排，均無機構來源可核，建議向保誠香港核對。'
    c,s,l,m,_=install(api,[reply(0,'登入myPrudential揀繳費設定。你預計幾月考慮？',next='ASK_MONTH'),
        reply(1,'你是否希望人工跟進？',[upd('month','12月','12月')],'ASK_FOLLOWUP'),
        reply(2,text,[upd('followup','YES','我希望人工跟進')],'SUMMARIZE')])
    assert send(c,s,l,1,'保誠香港人壽網上入口？唔好提交。').status_code==200
    assert send(c,s,l,2,'我打算12月先考慮。').status_code==200
    r=send(c,s,l,3,'我希望人工跟進，唔好話已經改好，整理摘要。')
    ctx=json.loads(m.requests[-1]['messages'][-1].content)
    assert ctx['knowledge_current']['status']=='NO_MATCH' and ctx['sources']['institution']
    if bad_summary:assert r.status_code==422 and 'SKILL_DENIES_VALID_NAVIGATION' in r.text
    else:assert r.status_code==200 and r.json()['skill_state']['status']=='COMPLETED'
    c.post(f'/api/voice-sessions/{s}/end',headers=A)


def test_navigation_known_does_not_authorize_cutoff_or_block_known_unknown_mix():
 from src.application.voice_skill import check_skill_body
 knowledge={'status':'FOUND','passages':[{'topic':'navigation'}]}
 check_skill_body('入口係myPrudential，截止日未知。',knowledge)
 with pytest.raises(SkillError):check_skill_body('入口資料目前未知。',knowledge)


def test_real_cantonese_followup_question_not_false_rejected():
 w=prepare(CFG,[],session_id='s',turn_id='t',utterance='我打算十二月先考慮。')
 r=SkillReply.model_validate(reply(0,'你希唔希望之後有真人跟進呢個諮詢？我只係記錄意願。',[upd('month','十二月','十二月')],'ASK_FOLLOWUP'))
 assert accept_proposals(w,r)['next']=='ASK_FOLLOWUP'
 r.text='之後有真人跟進呢個諮詢。'
 with pytest.raises(SkillError,match='QUESTION_NOT_DELIVERABLE'):accept_proposals(w,r)


def test_real_unknown_month_literal_keeps_evidence(api):
 c,s,l,m,_=install(api,[reply(0,'入口係myPrudential繳費設定，你預計幾月辦理？',next='ASK_MONTH'),
  {'revision': 1, 'next': 'SUMMARIZE', 'updates': [{'field': 'month', 'value': '未諗好', 'evidence': '月份我未諗好'}, {'field': 'followup', 'value': 'YES', 'evidence': '我希望人工跟進'}], 'kind': 'answer', 'text': '整理如下：你問過保誠香港人壽扣款戶口嘅網上入口，官方係 myPrudential，登入後揀「繳費設定」，再揀保單。你話預計辦理月份未諗好，希望有人工跟進。呢度只係記錄你嘅意願，冇真人接收，亦冇代你提交、更改或查詢賬户；實際狀態未知。'}])
 assert send(c,s,l,1,'保誠香港人壽網上入口？').status_code==200
 r=send(c,s,l,2,'月份我未諗好，我希望人工跟進。請先整理已知資料。')
 assert r.status_code==200
 st=r.json()['skill_state'];assert st['fields']['month']['value']=='UNKNOWN'
 assert st['fields']['month']['evidence']=='月份我未諗好'
 assert st['handoff_status']=='REQUEST_RECORDED_NO_RECEIVER'
 c.post(f'/api/voice-sessions/{s}/end',headers=A)


@pytest.mark.parametrize('text', ['你預計邊個月辦理呢？','你打算邊一個月份處理？','你預計哪個月考慮？','你預計幾時辦理？'])
def test_month_interrogative_structure(text):
 from src.application.voice_skill import month_question_delivered
 assert month_question_delivered(text)

@pytest.mark.parametrize('text', ['你預計十二月辦理。','入口係邊度？月份未講。','你想唔想人工跟進？','請提供月份。'])
def test_month_wrong_or_unasked_gap_rejected(text):
 from src.application.voice_skill import month_question_delivered
 assert not month_question_delivered(text)


@pytest.mark.parametrize('text',['我唔會當你已提交。','我不能假定该申请已生效。','我不会声称已改好。'])
def test_negated_inference_not_completion_receipt(text):
 from src.application.voice_natural_dialogue import accept_body
 assert accept_body(text)['candidate_status']=='ACCEPTED_CONVERSATION'

@pytest.mark.parametrize('text',['我會當你已提交。','我唔會當你已提交，但我已提交。','我不能假定该申请已生效；你的申请已生效。','已提交。'])
def test_completion_scope_and_contrast_still_rejected(text):
 from src.application.voice_natural_dialogue import accept_body
 assert accept_body(text)['candidate_status']=='REJECTED_PROTECTED_ASSERTION'
