/** Controlled local browser measurement; no production telemetry or private payload export.
 * Usage: node scripts/measure_runtime_browser.mjs RUN-ID [output-directory]
 * Attach to a dedicated headless Chrome on localhost:9227. Does NOT create Runs.
 * API/browser already running on localhost:8010/4173. Start before/just after admission.
 */
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const runId = process.argv[2];
if (!/^RUN-[a-zA-Z0-9-]+$/.test(runId ?? '')) throw Error('Explicit Run ID required');
const output = resolve(process.argv[3] ?? 'artifacts/runtime_efficiency_quick_wins');
await mkdir(output, { recursive: true });
const targets = await (await fetch('http://127.0.0.1:9227/json/list')).json();
const target = targets.find(t => t.type === 'page');
if (!target) throw Error('Dedicated browser page required');
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => { socket.onopen = res; socket.onerror = rej; });
let serial = 0;
const pending = new Map();
socket.onmessage = ({ data }) => {
  const result = JSON.parse(data);
  const job = pending.get(result.id);
  if (job) { pending.delete(result.id); result.error ? job.reject(Error(result.error.message)) : job.resolve(result.result); }
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++serial; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params }));
});
const evaluate = async expression => {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw Error('Browser evaluation failed');
  return r.result.value;
};

// Inject only a bounded, positive-allowlist trail. No body text, evidence or model outputs.
const source = `(() => {
  const runId = ${JSON.stringify(runId)};
  const trail = window.__runtimeTiming = {run_id:runId, origin_ms:performance.timeOrigin, milestones:[], sse:[]};
  const seen = new Set();
  const stamp = () => ({epoch_ms:performance.timeOrigin+performance.now(), monotonic_ms:performance.now()});
  const visible = e => {
    if(!e || !e.getClientRects().length || getComputedStyle(e).visibility==='hidden')return false;
    const r=e.getBoundingClientRect();
    return r.bottom>0 && r.right>0 && r.top<innerHeight && r.left<innerWidth;
  };
  const mark = (name, e, extra={}) => {
    if (seen.has(name) || !visible(e)) return;
    seen.add(name);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (!visible(e)) {seen.delete(name); return;}
      trail.milestones.push({name,run_id:runId,...stamp(),...extra});
    }));
  };
  const scan = () => {
    if (!location.pathname.includes('/runs/'+runId)) return;
    const workspace = document.querySelector('[data-testid="run-workspace"]');
    if (workspace?.dataset.runId === runId) {
      const active = document.querySelector('[data-testid="research-task"][data-task-status="RUNNING"]');
      if(active?.dataset.runId === runId) mark('first_progress_status_render',active,{task_id:active.dataset.taskId,projection_sequence:Number(workspace.dataset.projectionSequence)});
      const completed = [...document.querySelectorAll('[data-testid="research-task"][data-task-status="COMPLETED"]')].find(e=>e.dataset.runId===runId && !e.dataset.taskId.endsWith(':evidence'));
      if(completed) mark('first_specialist_completion_status_render',completed,{task_id:completed.dataset.taskId,projection_sequence:Number(workspace.dataset.projectionSequence)});
      mark('results_control_render',document.querySelector('[data-testid="open-results-workspace"]'));
    }
    const report = document.querySelector('[data-testid="interactive-research-report"]');
    mark('interactive_report_render',report,{report_id:report?.dataset.reportId??null});
  };
  new MutationObserver(scan).observe(document,{subtree:true,childList:true,attributes:true});
  document.addEventListener('DOMContentLoaded',scan);
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    const url = typeof args[0]==='string' ? args[0] : args[0]?.url ?? args[0]?.href;
    if (url?.includes('/research-runs/'+runId+'/events') && response.ok && response.body) {
      const reader = response.clone().body.getReader();
      void (async () => {
        const decoder = new TextDecoder(); let buffer='';
        try { while(true) {
          const {done,value}=await reader.read(); if(done) break;
          buffer+=decoder.decode(value,{stream:true});
          if(buffer.length>1048576) {await reader.cancel();break;}
          const frames=buffer.split(/\\r?\\n\\r?\\n/);buffer=frames.pop();
          for(const frame of frames) {
            const data=frame.split(/\\r?\\n/).filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\\n');
            if(!data)continue; let e;try{e=JSON.parse(data);}catch{continue;}
            if(e.run_id!==runId || trail.sse.length>=5000)continue;
            trail.sse.push({run_id:runId,event_id:e.event_id,type:e.type,sequence:e.sequence,backend_timestamp:e.timestamp,...stamp()});
          }
        }} catch { /* navigation/disconnect is not a fabricated measurement */ }
      })();
    }
    return response;
  };
})();`;
let last = {run_id:runId,milestones:[],sse:[],documents:[]};
try {
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.addScriptToEvaluateOnNewDocument', { source });
  await send('Page.navigate', { url: `http://127.0.0.1:4173/runs/${runId}?stage=research` });
  const deadline = Date.now() + 900000;
  let opened = false;
  let lastReleasePoll = 0;
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, 250));
    const current = await evaluate('window.__runtimeTiming ?? null');
    if (!current) continue;
    if (!last.documents.includes(current.origin_ms)) last.documents.push(current.origin_ms);
    for (const milestone of current.milestones) {
      if (!last.milestones.some(m => m.name === milestone.name)) last.milestones.push(milestone);
    }
    const received = new Set(last.sse.map(e => e.event_id));
    for (const event of current.sse) if (!received.has(event.event_id)) {
      last.sse.push(event); received.add(event.event_id);
    }
    await writeFile(`${output}/browser-timing.json`, JSON.stringify(last, null, 2));
    if (!opened && last.milestones.some(m => m.name === 'results_control_render')) {
      opened = true;
      await evaluate(`document.querySelector('[data-testid="open-results-workspace"]').click()`);
    }
    // Controlled direct navigation is an explicit measurement action, not a
    // claim that a missing live Results control was rendered. Retain its origin.
    if (!opened && Date.now() - lastReleasePoll >= 1000) {
      lastReleasePoll = Date.now();
      const response = await fetch(`http://127.0.0.1:8010/api/research-runs/${runId}`, {
        headers: {'X-Phase4-Contract-Version':'phase4-core/v1'}
      });
      if (response.ok && (await response.json()).status === 'RELEASED') {
        opened = true;
        last.milestones.push({name:'controlled_report_navigation',run_id:runId,epoch_ms:Date.now()});
        await send('Page.navigate', {url:`http://127.0.0.1:4173/runs/${runId}/results/report`});
      }
    }
    if (last.milestones.some(m => m.name === 'interactive_report_render')) break;
    if (await evaluate(`document.querySelector('[data-testid="run-workspace"]')?.dataset.runStatus === 'FAILED'`)) break;
  }
  console.log(JSON.stringify({run_id:runId,milestones:last?.milestones??[],sse_count:last?.sse.length??0}));
  if (!last?.milestones.some(m => m.name === 'interactive_report_render')) {
    process.exitCode = 1; // Preserve partial evidence, never signal successful render.
  }
} finally {
  if(last) await writeFile(`${output}/browser-timing.json`,JSON.stringify(last,null,2));
  socket.close();
}
