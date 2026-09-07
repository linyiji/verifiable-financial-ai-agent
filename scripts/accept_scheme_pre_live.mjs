/** Local Scheme preview only. Never clicks confirmation; server blocks every other write. */
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
const out='artifacts/phase5b_scheme_repair/';
const draft=JSON.parse(await readFile(out+'local-preview-draft.json','utf8'));
const context=draft.scheme_snapshot.incremental_context,BASE=context.base_run_id,VIEW=context.base_research_view_version;
const before=JSON.parse(execFileSync('.venv/bin/python',['scripts/phase5b_history_guard.py'],{encoding:'utf8'}));
const headers={'X-Phase4-Contract-Version':'phase4-core/v1','Content-Type':'application/json'},checks=[];
const check=(v,name)=>{assert(v,name);checks.push(name)};
const target=(await(await fetch('http://127.0.0.1:9227/json/list')).json()).find(t=>t.type==='page');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);let seq=0;const jobs=new Map();
ws.onmessage=({data})=>{const m=JSON.parse(data),job=jobs.get(m.id);if(job){jobs.delete(m.id);m.error?job.reject(Error(m.error.message)):job.resolve(m.result)}};
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;jobs.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
const ev=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error('Browser evaluation failed');return r.result.value};
const wait=async expression=>{for(let n=0;n<200;n++){if(await ev(expression))return;await new Promise(r=>setTimeout(r,150))}throw Error('Missing '+expression)};
const snap=async name=>{await ev(`(()=>{let b=document.getElementById('local-preview-label');if(!b){b=document.createElement('div');b.id='local-preview-label';b.style='position:fixed;top:0;left:230px;z-index:99999;background:#fff3cd;padding:5px 15px;font-size:13px';document.body.append(b)}b.textContent='本地契约预览 · HTTP 模拟响应 · 已阻止 R2 创建';})()`);const r=await send('Page.captureScreenshot',{format:'png'});await writeFile(out+name+'.png',Buffer.from(r.data,'base64'))};
try {
 await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:'http://127.0.0.1:4173/objects/OBJ-NVDA'});
 await wait(`document.querySelector('[data-testid="current-research-view"]')?.dataset.viewVersion==='${VIEW}'`);
 check(await ev(`document.querySelector('[data-testid="current-research-view"]').dataset.sourceRunId==='${BASE}'`),'exact R1/v1 loaded');
 await ev(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='开始新研究').click()`);
 await wait(`!!document.querySelector('[data-testid="previous-research-context"]')`);
 check(await ev(`new URLSearchParams(location.search).get('base_run_id')==='${BASE}'`),'explicit base carried into authoring');
 await ev(`(()=>{const e=document.querySelector('textarea[aria-label="研究目标"]');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,${JSON.stringify(draft.goal.goal_text)});e.dispatchEvent(new Event('input',{bubbles:true}))})()`);
 await wait(`!document.querySelector('[data-testid="wizard-next"]').disabled`);
 await ev(`document.querySelector('[data-testid="wizard-next"]').click()`);
 await wait(`!!document.querySelector('[data-testid="incremental-context"]')`);
 check(await ev(`document.querySelector('[data-testid="incremental-context"]').dataset.baseViewId==='${VIEW}'`),'preview exact source identity');
 check(await ev(`document.querySelectorAll('[data-testid="incremental-decision"]').length===3`),'only three authoritative items considered');
 check(await ev(`!document.querySelector('[data-testid="incremental-decision"][data-decision="REUSE"]')`),'zero REUSE renders no fabricated section');
 for(const d of ['REFRESH','REVALIDATE','PREVENT']) check(await ev(`!!document.querySelector('[data-testid="incremental-decision"][data-decision="${d}"]')`),d+' preview visible');
 await ev('window.scrollTo(0,0)');await snap('scheme-decisions-preview');
 await ev(`document.querySelector('.ai-plan-card').scrollIntoView({block:'center'})`);await snap('scheme-current-work-preview');
 check(await ev(`document.querySelector('.ai-plan-card').innerText.includes('本次研究任务与检查')`),'new current research work visible');
 await ev(`document.querySelector('[data-testid="wizard-next"]').click()`);
 await wait(`document.querySelector('[data-testid="wizard-next"]')?.innerText==='确认并开始研究'`);
 check(true,'unconfirmed Scheme reaches confirmation; confirmation NOT clicked');
 const blocked=await fetch('http://127.0.0.1:8010/api/research-runs',{method:'POST',headers,body:'{}'});
 check(blocked.status===403,'server R2 firewall rejects all admissions');
 for(const [surface,id] of [['report','interactive-research-report'],['review','interactive-financial-review'],['execution','interactive-execution-record']]) {
  await send('Page.navigate',{url:`http://127.0.0.1:4173/runs/${BASE}/results/${surface}`});await wait(`!!document.querySelector('[data-testid="${id}"]')`);
  check(await ev(`document.querySelector('.results-shell').dataset.runId==='${BASE}'`),'historical '+surface+' exact identity');
 }
 const memory=await(await fetch('http://127.0.0.1:8010/api/objects/OBJ-NVDA/memory',{headers})).json();
 check(memory.latest_research_view_version===1&&memory.latest_released_run_id===BASE,'pointer remains R1/v1');
 const after=JSON.parse(execFileSync('.venv/bin/python',['scripts/phase5b_history_guard.py'],{encoding:'utf8'}));
 check(JSON.stringify(before)===JSON.stringify(after),'all Run identities and R1/v1 fingerprints unchanged');
 const receipt=await(await fetch('http://127.0.0.1:8010/__pre_live_receipt')).json();
 check(receipt.provider_calls===0&&receipt.r2_created===false&&receipt.preview_prepares===1,'one local preview; no provider work or R2');
 await writeFile(out+'history-guard.json',JSON.stringify({before,after},null,2));await writeFile(out+'preview-firewall.json',JSON.stringify(receipt,null,2));
} finally {await writeFile(out+'browser-pre-live.json',JSON.stringify(checks,null,2));ws.close()}
console.log(`Scheme pre-live browser PASS (${checks.length} checks); R2_CREATED=NO`);
