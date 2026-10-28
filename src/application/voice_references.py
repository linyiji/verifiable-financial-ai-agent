"""Literal, session-scoped user definitions; never a dictionary or account authority.

This is a derived view of the existing user journal. Original text and superseded
relations remain visible. Unsupported phrasing stays unresolved, not guessed.
"""
import hashlib
import re

CONTRACT = 'user-object-reference-v1'
# Only first-person declarations, with no quoted third-party reporter prefix.
_DEFINITION = re.compile(
    r'我(?:之前|頭先|头先)?(?:講|讲|說|说|所講|所讲)(?:嘅|的)?\s*'
    r'(?P<term>[^，,。；;！？!?\n]{1,60}?)\s*'
    r'(?:即係|即系|係指|系指|是指|意思係|意思是)\s*'
    r'(?P<meaning>[^，,。；;！？!?\n]{1,60})')
_REPORT = re.compile(r'(?:職員|职员|佢|他|她|對方|对方).*(?:話|话|說|说|表示)')
_CORRECT = re.compile(r'更正|講錯|讲错|說錯|说错|改口|唔係.*(?:而係|而系)|不是.*而是')

def _span(text, start, end):
    raw=text[start:end];clean=raw.strip(' \t「」『』“”\"\'')
    offset=raw.find(clean)
    return clean, start+offset, start+offset+len(clean)


def user_reference_context(utterance, history=(), *, session_id, turn_id):
    relations=[]
    sources=[(x.get('content',''),str(x.get('turn_id') or f'history:{i}'))
             for i,x in enumerate(history)
             if x.get('role')=='user' and x.get('source','user_report')=='user_report'
             and x.get('session_id',session_id)==session_id
             and x.get('restored_from_session',session_id)==session_id]
    sources.append((utterance,turn_id))
    for text,turn in sources:
        for m in _DEFINITION.finditer(text):
            boundary=max((text.rfind(p,0,m.start()) for p in '，,。；;！？!?\n'),default=-1)
            prefix=text[boundary+1:m.start()]
            if (_REPORT.search(prefix) or re.search(r'如果|假如|係咪|是否|未確認|未确认|唔知',prefix)
                    or text[m.end():m.end()+1] in {'？','?'}):
                continue
            term,a,z=_span(text,*m.span('term'));meaning,b,y=_span(text,*m.span('meaning'))
            if not term or not meaning or term==meaning:continue
            key=hashlib.sha256(f'{session_id}:{turn}:{m.start()}:{m.group()}'.encode()).hexdigest()[:16]
            previous=[x for x in relations if x['term']==term and x['status']!='SUPERSEDED']
            previous_clause=re.split(r'[，,。；;！？!?\n]',text[:max(0,boundary)])[-1].strip()
            correction=bool(_CORRECT.search(prefix) or re.fullmatch(
                r'(?:我)?(?:更正|講錯|讲错|說錯|说错|改口)[：:]?',previous_clause))
            row={'id':key,'term':term,'meaning':meaning,'speaker':'current_user',
                 'session_id':session_id,'turn_id':turn,'source':'user_report',
                 'term_span':[a,z],'meaning_span':[b,y],
                 'evidence':m.group(),'evidence_span':[m.start(),m.end()],
                 'status':'ACTIVE','supersedes':[],
                 'authority':'USER_MEANING_ONLY_NOT_INSTITUTION_OR_PERMISSION'}
            for old in previous:
                if correction or old['meaning']==meaning:
                    old['status']='SUPERSEDED';old['superseded_by']=key;row['supersedes'].append(old['id'])
                else:
                    old['status']='AMBIGUOUS';row['status']='AMBIGUOUS'
            relations.append(row)
    return {'contract':CONTRACT,'session_id':session_id,'current_turn_id':turn_id,
            'relations':relations,'active_ids':[x['id'] for x in relations if x['status']=='ACTIVE'],
            'scope':'Only the current authenticated user in this session; no assistant guesses or third-party equivalence'}


def linked_omitted_object(target, evidence, utterance, context, *, action):
    """A unique explicit user definition can anchor an omitted current object.

    The action, negation, time and evidence remain current-utterance literals.
    A direct conflicting object is never replaced with a definition's target.
    """
    # A following literal object is not an omitted object, even if a definition
    # elsewhere happens to mention the model's proposed target.
    if action not in evidence or evidence.split(action,1)[1].strip(' \t。！？!?'):
        return False
    if linked_consultation_instruction(target, evidence, utterance, context, action=action):
        return True
    active=[x for x in context.get('relations',[]) if x['status']=='ACTIVE']
    matches=[x for x in active if target in {x['term'],x['meaning']}]
    if len(matches)!=1:return False
    selected=matches[0]
    mentioned=[x for x in active if x['term'] in utterance or x['meaning'] in utterance]
    if mentioned:
        return len(mentioned)==1 and mentioned[0]['id']==selected['id']
    return len(active)==1


