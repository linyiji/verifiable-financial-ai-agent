import { useState } from "react";
import { researchPlanLabel } from "../pages/NewResearchTaskPage";
import { PHASE4_RUN_STATUS_META } from "../state/status";
import type { ConnectionState, RunProjection } from "../types/domain";
import { ResearchPath } from "./research-path/ResearchPath";
import { TaskDetailDrawer } from "./tasks/TaskDetailDrawer";

export interface ProjectionLifecycle {
  readonly runId: string;
  readonly requestEpoch: number;
  readonly settled: boolean;
  readonly consumed?: {
    readonly runId: string;
    readonly requestEpoch: number;
    readonly revision: number;
    readonly sequence: number;
  };
  readonly discarded?: {
    readonly runId: string;
    readonly requestEpoch: number;
    readonly revision: number;
    readonly sequence: number;
    readonly reason: string;
  };
}

export interface ResearchRuntimeWorkspaceProps {
  readonly projection: RunProjection;
  readonly connection: ConnectionState;
  readonly lifecycle: ProjectionLifecycle | null;
  readonly reportBaseUrl: string;
}

type WorkspaceStage = "plan" | "research" | "review" | "report" | "complete";
type StageState = "done" | "current" | "pending";

const CONNECTION_LABELS: Readonly<Record<ConnectionState["kind"], string>> = {
  IDLE: "准备同步",
  CONNECTING: "正在连接",
  OPEN: "实时同步中",
  RECOVERING: "正在恢复连接",
  BACKOFF: "等待重新连接",
  TERMINAL: "研究已完成",
  FAILED: "实时连接不可用"
};

const STAGES: readonly { id: WorkspaceStage; number: string; label: string }[] = [
  { id: "plan", number: "01", label: "研究计划" },
  { id: "research", number: "02", label: "AI研究" },
  { id: "review", number: "03", label: "质量复核" },
  { id: "report", number: "04", label: "报告生成" },
  { id: "complete", number: "05", label: "完成" }
];

function stageState(projection: RunProjection, stage: WorkspaceStage): StageState {
  const hasEvent = (type: string) => projection.activity.some((event) => event.type === type);
  const planDone = hasEvent("plan.generated") || projection.plannedGraph.tasks.length > 0;
  const researchStarted = hasEvent("run.started")
    || projection.run.startedAt !== null
    || projection.run.backendStatus === "RUNNING"
    || projection.run.stage === "RESEARCH";
  const reviewStarted = hasEvent("review.started") || hasEvent("review.resolved") || projection.review.reviewId !== null;
  const reviewDone = (
    hasEvent("review.resolved") && projection.review.status === "PASS"
  ) || (
    projection.review.availability.status === "AVAILABLE" && projection.review.status === "PASS"
  );
  const reportDone = hasEvent("release.completed")
    && projection.artifacts.availability.status === "AVAILABLE"
    && projection.artifacts.reportId !== null
    && projection.artifacts.representationIds.length > 0
    && projection.result.availability.status === "AVAILABLE";
  const completeDone = projection.run.backendStatus === "RELEASED"
    && projection.terminal.isTerminal
    && projection.terminal.outcome === "SUCCESS"
    && hasEvent("run.completed")
    && reportDone;

  if (stage === "plan") return planDone ? "done" : "current";
  if (stage === "research") {
    if (reviewStarted || reviewDone || reportDone || completeDone) return "done";
    return researchStarted ? "current" : "pending";
  }
  if (stage === "review") {
    if (reviewDone || reportDone || completeDone) return "done";
    return reviewStarted ? "current" : "pending";
  }
  if (stage === "report") {
    if (reportDone || completeDone) return "done";
    return reviewDone && !projection.terminal.isTerminal ? "current" : "pending";
  }
  return completeDone ? "done" : "pending";
}

function stageStateLabel(state: StageState, selected: boolean): string {
  if (selected) return "正在查看";
  if (state === "done") return "已完成";
  if (state === "current") return "当前阶段";
  return "等待中";
}

