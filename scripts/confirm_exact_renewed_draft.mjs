/** One guarded real-browser confirmation. Never prepare; never retry confirmation. */
import assert from 'node:assert/strict';
import {mkdir, readFile, writeFile} from 'node:fs/promises';

const out = 'artifacts/phase5b_live_r2_final';
const draftId = 'DRAFT-036cd4bd-fb8b-4c05-a9ba-25c654588342';
const original = JSON.parse(await readFile('artifacts/mimo_provider_capability/validated-persisted-draft.json', 'utf8'));
const headers = {'X-Phase4-Contract-Version': 'phase4-core/v1'};
const target = (await (await fetch('http://127.0.0.1:9228/json/list')).json()).find(t => t.type === 'page');
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {socket.onopen = resolve; socket.onerror = reject;});
let serial = 0; const pending = new Map(); let confirms = 0, prepares = 0, responseId;
socket.onmessage = ({data}) => {
  const m = JSON.parse(data);
  if (m.id) {const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(m.error) : p.resolve(m.result);}
  if (m.method === 'Network.requestWillBeSent' && m.params.request.method === 'POST') {
    const path = new URL(m.params.request.url).pathname;
    if (path === '/api/research-runs') confirms++;
    if (path === '/api/research-runs/prepare') prepares++;
  }
  if (m.method === 'Network.responseReceived' && new URL(m.params.response.url).pathname === '/api/research-runs' && m.params.type === 'Fetch') responseId = m.params.requestId;
};
const send = (method, params = {}) => new Promise((resolve, reject) => {const id = ++serial; pending.set(id, {resolve, reject}); socket.send(JSON.stringify({id, method, params}));});
const evaluate = async expression => (await send('Runtime.evaluate', {expression, returnByValue: true})).result.value;
async function waitText(text) {
  for (let i = 0; i < 100; i++) {
    if ((await evaluate('document.body.innerText')).includes(text)) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw Error('Expected product state not visible');
}
await send('Network.enable'); await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
await send('Page.navigate', {url: 'http://127.0.0.1:4173/objects/OBJ-NVDA'});
await waitText('Research Memory');
const memory = await (await fetch('http://127.0.0.1:8010/api/objects/OBJ-NVDA/memory', {headers})).json();
assert.equal(memory.latest_released_run_id, original.scheme_snapshot.incremental_context.base_run_id);
assert.equal(memory.latest_research_view_version, 1);
await send('Page.navigate', {url: `http://127.0.0.1:4173/drafts/${draftId}`});
await waitText('确认此方案并开始研究');
const reviewed = await (await fetch(`http://127.0.0.1:8010/api/research-drafts/${draftId}`, {headers})).json();
assert.deepEqual(reviewed.draft, original);
assert.equal(reviewed.lease_id, 'LEASE-0e2bb5a10755b04f754bb905e1b5a8a004676c6fcbd1735ce1e92492f15a9bcf');
assert.equal(reviewed.consumed, false); assert.equal(reviewed.lease_valid, true);
assert.ok(Date.now() < Date.parse(reviewed.effective_expires_at));
assert.equal(await evaluate(`document.querySelector('[data-testid="exact-draft-review"]').dataset.draftHash`), original.draft_hash);
await mkdir(out, {recursive: true});
await writeFile(`${out}/confirmation-attempt-guard.json`, JSON.stringify({draft_id: draftId, draft_hash: original.draft_hash, lease_id: reviewed.lease_id, checked_at: new Date().toISOString(), max_graph_logical_calls: 1, max_runs: 1}), {flag: 'wx'});
await writeFile(`${out}/pre-confirm-review.json`, JSON.stringify(reviewed, null, 2));
const shot = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true});
await writeFile(`${out}/pre-confirm-review.png`, Buffer.from(shot.data, 'base64'));
console.log('Exact draft and effective lease verified. Clicking the product confirmation once.');
await evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent === '确认此方案并开始研究').click()`);
let result;
for (let i = 0; i < 2100; i++) {
  if (responseId) {
    try {result = JSON.parse((await send('Network.getResponseBody', {requestId: responseId})).body); break;} catch {}
  }
  await new Promise(resolve => setTimeout(resolve, 100));
}
assert.equal(confirms, 1); assert.equal(prepares, 0);
assert.ok(result, 'No confirmation outcome observed: do not retry');
await writeFile(`${out}/confirmation-response.json`, JSON.stringify(result, null, 2));
console.log(JSON.stringify({confirm_posts: confirms, prepare_posts: prepares, response: result}));
socket.close();
