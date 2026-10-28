"""Opt-in A1 method, source-grounded task proposals in the existing journal.
No network/runtime/tools; ordinary kind/text and operation contracts stay unchanged.
"""
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Literal
from functools import lru_cache
from pydantic import BaseModel, ConfigDict, Field
from src.application.voice_natural_dialogue import ModelReply, _normalizer

ROOT=Path(__file__).resolve().parents[2]
CONTRACT='voice.skill-consultation.v1'

class Update(BaseModel):
    model_config=ConfigDict(extra='forbid')
    field:Literal['month','followup']
    value:str=Field(min_length=1,max_length=16)
    evidence:str=Field(min_length=1,max_length=100)

class SkillReply(ModelReply):
    revision:int=Field(ge=0)
    updates:list[Update]=Field(max_length=2)
    next:Literal['ANSWER','ASK_MONTH','ASK_FOLLOWUP','SUMMARIZE','CLOSE']

class SkillError(ValueError):pass

def norm(t):return _normalizer().convert(t).lower()
def safe_read(relative):
    p=(ROOT/relative).resolve()
    if not p.is_relative_to(ROOT/'skills') and not p.is_relative_to(ROOT/'communication'):
        raise SkillError('SKILL_RESOURCE_SCOPE')
    return p.read_bytes()

@lru_cache(maxsize=32)
def _bundle(raw_key):
    files=json.loads(raw_key)
    return {k:json.loads(v) if k.endswith('.json') else v for k,v in files.items()}

