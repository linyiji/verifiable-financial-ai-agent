"""Opt-in consultation scope; no tools, no account authority, no word classifier."""
REVISION = 'procedure-provenance-v3-consultation-v1'


def prepare_consultation(context, previous_responses=()):
    # Dialogue already obtains same-session journal history. Do not turn the
    # prior assistant's explanation into user evidence or institution authority.
    context['consultation_scope'] = {
        'version': 'insurance-consultation-v1',
        'capabilities': ['explain_concepts', 'organize_user_intent', 'identify_missing_information'],
        'write_operations': False,
        'supported_change_options': [],
        'rule': 'Clarify only a gap affecting the current goal that the user can supply. Answer independent known parts. No mandatory meaning inventory.',
        'history_authority': 'User reports are not verified account facts; assistant replies are not institution sources.',
        'max_consecutive_clarifications': 2,
    }
    previous = next(((e.get('data') or {}).get('consultation_policy', {}).get('pending')
                     for e in previous_responses if (e.get('data') or {}).get('consultation_policy', {}).get('pending')), None)
    if previous:
        pending = dict(previous)
        import re
        # Explicit current-user reply only; not assistant guesses or reported speech.
        match = re.match(r'^[係系]([^，。！？]{1,40})[，。]', context['current_utterance'])
        if pending.get('status') == 'PENDING' and match:
            pending.update(status='RESOLVED_BY_USER', user_explanation=match.group(1),
                           resolution_turn=context['object_references']['current_turn_id'],
                           parsing_record={'original_prefix': match.group(0)[0], 'interpretation': 'explicit_current_user_explanation', 'raw_unchanged': True})
        context['consultation_scope']['pending'] = pending
    link_confirmed_consultation_object(context)
    return context


def preflight_clarification(context):
    """Conservative explicit-intent grammar, not a general semantic classifier.
    Only a literal generic arrangement with no supplied subtype and a current
    first-person change intention qualifies. Concept questions never enter.
    """
    import re
    text = context['current_utterance']
    if re.search(r'[？?]|有咩|點樣|分別|区别|區別', text): return None
    intent = re.search(r'(?:^|[，。])(?P<intent>我想(?P<when>下個月|下个月|十二月|遲啲|迟点)?(?:改|更改)扣款安排)(?=[，。]|$)',text)
    if not intent: return None
    # A pre-existing user discussion can contain a supplied subtype. Be
    # conservative: this first-turn shortcut does not guess across that history.
    if any(x.get('role')=='user' for x in context.get('voice_history',context.get('history',[]))): return None
    pending=context['consultation_scope'].get('pending')
    if pending and pending.get('status')!='PENDING': return None
    objects=context['object_references']['object_targets']['objects']
    generic=[x for x in objects if x['label']=='扣款安排' and x['speaker']=='current_user' and x['status']=='ACTIVE' and x['instruction_links']]
    if len(generic)!=1 or any(x['label']!='扣款安排' and x['instruction_links'] for x in objects):return None
    if not all(link['stance']=='forbid' for link in generic[0]['instruction_links']):return None
    return {'status':'PENDING','label':generic[0]['label'],'target_ref':generic[0]['id'],
            'source_turn':context['object_references']['current_turn_id'],
            'intent_evidence':intent.group('intent'),'intent_span':list(intent.span('intent')),
            'reason':'User explicitly considers changing the generic payment arrangement; the intended part is not supplied, and determines what preparation advice is relevant.',
            'question':f"你想更改「{generic[0]['label']}」嘅邊一項？"}


def clarification_reply_fields(context, gap):
    constraints=[]
    for obj in context['object_references']['object_targets']['objects']:
        constraints.extend({**link,'target_ref':obj['id']} for link in obj['instruction_links'])
    return {'kind':'clarification',
            'text':f"你提到「{gap['intent_evidence']}」。{gap['question']}",
            'constraints':constraints}


def consultation_decision(reply, previous_responses):
    """Lifecycle guard, not a semantic validator of model questions or answers."""
    consecutive = 0
    for event in previous_responses:
        if (event.get('data') or {}).get('reply_kind') != 'clarification': break
        consecutive += 1
    if reply.kind == 'clarification' and consecutive >= 2:
        return {'status': 'DEFERRED', 'generator': 'APPLICATION',
                'replacement_text': '呢項資料仲未釐清。你可以換個講法，或者暫時放低呢一項；未有真人接入。',
                'model_quality': 'NOT_PROVEN_BY_LIFECYCLE_GUARD'}
    return {'status': 'AWAITING_USER' if reply.kind == 'clarification' else 'REPLY_REQUIRES_CONTENT_REVIEW',
            'generator': 'MODEL', 'replacement_text': None,
            'model_quality': 'NOT_PROVEN_BY_SCHEMA_OR_KIND'}


# Reviewed application material, not institution-specific policy or account evidence.
CONCEPT_VERSION = 'preparation-submission-concepts-v1'
CONCEPT_TEXT = '準備係整理同核對擬使用嘅資料；提交係向機構發送申請或指示。提交本身唔足以確認已獲受理、開始處理、獲授權執行或生效。個案嘅實際狀態同扣款安排，要有機構資料先可以確認。'


