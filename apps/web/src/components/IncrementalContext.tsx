import type {IncrementalContext as Context} from "../types/incremental";

export function IncrementalContext({context}: {readonly context: Context}) {
  const names={REUSE:"继续沿用",REFRESH:"需要更新",REVALIDATE:"重新验证",PREVENT:"避免重复问题",UNKNOWN:"尚未确定 · 不沿用"};
  return <section className="card pad" data-testid="incremental-context" data-base-run-id={context.base_run_id} data-base-view-id={context.base_research_view_version}>
    <h2>基于上次研究 · View v{context.base_version_number}</h2>
    <p>保留历史出处，生成全新独立研究。本次证据、计算、审核与报告均重新产生，不继承上次批准。</p>
    {context.decisions.map(d=><article key={`${d.decision}:${d.source_identity}`} data-testid="incremental-decision" data-decision={d.decision} data-source-run-id={d.source_run_id} className="memory-item">
      <div><h3>{names[d.decision]}</h3><p>{d.statement}</p><p className="small">{d.reason}</p><details><summary>历史出处</summary><code>{d.source_run_id} / {d.source_identity}</code></details></div>
    </article>)}
  </section>;
}
