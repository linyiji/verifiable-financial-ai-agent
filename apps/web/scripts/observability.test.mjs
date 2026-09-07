import assert from 'node:assert/strict';
import vm from 'node:vm';
import {createServer} from 'vite';
import {installBrowserRuntimeObserver} from '../../../scripts/browser_runtime_observer.mjs';

const run = 'RUN-TEST';
let count = 0;
const check = (value, label) => { assert.ok(value, label); count++; };
const vite = await createServer({root: new URL('../', import.meta.url).pathname, server:{middlewareMode:true}, appType:'custom'});
try {
  const {recordRuntimeDiagnostic: record, runtimeDiagnosticReason: reason, diagnosticRequest} = await vite.ssrLoadModule('/src/runtime/diagnostics.ts');
  const {Phase4ApiClient, Phase4ProtocolError, Phase4TransportError} = await vite.ssrLoadModule('/src/api/client.ts');
  const {ContractDecodeError} = await vite.ssrLoadModule('/src/types/domain.ts');
  globalThis.window = {__vfaRuntimeDiagnostics:{enabled:true, runId:run, records:[], dropped:0}};
  const store = window.__vfaRuntimeDiagnostics;
  record('http_end', run, {status:200, operation:'projection', prompt:'CANARY-PRIVATE', secret:'CANARY-KEY', sequence:NaN, reason:'CANARY-RESPONSE'});
  check(JSON.stringify(store.records).includes('projection') && !JSON.stringify(store.records).includes('CANARY'), 'allowlist rejects arbitrary content');
  record('http_end', 'RUN-OTHER', {status:200}); record('CANARY-OP', run);
  check(store.records.length === 1, 'exact Run and fixed kinds');
  store.enabled = false; record('http_end', run); check(store.records.length === 1, 'disabled no-op'); store.enabled = true;
  check(diagnosticRequest(`/api/research-runs/${run}/projection`).operation === 'projection' && diagnosticRequest(`/api/research-runs/${run}/projection?secret=CANARY`) === null, 'no query/header/URL logging');
  check(reason(new ContractDecodeError('$.lifecycle.progress', 'Run progress contradicts authoritative Tasks/status')) === 'RUN_PROGRESS_CONTRACT', 'owned decoder classification');
  check(reason(new Error('CANARY-PRIVATE')) === 'UNKNOWN', 'unknown error content never captured');
  const responseHeaders = {'Content-Type':'application/json; charset=utf-8', 'X-Phase4-Contract-Version':'phase4-core/v1'};
  const client = new Phase4ApiClient({fetch:async()=>new Response('{}',{status:200,headers:responseHeaders})});
  await assert.rejects(client.requestJson({method:'GET',path:`/api/research-runs/${run}/projection`,expectedStatuses:[200],decode:()=>{throw new ContractDecodeError('$.lifecycle.progress','Run progress contradicts authoritative Tasks/status');}}), Phase4ProtocolError);
  check(store.records.some(r=>r.kind==='http_end'&&r.status===200) && store.records.some(r=>r.kind==='decode_failure'&&r.reason==='RUN_PROGRESS_CONTRACT'), 'HTTP 200 is distinct from failed decode');
  const network = new Phase4ApiClient({fetch:async()=>{throw new Error('CANARY-SECRET');}});
  await assert.rejects(network.requestJson({method:'GET',path:`/api/research-runs/${run}/projection`,expectedStatuses:[200],decode:x=>x}), Phase4TransportError);
  check(store.records.some(r=>r.kind==='http_failure'&&r.reason==='NETWORK'), 'network classification preserves product exception');
  for(let n=0;n<5010;n++)record('http_end',run,{status:200});
  check(store.records.length===5000 && store.dropped>0, 'bounded diagnostics');
  check(!JSON.stringify(store).includes('CANARY'), 'no raw errors persisted');
} finally { delete globalThis.window; await vite.close(); }

let mutation, workspace = true, retry = false, networkFailure = false;
const element = {dataset:{runId:run}, getClientRects:()=>[{}], getBoundingClientRect:()=>({top:0,bottom:10,left:0,right:10})};
const originalFailure = new Error('CANARY-NETWORK');
const context = {
  performance, URL, Headers, Response, TextDecoder, innerHeight:1100, innerWidth:1440,
  location:{href:'http://localhost/runs/'+run,pathname:'/runs/'+run},
  getComputedStyle:()=>({visibility:'visible'}), requestAnimationFrame:cb=>cb(), addEventListener:()=>{},
  MutationObserver:class{constructor(cb){mutation=cb;}observe(){}},
  document:{addEventListener:()=>{},querySelector:s=>s.includes('run-workspace')?(workspace?element:null):s.includes('error-retry')?(retry?element:null):null},
  window:{fetch:async()=>{if(networkFailure)throw originalFailure;return new Response(`data: ${JSON.stringify({run_id:run,event_id:'EVT-TEST',sequence:609,payload:{secret:'CANARY-BODY'}})}\n\n`,{headers:{'Content-Type':'text/event-stream'}});}}
};
vm.runInNewContext(`(${installBrowserRuntimeObserver.toString()})('${run}')`,context);
mutation(); workspace=false; retry=true; mutation(); mutation();
let rows=context.window.__vfaBrowserObservation.records;
check(rows.filter(r=>r.kind==='error_ui_onset').length===1,'first error DOM onset only once');
check(rows.findIndex(r=>r.kind==='workspace_disappeared')<rows.findIndex(r=>r.kind==='error_ui_onset'),'workspace disappearance independently observed');
retry=false;workspace=true;mutation();check(rows.some(r=>r.kind==='error_ui_removed'),'recovery DOM onset');
await context.window.fetch(`http://localhost/api/research-runs/${run}/events`,{headers:{'Last-Event-ID':'608'}});
await new Promise(r=>setTimeout(r,20));
await context.window.fetch(`http://localhost/api/research-runs/${run}/events`,{headers:{'Last-Event-ID':'609'}});
await new Promise(r=>setTimeout(r,20));
check(rows.filter(r=>r.kind==='sse_closed').length===2,'stream EOF captured');
check(rows.some(r=>r.kind==='sse_open_request'&&r.connection===2&&r.cursor===609),'new connection and resume cursor captured');
check(rows.some(r=>r.kind==='sse_receipt'&&r.event_id==='EVT-TEST'&&r.sequence===609),'exact event receipt identity');
networkFailure=true;
await assert.rejects(context.window.fetch(`http://localhost/api/research-runs/${run}/events`),e=>e===originalFailure);
check(rows.some(r=>r.kind==='sse_fetch_failure'),'original network failure rethrown unchanged');
check(!JSON.stringify(rows).includes('CANARY'),'observer excludes payloads and exception text');
context.location.pathname='/runs/RUN-OTHER';retry=true;mutation();
check(rows.filter(r=>r.kind==='error_ui_onset').length===1,'foreign route cannot create exact-Run error');
console.log(`${count} observability assertions PASS`);
