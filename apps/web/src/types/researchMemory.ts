import {decodeArray, decodeEnum, decodeObject, decodeOpaqueId, decodePublicText, decodeRfc3339Utc, decodeSafeJsonObject} from "./domain";
import {decodeIncrementalContext, type IncrementalContext} from "./incremental";

export interface MemoryItem {
  readonly memory_item_id: string;
  readonly category: "VERIFIED_METRIC" | "VERIFIED_CLAIM" | "RESOLVED_ISSUE";
  readonly source_run_id: string;
  readonly reference_id: string;
  readonly title: string;
  readonly statement: string;
  readonly display_value: string | null;
  readonly display_unit: string | null;
  readonly calculation_id: string | null;
  readonly evidence_ids: readonly string[];
  readonly review_id: string;
  readonly report_id: string;
  readonly report_anchor: string | null;
  readonly task_id: string | null;
  readonly agent_output_id: string | null;
}
interface SourceIdentity {
  readonly schema_version: string;
  readonly research_object_id: string;
  readonly source_run_id: string;
  readonly source_released_result_id: string;
  readonly source_report_id: string;
  readonly source_canonical_record_id: string;
  readonly created_at: string;
}
export interface ResearchObjectVersion extends SourceIdentity {
  readonly object_version: number;
  readonly object_version_id: string;
}
export interface ResearchViewVersion extends SourceIdentity {
  readonly research_view_version: number;
  readonly research_view_version_id: string;
  readonly research_object_version: number;
  readonly as_of: string;
  readonly summary: string | null;
  readonly items: readonly MemoryItem[];
  readonly unavailable_categories: readonly ("PEER_CONTEXT" | "PATH_CONTEXT" | "REUSABLE_CONTEXT")[];
}
export interface MemoryHistoryRef {
  readonly research_object_id: string;
  readonly source_run_id: string;
  readonly status: "RELEASED";
  readonly as_of: string | null;
  readonly source_released_result_id: string | null;
  readonly research_view_version: number | null;
  readonly availability: "AVAILABLE" | "UNAVAILABLE_INCOMPATIBLE";
}
export interface ResearchMemorySnapshot {
  readonly changes?: readonly {readonly category: MemoryItem["category"];readonly change: "UNCHANGED"|"UPDATED"|"NEW"|"REMOVED_FROM_CURRENT_VIEW"|"REVALIDATED";readonly logical_key: string|null;readonly base_item_id: string|null;readonly current_item_id: string|null}[];
  readonly base_memory?: ResearchMemorySnapshot;
  readonly incremental_context?: IncrementalContext;
  readonly schema_version: "phase5a-memory/v1";
  readonly research_object_id: string;
  readonly latest_released_run_id: string | null;
  readonly latest_research_object_version: number | null;
  readonly latest_research_view_version: number | null;
  readonly object_version: ResearchObjectVersion | null;
  readonly current_view: ResearchViewVersion | null;
  readonly historical_released_runs: readonly MemoryHistoryRef[];
}

const require = (ok: boolean): void => { if (!ok) throw new Error("Research Memory contract mismatch"); };
const keys = (x: Record<string, unknown>, names: string[]) => require(Object.keys(x).length === names.length && names.every(n => Object.hasOwn(x,n)));
const positive = (x: unknown) => { require(typeof x === "number" && Number.isSafeInteger(x) && x > 0); };
const nullableId = (x: unknown) => { if(x !== null) decodeOpaqueId(x); };
const nullableNumber = (x: unknown) => { if(x !== null) positive(x); };
const common = ["schema_version","research_object_id","source_run_id","source_released_result_id","source_report_id","source_canonical_record_id","created_at"];
function source(value: unknown, objectId: string, runId: string) {
  const x=decodeObject(value);
  for(const name of common.filter(n=>n!=="created_at")) decodeOpaqueId(x[name]);
  decodeRfc3339Utc(x.created_at);require(x.research_object_id===objectId && x.source_run_id===runId);
  return x;
}
function frozen<T>(x:T):T { if(x && typeof x==="object") {for(const child of Object.values(x)) frozen(child);Object.freeze(x);}return x; }

