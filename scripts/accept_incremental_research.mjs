/** Exact Phase5B journey. --start is guarded against a second provider workflow. */
import assert from 'node:assert/strict';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
const BASE='RUN-57aed683-75d6-4b47-acc6-a73053ea492e',VIEW='RVV-05bec42f-ab9b-55c5-b502-c439b8abe948',OBJECT='OBJ-NVDA';
const out=process.env.PHASE5B_EVIDENCE_DIR ?? 'artifacts/phase5b/';await mkdir(out,{recursive:true});
const mode=process.argv[2],checks=[];
const headers={'X-Phase4-Contract-Version':'phase4-core/v1','Content-Type':'application/json'};
const get=async path=>{const r=await fetch('http://127.0.0.1:8010/api/'+path,{headers});assert(r.ok,`${path}: ${r.status}`);return r.json();};
const save=(name,value)=>writeFile(out+name,JSON.stringify(value,null,2));
const guard=()=>JSON.parse(execFileSync('.venv/bin/python',['scripts/phase5b_history_guard.py'],{encoding:'utf8'}));
const check=(value,name)=>{checks.push({name,pass:!!value});assert(value,name);};
const target=(await(await fetch('http://127.0.0.1:9227/json/list')).json()).find(t=>t.type==='page');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);let sequence=0;const jobs=new Map();
ws.onmessage=({data})=>{const m=JSON.parse(data),job=jobs.get(m.id);if(job){jobs.delete(m.id);m.error?job.reject(Error(m.error.message)):job.resolve(m.result);}};
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;jobs.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
const ev=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error('Browser evaluation failed');return r.result.value;};
const wait=async(expression,seconds=35)=>{for(let i=0;i<seconds*5;i++){if(await ev(expression))return;await new Promise(r=>setTimeout(r,200));}throw Error('Missing browser condition: '+expression);};
const click=async selector=>{const p=await ev(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',clickCount:1});};
const navigate=url=>send('Page.navigate',{url:'http://127.0.0.1:4173'+url});
const snap=async name=>{const r=await send('Page.captureScreenshot',{format:'png'});await writeFile(out+name+'.png',Buffer.from(r.data,'base64'));};
try {
 await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
 if(mode==='--preflight') {
  const memory=await get(`objects/${OBJECT}/memory`);check(memory.latest_released_run_id===BASE&&memory.current_view.research_view_version_id===VIEW,'exact frozen R1/v1');
  await save('memory-v1.json',memory);await save('guard-before.json',guard());
  await navigate(`/objects/${OBJECT}`);await wait(`document.querySelector('[data-testid="current-research-view"]')?.dataset.viewVersion==='${VIEW}'`);await snap('01-object-v1');
  await ev(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='开始新研究').click()`);
  await wait(`document.querySelector('[data-testid="previous-research-context"]')?.dataset.baseViewId==='${VIEW}'`);
  check(await ev(`new URLSearchParams(location.search).get('base_run_id')==='${BASE}'`),'Start New Research carries exact selected base');
  await ev('window.__phase5bReloadMarker=true');await send('Page.reload',{ignoreCache:true});await wait(`!window.__phase5bReloadMarker&&document.querySelector('[data-testid="previous-research-context"]')?.dataset.baseRunId==='${BASE}'`);
  await wait(`!!document.querySelector('textarea[aria-label="研究目标"]')`);
  const goal='更新 NVIDIA 公司金融研究：基于上次研究的历史背景，使用当前可获得且期间一致的权威财务证据重新评估营收增长、盈利能力、估值与主要风险，结合最新公司披露和行业事件，区分已验证事实与尚待确认的信息。';
  await ev(`(()=>{const t=document.querySelector('textarea[aria-label="研究目标"]');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(t,${JSON.stringify(goal)});t.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await wait(`!document.querySelector('[data-testid="wizard-next"]').disabled`);await snap('02-goal-with-memory');check(true,'goal and previous context visible before provider call');
 } else if(mode==='--start'||mode==='--resume-pre-provider') {
  assert.equal(process.env.LIVE_R2_AUTHORIZED,'YES');
  const before=JSON.parse(await readFile(out+'guard-before.json','utf8'));check(JSON.stringify(before)===JSON.stringify(guard()),'history unchanged before one live attempt');
  if(mode==='--resume-pre-provider') {
   const failure=JSON.parse(await readFile(out+'pre-provider-composition-failure.json','utf8'));
   assert.equal(failure.provider_calls,0);assert.equal(failure.new_runs,0);
  }
  await writeFile(out+(mode==='--start'?'start-attempt.json':'resumed-provider-attempt.json'),JSON.stringify({base_run_id:BASE,base_view_id:VIEW,started_at:new Date().toISOString()}),{flag:'wx'});
  check(await ev(`!!document.querySelector('textarea[aria-label="研究目标"]')&&!document.querySelector('[data-testid="wizard-next"]').disabled`),'preflight goal still selected');
  await click('[data-testid="wizard-next"]');
  await wait(`!!document.querySelector('[data-testid="incremental-context"]')||!!document.querySelector('[data-testid="typed-error"]')`,240);
  check(await ev(`!!document.querySelector('[data-testid="incremental-context"]')&&!document.querySelector('[data-testid="typed-error"]')`),'real AI incremental scheme generated');
  const decisions=await ev(`Array.from(document.querySelectorAll('[data-testid="incremental-decision"]')).map(e=>({decision:e.dataset.decision,source_run_id:e.dataset.sourceRunId,text:e.innerText}))`);
  check(decisions.every(x=>['REUSE','REFRESH','REVALIDATE','PREVENT','UNKNOWN'].includes(x.decision)&&x.source_run_id===BASE),'only actual governed decisions before confirmation; zero categories valid');await save('scheme-decisions.json',decisions);await snap('03-incremental-scheme');
  await click('[data-testid="wizard-next"]');await snap('04-confirm');
  await click('[data-testid="wizard-next"]');await wait(`location.pathname.startsWith('/runs/')||!!document.querySelector('[data-testid="typed-error"]')`,240);
  const path=await ev('location.pathname');assert(path.startsWith('/runs/'),'confirmation failed; do not retry automatically');
  const runId=decodeURIComponent(path.split('/')[2]);assert.notEqual(runId,BASE);await save('r2.json',{run_id:runId,base_run_id:BASE,base_view_id:VIEW});
  const p=await get(`research-runs/${runId}/projection`);check(p.confirmed_scheme.incremental_context.base_run_id===BASE,'persisted R2 scheme exact base');
  await save('r2-initial-projection.json',p);await snap('05-independent-runtime');
  const after=guard();check(after.run_ids.filter(id=>!before.run_ids.includes(id)).join()===runId,'exactly one new Run');console.log('R2_RUN_ID = '+runId);
 } else if(mode==='--finish') {
  const {run_id:run}=JSON.parse(await readFile(out+'r2.json','utf8'));
  const p=await get(`research-runs/${run}/projection`);check(p.run.status==='RELEASED','R2 independently released');
  await save('r2-released-projection.json',p);
  const memory=await get(`objects/${OBJECT}/memory`);check(memory.latest_released_run_id===run&&memory.latest_research_view_version===2,'atomic memory v2 pointer');
  check(memory.base_memory.current_view.research_view_version_id===VIEW,'exact historical v1 available');await save('memory-v2.json',memory);
  for(const [surface,testid] of [['report','interactive-research-report'],['review','interactive-financial-review'],['execution','interactive-execution-record']]) {
   await navigate(`/runs/${run}/results/${surface}`);await wait(`!!document.querySelector('[data-testid="${testid}"]')`);
   check(await ev(`document.querySelector('.results-shell').dataset.runId===${JSON.stringify(run)}`),'R2 '+surface+' exact identity');await snap('06-'+surface);
  }
  await navigate(`/objects/${OBJECT}`);await wait(`document.querySelector('[data-testid="current-research-view"]')?.dataset.sourceRunId===${JSON.stringify(run)}`);
  await ev(`document.querySelector('[data-testid="base-vs-current"]').scrollIntoView({block:'start'})`);await snap('07-base-vs-current');
  check(await ev(`document.querySelector('[data-testid="base-vs-current"]').dataset.baseRunId==='${BASE}'`),'comparison exact R1');
  check(await ev(`document.querySelectorAll('[data-testid="governed-change"]').length===${memory.changes.length}`),'authoritative governed changes visible');
  await click('[data-testid="comparison-base-source"]');await wait(`document.querySelector('[data-testid="results-workspace"]')?.dataset.runId==='${BASE}'`);check(true,'exact R1 historical navigation');
  await navigate(`/objects/${OBJECT}`);await wait(`!!document.querySelector('[data-testid="comparison-current-source"]')`);await click('[data-testid="comparison-current-source"]');await wait(`document.querySelector('[data-testid="results-workspace"]')?.dataset.runId===${JSON.stringify(run)}`);check(true,'exact R2 result navigation');
  await navigate(`/objects/${OBJECT}`);await wait(`!!document.querySelector('[data-testid="base-vs-current"]')`);await send('Page.reload',{ignoreCache:true});await wait(`document.querySelector('[data-testid="current-research-view"]')?.dataset.sourceRunId===${JSON.stringify(run)}`);check(true,'v2 survives refresh');
  await send('Page.navigate',{url:'about:blank'});await navigate(`/objects/${OBJECT}`);await wait(`!!document.querySelector('[data-testid="base-vs-current"]')`);check(true,'v2/v1 survive reopen');
  await click('#object-tab-history');await wait(`!!document.querySelector('[data-testid="object-history-run"][data-run-id="${run}"]')`);check(await ev(`!!document.querySelector('[data-testid="object-history-run"][data-run-id="${BASE}"]')`),'history retains R1 and R2');await snap('08-history');
  const before=JSON.parse(await readFile(out+'guard-before.json','utf8')),after=guard();await save('guard-after.json',after);
  check(after.run_ids.filter(id=>!before.run_ids.includes(id)).join()===run,'new provider research Runs = 1');delete before.run_ids;delete after.run_ids;check(JSON.stringify(before)===JSON.stringify(after),'R1 and v1 byte/logical fingerprints unchanged');
 } else throw Error('Choose --preflight, --start or --finish');
} finally {await save(`browser-${mode?.slice(2)}.json`,checks);ws.close();}
console.log(`${mode}: ${checks.length} checks PASS`);
