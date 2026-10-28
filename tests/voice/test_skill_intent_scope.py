import json
from pathlib import Path
import pytest
from tests.voice.test_skill_plan_v2 import (api,no_network,mock_budget,install,understanding,expression,events,work,upd,send,A)
from src.application.voice_skill_plan import plan,Understanding,Intent,accept_intent_relation
from src.application.voice_skill import SkillError

@pytest.mark.parametrize('text,evidence',[
 ('暫時唔好提交任何變更，亦唔好話已經改好。','暫時唔好提交任何變更，亦唔好話已經改好'),
 ('我不是叫你別問，是叫你別提交。','別問'),
 ('先別問月份，其他可以問。','先別問月份'),
 ('不用交資料了嗎？','不用交資料了嗎'),
 ('朋友話不要繼續問。','不要繼續問'),
 ('不要停止諮詢。','停止諮詢'),
 ('我說過「不要繼續問」嗎？','不要繼續問'),
 ('暫停扣款，先別提交。','暫停扣款'),
])
def test_scope_rejects_wrong_object_polarity_and_quote(text,evidence):
 with pytest.raises(SkillError):accept_intent_relation(text,Intent(name='stop_questions',evidence=evidence))

@pytest.mark.parametrize('text,evidence',[
 ('今次到此為止，不要繼續問。','今次到此為止，不要繼續問'),
 ('請不要再追問我。','請不要再追問我'),
 ('唔好再問任何問題啦。','唔好再問任何問題啦'),
 ('唔好提交，今次到此為止。','今次到此為止'),
])
def test_direct_global_stop(text,evidence):
 st,p=plan(work(text),Understanding.model_validate(understanding(intents=[dict(name='stop_questions',evidence=evidence)])),{})
 assert p.question_target is None and p.after_delivery=='PARTIAL'
 if '提交' in text:assert st['restrictions']['prohibit_submission']


def test_only_business_prohibitions_remain_separate_no_global_stop(api):
 q='月份仲未諗好，唔好提交，亦唔好話已經改好。'
 c,s,l,m,raw=install(api,[understanding([upd('month','UNKNOWN','月份仲未諗好')]),expression('月份未定，只作諮詢，唔會提交，亦唔會話已經改好。')])
 r=send(c,s,l,1,q);assert r.status_code==200,r.text
 st=r.json()['skill_state'];assert st['reply_plan']['question_target']=='followup' and len(st['restrictions'])==2
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

@pytest.mark.parametrize('text,evidence',[
 ('我不是叫你別問，是叫你別提交。','別問'),
 ('先別問月份，其他可以問。','先別問月份'),
 ('不用交資料了嗎？','不用交資料了嗎'),
 ('我想知道入口。','不要追問')])
def test_original_entry_rejects_no_expression_no_partial_commit(api,text,evidence):
 c,s,l,m,raw=install(api,[understanding(intents=[dict(name='stop_questions',evidence=evidence)])])
 assert send(c,s,l,1,text).status_code==422
 assert len(m.requests)==1 and not any(e['kind']=='assistant_response' for e in events(c,s))
 c.post(f'/api/voice-sessions/{s}/end',headers=A)


def test_true_stop_cannot_be_omitted():
 with pytest.raises(SkillError,match='OMITTED_EXPLICIT_QUESTION_STOP'):
  plan(work('先整理，今次到此為止，不要繼續問。'),Understanding.model_validate(understanding()),{})


def test_partial_scope_explicit_boundary():
 with pytest.raises(SkillError,match='FIELD_QUESTION_SCOPE_UNSUPPORTED'):
  plan(work('先別問月份，其他可以問。'),Understanding.model_validate(understanding()),{})




def test_same_session_unknown_handoff_stop_and_source(api):
 q='保誠香港人壽扣款戶口網上入口？月份未諗好，唔好提交，唔好話已經改好。'
 c,s,l,m,raw=install(api,[understanding([upd('month','UNKNOWN','月份未諗好')]),expression(),
  understanding([upd('followup','YES','我希望人工跟進')],[dict(name='summary',evidence='先整理'),dict(name='stop_questions',evidence='今次到此為止，不要繼續問')],revision=1),
  expression('入口仍係myPrudential繳費設定；月份未定，截止及生效未知。只記錄人工需要，未有真人接收。唔會提交，亦唔會話已經改好。')])
 assert send(c,s,l,1,q).status_code==200
 r=send(c,s,l,2,'我希望人工跟進，先整理，今次到此為止，不要繼續問。');assert r.status_code==200,r.text
 st=r.json()['skill_state'];assert st['status']=='COMPLETED' and st['reply_plan']['question_target'] is None
 assert st['fields']['month']['value']=='UNKNOWN' and st['fields']['followup']['value']=='YES'
 assert len(st['restrictions'])==2 and st['handoff_status']=='REQUEST_RECORDED_NO_RECEIVER'
 c.post(f'/api/voice-sessions/{s}/end',headers=A)

@pytest.mark.parametrize('text',[
 '我想了解保诚香港人寿保单转扣款户口应该喺边个官方网上入口做？',
 '想請教網上邊度改資料？',
 '請解釋準備資料同提交指示有咩分別。',
])
def test_information_inquiry_is_not_summary_control(text):
 with pytest.raises(SkillError,match='INTENT_EVIDENCE_INVALID'):
  accept_intent_relation(text,Intent(name='summary',evidence=text))
 # Empty control list leaves ordinary answer planning available.
 st,p=plan(work(text),Understanding.model_validate(understanding()),{})
 assert p.after_delivery != 'COMPLETED'

@pytest.mark.parametrize('text',['請整理而家已有資料。','幫我總結頭先傾過嘅內容。'])
def test_explicit_summary_control_remains_accepted(text):
 accept_intent_relation(text,Intent(name='summary',evidence=text))
