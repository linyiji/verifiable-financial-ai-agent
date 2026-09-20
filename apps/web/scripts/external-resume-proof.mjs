import assert from 'node:assert/strict';
import fs from 'node:fs';
import {decodeRunProjection} from '../src/types/domain.ts';
import {decodeRuntimeEventV1, RuntimeEventIngestionGuard} from '../src/runtime/RuntimeTransport.ts';
import {createRunRuntimeState} from '../src/state/runtimeEventReducer.ts';
const stages = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
for (const stage of stages) {
  const p = decodeRunProjection(stage.projection, stage.run_id);
  const state = createRunRuntimeState(p, {runId: stage.run_id});
  assert.equal(state.runId, stage.run_id);
  const taskIds = stage.projection.actual_graph.tasks.map(t => t.task_id);
  const guard = new RuntimeEventIngestionGuard({runId: stage.run_id, initialSequence: 0,
    authoritativeTaskIds: taskIds});
  for (const frame of stage.frames) {
    const raw = JSON.parse(frame.split('data: ')[1]);
    const event = decodeRuntimeEventV1(raw, {expectedRunId: stage.run_id, authoritativeTaskIds: new Set(taskIds)});
    assert.equal(event.runId, stage.run_id);
    assert.equal(guard.ingest(raw).kind, 'APPLIED');
    assert.equal(guard.ingest(raw).kind, 'DUPLICATE');
  }
}
console.log('durable DTO/reducer reconstruction and SSE decoding PASS');
const {reduceRuntimeEvent, reconcileRunRuntimeState} = await import('../src/state/runtimeEventReducer.ts');
const initial = stages[0], authorized = stages[2];
let before = createRunRuntimeState(decodeRunProjection(initial.projection, initial.run_id), {runId: initial.run_id});
const suffix = authorized.frames.map(f=>JSON.parse(f.split('data: ')[1]))
  .filter(e=>e.sequence > before.committedSequence);
const first = decodeRuntimeEventV1(suffix[0], {expectedRunId: initial.run_id,
  authoritativeTaskIds: new Set(initial.projection.actual_graph.tasks.map(t=>t.task_id))});
const source = {runId: initial.run_id, streamGeneration: before.streamGeneration};
const pending = reduceRuntimeEvent(before, first, source);
assert.equal(pending.connection.kind, 'RECOVERING');
assert.equal(reduceRuntimeEvent(pending, first, source), pending);
const resumed = reconcileRunRuntimeState(pending, decodeRunProjection(authorized.projection, initial.run_id));
assert.equal(resumed.projection.externalFailureResume.state, 'EXTERNAL_RESUME_PENDING');
assert.notEqual(resumed.connection.kind, 'TERMINAL');
assert.throws(()=>reconcileRunRuntimeState(resumed, before.projection));
console.log('terminal-to-Resume reducer, duplicate delivery and stale snapshot rejection PASS');
