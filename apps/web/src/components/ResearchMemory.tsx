import type {ResearchMemorySnapshot} from "../types/researchMemory";
import {IncrementalContext} from "./IncrementalContext";

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
      <footer className="small">Peer / Path / Reusable Context：NOT_OBSERVED · 未纳入此版本。新研究可使用精确历史出处作为计划背景，不自动复制证据。</footer>
    </section>
    {memory.base_memory?.current_view && memory.incremental_context && <section className="card pad" data-testid="base-vs-current" data-base-run-id={memory.base_memory.current_view.source_run_id} data-current-run-id={view.source_run_id}>
      <h2>本次变化 · 历史研究与当前研究</h2>
      <p>View v{memory.base_memory.current_view.research_view_version} → View v{view.research_view_version}。按公式、期间、单位与结论类型比较；没有精确逻辑键的问题仅列为历史保留或本次新增。</p>
      <div data-testid="comparison-changes">{memory.changes?.map((c,index)=><p key={index} data-testid="governed-change" data-change={c.change} data-category={c.category}>{names[c.category]}：{({UNCHANGED:"数值未变 · 本次独立验证",UPDATED:"已更新",REVALIDATED:"已重新验证",NEW:"本次新增",REMOVED_FROM_CURRENT_VIEW:"仅保留在历史视图"})[c.change]}</p>)}</div>
      <div className="detail-grid">{[memory.base_memory.current_view,view].map((v,index)=><div key={v.research_view_version_id}>
        <h3>{index===0 ? "上次研究" : "当前研究"} · v{v.research_view_version}</h3><p>{v.summary ?? "未观察到已验证摘要"}</p>
        <button className="btn primary sm" data-testid={index===0?"comparison-base-source":"comparison-current-source"} onClick={()=>onOpenSource(v.source_run_id,null)}>打开{index===0?"历史":"本次"}研究结果 →</button>
        {v.items.map(i=><article className="memory-item" key={i.memory_item_id} data-testid="comparison-item" data-source-run-id={i.source_run_id}>
          <div><strong>{names[i.category]}</strong><p>{i.statement}</p><span className="small">{index===0?"仅保留在历史视图，不视为本次产出":"本次独立生成"}</span><button className="btn ghost sm" onClick={()=>onOpenSource(i.source_run_id,i.report_anchor)}>查看精确来源</button></div>
        </article>)}
      </div>)}</div>
      <IncrementalContext context={memory.incremental_context}/>
    </section>}
  </>;
}
