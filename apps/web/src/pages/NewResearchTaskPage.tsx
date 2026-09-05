import { useState, type ReactNode } from "react";
import type { NormalizedObjectIdentity, PreparedResearchDraft, SafeJsonValue } from "../types/domain";
import {
  selectCanConfirm,
  selectCanPrepare,
  selectConfirmPending,
  selectGoalText,
  selectPreparedDraft,
  selectProductFlowStep,
  selectRetryState,
  selectSelectedObject,
  selectVisibleError,
  type Phase4ProductState,
  type Phase4RequestFailure,
  type Phase4RetryState
} from "../state/status";
import { RunWorkspaceShell } from "./ResearchRunsPage";
import "../styles/workspace-pages.css";

type GoalTemplateId = "COMPREHENSIVE" | "VALUATION" | "RISK" | "CUSTOM";

interface GoalTemplate {
  readonly id: GoalTemplateId;
  readonly name: string;
  readonly description: string;
  readonly goal: string;
}

const GOAL_TEMPLATES: readonly GoalTemplate[] = [
  {
    id: "COMPREHENSIVE",
    name: "综合投资价值研究",
    description: "基本面、同行、估值、风险与催化因素。",
    goal: "评估 {company} 当前的基本面、估值、主要风险以及未来投资价值。"
  },
  {
    id: "VALUATION",
    name: "估值分析",
    description: "估值水平、关键假设、敏感性与价格区间。",
    goal: "评估 {company} 当前估值水平、关键假设、同行倍数和潜在估值区间。"
  },
  {
    id: "RISK",
    name: "风险分析",
    description: "经营、财务、市场与事件风险。",
    goal: "识别并评估 {company} 当前经营、财务、市场和事件风险。"
  },
  {
    id: "CUSTOM",
    name: "自定义目标",
    description: "用自然语言描述本次研究需要回答的问题。",
    goal: ""
  }
] as const;

const FLOW_STEPS = [
  ["OBJECT", "研究对象"],
  ["GOAL", "研究目标"],
  ["SCHEME", "研究方案"],
  ["CONFIRM", "确认"],
  ["WORKSPACE", "运行空间"]
] as const;

export interface NewResearchTaskPageProps {
  /** The single canonical business-state projection. */
  readonly state: Phase4ProductState;
  readonly objects: readonly NormalizedObjectIdentity[];
  readonly onBack?: () => void;
  readonly onCreateObject?: () => void;
  readonly onResetFlow?: () => void;
  readonly onSelectObject: (object: NormalizedObjectIdentity) => void;
  readonly onGoalChange: (goal: string) => void;
  readonly onPrepare: () => void;
  readonly onConfirm: () => void;
  readonly onRetry?: (retry: Phase4RetryState) => void;
  readonly onDismissAlert?: () => void;
  /** Reserved attachment point for the C-owned live Research Path projection. */
  readonly workspaceChildren?: ReactNode;
}

/**
 * Controlled Phase 4 journey. Canonical Object, Goal, draft, admission and Run
 * state all come from the central reducer; this component owns presentation only.
 */