def accept_consultation_body(text, context, *, application_clarification=False, reviewed_sources=()):
    """Closed, narrow material acceptance, NOT a general fact classifier.
    Arbitrary model prose is not proven by a regex, schema, or a source ID.
    reviewed_sources is server-owned exact claim material, never model/user IDs.
    """
    if application_clarification:
        return {'candidate_status':'NOT_CALLED', 'generator':'APPLICATION', 'text':text,
                'reason':'grounded application clarification', 'material_version':CONCEPT_VERSION}
    if text == CONCEPT_TEXT:
        return {'candidate_status':'ACCEPTED', 'generator':'MODEL', 'text':text,
                'reason':'exact reviewed generic material', 'material_version':CONCEPT_VERSION}
    for source in reviewed_sources:
        if source.get('server_reviewed') is True and source.get('scope')=='current_consultation' and source.get('exact_claim')==text and source.get('evidence_text')==text:
            return {'candidate_status':'ACCEPTED', 'generator':'MODEL', 'text':text,
                    'reason':'exact server-reviewed scoped evidence', 'source':source['id'], 'material_version':CONCEPT_VERSION}
    import re
    utterance=context['current_utterance']
    pending=context['consultation_scope'].get('pending',{})
    concept = bool(re.search(r'(準備|准备).*提交.*(分別|分别|區別|区别)',utterance))
    correction = re.search(r'更正[，,。 ]*[係系]?(?P<when>12月|十二月)先(?:考慮|考虑)改',utterance)
    if pending.get('status')=='RESOLVED_BY_USER' and (concept or correction):
        prefix=(f"你最新嘅打算係{correction.group('when')}先考慮更改。" if correction else '')
        return {'candidate_status':'REJECTED_UNVERIFIED_PROSE','generator':'APPLICATION',
                'text':prefix+CONCEPT_TEXT,'reason':'Independent reviewed concept response to confirmed question; model prose not accepted',
                'material_version':CONCEPT_VERSION}
    return {'candidate_status':'REJECTED_UNVERIFIED_PROSE','generator':None,'text':None,
            'reason':'No safely scoped application response; block before TTS','material_version':CONCEPT_VERSION}


def acceptance_receipt(session_id, turn_id, text, policy):
    import hashlib
    return {'status':'ACCEPTED_FINAL','session_id':session_id,'turn_id':turn_id,
            'text_sha256':hashlib.sha256(text.encode()).hexdigest(),**{k:v for k,v in policy.items() if k!='text'}}


def verify_acceptance(receipt, session_id, turn_id, text):
    import hashlib
    return bool(receipt and receipt.get('status')=='ACCEPTED_FINAL'
                and receipt.get('session_id')==session_id and receipt.get('turn_id')==turn_id
                and receipt.get('text_sha256')==hashlib.sha256(text.encode()).hexdigest())


