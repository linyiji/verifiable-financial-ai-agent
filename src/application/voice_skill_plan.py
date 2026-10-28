"""Isolated v2 causal contract. No provider, transport or alternative runtime.

Accepted fields/plan are tentative until the original assistant_response transaction.
The original journal fences a started turn: failed expression never silently repeats
understanding. A new user turn may continue; no partial field commit is disguised.
"""
import asyncio
import copy
import hashlib
import json
import re
import time
from typing import Literal, Annotated, Union
from pydantic import BaseModel, ConfigDict, Field
from src.application.voice_skill import Update, SkillError, accept_fields, norm, month_value
from src.application.voice_natural_dialogue import ModelReply, INSTRUCTION
from src.adapters.llm.provider import LLMMessage

CONTRACT = 'voice.skill-consultation.v2'

class Intent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Literal['summary', 'stop_questions'] = Field(description='summary:整理已有咨询资料；stop_questions:停止当前咨询的所有追问，不是停止业务操作或完成声明，也不是仅跳过某字段')
    evidence: str = Field(min_length=1, max_length=100)

class Understanding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    updates: list[Update] = Field(max_length=2)
    intents: list[Intent] = Field(max_length=2, description='可为空[]。只收当前用户明确的问答控制；业务禁止留在restrictions，人工偏好留在updates。无对应控制时不分类、不凑意图。')

class SourcedUpdate(Update):
    source_turn_id: str | None = Field(default=None, description='当前用户省略或null；补提只能引用runtime_handoff.pending_sources列明的原用户turn_id')

class SourcedMonth(SourcedUpdate):
    field: Literal['month']

class SourcedFollowup(SourcedUpdate):
    field: Literal['followup']
    value: Literal['YES','NO','UNKNOWN','REFUSED'] = Field(description='人工偏好规范值；原话仅放evidence，不将自然句写入value')

class PendingUnderstanding(Understanding):
    updates: list[Annotated[Union[SourcedMonth,SourcedFollowup],Field(discriminator='field')]] = Field(max_length=2)


def pending_fields(work, candidate):
    """v3 only: journal-backed deferred extraction, never an accepted inferred fact."""
    if work['bundle']['template'].get('write_operations') or work['bundle']['template'].get('dependencies',{}).get('business_operation',{}).get('enabled'):
        raise SkillError('SKILL_PENDING_OPERATION_UNSUPPORTED')
    current=[u for u in candidate.updates if not u.source_turn_id or u.source_turn_id==work['turn_id']]
    current_candidate=Understanding(revision=candidate.revision, updates=[Update(**u.model_dump(exclude={'source_turn_id'})) for u in current], intents=candidate.intents)
    state=accept_fields(work,current_candidate,require_correction=False)
    pending=state.setdefault('pending',[])
    supplied=bool(re.search(r'月份?',norm(work['raw_utterance'])) and month_value(norm(work['raw_utterance'])))
    current_month=any(u.field=='month' for u in current)
    historical_seen=set()
    for u in candidate.updates:
        if u in current:continue
        if (u.source_turn_id,u.field) in historical_seen:raise SkillError('SKILL_DUPLICATE_FIELD')
        historical_seen.add((u.source_turn_id,u.field))
        source=work.get('pending_sources',{}).get(u.source_turn_id)
        if not source or u.field!=source['field']:
            raise SkillError('SKILL_PENDING_SOURCE_INVALID')
        # Validate even a superseded historical proposal; never silently accept bad data.
        historical={**work,'state':copy.deepcopy(state),'raw_utterance':source['raw_text'],'turn_id':u.source_turn_id}
        validated=accept_fields(historical,Understanding(revision=candidate.revision,
            updates=[Update(**u.model_dump(exclude={'source_turn_id'}))],intents=[]),require_correction=False)
        if not supplied and not current_month:
            state['fields'][u.field]=validated['fields'][u.field]
            state['fields'][u.field].update(source='historical_user_pending',source_ref=copy.deepcopy(source['source_ref']))
        for item in pending:
            if item['source_ref']==source['source_ref']:
                item['status']='SUPERSEDED' if supplied or current_month else 'ACCEPTED'
    for item in pending:
        if item['source_ref']['turn_id'] in work.get('pending_sources',{}):
            item['recovery_attempts']+=1
        if (supplied or current_month) and item['status']=='PENDING_EXTRACTION':item['status']='SUPERSEDED'
    if supplied and not current_month:
        old=state['fields'].pop('month',None)
        if old:state['history'].append({'field':'month',**old,'superseded_by':work['turn_id'],'reason':'unaccepted_current_revision'})
        pending.append({'field':'month','status':'PENDING_EXTRACTION','recovery_attempts':0,
            'raw_text':work['raw_utterance'],'source_ref':{'session_id':state['session_id'],
            'turn_id':work['turn_id'],'event_id':'dialogue:input:'+str(work['turn_id'])},
            'reason':'MODEL_OMITTED_FIELD','dependency':'not_required_for_official_entry',
            'accepted_fact':False,'business_status':'AMBIGUOUS'})
    return state


