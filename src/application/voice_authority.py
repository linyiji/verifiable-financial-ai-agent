"""Read-only VeFin receipt projection. Never starts, confirms, or repairs a Run."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class AuthorityReceipt:
    task_id: str
    run_id: str | None
    version: str
    occurred_at: datetime
    reason: str
    text: str
    source_event_id: str


async def read_receipt(app, task_id: str) -> AuthorityReceipt | None:
    from src.application.errors import ApplicationError
    if not getattr(app.state, "research_task_service", None):
        raise ApplicationError("VOICE_BUSINESS_PORT_UNAVAILABLE", "Research authority port is not installed.", status_code=503)
    task = await app.state.research_task_service.get_research_task(task_id)
    if task is None:
        return None
    result = await app.state.research_start_service.get_active_run(task_id)
    if result is None:
        plans = getattr(app.state, "research_planning_repository", None)
        executability = getattr(app.state, "research_plan_executability", None)
        latest = await plans.get_latest_by_task(task_id) if plans else None
        assessment = (
            await executability._governance.get_assessment(latest.session.id)
            if latest and executability
            else None
        )
        if assessment and assessment.plan_hash == latest.session.plan_hash:
            # Read an already-created assessment; voice never invokes assess() or repairs.
            status = assessment.status.value
            reason = "waiting_user" if status in {"Ready", "NeedsUserDecision"} else "blocked"
            descriptions = "；".join(item.description for item in assessment.blocking_items)
            text = (
                "方案评估回执已收到，请在研究界面完成确认和启动。"
                if status == "Ready"
                else f"方案评估状态为 {status}，研究尚未启动。{descriptions}"
            )
            return AuthorityReceipt(
                task_id,
                None,
                f"assessment:{assessment.id}:{status}",
                assessment.created_at,
                reason,
                text[:4000],
                assessment.id,
            )
        # A Task Draft is not an assessment or an accepted execution.
        return AuthorityReceipt(
            task_id,
            None,
            f"task:{task.status}",
            task.created_at,
            "waiting_user",
            "研究任务已绑定。请在研究界面确认问题和方案后明确启动。",
            f"task:{task.id}:{task.status}",
        )
    run_id = result.run.id
    projection = await app.state.run_lifecycle_projection.get_status(run_id)
    timeline = await app.state.research_execution_observability.timeline(run_id)
    latest = timeline.events[-1] if timeline.events else None
    occurred = (
        latest.created_at
        if latest
        else projection.updated_at
        if projection and projection.updated_at
        else task.created_at
    )
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=UTC)
    state = projection.execution_status.value if projection else "Unknown"
    assurance = getattr(app.state, "research_ai_assurance", None)
    attempts = assurance.history(run_id) if assurance else []
    attempt = attempts[-1] if attempts else None
    try:
        from src.domain.services.research_ai_assurance import POLICY, current_review_policy
    except ModuleNotFoundError as exc:
        raise ApplicationError("VOICE_BUSINESS_PORT_UNAVAILABLE", "Research authority policy is not installed.", status_code=503) from exc

    publication_service = getattr(app.state, "research_publication_service", None)
    publication = publication_service._catalog.get(run_id) if publication_service else None
    version = hashlib.sha256(
        (
            f"{POLICY}:{run_id}:{state}:{latest.id if latest else 'none'}:"
            f"{attempt['id'] if attempt else ''}:"
            f"{attempt['status'] if attempt else ''}:"
            f"{publication.publication.id if publication else ''}"
        ).encode(),
    ).hexdigest()
    source = latest.id if latest else f"run:{run_id}:{state}"
    if publication:
        reason, text = "published", "用户已明确批准并发布这份研究报告，请查看已发布版本及其限制。"
        source = publication.publication.id
        occurred = publication.publication.published_at
    elif attempt and attempt["status"] == "ReportReady" and not current_review_policy(attempt):
        reason, text = (
            "blocked",
            "历史报告草稿可回查，按当前审核规则仍需复核。请查看历史回执并明确决定是否恢复。",
        )
        source = attempt["id"] + ":policy-review-required"
    elif attempt and attempt["status"] == "ReportReady":
        reason, text = (
            "report_ready",
            "报告草稿可查看。独立 AI 校验已完成，缺口和限制已披露，等待你的发布决定。",
        )
        source = attempt["id"]
        occurred = datetime.fromisoformat(attempt["receipts"][-1]["completed_at"])
    elif attempt and attempt["status"] in {"Blocked", "Interrupted"}:
        reason, text = (
            "missing_evidence",
            "执行已完成，AI 复核或报告校验受阻。请查看缺证或失败记录，补充后明确恢复。",
        )
        source = attempt["id"] + ":" + attempt["status"]
        occurred = datetime.fromisoformat(
            attempt.get("failure", {}).get("at", attempt["created_at"])
        )
    elif state == "Completed" and attempt and attempt["status"] == "Running":
        reason, text = "execution_complete", "研究执行完成待复核。结论与报告尚未获准发布。"
    elif latest and latest.event_type.value in {"blocked", "failed"}:
        reason, text = "blocked", f"研究当前受阻，尚未完成。{latest.message}"
    elif latest and latest.event_type.value == "waiting_user":
        reason, text = "waiting_user", f"研究需要你的确认。{latest.message}"
    elif state == "Completed":
        reason, text = "execution_complete", "研究执行完成待复核。结论与报告尚未获准发布。"
    elif state in {"Unknown", "Failed", "Cancelled"}:
        reason, text = "blocked", "执行状态尚未确认或执行已停止，不能宣称研究完成。"
    else:
        reason, text = "progress", "VeFin 已接收执行请求，研究仍在进行，等待权威回执。"
    return AuthorityReceipt(task_id, run_id, version, occurred, reason, text[:4000], source)
