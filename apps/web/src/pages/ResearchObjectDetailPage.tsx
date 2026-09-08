import type { Phase4FrontendDataSource } from "../data/FrontendDataSource";
import type { ResearchRunDetailV1 } from "../types/domain";
import { useEffect, useState } from "react";
import type { AvailabilityStatus, Phase4ResearchObjectDetail, RunCollectionItem, RunHistoryItem } from "../types/domain";
import { PHASE4_RUN_STATUS_META } from "../state/status";
import { missingObjectActivity, objectReleaseSummary } from "./objectSummaryCopy";
import {ResearchMemory} from "../components/ResearchMemory";
import type {ResearchMemorySnapshot, MemoryHistoryRef} from "../types/researchMemory";
import "../styles/workspace-pages.css";

export type ObjectTab = "overview" | "current" | "memories" | "compare" | "history";

const OBJECT_TABS: readonly ObjectTab[] = ["overview", "current", "memories", "compare", "history"];
const TAB_LABELS: Readonly<Record<ObjectTab, string>> = {
  overview: "概述",
  current: "Current Research View",
  memories: "Memories",
  compare: "对比",
  history: "研究记录"
};

export interface ResearchObjectDetailPageProps {
  readonly source?: Phase4FrontendDataSource;
  readonly memory?: ResearchMemorySnapshot | null;
  readonly memoryUnavailable?: boolean;
  readonly onOpenMemorySource?: (runId: string, anchor: string | null) => void;
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
  source,
  memory = null,
  memoryUnavailable = false,
  onOpenMemorySource,
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
  const readTab = (): ObjectTab => {
    if (typeof window === "undefined") return initialTab;
    const value = new URLSearchParams(window.location.search).get("tab") as ObjectTab;
    return OBJECT_TABS.includes(value) ? value : initialTab;
  };
  const [tab, setTab] = useState<ObjectTab>(readTab);
  const { object } = detail;

  useEffect(() => {
    const sync = () => setTab(readTab());
    sync(); window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [initialTab, object.objectId]);
  const safeMemory = memory?.research_object_id === object.objectId ? memory : null;

  const selectTab = (next: ObjectTab) => {
    setTab(next);
    const url = new URL(window.location.href); url.searchParams.set("tab", next);
    window.history.pushState(null, "", url);
    onTabChange?.(next);
  };

  return <section className="workspace-page" aria-labelledby="object-detail-title" data-testid="research-object-detail" data-object-id={object.objectId}>
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
          <span className="badge green">{safeMemory?.current_view ? `Current View v${safeMemory.current_view.research_view_version}` : safeMemory ? "尚未形成 Research View" : memoryUnavailable ? "Research View 暂不可用" : "Research View 读取中"}</span>
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

    {tab === "overview" && <>
      {safeMemory?.current_view && <section className="card pad"><h2>当前研究摘要</h2><p>{safeMemory.current_view.summary ?? "尚未形成已验证摘要。"}</p><span className="badge green">RELEASED · View v{safeMemory.current_view.research_view_version}</span></section>}
      <OverviewPanel detail={detail} onOpenRun={onOpenRun} />
    </>}
    {(["current", "memories", "compare"] as string[]).includes(tab) && <div id={`object-panel-${tab}`} role="tabpanel" aria-labelledby={`object-tab-${tab}`} className="object-pane active">{onOpenMemorySource && <ResearchMemory pane={tab as "current" | "memories" | "compare"} memory={safeMemory} unavailable={memoryUnavailable} onOpenSource={onOpenMemorySource} />}</div>}
    {tab === "history" && <HistoryPanel source={source} onOpenResults={onOpenMemorySource} memoryHistory={safeMemory?.historical_released_runs ?? []} detail={detail} runs={runs} loading={runsLoading} stale={runsStale} unavailable={runsUnavailable} onOpenRun={onOpenRun} />}
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
      <State label="已发布结果" value={objectReleaseSummary(detail)} tone={availabilityColor(availability.status)} />
      <State label="公司代码" value={object.symbol} />
      <State label="计价货币" value={object.currency} />
    </div>

    <div className="object-overview-grid">

      <div className="card pad">
        <div className="section-heading">
          <div><h2 className="panel-title">当前已发布研究</h2><div className="small">来自明确绑定的研究资产，不按时间猜测。</div></div>
          <span className={`badge ${availabilityColor(availability.status)}`}>{availability.status}</span>
        </div>
        {detail.latestReleasedRunId
          ? <div className="released-run-block">
              <code>{detail.latestReleasedRunId}</code>
              <button type="button" className="btn ghost sm" onClick={() => onOpenRun(detail.latestReleasedRunId!, object.objectId)}>打开已发布 Run →</button>
            </div>
          : <div className="runtime-unavailable" role="status"><strong>{objectReleaseSummary(detail)}</strong><span>{availability.reasonCode === "NO_RELEASED_RUN" ? "完成研究后将在这里显示。" : "未确定最新已发布 Run；不会猜测或替换其他 Run。"}</span></div>}
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
        : <div className="empty-state" role="status">{missingObjectActivity(detail)}</div>}
    </div>
  </div>;
}