def runtime_handoff(work, knowledge, state=None):
    state=state or work['state']
    return {'session_id':state['session_id'],'turn_id':work['turn_id'],'revision':state['revision'],
        'task_id':state['session_id']+':consultation','task_revision':state['revision'],
        'skill':{k:work['bundle'][k] for k in ('id','version','contract','selection')},
        'binding':work['bundle']['sha256'],'goal':work['bundle']['template'].get('goal'),
        'capabilities':{'business_operation':False,'actual_human_receiver':False},
        'restrictions':state['restrictions'],'accepted_fields':state['fields'],
        'knowledge':knowledge,'pending':state.get('pending',[]),
        'pending_sources':work.get('pending_sources',{}),'dependencies':work['bundle']['template'].get('dependencies',{}),'asked':state['asked'],
        'delivery_state':state.get('status'),'last_response_id':state.get('response_id'),
        'entry_explained':state.get('entry_explained',False),'reply_plan':state.get('reply_plan'),
        'rule':'pending不是已接受事实；不重问已提供待处理字段；历史补提仅限所列原事件，当前更正优先。'}


def summary_materials(work, state, knowledge):
    """Role-separated speech materials. No extraction or change to accepted fields."""
    reports=[]
    for item in state.get('pending',[]):
        if item['status']!='PENDING_EXTRACTION' or item['field'] in state['fields']:continue
        ref=item['source_ref']
        current=ref=={'session_id':state['session_id'],'turn_id':work['turn_id'],
                     'event_id':'dialogue:input:'+str(work['turn_id'])} and item['raw_text']==work['raw_utterance']
        old=work.get('user_event_sources',{}).get(ref['turn_id'])
        if not current and (not old or old['source_ref']!=ref or old['raw_text']!=item['raw_text']):
            raise SkillError('SKILL_SUMMARY_SOURCE_INVALID')
        # Quote only the whole month clause, not another speaker or an operation receipt.
        for clause in re.split(r'[。！？!?；;，,]',item['raw_text']):
            if not re.search(r'月份?',clause):continue
            if re.search(r'朋友|職員|职员|同事|佢話|佢话|他說|她說|已辦|已办|生效|提交|受理',clause):continue
            if clause.strip():reports.append({'role':'USER_REPORTED_NOT_NORMALIZED',
                'field':item['field'],'quote':clause.strip(),'source_ref':copy.deepcopy(ref),
                'authority':'USER_STATEMENT_ONLY_NOT_INSTITUTION_OR_EXECUTION'})
    return {'version':'summary-materials-r7','accepted_fields':copy.deepcopy(state['fields']),
        'official_knowledge':copy.deepcopy(knowledge),'user_statements':reports,
        'unresolved':[{'field':x['field'],'state':x['status'],'source_ref':x['source_ref']}
            for x in state.get('pending',[]) if x['status']=='PENDING_EXTRACTION'],
        'restrictions':copy.deepcopy(state['restrictions']),
        'capabilities':{'account_query':False,'business_write':False,'human_receiver':False},
        'rule':'已接受字段与用户陈述分开。待补不妨碍部分摘要；可省略字段值。若复述未规范化原话，明确归因为用户说法，优先照引user_statements.quote。不宣称已确认、已补提、机构核实或业务完成。'}


