"""V1.1 ordinary communication contracts, scoped to the existing consultation.

No model, credentials, business executor or second conversation store lives here.
The bounded preflight grammar is deliberately not a general semantic classifier.
Unmatched inputs retain the existing grounding/body boundary.
"""
from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

REVISION = "voice.communication.v1"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DialogueResult(Contract):
    schema_version: Literal["voice.dialogue.v1"] = "voice.dialogue.v1"
    kind: Literal["answer", "clarification", "delegation", "handoff"]
    reply_text: str = Field(min_length=1)
    # This consultation has no delegation or mutation capability. A future task
    # adapter must supply its own strict request contract, not untyped dictionaries.
    delegations: list = Field(default_factory=list, max_length=0)
    task_update_proposals: list = Field(default_factory=list, max_length=0)


class KnowledgePassage(Contract):
    source_id: str
    passage_id: str
    url: str
    title: str
    version: str
    scope: dict[str, str]
    text: str
    topic: str


class KnowledgeResult(Contract):
    status: Literal["FOUND", "NO_MATCH", "NOT_CONFIGURED", "STALE", "CONFLICT", "UNAUTHORIZED", "UNAVAILABLE", "NOT_APPLICABLE"]
    reason: str | None = None
    passages: tuple[KnowledgePassage, ...] = ()
    source_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def source_boundary(self):
        if self.status == "FOUND" and not self.source_refs:
            raise ValueError("FOUND_REQUIRES_SOURCE")
        if self.status != "FOUND" and self.passages:
            raise ValueError("NON_FOUND_PASSAGE_DISCLOSURE")
        if self.status == "UNAUTHORIZED" and self.source_refs:
            raise ValueError("UNAUTHORIZED_SOURCE_DISCLOSURE")
        return self


class RecordResult(Contract):
    status: Literal["FOUND", "NOT_FOUND", "UNAUTHORIZED", "UNAVAILABLE", "FAILED"]
    source_ref: str | None = None
    as_of: str | None = None
    request_ref: str | None = None

    @model_validator(mode="after")
    def source_boundary(self):
        if self.status == "FOUND" and not all((self.source_ref, self.as_of, self.request_ref)):
            raise ValueError("RECORD_RECEIPT_REQUIRED")
        if self.status == "UNAUTHORIZED" and any((self.source_ref, self.as_of, self.request_ref)):
            raise ValueError("UNAUTHORIZED_RECORD_DISCLOSURE")
        return self


class KnowledgePort(Protocol):
    async def lookup(self, *, question: str, session_id: str, context: dict | None = None) -> KnowledgeResult: ...


class RecordPort(Protocol):
    async def lookup(self, *, question: str, session_id: str) -> RecordResult: ...


class UnconfiguredKnowledge:
    async def lookup(self, **kwargs) -> KnowledgeResult:
        return KnowledgeResult(status="NOT_CONFIGURED")


class UnauthorizedRecords:
    async def lookup(self, **kwargs) -> RecordResult:
        # No tenant/customer identity is inferred from a voice session or text.
        return RecordResult(status="UNAUTHORIZED")


class AnswerPlan(Contract):
    route: Literal["GENERAL_CONCEPT", "KNOWLEDGE_GAP", "RECORD_GAP"]
    answerable: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    knowledge: KnowledgeResult | None = None
    record: RecordResult | None = None
    disposition: Literal["ANSWERED", "PARTIAL", "TECHNICAL_INCOMPLETE"]
    material_version: str


# Whole-clause routing only. Never use a keyword anywhere in a long utterance
# to suppress the remainder or infer that a user requested/authorized an action.
CONCEPT_QUESTION = re.compile(
    r"(?:我想(?:問|问|了解))?(?:準備|准备)(?:資料|资料)?(?:同|和|與|与)"
    r"(?:正式)?提交(?:申請|申请)?(?:有咩|有什麼|有什么|嘅)?(?:分別|分别|區別|区别)"
)
RULE_QUESTION = re.compile(
    r"(?:呢間|這家|这家|呢家)(?:公司|機構|机构)(?:\d{1,2}月|十二月)?"
    r"(?:更改|變更|变更)(?:扣款)?(?:戶口|户口|帳戶|账户)"
    r"(?:嘅|的)?(?:截止日|截止日期|時限|时限)(?:係幾時|是什麼|是什么|係乜嘢)"
)
RECORD_QUESTION = re.compile(
    r"(?:我嘅|我的)(?:更改|變更|变更)(?:而家|現在|现在)"
    r"(?:生效未|生效了嗎|生效了吗|有冇生效)"
)


