export type Selector = {review_id:string; check_code:string; subject_refs:string[]};
export type SemanticCheck = {selector:Selector;status:string;comparison:{field:string;expected:string|null;actual:string|null}[];execution_refs:string[]};
export type SemanticBlock = {claim_id:string;metric_id:string;title:string;statement:string;calculation_id:string;evidence_refs:string[];review_selectors:Selector[];execution_refs:string[]};
export type SemanticRecord = {ref:string;category:string;label:string;status:string;input_refs:string[];process:string;output:string;report_claim_refs:string[]};
export type Recovery = {attempt_id:string;original_terminal_state:string;failure_stage:string;authorized_by:string;resume_from:string;reused_artifacts:string[];reexecuted_stages:string[];new_model_calls:number;new_calculations:number;new_proof_calls:number;final_state:string;memory_status:string};
export type SemanticPackage = {schema_version:string;run_id:string;object_id:string;company_name:string;symbol:string;as_of:string;result_id:string;review_id:string;review_status:string;publication:string;limitations:string[];blocks:SemanticBlock[];checks:SemanticCheck[];records:SemanticRecord[];categories:string[];recovery:Recovery|null;memory_refs:string[];html_artifact_id:string;legacy_export:boolean};

export const selectorKey=(s:Selector)=>JSON.stringify([s.review_id,s.check_code,[...s.subject_refs].sort()]);
const fail=():never=>{throw new Error("Exact Results semantic integrity failure");};
const string=(x:unknown):x is string=>typeof x==="string";
const strings=(x:unknown):x is string[]=>Array.isArray(x)&&x.every(string);
const object=(x:unknown):x is Record<string,unknown>=>x!==null&&typeof x==="object"&&!Array.isArray(x);
function selector(x:unknown):x is Selector {return object(x)&&string(x.review_id)&&string(x.check_code)&&strings(x.subject_refs)&&new Set(x.subject_refs).size===x.subject_refs.length;}
export function decodeSemanticPackage(raw:unknown,runId:string):SemanticPackage {
  if(!object(raw)||raw.schema_version!=="phase6a-results-semantics/v1"||raw.run_id!==runId)fail();
  const o=raw as Record<string,unknown>;
  for(const key of ["object_id","company_name","symbol","as_of","result_id","review_id","review_status","publication","html_artifact_id"])if(!string(o[key]))fail();
  for(const key of ["limitations","categories","memory_refs"])if(!strings(o[key]))fail();
  if(!["RELEASED","RELEASED_WITH_LIMITATIONS"].includes(o.publication as string)||typeof o.legacy_export!=="boolean")fail();
  for(const key of ["blocks","checks","records"])if(!Array.isArray(o[key])||(o[key] as unknown[]).length>20000)fail();
  const p=o as unknown as SemanticPackage;
  const known=new Set<string>();
  for(const r of p.records){
    if(!object(r)||![r.ref,r.category,r.label,r.status,r.process,r.output].every(string)||!strings(r.input_refs)||!strings(r.report_claim_refs)||known.has(r.ref)||!p.categories.includes(r.category))fail();known.add(r.ref);
  }
  const selectors=new Set<string>();
  const passed=new Set<string>();
  for(const c of p.checks){
    if(!object(c)||!selector(c.selector)||c.selector.review_id!==p.review_id||!["PASS","REVIEW","BLOCK"].includes(c.status)||!strings(c.execution_refs)||!Array.isArray(c.comparison))fail();
    if(selectors.has(selectorKey(c.selector)))fail();selectors.add(selectorKey(c.selector));
    if(c.status==="PASS")passed.add(selectorKey(c.selector));
    if(c.execution_refs.some(r=>!known.has(r)))fail();
    for(const pair of c.comparison)if(!object(pair)||!string(pair.field)||(pair.expected!==null&&!string(pair.expected))||(pair.actual!==null&&!string(pair.actual)))fail();
  }
  const claims=new Set<string>();
  for(const b of p.blocks){
    if(!object(b)||![b.claim_id,b.metric_id,b.title,b.statement,b.calculation_id].every(string)||!strings(b.evidence_refs)||!strings(b.execution_refs)||!Array.isArray(b.review_selectors)||!b.review_selectors.length)fail();
    if(claims.has(b.claim_id)||!known.has(b.calculation_id)||[...b.evidence_refs,...b.execution_refs].some(r=>!known.has(r)))fail();claims.add(b.claim_id);
    if(b.review_selectors.some(s=>!selector(s)||!passed.has(selectorKey(s))))fail();
  }
  for(const r of p.records)if(r.input_refs.some(ref=>!known.has(ref))||r.report_claim_refs.some(ref=>!claims.has(ref)))fail();
  if(p.memory_refs.some(r=>!known.has(r)))fail();
  if(p.recovery!==null){const r=p.recovery;
    if(!object(r)||![r.attempt_id,r.original_terminal_state,r.failure_stage,r.authorized_by,r.resume_from,r.final_state,r.memory_status].every(string)||!strings(r.reused_artifacts)||!strings(r.reexecuted_stages))fail();
    if(r.original_terminal_state!=="FAILED"||r.authorized_by!=="OWNER"||r.resume_from!=="Release"||r.reused_artifacts.some(ref=>!known.has(ref)))fail();
    for(const v of [r.new_model_calls,r.new_calculations,r.new_proof_calls])if(!Number.isSafeInteger(v)||v<0)fail();
  }
  return p;
}