def attributed_pending_text(text, state):
    """Bounded provenance check; does not prove arbitrary paraphrase semantics.

    Masks validated user quotes only for field-conflict checks, never for the
    original institution/operation acceptance layer, which still gets raw text.
    """
    materials=state.get('summary_materials',{})
    reports=list(materials.get('user_statements',[]))
    # A currently accepted month still has user evidence after pending is resolved.
    # Only that active field's validated original evidence is quote authority;
    # superseded history, other fields and assistant prose are not candidates.
    accepted_month=materials.get('accepted_fields',{}).get('month',{})
    evidence=accepted_month.get('evidence','')
    if (accepted_month.get('source')=='current_user' and accepted_month.get('turn_id')
            and evidence and month_value(evidence)==accepted_month.get('value')):
        reports.append({'field':'month','quote':evidence,
                        'authority':'ACTIVE_ACCEPTED_USER_MONTH_EVIDENCE'})
    result=text
    quote_pattern=r'你(?:之前|先前|曾經|曾经)?(?:講過|讲过|講|讲|話|话|提到|表示|說過|说过|說|说)[：:]?\s*[「“『](.*?)[」”』]'
    for m in list(re.finditer(quote_pattern,text)):
        excerpt=norm(m.group(1))
        # Necessary verbatim excerpt: retain the source's semantic polarity, and
        # locate its object in the enclosing attributed clause (not elsewhere).
        start=max(text.rfind(c,0,m.start()) for c in '。；;\n')+1
        clause=norm(text[start:m.end()])
        matching=[r for r in reports if norm(r['quote'])==excerpt or (
            excerpt in norm(r['quote']) and re.search(r'月份?',clause)
            and month_value(excerpt) is not None
            and month_value(excerpt)==month_value(r['quote'])
            and not re.search(r'不是|唔系|并非|否认|不想|唔想',norm(r['quote']).replace(excerpt,'')))]
        if not matching:raise SkillError('SKILL_SUMMARY_QUOTE_UNSUPPORTED')
        result=result.replace(m.group(0),'有來源的用戶陳述')
    # Narrow old-R6 paraphrase review: supported user undecided-month statement,
    # explicitly attributed locally or by the enclosing summary's source scope.
    document_user_scope=bool(re.search(r'整理你(?:之前|先前)?(?:講過|讲过|說過|说过)嘅(?:內容|内容)',text))
    supported_unknown=any(month_value(r['quote'])=='UNKNOWN' for r in reports)
    for clause in re.split(r'[。；;\n]',result):
        n=norm(clause)
        if not re.search(r'月份?.{0,4}(?:未定|未决定|未谂好|未知)',n):continue
        local=bool(re.search(r'你(?:之前|先前)?(?:话|提到|表示|说)',n))
        if supported_unknown and (local or (document_user_scope and '你' in n)) and not re.search(r'已确认|确定|核实|机构|保诚|生效|系统',n):
            result=result.replace(clause,re.sub(r'月份?.{0,4}(?:未定|未决定|未谂好|未知)','用户陈述',n))
    return norm(result)

class Expression(ModelReply):
    plan_id: str = Field(min_length=1, max_length=80)

