import type { NormalizedObjectIdentity, PreparedResearchDraft } from "../types/domain";

export type NewResearchStep = "OBJECT" | "GOAL" | "SCHEME" | "CONFIRM";

export interface NewResearchTaskPageProps {
  readonly step: NewResearchStep;
  readonly objects: readonly NormalizedObjectIdentity[];
  readonly selected: NormalizedObjectIdentity | null;
  readonly goal: string;
  readonly asOf: string;
  readonly draft: PreparedResearchDraft | null;
  readonly preparing: boolean;
  readonly confirming: boolean;
  readonly onSelectObject: (object: NormalizedObjectIdentity) => void;
  readonly onGoalChange: (goal: string) => void;
  readonly onStepChange: (step: NewResearchStep) => void;
  readonly onPrepare: () => void;
  readonly onConfirm: () => void;
}

const STEPS: readonly { id: NewResearchStep; number: string; label: string }[] = [
  { id: "OBJECT", number: "1", label: "研究对象" },
  { id: "GOAL", number: "2", label: "研究目标" },
  { id: "SCHEME", number: "3", label: "AI 研究计划" },
  { id: "CONFIRM", number: "4", label: "确认" }
];

const PLAN_LABELS: Readonly<Record<string, string>> = {
  verified_financial_evidence: "金融数据验证",
  evidence_collection: "金融数据验证",
  fundamental_analysis: "Fundamental Analysis · 基本面分析",
  peer_analysis: "Peer Analysis · 同业分析",
  research_and_news_analysis: "Research & News · 研究与事件分析",
  research_news_analysis: "Research & News · 研究与事件分析",
  valuation_analysis: "Valuation Analysis · 估值分析",
  risk_analysis: "Risk Analysis · 风险分析",
  risk_follow_up: "风险跟进验证",
  report_synthesis: "Report Synthesis · 研究汇总"
};

export function researchPlanLabel(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[\s-]+/gu, "_");
  return PLAN_LABELS[normalized] ?? value.replace(/_/gu, " ");
}

export function NewResearchTaskPage({
  step,
  objects,
  selected,
  goal,
  asOf,
  draft,
  preparing,
  confirming,
  onSelectObject,
  onGoalChange,
  onStepChange,
  onPrepare,
  onConfirm
}: NewResearchTaskPageProps) {
  const stepIndex = STEPS.findIndex((item) => item.id === step);
  return <section className="workspace-page new-research-page" aria-labelledby="new-research-title">
    <div className="page-head">
      <div>
        <div className="breadcrumb">Research › 新建研究</div>
        <h1 className="page-title" id="new-research-title">新建公司金融研究</h1>
        <div className="page-sub">定义 Research Object 与研究目标，由真实后端生成 AI 研究计划并创建唯一 Research Run。</div>
      </div>
    </div>

    <ol className="wizard-stepper" aria-label="新建研究进度">
      {STEPS.map((item, index) => <li
        key={item.id}
        className={`${index === stepIndex ? "active" : ""} ${index < stepIndex ? "done" : ""}`}
        aria-current={index === stepIndex ? "step" : undefined}
      >
        <span>{index < stepIndex ? "✓" : item.number}</span>
        <strong>{item.label}</strong>
      </li>)}
    </ol>

    <div className="research-wizard">
      <div className="card wizard-main">
        {step === "OBJECT" && <ObjectStep objects={objects} selected={selected} onSelect={onSelectObject} onNext={() => onStepChange("GOAL")} />}
        {step === "GOAL" && <GoalStep selected={selected} goal={goal} asOf={asOf} onGoalChange={onGoalChange} onBack={() => onStepChange("OBJECT")} onPrepare={onPrepare} preparing={preparing} />}
        {step === "SCHEME" && draft && <PlanStep draft={draft} onBack={() => onStepChange("GOAL")} onNext={() => onStepChange("CONFIRM")} />}
        {step === "CONFIRM" && draft && <ConfirmStep draft={draft} selected={selected} goal={goal} confirming={confirming} onBack={() => onStepChange("SCHEME")} onConfirm={onConfirm} />}
      </div>
      <ResearchDraftSummary selected={selected} goal={goal} asOf={asOf} draft={draft} />
    </div>
  </section>;
}

function ObjectStep({ objects, selected, onSelect, onNext }: {
  readonly objects: readonly NormalizedObjectIdentity[];
  readonly selected: NormalizedObjectIdentity | null;
  readonly onSelect: (object: NormalizedObjectIdentity) => void;
  readonly onNext: () => void;
}) {
  return <>
    <div className="wizard-section-heading"><span>STEP 1</span><h2>选择 Research Object</h2><p>选择本次研究对应的公司实体。</p></div>
    <div className="object-option-grid">
      {objects.map((object) => <button
        type="button"
        className={`object-option ${selected?.objectId === object.objectId ? "selected" : ""}`}
        data-testid="research-object-option"
        data-object-id={object.objectId}
        key={object.objectId}
        onClick={() => onSelect(object)}
      >
        <span className="company-logo" aria-hidden="true">{object.symbol}</span>
        <span><strong>{object.companyName}</strong><small>{object.symbol} · {object.exchange}</small></span>
        <span className="selection-mark" aria-hidden="true">{selected?.objectId === object.objectId ? "✓" : ""}</span>
      </button>)}
    </div>
    <WizardActions nextLabel="下一步：研究目标" nextDisabled={selected === null} onNext={onNext} />
  </>;
}

