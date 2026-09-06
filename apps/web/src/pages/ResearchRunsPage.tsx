import type { ReactNode } from "react";
import type { RunCollectionItem, RunHistoryItem, RunProjection } from "../types/domain";
import {
  PHASE4_RUN_STATUS_META,
  selectAutoStartState,
  selectConfirmResponseMeta,
  selectRetryState,
  selectVisibleError,
  selectWorkspaceRunIdentity,
  selectWorkspaceShell,
  type Phase4ProductState,
  type Phase4RequestFailure,
  type Phase4RetryState,
  type Phase4WorkspaceRunIdentity,
  type Phase4WorkspaceState
} from "../state/status";
import "../styles/workspace-pages.css";

export interface ResearchRunsPageProps {
  readonly runs: readonly RunHistoryItem[];
  readonly objectCount: number;
  readonly onCreate: () => void;
  readonly onOpen: (runId: string, objectId: string) => void;
  readonly loading?: boolean;
  readonly unavailable?: boolean;
  readonly stale?: boolean;
  readonly nextCursor?: string | null;
  readonly onLoadMore?: (cursor: string) => void;
}

export function ResearchRunsPage({
  runs,
  objectCount,
  onCreate,
  onOpen,
  loading = false,
  unavailable = false,
  stale = false,
  nextCursor = null,
  onLoadMore
}: ResearchRunsPageProps) {
  const active = runs.filter((item) => !["RELEASED", "FAILED", "CANCELLED"].includes(historyStatus(item))).length;
  const completed = runs.filter((item) => historyStatus(item) === "RELEASED").length;
  const unsuccessful = runs.filter((item) => ["FAILED", "CANCELLED"].includes(historyStatus(item))).length;

  return <section className="workspace-page" aria-labelledby="research-runs-title">
    <div className="page-head">
      <div>
        <div className="breadcrumb breadcrumb-context">Research / 研究记录</div>
        <h1 className="page-title" id="research-runs-title">研究记录</h1>
        <div className="page-sub">查看已创建的 Research Run，并按精确 Run ID 打开对应研究工作区。</div>
      </div>
      <button type="button" className="btn primary" onClick={onCreate}>+ 新建研究任务</button>
    </div>

    {stale && <div className="stale-banner" role="status">任务列表正在刷新；当前显示的是上一次有效投影。</div>}
    <div className="run-kpis">
      <Kpi label="进行中" value={active} foot="后端非终态 Run" />
      <Kpi label="已完成" value={completed} foot="已正式发布" />
      <Kpi label="未成功终止" value={unsuccessful} foot="失败或已取消" />
      <Kpi label="研究对象" value={objectCount} foot="当前对象集合" />
    </div>

    {unavailable
      ? null
      : loading && runs.length === 0
      ? <div className="card loading-row" role="status"><div className="spinner" aria-hidden="true" /><span>正在载入 Run 列表…</span></div>
      : runs.length === 0
        ? <div className="card empty-state" role="status">尚无 Research Run。创建研究任务并确认方案后，Run 会在这里出现。</div>
        : <div className="run-list">{runs.map((item) => item.availability === "AVAILABLE"
            ? <RunRow key={item.run.runId} run={item.run} onOpen={onOpen} />
            : <UnavailableRunRow key={item.runId} item={item} />)}</div>}

    {nextCursor && onLoadMore && <div className="collection-footer">
      <button type="button" className="btn" disabled={loading} onClick={() => onLoadMore(nextCursor)}>
        {loading ? "正在载入…" : "载入更多"}
      </button>
    </div>}
  </section>;
}

