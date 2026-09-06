import { useEffect, useState } from "react";
import type { AvailabilityStatus, Phase4ResearchObjectDetail, RunCollectionItem, RunHistoryItem } from "../types/domain";
import { PHASE4_RUN_STATUS_META } from "../state/status";
import "../styles/workspace-pages.css";

export type ObjectTab = "overview" | "history";

const OBJECT_TABS: readonly ObjectTab[] = ["overview", "history"];
const TAB_LABELS: Readonly<Record<ObjectTab, string>> = {
  overview: "对象概览",
  history: "研究记录"
};

export interface ResearchObjectDetailPageProps {
  readonly detail: Phase4ResearchObjectDetail;
  readonly runs?: readonly RunHistoryItem[] | null;
  readonly runsLoading?: boolean;
  readonly runsStale?: boolean;
  readonly runsUnavailable?: boolean;
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
  runsUnavailable = false,
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
            <div className="small">{object.symbol} · {object.exchange} · {object.sector ?? "行业信息暂不可用"} · {object.currency}</div>
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
    {tab === "history" && <HistoryPanel detail={detail} runs={runs} loading={runsLoading} stale={runsStale} unavailable={runsUnavailable} onOpenRun={onOpenRun} />}
  </section>;
}

function OverviewPanel({ detail, onOpenRun }: {
  readonly detail: Phase4ResearchObjectDetail;
  readonly onOpenRun: (runId: string, objectId: string) => void;
}) {
  const { object, releasedResultAvailability: availability } = detail;
  return <div className="object-pane active" id="object-panel-overview" role="tabpanel" aria-labelledby="object-tab-overview">
    <div className="grid4 object-state-grid">
      <State label="研究次数" value={String(detail.runCount)} />
      <State label="已发布结果" value={availabilityLabel(availability.status)} tone={availabilityColor(availability.status)} />
      <State label="公司代码" value={object.symbol} />
      <State label="计价货币" value={object.currency} />
    </div>

    <div className="grid2 object-overview-grid">
      <div className="card pad">
        <div className="section-heading"><div><h2 className="panel-title">Research Object</h2><div className="small">公司研究对象与市场身份。</div></div></div>
        <dl className="detail-grid object-detail-grid">
          <Identity label="Object ID" value={object.objectId} mono />
          <Identity label="公司" value={object.companyName} />
          <Identity label="股票代码" value={object.symbol} />
          <Identity label="交易所" value={object.exchange} />
          <Identity label="行业" value={object.sector ?? "暂不可用"} />
          <Identity label="货币" value={object.currency} />
        </dl>
      </div>

      <div className="card pad">
        <div className="section-heading">
          <div><h2 className="panel-title">最近完成的研究</h2><div className="small">仅显示已正式完成的 Research Run。</div></div>
          <span className={`badge ${availabilityColor(availability.status)}`}>{availability.status}</span>
        </div>
        {detail.latestReleasedRunId
          ? <div className="released-run-block">
              <code>{detail.latestReleasedRunId}</code>
              <button type="button" className="btn ghost sm" onClick={() => onOpenRun(detail.latestReleasedRunId!, object.objectId)}>打开已发布 Run →</button>
            </div>
          : <div className="runtime-unavailable" role="status"><strong>尚无已发布 Research Run</strong><span>完成研究后将在这里显示。</span></div>}
      </div>
    </div>

    <div className="card pad object-activity-card">
      <div className="section-heading"><div><h2 className="panel-title">最近活动</h2><div className="small">该 Research Object 最近一次安全研究活动。</div></div></div>
      {detail.lastActivity
        ? <dl className="detail-grid object-detail-grid">
            <Identity label="活动" value="Research Run 状态已更新" />
            <Identity label="时间" value={formatTimestamp(detail.lastActivity.timestamp)} />
            <Identity label="层级" value={detail.lastActivity.taskId === null ? "Research Run" : "Research Task"} />
          </dl>
        : <div className="empty-state" role="status">尚无该对象的 Run 活动。</div>}
    </div>
  </div>;
}

function HistoryPanel({ detail, runs, loading, stale, unavailable, onOpenRun }: {
  readonly detail: Phase4ResearchObjectDetail;
  readonly runs: readonly RunHistoryItem[] | null;
  readonly loading: boolean;
  readonly stale: boolean;
  readonly unavailable: boolean;
  readonly onOpenRun: (runId: string, objectId: string) => void;
}) {
  return <div className="object-pane active" id="object-panel-history" role="tabpanel" aria-labelledby="object-tab-history">
    {stale && <div className="stale-banner" role="status">对象历史正在刷新；当前显示的是上一次有效投影。</div>}
    <div className="card">
      {unavailable
        ? <div className="collection-unavailable embedded" role="status"><strong>部分历史研究暂不可用</strong><span>当前 Research Object 不受影响，可继续发起新的研究。</span></div>
        : loading && runs === null
        ? <div className="loading-row" role="status"><div className="spinner" aria-hidden="true" /><span>正在载入对象级 Run 历史…</span></div>
        : runs === null
          ? <div className="empty-state" role="status">Run 历史尚未载入。</div>
          : runs.length === 0
            ? <div className="empty-state" role="status">该对象尚无 Research Run。</div>
            : runs.map((item) => item.availability === "AVAILABLE"
              ? <ObjectRunRow key={item.run.runId} run={item.run} expectedObjectId={detail.object.objectId} onOpenRun={onOpenRun} />
              : <UnavailableObjectRunRow key={item.runId} item={item} expectedObjectId={detail.object.objectId} />)}
    </div>
  </div>;
}

function UnavailableObjectRunRow({ item, expectedObjectId }: {
  readonly item: Extract<RunHistoryItem, { availability: "UNAVAILABLE_INCOMPATIBLE" }>;
  readonly expectedObjectId: string;
}) {
  if (item.object.objectId !== expectedObjectId) {
    return <div className="history-row history-row-invalid" role="alert">身份不匹配的 Run 行已拒绝显示。</div>;
  }
  return <div className="history-row unavailable-history-row" data-run-id={item.runId}>
    <span>
      <strong>{item.object.companyName}</strong>
      <span className="small option-sub">Run ID · <code>{item.runId}</code></span>
      <span className="small option-sub">legacy / incompatible · 历史记录不可完整读取</span>
    </span>
    <span className="history-meta">
      <span className="badge amber">{historyStatusLabel(item.backendStatus)}</span>
      <button type="button" className="btn ghost sm" disabled>不可打开完整工作区</button>
    </span>
  </div>;
}

function historyStatusLabel(status: RunCollectionItem["backendStatus"]): string {
  if (status === "RELEASED") return "已完成";
  if (status === "FAILED") return "未成功终止";
  if (status === "CANCELLED") return "已取消";
  return "进行中";
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
      <strong>{run.object.companyName} · {run.asOf}</strong>
      <span className="small option-sub">Run ID · <code>{run.runId}</code></span>
    </span>
    <span className="history-meta">
      <span className={`badge ${meta.color}`}>{meta.label}</span>
      <span className="btn ghost sm">打开 Research Run →</span>
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
    PENDING: "准备中",
    AVAILABLE: "可查看",
    NOT_GENERATED: "尚未生成",
    NOT_RELEASED: "尚未发布",
    UNAVAILABLE: "暂不可用",
    FAILED: "生成失败"
  };
  return labels[status];
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN");
}
