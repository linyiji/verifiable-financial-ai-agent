"""Ordinary model wire and bounded business-assertion checks, not a truth prover.

No action/target/reference is requested from this conversational model. The old
operation plugin keeps its strict grounding. Text cannot authorize any tool.
These checks catch explicit unsupported claim forms; semantic adequacy is a
separate evaluation, never inferred from a model's kind or a source identifier.
"""
import re
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

REVISION = 'voice.communication.v2'
PROMPT_VERSION = 'ordinary-communication-knowledge-v1'
ACCEPTANCE_VERSION = 'ordinary-boundaries-knowledge-v2'


class ModelReply(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['answer', 'clarification']
    text: str = Field(min_length=1, max_length=500)


INSTRUCTION = (
    '你是普通保险咨询助手，用自然香港粤语繁体回应。只输出kind和text的JSON。'
    '理解当前问题并承接本会话用户原话；更正替代旧意向，但不是后台业务变更。'
    '直接回答能解释的部分，不重复询问已明确对象；仅追问影响当前问题的缺口，不猜异常词。'
    '一般概念解释只描述使用者做甚么，不能由使用者动作推导机构下一步或个案状态。整理是核对内容，递交是发出申请；两者均不证明受理、开始处理或生效，未递交也不证明现有安排不变。具体机构的文件、截止、生效与处理起算均需机构来源。'
    'sources中机构规则/个案记录为空时，明确具体未知，可建议向机构核对；'
    '不要先编一个具体结论再加“可能/请核对”。未提交不推出未生效；提交不推出开始处理。'
    '用户说法是用户资料，助手旧回答不是机构依据。技术未完成、未配置、无权限、未找到分别说明。用户说只想咨询，不足以推断此前没有任何提交或更改；只能说明本对话没有执行操作，实际状态未知。'
    '本会话没有提交、更改、查询账户或转人工执行能力；不要声称已查、正在办、已提交或改好。'
    '不提交操作与不声称完成是两种不同限制，保留对象和时间，不把释义或意向当授权。'
    '先答当前问题；后续轮次只回应新增或更正，非必要不重复解释和免责声明。不主动列无来源材料清单；有帮助的一般例子标明可选。sources.institution是本轮适用公开段落，只按命中内容回答，不推断页面未载的截止或生效保证，知识不等于个人账户查询。知识NO_MATCH未覆盖，NOT_APPLICABLE不适用，STALE停用，UNAUTHORIZED无权限，UNAVAILABLE技术故障，分别说明相关缺口。历史助手不是现行来源。回答有用部分后收口，不播内部字段。'
    '不填操作、引用或执行字段；重要要求完整优先于简短，避免重复，遵守256-token上限。'
)


def model_context(context):
    """A compact view of the existing journal, not a second memory store."""
    knowledge = context.get('knowledge_result') or {'status': 'NOT_CONFIGURED', 'source_refs': [], 'passages': []}
    current_refs = set(knowledge.get('source_refs', []))
    history = [h for h in context.get('voice_history', [])
               if not h.get('knowledge_refs') or set(h['knowledge_refs']).issubset(current_refs)]
    return {
        'current_utterance': context['current_utterance'],
        'history': [{k: x[k] for k in ('role', 'content', 'source', 'turn_id', 'publication_state') if k in x}
                    for x in history],
        'current_restriction_cues': context.get('constraint_cues', []),
        'capabilities': {'account_mutation_capability': False, 'account_query_capability': False,
                         'handoff_capability': False},
        'sources': {'institution': knowledge.get('passages', []), 'records': [], 'operation_receipts': []},
        'information_status': {'knowledge': knowledge['status'], 'knowledge_reason': knowledge.get('reason'), 'records': 'UNAUTHORIZED'},
        'language': context.get('session_language', 'auto'),
    }


@lru_cache(maxsize=1)
def _normalizer():
    from opencc import OpenCC
    return OpenCC('t2s')


# Explicit protected assertions only. The checker never returns a certificate
# that arbitrary natural prose is true. Originals are untouched; normalization
# is local to detection and recorded spans are explicitly normalized diagnostics.
_CLAIMS = (
    ('UNSOURCED_INSTITUTION_RULE', r'(?:保险公司|公司|机构|保诚).{0,16}(?:规定|要求(?:你|客户|提供|递交|提交|准备)|必须|一律|会在|将于)'),
    ('UNSOURCED_MATERIAL_REQUIREMENT', r'(?:必须|需要|一定要|要提供|要交).{0,10}(?:身份证|银行结单|证明文件|申请表格)'),
    ('UNSOURCED_PROCESS_START', r'(?:提交|送达|交表|交咗|递交).{0,24}(?:就|便|即|先|才|之后|后).{0,10}(?:开始|计处理|生效)'),
    ('UNSOURCED_EFFECT_INFERENCE', r'(?:未|没有|冇)(?:提交|递交).{0,8}(?:就|即|代表|一定).{0,8}(?:未|冇|不|无).{0,3}生效'),
    ('UNSOURCED_DEADLINE', r'(?:截止|最迟).{0,8}[一二三四五六七八九十廿\d]+(?:号|日|月)'),
    ('UNSOURCED_CONCRETE_TIMING', r'[一二三四五六七八九十百\d]+(?:个)?(?:工作天|工作日|天|日).{0,8}(?:生效|受理|处理|完成)'),
    ('UNRECEIPTED_LOOKUP', r'(?:我|我哋|系统)(?:已经|已|刚刚)?(?:帮你|替你)?(?:查到|查过|查咗|核实咗)'),
    ('UNRECEIPTED_COMPLETION', r'(?:已经|已)(?:经)?(?:成功)?(?:帮你|替你)?(?:提交|更改|改好|办好|处理好|生效|受理)'),
    ('UNRECEIPTED_CASE_STATUS', r'(?:你嘅|你的|你个|你個|你).{0,10}(?:更改|申请|户口|个案)(?:而家|现在|目前)?(?:已|未|正在|已经|没有).{0,5}(?:生效|受理|处理中|改好|提交)'),
    ('UNAUTHORIZED_ACTION_PROMISE', r'(?:我|我哋|系统)(?:会|将|即刻|而家)(?:帮你|替你)?(?:提交|更改|暂停|办理|转接)'),
)
_EPISTEMIC_PREFIX = re.compile(r'(?:唔知|不知道|唔确定|不确定|未能确认|确认唔到|无法确认|不能确认|唔可以确认|唔会(?:自动)?代表|不会(?:自动)?代表|唔代表|不代表|未等于|唔等于|不等于|未足以确认|唔足以确认)')
_REPORTED_USER = re.compile(r'(?:你提到|你表示|你话|你讲|按你所讲|据你所述)')


def accept_body(text, *, knowledge=None):
    normalized = _normalizer().convert(text)
    findings = []
    knowledge = knowledge or {}
    topics = {p['topic'] for p in knowledge.get('passages', [])} if knowledge.get('status')=='FOUND' else set()
    # Only actual matched passages support these institutional UI facts. FOUND
    # never bypasses the existing process/timing/case/receipt guards below.
    for clause in re.split(r'[。；;！？!?]', normalized):
        if re.search(r'(?:登入|登录|选择|揀|可以|可于|透过).*(?:myprudential|缴费设定)', clause, re.I):
            if 'navigation' not in topics and not _EPISTEMIC_PREFIX.search(clause):
                findings.append({'code': 'UNSOURCED_NAVIGATION', 'normalized_excerpt': clause})
    for clause in re.split(r'[。；;！？!?]', normalized):
        for code, expression in _CLAIMS:
            for match in re.finditer(expression, clause):
                before = clause[:match.start()]
                # A bare timing question is not a processing/effect assertion.
                # Restrict this exemption to the entire matched span; later
                # definite claims still receive their own evidence checks.
                if code == 'UNSOURCED_PROCESS_START' and re.fullmatch(
                    r'(?:提交|送达|交表|交咗|递交)(?:之后|后)(?:几时|何时|什么时候)(?:先|才)?(?:开始|计处理|生效)',
                    match.group(0),
                ):
                    continue
                # Local epistemic/negative scope, not a global hedge that can
                # license a concrete assertion in a later clause.
                uncertainty = list(_EPISTEMIC_PREFIX.finditer(before))
                if uncertainty and not re.search(r'但|不过|然而|实际上|实际上', before[uncertainty[-1].end():]):
                    continue
                if code == 'UNRECEIPTED_COMPLETION' and re.search(r'(?:唔|不)(?:会|能|可以|好|要)(?:话|说|声称|表示|当|认为|假定|推断)(?:你|你嘅|你的|本次|该申请|今次|此项)?$', before):
                    continue
                if code == 'UNRECEIPTED_CASE_STATUS' and _REPORTED_USER.search(before):
                    continue
                findings.append({'code': code, 'normalized_excerpt': match.group(0)})
    return {
        'candidate_status': 'REJECTED_PROTECTED_ASSERTION' if findings else 'ACCEPTED_CONVERSATION',
        'generator': 'MODEL', 'text': None if findings else text,
        'reason': 'Explicit business assertion lacks applicable evidence' if findings else
                  'Ordinary conversation accepted; no exact-material requirement and no execution authority',
        'findings': findings, 'acceptance_version': ACCEPTANCE_VERSION,
        'semantic_quality': 'REQUIRES_SEPARATE_CONTENT_REVIEW',
        'coverage': 'Bounded assertion forms, not exhaustive semantic or factual proof',
        'source_authority': 'PUBLIC_DEMO_PASSAGES_ONLY_NO_CASE_AUTHORITY' if topics else 'NO_INSTITUTION_OR_CASE_EVIDENCE',
        'source_refs': knowledge.get('source_refs', []) if topics else [],
        'knowledge_status': knowledge.get('status', 'NOT_CONFIGURED'),
    }