def load(config, prior=None):
    """Re-read registry for disablement; cache immutable parsed resources by bytes."""
    registry=json.loads(safe_read('communication/skill-registry.json'))
    item=registry.get(config['id'])
    if not item or not item['enabled']:raise SkillError('SKILL_NOT_AVAILABLE')
    if item['version']!=config['version']:
        variant=item.get('versions',{}).get(config['version'])
        if not variant or not variant['enabled']:raise SkillError('SKILL_NOT_AVAILABLE')
        item=variant
    m=json.loads(safe_read(item['manifest']))
    if m['contract'] not in (CONTRACT,'voice.skill-consultation.v2','voice.skill-consultation.v3') or m['scripts']:raise SkillError('SKILL_CONTRACT_UNSUPPORTED')
    choice=copy.deepcopy(prior or {k:config[k] for k in ['persona','policy','depth','verbosity']})
    if choice['persona'] not in m['personas'] or choice['policy'] not in m['policies']:raise SkillError('SKILL_SELECTION_UNKNOWN')
    if choice['depth'] not in ['core','detail'] or choice['verbosity'] not in ['concise','normal']:raise SkillError('SKILL_STYLE_UNKNOWN')
    # Pin complete registered package including selectable styles, inject only current ones.
    paths=[item['manifest'],str(Path(item['manifest']).parent/m['method_file']),m['task_template_ref'],*m['personas'].values(),*m['policies'].values()]
    files={p:safe_read(p).decode() for p in paths};key=json.dumps(files,sort_keys=True,ensure_ascii=False)
    digest=hashlib.sha256(key.encode()).hexdigest()
    if config.get('sha256') and config['sha256']!=digest:raise SkillError('SKILL_VERSION_HASH_CHANGED')
    data=_bundle(key)
    return {'contract':m['contract'],'id':m['id'],'version':m['version'],'sha256':digest,'selection':choice,
        'method':data[paths[1]],'template':data[m['task_template_ref']],
        'persona':data[m['personas'][choice['persona']]],'policy':data[m['policies'][choice['policy']]],'resource_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in files.items()}}

def prepare(config, events, *, session_id, turn_id, utterance):
    previous=next(((e.payload.get('data') or {}).get('skill_state') for e in events
                   if e.payload.get('kind')=='assistant_response' and (e.payload.get('data') or {}).get('skill_state')),None)
    if previous and previous['session_id']!=session_id:raise SkillError('SKILL_SESSION_MISMATCH')
    state=copy.deepcopy(previous or {'session_id':session_id,'revision':0,'communication_revision':0,'fields':{},'history':[],
        'restrictions':{},'asked':{},'status':'OPEN','entry_explained':False})
    if previous and previous.get('next','').startswith('ASK_'):
        delivered=any((e.payload.get('data') or {}).get('response_id')==previous.get('response_id') and (e.payload.get('data') or {}).get('delivery_state')=='PUBLISHED' for e in events)
        text_reply=any((e.payload.get('data') or {}).get('response_id')==previous.get('response_id') and (e.payload.get('data') or {}).get('track_sid')=='NO_RTC' for e in events)
        if delivered or text_reply:
            key=previous['next'];state['asked'][key]=state['asked'].get(key,0)+1
    bundle=load(config,state.get('selection'))
    if previous and previous['package_sha256']!=bundle['sha256']:raise SkillError('SKILL_RUNNING_VERSION_CHANGED')
    if previous and previous['status'] in ['COMPLETED','CANCELLED']:raise SkillError('SKILL_TASK_TERMINAL')
    text=norm(utterance);choice=dict(bundle['selection']);errors=[]
    aliases={'稳健顾问':'steady-advisor','干练伙伴':'efficient-partner','好奇访谈者':'curious-interviewer'}
    if re.search(r'换成|换做|切换|改用',text):
        matches=[v for k,v in aliases.items() if k in text]+[v for v in aliases.values() if v in text]
        if len(set(matches))==1:choice['persona']=matches[0]
        else:errors.append('PERSONA_SWITCH_NOT_APPLIED_UNKNOWN_OR_AMBIGUOUS')
    if re.search(r'只回答|只答|唔好追问|不要追问',text):choice['policy']='responsive'
    elif re.search(r'你可以问|可以继续问|一起整理',text):choice['policy']='collaborative'
    elif '目标主导' in text:choice['policy']='goal-led'
    if re.search(r'简短|精简|短啲',text):choice['verbosity']='concise'
    if re.search(r'解释原因|详细解释',text):choice['depth']='detail'
    if choice!=bundle['selection']:state['communication_revision']+=1
    bundle=load(config,choice);state.update(selection=choice,package_sha256=bundle['sha256'])
    # Only explicit current instructions, never inferred from an intention or old assistant.
    for key,expr in [('prohibit_submission',r'(?:唔好|不要|唔会|不会|暂不)(?:立即|即刻|再)?提交'),
                     ('prohibit_completion_claim',r'(?:唔好|不要|唔会|不会)(?:话|说|声称)(?:已经|已)?改好')]:
        hit=re.search(expr,text)
        if hit:state['restrictions'][key]={'value':True,'turn_id':turn_id,'source':'current_user','normalized_evidence':hit.group(),'raw_utterance':utterance}
    stopped=bool(re.search(r'(?:停喺呢度|到此为止|结束咨询|唔倾住|不要再问|停止咨询)',text))
    state['generation']=turn_id
    pending_sources={};user_event_sources={}
    if bundle['contract']=='voice.skill-consultation.v3':
        for item in state.get('pending',[]):
            if item['status']!='PENDING_EXTRACTION':continue
            event=next((e for e in events if e.payload.get('event_id')==item['source_ref']['event_id'] and e.payload.get('kind')=='conversation_turn'),None)
            if event is None or event.payload.get('text')!=item['raw_text'] or item['source_ref']['session_id']!=session_id:
                raise SkillError('SKILL_PENDING_SOURCE_INVALID')
            user_event_sources[item['source_ref']['turn_id']]=copy.deepcopy(item)
            if item['recovery_attempts']<bundle['template']['pending_policy']['default_recovery_attempts']:
                pending_sources[item['source_ref']['turn_id']]=copy.deepcopy(item)
    return {'user_event_sources':user_event_sources,'pending_sources':pending_sources,'bundle':bundle,'state':state,'base_revision':state['revision'],'selection_errors':errors,'stopped':stopped,
            'raw_utterance':utterance,'turn_id':turn_id}

def month_value(e):
    t=norm(e)
    if re.search(r'唔知|不知道|未决定|未谂好',t):return 'UNKNOWN'
    if re.search(r'唔想讲|不想说|拒绝',t):return 'REFUSED'
    m=re.search(r'(?:12|十二|11|十一|10|十|[1-9一二三四五六七八九])月|下个?月',t)
    if not m:return None
    v=m.group();return '12月' if v=='十二月' else v

def followup_value(e):
    t=norm(e)
    if re.search(r'唔知|不知道|未决定|未谂好',t):return 'UNKNOWN'
    if re.search(r'唔想讲|不想说|拒绝回答',t):return 'REFUSED'
    if re.search(r'(?:唔|不|无|毋须|无需).{0,4}(?:人工|跟进|跟進)',t):return 'NO'
    if re.search(r'(?:想|希望|需要|要|请|搵).{0,8}(?:人工|跟进)',t):return 'YES'
    return None

def month_question_delivered(spoken):
    """Bounded interrogative grammar for the pending month gap, not prose truth.

    Inspect individual question clauses, not unrelated target/interrogative words
    anywhere in the answer. Month/time interrogatives can have classifiers.
    """
    for clause in re.split(r'[。；;！!]', norm(spoken)):
        for question in re.findall(r'[^？?]*[？?]', clause):
            if re.search(r'(?:边|哪|几|何)(?:一|个|個|些|多|年|月份|月|时|时候|时间){0,4}(?:月|时|时候|时间)', question):
                return True
            if re.search(r'月份.{0,8}(?:系|是|为).{0,3}(?:边|哪|几|何)', question):
                return True
    return False

def accept_fields(work, reply, *, require_correction=True):
    if reply.revision!=work['base_revision']:raise SkillError('SKILL_STALE_REVISION')
    state=copy.deepcopy(work['state']);text=work['raw_utterance'];seen=set()
    for u in reply.updates:
        if u.field in seen:raise SkillError('SKILL_DUPLICATE_FIELD')
        seen.add(u.field)
        if u.evidence not in text:raise SkillError('SKILL_EVIDENCE_NOT_CURRENT_USER')
        # Conservative reported-speaker boundary; ambiguous assignment stays unaccepted.
        clause=next((c for c in re.split(r'[。！？!?；;]',text) if u.evidence in c),'')
        if re.search(r'职员|職員|佢话|佢話|他说|她说|朋友|同事',clause):raise SkillError('SKILL_REPORTED_SPEAKER_NOT_USER')
        expected=(month_value if u.field=='month' else followup_value)(u.evidence)
        proposed=(month_value(u.value) or u.value) if u.field=='month' else norm(u.value)
        if expected is None or norm(proposed or '')!=norm(expected):raise SkillError('SKILL_VALUE_EVIDENCE_MISMATCH')
        old=state['fields'].get(u.field)
        if old:state['history'].append({'field':u.field,'superseded':old,'by_turn':work['turn_id']})
        state['fields'][u.field]={'value':expected,'year':None if u.field=='month' else None,'source':'current_user',
            'turn_id':work['turn_id'],'evidence':u.evidence,'status':expected if expected in ['UNKNOWN','REFUSED'] else 'USER_STATED'}
    if require_correction and re.search(r'更正|改为|改做',norm(text)) and month_value(text) not in (None,'UNKNOWN','REFUSED') and 'month' not in seen:
        raise SkillError('SKILL_OMITTED_MONTH_CORRECTION')
    return state

def accept_proposals(work, reply):
    state=accept_fields(work,reply)
    fields=state['fields'];missing=[k for k in ['month','followup'] if k not in fields]
    action=reply.next
    if action=='ASK_MONTH' and 'month' not in missing:raise SkillError('SKILL_REASK_RESOLVED_FIELD')
    if action=='ASK_FOLLOWUP' and ('followup' not in missing or 'month' in missing):raise SkillError('SKILL_WRONG_NEXT_GAP')
    if state['selection']['policy']=='responsive' and action.startswith('ASK_'):raise SkillError('SKILL_USER_REQUESTED_RESPONSIVE')
    if action=='SUMMARIZE' and missing:raise SkillError('SKILL_PREMATURE_SUMMARY')
    if action=='CLOSE' and not work['stopped'] and missing:raise SkillError('SKILL_UNEXPLAINED_CLOSE')
    spoken=norm(reply.text)
    if action=='ASK_FOLLOWUP' and not (re.search(r'人工|跟进',spoken) and re.search(r'希唔希望|想唔想|要唔要|需唔需要|是否|希望.{0,10}(?:吗|？|\?)|(?:吗|呢|意愿|意向)[？?]',spoken)):
        raise SkillError('SKILL_QUESTION_NOT_DELIVERABLE')
    if action=='ASK_MONTH' and not month_question_delivered(spoken):
        raise SkillError('SKILL_QUESTION_NOT_DELIVERABLE')
    if action.startswith('ASK_') and state['asked'].get(action,0)>=2:raise SkillError('SKILL_GAP_NO_PROGRESS')
    state.update(revision=state['revision']+1,status='WAITING_USER' if action.startswith('ASK_') else
        'COMPLETED' if action=='SUMMARIZE' else 'CANCELLED' if action=='CLOSE' else 'IN_PROGRESS',next=action,missing=missing)
    # Generated question is not recorded as heard. Delivery receipts reconcile it next turn.
    return state

async def knowledge_context(port, request, events):
    """Re-query eligible prior source through the same Port, never cache old prose."""
    from src.application.voice_communication import KnowledgeResult
    current=await port.lookup(**request);checks=[{'request':request,'result':current.model_dump(mode='json')}]
    result=current
    if current.status=='NO_MATCH':
        for e in events:
            d=e.payload.get('data') or {};old=d.get('knowledge_result') or {}
            if old.get('status')!='FOUND':continue
            # Carry the actual successful retrieval request, not the later
            # NO_MATCH question whose answer happened to inherit this passage.
            candidates=[c['request'] for c in d.get('knowledge_checks',[]) if c['result'].get('status')=='FOUND']
            if not candidates and d.get('knowledge_request'):candidates=[d['knowledge_request']]
            for req in candidates:
                req={**req,'context':request['context']}
                fresh=await port.lookup(**req);checks.append({'request':req,'result':fresh.model_dump(mode='json')})
                if fresh.status!='NO_MATCH':return current,fresh,checks
    return current,result,checks

async def revalidate(port,checks):
    for c in checks:
        fresh=await port.lookup(**c['request'])
        if fresh.model_dump(mode='json')!=c['result']:raise SkillError('SKILL_KNOWLEDGE_CHANGED')


def checked(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except (SkillError,OSError,KeyError,ValueError) as exc:
        from src.application.voice_sessions import fail
        code=str(exc) if isinstance(exc,SkillError) else 'SKILL_CONFIGURATION_INVALID'
        fail('VOICE_'+code, '本輪Skill配置或來源合同未獲接受，進度保留，未進入播報。',422)


def skill_instruction(work):
    from src.application.voice_natural_dialogue import INSTRUCTION
    b=work['bundle']
    base=INSTRUCTION.replace('只输出kind和text的JSON。','使用隔离任务合同的JSON；正文仍kind/text，不产生业务操作。')
    return base+'\n'+b['method']+'\n'+b['persona']['method']+'\n'+b['policy']['method']+'\n深度:'+b['selection']['depth']+'；篇幅:'+b['selection']['verbosity']+'。短答优先约60—100中文字，不能删关键限制。'


def check_skill_body(text,knowledge):
    """Bounded explicit contradiction check, not full prose fact verification."""
    if knowledge.get('status')!='FOUND' or not any(p['topic']=='navigation' for p in knowledge.get('passages',[])):return
    for clause in re.split(r'[。；;！？!?]',norm(text)):
        if (re.search(r'入口[」”]?\s*(?:具体位置|位置|资料)?[，,:： ]*(?:仍|目前|系|是)?(?:未知|未能确认|无.{0,5}来源|没有.{0,5}资料|冇.{0,5}资料)',clause)
                or re.search(r'入口.{0,30}(?:均|都)(?:无|冇|没有).{0,5}(?:来源|资料)',clause)
                or re.search(r'(?:冇|没有).{0,12}(?:正式页面|入口资料)',clause)):
            raise SkillError('SKILL_DENIES_VALID_NAVIGATION')