export function NewResearchTaskPage({
  state,
  objects,
  onBack,
  onCreateObject,
  onResetFlow,
  onSelectObject,
  onGoalChange,
  onPrepare,
  onConfirm,
  onRetry,
  onDismissAlert,
  workspaceChildren
}: NewResearchTaskPageProps) {
  const [template, setTemplate] = useState<GoalTemplateId | null>(null);
  const step = selectProductFlowStep(state);
  const selected = selectSelectedObject(state);
  const goal = selectGoalText(state);
  const draft = selectPreparedDraft(state);
  const retry = selectRetryState(state);
  const alert = selectVisibleError(state);
  const canPrepare = selectCanPrepare(state);
  const canConfirm = selectCanConfirm(state);
  const confirmPending = selectConfirmPending(state);

  if (step === "WORKSPACE") {
    return <RunWorkspaceShell
      state={state}
      onBackToRuns={onBack}
      onRetry={onRetry}
    >{workspaceChildren}</RunWorkspaceShell>;
  }

  const activeIndex = FLOW_STEPS.findIndex(([id]) => id === step);
  const chooseTemplate = (item: GoalTemplate) => {
    setTemplate(item.id);
    onGoalChange(item.goal.replace("{company}", selected?.companyName ?? "所选公司"));
  };

  return <section className="workspace-page" aria-labelledby="new-task-title">
    <div className="page-head">
      <div>
        <button type="button" className="breadcrumb breadcrumb-button" onClick={onBack}>Research › 新建任务</button>
        <h1 className="page-title" id="new-task-title">新建研究任务</h1>
        <div className="page-sub">选择研究对象，定义目标，审阅 AI 研究方案并确认一次。确认后 Run 将自动创建并启动。</div>
      </div>
    </div>

    <div className="stepper" aria-label="新建研究任务步骤">
      {FLOW_STEPS.map(([id, label], index) => <div className="step-fragment" key={id}>
        <div
          className={`step ${index < activeIndex ? "done" : index === activeIndex ? "active" : ""}`}
          aria-current={index === activeIndex ? "step" : undefined}
        >
          <span className="step-num" aria-hidden="true">{index < activeIndex ? "✓" : index + 1}</span>
          <span>{label}</span>
        </div>
        {index < FLOW_STEPS.length - 1 && <div className="step-line" />}
      </div>)}
    </div>

    <div className="wizard">
      <div className="card wizard-main">
        {step === "OBJECT" && <ObjectStep
          objects={objects}
          selected={selected}
          onCreateObject={onCreateObject}
          onSelectObject={onSelectObject}
        />}

        {step === "GOAL" && selected && <GoalStep
          selected={selected}
          goal={goal}
          selectedTemplate={template}
          onChooseTemplate={chooseTemplate}
          onGoalChange={(value) => {
            setTemplate(value === goal ? template : "CUSTOM");
            onGoalChange(value);
          }}
        />}

        {(step === "SCHEME" || step === "CONFIRM") && <SchemeStep
          state={state}
          draft={draft}
          confirmPending={confirmPending}
          retry={retry}
          onPrepare={onPrepare}
          onRetry={onRetry}
        />}

        {alert && <FlowAlert alert={alert} retry={retry} onRetry={onRetry} onDismiss={onDismissAlert} />}

        <div className="wizard-footer">
          <button
            type="button"
            className="btn"
            disabled={confirmPending}
            onClick={step === "OBJECT" ? onBack : onResetFlow ?? onBack}
          >{step === "OBJECT" ? "返回" : "重新选择对象"}</button>

          {step === "GOAL" && <button type="button" className="btn primary" disabled={!canPrepare} onClick={onPrepare}>
            生成研究方案
          </button>}

          {step === "SCHEME" && <button
            type="button"
            className="btn primary"
            disabled={!canConfirm}
            onClick={onConfirm}
          >确认研究方案</button>}

          {step === "CONFIRM" && <button type="button" className="btn primary" disabled>
            {confirmPending ? "正在确认并自动启动…" : "确认请求未完成"}
          </button>}
        </div>
      </div>

      <aside className="card wizard-side" aria-label="研究任务身份摘要">
        <strong>Research Draft</strong>
        <Summary label="Object" value={selected ? `${selected.companyName} · ${selected.symbol}` : "未选择"} />
        <Summary label="Object ID" value={selected?.objectId ?? "Unavailable"} mono />
        <Summary label="Goal ID" value={draft?.goal.goalId ?? "准备后分配"} mono />
        <Summary label="Scheme ID" value={draft?.schemeSnapshot.schemeId ?? "准备后分配"} mono />
        <Summary label="Preview" value={draft?.previewKind ?? "等待生成"} />
      </aside>
    </div>
  </section>;
}

function ObjectStep({ objects, selected, onCreateObject, onSelectObject }: {
  readonly objects: readonly NormalizedObjectIdentity[];
  readonly selected: NormalizedObjectIdentity | null;
  readonly onCreateObject?: () => void;
  readonly onSelectObject: (object: NormalizedObjectIdentity) => void;
}) {
  return <div>
    <div className="section-heading">
      <div>
        <strong>选择研究对象</strong>
        <div className="small">后续 Goal、Scheme 与 Run 始终绑定此精确对象身份。</div>
      </div>
      {onCreateObject && <button type="button" className="btn sm" onClick={onCreateObject}>+ 创建研究对象</button>}
    </div>
    {objects.length === 0
      ? <div className="empty-state" role="status">尚无可用研究对象。请先创建一个 Research Object。</div>
      : <div className="option-grid">{objects.map((object) => <button
          type="button"
          key={object.objectId}
          className={`option ${selected?.objectId === object.objectId ? "selected" : ""}`}
          aria-pressed={selected?.objectId === object.objectId}
          onClick={() => onSelectObject(object)}
        >
          <span>
            <strong>{object.companyName} · {object.symbol}</strong>
            <span className="small option-sub">{object.exchange} · {object.sector ?? "Sector unavailable"}</span>
          </span>
          <span className="identity-token">{object.objectId}</span>
        </button>)}</div>}
  </div>;
}