export function decodeResearchMemory(value: unknown, expectedObjectId: string): ResearchMemorySnapshot {
  // Shared public safety boundary rejects secret/private keys and strings first.
  const x=decodeObject(decodeSafeJsonObject(value));
  const hasBase=Object.hasOwn(x,"base_memory");
  keys(x,["schema_version","research_object_id","latest_released_run_id","latest_research_object_version","latest_research_view_version","object_version","current_view","historical_released_runs",...(hasBase?["base_memory","incremental_context"]:[]),...(Object.hasOwn(x,"changes")?["changes"]:[])]);
  let base: ResearchMemorySnapshot | undefined;
  if(hasBase) {
    const rawBase=decodeObject(x.base_memory);require(!Object.hasOwn(rawBase,"base_memory"));
    base=decodeResearchMemory(rawBase,expectedObjectId);
    const context=decodeIncrementalContext(x.incremental_context,expectedObjectId);
    require(base.current_view!==null && base.latest_released_run_id===context.base_run_id && base.current_view.research_view_version_id===context.base_research_view_version && base.latest_released_run_id!==x.latest_released_run_id);
    require(x.latest_research_view_version===context.base_version_number+1 && base.latest_research_view_version===context.base_version_number);
    const identities=new Map(base.current_view!.items.map(i=>[i.memory_item_id,i]));
    for(const d of context.decisions) if(d.category!=="VIEW_CONTEXT") require(identities.get(d.source_identity)?.category===d.category);
  }
  require(x.schema_version==="phase5a-memory/v1" && x.research_object_id===expectedObjectId);
  decodeOpaqueId(x.research_object_id);nullableId(x.latest_released_run_id);
  nullableNumber(x.latest_research_object_version);nullableNumber(x.latest_research_view_version);
  const history=decodeArray(x.historical_released_runs).map(value=>{
    const h=decodeObject(value);keys(h,["research_object_id","source_run_id","status","as_of","source_released_result_id","research_view_version","availability"]);
    require(h.research_object_id===expectedObjectId && h.status==="RELEASED");decodeOpaqueId(h.source_run_id);
    nullableId(h.source_released_result_id);nullableNumber(h.research_view_version);
    if(h.as_of!==null) require(typeof h.as_of==="string" && /^\d{4}-\d{2}-\d{2}$/.test(h.as_of));
    decodeEnum(h.availability,["AVAILABLE","UNAVAILABLE_INCOMPATIBLE"]);
    require((h.availability==="AVAILABLE")===(h.source_released_result_id!==null));
    if(h.research_view_version!==null) require((h.source_run_id===x.latest_released_run_id && h.research_view_version===x.latest_research_view_version) || (base!==undefined && h.source_run_id===base.latest_released_run_id && h.research_view_version===base.latest_research_view_version));
    return h;
  });
  require(new Set(history.map(h=>h.source_run_id)).size===history.length);
  const pair=[x.latest_released_run_id,x.latest_research_object_version,x.latest_research_view_version,x.object_version,x.current_view];
  if(pair.some(v=>v===null)){require(pair.every(v=>v===null));return frozen(x as unknown as ResearchMemorySnapshot);}
  const runId=decodeOpaqueId(x.latest_released_run_id),obj=source(x.object_version,expectedObjectId,runId),view=source(x.current_view,expectedObjectId,runId);
  keys(obj,[...common,"object_version","object_version_id"]);keys(view,[...common,"research_view_version","research_view_version_id","research_object_version","as_of","summary","items","unavailable_categories"]);
  require(obj.schema_version==="phase5a-object-version/v1" && view.schema_version==="phase5a-view-version/v1");
  decodeOpaqueId(obj.object_version_id);decodeOpaqueId(view.research_view_version_id);
  positive(obj.object_version);positive(view.research_object_version);positive(view.research_view_version);
  require(obj.object_version===view.research_object_version && obj.object_version===x.latest_research_object_version && view.research_view_version===x.latest_research_view_version);
  for(const key of ["source_released_result_id","source_report_id","source_canonical_record_id"])require(obj[key]===view[key]);
  require(typeof view.as_of==="string" && /^\d{4}-\d{2}-\d{2}$/.test(view.as_of));if(view.summary!==null)decodePublicText(view.summary);
  const categories=decodeArray(view.unavailable_categories);categories.forEach(c=>decodeEnum(c,["PEER_CONTEXT","PATH_CONTEXT","REUSABLE_CONTEXT"]));require(new Set(categories).size===categories.length);
  const items=decodeArray(view.items).map(value=>{
    const i=decodeObject(value);keys(i,["memory_item_id","category","source_run_id","reference_id","title","statement","display_value","display_unit","calculation_id","evidence_ids","review_id","report_id","report_anchor","task_id","agent_output_id"]);
    for(const key of ["memory_item_id","source_run_id","reference_id","review_id","report_id"])decodeOpaqueId(i[key]);
    for(const key of ["title","statement"])decodePublicText(i[key]);
    for(const key of ["display_value","display_unit","calculation_id","report_anchor","task_id","agent_output_id"])nullableId(i[key]);
    decodeEnum(i.category,["VERIFIED_METRIC","VERIFIED_CLAIM","RESOLVED_ISSUE"]);decodeArray(i.evidence_ids).forEach(e=>decodeOpaqueId(e));
    require(i.source_run_id===runId && i.report_id===view.source_report_id);return i;
  });
  require(new Set(items.map(i=>i.memory_item_id)).size===items.length);
  if(base) {
    const baseItems=new Map(base.current_view!.items.map(i=>[i.memory_item_id,i]));
    const currentItems=new Map(items.map(i=>[i.memory_item_id,i]));
    const usedBase=new Set(),usedCurrent=new Set();
    for(const value of decodeArray(x.changes ?? [])) {
      const c=decodeObject(value);keys(c,["category","change","logical_key","base_item_id","current_item_id"]);
      decodeEnum(c.change,["UNCHANGED","UPDATED","NEW","REMOVED_FROM_CURRENT_VIEW","REVALIDATED"]);
      if(c.logical_key!==null) decodePublicText(c.logical_key);
      if(c.base_item_id!==null) {decodeOpaqueId(c.base_item_id);require(baseItems.get(String(c.base_item_id))?.category===c.category && !usedBase.has(c.base_item_id));usedBase.add(c.base_item_id);} else require(c.change==="NEW");
      if(c.current_item_id!==null) {decodeOpaqueId(c.current_item_id);require(currentItems.get(c.current_item_id)?.category===c.category && !usedCurrent.has(c.current_item_id));usedCurrent.add(c.current_item_id);} else require(c.change==="REMOVED_FROM_CURRENT_VIEW");
      if(c.base_item_id!==null && c.current_item_id!==null) require(c.logical_key!==null && !["NEW","REMOVED_FROM_CURRENT_VIEW"].includes(String(c.change)));
    }
    require(usedBase.size===baseItems.size && usedCurrent.size===currentItems.size);
  } else require(x.changes===undefined);
  return frozen(x as unknown as ResearchMemorySnapshot);
}
