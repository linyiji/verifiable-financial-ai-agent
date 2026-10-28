"""Scoped meaning assessment and application clarification, on the existing journal.

Identity provenance is deterministic; GENERAL/UNKNOWN judgments supplied by the
same dialogue model remain semantic judgments, not verified institution facts.
"""
import hashlib
import re

REVISION = 'procedure-provenance-v3-meaning-v3'
CONTRACT = 'user-object-meaning-v3'


def prepare_meaning_context(context, previous=None):
    refs = context['object_references']; table = refs['object_targets']
    objects = table['objects']; previous = previous or {}
    if previous.get('session_id') != refs['session_id']: previous = {}
    pending = [dict(x) for x in previous.get('pending', [])]
    active = [x for x in refs['relations'] if x['status'] == 'ACTIVE']
    for item in pending:
        definitions = [x for x in active if x['term'] == item['label']]
        if len(definitions) == 1:
            item.update(status='RESOLVED_BY_USER', relation_id=definitions[0]['id'],
                        meaning=definitions[0]['meaning'])
    # Quoted literal identities support consultation without an action directive.
    mentions = [(m.group(1), refs['current_turn_id'], [m.start(1),m.end(1)])
                for m in re.finditer(r'[「“"]([^」”"\n]{1,60})[」”"]',context['current_utterance'])]
    mentions += [(p['label'],p['source_turn'],p['source_span']) for p in pending
                 if p['status'] in {'PENDING','DEFERRED'}]
    for label, turn, span in mentions:
        if any(x['label'] == label for x in objects): continue
        key=hashlib.sha256(f"{refs['session_id']}:{refs['current_turn_id']}:{turn}:{span}:{label}:meaning".encode()).hexdigest()[:10]
        objects.append({'id':key,'label':label,'speaker':'current_user','session_id':refs['session_id'],
            'turn_id':turn,'source':'literal_mention_or_pending_user_question','span':span,
            'status':'ACTIVE','relation_id':None,'instruction_links':[]})
    for obj in objects:
        definitions = [x for x in active if obj['label'] in {x['term'],x['meaning']}]
        ambiguous = [x for x in refs['relations'] if x['status']=='AMBIGUOUS' and x['term']==obj['label']]
        obj['identity_valid'] = True
        obj['meaning_status'] = 'USER_DEFINED' if len(definitions)==1 else 'AMBIGUOUS' if ambiguous else 'UNASSESSED'
        obj['meaning_source'] = definitions[0]['id'] if len(definitions)==1 else None
        obj['operation_authorization'] = 'NOT_GRANTED_BY_IDENTITY_OR_DEFINITION'
    context['clarification_context'] = {'contract':CONTRACT,'session_id':refs['session_id'],
        'pending':pending,'last_asked_key':previous.get('last_asked_key'),
        'rule':'Only unresolved/ambiguous meaning that affects the current answer or operation needs a question. Unassessed is not unknown. General concepts and irrelevant words do not automatically block.',
        'resume':'When the user resolves a pending term, continue its original user question using latest user corrections; never turn an explanation into authorization.'}
    return context


def neutral_question(label, language='yue-HK'):
    return f'你講嘅「{label}」係指邊樣嘢？' if language=='yue-HK' else f'你说的“{label}”具体指什么？'


