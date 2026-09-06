import type { AvailabilityStatus, Phase4ResearchObjectDetail } from "../types/domain";
import "../styles/workspace-pages.css";

export interface ResearchObjectsPageProps {
  readonly objects: readonly Phase4ResearchObjectDetail[];
  readonly onOpen: (objectId: string) => void;
  readonly onCreate: () => void;
  readonly loading?: boolean;
  readonly stale?: boolean;
  readonly nextCursor?: string | null;
  readonly onLoadMore?: (cursor: string) => void;
}

export function ResearchObjectsPage({
  objects,
  onOpen,
  onCreate,
  loading = false,
  stale = false,
  nextCursor = null,
  onLoadMore
}: ResearchObjectsPageProps) {
  return <section className="workspace-page" aria-labelledby="research-objects-title">
    <div className="page-head">
      <div>
        <div className="breadcrumb">Research › 研究对象</div>
        <h1 className="page-title" id="research-objects-title">Research Object</h1>
        <div className="page-sub">管理公司研究对象，查看历史研究，并从同一公司身份发起新的 Research Run。</div>
      </div>
      <button type="button" className="btn primary" onClick={onCreate}>+ 创建研究对象</button>
    </div>

    {stale && <div className="stale-banner" role="status">研究对象列表正在刷新；当前显示的是上一次有效投影。</div>}
    {loading && objects.length === 0
      ? <div className="card loading-row" role="status"><div className="spinner" aria-hidden="true" /><span>正在载入研究对象…</span></div>
      : objects.length === 0
        ? <div className="card empty-state" role="status">尚无 Research Object。创建对象后即可定义研究目标。</div>
        : <div className="object-list">{objects.map((detail) => <ObjectCard key={detail.object.objectId} detail={detail} onOpen={onOpen} />)}</div>}

    {nextCursor && onLoadMore && <div className="collection-footer">
      <button type="button" className="btn" disabled={loading} onClick={() => onLoadMore(nextCursor)}>
        {loading ? "正在载入…" : "载入更多"}
      </button>
    </div>}
  </section>;
}

function ObjectCard({ detail, onOpen }: { readonly detail: Phase4ResearchObjectDetail; readonly onOpen: (objectId: string) => void }) {
  const { object } = detail;
  const availability = detail.releasedResultAvailability;
  return <button
    type="button"
    className="card object-card"
    onClick={() => onOpen(object.objectId)}
    aria-label={`打开研究对象 ${object.companyName}，${object.objectId}`}
  >
    <span className="object-card-head">
      <span>
        <strong>{object.companyName}</strong>
        <span className="small option-sub">{object.symbol} · {object.exchange} · {object.sector ?? "行业信息暂不可用"}</span>
      </span>
      <span className={`badge ${availabilityColor(availability.status)}`}>{availabilityLabel(availability.status)}</span>
    </span>
    <span className="object-metrics">
      <Metric label="研究次数" value={String(detail.runCount)} />
      <Metric label="最近完成" value={detail.latestReleasedRunId ? "已有发布结果" : "尚未发布"} />
      <Metric label="计价货币" value={object.currency} />
      <Metric label="对象状态" value="可研究" />
    </span>
    {detail.lastActivity
      ? <span className="object-last-activity">
          <span className="micro">最近活动</span>
          <strong>Research Run 状态已更新</strong>
          <span className="small">{formatTimestamp(detail.lastActivity.timestamp)}</span>
        </span>
      : <span className="object-last-activity small">尚无 Run 活动。</span>}
    <span className="object-card-action">打开研究对象 →</span>
  </button>;
}

function Metric({ label, value, mono = false }: { readonly label: string; readonly value: string; readonly mono?: boolean }) {
  return <span><span className="om-label">{label}</span><span className={`om-value ${mono ? "mono-value" : ""}`}>{value}</span></span>;
}

function availabilityColor(status: AvailabilityStatus): "green" | "amber" | "red" | "blue" {
  if (status === "AVAILABLE") return "green";
  if (status === "FAILED" || status === "UNAVAILABLE") return "red";
  if (status === "PENDING") return "blue";
  return "amber";
}

function availabilityLabel(status: AvailabilityStatus): string {
  const labels: Readonly<Record<AvailabilityStatus, string>> = {
    PENDING: "结果准备中",
    AVAILABLE: "已有发布结果",
    NOT_GENERATED: "结果未生成",
    NOT_RELEASED: "尚未发布",
    UNAVAILABLE: "结果不可用",
    FAILED: "结果失败"
  };
  return labels[status];
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN");
}
