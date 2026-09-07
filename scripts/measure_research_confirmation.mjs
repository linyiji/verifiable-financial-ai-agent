/** Opt-in local acceptance harness. Starts exactly ONE real Full Research Run.
 * node scripts/measure_research_confirmation.mjs --start-full-research OUTPUT_DIR
 * Requires dedicated Chrome9227, app4173 and API8010. Does not change product UI.
 * Preinstalls metadata-only observers before app creation, then clicks native UI.
 */
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {installBrowserRuntimeObserver} from './browser_runtime_observer.mjs';
if(process.argv[2]!=='--start-full-research')throw Error('Explicit --start-full-research required');
const output=resolve(process.argv[3]??'artifacts/runtime_observability_enhancement');
await mkdir(output,{recursive:true});
try {const prior=JSON.parse(await readFile(output+'/browser-measurement.json','utf8'));if(prior.t0||prior.run_id)throw Error('Prior confirmation exists: do not create another Run');}
catch(error){if(error.code!=='ENOENT')throw error;}
const target=(await(await fetch('http://127.0.0.1:9227/json/list')).json()).find(t=>t.type==='page');
if(!target)throw Error('Dedicated Chrome page required');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});
let sequence=0;const pending=new Map();
ws.onmessage=({data})=>{const m=JSON.parse(data);const job=pending.get(m.id);if(job){pending.delete(m.id);m.error?job.reject(Error(m.error.message)):job.resolve(m.result)}};
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error('Browser evaluation failed');return r.result.value};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const wait=async selector=>{for(let i=0;i<300;i++){if(await evaluate(`!!document.querySelector(${JSON.stringify(selector)}) && !document.querySelector(${JSON.stringify(selector)}).disabled`))return;await pause(100)}throw Error('Control unavailable '+selector)};
const click=async selector=>{await wait(selector);const point=await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1})};

