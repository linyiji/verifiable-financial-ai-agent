"""Network-blocked original business entry. Not supplier quality evidence."""
import json
import socket
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from tests.voice.test_continuous_voice_backend import api, A
from tests.voice.test_voice_dialogue_v04 import payload, W
from src.application.voice_dialogue import VoiceDialogue
from src.application.voice_consultation import REVISION as CONSULTATION
from src.application.voice_natural_dialogue import ModelReply, REVISION, accept_body


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **k):
        raise AssertionError('NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', blocked)


class Model:
    def __init__(self, answers):
        self.answers, self.requests = list(answers), []

    async def complete_structured(self, **kw):
        self.requests.append(kw)
        assert kw['response_model'] is ModelReply
        return SimpleNamespace(output=ModelReply.model_validate(self.answers.pop(0)),
            provider='OFFLINE_FIXTURE', actual_model='NONE', request_id='offline')


def setup(api, answers):
    client, app, _ = api
    model = Model(answers); observed = []
    app.state.voice_sessions.dialogue = VoiceDialogue(app.state.voice_sessions, model,
        structured_constraints=True, instruction_revision=CONSULTATION,
        communication_revision=REVISION, raw_observer=observed.append)
    r = client.post('/api/voice-sessions', headers={**A, 'Idempotency-Key': 'm1b'},
        json={'interaction_mode': 'conversation', 'language': 'yue-HK'})
    assert r.status_code == 201
    sid = r.json()['id']
    claim = client.post(f'/internal/voice/{sid}/claim', headers=W, json={'worker_id': 'unit-v04'})
    return client, sid, claim.json()['lease_id'], model, observed


def send(c, sid, lease, n, text):
    return c.post(f'/internal/voice/{sid}/dialogue', headers=W, json=payload(lease, n, text))


@pytest.mark.parametrize('question,answer', [
    ('我未諗住辦手續，可唔可以講下整理資料同遞交申請差喺邊？',
     '整理資料係先核對內容；遞交就係將申請交畀機構。交咗唔等於已獲受理或生效，個案要另行確認。'),
    ('我想理解準備好資料係咪就代表已經提出申請？',
     '準備好資料同提出申請係兩回事：前者係整理內容，後者係向機構發送申請，唔代表結果已經確認。'),
])
def test_natural_paraphrase_uses_minimal_model_contract(api, question, answer):
    c, sid, lease, m, raw = setup(api, [{'kind': 'answer', 'text': answer}])
    r = send(c, sid, lease, 1, question)
    assert r.status_code == 200, r.text
    assert len(m.requests) == 1
    assert set(ModelReply.model_fields) == {'kind', 'text'}
    assert r.json()['content_acceptance']['candidate_status'] == 'ACCEPTED_CONVERSATION'
    assert r.json()['dialogue_result']['reply_text'] == r.json()['text']
    assert 'constraints' not in next(x['raw_reply'] for x in raw if x.get('raw_reply'))
    same = send(c, sid, lease, 1, question).json()
    assert same['replayed'] and len(m.requests) == 1
    c.post(f'/api/voice-sessions/{sid}/end', headers=A)


def test_three_turn_context_correction_and_independent_restrictions(api):
    answers = [
        {'kind':'answer','text':'扣款戶口係你想了解嘅對象。整理資料係核對內容；正式提交係交畀機構，唔等於已生效。'},
        {'kind':'answer','text':'我冇呢間公司嘅現行規則，確認唔到截止日或所需文件。你可以向機構查詢；整理資料唔等於已經提交。'},
        {'kind':'answer','text':'以你最新講嘅12月先考慮為準。我唔會提交扣款戶口變更，亦唔會聲稱已經改好；呢次只係交流資料，實際生效狀態仍要向機構確認。'},
    ]
    c, sid, lease, m, raw = setup(api, answers)
    inputs = ['我想下個月考慮改扣款戶口，先解釋整理資料同提出申請差喺邊。',
              '機構要幾時收申請同要乜文件？我未有佢哋嘅資料。',
              '改返做12月先考慮，唔好提交，亦唔好話已經改好。']
    for n, t in enumerate(inputs, 1):
        r = send(c,sid,lease,n,t); assert r.status_code == 200,r.text
    context = json.loads(m.requests[-1]['messages'][-1].content)
    assert [x['content'] for x in context['history'] if x['role']=='user'] == inputs[:2]
    assert context['current_utterance']==inputs[-1]
    assert context['capabilities']['account_mutation_capability'] is False
    assert context['sources']['institution'] == [] and context['sources']['records'] == []
    assert r.json()['reply_kind']=='conversation' and '12月' in r.json()['text']
    assert '唔會提交' in r.json()['text'] and '唔會聲稱' in r.json()['text']
    events=c.get(f'/api/voice-sessions/{sid}/events',headers=A,params={'limit':100}).json()['events']
    assert all(e['data']['actions_executed']==[] for e in events if e['kind']=='assistant_response')
    c.post(f'/api/voice-sessions/{sid}/end', headers=A)


