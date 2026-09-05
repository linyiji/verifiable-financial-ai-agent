import { useEffect, useMemo, useState } from "react";
import type { ObjectComparisonItem, ResearchObjectDetail, ResearchRun } from "../types/domain";
import { RUN_STATUS_META } from "../state/status";
import "../styles/workspace-pages.css";

type ObjectTab = "overview" | "financials" | "history" | "view";
const OBJECT_TABS: ObjectTab[] = ["overview", "financials", "history", "view"];
const TAB_LABELS = ["Overview", "Financials", "Research History", "Research View"];
const categoryLabels: Record<ObjectComparisonItem["category"], string> = { METRIC_CHANGED: "Metric changed", JUDGMENT_CHANGED: "Judgment changed", CLAIM_REVISED: "Claim revised", CLAIM_UNCHANGED: "Claim unchanged", NEW_RISK: "New risk", NEW_CATALYST: "New catalyst" };

export function ResearchObjectDetailPage({ detail, initialTab = "overview", onTabChange, onBack, onStartRun, onStartIncremental, onOpenRun, onOpenClaim }: {
  detail: ResearchObjectDetail;
  initialTab?: ObjectTab;
  onTabChange?: (tab: ObjectTab) => void;
  onBack?: () => void;
  onStartRun: () => void;
  onStartIncremental: () => void;
  onOpenRun: (run: ResearchRun) => void;
  onOpenClaim?: (runId: string, claimId: string) => void;
}) {
  const [tab, setTab] = useState<ObjectTab>(initialTab);
  const { object } = detail;
  useEffect(() => setTab(initialTab), [initialTab]);
  const latest = detail.researchViews.find((view) => view.runId === detail.latestReleasedRunId);
  const latestRun = detail.runs.find((run) => run.id === detail.latestReleasedRunId);
  const periods = useMemo(() => Array.from(new Set(detail.financials.flatMap((metric) => metric.values.map((value) => value.period)))), [detail.financials]);
  const selectTab = (next: ObjectTab) => { setTab(next); onTabChange?.(next); };

  return <section className="workspace-page">
    <button className="breadcrumb breadcrumb-button" onClick={onBack}>研究对象 › {object.name}</button>
    <div className="card object-head">
      <div className="object-header-row"><div className="object-title-cluster"><div className="company-logo">{object.symbol}</div><div><h1>{object.name}</h1><div className="small">{object.symbol} · {object.exchange} · {object.industry} · {object.currency}</div></div></div><div className="actions"><span className="incremental-action"><button aria-describedby={!detail.latestReleasedRunId ? "object-incremental-reason" : undefined} className="btn" disabled={!detail.latestReleasedRunId} onClick={onStartIncremental} title={!detail.latestReleasedRunId ? "需要该对象先有一个已发布 Research Run" : undefined}>基于历史研究开始</button>{!detail.latestReleasedRunId && <small className="disabled-reason" id="object-incremental-reason">需先完成一次 Full Research</small>}</span><button className="btn primary" onClick={onStartRun}>开始 Full Research</button></div></div>
      <div className="object-tabs" role="tablist">{OBJECT_TABS.map((item, index) => <button role="tab" id={`object-tab-${item}`} aria-controls={`object-panel-${item}`} aria-selected={tab === item} tabIndex={tab === item ? 0 : -1} className={`object-tab ${tab === item ? "active" : ""}`} key={item} onClick={() => selectTab(item)} onKeyDown={(event) => { if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return; event.preventDefault(); const next = OBJECT_TABS[(index + (event.key === "ArrowRight" ? 1 : -1) + OBJECT_TABS.length) % OBJECT_TABS.length]; selectTab(next); window.requestAnimationFrame(() => document.getElementById(`object-tab-${next}`)?.focus()); }}>{TAB_LABELS[index]}</button>)}</div>
    </div>

    {tab === "overview" && <div className="object-pane active" id="object-panel-overview" role="tabpanel" aria-labelledby="object-tab-overview"><div className="version-lock"><strong>Latest Released Research Snapshot</strong><span>{detail.latestReleasedRunId ?? "NOT_GENERATED"}</span><small>Title、KPIs、Research View 与 Claims 均锁定到同一 released version。</small></div><div className="grid4"><State label="Price" value={object.price} /><State label="Revenue" value={object.revenue} /><State label="Revenue Growth" value={object.revenueGrowth} /><State label="Forward P/E" value={object.forwardPe} /></div><div className="grid2 object-overview-grid"><div className="card pad"><div className="small">Latest Research</div><h3>{latestRun?.title ?? "暂无已发布研究"}</h3><div className="view-state-grid"><ViewStat label="Growth" value={latest?.growth} /><ViewStat label="Valuation" value={latest?.valuation} /><ViewStat label="Risk" value={latest?.risk} /></div>{latestRun && <button className="btn ghost sm" onClick={() => onOpenRun(latestRun)}>查看最新研究 →</button>}</div><div className="card pad"><div className="small">Object State · {latest?.runId ?? "MISSING_PROJECTION"}</div><div className="info-list"><Info label="Growth Quality" value={latest?.growth} color="green" /><Info label="Profitability" value={latest?.profitability} color="green" /><Info label="Valuation" value={latest?.valuation} color="amber" /><Info label="Risk" value={latest?.risk} color="amber" /></div></div></div></div>}

    {tab === "financials" && <div className="object-pane active" id="object-panel-financials" role="tabpanel" aria-labelledby="object-tab-financials"><div className="card pad table-scroll"><div className="stage-titlebar"><div><h3>Financial Statements</h3><div className="small">Actual 与 Estimate 分开；这里只展示 DataSource projection，不在前端重算。</div></div></div>{detail.financials.length ? <table className="report-table"><thead><tr><th scope="col">Metric</th>{periods.map((period) => <th scope="col" key={period}>{period}</th>)}</tr></thead><tbody>{detail.financials.map((metric) => <tr key={metric.key}><th scope="row">{metric.label}</th>{periods.map((period) => { const value = metric.values.find((item) => item.period === period); return <td key={period} className={value?.estimate ? "estimate-cell" : ""}>{value?.value ?? "—"}{value?.estimate && <sup>E</sup>}</td>; })}</tr>)}</tbody></table> : <div className="empty-state" role="status">Financial projection unavailable for this object.</div>}</div></div>}

    {tab === "history" && <div className="object-pane active" id="object-panel-history" role="tabpanel" aria-labelledby="object-tab-history"><div className="card">{detail.runs.length ? detail.runs.map((run) => { const meta = RUN_STATUS_META[run.status]; return <button className="history-row" key={run.id} onClick={() => onOpenRun(run)}><span><strong>{run.id} · {run.title}</strong><span className="small option-sub">{run.goal}</span></span><span className="history-meta"><span className={`badge ${meta.color}`}>{meta.label}</span><span className="btn ghost sm">{run.status === "COMPLETED" ? "查看结果" : "打开任务"} →</span></span></button>; }) : <div className="empty-state" role="status">No Research Runs yet.</div>}</div></div>}

    {tab === "view" && <div className="object-pane active" id="object-panel-view" role="tabpanel" aria-labelledby="object-tab-view"><div className="card pad"><div className="stage-titlebar"><div><h3>Latest Research View</h3><div className="small">新 Run 形成新版本，不覆盖历史研究判断。</div></div><span className="badge green">{latest?.runId ?? "MISSING_PROJECTION"}</span></div><div className="grid4"><State label="Growth" value={latest?.growth} /><State label="Profitability" value={latest?.profitability} /><State label="Valuation" value={latest?.valuation} /><State label="Risk" value={latest?.risk} /></div><div className="research-view-history"><div className="micro">Research View History</div>{["risk", "valuation", "growth"].map((key) => <div className="trendline" key={key}><strong>{key[0].toUpperCase() + key.slice(1)}</strong>{detail.researchViews.map((view) => <span className="trendvalue" key={view.runId}>{view[key as "risk" | "valuation" | "growth"]}<small>{view.asOf}</small></span>)}</div>)}</div><Comparison detail={detail} onOpenClaim={onOpenClaim} /></div></div>}
  </section>;
}

