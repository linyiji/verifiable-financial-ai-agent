import { useEffect, useState } from "react";
import type { AvailabilityStatus, Phase4ResearchObjectDetail, RunCollectionItem } from "../types/domain";
import { PHASE4_RUN_STATUS_META } from "../state/status";
import "../styles/workspace-pages.css";

export type ObjectTab = "overview" | "history";

const OBJECT_TABS: readonly ObjectTab[] = ["overview", "history"];
const TAB_LABELS: Readonly<Record<ObjectTab, string>> = {
  overview: "Overview",
  history: "Research Runs"
};

export interface ResearchObjectDetailPageProps {
  readonly detail: Phase4ResearchObjectDetail;
  readonly runs?: readonly RunCollectionItem[] | null;
  readonly runsLoading?: boolean;
  readonly runsStale?: boolean;
  readonly initialTab?: ObjectTab;
  readonly onTabChange?: (tab: ObjectTab) => void;
  readonly onBack?: () => void;
  readonly onBeginResearch: (objectId: string) => void;
  readonly onOpenRun: (runId: string, objectId: string) => void;
}

export function ResearchObjectDetailPage({
  detail,
  runs = null,
  runsLoading = false,
  runsStale = false,
  initialTab = "overview",
  onTabChange,
  onBack,
  onBeginResearch,
  onOpenRun
}: ResearchObjectDetailPageProps) {
  const [tab, setTab] = useState<ObjectTab>(initialTab);
  const { object } = detail;

  useEffect(() => setTab(initialTab), [initialTab]);

  const selectTab = (next: ObjectTab) => {
    setTab(next);
    onTabChange?.(next);
  };

  return <section className="workspace-page" aria-labelledby="object-detail-title">
    <button type="button" className="breadcrumb breadcrumb-button" onClick={onBack}>研究对象 › {object.companyName}</button>
    <div className="card object-head">
      <div className="object-header-row">
        <div className="object-title-cluster">
          <div className="company-logo" aria-hidden="true">{object.symbol}</div>
          <div>
            <h1 id="object-detail-title">{object.companyName}</h1>
            <div className="small">{object.symbol} · {object.exchange} · {object.sector ?? "Sector unavailable"} · {object.currency}</div>
            <div className="micro mono-value object-id-line">{object.objectId}</div>
          </div>
        </div>
        <div className="actions">
          <button type="button" className="btn primary" onClick={() => onBeginResearch(object.objectId)}>开始新研究</button>
        </div>
      </div>
      <div className="object-tabs" role="tablist" aria-label="研究对象详情">
        {OBJECT_TABS.map((item, index) => <button
          type="button"
          role="tab"
          id={`object-tab-${item}`}
          aria-controls={`object-panel-${item}`}
          aria-selected={tab === item}
          tabIndex={tab === item ? 0 : -1}
          className={`object-tab ${tab === item ? "active" : ""}`}
          key={item}
          onClick={() => selectTab(item)}
          onKeyDown={(event) => {
            if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
            event.preventDefault();
            const offset = event.key === "ArrowRight" ? 1 : -1;
            const next = OBJECT_TABS[(index + offset + OBJECT_TABS.length) % OBJECT_TABS.length];
            selectTab(next);
            window.requestAnimationFrame(() => document.getElementById(`object-tab-${next}`)?.focus());
          }}
        >{TAB_LABELS[item]}</button>)}
      </div>
    </div>

    {tab === "overview" && <OverviewPanel detail={detail} onOpenRun={onOpenRun} />}
    {tab === "history" && <HistoryPanel detail={detail} runs={runs} loading={runsLoading} stale={runsStale} onOpenRun={onOpenRun} />}
  </section>;
}