function GoalStep({ selected, goal, asOf, onGoalChange, onBack, onPrepare, preparing }: {
  readonly selected: NormalizedObjectIdentity | null;
  readonly goal: string;
  readonly asOf: string;
  readonly onGoalChange: (goal: string) => void;
  readonly onBack: () => void;
  readonly onPrepare: () => void;
  readonly preparing: boolean;
}) {
  return <>
    <div className="wizard-section-heading"><span>STEP 2</span><h2>定义研究目标</h2><p>明确本次研究需要回答的问题和时间基准。</p></div>
    <button type="button" className="goal-template" data-testid="full-research" onClick={() => onGoalChange("完整公司金融研究")}>
      <strong>完整公司金融研究</strong><small>基本面、同业、估值、风险与研究汇总</small>
    </button>
    <label className="field-label">研究目标
      <textarea className="goal" aria-label="研究目标" value={goal} onChange={(event) => onGoalChange(event.target.value)} placeholder={`描述需要针对 ${selected?.companyName ?? "该公司"} 回答的研究问题`} />
    </label>
    <label className="field-label">As-of<input className="text-input" value={asOf} readOnly /></label>
    <WizardActions backLabel="返回" nextLabel={preparing ? "正在生成 AI 研究计划…" : "生成 AI 研究计划"} nextDisabled={!goal.trim() || preparing} onBack={onBack} onNext={onPrepare} />
  </>;
}

function PlanStep({ draft, onBack, onNext }: { readonly draft: PreparedResearchDraft; readonly onBack: () => void; readonly onNext: () => void }) {
  return <>
    <div className="wizard-section-heading"><span>STEP 3</span><h2>AI 研究计划</h2><p>计划来自当前草稿投影；确认前不会创建 Research Run。</p></div>
    <div className="ai-plan-card">
      <div className="ai-plan-head"><div><span>PLANNED RESEARCH</span><strong>{draft.goal.goalText}</strong></div><span className="badge amber">等待确认</span></div>
      <div className="plan-workstreams">
        {draft.schemeSnapshot.researchScope.map((item, index) => <div className="plan-workstream" key={`${item}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><strong>{researchPlanLabel(item)}</strong></div>)}
      </div>
      <details className="technical-details"><summary>计划技术详情</summary><dl><dt>Draft ID</dt><dd>{draft.draftId}</dd><dt>Goal ID</dt><dd>{draft.goal.goalId}</dd><dt>Scheme ID</dt><dd>{draft.schemeSnapshot.schemeId}</dd></dl></details>
    </div>
    <WizardActions backLabel="修改目标" nextLabel="下一步：确认" onBack={onBack} onNext={onNext} />
  </>;
}

function ConfirmStep({ draft, selected, goal, confirming, onBack, onConfirm }: {
  readonly draft: PreparedResearchDraft;
  readonly selected: NormalizedObjectIdentity | null;
  readonly goal: string;
  readonly confirming: boolean;
  readonly onBack: () => void;
  readonly onConfirm: () => void;
}) {
  return <>
    <div className="wizard-section-heading"><span>STEP 4</span><h2>确认研究</h2><p>一次确认将创建一个唯一 Research Run，并由后端自动开始研究。</p></div>
    <div className="confirm-summary">
      <div><span>Research Object</span><strong>{selected?.companyName ?? draft.objectId}</strong></div>
      <div><span>研究目标</span><strong>{goal}</strong></div>
      <div><span>AI 研究计划</span><strong>{draft.schemeSnapshot.researchScope.length} 个研究工作流</strong></div>
    </div>
    <WizardActions backLabel="返回计划" nextLabel={confirming ? "正在创建 Research Run…" : "确认并开始研究"} nextDisabled={confirming} onBack={onBack} onNext={onConfirm} />
  </>;
}

function ResearchDraftSummary({ selected, goal, asOf, draft }: {
  readonly selected: NormalizedObjectIdentity | null;
  readonly goal: string;
  readonly asOf: string;
  readonly draft: PreparedResearchDraft | null;
}) {
  return <aside className="card draft-summary" aria-label="Research Draft 摘要">
    <div><span className="eyebrow">RESEARCH DRAFT</span><h2>本次研究</h2><p>确认前可持续调整。</p></div>
    <dl>
      <div><dt>Research Object</dt><dd>{selected ? `${selected.companyName} · ${selected.symbol}` : "尚未选择"}</dd></div>
      <div><dt>研究目标</dt><dd>{goal || "尚未定义"}</dd></div>
      <div><dt>As-of</dt><dd>{asOf}</dd></div>
      <div><dt>AI 研究计划</dt><dd>{draft ? `${draft.schemeSnapshot.researchScope.length} 个工作流` : "等待生成"}</dd></div>
    </dl>
    <div className="draft-note">Research Run 仅在最后确认后创建。</div>
  </aside>;
}

function WizardActions({ backLabel, nextLabel, nextDisabled = false, onBack, onNext }: {
  readonly backLabel?: string;
  readonly nextLabel: string;
  readonly nextDisabled?: boolean;
  readonly onBack?: () => void;
  readonly onNext: () => void;
}) {
  return <div className="wizard-actions">
    <div>{onBack && <button type="button" className="secondary" onClick={onBack}>{backLabel}</button>}</div>
    <button type="button" className="primary" data-testid="wizard-next" disabled={nextDisabled} onClick={onNext}>{nextLabel}</button>
  </div>;
}
