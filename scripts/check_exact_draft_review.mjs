/** Read-only real-browser reload/reopen check on a dedicated local Chrome (9228). */
import assert from 'node:assert/strict';
import {readFile, mkdir, writeFile} from 'node:fs/promises';

const draftId = 'DRAFT-036cd4bd-fb8b-4c05-a9ba-25c654588342';
const url = `http://127.0.0.1:4173/drafts/${draftId}`;
const original = JSON.parse(await readFile('artifacts/mimo_provider_capability/validated-persisted-draft.json', 'utf8'));
const out = 'artifacts/phase5b_exact_draft_renewal';
let writes = 0;
async function attach(target) {
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {ws.onopen = resolve; ws.onerror = reject;});
  let serial = 0; const pending = new Map();
  ws.onmessage = ({data}) => {
    const m = JSON.parse(data);
    if (m.id) {const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(m.error) : p.resolve(m.result);}
    if (m.method === 'Network.requestWillBeSent' && !['GET', 'HEAD', 'OPTIONS'].includes(m.params.request.method)) writes++;
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {const id = ++serial; pending.set(id, {resolve, reject}); ws.send(JSON.stringify({id, method, params}));});
  await send('Network.enable'); await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
  return {send, close: () => ws.close()};
}
async function readPage(client) {
  for (let i = 0; i < 100; i++) {
    const r = await client.send('Runtime.evaluate', {expression: `document.querySelector('[data-testid="exact-draft-review"]')?.getAttribute('data-draft-hash')`, returnByValue: true});
    if (r.result.value === original.draft_hash) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  const r = await client.send('Runtime.evaluate', {expression: `({text: document.body.innerText, id: document.querySelector('[data-testid="exact-draft-review"]')?.dataset.draftId, hash: document.querySelector('[data-testid="exact-draft-review"]')?.dataset.draftHash})`, returnByValue: true});
  const v = r.result.value;
  assert.equal(v.id, draftId); assert.equal(v.hash, original.draft_hash);
  for (const text of ['重新确认该研究方案', '没有重新生成 AI 研究方案', '确认授权有效', 'REUSE = 0 · REFRESH = 1 · REVALIDATE = 1 · PREVENT = 1 · UNKNOWN = 0', original.scheme_snapshot.incremental_context.base_run_id, original.scheme_snapshot.incremental_context.base_research_view_version]) assert.ok(v.text.includes(text));
  const response = await fetch(`http://127.0.0.1:8010/api/research-drafts/${draftId}`, {headers: {'X-Phase4-Contract-Version': 'phase4-core/v1'}});
  assert.equal(response.status, 200);
  const value = await response.json();
  assert.deepEqual(value.draft, original); assert.equal(value.lease_valid, true); assert.equal(value.consumed, false);
  return value;
}
const target = (await (await fetch('http://127.0.0.1:9228/json/list')).json()).find(x => x.type === 'page');
let client = await attach(target);
await client.send('Page.navigate', {url});
const first = await readPage(client);
await client.send('Page.reload', {ignoreCache: true});
await new Promise(resolve => setTimeout(resolve, 500));
assert.deepEqual(await readPage(client), first);
await mkdir(out, {recursive: true});
await client.send('Runtime.evaluate', {expression: `document.querySelectorAll('details').forEach(e => e.open = true)`});
const shot = await client.send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true});
await writeFile(`${out}/exact-draft-review.png`, Buffer.from(shot.data, 'base64'));
client.close();
await fetch(`http://127.0.0.1:9228/json/close/${target.id}`);
const reopened = await (await fetch(`http://127.0.0.1:9228/json/new?${encodeURIComponent(url)}`, {method: 'PUT'})).json();
client = await attach(reopened);
assert.deepEqual(await readPage(client), first);
assert.equal(writes, 0);
client.close();
const receipt = {real_browser_review: 'PASS', reload: 'PASS', close_reopen: 'PASS', exact_api_draft_matches_original: true, browser_mutations: writes, draft_id: draftId, draft_hash: original.draft_hash, new_expires_at: first.effective_expires_at};
await writeFile(`${out}/browser-review.json`, JSON.stringify(receipt, null, 2));
console.log(JSON.stringify(receipt));