function OverviewPanel({ detail, onOpenRun }: {
  readonly detail: Phase4ResearchObjectDetail;
  readonly onOpenRun: (runId: string, objectId: string) => void;
}) {
  const { object, releasedResultAvailability: availability } = detail;
  return <div className="object-pane active" id="object-panel-overview" role="tabpanel" aria-labelledby="object-tab-overview">
    <div className="grid4 object-state-grid">
      <State label="Research Runs" value={String(detail.runCount)} />
      <State label="Released Result" value={availabilityLabel(availability.status)} tone={availabilityColor(availability.status)} />
      <State label="Identity Version" value={`v${object.identityVersion}`} />
      <State label="Object Type" value={object.objectType} />
    </div>

    <div className="grid2 object-overview-grid">
      <div className="card pad">
        <div className="section-heading"><div><h2 className="panel-title">Object Identity</h2><div className="small">由后端归一化并按精确 ID 读取。</div></div></div>
        <dl className="detail-grid object-detail-grid">
          <Identity label="Object ID" value={object.objectId} mono />
          <Identity label="Company" value={object.companyName} />
          <Identity label="Symbol" value={object.symbol} />
          <Identity label="Exchange" value={object.exchange} />
          <Identity label="Sector" value={object.sector ?? "Unavailable"} />
          <Identity label="Currency" value={object.currency} />
        </dl>
      </div>

      <div className="card pad">
        <div className="section-heading">
          <div><h2 className="panel-title">Latest Released Run</h2><div className="small">仅显示经过发布闭包校验的对象级引用。</div></div>
          <span className={`badge ${availabilityColor(availability.status)}`}>{availability.status}</span>
        </div>
        {detail.latestReleasedRunId
          ? <div className="released-run-block">
              <code>{detail.latestReleasedRunId}</code>
              <button type="button" className="btn ghost sm" onClick={() => onOpenRun(detail.latestReleasedRunId!, object.objectId)}>打开已发布 Run →</button>
            </div>
          : <div className="runtime-unavailable" role="status"><strong>尚无已发布 Run</strong><span>{availability.reasonCode ?? "NO_RELEASED_RUN"}</span></div>}
      </div>
    </div>

    <div className="card pad object-activity-card">
      <div className="section-heading"><div><h2 className="panel-title">Last Activity</h2><div className="small">对象拥有的最后一条安全运行活动。</div></div></div>
      {detail.lastActivity
        ? <dl className="detail-grid object-detail-grid">
            <Identity label="Event ID" value={detail.lastActivity.eventId} mono />
            <Identity label="Type" value={detail.lastActivity.type} />
            <Identity label="Message" value={detail.lastActivity.messageCode} />
            <Identity label="Sequence" value={String(detail.lastActivity.sequence)} />
            <Identity label="Task ID" value={detail.lastActivity.taskId ?? "Run-level"} mono={detail.lastActivity.taskId !== null} />
            <Identity label="Timestamp" value={formatTimestamp(detail.lastActivity.timestamp)} />
          </dl>
        : <div className="empty-state" role="status">尚无该对象的 Run 活动。</div>}
    </div>
  </div>;
}

function HistoryPanel({ detail, runs, loading, stale, onOpenRun }: {
  readonly detail: Phase4ResearchObjectDetail;
  readonly runs: readonly RunCollectionItem[] | null;
  readonly loading: boolean;
  readonly stale: boolean;
  readonly onOpenRun: (runId: string, objectId: string) => void;
}) {
  return <div className="object-pane active" id="object-panel-history" role="tabpanel" aria-labelledby="object-tab-history">
    {stale && <div className="stale-banner" role="status">对象历史正在刷新；当前显示的是上一次有效投影。</div>}
    <div className="card">
      {loading && runs === null
        ? <div className="loading-row" role="status"><div className="spinner" aria-hidden="true" /><span>正在载入对象级 Run 历史…</span></div>
        : runs === null
          ? <div className="empty-state" role="status">Run 历史尚未载入。</div>
          : runs.length === 0
            ? <div className="empty-state" role="status">该对象尚无 Research Run。</div>
            : runs.map((run) => <ObjectRunRow key={run.runId} run={run} expectedObjectId={detail.object.objectId} onOpenRun={onOpenRun} />)}
    </div>
  </div>;
}

function ObjectRunRow({ run, expectedObjectId, onOpenRun }: {
  readonly run: RunCollectionItem;
  readonly expectedObjectId: string;
  readonly onOpenRun: (runId: string, objectId: string) => void;
}) {
  if (run.object.objectId !== expectedObjectId) {
    return <div className="history-row history-row-invalid" role="alert">身份不匹配的 Run 行已拒绝显示。</div>;
  }
  const meta = PHASE4_RUN_STATUS_META[run.status];
  return <button type="button" className="history-row" onClick={() => onOpenRun(run.runId, run.object.objectId)}>
    <span>
      <strong><code>{run.runId}</code> · {run.object.companyName}</strong>
      <span className="small option-sub">{run.stage} · As of {run.asOf} · projection r{run.projectionRevision}/seq {run.projectionSequence}</span>
    </span>
    <span className="history-meta">
      <span className={`badge ${meta.color}`}>{meta.label}</span>
      <span className="btn ghost sm">{run.status === "COMPLETED" ? "查看结果" : "打开任务"} →</span>
    </span>
  </button>;
}

function State({ label, value, tone }: { readonly label: string; readonly value: string; readonly tone?: string }) {
  return <div className="card state-card"><div className="state-label">{label}</div><div className={`state-value ${tone ? `state-${tone}` : ""}`}>{value}</div></div>;
}

function Identity({ label, value, mono = false }: { readonly label: string; readonly value: string; readonly mono?: boolean }) {
  return <div><dt>{label}</dt><dd className={mono ? "mono-value" : undefined}>{value}</dd></div>;
}

function availabilityColor(status: AvailabilityStatus): "green" | "amber" | "red" | "blue" {
  if (status === "AVAILABLE") return "green";
  if (status === "FAILED" || status === "UNAVAILABLE") return "red";
  if (status === "PENDING") return "blue";
  return "amber";
}

function availabilityLabel(status: AvailabilityStatus): string {
  const labels: Readonly<Record<AvailabilityStatus, string>> = {
    PENDING: "Preparing",
    AVAILABLE: "Available",
    NOT_GENERATED: "Not generated",
    NOT_RELEASED: "Not released",
    UNAVAILABLE: "Unavailable",
    FAILED: "Failed"
  };
  return labels[status];
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN");
}
