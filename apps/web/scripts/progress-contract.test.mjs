import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {completedTasksWire, releasedWire} from './product-contract-fixtures.mjs';

const vite = await createServer({root:new URL('../',import.meta.url).pathname,server:{middlewareMode:true},appType:'custom'});
let count = 0;
const check = (predicate, name) => { assert.ok(predicate,name); count++; };
try {
  const {decodeRunProjection, ContractDecodeError} = await vite.ssrLoadModule('/src/types/domain.ts');
  const {stageState} = await vite.ssrLoadModule('/src/components/ResearchRuntimeWorkspace.tsx');
  for (const status of ['RUNNING','REVIEW']) {
    const p = decodeRunProjection(completedTasksWire(status),'RUN-A');
    check(p.lifecycle.progress.fraction===1 && p.run.backendStatus===status && !p.terminal.isTerminal,`A1 ${status} accepts complete task progress without terminality`);
    check(stageState(p,'complete')==='pending',`A5 ${status} 100% does not render Released`);
  }
  for (const fraction of [-0.01,1.01]) {
    const p = completedTasksWire(); p.lifecycle.progress.fraction=fraction;
    assert.throws(()=>decodeRunProjection(p,'RUN-A'),ContractDecodeError);count++;
  }
  for (const mutate of [p=>{p.lifecycle.progress.fraction=0.99;},p=>{p.lifecycle.progress.completed_tasks=1;}]) {
    const p = completedTasksWire(); mutate(p);
    assert.throws(()=>decodeRunProjection(p,'RUN-A'),ContractDecodeError);count++;
  }
  const released = decodeRunProjection(releasedWire(),'RUN-A');
  check(released.terminal.isTerminal && released.lifecycle.progress.fraction===1,'A4 RELEASED remains accepted');
  check(stageState(released,'complete')==='done','Released stage derives from explicit closure');
} finally { await vite.close(); }
console.log(`P1-A progress contract PASS (${count} checks)`);
