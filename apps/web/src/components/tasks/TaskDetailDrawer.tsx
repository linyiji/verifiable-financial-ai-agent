import { useEffect, useMemo } from "react";
import type { ObservableTaskEvent, ResearchTask } from "../../types/domain";
import { OverlaySurface } from "../overlays/OverlaySurface";
import { TASK_STATUS_LABELS as STATUS_LABELS } from "../../state/status";

type TimelineEvent = { id: string; title: string; meta?: string; status: "done" | "live" | "waiting" | "warning"; timestamp?: string; anchor?: string };
const EVENT_STATUS: Record<ObservableTaskEvent["status"], TimelineEvent["status"]> = { DONE: "done", LIVE: "live", WAITING: "waiting", WARNING: "warning" };

function formatTimestamp(value?: string) {
  if (!value) return undefined;
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(timestamp);
}

export function TaskDetailDrawer({ task, claimId, targetAnchor, onOpenClaim, onClose }: {
  task: ResearchTask | null;
  claimId?: string | null;
  targetAnchor?: string | null;
  onOpenClaim?: (claimId: string) => void;
  onClose: () => void;
}) {
  const timeline = useMemo<TimelineEvent[]>(() => (task?.observableEvents ?? []).map((event) => ({ ...event, status: EVENT_STATUS[event.status] })), [task?.observableEvents]);

  useEffect(() => {
    if (!task || !targetAnchor) return;
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
      const target = document.getElementById(`task-event-${task.id}-${targetAnchor}`);
      target?.scrollIntoView({ block: "center" });
      target?.focus();
    }));
  }, [task, targetAnchor]);

  if (!task) return null;
  const isCorrecting = task.status === "SELF_CORRECTING";
  const isRunning = task.status === "RUNNING";
  const stateTitle = isCorrecting ? "原任务正在自我修正" : isRunning ? "AI 正在处理此研究任务" : task.status === "WAITING" ? "任务正在等待前置条件" : task.status === "READY" ? "任务已就绪" : STATUS_LABELS[task.status];

  return <OverlaySurface kind="drawer" titleId="task-drawer-title" className="rr-task-drawer" onClose={onClose} footer={
    <><button type="button" className="btn" onClick={onClose}>关闭</button><span className="small">Task projection · read only</span>{claimId && onOpenClaim && <button type="button" className="btn ghost sm" onClick={() => onOpenClaim(claimId)}>返回关联 Claim</button>}</>
  }>
    <div className="drawer-head"><div><strong id="task-drawer-title">{task.name}</strong><div className="small">{task.id} · {task.symbol} · {task.runId}</div></div><button type="button" className="btn ghost" data-autofocus onClick={onClose} aria-label="关闭任务详情">✕</button></div>
    <div className="drawer-body">
      <div className={`rr-task-state ${isRunning ? "active" : task.status.toLowerCase()}`}>
        {isCorrecting ? <div className="rr-loop-indicator">↻</div> : isRunning ? <div className="spinner" /> : <div className="rr-state-mark">{task.status === "COMPLETED" ? "✓" : task.status === "FAILED" ? "×" : task.status === "BLOCKED" ? "!" : "◷"}</div>}
        <div><div className="rr-state-line"><strong>{stateTitle}</strong><span className="badge neutral">{STATUS_LABELS[task.status]}</span></div><div className="small">{task.summary ?? "Unavailable in Pre-Integration"}</div>{task.progress !== undefined && task.status !== "COMPLETED" && <div className="rr-drawer-progress" role="progressbar" aria-label={`任务进度 ${task.progress}%`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={task.progress}><span style={{ width: `${Math.max(0, Math.min(100, task.progress))}%` }} /><small>{task.progress}%</small></div>}</div>
      </div>

      {task.supportingActivity && <div className={`rr-drawer-support ${task.supportingActivity.status.toLowerCase()}`}><span className="rr-support-icon">◇</span><div><div className="rr-state-line"><strong>Supporting Runtime Activity</strong><span className="badge neutral">{task.supportingActivity.status}</span></div><p>{task.supportingActivity.label}</p><small>{task.supportingActivity.capabilityId} · same Research Task</small><ol className="capability-lifecycle">{task.supportingActivity.lifecycle.map((step, index) => <li key={`${step.status}-${index}`}><strong>{step.status}</strong><span>{step.label}</span></li>)}</ol></div></div>}

      <div className="trace-card rr-task-trace">
        <TaskSection title="Task purpose" empty="Unavailable in Pre-Integration">{task.question}</TaskSection>
        <TaskSection title="Agent / Skill / Tool / Duration"><div className="detail-grid"><span>Agent</span><strong>{task.agentLabel ?? "Unavailable in Pre-Integration"}</strong><span>Skill</span><strong>{task.skillLabel ?? "Unavailable in Pre-Integration"}</strong><span>Tool / Capability</span><strong>{task.toolLabels?.join(" · ") ?? task.supportingActivity?.capabilityId ?? "Unavailable in Pre-Integration"}</strong><span>Duration</span><strong>{task.duration ?? "Unavailable in Pre-Integration"}</strong></div></TaskSection>
        <TaskSection title="Data / Evidence / Calculation"><div className="chips">{[...(task.dataRefs ?? []), ...(task.evidenceRefs ?? []), ...(task.calculationRefs ?? [])].map((ref) => <span className="chip2" key={ref}>{ref}</span>)}</div></TaskSection>
        <TaskSection title="Analysis / Conclusion" empty="Unavailable in Pre-Integration">{task.analysisSummary && <p>{task.analysisSummary}</p>}{task.conclusion && <strong>{task.conclusion}</strong>}</TaskSection>
        <TaskSection title="Correction / Replan / Error"><div className="task-fact-list"><span>Correction · {task.correctionSummary ?? "None"}</span><span>Replan · {task.replanSummary ?? "None"}</span><span>Error · {task.errorSummary ?? "None"}</span></div></TaskSection>
        {task.dependsOn?.length ? <TaskSection title="Task dependencies"><div className="chips">{task.dependsOn.map((id) => <span className="chip2" key={id}>{id}</span>)}</div></TaskSection> : null}
      </div>

      <div className="rr-timeline-heading"><strong>Trace · 可观察研究时间线</strong><div className="small">仅展示数据访问、校验、计算状态与执行结果，不展示隐藏思维过程。</div></div>
      {timeline.length ? <div className="timeline rr-task-timeline">{timeline.map((event) => <div className={`timeline-item ${event.status} ${targetAnchor === event.anchor ? "is-highlighted" : ""}`} id={`task-event-${task.id}-${event.anchor ?? event.id}`} key={event.id} tabIndex={-1}><div className="rr-event-topline"><div className="timeline-title">{event.title}</div>{event.timestamp && <time>{formatTimestamp(event.timestamp)}</time>}</div>{event.meta && <div className="timeline-meta">{event.meta}</div>}</div>)}</div> : <div className="rr-timeline-empty">Unavailable in Pre-Integration · 暂无可观察任务事件。</div>}
    </div>
  </OverlaySurface>;
}

function TaskSection({ title, empty, children }: { title: string; empty?: string; children?: React.ReactNode }) {
  const hasContent = Array.isArray(children) ? children.some(Boolean) : Boolean(children);
  return <div className="trace-section"><h4>{title}</h4>{hasContent ? children : <div className="small rr-empty-copy">{empty ?? "Unavailable in Pre-Integration"}</div>}</div>;
}