export function ResearchRuntimeWorkspace({ projection, connection, lifecycle, reportBaseUrl }: ResearchRuntimeWorkspaceProps) {
  const [selectedStage, setSelectedStage] = useState<WorkspaceStage>("research");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const runId = projection.run.runId;
  const status = PHASE4_RUN_STATUS_META[projection.run.status];
  const stale = connection.kind === "BACKOFF" || connection.kind === "RECOVERING";

  return <section
    className="workspace-main runtime-workspace"
    data-testid="run-workspace"
    data-run-id={runId}
    data-object-id={projection.object.objectId}
    data-goal-id={projection.goal.goalId}
    data-scheme-id={projection.confirmedScheme.schemeId}
    data-run-status={projection.run.backendStatus}
    data-run-stage={projection.run.stage}
    data-projection-revision={projection.projectionRevision}
    data-projection-sequence={projection.projectionSequence}
    aria-labelledby="research-run-title"
  >
    <header className="card workspace-shell-card workspace-header">
      <div className="workspace-heading">
        <div className="eyebrow">RESEARCH RUN</div>
        <h1 id="research-run-title">{projection.object.companyName}</h1>
        <p>完整公司金融研究</p>
        <div className="workspace-object">{projection.object.symbol} · Research Object</div>
      </div>
      <span className={`badge ${status.color}`}><span className="dot" />{status.label}</span>
    </header>

    <dl className="workspace-facts" aria-label="Research Run 摘要">
      <div><dt>Run ID</dt><dd>{runId}</dd></div>
      <div><dt>As-of</dt><dd>{projection.run.asOf}</dd></div>
      <div><dt>状态</dt><dd>{status.label}</dd></div>
    </dl>

    <div className="runtime-indicators" aria-label="运行同步状态">
      <div
        className="runtime-indicator"
        role="status"
        aria-live="polite"
        data-testid="runtime-connection"
        data-run-id={runId}
        data-connection-state={connection.kind}
        data-last-sequence={connection.lastSequence}
        data-stale={stale ? "true" : "false"}
      ><span className={`sync-dot ${stale ? "warning" : ""}`} aria-hidden="true" />实时状态：{CONNECTION_LABELS[connection.kind]}</div>
      <div
        className="runtime-indicator"
        role="status"
        data-testid="projection-lifecycle"
        data-run-id={lifecycle?.runId ?? runId}
        data-request-epoch={lifecycle?.requestEpoch ?? 0}
        data-settled={String(lifecycle?.settled ?? false)}
        data-consumed-run-id={lifecycle?.consumed?.runId ?? ""}
        data-consumed-request-epoch={lifecycle?.consumed?.requestEpoch ?? ""}
        data-consumed-projection-revision={lifecycle?.consumed?.revision ?? ""}
        data-consumed-projection-sequence={lifecycle?.consumed?.sequence ?? ""}
        data-last-discarded-run-id={lifecycle?.discarded?.runId ?? ""}
        data-last-discarded-request-epoch={lifecycle?.discarded?.requestEpoch ?? ""}
        data-last-discarded-projection-revision={lifecycle?.discarded?.revision ?? ""}
        data-last-discarded-projection-sequence={lifecycle?.discarded?.sequence ?? ""}
        data-last-discard-reason={lifecycle?.discarded?.reason ?? ""}
      >数据状态：{lifecycle?.settled ? "当前视图已同步" : "正在载入权威视图"}</div>
    </div>

    <ol className="run-lifecycle" aria-label="Research Run 生命周期">
      {STAGES.map((stage) => {
        const state = stageState(projection, stage.id);
        const selected = selectedStage === stage.id;
        return <li key={stage.id} className={`${state} ${selected ? "selected" : ""}`}>
          <button
            type="button"
            disabled={state === "pending"}
            aria-pressed={selected}
            onClick={() => setSelectedStage(stage.id)}
          >
            <span className="lifecycle-number">{state === "done" ? "✓" : stage.number}</span>
            <span><strong>{stage.label}</strong><small>{stageStateLabel(state, selected)}</small></span>
          </button>
        </li>;
      })}
    </ol>

    {selectedStage === "plan" && <PlanSurface projection={projection} />}
    {selectedStage === "research" && <section className="card lifecycle-surface" aria-labelledby="ai-research-heading">
      <div className="lifecycle-surface-head"><div><span>02 · AI研究</span><h2 id="ai-research-heading">研究路径 · Research Path</h2><p>对照初始计划与实际执行路径，查看本次研究如何完成调整。</p></div><span className="badge green">{projection.tasks.length} Tasks</span></div>
      <ResearchPath projection={projection} onOpenTask={(task) => setSelectedTaskId(task.taskId)} />
    </section>}
    {selectedStage === "review" && <DeferredDetailSurface number="03" title="质量复核" state={stageState(projection, "review")} />}
    {selectedStage === "report" && <DeferredDetailSurface number="04" title="报告生成" state={stageState(projection, "report")} />}
    {selectedStage === "complete" && <CompleteSurface projection={projection} reportBaseUrl={reportBaseUrl} />}

    <TaskDetailDrawer projection={projection} taskId={selectedTaskId} onClose={() => setSelectedTaskId(null)} />
  </section>;
}

