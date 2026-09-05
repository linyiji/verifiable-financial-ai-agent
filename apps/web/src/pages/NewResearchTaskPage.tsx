import { useEffect, useMemo, useState } from "react";
import type { CreateResearchObjectInput, PrepareResearchRunInput } from "../data/FrontendDataSource";
import type { ResearchObject, ResearchPlan, ResearchRun } from "../types/domain";
import { OverlaySurface } from "../components/overlays/OverlaySurface";
import "../styles/workspace-pages.css";

type GoalTemplate = PrepareResearchRunInput["template"];
const goalTemplates: Array<{ id: GoalTemplate; name: string; description: string; goal: string }> = [
  { id: "COMPREHENSIVE", name: "综合投资价值研究", description: "基本面、同行、估值、风险与催化。", goal: "评估 {company} 当前的基本面、估值、主要风险以及未来投资价值。" },
  { id: "VALUATION", name: "估值分析", description: "估值水平、关键假设、敏感性与价格区间。", goal: "评估 {company} 当前估值水平、关键假设、同行倍数和潜在估值区间。" },
  { id: "RISK", name: "风险分析", description: "经营、财务、市场与事件风险。", goal: "识别并评估 {company} 当前经营、财务、市场和事件风险。" },
  { id: "CUSTOM", name: "自定义目标", description: "用自然语言描述这次研究要回答的问题。", goal: "" }
];
const goalFor = (template: GoalTemplate, company?: string) => (goalTemplates.find((item) => item.id === template)?.goal ?? "").replace("{company}", company ?? "所选公司");

