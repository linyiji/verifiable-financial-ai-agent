"""Minimal freshness policy over exact released public memory."""

from src.domain.incremental import IncrementalDecision, IncrementalResearchContext
from src.phase4_product.safety import safe_text


def validate_incremental_scheme(scheme, context):
    if not scheme.generated_model or scheme.incremental_context is None:
        raise ValueError("incremental scheme requires real AI generation")
    candidate = scheme.incremental_context
    original = context.model_dump(exclude={"decisions"})
    if candidate.model_dump(exclude={"decisions"}) != original:
        raise ValueError("AI scheme changed exact base context")
    if tuple(d.model_dump(exclude={"reason", "decision"}) for d in candidate.decisions) != tuple(
        d.model_dump(exclude={"reason", "decision"}) for d in context.decisions
    ):
        raise ValueError("AI scheme changed governed decision or immutable source")
    IncrementalResearchContext.model_validate(candidate.model_dump())
    for original_decision, decision in zip(context.decisions, candidate.decisions, strict=True):
        if original_decision.decision == "UNKNOWN" and decision.decision != "UNKNOWN":
            raise ValueError("UNKNOWN source cannot acquire unsupported applicability")
        safe_text(decision.reason, max_length=2000)


def resolve_incremental_decisions(context, proposals):
    """Model selects within authoritative policy; exact coverage includes UNKNOWN."""
    identities = [p.source_identity for p in proposals]
    if len(set(identities)) != len(identities) or set(identities) != {
        d.source_identity for d in context.decisions
    }:
        raise ValueError("decision proposal requires unique exact source coverage")
    by_id = {p.source_identity: p for p in proposals}
    decisions = []
    for original in context.decisions:
        proposal = by_id[original.source_identity]
        if original.decision == "UNKNOWN" and proposal.decision != "UNKNOWN":
            raise ValueError("UNKNOWN does not silently become applicable")
        decisions.append(
            IncrementalDecision.model_validate(
                {
                    **original.model_dump(),
                    "decision": proposal.decision,
                    "reason": safe_text(proposal.reason, max_length=2000),
                }
            )
        )
    return IncrementalResearchContext.model_validate(
        {
            **context.model_dump(),
            "decisions": decisions,
        }
    )


def bind_incremental_plan(graph, context):
    """Constrain fresh tasks without importing historical runtime artifacts."""
    if graph.run_id == context.base_run_id:
        raise ValueError("incremental plan must have a new Run")
    tasks = []
    for task in graph.tasks:
        if task.run_id != graph.run_id or not task.task_id.startswith(graph.run_id + ":"):
            raise ValueError("foreign incremental task identity")
        if task.task_input_evidence_ids or task.task_output_evidence_ids or task.result_ref:
            raise ValueError("initial incremental plan cannot inherit evidence or results")
        constraint = (
            " Incremental policy: prior research is historical context only. "
            "Acquire fresh evidence owned by this Run; revalidate financial claims with new "
            "calculations, review and proof. Do not inherit prior approval."
        )
        if any(d.decision == "PREVENT" for d in context.decisions):
            constraint += " Check financial input period consistency before calculations."
        tasks.append(task.model_copy(update={"goal": task.goal + constraint}))
    return graph.model_copy(update={"tasks": tasks})


def build_incremental_context(view, *, object_id, base_run_id, base_view_id, target_as_of):
    if (view.research_object_id, view.source_run_id, view.research_view_version_id) != (
        object_id,
        base_run_id,
        base_view_id,
    ):
        raise ValueError("incremental base identity mismatch")
    # Base context is not automatically a reusable research component.
    # Phase5A's REUSABLE_CONTEXT is NOT_OBSERVED; do not fabricate a fourth item.
    decisions = []
    rules = {
        "VERIFIED_METRIC": (
            "REFRESH",
            "财务输入具有时效性；本次重新获取证据并生成独立计算，不复制历史证据。",
        ),
        "VERIFIED_CLAIM": (
            "REVALIDATE",
            "保留研究问题，以本次数据重新计算、审核与验证；不继承历史批准。",
        ),
        "RESOLVED_ISSUE": (
            "PREVENT",
            "本次执行必须检查输入期间一致性，避免重复历史期间不匹配问题；保留原问题出处。",
        ),
    }
    for item in view.items:
        decision, reason = rules[item.category]
        if item.category == "RESOLVED_ISSUE" and item.statement != "PERIOD_MISMATCH":
            decision, reason = "UNKNOWN", "未观察到可执行的期间一致性约束；不自动沿用。"
        decisions.append(
            IncrementalDecision(
                decision=decision,
                source_run_id=item.source_run_id,
                source_identity=item.memory_item_id,
                category=item.category,
                statement=safe_text(item.statement, max_length=4000),
                reason=reason,
            )
        )
    return IncrementalResearchContext(
        research_object_id=object_id,
        base_run_id=base_run_id,
        base_research_view_version=base_view_id,
        base_version_number=view.research_view_version,
        base_as_of=view.as_of,
        target_as_of=target_as_of,
        prior_summary=safe_text(view.summary, max_length=4000) if view.summary else None,
        decisions=tuple(decisions),
    )