function HistoryPanel({ source, detail, runs, loading, stale, unavailable, onOpenRun, memoryHistory, onOpenResults }: {
  readonly onOpenResults?: (runId: string, anchor: string | null) => void;
  readonly source?: Phase4FrontendDataSource;
  readonly memoryHistory: readonly MemoryHistoryRef[];
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
            : [...runs].sort((a,b) => {
                const priority = (item: RunHistoryItem) => {
                  const id = item.availability==="AVAILABLE" ? item.run.runId : item.runId;
                  return id===detail.latestReleasedRunId ? 0 : memoryHistory.some(h=>h.source_run_id===id && h.research_view_version!==null) ? 1 : 2;
                }; return priority(a)-priority(b);
              }).map((item) => item.availability === "AVAILABLE"
              ? <ObjectRunRow source={source} current={item.run.runId===detail.latestReleasedRunId} onOpenResults={onOpenResults} memoryHistory={memoryHistory.find(h=>h.source_run_id===item.run.runId&&h.research_object_id===detail.object.objectId)} key={item.run.runId} run={item.run} expectedObjectId={detail.object.objectId} onOpenRun={onOpenRun} />
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

function ObjectRunRow({ source, current, run, expectedObjectId, onOpenRun, memoryHistory, onOpenResults }: {
  readonly onOpenResults?: (runId: string, anchor: string | null) => void;
  readonly source?: Phase4FrontendDataSource;
  readonly current: boolean;
  readonly memoryHistory?: MemoryHistoryRef;
  readonly run: RunCollectionItem;
  readonly expectedObjectId: string;
  readonly onOpenRun: (runId: string, objectId: string) => void;
}) {
  const [lineage, setLineage] = useState<ResearchRunDetailV1 | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  const [recoveries, setRecoveries] = useState<number | null>(null);
  useEffect(() => {
    let active = true; const controller = new AbortController();
    setLineage(null); setRecoveries(null); setFailed(false);
    if (!source || run.object.objectId !== expectedObjectId) { setFailed(true); return; }
    source?.getResearchRun(run.runId, expectedObjectId, {signal:controller.signal}).then(value=>{if(active && value.runId===run.runId && value.researchObjectId===expectedObjectId)setLineage(value);}).catch(()=>{if(active)setFailed(true);});
    if(current) source?.getRecoveryEvidence?.(run.runId, expectedObjectId, {signal:controller.signal}).then(rows=>{if(active)setRecoveries(new Set(rows.filter(r=>r.kind==="DECISION" && r.outcome==="ALLOW").map(r=>r.taskId)).size);}).catch(()=>{});
    return ()=>{active=false;controller.abort();};
  }, [source, run.runId, expectedObjectId, current, attempt]);
  if (run.object.objectId !== expectedObjectId) {
    return <div className="history-row history-row-invalid" role="alert">身份不匹配的 Run 行已拒绝显示。</div>;
  }
  const meta = PHASE4_RUN_STATUS_META[run.status];
  const hasResults = memoryHistory?.availability === "AVAILABLE" && onOpenResults;
  return <article className="history-row" data-testid="object-history-run" data-run-id={run.runId}>
    <span>
      <strong>{current ? "当前已发布研究" : memoryHistory?.research_view_version ? "已发布历史研究 / 知识基线" : run.backendStatus==="FAILED" ? "研究执行未完成" : "研究执行"} · {run.asOf}</strong>
      <span className="small option-sub">Run ID · <code>{run.runId}</code></span>
      {run.backendStatus==="FAILED" && <span className="small option-sub">失败执行历史 · 未形成 Research Memory 版本</span>}
      {lineage && <details className="run-lineage"><summary>执行关系与身份</summary><p>知识基线：{lineage.baseRunId === undefined ? "历史记录未提供" : lineage.baseRunId ?? "无增量基线"}</p><p>前次执行：{lineage.reexecutionOfRunId === undefined ? "历史记录未提供" : lineage.reexecutionOfRunId ?? "无前次执行"}</p><p>Scheme：{lineage.schemeId}</p><p>状态：{lineage.backendStatus}</p></details>}
      {!lineage && <span className="small option-sub">{failed ? <button className="btn ghost sm" onClick={()=>setAttempt(n=>n+1)}>执行关系暂不可用 · 重新读取</button> : "正在读取执行关系…"}</span>}
      {recoveries !== null && recoveries > 0 && <a className="btn ghost sm" href={`/runs/${encodeURIComponent(run.runId)}/results/execution`}>Adaptive Recovery · {recoveries} 个 Task 的受控恢复 →</a>}
      {memoryHistory && <span className="small option-sub">{memoryHistory.source_released_result_id ?? "Released Result · UNAVAILABLE_INCOMPATIBLE"} · {memoryHistory.research_view_version ? `Research View v${memoryHistory.research_view_version}` : "尚未纳入研究记忆"}</span>}
    </span>
    <span className="history-meta">
      <span className={`badge ${meta.color}`}>{run.backendStatus==="RELEASED" ? "RELEASED · 已发布" : run.backendStatus==="FAILED" ? "FAILED · 未完成" : meta.label}</span>
      <button type="button" className="btn ghost sm" onClick={() => hasResults ? onOpenResults(run.runId,null) : onOpenRun(run.runId, run.object.objectId)}>{hasResults ? "打开原始 Results →" : "打开 Research Run →"}</button>
    </span>
  </article>;
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