function Comparison({ detail, onOpenClaim }: { detail: ResearchObjectDetail; onOpenClaim?: (runId: string, claimId: string) => void }) {
  const comparison = detail.comparison;
  return <div className="card compare-card"><div className="stage-titlebar"><div><h3>Compared with Previous Research</h3><div className="small">baseRunId 与 compareRunId 已冻结；Claim 使用 sourceRunId，不回退 latest。</div></div><span className="badge blue">{comparison.previousRunId || "N/A"} → {comparison.currentRunId || "N/A"}</span></div>{comparison.items.length ? <div className="comparison-list">{comparison.items.map((item) => {
    const body = <><span className={`change-kind ${item.category.toLowerCase()}`}>{categoryLabels[item.category]}</span><span><strong>{item.label}</strong><span className="small option-sub">{item.explanation} · source {item.sourceRunId}</span></span><span className="comparison-values"><del>{item.previousValue ?? "New"}</del><strong>{item.currentValue}</strong></span>{item.claimId ? <span className="claim-arrow">查看 Claim →</span> : <span className="small">No Claim link</span>}</>;
    return item.claimId ? <button className="comparison-row" key={item.id} onClick={() => onOpenClaim?.(item.sourceRunId, item.claimId!)}>{body}</button> : <div className="comparison-row comparison-row-static" key={item.id}>{body}</div>;
  })}</div> : <div className="empty-state" role="status">No comparison is available until two released versions exist.</div>}</div>;
}
function State({ label, value }: { label: string; value?: string }) { return <div className="card state-card"><div className="state-label">{label}</div><div className="state-value">{value ?? "—"}</div></div>; }
function ViewStat({ label, value }: { label: string; value?: string }) { return <div><div className="micro">{label}</div><strong>{value ?? "—"}</strong></div>; }
function Info({ label, value, color }: { label: string; value?: string; color: string }) { return <div className="info-row"><strong>{label}</strong><span className={`badge ${color}`}>{value ?? "—"}</span></div>; }