def reject_definition_target(target, context):
    """Return a reason, never truncate/repair a model's malformed object."""
    for rel in context.get('relations',[]):
        if target not in {rel['term'],rel['meaning']} and rel['term'] in target and rel['meaning'] in target:
            return 'Definition relationship is not a target identity'
    return None


TARGET_CONTRACT = 'user-object-target-ref-v2'


def object_target_candidates(utterance, context, cues):
    """Server-owned literal identities, scoped to this user/session/turn.

    A candidate supplies identity, never permission. Allowed links retain the
    current directive; definitions alone cannot create one.
    """
    rows = []
    def add(label, source, source_turn, span, relation_id=None):
        key = hashlib.sha256(f"{context['session_id']}:{context['current_turn_id']}:{source_turn}:{span}:{label}:{relation_id}".encode()).hexdigest()[:10]
        row = {'id': key, 'label': label, 'speaker': 'current_user',
               'session_id': context['session_id'], 'turn_id': source_turn,
               'source': source, 'span': span, 'status': 'ACTIVE',
               'relation_id': relation_id, 'instruction_links': []}
        if not any(x['id'] == key for x in rows): rows.append(row)
        return next(x for x in rows if x['id'] == key)
    for rel in context['relations']:
        if rel['status'] != 'ACTIVE': continue
        # The user's original name is one identity. Meaning remains a separate
        # sourced relation, not a concatenated business object.
        add(rel['term'], 'user_definition', rel['turn_id'], rel['term_span'], rel['id'])
    for cue in cues:
        label = cue.get('target')
        if not label:
            start = utterance.find(cue['evidence'])
            verb = r'(?<![更修])改' if cue['action'] == '改' else re.escape(cue['action'])
            earlier = list(re.finditer(verb + r'([^，,。；;！？!?]+)', utterance[:start]))
            if earlier:
                label = earlier[-1].group(1).strip()
        if label:
            start = utterance.find(label)
            add(label, 'current_user_literal', context['current_turn_id'], [start, start+len(label)])
    for row in rows:
        for cue in cues:
            target = cue.get('target')
            linked = (row['label'] == target) if target else linked_omitted_object(
                row['label'], cue['evidence'], utterance, context, action=cue['action'])
            if not target and not linked:
                start = utterance.find(cue['evidence'])
                verb = r'(?<![更修])改' if cue['action'] == '改' else re.escape(cue['action'])
                earlier = list(re.finditer(verb + r'([^，,。；;！？!?]+)', utterance[:start]))
                linked = bool(earlier and row['label'] == earlier[-1].group(1).strip())
            if linked:
                row['instruction_links'].append({k: cue.get(k, '') for k in
                    ('action','stance','domain','time_scope','evidence')})
    return {'contract': TARGET_CONTRACT, 'session_id': context['session_id'],
            'turn_id': context['current_turn_id'], 'objects': rows,
            'authority': 'IDENTITY_ONLY_NOT_PERMISSION_OR_EXECUTION'}


def linked_consultation_instruction(target, evidence, utterance, context, *, action):
    """Validate server-constructed link; current action and prior identity separate."""
    matches=[o for o in context.get('object_targets',{}).get('objects',[])
             if o.get('label')==target and o.get('source')=='confirmed_consultation_change_instruction']
    if len(matches)!=1:return False
    obj=matches[0];link=obj.get('consultation_link',{})
    if (obj.get('status')!='ACTIVE' or obj.get('speaker')!='current_user'
        or obj.get('session_id')!=context['session_id'] or link.get('session_id')!=context['session_id']
        or link.get('action_source_turn')!=context['current_turn_id']
        or link.get('action_source_utterance')!=utterance):return False
    a,b=link.get('object_span',[-1,-1]);source=link.get('source_utterance','')
    if a<0 or source[a:b]!=link.get('object_evidence') or obj.get('verbatim_label')!=source[a:b]:return False
    return action=='提交' and action in evidence and evidence in utterance and any(
        x['domain']=='operation' and x['stance']=='forbid' and x['action']==action and x['evidence']==evidence
        for x in obj.get('instruction_links',[]))