def meaning_decision(reply, context):
    from src.application.voice_dialogue import VoiceGroundingError
    refs=context['object_references']; objects=refs['object_targets']['objects']
    by_id={x['id']:x for x in objects}; checks=reply.meaning_checks
    if set(checks)-set(by_id): raise VoiceGroundingError('Meaning assessment references an unknown object')
    pending=[dict(x) for x in context['clarification_context']['pending']]
    state={'contract':CONTRACT,'session_id':refs['session_id'],'pending':pending,'last_asked_key':None}
    assessed=[]; required=[]
    for obj in objects:
        value=checks.get(obj['id'])
        if obj['meaning_status']=='USER_DEFINED':
            if value in {'UNKNOWN','AMBIGUOUS'}:
                raise VoiceGroundingError('Meaning assessment ignores an active user explanation')
            meaning='USER_DEFINED';basis='USER_REPORT_NOT_INSTITUTION_FACT'
        else:
            if value is None: raise VoiceGroundingError('Missing same-call meaning assessment')
            meaning={'GENERAL':'GENERAL_CONCEPT','UNKNOWN':'UNRESOLVED','AMBIGUOUS':'AMBIGUOUS','UNRELATED':'UNRESOLVED_IRRELEVANT'}[value]
            basis='SAME_CALL_MODEL_JUDGMENT_NOT_FACT_PROOF'
        needed=value in {'UNKNOWN','AMBIGUOUS'} and meaning!='USER_DEFINED'
        assessed.append({'target_ref':obj['id'],'label':obj['label'],'identity_valid':True,
            'meaning_status':meaning,'basis':basis,'affects_current_answer':needed,
            'operation_authorization':'NO_EXECUTION_CAPABILITY',
            'source_turn':obj['turn_id'],'source_span':obj['span']})
        if needed: required.append(obj)
    decision={'assessments':assessed,'state':state,'branch':'MODEL_REPLY','generator':'MODEL',
        'model_clarification_quality':'NOT_REQUIRED','replacement_text':None,'trigger':None}
    if not required: return decision
    obj=required[0]
    key=hashlib.sha256(f"{refs['session_id']}:{obj['label']}".encode()).hexdigest()[:16]
    item=next((x for x in pending if x['key']==key),None)
    if item is None:
        item={'key':key,'label':obj['label'],'source_turn':obj['turn_id'],'source_span':obj['span'],
            'original_utterance':context['current_utterance'],'status':'PENDING','consecutive_asks':0}
        pending.append(item)
    previous_key=context['clarification_context'].get('last_asked_key')
    count=item.get('consecutive_asks',0) if previous_key==key else 0
    state['last_asked_key']=key
    question=neutral_question(obj['label'],context.get('session_language','auto'))
    # Exact application-approved semantics only. Arbitrary wording is not accepted
    # by punctuation, kind, keywords, or an extra model judgment.
    accepted=reply.text.strip()==question
    decision.update(trigger={'target_ref':obj['id'],'pending_key':key,'meaning':next(x for x in assessed if x['target_ref']==obj['id']),
        'question_acceptance':'EXACT_APPROVED_NEUTRAL_QUESTION_ONLY'},
        model_clarification_quality='APPROVED_NEUTRAL_QUESTION' if accepted else 'MISSING_OR_UNVERIFIED_QUESTION_RAW_RETAINED')
    if count>=2:
        item.update(status='DEFERRED',consecutive_asks=2)
        decision.update(branch='SYSTEM_CLARIFICATION',generator='APPLICATION',replacement_text=
            f'「{obj["label"]}」仲未釐清。你可以換個講法，或者暫時放低呢一項。')
        return decision
    item.update(status='PENDING',consecutive_asks=count+1)
    # Preserve a literal current user's intention separately from operation facts.
    intents=[]
    for clause in re.split(r'[，,。；;！？!?]',context['current_utterance']):
        if re.search(r'(職員|职员|佢|他|她).*(話|话|說|说)',clause): continue
        m=re.search(r'我想[^，,。；;！？!?]{1,80}',clause)
        if m: intents.append(m.group())
    prefix=(f'你提到「{intents[0]}」，呢個係你嘅打算。' if intents else '')
    decision.update(branch='MODEL_CLARIFICATION' if accepted else 'SYSTEM_CLARIFICATION',
        generator='MODEL_APPROVED_QUESTION_WITH_APPLICATION_CONTEXT' if accepted else 'APPLICATION',
        replacement_text=prefix+question)
    return decision