const observer=`(() => {
 const data=window.__researchMeasurement={schema_version:'browser-performance/v1',document_origin_ms:performance.timeOrigin,run_id:null,t0:null,milestones:[],sse:[]};
 const stamp=()=>({monotonic_ms:performance.now(),epoch_ms:performance.timeOrigin+performance.now()});
 const visible=e=>{if(!e||!e.getClientRects().length||getComputedStyle(e).visibility==='hidden')return false;const r=e.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth};
 const seen=new Set();
 const mark=(name,extra={})=>{if(!data.t0||seen.has(name))return;seen.add(name);data.milestones.push({name,run_id:data.run_id,...stamp(),...extra})};
 const rendered=(name,e,extra={})=>{if(seen.has(name)||!visible(e))return;requestAnimationFrame(()=>requestAnimationFrame(()=>{if(visible(e))mark(name,extra)}))};
 document.addEventListener('click',e=>{const b=e.target.closest?.('[data-testid="wizard-next"]');if(b&&!b.disabled&&b.textContent.trim()==='确认并开始研究'&&!data.t0){data.t0=stamp();}},true);
 const fetchOriginal=window.fetch.bind(window);
 window.fetch=async(...args)=>{
   const response=await fetchOriginal(...args);
   const url=typeof args[0]==='string'?args[0]:args[0]?.url??args[0]?.href??'';
   const method=args[1]?.method??args[0]?.method??'GET';
   if(method.toUpperCase()==='POST'&&/\\/api\\/research-runs$/.test(url)&&data.t0){
     void response.clone().json().then(body=>{const id=body?.admission?.run_id;if(response.ok&&/^RUN-[A-Za-z0-9-]+$/.test(id)){data.run_id=id;mark('run_identity_received',{http_status:response.status})}else mark('confirmation_failed',{http_status:response.status});}).catch(()=>mark('confirmation_decode_failed'));
   }
   if(url.includes('/research-runs/')&&url.endsWith('/events')&&response.ok&&response.body){
     const reader=response.clone().body.getReader();
     void(async()=>{let buffer='';const decoder=new TextDecoder();try{while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});if(buffer.length>1048576){await reader.cancel();break;}const frames=buffer.split(/\\r?\\n\\r?\\n/);buffer=frames.pop();for(const f of frames){const raw=f.split(/\\r?\\n/).filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\\n');if(!raw)continue;let e;try{e=JSON.parse(raw)}catch{continue}if(e.run_id!==data.run_id||data.sse.length>=5000)continue;data.sse.push({run_id:e.run_id,event_id:e.event_id,sequence:e.sequence,type:e.type,backend_timestamp:e.timestamp,...stamp()});mark('first_public_event',{event_id:e.event_id,sequence:e.sequence,backend_timestamp:e.timestamp});}}}catch{/* expected stream cancellation is not a fabricated event */}})();
   }
   return response;
 };
 const scan=()=>{
   if(!data.run_id)return;
   rendered('blocking_error_dom',document.querySelector('[data-testid="error-retry"]'));
   const w=document.querySelector('[data-testid="run-workspace"]');
   if(w?.dataset.runId===data.run_id){
     const header=w.querySelector('.workspace-header-actions .badge');
     const extra={projection_sequence:Number(w.dataset.projectionSequence)};
     if(w.dataset.runStatus==='RUNNING')rendered('first_progress_dom',header,extra);
     if(w.dataset.runStatus==='RELEASED')rendered('release_dom',header,extra);
     const control=document.querySelector('[data-testid="open-results-workspace"]');
     if(control&&!control.disabled)rendered('report_navigable_dom',control,extra);
     const review=document.querySelector('[data-testid="stage-03-open-review"]');
     if(review&&!review.disabled)rendered('review_control_dom',review,extra);
     rendered('review_complete_dom',document.querySelector('.run-lifecycle li:nth-child(3).done button'),extra);
   }
   const workspace=document.querySelector('[data-testid="results-workspace"]');
   const report=workspace?.querySelector('[data-testid="interactive-research-report"]');
   const summary=report?.querySelector('.report-summary p');
   if(workspace?.dataset.runId===data.run_id&&summary?.textContent.trim()&&report.querySelector('.report-key-metrics')&&!summary.textContent.includes('当前没有可展示')){
     rendered('report_content_dom',summary,{report_id:report.dataset.reportId});
     rendered('first_useful_financial_content_dom',summary,{report_id:report.dataset.reportId});
   }
 };
 new MutationObserver(scan).observe(document,{subtree:true,childList:true,attributes:true});
 document.addEventListener('DOMContentLoaded',scan);
})();`;
let measurement, installedObserver;
try{
 await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
 installedObserver=await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${installBrowserRuntimeObserver.toString()})(null);`+observer});
 await send('Page.navigate',{url:'http://127.0.0.1:4173/'});
 await click('[data-testid="research-object-option"][data-object-id="OBJ-NVDA"]');
 await click('[data-testid="wizard-next"]');
 await click('[data-testid="full-research"]');
 await click('[data-testid="wizard-next"]');
 await wait('[data-testid="wizard-next"]');
 await click('[data-testid="wizard-next"]');
 await wait('[data-testid="wizard-next"]');
 if(!await evaluate(`document.querySelector('[data-testid="wizard-next"]').textContent.trim()==='确认并开始研究'`))throw Error('Not at final confirmation');
 await click('[data-testid="wizard-next"]');
 let opened=false, positioned=false;
 const deadline=Date.now()+900000;
 while(Date.now()<deadline){
   await pause(150);
   measurement=await evaluate('window.__researchMeasurement');
   measurement.diagnostics=await evaluate('window.__vfaRuntimeDiagnostics');
   measurement.browser_observation=await evaluate('window.__vfaBrowserObservation');
   if(measurement.run_id&&!positioned){positioned=true;await evaluate('window.scrollTo(0,0)');}
   await writeFile(output+'/browser-measurement.json',JSON.stringify(measurement,null,2));
   if(!opened&&measurement.milestones.some(m=>m.name==='report_navigable_dom')){
     opened=true;measurement.report_click_epoch_ms=Date.now();
     await evaluate(`window.__researchMeasurement.report_click_monotonic_ms=performance.now()`);
     await click('[data-testid="open-results-workspace"]');
   }
   if(measurement.milestones.some(m=>m.name==='first_useful_financial_content_dom'))break;
   if(measurement.milestones.some(m=>m.name==='blocking_error_dom'))break;
   if(measurement.milestones.some(m=>m.name==='confirmation_failed'||m.name==='confirmation_decode_failed'))break;
   if(await evaluate(`document.querySelector('[data-testid="run-workspace"]')?.dataset.runStatus==='FAILED'`))break;
 }
 console.log(JSON.stringify({run_id:measurement?.run_id,t0:measurement?.t0,milestones:measurement?.milestones,sse_count:measurement?.sse.length}));
 if(!measurement?.milestones.some(m=>m.name==='first_useful_financial_content_dom'))process.exitCode=1;
}finally{
 if(measurement)await writeFile(output+'/browser-measurement.json',JSON.stringify(measurement,null,2));
 if(installedObserver)await send('Page.removeScriptToEvaluateOnNewDocument',{identifier:installedObserver.identifier});
 ws.close();
}