def link_confirmed_consultation_object(context):
    """Narrow omitted-submit link, derived again from actual user journal.
    No inherited permission, model output, or last-mentioned-object guessing.
    """
    import re, hashlib
    scope=context['consultation_scope']; refs=context['object_references']
    pending=scope.get('pending',{})
    text=context['current_utterance']; current=refs['current_turn_id']; sid=refs['session_id']
    cues=[c for c in context.get('constraint_cues',[]) if c['domain']=='operation'
          and c['action']=='提交' and c['stance']=='forbid' and not c.get('target')]
    if not cues:return
    table=refs['object_targets']
    missing=[c for c in cues if not any(c['evidence']==l['evidence'] and l['domain']=='operation'
             for obj in table['objects'] for l in obj['instruction_links'])]
    if not missing:return
    review={'status':'UNRESOLVED','current_turn':current,'action_cues':missing,
            'scope':'CURRENT_SESSION_CONFIRMED_CHANGE_INTENTION_ONLY'}
    scope['reference_link_review']=review
    users=[x for x in context.get('voice_history',[]) if x.get('role')=='user'
           and x.get('source')=='user_report' and x.get('session_id',sid)==sid
           and x.get('restored_from_session',sid)==sid]
    if pending.get('status')!='RESOLVED_BY_USER':
        review['reason']='NO_VALID_CONFIRMED_OBJECT';return
    origin=[x for x in users if x.get('turn_id')==pending.get('source_turn')]
    resolutions=[x for x in users if x.get('turn_id')==pending.get('resolution_turn')]
    if len(origin)!=1 or len(resolutions)!=1 or not users or users[-1] is not resolutions[0]:
        review['reason']='SOURCE_MISSING_EXPIRED_OR_TOPIC_CHANGED';return
    # Verify the original intention as well as the user's explicit reply. The
    # assistant's safe concept answer need not repeat any object name.
    if not pending.get('intent_evidence') or pending['intent_evidence'] not in origin[0]['content']:
        review['reason']='INTENTION_SOURCE_MISMATCH';return
    m=re.match(r'^[係系]([^，。！？]{1,40})[，。]',resolutions[0]['content'])
    if not m or m.group(1)!=pending.get('user_explanation'):
        review['reason']='CONFIRMATION_SOURCE_MISMATCH';return
    label=m.group(1);source=resolutions[0];span=list(m.span(1))
    # Explicit current correction can replace the confirmed name, never a date.
    replacement=re.match(r'^(?:更正[，,。 ]*)?[係系]([^，。！？]{1,40})[，。]',text)
    if replacement and not re.search(r'月|考慮|考虑',replacement.group(1)):
        label=replacement.group(1);source={'content':text,'turn_id':current};span=list(replacement.span(1))
    if re.search(r'同|及|與|与|、|或者|或|唔係|不是|撤回|取消|唔改|不改',label) or re.search(r'另外|換個話題|换个话题|唔再|不再|撤回',text):
        review['reason']='AMBIGUOUS_CHANGED_OR_WITHDRAWN';return
    # Only the confirmed payment-object family is supported by this local link.
    # It is not a lexicon for unknown terms and does not interpret arbitrary nouns.
    if not re.fullmatch(r'扣款(?:戶口|户口|日期|金額|金额)',label):
        review['reason']='UNSUPPORTED_OBJECT_SCOPE';return
    # Avoid switching to another explicit payment object in non-correction prose.
    mentions=set(re.findall(r'扣款(?:戶口|户口|日期|金額|金额)',text))
    if mentions and mentions!={label}:
        review['reason']='MULTIPLE_OR_CONFLICTING_CURRENT_OBJECTS';return
    display=label+'變更指示'
    relation_id=None
    key=hashlib.sha256(f"{sid}:{current}:{source['turn_id']}:{span}:{display}:{relation_id}".encode()).hexdigest()[:10]
    linkage={'session_id':sid,'intention_source_turn':pending['source_turn'],
             'intention_evidence':pending['intent_evidence'],'object_source_turn':source['turn_id'],
             'object_evidence':label,'object_span':span,'source_utterance':source['content'],
             'action_source_turn':current,'action_source_utterance':text,
             'basis':'Unique current consultation intention plus explicit user object confirmation',
             'authority':'USER_INTENTION_ONLY_NO_AUTHORIZATION_OR_EXECUTION'}
    obj={'id':key,'label':display,'verbatim_label':label,'label_is_verbatim':False,
         'speaker':'current_user','session_id':sid,'turn_id':source['turn_id'],
         'source':'confirmed_consultation_change_instruction','span':span,'status':'ACTIVE',
         'relation_id':None,'consultation_link':linkage,
         'instruction_links':[{k:c.get(k,'') for k in ('action','stance','domain','time_scope','evidence')} for c in missing]}
    table['objects'].append(obj)
    review.update(status='LINKED',candidate=obj)


def preflight_concept_reply(context):
    """Opt-in closed concept route, before model invocation.

    Every current clause must fit the supported question/explanation grammar;
    unresolved or additional requests stay on the existing guarded path. This
    is not a general intent classifier and grants no action authority.
    """
    import re
    pending = context['consultation_scope'].get('pending', {})
    refs = context['object_references']
    text = context['current_utterance']
    if context.get('constraint_cues') or pending.get('status') != 'RESOLVED_BY_USER':
        return None
    label = pending.get('user_explanation', '')
    if not re.fullmatch(r'扣款(?:戶口|户口|日期|金額|金额)', label):
        return None
    # Revalidate current user's literal explanation and original intention.
    if pending.get('resolution_turn') != refs['current_turn_id']:
        return None
    introduction = re.match(r'^[係系]([^，,。！？!?]{1,40})[，,。]', text)
    if not introduction or introduction.group(1) != label:
        return None
    origin = [x for x in context.get('voice_history', [])
              if x.get('role') == 'user' and x.get('source') == 'user_report'
              and x.get('turn_id') == pending.get('source_turn')
              and x.get('session_id', refs['session_id']) == refs['session_id']
              and x.get('restored_from_session', refs['session_id']) == refs['session_id']]
    if len(origin) != 1 or not pending.get('intent_evidence') or pending['intent_evidence'] not in origin[0]['content']:
        return None
    clauses = [c.strip() for c in re.split(r'[，,。；;！？!?]', text[introduction.end():]) if c.strip()]
    question = r'(?:我想(?:問|问|了解))?(?:準備|准备)(?:資料|资料)?(?:同|和|與|与)(?:正式)?提交(?:申請|申请)?(?:有咩|有什麼|有什么|嘅)?(?:分別|分别|區別|区别)'
    neutral = r'(?:我)?(?:想|打算)(?:先)?(?:準備|准备)(?:資料|资料)|(?:我)?(?:仲未|還未|还未|未)(?:正式)?提交'
    questions = [c for c in clauses if re.fullmatch(question, c)]
    if len(questions) != 1 or not all(re.fullmatch(question, c) or re.fullmatch(neutral, c) for c in clauses):
        return None
    return {'kind': 'conversation', 'text': CONCEPT_TEXT, 'constraints': []}