class ReplyPlan(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: Literal['skill.reply-plan.v2'] = 'skill.reply-plan.v2'
    plan_id: str
    based_on_task_revision: int
    generation: str
    summary_scope: tuple[str, ...]
    question_target: Literal['month','followup'] | None
    after_delivery: Literal['WAITING_USER','IN_PROGRESS','COMPLETED','PARTIAL']
    # Only current revalidated knowledge may support institution assertions.
    knowledge_status: str
    allowed_actions: tuple = ()



def control_clauses(text):
    """Bounded direct speech relation grammar, not a general intent classifier.

    Keep whole clause polarity/object: a substring like 别问 inside 不是叫你别问
    cannot turn a negated/quoted instruction into a current instruction.
    """
    return [c.strip() for c in re.split(r'[，,。；;！!]', norm(text)) if c.strip()]


def global_stop_clause(clause):
    if re.search(r'[？?「」“”"《》]|(?:吗|呀|呢)$|不是|唔系|并非|并不|冇叫|没有叫|如果|假如|职员|朋友|同事|佢话|他说|她说',clause):
        return False
    prefix=r'(?:我(?:想|希望|要求))?(?:请|麻烦)?(?:你)?'
    stop_questions=prefix+r'(?:不要|唔好|别|不用|无需)(?:再|继续|再继续)?(?:问|追问)(?:我|任何问题|其他问题|问题)?(?:了|啦|喇)?'
    close=prefix+r'(?:(?:今次|本次|这次|当前)(?:咨询|询问|对话)?)?(?:到此为止|停喺呢度|结束咨询|停止咨询|结束询问)'
    return bool(re.fullmatch(stop_questions,clause) or re.fullmatch(close,clause))


def has_global_stop(text):
    return any(global_stop_clause(c) for c in control_clauses(text))


def accept_intent_relation(text, intent):
    if intent.evidence not in text:raise SkillError('SKILL_INTENT_EVIDENCE_INVALID')
    # Evaluate complete enclosing clauses, including negation outside the quote.
    clauses=[c for c in control_clauses(text) if any(e in c or c in e for e in control_clauses(intent.evidence))]
    if intent.name=='stop_questions':
        valid=any(global_stop_clause(c) for c in clauses)
    else:
        valid=any(not re.search(r'[？?「」“”"]|不是|唔系|不要|唔好|不用|朋友|职员|佢话|他说|她说',c)
                  and re.search(r'(?:请|先|帮我|麻烦|想|希望|要|可以)?(?:整理|总结|摘要|归纳)',c) for c in clauses)
    if not valid:raise SkillError('SKILL_INTENT_EVIDENCE_INVALID')


def plan(work, candidate, knowledge):
    v3=work['bundle']['contract']=='voice.skill-consultation.v3'
    state = pending_fields(work,candidate) if v3 else accept_fields(work, candidate)
    current = norm(work['raw_utterance'])
    # Reuse the existing bounded field parser as a completeness check, not a new
    # phrase lookup/ASR correction. General extraction remains model-dependent.
    if not v3 and re.search(r'月份?', current) and month_value(current) and not any(u.field=='month' for u in candidate.updates):
        raise SkillError('SKILL_OMITTED_EXPLICIT_MONTH')
    intents=set()
    for intent in candidate.intents:
        if intent.name in intents or intent.evidence not in work['raw_utterance']:
            raise SkillError('SKILL_INTENT_EVIDENCE_INVALID')
        accept_intent_relation(work['raw_utterance'],intent)
        intents.add(intent.name)
    stopped=has_global_stop(work['raw_utterance'])
    if stopped and 'stop_questions' not in intents:
        raise SkillError('SKILL_OMITTED_EXPLICIT_QUESTION_STOP')
    if any(re.search(r'(?:不要|唔好|别).*(?:问|追问).*(?:月份|几月|人工|跟进)',c) for c in control_clauses(work['raw_utterance'])):
        raise SkillError('SKILL_FIELD_QUESTION_SCOPE_UNSUPPORTED')
    # Silence/declining are not missing. Literal refusal is preserved for v1
    # compatibility; v2 presents its semantic status as DECLINED.
    for field in state['fields'].values():
        if field['value']=='REFUSED':field['status']='DECLINED'
    missing=tuple(k for k in work['bundle']['template']['fields'] if k not in state['fields'])
    no_questions=stopped or 'stop_questions' in intents or state['selection']['policy']=='responsive'
    deferred={p['field'] for p in state.get('pending',[]) if p['status']=='PENDING_EXTRACTION'}
    askable=[k for k in missing if k not in deferred]
    question=askable[0] if askable and not no_questions else None
    if question and state['asked'].get('ASK_'+question.upper(),0)>=2:question=None
    summary=tuple(state['fields']) if 'summary' in intents or not missing or stopped else ()
    closing=stopped or 'stop_questions' in intents or (bool(summary) and not missing)
    after='WAITING_USER' if question else ('PARTIAL' if missing else 'COMPLETED') if closing else 'IN_PROGRESS'
    # A style switch alone is not a task fact revision.
    changed=bool(candidate.updates) or state.get('pending',[])!=work['state'].get('pending',[]) or any(v.get('turn_id')==work['turn_id'] for v in state['restrictions'].values())
    state['revision']=work['base_revision']+int(changed)
    data=dict(based_on_task_revision=state['revision'],generation=str(work['turn_id']),
        summary_scope=summary,question_target=question,after_delivery=after,
        knowledge_status=knowledge.get('status','UNKNOWN'))
    if v3:state['summary_materials']=summary_materials(work,state,knowledge)
    identity={'plan':data,'state':state,'package':work['bundle']['sha256'],'knowledge':knowledge}
    ident=hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:32]
    frozen=ReplyPlan(plan_id=ident,**data)
    # Compatibility next is application-derived, never patched into raw JSON.
    state.update(next='ASK_'+question.upper() if question else 'SUMMARIZE' if closing else 'ANSWER',
        status=after,missing=list(missing),reply_plan=frozen.model_dump(mode='json'))
    return state,frozen


