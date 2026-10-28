"""Small, operator-curated public-source index. No network, embedding or answer cache.

Registry is re-read per lookup, including the pre-acceptance freshness check.
Only passages, never saved answers, are returned. Scope is demo configuration,
not customer identity or delegated enterprise authority.
"""
import asyncio
import hashlib
import json
from pathlib import Path

from src.application.voice_communication import KnowledgeResult, KnowledgePassage


def _normalize(text):
    from opencc import OpenCC
    return OpenCC('t2s').convert(text).lower()


class PublicKnowledge:
    def __init__(self, registry, *, scope, authorized=True):
        self.registry = Path(registry)
        self.scope = dict(scope)
        self.authorized = authorized

    async def lookup(self, *, question, session_id, context=None):
        if not self.authorized:
            return KnowledgeResult(status='UNAUTHORIZED', reason='DEMO_SOURCE_ACCESS_DENIED')
        try:
            data = await asyncio.to_thread(self.registry.read_text)
            index = json.loads(data)
            return self._lookup(index, question, context or {})
        except (OSError, ValueError, KeyError, TypeError):
            return KnowledgeResult(status='UNAVAILABLE', reason='SOURCE_INDEX_READ_OR_VALIDATION_FAILED')

    def _lookup(self, index, question, context):
        q = _normalize(question)
        # Explicit foreign scope is not overridden by an earlier matching user turn.
        utterances = [*context.get('user_history', []), question]
        active = [s for s in index['sources'] if s['enabled']]
        if not active:
            return KnowledgeResult(status='STALE', reason='SOURCE_DISABLED')
        scoped = [s for s in active if s['scope'] == self.scope]
        if not scoped:
            return KnowledgeResult(status='NOT_APPLICABLE', reason='CONFIGURED_SCOPE_MISMATCH')
        passages = []
        confirmed = False
        for source in scoped:
            # Latest explicit institution/region/channel mention governs applicability.
            matched = False
            for text in utterances:
                t = _normalize(text)
                if any(_normalize(x) in t for x in source['out_of_scope_terms']):
                    matched = False
                elif any(_normalize(x) in t for x in source['scope_aliases']):
                    matched = True
            if not matched:
                continue
            confirmed = True
            for p in source['passages']:
                if not any(_normalize(k) in q for k in p['retrieval_terms']):
                    continue
                version = hashlib.sha256(p['text'].encode()).hexdigest()
                if version != p['sha256']:
                    raise ValueError('PASSAGE_HASH_MISMATCH')
                passages.append(KnowledgePassage(source_id=source['id'], passage_id=p['id'],
                    url=source['url'], title=source['title'], version=version,
                    scope=source['scope'], text=p['text'], topic=p['topic']))
        if not confirmed:
            return KnowledgeResult(status='NOT_APPLICABLE', reason='EXPLICIT_APPLICABLE_USER_SCOPE_REQUIRED')
        if not passages:
            return KnowledgeResult(status='NO_MATCH', reason='QUESTION_NOT_COVERED_BY_ENABLED_PASSAGES')
        passages = tuple(passages[:3])
        return KnowledgeResult(status='FOUND', passages=passages,
            source_refs=tuple(f'{p.source_id}/{p.passage_id}@{p.version}' for p in passages),
            reason='PUBLIC_DEMO_SCOPE_AND_PASSAGES_MATCHED')


def configured_knowledge(profile):
    from src.application.voice_communication import UnconfiguredKnowledge
    config = profile.get('knowledge')
    if not config:
        return UnconfiguredKnowledge()
    if config.get('mode') != 'PUBLIC_DEMO_ONLY':
        raise ValueError('KNOWLEDGE_MODE_UNSUPPORTED')
    return PublicKnowledge(config['registry'], scope=config['scope'], authorized=config.get('authorized', False))