function GoalStep({ selected, goal, selectedTemplate, onChooseTemplate, onGoalChange }: {
  readonly selected: NormalizedObjectIdentity;
  readonly goal: string;
  readonly selectedTemplate: GoalTemplateId | null;
  readonly onChooseTemplate: (template: GoalTemplate) => void;
  readonly onGoalChange: (goal: string) => void;
}) {
  return <div>
    <div className="section-heading">
      <div>
        <strong>设置研究目标</strong>
        <div className="small">目标文本是研究意图的权威输入；模板仅用于填写文本。</div>
      </div>
      <span className="badge blue">Full Research</span>
    </div>
    <div className="option-grid">{GOAL_TEMPLATES.map((item) => <button
      type="button"
      key={item.id}
      className={`option ${selectedTemplate === item.id ? "selected" : ""}`}
      aria-pressed={selectedTemplate === item.id}
      onClick={() => onChooseTemplate(item)}
    >
      <span>
        <strong>{item.name}</strong>
        <span className="small option-sub">{item.description}</span>
      </span>
    </button>)}</div>
    <div className="field spaced-field">
      <label className="label" htmlFor="research-goal">Research Goal · {selected.symbol}</label>
      <textarea
        id="research-goal"
        className="textarea"
        value={goal}
        onChange={(event) => onGoalChange(event.target.value)}
        aria-describedby="research-goal-help"
      />
      <div className="small field-help" id="research-goal-help">请明确本次研究需要回答的问题。研究方案会绑定当前 Goal 文本。</div>
    </div>
  </div>;
}

function SchemeStep({ state, draft, confirmPending, retry, onPrepare, onRetry }: {
  readonly state: Phase4ProductState;
  readonly draft: PreparedResearchDraft | null;
  readonly confirmPending: boolean;
  readonly retry: Phase4RetryState | null;
  readonly onPrepare: () => void;
  readonly onRetry?: (retry: Phase4RetryState) => void;
}) {
  const phase = state.prepare.request.phase;
  if (phase === "LOADING") {
    return <div aria-live="polite">
      <div className="section-heading"><div><strong>AI 正在生成研究方案</strong><div className="small">这里只生成 Scheme；Task 与执行图将在确认后由后端创建。</div></div></div>
      <div className="plan-shell"><div className="loading-row" role="status"><div className="spinner" aria-hidden="true" /><strong>正在准备 Scheme-only 预览…</strong></div></div>
    </div>;
  }

  if (!draft) {
    return <div>
      <div className="section-heading"><div><strong>研究方案不可用</strong><div className="small">当前没有可确认的 Scheme。</div></div></div>
      <div className="empty-state" role="status">未接纳任何草稿或运行身份。</div>
      {retry?.request === "PREPARE" && onRetry
        ? <button type="button" className="btn" onClick={() => onRetry(retry)}>重试生成方案</button>
        : state.prepare.mutation === null || phase === "READY"
          ? <button type="button" className="btn" onClick={onPrepare}>重新生成方案</button>
          : <div className="small field-help">该请求不可用新的幂等键重提；请修改目标或重新选择对象。</div>}
    </div>;
  }

  return <div>
    <div className="section-heading">
      <div>
        <strong>{confirmPending ? "正在确认研究方案" : "审阅 AI 研究方案"}</strong>
        <div className="small">Scheme-only 预览不包含尚未创建的 Task 或运行进度。</div>
      </div>
      <span className="badge green">{draft.previewKind}</span>
    </div>
    {confirmPending && <div className="loading-row confirm-progress" role="status" aria-live="assertive">
      <div className="spinner" aria-hidden="true" />
      <div><strong>正在确认、创建 Run 并自动启动研究…</strong><div className="small">请勿重复提交；此流程不需要第二次启动操作。</div></div>
    </div>}
    <SchemePreview draft={draft} />
    {!confirmPending && state.step === "SCHEME" && <div className="scheme-actions">
      <button type="button" className="btn sm" onClick={onPrepare}>重新生成研究方案</button>
      <span className="small">重新生成会创建新的草稿身份。</span>
    </div>}
  </div>;
}

