import type { ResearchObject } from "../types/domain";
import { RUN_STATUS_META } from "../state/status";
import "../styles/workspace-pages.css";

export function ResearchObjectsPage({ objects, onOpen, onCreate }: { objects: ResearchObject[]; onOpen: (object: ResearchObject) => void; onCreate: () => void }) {
  return <section className="workspace-page">
    <div className="page-head"><div><div className="breadcrumb">Research › 研究对象</div><h1 className="page-title">研究对象</h1><div className="page-sub">Research Object 是长期金融资产：持续沉淀最新状态、历史研究和版本化观点。</div></div><button className="btn primary" onClick={onCreate}>+ 创建研究对象</button></div>
    {objects.length === 0 ? <div className="card empty-state" role="status">尚无 Research Object。点击“创建研究对象”开始。</div> : <div className="object-list">{objects.map((object) => { const runMeta = object.latestRunStatus ? RUN_STATUS_META[object.latestRunStatus] : null; return <button className="card object-card" key={object.id} onClick={() => onOpen(object)}>
      <span className="object-card-head"><span><strong>{object.name}</strong><span className="small option-sub">{object.symbol} · {object.exchange} · {object.industry} · Data {object.dataStatus}</span></span><span className={`badge ${runMeta?.color ?? "amber"}`}>{runMeta?.label ?? "尚无研究"}</span></span>
      <span className="object-metrics"><Metric label="Price" value={object.price} /><Metric label="Revenue" value={object.revenue} /><Metric label="Forward P/E" value={object.forwardPe} /><Metric label="Research Runs" value={String(object.runCount)} /></span>
      <span className="object-card-action">打开研究对象 →</span>
    </button>; })}</div>}
  </section>;
}

function Metric({ label, value }: { label: string; value?: string }) { return <span><span className="om-label">{label}</span><span className="om-value">{value ?? "—"}</span></span>; }