export function NewResearchTaskPage({ objects, initialObjectId, initialMode = "FULL", onBack, onSearchObjects, onCreateObject, onPrepare, onStart }: {
  objects: ResearchObject[];
  initialObjectId?: string | null;
  initialMode?: "FULL" | "INCREMENTAL";
  onBack?: () => void;
  onSearchObjects: (query: string) => Promise<ResearchObject[]>;
  onCreateObject: (input: CreateResearchObjectInput) => Promise<ResearchObject>;
  onPrepare: (input: PrepareResearchRunInput) => Promise<ResearchPlan>;
  onStart: (input: { object: ResearchObject; goal: string; plan: ResearchPlan }) => Promise<ResearchRun>;
}) {
  const initialObject = objects.find((item) => item.id === initialObjectId) ?? objects[0];
  const [selectedId, setSelectedId] = useState(initialObject?.id ?? "");
  const [template, setTemplate] = useState<GoalTemplate>("COMPREHENSIVE");
  const [mode, setMode] = useState<"FULL" | "INCREMENTAL">(initialMode);
  const [goal, setGoal] = useState(goalFor("COMPREHENSIVE", initialObject?.name));
  const [step, setStep] = useState(1);
  const [plan, setPlan] = useState<ResearchPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const selected = useMemo(() => objects.find((item) => item.id === selectedId) ?? objects[0], [objects, selectedId]);
  const steps = ["研究对象", "研究目标", "AI 研究计划", "确认"];

  useEffect(() => {
    if (!initialObjectId) return;
    const object = objects.find((item) => item.id === initialObjectId);
    if (!object) return;
    setSelectedId(initialObjectId);
    if (template !== "CUSTOM") setGoal(goalFor(template, object.name));
  }, [initialObjectId, objects, template]);

  const selectObject = (object: ResearchObject) => { setSelectedId(object.id); if (template !== "CUSTOM") setGoal(goalFor(template, object.name)); };
  const prepare = async () => {
    if (!selected) return;
    setBusy(true); setError(null);
    try { setPlan(await onPrepare({ objectId: selected.id, goal: goal.trim(), template, mode })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "研究计划生成失败"); }
    finally { setBusy(false); }
  };
  const advance = async () => {
    setError(null);
    if (step === 1 && !selected) return setError("请先选择研究对象。");
    if (step === 2) { if (!goal.trim()) return setError("请描述本次研究目标。"); setStep(3); await prepare(); return; }
    if (step === 3) { if (!plan) return setError("AI 研究计划尚未准备完成。"); setStep(4); return; }
    if (step === 4 && selected && plan) { setBusy(true); try { await onStart({ object: selected, goal: goal.trim(), plan }); } catch (reason) { setError(reason instanceof Error ? reason.message : "Research Run 创建失败"); setBusy(false); } return; }
    setStep((value) => Math.min(4, value + 1));
  };

  return <section className="workspace-page" aria-labelledby="new-task-title">
    <div className="page-head"><div><button className="breadcrumb breadcrumb-button" onClick={onBack}>Research › 新建任务</button><h1 className="page-title" id="new-task-title">新建研究任务</h1><div className="page-sub">Full Research 与基于历史研究的 Incremental Research 使用不同计划投影。</div></div></div>
    <div className="stepper" aria-label="新建研究任务步骤">{steps.map((label, index) => <div className="step-fragment" key={label}><div className={`step ${index + 1 < step ? "done" : index + 1 === step ? "active" : ""}`}><span className="step-num">{index + 1 < step ? "✓" : index + 1}</span><span>{label}</span></div>{index < steps.length - 1 && <div className="step-line" />}</div>)}</div>
    <div className="wizard"><div className="card wizard-main">
      {step === 1 && <div><div className="section-heading"><div><strong>选择研究对象</strong><div className="small">Broadcom creation 是独立的 generic acceptance，不会继承 NVIDIA 数据。</div></div><button className="btn sm" onClick={() => setShowCreate(true)}>+ 创建新对象</button></div><div className="option-grid">{objects.map((item) => <button type="button" key={item.id} className={`option ${selected?.id === item.id ? "selected" : ""}`} onClick={() => selectObject(item)}><span><strong>{item.name} · {item.symbol}</strong><span className="small option-sub">{item.exchange} · {item.industry}</span></span><span className={`badge ${item.dataStatus === "READY" ? "green" : "amber"}`}>{item.dataStatus}</span></button>)}</div></div>}
      {step === 2 && <div><div className="section-heading"><div><strong>设置研究目标</strong><div className="small">选择研究模式后，AI Plan 会展示对应的路径与历史复用策略。</div></div></div><div className="research-mode-grid"><button className={`option ${mode === "FULL" ? "selected" : ""}`} onClick={() => setMode("FULL")}><strong>Full Research</strong><span className="small option-sub">从数据获取开始的完整研究。</span></button><div className="research-mode-option"><button aria-describedby={!selected?.latestReleasedRunId ? "incremental-mode-reason" : undefined} className={`option ${mode === "INCREMENTAL" ? "selected" : ""}`} disabled={!selected?.latestReleasedRunId} onClick={() => setMode("INCREMENTAL")} title={!selected?.latestReleasedRunId ? "需要该对象先有一个已发布 Research Run" : undefined}><strong>基于历史研究开始</strong><span className="small option-sub">Previous Research Memory → Freshness Check → Updated Result</span></button>{!selected?.latestReleasedRunId && <small className="disabled-reason" id="incremental-mode-reason">需要该对象先完成并发布一次 Full Research，才能复用历史研究。</small>}</div></div><div className="option-grid">{goalTemplates.map((item) => <button type="button" key={item.id} className={`option ${template === item.id ? "selected" : ""}`} onClick={() => { setTemplate(item.id); setGoal(item.goal ? goalFor(item.id, selected?.name) : ""); }}><strong>{item.name}</strong><span className="small option-sub">{item.description}</span></button>)}</div><div className="field spaced-field"><label className="label" htmlFor="research-goal">Research Goal</label><textarea id="research-goal" className="textarea" value={goal} onChange={(event) => setGoal(event.target.value)} /></div></div>}
      {step === 3 && <div><div className="section-heading"><div><strong>AI 生成研究计划</strong><div className="small">计划内容来自 Demo scenario projection，不展示隐藏推理。</div></div><button className="btn sm" disabled={busy} onClick={prepare}>重新生成</button></div><div className="plan-shell" aria-live="polite">{busy && <div className="loading-row"><div className="spinner" /><div><strong>AI 正在生成金融研究计划…</strong></div></div>}{!busy && plan && <PlanPreview plan={plan} />}{!busy && !plan && <div className="empty-state">计划尚未生成。</div>}</div></div>}
      {step === 4 && selected && plan && <div><div className="section-heading"><div><strong>确认研究任务</strong><div className="small">{plan.mode} · {plan.symbol} · subject-owned runtime</div></div><span className="badge green">Plan ready</span></div><div className="grid2"><div className="plan-section"><h4>研究对象</h4><strong>{selected.name} · {selected.symbol}</strong></div><div className="plan-section"><h4>研究目标</h4><div className="small">{goal}</div></div><div className="plan-section"><h4>研究模式</h4><strong>{plan.mode}</strong></div><div className="plan-section"><h4>最终交付</h4><div className="small">Report · Financial Review · Canonical Execution Record</div></div></div></div>}
      {error && <div className="inline-error" role="alert">{error}</div>}
      <div className="wizard-footer"><button className="btn" disabled={step === 1 || busy} onClick={() => { setError(null); setStep((value) => Math.max(1, value - 1)); }}>返回</button><button className="btn primary" disabled={busy || (step === 3 && !plan)} onClick={advance}>{step === 4 ? "开始研究" : "下一步"}</button></div>
    </div><aside className="card wizard-side"><strong>Research Draft</strong><Summary label="Object" value={selected ? `${selected.name} · ${selected.symbol}` : "未选择"} /><Summary label="Mode" value={mode} /><Summary label="Plan" value={plan ? "AI Research Plan Ready" : "等待 AI 生成"} /><Summary label="Identity" value={selected ? selected.id : "Unavailable"} /></aside></div>
    {showCreate && <CreateObjectModal onSearch={onSearchObjects} onClose={() => setShowCreate(false)} onCreate={async (input) => { const created = await onCreateObject(input); selectObject(created); setShowCreate(false); }} />}
  </section>;
}