function SchemePreview({ draft }: { readonly draft: PreparedResearchDraft }) {
  const scheme = draft.schemeSnapshot;
  const assuranceItems = Object.entries(scheme.assuranceRequirements).map(([key, value]) => `${key}: ${safeValueText(value)}`);
  return <div className="plan-shell" aria-label="研究方案预览">
    <div className="plan-title-row">
      <div>
        <strong>AI Research Scheme</strong>
        <div className="small identity-line">Draft <code>{draft.draftId}</code> · v{draft.draftVersion} · expires {formatTimestamp(draft.expiresAt)}</div>
      </div>
      <span className="badge amber">等待确认</span>
    </div>
    <dl className="identity-grid compact-identity-grid">
      <Identity label="Object ID" value={draft.objectId} />
      <Identity label="Goal ID" value={draft.goal.goalId} />
      <Identity label="Scheme ID" value={scheme.schemeId} />
      <Identity label="Planned graph" value={`${draft.plannedGraphAvailability.status} · ${draft.plannedGraphAvailability.reasonCode ?? "No reason"}`} />
      <Identity label="Draft hash" value={draft.draftHash} />
    </dl>
    <div className="goal-statement"><span className="micro">研究目标</span><strong>{draft.goal.goalText}</strong><span className="small">As of {draft.goal.asOf}</span></div>
    <div className="scheme-grid">
      <PlanList title="研究范围" items={scheme.researchScope} />
      <PlanList title="数据要求" items={scheme.dataRequirements} />
      <PlanList title="Agent 要求" items={scheme.agentRequirements} />
      <PlanList title="Skill 要求" items={scheme.skillRequirements} />
      <PlanList title="计算要求" items={scheme.calculationRequirements} />
      <PlanList title="保证要求" items={assuranceItems} />
      <PlanList title="报告要求" items={scheme.reportRequirements} />
      <PlanList title="已知限制" items={scheme.limitations} emptyLabel="未声明限制" />
    </div>
    <div className="scheme-provenance small">Generated by {scheme.generatedBy}{scheme.generatedModel ? ` · ${scheme.generatedModel}` : ""} · {formatTimestamp(scheme.createdAt)}</div>
  </div>;
}

function FlowAlert({ alert, retry, onRetry, onDismiss }: {
  readonly alert: ReturnType<typeof selectVisibleError>;
  readonly retry: Phase4RetryState | null;
  readonly onRetry?: (retry: Phase4RetryState) => void;
  readonly onDismiss?: () => void;
}) {
  if (!alert) return null;
  const text = alert.kind === "ERROR"
    ? failureText(alert.error)
    : "响应身份或请求顺序不匹配，已隔离且未写入当前研究状态。";
  return <div className="inline-error flow-alert" role="alert">
    <span>{text}</span>
    <span className="flow-alert-actions">
      {retry && onRetry && <button type="button" className="btn sm" onClick={() => onRetry(retry)}>
        {retry.request === "CONFIRM" ? "重试同一确认请求" : retry.request === "WORKSPACE" ? "重试载入快照" : "重试"}
      </button>}
      {onDismiss && <button type="button" className="btn ghost sm" onClick={onDismiss}>关闭</button>}
    </span>
  </div>;
}

function PlanList({ title, items, emptyLabel = "未提供" }: { readonly title: string; readonly items: readonly string[]; readonly emptyLabel?: string }) {
  return <div className="plan-section">
    <h4>{title}</h4>
    {items.length > 0
      ? <ul className="plan-list">{items.map((item, index) => <li key={`${index}:${item}`}>{item}</li>)}</ul>
      : <div className="small">{emptyLabel}</div>}
  </div>;
}

function Summary({ label, value, mono = false }: { readonly label: string; readonly value: string; readonly mono?: boolean }) {
  return <div className="summary-item"><div className="summary-label">{label}</div><strong className={mono ? "mono-value" : undefined}>{value}</strong></div>;
}

function Identity({ label, value }: { readonly label: string; readonly value: string }) {
  return <div><dt>{label}</dt><dd><code>{value}</code></dd></div>;
}

function safeValueText(value: SafeJsonValue): string {
  if (value === null) return "null";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function failureText(failure: Phase4RequestFailure): string {
  return "kind" in failure
    ? `${failure.code}: ${failure.message}`
    : `${failure.error.code}: ${failure.error.message}`;
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN");
}