function RunRow({ run, onOpen }: { readonly run: RunCollectionItem; readonly onOpen: (runId: string, objectId: string) => void }) {
  const meta = PHASE4_RUN_STATUS_META[run.status];
  return <button
    type="button"
    className="card run-card"
    onClick={() => onOpen(run.runId, run.object.objectId)}
    aria-label={`打开 ${run.object.companyName} 的运行 ${run.runId}`}
  >
    <span className="run-card-primary">
      <span className={`badge ${meta.color}`}><span className={`dot ${run.status === "RESEARCHING" ? "pulse" : ""}`} />{meta.label}</span>
      <span className="run-title">{run.object.companyName} · {run.object.symbol}</span>
      <span className="run-purpose">完整公司金融研究</span>
      <span className="run-meta">Run ID · <code>{run.runId}</code></span>
      <span className="run-meta">As-of {run.asOf} · {run.progress.completedTasks}/{run.progress.totalTasks} 个研究任务完成</span>
    </span>
    <span className="optional">
      <span className="stage">研究进度</span>
      <span className="progress" role="progressbar" aria-label={`${run.object.symbol} Run 进度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={run.progress.percent}>
        <i style={{ width: `${run.progress.percent}%` }} />
      </span>
      <span className="stage-sub">{formatPercent(run.progress.percent)}</span>
    </span>
    <span className="optional">
      <span className="stage">{run.graphVersion === null ? "研究路径准备中" : `实际路径 · Graph v${run.graphVersion}`}</span>
      <span className="stage-sub">{formatTimestamp(run.updatedAt)}</span>
    </span>
    <span className="run-card-end">
      <span className={`badge ${availabilityColor(run.resultAvailability.status)}`}>{availabilityLabel(run.resultAvailability.status)}</span>
      <span className={`btn sm ${run.status === "COMPLETED" ? "primary" : ""}`}>打开 Research Run</span>
    </span>
  </button>;
}

function UnavailableRunRow({ item }: {
  readonly item: Extract<RunHistoryItem, { availability: "UNAVAILABLE_INCOMPATIBLE" }>;
}) {
  return <article className="card run-card unavailable-history-row" data-run-id={item.runId}>
    <div className="run-card-primary">
      <span className="badge amber">历史记录不可完整读取</span>
      <span className="run-title">{item.object.companyName} · {item.object.symbol}</span>
      <span className="run-purpose">完整公司金融研究</span>
      <span className="run-meta">Run ID · <code>{item.runId}</code></span>
    </div>
    <div className="unavailable-history-copy"><strong>legacy / incompatible</strong><span>仅保留可验证的历史身份与状态信息。</span></div>
    <div className="optional"><span className="stage">历史状态</span><span className="stage-sub">{historyStatusLabel(item.backendStatus)}</span></div>
    <div className="run-card-end"><button type="button" className="btn sm" disabled>不可打开完整工作区</button></div>
  </article>;
}

function historyStatus(item: RunHistoryItem): RunCollectionItem["backendStatus"] {
  return item.availability === "AVAILABLE" ? item.run.backendStatus : item.backendStatus;
}

function historyStatusLabel(status: RunCollectionItem["backendStatus"]): string {
  if (status === "RELEASED") return "已完成";
  if (status === "FAILED") return "未成功终止";
  if (status === "CANCELLED") return "已取消";
  return "进行中";
}

export interface RunWorkspaceShellProps {
  readonly state: Phase4ProductState;
  readonly onBackToRuns?: () => void;
  readonly onRetry?: (retry: Phase4RetryState) => void;
  readonly children?: ReactNode;
}

/**
 * B-owned shell for the exact admitted Run. C may attach its live Research Path
 * as children without reconstructing admission identity or initial snapshot.
 */
export function RunWorkspaceShell({ state, onBackToRuns, onRetry, children }: RunWorkspaceShellProps) {
  const identity = selectWorkspaceRunIdentity(state);
  const workspace = selectWorkspaceShell(state);
  const autoStart = selectAutoStartState(state);
  const responseMeta = selectConfirmResponseMeta(state);
  const retry = selectRetryState(state);
  const alert = selectVisibleError(state);

  if (!identity) {
    return <section className="workspace-page" aria-labelledby="run-workspace-title">
      <div className="page-head"><div><h1 className="page-title" id="run-workspace-title">Run Workspace</h1></div></div>
      <div className="card empty-state" role="status">Run 身份不可用。未渲染任何运行详情。</div>
    </section>;
  }

  return <section className="workspace-page run-workspace-shell" aria-labelledby="run-workspace-title">
    <button type="button" className="breadcrumb breadcrumb-button" onClick={onBackToRuns}>Research › 任务列表</button>
    <div className="card workspace-identity-card">
      <div className="workspace-title-row">
        <div>
          <div className="micro">RUN WORKSPACE</div>
          <h1 id="run-workspace-title">{identity.runId}</h1>
          <div className="small">确认已接纳同一 Run；研究由后端自动启动。</div>
        </div>
        <span className={`badge ${autoStart === "ADMITTED" ? "green" : autoStart === "FAILED" ? "red" : "blue"}`}>
          {autoStart === "ADMITTED" ? "自动启动已接纳" : autoStart === "FAILED" ? "自动启动失败" : "自动启动处理中"}
        </span>
      </div>
      <dl className="identity-grid">
        <Identity label="Run ID" value={identity.runId} />
        <Identity label="Object ID" value={identity.objectId} />
        <Identity label="Goal ID" value={identity.goalId} />
        <Identity label="Scheme ID" value={identity.schemeId} />
        <Identity label="Admission ID" value={identity.admissionId} />
        <Identity label="Planned Graph ID" value={identity.plannedGraphId} />
      </dl>
      {responseMeta?.idempotencyReplayed === true && <details className="retry-diagnostic">
        <summary>重试诊断</summary>
        <p>确认响应来自同一幂等请求的重放；上方 Run、Object、Goal 与 Scheme 身份均未改变。</p>
      </details>}
    </div>

    {alert && <div className="inline-error workspace-alert" role="alert">
      <span>{alert.kind === "ERROR" ? failureText(alert.error) : "快照响应未通过身份或顺序校验，已被隔离。"}</span>
      {retry?.request === "WORKSPACE" && onRetry && <button type="button" className="btn sm" onClick={() => onRetry(retry)}>重试载入快照</button>}
    </div>}

    <SnapshotPanel identity={identity} workspace={workspace} />

    <div className="card runtime-slot" aria-label="实时研究路径">
      <div className="section-heading"><div><strong>Research Path</strong><div className="small">此区域只接收同一 Run 的实时运行投影。</div></div></div>
      {children ?? <div className="runtime-unavailable" role="status">
        <strong>实时运行详情暂不可用</strong>
        <span>初始 Run 快照与实时连接状态分开呈现；在实时投影接入前不会推测 Task 或进度。</span>
      </div>}
    </div>
  </section>;
}

function SnapshotPanel({ identity, workspace }: { readonly identity: Phase4WorkspaceRunIdentity; readonly workspace: Phase4WorkspaceState }) {
  const { snapshot } = workspace;
  if (snapshot) return <SnapshotSummary snapshot={snapshot} stale={workspace.stale || workspace.request.phase === "LOADING"} />;

  if (workspace.request.phase === "LOADING") {
    return <div className="card snapshot-state loading-row" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <div><strong>正在载入初始 Run 快照…</strong><div className="small">Run <code>{identity.runId}</code></div></div>
    </div>;
  }

  if (workspace.request.phase === "ERROR") {
    return <div className="card snapshot-state runtime-unavailable" role="status">
      <strong>初始 Run 快照不可用</strong>
      <span>已保留接纳身份；当前没有可安全显示的运行详情。</span>
    </div>;
  }

  if (workspace.request.phase === "QUARANTINED") {
    return <div className="card snapshot-state runtime-unavailable" role="status">
      <strong>初始 Run 快照已隔离</strong>
      <span>响应未通过精确身份校验，因此没有进入当前 Run 状态。</span>
    </div>;
  }

  return <div className="card snapshot-state runtime-unavailable" role="status">
    <strong>初始 Run 快照尚未载入</strong>
    <span>Run 已接纳；运行状态、进度与图版本将在权威快照返回后显示。</span>
  </div>;
}

function SnapshotSummary({ snapshot, stale }: { readonly snapshot: RunProjection; readonly stale: boolean }) {
  const meta = PHASE4_RUN_STATUS_META[snapshot.run.status];
  return <div className="card snapshot-summary">
    <div className="section-heading">
      <div><strong>Initial Run Snapshot</strong><div className="small">Generated {formatTimestamp(snapshot.generatedAt)}</div></div>
      <span className={`badge ${stale ? "amber" : meta.color}`}>{stale ? "刷新中 · 上次有效快照" : meta.label}</span>
    </div>
    <div className="snapshot-grid">
      <SnapshotValue label="Stage" value={snapshot.run.stage} />
      <SnapshotValue label="Progress" value={formatPercent(snapshot.lifecycle.progress.percent)} />
      <SnapshotValue label="Graph" value={snapshot.graphVersion === null ? "Unavailable" : `v${snapshot.graphVersion}`} />
      <SnapshotValue label="Projection" value={`r${snapshot.projectionRevision} · seq ${snapshot.projectionSequence}`} />
    </div>
  </div>;
}

function Identity({ label, value }: { readonly label: string; readonly value: string }) {
  return <div><dt>{label}</dt><dd><code>{value}</code></dd></div>;
}

function SnapshotValue({ label, value }: { readonly label: string; readonly value: string }) {
  return <div><span className="micro">{label}</span><strong>{value}</strong></div>;
}

function Kpi({ label, value, foot }: { readonly label: string; readonly value: number; readonly foot: string }) {
  return <div className="card kpi"><div className="kpi-label">{label}</div><div className="kpi-value">{value}</div><div className="kpi-foot">{foot}</div></div>;
}

function availabilityColor(status: RunCollectionItem["resultAvailability"]["status"]): "green" | "amber" | "red" | "blue" {
  if (status === "AVAILABLE") return "green";
  if (status === "FAILED" || status === "UNAVAILABLE") return "red";
  if (status === "PENDING") return "blue";
  return "amber";
}

function availabilityLabel(status: RunCollectionItem["resultAvailability"]["status"]): string {
  return {
    PENDING: "结果准备中",
    AVAILABLE: "结果可查看",
    NOT_GENERATED: "结果未生成",
    NOT_RELEASED: "结果未发布",
    UNAVAILABLE: "结果暂不可用",
    FAILED: "结果生成失败"
  }[status];
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN");
}

function formatPercent(value: number): string {
  return `${Math.round(value * 10) / 10}%`;
}

function failureText(failure: Phase4RequestFailure): string {
  return "kind" in failure
    ? `${failure.code}: ${failure.message}`
    : `${failure.error.code}: ${failure.error.message}`;
}
