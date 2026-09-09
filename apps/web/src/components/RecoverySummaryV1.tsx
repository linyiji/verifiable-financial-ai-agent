import type { RecoverySummaryV1 as Summary } from "../runtime/recoveryV1";

/** Unmounted by default: integration must provide an accepted, authenticated action. */
export function RecoverySummaryV1({ summary, authorize, pending = false }: {
  summary: Summary;
  authorize?: (summary: Summary) => Promise<void>;
  pending?: boolean;
}) {
  const allowed = summary.recoverable
    && summary.accepted_actions.includes("AUTHORIZE_FAILED_OPERATION") && authorize;
  return <section aria-label="恢复执行 / Recoverable execution">
    <h3>恢复执行 / Recoverable execution</h3>
    <p>原失败：{summary.original_failure ?? "未记录"} · 当前状态：{summary.status}</p>
    <p>Attempt {summary.attempt} · 调用 {summary.physical_calls_used}/{summary.physical_calls_limit}
      · 截止 {new Date(summary.deadline * 1000).toISOString()}</p>
    <p>范围：{summary.scope.join(", ")} · 已保存成果：{summary.reusable_output_refs.join(", ") || "无"}</p>
    {summary.denial_reason && <p role="status">不可恢复：{summary.denial_reason}</p>}
    {allowed && <button disabled={pending} onClick={() => { void authorize?.(summary); }}>
      授权本次失败操作恢复（不新建研究）
    </button>}
  </section>;
}