@pytest.mark.parametrize('text', [
    '保誠規定必須提供銀行結單。',
    '可能三個工作天就會生效，請核對。',
    '未提交就一定未生效。',
    '提交之後就開始計處理時間。',
    '正式遞交就要你向保險公司提交申請，先會開始佢哋嘅處理。',
    '我已經幫你提交，戶口已改好。',
    '我查到你個案已生效。',
    '你嘅更改而家未生效。',
    '我不知道但公司規定必須交身份證。',
])
def test_protected_assertion_is_not_allowed_by_self_reported_kind(api,text):
    c,sid,lease,m,raw=setup(api,[{'kind':'clarification','text':text},
        {'kind':'answer','text':'一般整理資料唔等於已提出申請，個案狀態未有資料可以確認。'}])
    r=send(c,sid,lease,1,'可以講下我個案情況嗎？');assert r.status_code==422,r.text
    assert any(x.get('policy',{}).get('candidate_status')=='REJECTED_PROTECTED_ASSERTION' for x in raw)
    r=send(c,sid,lease,2,'咁一般整理同申請係咪一樣？');assert r.status_code==200,r.text
    ctx=json.loads(m.requests[-1]['messages'][-1].content)
    assert not any(x['role']=='assistant' for x in ctx['history'])
    c.post(f'/api/voice-sessions/{sid}/end',headers=A)


def test_bad_json_and_operation_plugin_remain_strict():
    for bad in [{'kind':'business_action_request','text':'x'},
                {'kind':'answer','text':'x','constraints':[]},
                {'kind':'answer','text':'x','executed':True}]:
        with pytest.raises(ValidationError): ModelReply.model_validate(bad)
    from src.application.voice_dialogue import TargetRefDialogueReply
    with pytest.raises(ValidationError):
        TargetRefDialogueReply.model_validate({'kind':'conversation','text':'x','constraints':[{'target':'long definition'}]})


def test_general_uncertainty_is_not_a_case_assertion():
    for text in ['提交唔代表已受理或已生效。', '未有資料，我確認唔到你嘅更改而家有冇生效。',
                 '我唔會提交，亦唔會話已經改好。', '截止日同材料要求要向機構核對。']:
        assert accept_body(text)['text']==text


def test_supplier_hint_and_budget_stay_consistent():
    from src.adapters.voice_dialogue_model import DeepSeekVoiceDialogueModel, structured_json_hint
    from src.adapters.llm.provider import LLMMessage
    hint = structured_json_hint(ModelReply)
    assert 'answer' in hint and 'conversation' not in hint and 'constraints' not in hint
    node = object.__new__(DeepSeekVoiceDialogueModel)
    node.settings = SimpleNamespace(model='deepseek-flash')
    body = node.request_body([LLMMessage(role='system',content='test')], ModelReply)
    assert body['max_tokens']==256 and body['response_format']=={'type':'json_object'}
    assert body['thinking']=={'type':'disabled'}


def test_scoped_non_implication_and_requirement_topic():
    assert accept_body('兩者都唔會自動代表機構已受理、開始處理或者生效。')['text']
    assert accept_body('機構嘅文件要求，我哋未有資料可依。')['text']
    assert accept_body('保險公司要求提供銀行結單。')['text'] is None
