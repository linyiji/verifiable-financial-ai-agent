/** Retained exact-Run journey; no provider run, retry click, or runtime reset. */
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createServer} from '../apps/web/node_modules/vite/dist/node/index.js';
import {installBrowserRuntimeObserver} from './browser_runtime_observer.mjs';
const RUN='RUN-645b12e5-12a1-4a50-8446-684c1c8b9cfc';
const output=resolve('artifacts/product_contract_repair_1'); await mkdir(output,{recursive:true});
const headers={'X-Phase4-Contract-Version':'phase4-core/v1'};
const endpoint=`http://127.0.0.1:8010/api/research-runs/${RUN}`;
const terminal=await(await fetch(endpoint+'/projection',{headers})).json();
let reconstructed;
try {reconstructed=JSON.parse(execFileSync('.venv/bin/python',['scripts/reconstruct_observability_projection.py'],{env:{...process.env,PYTHONPATH:'.'},encoding:'utf8',maxBuffer:16*1024*1024}));}
catch{throw Error('Retained reconstruction failed; child output suppressed');}
const snapshots={...reconstructed.intermediate,606:reconstructed.initial,609:reconstructed.review,612:reconstructed.proof,614:reconstructed.verified,616:terminal};
const stream=await fetch(endpoint+'/events',{headers:{...headers,'Last-Event-ID':'606'}});
const frames=(await stream.text()).split(/\r?\n\r?\n/).filter(f=>f.includes('data:'));
const events=frames.map(f=>JSON.parse(f.split(/\r?\n/).find(l=>l.startsWith('data:')).slice(5)));
assert.equal(events.map(e=>e.sequence).join(','),'607,608,609,610,611,612,613,614,615,616');
const chunks={};
// Each post-review lifecycle event requests a projection and cancels the old
// stream. Advance only to that event so reconnect consumes every retained frame.
for(const [from,to] of [[606,609],...[609,610,611,612,613,614,615].map(n=>[n,n+1])])chunks[from]={to,body:frames.filter((_,i)=>events[i].sequence>from&&events[i].sequence<=to).join('\n\n')+'\n\n'};
const streamHeaders=Object.fromEntries([...stream.headers].filter(([k])=>k.startsWith('x-phase4')||k==='content-type'));
const vite=await createServer({root:resolve('apps/web'),server:{middlewareMode:true},appType:'custom'});
try {
  const {decodeRunProjection}=await vite.ssrLoadModule('/src/types/domain.ts');
  const {createRunRuntimeState,reconcileRunRuntimeState}=await vite.ssrLoadModule('/src/state/runtimeEventReducer.ts');
  let state=createRunRuntimeState(decodeRunProjection(snapshots[606],RUN),{runId:RUN,canonicalRecordId:null});
  for(const cursor of [609,612,614,616])state=reconcileRunRuntimeState(state,decodeRunProjection(snapshots[cursor],RUN));
  assert.equal(state.identity.canonicalRecordId,terminal.execution.canonical_record_id);
}finally{await vite.close();}
const target=(await(await fetch('http://127.0.0.1:9227/json/list')).json()).find(t=>t.type==='page');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
let seq=0;const jobs=new Map();
ws.onmessage=({data})=>{const m=JSON.parse(data),j=jobs.get(m.id);if(j){jobs.delete(m.id);m.error?j.reject(Error(m.error.message)):j.resolve(m.result);}};
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;jobs.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
const ev=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error('Browser evaluation failed');return r.result.value;};
const wait=async expression=>{for(let i=0;i<300;i++){if(await ev(expression))return;await new Promise(r=>setTimeout(r,100));}throw Error('Acceptance condition not met');};
const click=async selector=>{const p=await ev(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',clickCount:1});};
let installed,result;
try{
  await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  const replay=`(()=>{let phase=606;const snapshots=${JSON.stringify(snapshots)},chunks=${JSON.stringify(chunks)};const original=window.fetch.bind(window);window.fetch=async(...args)=>{const raw=typeof args[0]==='string'?args[0]:args[0]?.url??'';if(raw.endsWith('/api/research-runs/${RUN}/projection')){const p=snapshots[phase];return new Response(JSON.stringify(p),{status:200,headers:{'Content-Type':'application/json; charset=utf-8','X-Phase4-Contract-Version':'phase4-core/v1','ETag':'"p4:${RUN}:'+p.projection_revision+':'+p.projection_sequence+'"'}});}if(raw.endsWith('/api/research-runs/${RUN}/events')){const cursor=Number(new Headers(args[1]?.headers).get('Last-Event-ID'));const chunk=chunks[cursor];if(!chunk)throw Error('Unexpected replay cursor');return new Response(new ReadableStream({start(c){const release=()=>{phase=chunk.to;c.enqueue(new TextEncoder().encode(chunk.body));};if(cursor===606)window.__startRetainedReplay=release;else release();args[1]?.signal?.addEventListener('abort',()=>{try{c.error(new DOMException('Aborted','AbortError'))}catch{}});}}),{status:200,headers:${JSON.stringify(streamHeaders)}});}return original(...args);};})();`;
  installed=await send('Page.addScriptToEvaluateOnNewDocument',{source:replay+`(${installBrowserRuntimeObserver.toString()})(${JSON.stringify(RUN)});`});
  await send('Page.navigate',{url:`http://127.0.0.1:4173/runs/${RUN}?stage=research`});
  await wait(`!!document.querySelector('[data-testid="run-workspace"]')&&typeof window.__startRetainedReplay==='function'`);
  await ev(`window.__mountedRunWorkspace=document.querySelector('[data-testid="run-workspace"]');window.__startRetainedReplay()`);
  await wait(`document.querySelector('[data-testid="run-workspace"]')?.dataset.runStatus==='RELEASED'`);
  const mounted=await ev(`window.__mountedRunWorkspace.isConnected&&window.__mountedRunWorkspace===document.querySelector('[data-testid="run-workspace"]')`);
  const journey=await ev('({browser:window.__vfaBrowserObservation,diagnostics:window.__vfaRuntimeDiagnostics})');
  const d=journey.diagnostics.records,b=journey.browser.records;
  const checks={
    backend_retained_stream:stream.status===200&&events.every(e=>e.run_id===RUN),
    complete_event_sequence:d.filter(r=>r.kind==='sse_event').map(r=>r.sequence).join(',')==='607,608,609,610,611,612,613,614,615,616',
    review_handoff:d.some(r=>r.kind==='projection_installed'&&r.sequence===609),
    proof_handoff:d.some(r=>r.kind==='projection_installed'&&r.sequence===612),
    proof_verified_handoff:d.some(r=>r.kind==='projection_installed'&&r.sequence===614),
    release_handoff:d.some(r=>r.kind==='projection_installed'&&r.sequence===616),
    canonical_appears:d.some(r=>r.kind==='projection_received'&&r.sequence===616&&r.canonicalPresent),
    no_failures:!d.some(r=>['load_failure','decode_failure','http_failure'].includes(r.kind)),
    no_retry:!b.some(r=>r.kind==='error_ui_onset'),
    no_workspace_loss:!b.some(r=>r.kind==='workspace_disappeared'),
    same_mounted_element:mounted,
    no_drops:journey.diagnostics.dropped===0&&journey.browser.dropped===0
  };
  result={classification:'DERIVED RETAINED REPLAY, NOT native confirmation timing',run_id:RUN,checkpoints:[606,609,612,614,616],checks,journey};
  assert(Object.values(checks).every(Boolean),'Continuous journey failed');
  await click('[data-testid="open-results-workspace"]');
  await wait(`window.__vfaBrowserObservation.records.some(r=>r.kind==='useful_report_dom')`);
  result.report=await ev('window.__vfaBrowserObservation');
  result.checks.authoritative_report_visible=true;
  const screenshot=await send('Page.captureScreenshot',{format:'png'});await writeFile(output+'/continuous-report.png',Buffer.from(screenshot.data,'base64'));
}finally{
  if(result)await writeFile(output+'/continuous-replay.json',JSON.stringify(result,null,2)+'\n');
  if(installed)await send('Page.removeScriptToEvaluateOnNewDocument',{identifier:installed.identifier});
  ws.close();
}
console.log(JSON.stringify(result.checks));