async def plan_ordinary_question(context, *, knowledge: KnowledgePort, records: RecordPort):
    """Return an application plan/text or None; all ports default to explicit gaps.

Ports currently carry capability/status only, not authority to publish a found
document or record. FOUND stays review-required until EN05 is implemented.
Canceled/expired calls propagate to VoiceDialogue's existing absolute deadline.
"""
    from src.application.voice_consultation import CONCEPT_TEXT, CONCEPT_VERSION

    if context.get("constraint_cues"):
        return None
    clauses = [x.strip() for x in re.split(r"[。！？!?；;]", context["current_utterance"]) if x.strip()]
    if not clauses:
        return None
    concept = [x for x in clauses if CONCEPT_QUESTION.fullmatch(x)]
    rules = [x for x in clauses if RULE_QUESTION.fullmatch(x)]
    cases = [x for x in clauses if RECORD_QUESTION.fullmatch(x)]
    if len(concept) > 1 or len(rules) + len(cases) > 1 or len(concept) + len(rules) + len(cases) != len(clauses):
        return None
    if concept and not rules and not cases:
        return AnswerPlan(route="GENERAL_CONCEPT", answerable=("preparation_submission",),
                          disposition="ANSWERED", material_version=CONCEPT_VERSION), CONCEPT_TEXT
    sid = context["object_references"]["session_id"]
    answerable = ("preparation_submission",) if concept else ()
    prefix = CONCEPT_TEXT if concept else ""
    if rules:
        result = await knowledge.lookup(question=rules[0], session_id=sid)
        explanations = {
            "NOT_CONFIGURED": "目前未接入呢間機構嘅規則資料，確認唔到呢個截止日。",
            "NO_MATCH": "今次獲准查閱嘅資料未搵到足夠依據，唔代表機構冇呢項規定。",
            "STALE": "現有資料已過期，確認唔到現行截止日。",
            "NOT_APPLICABLE": "現有資料唔適用於今次問題嘅範圍，未能確認截止日。",
            "CONFLICT": "現有來源互有衝突，未能確認應採用邊項規定。",
            "UNAUTHORIZED": "目前冇權限查閱所需機構資料。",
            "UNAVAILABLE": "資料服務暫時無法完成查閱，未能確認截止日。",
            "FOUND": "已取得來源引用，但適用範圍尚未完成核對，未能確認截止日。",
        }
        plan = AnswerPlan(route="KNOWLEDGE_GAP", answerable=answerable,
                          gaps=("institution_rule",), knowledge=result,
                          disposition="TECHNICAL_INCOMPLETE" if result.status == "UNAVAILABLE" else "PARTIAL",
                          material_version="knowledge-gap-v1")
        return plan, prefix + explanations[result.status] + "可以向機構核對適用規定。"
    if cases:
        result = await records.lookup(question=cases[0], session_id=sid)
        explanations = {
            "UNAUTHORIZED": "目前未具備查閱你個案嘅權限，確認唔到更改有冇生效。",
            "UNAVAILABLE": "個案查詢服務暫時未能完成查詢，確認唔到實際狀態。",
            "FAILED": "今次個案查詢未完成，唔可以據此判斷更改有冇生效。",
            "NOT_FOUND": "今次查詢未取得對應記錄，唔代表更改冇發生或未生效。",
            "FOUND": "已取得記錄引用，但業務結果尚未完成核對，未能確認生效狀態。",
        }
        plan = AnswerPlan(route="RECORD_GAP", answerable=answerable, gaps=("case_status",), record=result,
                          disposition="TECHNICAL_INCOMPLETE" if result.status in {"UNAVAILABLE", "FAILED"} else "PARTIAL",
                          material_version="record-gap-v1")
        return plan, prefix + explanations[result.status] + "可以向機構核對個案狀態。"
    return None


def turn_result(text, effective_kind, policy, plan=None):
    """Project the accepted dialogue only; publication remains Worker-owned."""
    result = DialogueResult(kind="clarification" if effective_kind == "clarification" else "answer",
                            reply_text=text)
    return {
        "dialogue_result": result.model_dump(mode="json"),
        "answer_plan": plan.model_dump(mode="json") if plan else None,
        "reply_result": {"generator": policy["generator"],
                         "candidate_status": policy["candidate_status"],
                         "semantic_quality": "NOT_PROVEN_BY_CONTRACT",
                         "material_version": policy.get("material_version")},
        "turn_outcome": {"disposition": plan.disposition if plan else
                         "NEEDS_CLARIFICATION" if effective_kind == "clarification" else "ANSWERED",
                         "business_execution": "NO_WRITE_EXECUTION",
                         "delivery": "NOT_STARTED"},
    }