def accept_expression(expression, frozen, state):
    if expression.plan_id!=frozen.plan_id or state['revision']!=frozen.based_on_task_revision:
        raise SkillError('SKILL_STALE_PLAN')
    text=norm(expression.text)
    field_text=attributed_pending_text(expression.text,state) if state.get('summary_materials') else text
    # The model's scope is explanatory prose, never the authoritative question.
    # Bounded detection is defense-in-depth, not a proof of all natural semantics.
    if re.search(r'[?？]|(?:想|要|需|希|可).{0,1}(?:唔|不).{0,1}(?:想|要|需|希望|可以)|(?:请|请问|麻烦).{0,6}(?:告知|提供|讲|告诉)',text):
        raise SkillError('SKILL_EXPRESSION_QUESTION_OUTSIDE_PLAN')
    months=set(re.findall(r'(?:12|十二|11|十一|10|十|[1-9一二三四五六七八九])月|下个?月',field_text))
    accepted=state['fields'].get('month',{}).get('value')
    if any(month_value(m)!=accepted for m in months):raise SkillError('SKILL_EXPRESSION_MONTH_CONFLICT')
    if accepted in ('UNKNOWN','REFUSED') and re.search(r'月份?.{0,4}(?:已确定|已决定)',text):raise SkillError('SKILL_EXPRESSION_MONTH_CONFLICT')
    if accepted is None and any(p['status']=='PENDING_EXTRACTION' and p['field']=='month' for p in state.get('pending',[])) and re.search(r'月份?.{0,4}(?:未定|未决定|未谂好|未知)',field_text):
        raise SkillError('SKILL_EXPRESSION_PENDING_AS_FACT')
    if state.get('summary_materials') and re.search(r'(?:20[0-9]{2}|二[零〇一二三四五六七八九]{3})年',field_text):
        raise SkillError('SKILL_EXPRESSION_UNSUPPORTED_YEAR')
    followup=state['fields'].get('followup',{}).get('value')
    if followup!='YES' and re.search(r'你.{0,3}(?:希望|需要|想要)人工',text):raise SkillError('SKILL_EXPRESSION_FOLLOWUP_CONFLICT')
    if re.search(r'(?:已|已经|会帮你|帮你).{0,6}(?:通知|安排|转接).{0,6}(?:人工|专员|顾问)',text):
        raise SkillError('SKILL_EXPRESSION_UNRECEIPTED_HANDOFF')