function PlanPreview({ plan }: { plan: ResearchPlan }) {
  return <><div className="plan-title-row"><div><strong>{plan.title}</strong><div className="small">{plan.planId} · {plan.symbol} · {plan.mode}</div></div><span className="badge green">可以确认</span></div>{plan.memory && <div className="memory-card"><div><strong>Previous Research Memory</strong><span className="small">source · {plan.memory.sourceRunId} · Demo provenance</span></div><div className="grid2"><PlanList title="Reviewed / Verified" items={[`${plan.memory.reviewedClaims} reviewed claims`, ...plan.memory.verifiedMetrics]} /><PlanList title="Historical Issues" items={[...plan.memory.historicalIssues, ...plan.memory.priorPathAdjustments]} /></div></div>}{plan.incrementalStrategy && <div className="strategy-grid"><PlanList title="REUSE" items={plan.incrementalStrategy.reuse} /><PlanList title="REFRESH" items={plan.incrementalStrategy.refresh} /><PlanList title="REVALIDATE" items={plan.incrementalStrategy.revalidate} /><PlanList title="PREVENT PREVIOUS ISSUE" items={plan.incrementalStrategy.prevent} /></div>}<div className="grid2"><PlanList title="本次重点回答" items={plan.questions} /><PlanList title="研究范围" items={plan.scopes} /><PlanList title="重点数据" items={plan.dataRequirements} /><PlanList title="研究方法" items={plan.methods} /></div></>;
}
function PlanList({ title, items }: { title: string; items: string[] }) { return <div className="plan-section"><h4>{title}</h4><ul className="plan-list">{items.map((item) => <li key={item}>{item}</li>)}</ul></div>; }
function Summary({ label, value }: { label: string; value: string }) { return <div className="summary-item"><div className="summary-label">{label}</div><strong>{value}</strong></div>; }

function CreateObjectModal({ onClose, onSearch, onCreate }: { onClose: () => void; onSearch: (query: string) => Promise<ResearchObject[]>; onCreate: (input: CreateResearchObjectInput) => Promise<void> }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ResearchObject[]>([]);
  const [candidate, setCandidate] = useState<ResearchObject | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "empty" | "invalid">("idle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setCandidate(null); setError(null);
    if (!query.trim()) { setResults([]); setStatus("idle"); return; }
    setStatus("loading");
    const timeout = window.setTimeout(() => void onSearch(query).then((items) => { setResults(items); setStatus(items.length ? "ready" : "empty"); }).catch((reason) => { setResults([]); setStatus("invalid"); setError(reason instanceof Error ? reason.message : "搜索失败"); }), 220);
    return () => window.clearTimeout(timeout);
  }, [onSearch, query]);
  return <OverlaySurface kind="modal" titleId="create-object-title" onClose={onClose} footer={<><button className="btn" onClick={onClose}>取消</button><button className="btn primary" disabled={!candidate || busy} onClick={async () => { if (!candidate) return; setBusy(true); try { await onCreate(candidate); } catch (reason) { setError(reason instanceof Error ? reason.message : "研究对象创建失败"); setBusy(false); } }}>{busy ? "正在创建…" : "创建研究对象"}</button></>}>
    <div className="modal-head"><strong id="create-object-title">创建研究对象</strong><button className="btn ghost" onClick={onClose} aria-label="关闭创建对象">✕</button></div>
    <div className="modal-body"><div className="field"><label className="label" htmlFor="company-search">公司名称 / Ticker</label><div className="search-input-row"><input className="input" id="company-search" data-autofocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="例如 Broadcom 或 AVGO" aria-describedby="company-search-status" />{query && <button className="btn ghost sm" onClick={() => setQuery("")} aria-label="清除搜索">清除</button>}</div></div><div id="company-search-status" className="search-status" role="status">{status === "idle" && "输入公司名称或 Ticker 开始搜索。"}{status === "loading" && "正在搜索 Demo company catalog…"}{status === "empty" && "未找到匹配公司。请清除后重试。"}{status === "invalid" && "输入无效。"}{status === "ready" && `${results.length} 个结果`}</div>{results.map((object) => <button className={`company-result ${candidate?.id === object.id ? "selected" : ""}`} key={object.id} onClick={() => setCandidate(object)}><strong>{object.name}</strong><span className="small option-sub">{object.symbol} · {object.exchange} · {object.industry}</span></button>)}{candidate && <div className="card candidate-card"><div className="section-heading"><div><strong>{candidate.name}</strong><div className="small">{candidate.symbol} · {candidate.exchange}</div></div><span className="badge green">已选择</span></div><div className="small">新对象只创建身份与空 projection；不会复用任何其他公司的 Claim、Task 或 Artifact。</div></div>}{error && <div className="inline-error" role="alert">{error}</div>}</div>
  </OverlaySurface>;
}
