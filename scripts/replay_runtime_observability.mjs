/** Read-only retained Run replay. Derived pre-release snapshot is explicit, never native T0. */
import {writeFile, mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
import {createServer} from '../apps/web/node_modules/vite/dist/node/index.js';
import {installBrowserRuntimeObserver} from './browser_runtime_observer.mjs';

const RUN = 'RUN-645b12e5-12a1-4a50-8446-684c1c8b9cfc';
const output = resolve(process.argv[2] ?? 'artifacts/runtime_observability_enhancement/v2');
await mkdir(output, {recursive: true});
const headers = {'X-Phase4-Contract-Version': 'phase4-core/v1'};
const endpoint = `http://127.0.0.1:8010/api/research-runs/${RUN}/projection`;
const terminal = await (await fetch(endpoint, {headers})).json();
let reconstructed;
try { reconstructed = JSON.parse(execFileSync('.venv/bin/python', ['scripts/reconstruct_observability_projection.py'], {env: {...process.env, PYTHONPATH: '.'}, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024})); }
catch { throw Error('Read-only projection reconstruction failed; raw child output suppressed'); }
const before = reconstructed.initial, review = reconstructed.review;
const replayResponse = await fetch(endpoint.replace('/projection', '/events'), {headers: {...headers, 'Last-Event-ID': '606'}});
const frames = (await replayResponse.text()).split(/\r?\n\r?\n/).filter(f => f.includes('data:'));
const receipts = frames.map(f => JSON.parse(f.split(/\r?\n/).find(l => l.startsWith('data:')).slice(5)));
const slice = frames.filter((_, i) => receipts[i].sequence <= 609).join('\n\n') + '\n\n';
const replayHeaders = Object.fromEntries([...replayResponse.headers].filter(([k]) => k.toLowerCase().startsWith('x-phase4') || k.toLowerCase() === 'content-type'));
const resumeResponse = await fetch(endpoint.replace('/projection', '/events'), {headers: {...headers, 'Last-Event-ID': '609'}});
const resumed = (await resumeResponse.text()).split(/\r?\n\r?\n/).filter(f=>f.includes('data:')).map(f=>JSON.parse(f.split(/\r?\n/).find(l=>l.startsWith('data:')).slice(5)));

const vite = await createServer({root: resolve('apps/web'), server: {middlewareMode: true}, appType: 'custom'});
let pure, canonicalCheck;
try {
  const {decodeRunProjection} = await vite.ssrLoadModule('/src/types/domain.ts');
  const {createRunRuntimeState, reconcileRunRuntimeState} = await vite.ssrLoadModule('/src/state/runtimeEventReducer.ts');
  const first = decodeRunProjection(before, RUN), last = decodeRunProjection(terminal, RUN);
  try { decodeRunProjection(review, RUN); pure = 'ACCEPTED'; }
  catch (e) { pure = e.name === 'ContractDecodeError' && e.path === '$.lifecycle.progress' ? 'RUN_PROGRESS_CONTRACT' : 'OTHER_REJECTION'; }
  const state = createRunRuntimeState(first, {runId: RUN, objectId: first.object.objectId, goalId: first.goal.goalId, schemeId: first.confirmedScheme.schemeId, plannedGraphId: first.plannedGraph.graphId, actualGraphId: first.actualGraph?.graphId ?? null, canonicalRecordId: first.execution.canonicalRecordId});
  try { reconcileRunRuntimeState(state, last); canonicalCheck = 'ACCEPTED'; }
  catch (e) { canonicalCheck = e.name === 'RuntimeProjectionError' && e.message === 'projection unexpectedly exposes a canonical record' ? 'CANONICAL_RECORD_APPEARED' : 'OTHER_REJECTION'; }
} finally { await vite.close(); }

const target = (await (await fetch('http://127.0.0.1:9227/json/list')).json()).find(t => t.type === 'page');
const ws = new WebSocket(target.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
let seq = 0; const jobs = new Map();
ws.onmessage = ({data}) => { const m = JSON.parse(data); const job = jobs.get(m.id); if (job) { jobs.delete(m.id); m.error ? job.reject(Error(m.error.message)) : job.resolve(m.result); } };
const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++seq; jobs.set(id, {resolve, reject}); ws.send(JSON.stringify({id, method, params})); });
const ev = async expression => { const r = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true}); if (r.exceptionDetails) throw Error('Evaluation failed'); return r.result.value; };
const wait = async predicate => { for (let n = 0; n < 300; n++) { if (await ev(predicate)) return; await new Promise(r => setTimeout(r, 100)); } throw Error('Replay condition not met'); };
const click = async selector => { const p = await ev(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`); await send('Input.dispatchMouseEvent', {type:'mousePressed', ...p, button:'left', clickCount:1}); await send('Input.dispatchMouseEvent', {type:'mouseReleased', ...p, button:'left', clickCount:1}); };
let result, installed;
try {
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width:1440, height:1100, deviceScaleFactor:1, mobile:false});
  // Two production-builder reconstructed projections, then the actual retained terminal response.
  // Deliver retained events 607..609 without changing payloads; hold at the failure boundary until unsubscribe.
  const replay = `(()=>{let streaming=false,recovering=false;document.addEventListener('click',e=>{if(e.target.closest?.('[data-testid="error-retry"]'))recovering=true;},true);const original=window.fetch.bind(window);window.fetch=async(...args)=>{const url=typeof args[0]==='string'?args[0]:args[0]?.url??'';if(url.endsWith('/api/research-runs/${RUN}/projection')&&!recovering){const p=streaming?${JSON.stringify(review)}:${JSON.stringify(before)};return new Response(JSON.stringify(p),{status:200,headers:{'Content-Type':'application/json; charset=utf-8','X-Phase4-Contract-Version':'phase4-core/v1','ETag':'"p4:${RUN}:'+p.projection_revision+':'+p.projection_sequence+'"'}});}if(url.endsWith('/api/research-runs/${RUN}/events')&&!recovering){streaming=true;return new Response(new ReadableStream({start(c){c.enqueue(new TextEncoder().encode(${JSON.stringify(slice)}));args[1]?.signal?.addEventListener('abort',()=>{try{c.error(new DOMException('Aborted','AbortError'))}catch{}});}}),{status:200,headers:${JSON.stringify(replayHeaders)}});}return original(...args);};})();`;
  installed = await send('Page.addScriptToEvaluateOnNewDocument', {source: replay + `(${installBrowserRuntimeObserver.toString()})(${JSON.stringify(RUN)});`});
  await send('Page.navigate', {url:`http://127.0.0.1:4173/runs/${RUN}?stage=research`});
  await wait(`!!document.querySelector('[data-testid="error-retry"]')`);
  await new Promise(r => setTimeout(r, 100));
  const failure = await ev('({browser:window.__vfaBrowserObservation,diagnostics:window.__vfaRuntimeDiagnostics})');
  await click('[data-testid="error-retry"]');
  await wait(`document.querySelector('[data-testid="run-workspace"]')?.dataset.runStatus==='RELEASED'`);
  await ev(`document.querySelector('[data-testid="open-results-workspace"]').scrollIntoView({block:'center'})`);
  await new Promise(r => setTimeout(r, 100));
  await click('[data-testid="open-results-workspace"]');
  await wait(`!!window.__vfaBrowserObservation.records.find(r=>r.kind==='useful_report_dom')`);
  result = {classification:'DERIVED_REPLAY_NOT_NATIVE_T0', run_id:RUN, initial_projection:'production-builder reconstruction at 606 then 609; not retained original HTTP responses', pure_decoder:pure, secondary_reconciliation:canonicalCheck, backend_replay:{http_status:replayResponse.status, sequences:receipts.map(e=>e.sequence), event_ids:receipts.map(e=>e.event_id)}, backend_resume:{http_status:resumeResponse.status, cursor:609, sequences:resumed.map(e=>e.sequence)}, failure, recovered:await ev('({browser:window.__vfaBrowserObservation,diagnostics:window.__vfaRuntimeDiagnostics})')};
  const diagnostics = failure.diagnostics.records, browser = failure.browser.records;
  const checks = {
    backend_stream:replayResponse.status===200 && receipts.map(e=>e.sequence).join(',')==='607,608,609,610,611,612,613,614,615,616',
    backend_resume:resumeResponse.status===200 && resumed.map(e=>e.sequence).join(',')==='610,611,612,613,614,615,616',
    exact_event_identity:receipts.every(e=>e.run_id===RUN) && resumed.every(e=>e.run_id===RUN),
    installed_initial:diagnostics.some(r=>r.kind==='projection_installed'&&r.sequence===606),
    browser_stream:diagnostics.filter(r=>r.kind==='sse_event').map(r=>r.sequence).join(',')==='607,608,609',
    decoder_boundary:diagnostics.some(r=>r.kind==='decode_failure'&&r.reason==='RUN_PROGRESS_CONTRACT'&&r.status===200),
    disappeared:browser.some(r=>r.kind==='workspace_disappeared'),
    error_onset:browser.some(r=>r.kind==='error_ui_onset'),
    recovery:result.recovered.diagnostics.records.some(r=>r.kind==='projection_installed'&&r.sequence===616),
    report_navigable:result.recovered.browser.records.some(r=>r.kind==='report_navigable'),
    useful_report:result.recovered.browser.records.some(r=>r.kind==='useful_report_dom'),
    no_drops:result.recovered.browser.dropped===0 && result.recovered.diagnostics.dropped===0
  };
  result.checks = checks;
  assert(Object.values(checks).every(Boolean),'Replay checks failed');
} finally {
  if (result) await writeFile(output+'/browser-measurement-v2.json', JSON.stringify(result,null,2)+'\n');
  if (installed) await send('Page.removeScriptToEvaluateOnNewDocument', {identifier:installed.identifier});
  ws.close();
}
console.log(JSON.stringify({pure_decoder:pure, secondary_reconciliation:canonicalCheck, checks:result?.checks}));
