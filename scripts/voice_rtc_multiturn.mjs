/** Finite extension of the existing product RTC acceptance Harness.
 * No model calls or alternate dialogue/playback implementation in this client.
 */
import {chromium} from '../apps/web/node_modules/playwright-core/index.mjs';
import {ReviewGate,waitForTurn,assertNotTerminal} from './voice_rtc_review_gate.mjs';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs/promises';import path from 'node:path';import crypto from 'node:crypto';
const root=process.cwd(),base=path.join(root,'output/voice-cantonese-e2e-20261024');
const evidenceName=process.argv.includes('--evidence-dir')?process.argv[process.argv.indexOf('--evidence-dir')+1]:'unified-voice-20261025';
if(!/^[a-z0-9-]+(?:\/[a-z0-9-]+)*$/.test(evidenceName))throw Error('INVALID_EVIDENCE_SCOPE');
const out=await fs.realpath(path.join(base,evidenceName));
const allowedRoot=await fs.realpath(base);
if(!out.startsWith(allowedRoot+path.sep))throw Error('EVIDENCE_REALPATH_OUTSIDE_ROOT');
const plan=JSON.parse(await fs.readFile(path.join(out,'input-plan.json'))),profile=await fs.readFile(path.join(out,'profile.json'));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
if(JSON.parse(profile).require_llm_tls_preflight){execFileSync(path.join(root,'.venv/bin/python'),['-m','src.adapters.voice_candidate_http','check',path.join(out,'profile.json'),path.join(out,'tls-preflight.json')],{cwd:root,stdio:'pipe'});}
if(process.argv.includes('--preflight-only')){console.log(JSON.stringify({out,profileSHA256:sha(profile),autonomous_skill:plan.autonomous_skill,sessions:plan.sessions.length,scope:'NO_NETWORK_OR_MODEL_EXECUTION'}));process.exit(0);}
try{await fs.access(path.join(out,'rtc-sessions.json'));throw Error('NO_REPEAT_ALLOWED')}catch(e){if(e.code!=='ENOENT')throw e;}
// Local API reload can precede browser startup; no supplier call or retry here.
let startupReady=false;const startupDeadline=Date.now()+10000;
while(Date.now()<startupDeadline){
 try{const r=await fetch('http://127.0.0.1:15364/api/local-qa/session',{signal:AbortSignal.timeout(1500)});if(r.ok){startupReady=true;break;}}catch{}
 await new Promise(resolve=>setTimeout(resolve,250));
}
if(!startupReady)throw Error('LOCAL_API_NOT_READY_NO_RTC_STARTED');
const all={startedAt:Date.now(),scope:'EXISTING_PRODUCT_HARNESS_REAL_RTC_SELF_AUDIO',profileSHA256:sha(profile),sessions:[],humanAssessment:'PENDING_NEW_RECORDINGS'};
const save=()=>fs.writeFile(path.join(out,'rtc-sessions.json'),JSON.stringify(all,null,2));await save();
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--autoplay-policy=no-user-gesture-required']});
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function trace(sid){try{return(await fs.readFile(path.join(base,'worker',sid+'.jsonl'),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse)}catch{return[]}}
async function until(sid,check,timeout){return waitForTurn(()=>trace(sid),check,{timeout,wait})}
const failed=rows=>rows.find(e=>['turn_failed','response_failed','turn_deadline_exceeded','asr_queue_timeout','call_stopped','call_ended','response_cancelled','turn_cancelled'].includes(e.kind));
let stop=false;
try{for(const spec of plan.sessions){
 if(stop)break;
 const result={scenario:spec.scenario,index:spec.id,turns:[],errors:[],startedAt:Date.now()};all.sessions.push(result);await save();
 const context=await browser.newContext({viewport:{width:1440,height:950}}),page=await context.newPage();page.setDefaultTimeout(20000);let sid=null;
 page.on('pageerror',e=>result.errors.push({type:'pageerror',message:e.message}));
 // Retain only known SDK lifecycle messages, never arbitrary console objects or credentials.
 result.connectionDiagnostics=[];
 page.on('console',m=>{const t=m.text();for(const label of ['ping timeout','connection quality lost','could not recover connection','Page leave detected','Signal connection closed'])if(t.includes(label))result.connectionDiagnostics.push({at:Date.now(),type:m.type(),label});});
 try{
  await page.goto('http://127.0.0.1:15364/');await page.getByRole('button',{name:'使用 local-alice',exact:true}).click();
  await page.waitForFunction(()=>!document.body.innerText.includes('使用 local-alice'));
  await page.evaluate(await fs.readFile(path.join(root,'scripts/voice_rtc_browser_fixture.js'),'utf8'));
  await page.evaluate(()=>{
   window.__rtcCapture={clips:[],pcs:[],recorders:[]};const Native=window.RTCPeerConnection;
   window.RTCPeerConnection=class extends Native{constructor(...args){super(...args);window.__rtcCapture.pcs.push(this)}};
   const seen=new WeakSet();const attach=()=>{for(const el of document.querySelectorAll('audio[data-vefin-worker-audio]')){
    if(!el.srcObject||seen.has(el.srcObject))continue;seen.add(el.srcObject);
    const item={trackSid:el.dataset.vefinTrackSid,attachedAt:Date.now(),base64:null};window.__rtcCapture.clips.push(item);
    const chunks=[],rec=new MediaRecorder(el.srcObject,{mimeType:'audio/webm;codecs=opus'});
    rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
    rec.onstop=async()=>{const bytes=new Uint8Array(await new Blob(chunks,{type:rec.mimeType}).arrayBuffer());let s='';for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));item.base64=btoa(s);item.stoppedAt=Date.now()};
    rec.onstart=()=>item.recordingStartedAt=Date.now();rec.start(100);window.__rtcCapture.recorders.push(rec);
   }};new MutationObserver(attach).observe(document.body,{childList:true,subtree:true});attach();
  });
  const key='vefin-'+evidenceName+'-session-'+spec.id;
  const admission={enabled:true,user:'local-alice',idempotency_key:key,expires_at:new Date(Date.now()+900000).toISOString()};
  await fs.writeFile(path.join(out,'test-admission.json'),JSON.stringify(admission));
  const created=await page.evaluate(async key=>{const r=await fetch('/api/voice-sessions',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify({interaction_mode:'conversation',language:'yue-HK'})});if(!r.ok)throw Error('CREATE_'+r.status);return r.json()},key);
  sid=created.id;result.sessionId=sid;if(!sid||created.language!=='yue-HK')throw Error('INVALID_SESSION');
  const allow=JSON.parse(await fs.readFile(path.join(base,'sessions.json')));allow[sid]={label:'AUTOMATED_AUDIO',phase:'UNIFIED_MULTITURN_'+spec.id,node_profile:{file:evidenceName+'/profile.json',sha256:sha(profile)}};
  if(spec.restore_context){const seed=await fs.readFile(path.join(out,'restored-context.json'));allow[sid].restored_context={file:evidenceName+'/restored-context.json',sha256:sha(seed)};result.restoredContext={sha256:sha(seed),scope:'NEW_SESSION_RESTORED_TEXT_CONTEXT_NOT_OLD_SOCKET_OR_AUDIO_REPLAY'}};
  await fs.writeFile(path.join(base,'sessions.json'),JSON.stringify(allow));await fs.writeFile(path.join(out,'test-admission.json'),JSON.stringify({...admission,session_id:sid}));await save();
  await page.evaluate(async id=>{const r=await fetch(`/api/voice-sessions/${id}/credentials`,{method:'POST',credentials:'same-origin'});if(!r.ok)throw Error('CREDENTIALS_'+r.status);const credentials=await r.json();const {LiveKitVoiceMedia}=await import('/src/features/voice/livekit.ts');window.__unifiedMedia=new LiveKitVoiceMedia();await window.__vefinOutputProbe.resume();await window.__unifiedMedia.connect(credentials,()=>window.__unifiedDisconnectedAt=Date.now())},sid);
  await page.waitForFunction(()=>window.__vefinAutomationAudio.events.some(e=>e.event==='worker_track_subscribed'),{},{timeout:30000});
  await page.waitForFunction(()=>window.__rtcCapture.clips.length>0&&window.__rtcCapture.clips.every(c=>c.recordingStartedAt),{},{timeout:10000});
  for(let j=0;j<spec.turns.length;j++){
   assertNotTerminal(await trace(sid));
   const input=spec.turns[j],bytes=await fs.readFile(input.file);if(sha(bytes)!==input.sha256)throw Error('INPUT_HASH_CHANGED');
   const row={round:j+1,input:input.file,inputSHA256:input.sha256,expectations:input.expectations};result.turns.push(row);await save();
   if(plan.autonomous_skill)execFileSync(path.join(root,'.venv/bin/python'),['-c','from src.adapters.voice_call_budget import charge_rtc_input; import sys; charge_rtc_input(sys.argv[1],sys.argv[2],int(sys.argv[3]),sys.argv[4])',path.join(out,'call-ledger.json'),sid,String(j+1),input.sha256],{cwd:root,stdio:'pipe'});
   row.inputTiming=await page.evaluate(b64=>window.__vefinAutomationAudio.playBase64(b64),bytes.toString('base64'));await save();
   if(spec.interrupt_after_round===j+1){
    const first=await until(sid,rows=>failed(rows)||rows.find(e=>e.kind==='playout_first_frame'&&e.turn===j+1),120000);
    if(failed([first]))throw Error('AFFECTED_NODE_FAILED');
    const deadline=Date.now()+3000;let active=null;
    while(Date.now()<deadline){active=await page.evaluate(()=>window.__vefinOutputProbe.outputs.flatMap(x=>x.intervals).filter(x=>Date.now()-x.lastAt<60).at(-1)??null);if(active)break;await wait(20)}
    if(!active)throw Error('CLIENT_NOT_ACTUALLY_HEARING_AUDIO_NO_BARGE_IN');
    row.interruptTriggeredByNextRTCInput=true;row.firstFrame=first;row.clientActiveBeforeInterrupt=active;row.bargeInPlannedAt=Date.now();await save();continue;
   }
   const end=await until(sid,rows=>failed(rows)||rows.find(e=>e.kind==='playout_completed'&&e.turn===j+1),150000);
   row.workerTerminal=end;await save();if(failed([end]))throw Error('AFFECTED_NODE_FAILED');
   // Client activity, not a fixed inter-turn sleep, establishes input readiness.
   await page.waitForFunction(since=>{
    const intervals=window.__vefinOutputProbe.outputs.flatMap(x=>x.intervals);
    const last=intervals.filter(x=>x.lastAt>=since).sort((a,b)=>b.lastAt-a.lastAt)[0];
    return last&&Date.now()-last.lastAt>=500;
   },row.inputTiming.endedAt,{timeout:10000});
   row.clientPlaybackBoundary=await page.evaluate(()=>({observedAt:Date.now(),lastAudioAt:Math.max(...window.__vefinOutputProbe.outputs.flatMap(x=>x.intervals.map(y=>y.lastAt))),quietWindowMs:500}));await save();
   if(plan.review_required){
    const traces=await trace(sid),content=traces.find(e=>e.kind==='response_first_content'&&e.turn===j+1);
    if(!content?.text||!content.content_acceptance)throw Error('NO_ACCEPTED_CONTENT_FOR_REVIEW');
    const gate=new ReviewGate(sid,j+1,sha(Buffer.from(content.text))),request={...gate.identity,turn_id:content.turn_id,text:content.text,acceptance:content.content_acceptance,requestedAt:Date.now()};
    await fs.writeFile(path.join(out,`review-request-${j+1}.json`),JSON.stringify(request,null,2));
    const reviewDeadline=Date.now()+300000;
    while(!gate.allowed){
     if(Date.now()>reviewDeadline)throw Error('REVIEW_WAIT_EXPIRED');
     const current=await trace(sid);if(failed(current)||current.some(e=>['room_disconnected','response_cancelled','turn_cancelled'].includes(e.kind))){gate.stop();throw Error('SESSION_TERMINAL')}
     try{const decision=JSON.parse(await fs.readFile(path.join(out,`review-decision-${j+1}.json`)));gate.review(decision)}catch(e){if(e.code!=='ENOENT')throw e}
     if(!gate.allowed)await wait(100);
    }
    row.review={...request,acceptedAt:Date.now(),decision:'PASS'};await save();
   }
   if(plan.autonomous_skill){
    const ev=await page.evaluate(async id=>(await(await fetch(`/api/voice-sessions/${id}/events?limit=500`,{credentials:'same-origin'})).json()).events??[],sid);
    const response=ev.filter(e=>e.kind==='assistant_response').at(-1);
    if(!response?.data?.skill_state)throw Error('SKILL_STATE_MISSING');
    row.skillState=response.data.skill_state;row.contentAcceptance=response.data.content_acceptance;await save();
    if(['COMPLETED','CANCELLED','PARTIAL'].includes(row.skillState.status)){result.skillTerminal=row.skillState.status;break;}
   }

  }
  if(plan.autonomous_skill&&!result.skillTerminal)throw Error('SKILL_TASK_INPUTS_EXHAUSTED_WITHOUT_CLOSURE');
  result.status='EXECUTED_CLIENT_COVERAGE_PENDING';
 }catch(e){result.status='FAILED_STOP_NO_RETRY';result.failure={type:e.name,message:e.message};stop=true;}
 finally{
  if(sid){
   await wait(900);
   result.events=await page.evaluate(async id=>{const r=await fetch(`/api/voice-sessions/${id}/events?limit=500`,{credentials:'same-origin'});return(await r.json()).events??[]},sid).catch(()=>[]);
   result.client=await page.evaluate(async()=>({probe:window.__vefinOutputProbe.outputs,media:window.__vefinAutomationAudio.events,stats:await Promise.all(window.__rtcCapture.pcs.map(async pc=>{try{return[...(await pc.getStats()).values()].filter(s=>s.type==='inbound-rtp'&&s.kind==='audio').map(s=>({bytesReceived:s.bytesReceived,packetsReceived:s.packetsReceived,packetsLost:s.packetsLost,totalSamplesReceived:s.totalSamplesReceived,jitter:s.jitter,concealedSamples:s.concealedSamples}))}catch{return[]}}))})).catch(()=>({}));
   await page.evaluate(()=>window.__rtcCapture.recorders.forEach(r=>{if(r.state!=='inactive')r.stop()})).catch(()=>{});
   await page.waitForFunction(()=>window.__rtcCapture.clips.every(c=>c.base64!==null),{},{timeout:6000}).catch(()=>{});
   const clips=await page.evaluate(()=>window.__rtcCapture.clips).catch(()=>[]);result.client.clips=[];
   for(let i=0;i<clips.length;i++){const c=clips[i];if(!c.base64)continue;const bytes=Buffer.from(c.base64,'base64'),name=`session-${spec.id}-client-${i+1}.webm`;await fs.writeFile(path.join(out,name),bytes);delete c.base64;result.client.clips.push({...c,file:name,sha256:sha(bytes)})}
   await page.screenshot({path:path.join(out,`session-${spec.id}-page.png`)}).catch(()=>{});
   await page.evaluate(async id=>{window.__unifiedMedia?.disconnect();const r=await fetch(`/api/voice-sessions/${id}/end`,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'});if(!r.ok)throw Error('END_'+r.status)},sid).then(()=>result.sessionEnded=true).catch(e=>result.errors.push({cleanup:e.message}));
   await until(sid,rows=>rows.find(e=>e.kind==='call_ended'||e.kind==='room_disconnected'),5000).catch(()=>{});
   const allow=JSON.parse(await fs.readFile(path.join(base,'sessions.json')));if(allow[sid]){delete allow[sid].node_profile;delete allow[sid].restored_context;allow[sid].replay_revoked=true;allow[sid].endedAt=Date.now()};await fs.writeFile(path.join(base,'sessions.json'),JSON.stringify(allow));
  }
  const admission=JSON.parse(await fs.readFile(path.join(out,'test-admission.json')));admission.enabled=false;await fs.writeFile(path.join(out,'test-admission.json'),JSON.stringify(admission));
  result.finishedAt=Date.now();await save();await context.close();console.log(JSON.stringify({session:spec.id,status:result.status,turns:result.turns.length,failure:result.failure??null}));
 }
}}
finally{all.finishedAt=Date.now();await save();await browser.close()}
