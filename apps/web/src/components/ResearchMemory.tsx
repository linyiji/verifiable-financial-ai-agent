import type {ResearchMemorySnapshot} from "../types/researchMemory";

export function ResearchMemory({memory, unavailable, onOpenSource}: {
  readonly memory: ResearchMemorySnapshot | null;
  readonly unavailable: boolean;
  readonly onOpenSource: (runId: string, anchor: string | null) => void;
}) {
  const view=memory?.current_view;
  if (!memory) return <section className="card pad" data-testid="research-memory-loading"><h2>Research Memory</h2><p>{unavailable ? "研究记忆暂不可用；不会推测其他 Run 的研究资产。" : "正在读取持久化研究资产…"}</p></section>;
  if (!view) return <section className="card pad" data-testid="research-memory-empty"><h2>Current Research View</h2><p>尚未建立研究记忆。历史研究仍保留在“研究记录”中；当前视图不会按日期自动选取。</p></section>;
  const names={VERIFIED_METRIC:"Verified Metrics · 已验证指标",VERIFIED_CLAIM:"Verified Claims · 已验证结论",RESOLVED_ISSUE:"Resolved Issues · 已解决问题"};
  return <>
    <section className="card pad memory-current" data-testid="current-research-view" data-source-run-id={view.source_run_id} data-view-version={view.research_view_version_id} data-object-version={memory.object_version?.object_version_id}>
      <div className="section-heading"><div><div className="small">DURABLE RESEARCH ASSET</div><h2>Current Research View</h2></div><span className="badge green">View v{view.research_view_version}</span></div>
      <p className="memory-summary">{view.summary ?? "当前没有可展示的已验证研究结论。"}</p>
      <div className="small">As-of {view.as_of} · Object v{view.research_object_version} · 持久化研究资产</div>
      <div className="memory-provenance"><span>明确绑定的已发布 Run</span><code data-testid="object-latest-released-run">{memory.latest_released_run_id}</code><button type="button" className="btn primary sm" onClick={()=>onOpenSource(view.source_run_id,null)}>打开原始研究结果 →</button></div>
      <details><summary>版本与来源身份</summary><dl className="detail-grid"><div><dt>Object version</dt><dd>{memory.object_version?.object_version_id}</dd></div><div><dt>View version</dt><dd>{view.research_view_version_id}</dd></div><div><dt>Released Result</dt><dd>{view.source_released_result_id}</dd></div><div><dt>Canonical Record</dt><dd>{view.source_canonical_record_id}</dd></div></dl></details>
    </section>
    <section className="card pad research-memory" data-testid="research-memory">
      <h2>Research Memory</h2><p className="small">保留权威研究材料及其精确来源。已发布不等于已证明；此处只把 proof VERIFIED 的指标及其结论列为已验证。</p>
      {(Object.keys(names) as Array<keyof typeof names>).map(category=><section className="memory-category" key={category}><h3>{names[category]} <span className="badge neutral">{view.items.filter(i=>i.category===category).length}</span></h3>
        {view.items.filter(i=>i.category===category).map(item=><article className="memory-item" key={item.memory_item_id} data-testid="memory-item" data-memory-item-id={item.memory_item_id} data-source-run-id={item.source_run_id}>
          <div><strong>{item.title}</strong><p>{item.statement}</p><code>{item.reference_id}</code></div>
          <button type="button" className="btn ghost sm" data-testid="memory-source-link" onClick={()=>onOpenSource(item.source_run_id,item.report_anchor)}>查看原始来源 →</button>
        </article>)}
        {!view.items.some(i=>i.category===category)&&<p className="small">NOT_OBSERVED · 未保留可验证的权威材料。</p>}
      </section>)}
      <footer className="small">Peer / Path / Reusable Context：NOT_OBSERVED · 未纳入此版本。记忆不会自动复用证据或发起增量研究。</footer>
    </section>
  </>;
}