function DeferredDetailSurface({ number, title, state }: {
  readonly number: string;
  readonly title: string;
  readonly state: StageState;
}) {
  const completed = state === "done";
  return <section className="card lifecycle-surface deferred-detail-surface" aria-labelledby={`deferred-${number}`}>
    <div className="lifecycle-surface-head">
      <div>
        <span>{number} · {title}</span>
        <h2 id={`deferred-${number}`}>{completed ? `${title}已完成` : `${title}正在进行`}</h2>
        <p>{completed ? "权威 Run 投影确认此业务阶段已经完成。" : "权威 Run 投影显示此业务阶段正在进行。"}</p>
      </div>
      <span className={`badge ${completed ? "green" : "blue"}`}>{completed ? "已完成" : "进行中"}</span>
    </div>
    <div className="runtime-unavailable" role="status">
      <strong>详细内容将在后续产品阶段提供</strong>
      <span>当前仅呈现生命周期事实，不推测或提前展示尚未接入的明细。</span>
    </div>
  </section>;
}

function PlanSurface({ projection }: { readonly projection: RunProjection }) {
  return <section className="card lifecycle-surface" aria-labelledby="research-plan-heading">
    <div className="lifecycle-surface-head"><div><span>01 · 研究计划</span><h2 id="research-plan-heading">已确认的 AI 研究计划</h2><p>{projection.goal.goalText}</p></div><span className="badge blue">Graph v{projection.plannedGraph.version}</span></div>
    <div className="plan-workstreams run-plan-workstreams">
      {projection.plannedGraph.tasks.map((task, index) => <div className="plan-workstream" key={task.taskId}><span>{String(index + 1).padStart(2, "0")}</span><strong>{researchPlanLabel(task.taskType)}</strong></div>)}
    </div>
    <details className="technical-details"><summary>计划技术详情</summary><dl><dt>Graph ID</dt><dd>{projection.plannedGraph.graphId}</dd><dt>Goal ID</dt><dd>{projection.goal.goalId}</dd><dt>Scheme ID</dt><dd>{projection.confirmedScheme.schemeId}</dd></dl></details>
  </section>;
}

function CompleteSurface({ projection, reportBaseUrl }: {
  readonly projection: RunProjection;
  readonly reportBaseUrl: string;
}) {
  const artifactId = projection.artifacts.availability.status === "AVAILABLE"
    && projection.artifacts.representationIds.length === 1
    ? projection.artifacts.representationIds[0]
    : null;
  const reportUrl = artifactId === null ? null : `${reportBaseUrl}/api/research-runs/${encodeURIComponent(projection.run.runId)}/artifacts/${encodeURIComponent(artifactId)}/content`;
  return <section className="card lifecycle-surface completion-surface" aria-labelledby="research-complete-heading">
    <div className="completion-mark" aria-hidden="true">✓</div>
    <div><span>05 · 完成</span><h2 id="research-complete-heading">Research Run 已完成</h2><p>初始 Graph v{projection.plannedGraph.version} 经批准的研究路径调整后，形成 Actual Graph v{projection.actualGraph?.version ?? "—"}。</p>{reportUrl !== null && <a className="report-link" data-testid="open-research-report" data-report-artifact-id={artifactId ?? ""} href={reportUrl} target="_blank" rel="noreferrer">查看研究结果</a>}</div>
  </section>;
}
