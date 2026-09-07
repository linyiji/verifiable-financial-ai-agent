import { useEffect, useMemo, useRef, useState } from "react";
import type { FinancialReviewCheckV1, FinancialReviewSurfaceV1, ReviewCheckSelectorV1 } from "../../types/domain";
import {
  checkPresentation,
  exceptionReviewChecks,
  groupFinancialReview,
  resolveExactReviewCheck,
  reviewHasObservableMachineRelation,
  reviewSelectorKey,
  subjectKind
} from "./reviewModel";

export interface InteractiveFinancialReviewProps {
  readonly review: FinancialReviewSurfaceV1;
  readonly requestedSelector?: ReviewCheckSelectorV1 | null;
  readonly returnAnchor?: string | null;
  readonly context: "results" | "run";
  readonly onOpenReport?: (anchor: string) => void;
  readonly onOpenExecution?: (check: FinancialReviewCheckV1) => void;
}

type ReviewMode = "FULL" | "EXCEPTIONS";

const verdictLabel = (status: FinancialReviewCheckV1["status"]): string => status === "PASS"
  ? "通过"
  : status === "REVIEW" ? "需要复核" : "阻断发布";

const verdictClass = (status: FinancialReviewCheckV1["status"]): string => status === "PASS"
  ? "green"
  : status === "REVIEW" ? "amber" : "red";

