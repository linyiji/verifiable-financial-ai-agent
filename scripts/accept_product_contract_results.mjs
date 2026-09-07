import {writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const RUN='RUN-645b12e5-12a1-4a50-8446-684c1c8b9cfc';
const BASE='RUN-57aed683-75d6-4b47-acc6-a73053ea492e';
const REPLAY='RUN-fed43a33-d91f-4ad3-8af8-fc7d9672a005';
const out='artifacts/product_contract_repair_1/';
const target=(await(await fetch('http://127.0.0.1:9227/json/list')).json()).find(t=>t.type==='page');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
let seq=0;const jobs=new Map(),checks=[];
ws.onmessage=({data})=>{const x=JSON.parse(data);if(jobs.has(x.id)){jobs.get(x.id)(x);jobs.delete(x.id)}};
const send=async(method,params={})=>{const r=await new Promise(resolve=>{jobs.set(++seq,resolve);ws.send(JSON.stringify({id:seq,method,params}))});if(r.error)throw Error(r.error.message);return r.result};
const ev=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true});if(r.exceptionDetails)throw Error('evaluation failed');return r.result.value};
const wait=async(selector)=>{for(let i=0;i<150;i++){if(await ev(`!!document.querySelector(${JSON.stringify(selector)})`))return;await new Promise(r=>setTimeout(r,100))}throw Error('missing '+selector)};
const click=async selector=>{const p=await ev(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',clickCount:1});};
const check=(v,name)=>{checks.push({name,pass:!!v});assert(v,name)};
try{
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:`http://127.0.0.1:4173/runs/${BASE}?stage=research`});await wait('[data-testid="run-workspace"]');
 check(await ev(`document.querySelector('[data-testid="run-workspace"]').dataset.runStatus==='RELEASED'`),'accepted Run page released');
 for(const run of [RUN,BASE,REPLAY]){
  for(const [surface,testid] of [['report','interactive-research-report'],['review','interactive-financial-review'],['execution','interactive-execution-record']]){
   await send('Page.navigate',{url:`http://127.0.0.1:4173/runs/${run}/results/${surface}`});await wait(`[data-testid="${testid}"]`);
   check(await ev(`document.querySelector('.results-shell').dataset.runId===${JSON.stringify(run)}`),`${run} ${surface} exact Run DOM`);
   const endpoint={report:'report-view',review:'review-view',execution:'execution-view'}[surface];
   const r=await fetch(`http://127.0.0.1:8010/api/research-runs/${run}/${endpoint}`,{headers:{'X-Phase4-Contract-Version':'phase4-core/v1'}});
   check(r.ok,`${run} ${surface} API ready`);const data=await r.json();check(data.run_id===run,`${run} ${surface} API identity`);
   if(surface==='review')check(data.checks.length===54&&data.verdict==='PASS',`${run} Review 54 PASS`);
  }
 }
 await send('Page.navigate',{url:`http://127.0.0.1:4173/runs/${BASE}/results/report`});await wait('[data-testid="report-source-contribution"]');
 await click('[data-testid="report-source-contribution"]');await wait('[data-testid="execution-exact-focus"]');
 const focus=await ev('Object.fromEntries(new URLSearchParams(location.search))');
 check(await ev(`location.pathname==='/runs/${BASE}/results/execution'&&!document.querySelector('[data-testid="execution-focus-invalid"]')`),'Report to same Run exact Execution');
 check(!!focus.actor&&!!focus.output&&!!focus.event&&!!focus.return_anchor,'complete authoritative contribution focus');
 await click('[data-testid="execution-exact-focus"] [data-testid="execution-open-report-anchor"]');await wait('[data-testid="revenue-growth-section"].report-focus');
 check(await ev(`location.pathname==='/runs/${BASE}/results/report'&&new URLSearchParams(location.search).get('anchor')===${JSON.stringify(focus.return_anchor)}&&document.querySelector('.report-focus').id===${JSON.stringify(focus.return_anchor)}`),'Execution to exact same Run Report anchor');
 await send('Page.navigate',{url:`http://127.0.0.1:4173/runs/${REPLAY}?stage=research`});await wait('[data-testid="path-correction-summary"]');
 for(const id of ['path-correction-summary','added-task'])check(await ev(`document.querySelector('[data-testid="${id}"]').dataset.runId===${JSON.stringify(REPLAY)}`),'replayed history '+id);
 check(await ev(`document.querySelector('[data-testid="path-correction-summary"]').dataset.correctionStatus==='RESOLVED'`),'replayed correction resolved');
 check(await ev(`document.querySelector('[data-testid="replan-approved"]')?.dataset.decision==='APPROVED'`),'replayed replan approved visible');
 check(await ev(`Number(document.querySelector('[data-testid="replan-requested"]').dataset.eventSequence)<Number(document.querySelector('[data-testid="replan-approved"]').dataset.eventSequence)`),'replayed request precedes approval');
 await ev(`document.querySelector('.replan-hero').scrollIntoView({block:'center'})`);
 const screenshot=await send('Page.captureScreenshot',{format:'png'});
 await writeFile(out+'replayed-path.png',Buffer.from(screenshot.data,'base64'));
}finally{await writeFile(out+'browser-acceptance.json',JSON.stringify(checks,null,2));ws.close()}
console.log(`${checks.length} browser/API assertions PASS`);

