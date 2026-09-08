import { useEffect, useState } from "react";
import type { Phase4FrontendDataSource } from "../../data/FrontendDataSource";
import type { RecoveryRow } from "../../types/recovery";

const profiles: Record<string, string> = { fundamental_analysis: "Fundamental Analyst", peer_analysis: "Peer Analyst", research_news_analysis: "Research & News Analyst", valuation_analysis: "Valuation Analyst", risk_analysis: "Risk Analyst", risk_follow_up: "Risk Follow-up", report_synthesis: "Research Lead" };
const actions: Record<string, string> = { SWITCH_PROVIDER: "切换供应商", SWITCH_MODEL: "切换模型", CAPABILITY_CHECK: "能力检查", RETRY_SAME_ROUTE: "重试当前路由", WAIT_AND_RETRY: "等待后重试", FAIL_TASK: "停止 Task", FAIL_RUN: "停止 Run", REPLAN_TASK: "申请重新规划", CORRECT_RESEARCH_PATH: "申请研究修正" };

export function RecoveryTimeline({ rows }: { rows: readonly RecoveryRow[] }) {
  const tasks = [...new Set(rows.map(r => r.taskId))];
  return <section className="runtime-recovery" aria-label="同 Run 运行恢复">
    <h3>同 Run 运行恢复</h3>
    <p>原 Task / Run 身份保持不变。Main Agent 提议，Policy Gate 审核；以下只读记录不触发重试，也不展示私有推理。</p>
    {tasks.length === 0 ? <p>此 Run 未记录恢复决策；不补造历史尝试。</p> : tasks.map(taskId => {
      const records = rows.filter(r => r.taskId === taskId);
      return <article key={taskId}><h4>{profiles[records[0].profile]}</h4><code>{taskId}</code>
        <ol>{records.map(r => <li key={r.id}>
          <strong>{r.kind === "DECISION" ? `Recovery Decision · ${actions[r.action ?? ""] ?? "未提供动作"}` : r.kind === "TERMINAL" ? "恢复终止" : `${r.check ? "能力检查" : "执行尝试"} #${r.attempt} · ${r.kind === "ATTEMPT_STARTED" ? "开始" : "完成"}`}</strong>
          <span>{r.route ?? "无目标路由"}{r.model ? ` / ${r.model}` : ""} · {r.kind === "DECISION" ? "Policy Gate: " : ""}{r.outcome}{r.failure ? ` · ${r.failure}` : ""}{r.reason !== "OBSERVED" ? ` · ${r.reason}` : ""}{r.latencyMs !== null ? ` · ${(r.latencyMs / 1000).toFixed(2)}s` : ""}</span>
          <small>{r.id}</small>
          {r.actualModel && <span>Preferred Model: {r.preferredModel ?? "历史记录未提供"} · Actual Model: {r.actualModel} · {r.routing === "MODEL_EXECUTION_SUBSTITUTED" ? "受控动态模型替换" : r.routing ?? "历史精确模型记录"} · Policy: {r.policyGate ?? "历史记录未提供"}</span>}
        </li>)}</ol>
      </article>;
    })}
  </section>;
}

export function RuntimeRecoveryEvidence({ source, runId, objectId }: { source: Phase4FrontendDataSource; runId: string; objectId: string }) {
  const [state, setState] = useState<{ key: string; rows: readonly RecoveryRow[] | null; failed: boolean } | null>(null);
  const key = `${runId}/${objectId}`;
  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setState(null);
    if (!source.getRecoveryEvidence) { setState({ key, rows: null, failed: true }); return; }
    source.getRecoveryEvidence(runId, objectId, { signal: controller.signal })
      .then(rows => { if (current) setState({ key, rows, failed: false }); })
      .catch(() => { if (current) setState({ key, rows: null, failed: true }); });
    return () => { current = false; controller.abort(); };
  }, [source, runId, objectId, key]);
  if (!state || state.key !== key) return <p role="status">正在读取此 Run 的恢复证据…</p>;
  if (state.failed || !state.rows) return <p role="status">此 Run 的恢复证据暂不可用；未使用其他 Run 的数据。</p>;
  return <RecoveryTimeline rows={state.rows} />;
}