async def generate(model, work, provider_context, *, observer=None, deadline=None):
    """Called inside VoiceDialogue's existing absolute timeout and lease lock.

    Two reservations, two adapter charges, no retry. Cancellation propagates;
    unused reservations release in finally, sent attempts cannot be reversed.
    """
    from src.adapters.voice_call_budget import reserve, release
    reservation=reserve('LLM',2)
    if reservation is None:
        raise SkillError('SKILL_V2_EXPLICIT_BUDGET_REQUIRED')
    def record(**event):
        if observer:observer({'contract':work['bundle']['contract'],'monotonic':time.monotonic(),**event})
    async def call(stage, **kwargs):
        remaining = min(5.0, deadline-time.monotonic()) if deadline is not None else 5.0
        record(event='skill_request_started',stage=stage,remaining_seconds=remaining)
        try:
            async with asyncio.timeout(max(0,remaining)):
                result=await model.complete_structured(**kwargs)
            record(event='skill_request_completed',stage=stage,request_id=result.request_id,
                input_tokens=getattr(result,'input_tokens',None),output_tokens=getattr(result,'output_tokens',None))
            return result
        except BaseException as exc:
            record(event='skill_request_failed',stage=stage,error_type=type(exc).__name__)
            raise
    try:
        common=work['bundle']['method']
        v3=work['bundle']['contract']=='voice.skill-consultation.v3'
        if v3:
            provider_context={**provider_context,'runtime_handoff':runtime_handoff(work,provider_context.get('skill_knowledge',{}))}
        understood=await call('understanding',messages=[
            LLMMessage(role='system',content=common+'\n本次只做理解候选，禁止正文或next。逐字引用当前用户（v3仅可额外引用交接中pending_sources的原用户事件，须标source_turn_id），未提及的字段不补造；当前明确未知月份必须保留。intents只记录问答控制；无此控制就返回[]。按作用对象分别判断：停止业务操作或完成声明不是停止追问；人工意愿只是偏好。保留原文，不把所有否定塞进intents。'),
            LLMMessage(role='user',content=json.dumps(provider_context,ensure_ascii=False))],
            response_model=PendingUnderstanding if v3 else Understanding,schema_name='voice_skill_understanding_v3' if v3 else 'voice_skill_understanding_v2')
        record(event='skill_understanding_raw',request_id=understood.request_id,raw=understood.output.model_dump(mode='json'))
        state,frozen=plan(work,understood.output,provider_context.get('skill_knowledge',{}))
        record(event='skill_plan_tentative',accepted_snapshot=state,reply_plan=frozen.model_dump(mode='json'),committed=False)
        await asyncio.sleep(0)  # cancellation checkpoint before the dependent request
        expression_context={**provider_context,'communication_skill':{'accepted_snapshot':state,'reply_plan':frozen.model_dump(mode='json')}}
        if v3:
            # Do not hand the expression model the extraction feed or old assistant prose.
            # Actual journal remains untouched. It receives a role-selected projection.
            projection={k:state[k] for k in ('session_id','revision','fields','restrictions','selection','status','missing')}
            expression_context={
                'language':provider_context.get('language'),'summary_materials':state['summary_materials'],
                'communication_skill':{'accepted_snapshot':projection,'reply_plan':frozen.model_dump(mode='json')},
                'runtime_handoff':{'task_id':state['session_id']+':consultation','turn_id':work['turn_id'],
                    'revision':state['revision'],'binding':work['bundle']['sha256'],
                    'asked':state['asked'],'reply_plan':frozen.model_dump(mode='json')},
                'sources':provider_context.get('sources',{}),'information_status':provider_context.get('information_status',{})}
            record(event='skill_expression_materials',context=expression_context)
        expressed=await call('expression',messages=[
            LLMMessage(role='system',content=INSTRUCTION.replace('只输出kind和text的JSON。','只输出kind、text和plan_id的JSON。')+'\n'+common+'\n'+work['bundle']['persona']['method']+
                '\n'+work['bundle']['policy']['method']+'\n只输出kind/text/plan_id。按冻结计划自然解释已知部分及具体未知，不自行追问；应用另行附上计划问题。不能更新事实、权限或结束状态。篇幅:'+state['selection']['verbosity']+'；深度:'+state['selection']['depth']),
            LLMMessage(role='user',content=json.dumps(expression_context,ensure_ascii=False))],
            response_model=Expression,schema_name='voice_skill_expression_v2')
        record(event='skill_expression_raw',request_id=expressed.request_id,raw=expressed.output.model_dump(mode='json'))
        accept_expression(expressed.output,frozen,state)
        parts=[{'generator':'MODEL','text':expressed.output.text,'request_id':expressed.request_id}]
        if frozen.question_target:
            question=work['bundle']['template']['questions'][state['selection']['persona']][frozen.question_target]
            parts.append({'generator':'APPLICATION','text':question,'resource':work['bundle']['template']['id'],'target':frozen.question_target})
        record(event='skill_expression_accepted',reply_plan=frozen.model_dump(mode='json'),parts=parts,committed=False)
        return expressed,state,parts,{'understanding':understood.request_id,'expression':expressed.request_id,
            'input_tokens':(sum(r.input_tokens for r in (understood,expressed)) if all(getattr(r,'input_tokens',None) is not None for r in (understood,expressed)) else None),
            'output_tokens':(sum(r.output_tokens for r in (understood,expressed)) if all(getattr(r,'output_tokens',None) is not None for r in (understood,expressed)) else None)}
    finally:
        release(reservation)
        record(event="skill_reservation_released")
