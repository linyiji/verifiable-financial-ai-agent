import { useMemo } from "react";
import { researchPlanLabel } from "../../pages/NewResearchTaskPage";
import { PHASE4_TASK_STATUS_LABELS } from "../../state/status";
import type { RunProjection } from "../../types/domain";
import { OverlaySurface } from "../overlays/OverlaySurface";

const AGENT_LABELS: Readonly<Record<string, string>> = {
  research_lead: "Research Lead",
  research_news_analyst: "研究与事件分析师",
  fundamental_analyst: "Fundamental Analyst",
  peer_analyst: "Peer Analyst",
  valuation_analyst: "Valuation Analyst",
  risk_analyst: "Risk Analyst"
};

function agentLabel(value: string): string {
  return AGENT_LABELS[value.trim().toLowerCase()] ?? value.replace(/_/gu, " ");
}

const TASK_PURPOSES: Readonly<Record<string, string>> = {
  verified_financial_evidence: "核验本次研究所需的公司金融数据及其期间口径。",
  evidence_collection: "核验本次研究所需的公司金融数据及其期间口径。",
  fundamental_analysis: "分析公司的增长、盈利能力、现金流与经营质量。",
  peer_analysis: "对照同业公司的经营表现与关键金融指标。",
  research_and_news_analysis: "梳理影响公司判断的研究信息与重要事件。",
  research_news_analysis: "梳理影响公司判断的研究信息与重要事件。",
  valuation_analysis: "基于已核验数据评估公司的估值水平与关键假设。",
  risk_analysis: "识别并评估可能影响研究结论的主要风险。",
  risk_follow_up: "对已识别的重要风险信号进行边界明确的补充验证。",
  report_synthesis: "汇总各研究任务的结果并形成一致的研究结论。"
};

function taskPurpose(taskType: string, backendGoal: string): string {
  const normalized = taskType.trim().toLowerCase().replace(/[\s-]+/gu, "_");
  return TASK_PURPOSES[normalized] ?? backendGoal;
}

function formatTimestamp(value: string): string {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString("zh-CN");
}

export function TaskDetailDrawer({ projection, taskId, onClose }: {
  readonly projection: RunProjection;
  readonly taskId: string | null;
  readonly onClose: () => void;
}) {
  const task = useMemo(() => {
    if (taskId === null) return null;
    const matches = projection.tasks.filter((candidate) => candidate.taskId === taskId);
    return matches.length === 1 ? matches[0] : undefined;
  }, [projection.tasks, taskId]);

  const activity = useMemo(() => task
    ? projection.activity.filter((item) => item.taskId === task.taskId).slice().sort((a, b) => a.sequence - b.sequence)
    : [], [projection.activity, task]);
  const changes = useMemo(() => task
    ? projection.pathChanges.filter((change) => change.taskRefs.includes(task.taskId))
    : [], [projection.pathChanges, task]);
  const taskById = useMemo(() => new Map(projection.tasks.map((candidate) => [candidate.taskId, candidate])), [projection.tasks]);

  if (taskId === null) return null;

  return <OverlaySurface
    kind="drawer"
    titleId="task-drawer-title"
    className="rr-task-drawer"
    onClose={onClose}
    footer={<><span className="small">精确 Research Run · 只读</span><button type="button" className="btn" onClick={onClose}>关闭</button></>}
  >
    <div className="drawer-head">
      <div><span className="eyebrow">RESEARCH TASK</span><strong id="task-drawer-title">{task ? researchPlanLabel(task.taskType) : "Task 暂不可用"}</strong></div>
      <button type="button" className="btn ghost" data-autofocus onClick={onClose} aria-label="关闭任务详情">✕</button>
    </div>
    <div className="drawer-body" data-testid="task-detail-drawer" data-task-id={taskId}>
      {task === undefined
        ? <div className="drawer-unavailable" role="alert">当前权威投影中没有唯一匹配的 Task；未使用其他 Task 替代。</div>
        : task === null
          ? null
          : task.runId !== projection.run.runId
            ? <div className="drawer-unavailable" role="alert">该 Task 不属于当前 Research Run，无法显示。</div>
            : <>
                <div className="task-drawer-summary">
                  <span className={`task-state-dot ${task.status.toLowerCase()}`} aria-hidden="true" />
                  <div><span>当前状态</span><strong>{PHASE4_TASK_STATUS_LABELS[task.status]}</strong><small>研究进度 {Math.round(task.progress * 100)}%</small></div>
                </div>
                <section className="drawer-section"><h3>研究任务</h3><p>{taskPurpose(task.taskType, task.goal)}</p><dl className="drawer-facts"><dt>负责人</dt><dd>{agentLabel(task.assignedAgent)}</dd><dt>创建来源</dt><dd>{task.origin === "REPLAN" ? "Research Lead 批准的 Replan" : "初始研究计划"}</dd><dt>创建时间</dt><dd>{formatTimestamp(task.createdAt)}</dd></dl></section>
                <section className="drawer-section"><h3>依赖关系</h3>{task.dependencies.length === 0 ? <p className="muted">该 Task 没有前置依赖。</p> : <ul className="reference-list">{task.dependencies.map((dependency) => <li key={dependency}>{taskById.has(dependency) ? researchPlanLabel(taskById.get(dependency)!.taskType) : dependency}</li>)}</ul>}</section>
                {changes.length > 0 && <section className="drawer-section"><h3>路径调整</h3>{changes.map((change) => <div className="drawer-change" key={change.pathChangeId}><strong>{change.changeKind === "SELF_CORRECTION" ? "期间数据修正" : "新增风险跟进任务"}</strong><span>{change.reasonCode ?? "研究路径调整"} · {change.decision ?? change.status}</span></div>)}</section>}
                <details className="technical-details drawer-technical"><summary>Task 技术详情</summary><dl><dt>Task ID</dt><dd>{task.taskId}</dd><dt>Run ID</dt><dd>{task.runId}</dd><dt>Raw goal</dt><dd>{task.goal}</dd><dt>Raw status</dt><dd>{task.backendStatus}</dd><dt>Projected status</dt><dd>{task.status}</dd><dt>Skill ID</dt><dd>{task.skillId}</dd><dt>Attempt</dt><dd>{task.attemptCount}</dd></dl>{activity.length > 0 && <div className="safe-activity"><strong>安全可观察活动</strong>{activity.map((item) => <div key={item.eventId}><span>{formatTimestamp(item.timestamp)}</span><code>{item.messageCode}</code></div>)}</div>}</details>
              </>}
    </div>
  </OverlaySurface>;
}
