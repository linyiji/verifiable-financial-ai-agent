import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {completedTasksWire, releasedWire} from './product-contract-fixtures.mjs';

const vite=await createServer({root:new URL('../',import.meta.url).pathname,server:{middlewareMode:true},appType:'custom'});
let count=0;
const check=(value,label)=>{assert.ok(value,label);count++;};
try {
  const {decodeRunProjection}=await vite.ssrLoadModule('/src/types/domain.ts');
  const {createRunRuntimeState:create,reconcileRunRuntimeState:reconcile,RuntimeProjectionError}=await vite.ssrLoadModule('/src/state/runtimeEventReducer.ts');
  const before=decodeRunProjection(completedTasksWire(),'RUN-A'), released=decodeRunProjection(releasedWire(),'RUN-A');
  const initial=create(before,{runId:'RUN-A',canonicalRecordId:null});
  const bound=reconcile(initial,released);
  check(bound.identity.canonicalRecordId==='CER-A'&&bound.connection.kind==='TERMINAL','B1 legitimate release materialization binds identity');
  check(initial.identity.canonicalRecordId===null&&Object.isFrozen(bound.identity),'B7 immutable prior state retained; no reset');
  check(bound.streamGeneration===initial.streamGeneration+1&&bound.runId===initial.runId,'continuous reconciliation, not recreation');
  check(reconcile(bound,released).identity.canonicalRecordId==='CER-A','B2 same canonical stays bound');
  for(const id of ['CER-OTHER',null]) {
    const next=structuredClone(released);next.result.canonicalRecordId=next.execution.canonicalRecordId=id;
    assert.throws(()=>reconcile(bound,next),RuntimeProjectionError);count++;
  }
  const foreign=structuredClone(released);foreign.run.runId='RUN-B';
  assert.throws(()=>reconcile(initial,foreign),RuntimeProjectionError);count++;
  const foreignWire=releasedWire();foreignWire.run.run_id='RUN-B';
  assert.throws(()=>decodeRunProjection(foreignWire,'RUN-A'));count++;
  const early=structuredClone(before);early.result.canonicalRecordId=early.execution.canonicalRecordId='CER-A';
  assert.throws(()=>reconcile(initial,early),RuntimeProjectionError);count++;
  const mismatch=structuredClone(released);mismatch.execution.canonicalRecordId='CER-B';
  assert.throws(()=>reconcile(initial,mismatch),RuntimeProjectionError);count++;
  const missing=structuredClone(released);missing.execution.canonicalRecordId=null;
  assert.throws(()=>reconcile(initial,missing),RuntimeProjectionError);count++;
  const stale=structuredClone(released);stale.projectionSequence=0;
  assert.throws(()=>reconcile(initial,stale),RuntimeProjectionError);count++;
  check(initial.identity.canonicalRecordId===null,'failed replacement cannot bind source state');
  const direct=create(released,{runId:'RUN-A'});
  check(direct.identity.canonicalRecordId==='CER-A','initial released mount binds omitted optional identity');
  const substituted=structuredClone(released);substituted.result.canonicalRecordId=substituted.execution.canonicalRecordId='CER-B';
  assert.throws(()=>reconcile(direct,substituted),RuntimeProjectionError);count++;
} finally {await vite.close();}
console.log(`P1-B canonical lifecycle PASS (${count} checks)`);