export function InteractiveFinancialReview({
  review,
  requestedSelector = null,
  returnAnchor = null,
  context,
  onOpenReport,
  onOpenExecution
}: InteractiveFinancialReviewProps) {
  const [mode, setMode] = useState<ReviewMode>("FULL");
  const groups = useMemo(() => groupFinancialReview(review), [review]);
  const exceptions = useMemo(() => exceptionReviewChecks(review), [review]);
  const focused = requestedSelector === null ? null : resolveExactReviewCheck(review, requestedSelector);
  const requestedInvalid = requestedSelector !== null && focused === null;
  const checkRefs = useRef(new Map<string, HTMLElement>());

  useEffect(() => {
    if (focused === null) return;
    setMode("FULL");
    const key = reviewSelectorKey(focused.selector);
    if (key === null) return;
    const timer = window.setTimeout(() => checkRefs.current.get(key)?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
    return () => window.clearTimeout(timer);
  }, [focused]);

  return <div
    className={`financial-review ${context === "run" ? "run-financial-review" : ""}`}
    data-testid="interactive-financial-review"
    data-review-id={review.reviewId}
    data-review-check-count={review.checks.length}
    data-review-group-count={groups.length}
  >
    <section className="review-summary" aria-label="财务复核摘要">
      <div className="review-verdict-mark" aria-hidden="true">{review.verdict === "PASS" ? "✓" : "!"}</div>
      <div className="review-summary-copy"><span>REVIEW VERDICT</span><h3>{review.verdict === "PASS" ? "复核通过" : verdictLabel(review.verdict)}</h3><p>本视图直接呈现同一 Research Run 的持久化 ReviewRecord 与 ReviewChecks，不使用演示步骤或推测关系。</p></div>
      <dl className="review-summary-facts"><div><dt>真实检查</dt><dd>{review.checks.length}</dd></div><div><dt>业务分组</dt><dd>{groups.length}</dd></div><div><dt>需处理</dt><dd>{exceptions.length}</dd></div></dl>
    </section>

    <div className="review-toolbar" role="tablist" aria-label="复核查看模式">
      <button type="button" role="tab" aria-selected={mode === "FULL"} className={mode === "FULL" ? "active" : ""} data-testid="review-mode-full" onClick={() => setMode("FULL")}><strong>完整复核</strong><small>{review.checks.length} 项真实检查</small></button>
      <button type="button" role="tab" aria-selected={mode === "EXCEPTIONS"} className={mode === "EXCEPTIONS" ? "active" : ""} data-testid="review-mode-exceptions" onClick={() => setMode("EXCEPTIONS")}><strong>异常筛选</strong><small>{exceptions.length} 项需处理</small></button>
    </div>

    {requestedInvalid && <div className="review-focus-invalid" role="alert" data-testid="review-focus-invalid">请求的 scoped selector 与此 Review 不匹配；未使用近似检查或首项回退。</div>}

    {mode === "EXCEPTIONS" ? <section className="review-exception-empty" data-testid="review-exception-state" aria-live="polite">
      {exceptions.length === 0 ? <><span className="review-empty-mark">✓</span><div><h4>当前没有可操作异常</h4><p>{review.checks.length} 项真实检查均为 PASS；ReviewCheck 未观察到可归属的 correction 或 replan 关系，因此这里不会伪造异常事件。</p></div></> : <div className="review-groups">{renderGroups(groupFinancialReview({ ...review, checks: exceptions }), focused, checkRefs, returnAnchor, onOpenReport, onOpenExecution)}</div>}
    </section> : <div className="review-groups" data-testid="review-full-content">
      {renderGroups(groups, focused, checkRefs, returnAnchor, onOpenReport, onOpenExecution)}
    </div>}

    <footer className="review-observability-note"><strong>可观察边界</strong><span>“复核逻辑”是公开检查语义，不是隐藏推理或 Chain-of-Thought。只有 output_refs 中 AVAILABLE 的精确目标才可进入机器记录。</span></footer>
  </div>;
}

function renderGroups(
  groups: ReturnType<typeof groupFinancialReview>,
  focused: FinancialReviewCheckV1 | null,
  checkRefs: { current: Map<string, HTMLElement> },
  returnAnchor: string | null,
  onOpenReport: InteractiveFinancialReviewProps["onOpenReport"],
  onOpenExecution: InteractiveFinancialReviewProps["onOpenExecution"]
) {
  return groups.map((group, groupIndex) => {
    const containsFocus = focused !== null && group.checks.includes(focused);
    const groupStatus = group.blockCount > 0 ? "BLOCK" : group.reviewCount > 0 ? "REVIEW" : "PASS";
    return <details className="review-group" key={group.groupKey} open={containsFocus || groupIndex === 0}>
      <summary><span className="review-group-number">{String(groupIndex + 1).padStart(2, "0")}</span><span className="review-group-title"><strong>{group.groupTitle}</strong><small>{group.groupDescription}</small></span><span className="review-group-count">{group.checks.length} checks</span><span className={`badge ${verdictClass(groupStatus)}`}>{groupStatus}</span></summary>
      <div className="review-check-list">{group.checks.map((check, index) => <ReviewCheckCard
        key={reviewSelectorKey(check.selector) ?? `${check.selector.checkCode}-${index}`}
        check={check}
        index={index}
        focused={focused === check}
        register={(node) => {
          const key = reviewSelectorKey(check.selector);
          if (key === null) return;
          if (node === null) checkRefs.current.delete(key); else checkRefs.current.set(key, node);
        }}
        returnAnchor={focused === check ? returnAnchor : null}
        onOpenReport={onOpenReport}
        onOpenExecution={onOpenExecution}
      />)}</div>
    </details>;
  });
}

function ReviewCheckCard({ check, index, focused, register, returnAnchor, onOpenReport, onOpenExecution }: {
  readonly check: FinancialReviewCheckV1;
  readonly index: number;
  readonly focused: boolean;
  readonly register: (node: HTMLElement | null) => void;
  readonly returnAnchor: string | null;
  readonly onOpenReport: InteractiveFinancialReviewProps["onOpenReport"];
  readonly onOpenExecution: InteractiveFinancialReviewProps["onOpenExecution"];
}) {
  const presentation = checkPresentation(check.selector.checkCode);
  const availableInputs = check.inputRefs.filter((ref) => ref.status === "AVAILABLE").length;
  const hasMachineRelation = reviewHasObservableMachineRelation(check);
  return <article ref={register} className={`review-check ${focused ? "focused" : ""}`} data-testid={focused ? "review-exact-focus" : undefined} data-check-code={check.selector.checkCode}>
    <details open={focused || index === 0}>
      <summary><span className="review-check-index">{String(index + 1).padStart(2, "0")}</span><span><strong>{presentation.label}</strong><small>{check.selector.checkCode}</small></span><span className={`badge ${verdictClass(check.status)}`}>{check.status}</span></summary>
      <div className="review-iprv">
        <section><span>输入 · INPUT</span><div className="review-subjects">{check.selector.subjectRefs.map((ref) => <code key={ref}><b>{subjectKind(ref)}</b>{ref}</code>)}</div></section>
        <section><span>复核逻辑 · PROCESS</span><p>{presentation.logic}</p>{check.safeExplanation && <p className="review-safe-explanation">公开说明：{check.safeExplanation}</p>}</section>
        <section><span>结果 · RESULT</span><p>观察到 {availableInputs}/{check.inputRefs.length} 个权威输入关系可用；{check.outputRefs.length === 0 ? "此检查未声明输出关系。" : `记录了 ${check.outputRefs.length} 个输出关系。`}</p></section>
        <section className="review-verdict"><span>复核结论 · VERDICT</span><strong className={`state-${check.status === "PASS" ? "green" : check.status === "REVIEW" ? "amber" : "red"}`}>{check.status} · {verdictLabel(check.status)}</strong></section>
      </div>
      <div className="review-check-actions">
        {returnAnchor !== null && onOpenReport && <button type="button" className="btn sm" onClick={() => onOpenReport(returnAnchor)}>查看报告位置</button>}
        {hasMachineRelation && onOpenExecution
          ? <button type="button" className="btn sm" onClick={() => onOpenExecution(check)}>查看机器记录</button>
          : <span className="review-no-relation">机器记录：未观察到精确关联</span>}
      </div>
    </details>
  </article>;
}
