import assert from "node:assert/strict";

import {
  RUNTIME_EVENT_EFFECT_BY_TYPE_V1,
  RuntimeEventIngestionGuard,
  RuntimeIngestionError,
  decodeRuntimeEventV1,
  runtimeEventFingerprintV1
} from "../src/runtime/RuntimeTransport.ts";
import {
  SSEFrameParser,
  SSERuntimeTransport,
  runtimeCursorHeaderV1
} from "../src/runtime/SSERuntimeTransport.ts";
import {
  RuntimeProjectionError,
  beginRuntimeStream,
  createRunRuntimeState,
  markRuntimeBackoff,
  markRuntimeStreamOpen,
  markRuntimeTransportFailed,
  reconcileRunRuntimeState,
  reduceRuntimeEvent,
  selectRunProjection
} from "../src/state/runtimeEventReducer.ts";

const RUN_A = "RUN-EXACT-A";
const RUN_B = "RUN-EXACT-B";
const OBJECT_A = "OBJECT-A";
const GOAL_A = "GOAL-A";
const SCHEME_A = "SCHEME-A";
const PLANNED_GRAPH_A = "GRAPH-PLANNED-A";
const ACTUAL_GRAPH_A = "GRAPH-ACTUAL-A";
const TASK_A = "TASK-A";
const TASK_B = "TASK-B";
const NOW = "2026-09-05T00:00:00.000Z";

let checks = 0;
const check = (actual, expected, message) => {
  checks += 1;
  assert.deepEqual(actual, expected, message);
};
const ok = (value, message) => {
  checks += 1;
  assert.ok(value, message);
};
const throws = (callback, expectation, message) => {
  checks += 1;
  assert.throws(callback, expectation, message);
};

function task(taskId, runId = RUN_A, dependencies = [], backendStatus = "RUNNING") {
  const status = {
    CREATED: "QUEUED",
    WAITING: "QUEUED",
    READY: "READY",
    RUNNING: "ACTIVE",
    WAITING_FOR_CAPABILITY: "WAITING_SUPPORT",
    SELF_CORRECTING: "CORRECTING",
    BLOCKED: "BLOCKED",
    REVIEW: "REVIEW",
    COMPLETED: "COMPLETE",
    FAILED: "FAILED",
    CAPABILITY_BUILD_FAILED: "FAILED",
    CANCELLED: "CANCELLED"
  }[backendStatus];
  return {
    taskId,
    runId,
    backendStatus,
    status,
    dependencies,
    progress: 0.1,
    attemptCount: 1
  };
}

function availability(status = "AVAILABLE") {
  return { status };
}

function projection({
  runId = RUN_A,
  objectId = OBJECT_A,
  goalId = GOAL_A,
  schemeId = SCHEME_A,
  plannedGraphId = PLANNED_GRAPH_A,
  actualGraphId = ACTUAL_GRAPH_A,
  graphVersion = 1,
  sequence = 10,
  revision = 1,
  tasks = [task(TASK_A, runId)],
  pathChanges = [],
  status = "RUNNING",
  terminalEventId = null
} = {}) {
  const terminal = status === "RELEASED" || status === "FAILED" || status === "CANCELLED";
  const outcome = status === "RELEASED" ? "SUCCESS" : status === "CANCELLED" ? "CANCELLED" : "FAILURE";
  const runMapping = {
    DRAFT: { status: "PREPARING", stage: "PREPARE" },
    SCHEME_GENERATING: { status: "PREPARING", stage: "PREPARE" },
    AWAITING_CONFIRMATION: { status: "AWAITING_CONFIRMATION", stage: "CONFIRM" },
    PLANNING: { status: "PLANNING", stage: "PLANNING" },
    RUNNING: { status: "RESEARCHING", stage: "RESEARCH" },
    REVIEW: { status: "REVIEWING", stage: "REVIEW" },
    PROVING: { status: "PROVING", stage: "PROVING" },
    RELEASED: { status: "COMPLETED", stage: "COMPLETE" },
    FAILED: { status: "FAILED", stage: "FAILED" },
    CANCELLED: { status: "CANCELLED", stage: "CANCELLED" }
  }[status];
  const snapshotTasks = structuredClone(tasks);
  const lifecycleFraction = snapshotTasks.length === 0
    ? 0
    : snapshotTasks.reduce((total, item) => total + item.progress, 0) / snapshotTasks.length;
  const completedTasks = snapshotTasks.filter((item) => item.backendStatus === "COMPLETED").length;
  return {
    projectionSchemaVersion: "phase4-run-projection/v1",
    projectionRevision: revision,
    projectionSequence: sequence,
    generatedAt: NOW,
    object: { objectId },
    goal: { goalId, researchObjectId: objectId },
    confirmedScheme: { schemeId, goalId, researchObjectId: objectId },
    run: {
      runId,
      researchObjectId: objectId,
      goalId,
      schemeId,
      plannedGraphId,
      actualGraphId,
      backendStatus: status,
      status: runMapping.status,
      stage: runMapping.stage,
      terminal
    },
    plannedGraph: { graphId: plannedGraphId, runId, version: 1, tasks: structuredClone(snapshotTasks) },
    actualGraph: {
      graphId: actualGraphId,
      runId,
      version: graphVersion,
      tasks: structuredClone(snapshotTasks)
    },
    graphVersion,
    tasks: snapshotTasks,
    pathChanges: structuredClone(pathChanges),
    activity: [],
    lifecycle: {
      backendStatus: status,
      status: runMapping.status,
      stage: runMapping.stage,
      progress: {
        method: "ACTUAL_TASK_MEAN_V1",
        completedTasks,
        totalTasks: snapshotTasks.length,
        fraction: lifecycleFraction,
        percent: lifecycleFraction * 100
      },
      terminal,
      terminalOutcome: terminal ? outcome : null
    },
    terminal: {
      isTerminal: terminal,
      outcome: terminal ? outcome : null,
      eventId: terminal ? terminalEventId : null,
      sequence: terminal ? sequence : null
    },
    review: { availability: availability(terminal && status !== "RELEASED" ? "UNAVAILABLE" : "AVAILABLE") },
    result: { availability: availability(terminal && status !== "RELEASED" ? "UNAVAILABLE" : "AVAILABLE") },
    artifacts: { availability: availability(terminal && status !== "RELEASED" ? "UNAVAILABLE" : "AVAILABLE") },
    proof: { availability: availability(terminal && status !== "RELEASED" ? "UNAVAILABLE" : "AVAILABLE") },
    execution: { availability: availability(terminal && status !== "RELEASED" ? "UNAVAILABLE" : "AVAILABLE") }
  };
}

function identity(runId = RUN_A) {
  return {
    runId,
    objectId: OBJECT_A,
    goalId: GOAL_A,
    schemeId: SCHEME_A,
    plannedGraphId: PLANNED_GRAPH_A,
    actualGraphId: ACTUAL_GRAPH_A,
    canonicalRecordId: null
  };
}

function wireEvent({
  eventId,
  runId = RUN_A,
  taskId = null,
  type,
  sequence,
  payload = {},
  graphVersion = null,
  effect = RUNTIME_EVENT_EFFECT_BY_TYPE_V1[type],
  projectionRefreshRequired = effect === "REFRESH_PROJECTION" || effect === "TERMINAL",
  extra = {}
}) {
  return {
    event_contract_version: "phase4-runtime-event/v1",
    event_id: eventId,
    run_id: runId,
    task_id: taskId,
    type,
    timestamp: NOW,
    sequence,
    payload_schema_version: 1,
    payload,
    graph_version: graphVersion,
    effect,
    projection_refresh_required: projectionRefreshRequired,
    ...extra
  };
}

function decode(event, context = {}) {
  return decodeRuntimeEventV1(event, {
    expectedRunId: context.expectedRunId ?? RUN_A,
    authoritativeTaskIds: context.authoritativeTaskIds ?? [TASK_A],
    ...(context.frameId === undefined ? {} : { frameId: context.frameId }),
    ...(context.frameType === undefined ? {} : { frameType: context.frameType })
  });
}

function startedState(snapshot = projection()) {
  return beginRuntimeStream(createRunRuntimeState(snapshot, identity(snapshot.run.runId)));
}

function source(state) {
  return { runId: state.runId, streamGeneration: state.streamGeneration };
}

function correctionPathChange() {
  return {
    pathChangeId: "CORRECTION-1",
    sourceId: "CORRECTION-1",
    sourceKind: "CORRECTION",
    changeKind: "SELF_CORRECTION",
    decision: null,
    taskRefs: [TASK_A],
    operations: [],
    graphVersionBefore: null,
    graphVersionAfter: null,
    createdAt: NOW,
    resolvedAt: NOW
  };
}

function replanPathChange({ decision, withMutation = false } = {}) {
  return {
    pathChangeId: "REPLAN-1",
    sourceId: "REPLAN-1",
    sourceKind: "REPLAN",
    changeKind: "ADD_TASK",
    decision,
    taskRefs: withMutation ? [TASK_B] : [TASK_A],
    operations: withMutation
      ? [
          { operation: "add_node", taskId: TASK_B, dependencyTaskId: null },
          { operation: "add_edge", taskId: TASK_B, dependencyTaskId: TASK_A }
        ]
      : [],
    graphVersionBefore: withMutation ? 1 : null,
    graphVersionAfter: withMutation ? 2 : null,
    createdAt: NOW,
    resolvedAt: decision === "PENDING" ? null : NOW
  };
}

function expectIngestionReason(reason) {
  return (error) => error instanceof RuntimeIngestionError && error.reason === reason;
}

// Snapshot N -> exact event N+1; PATCH state never mutates the atomic snapshot.
const initial = projection();
let runtime = startedState(initial);
const runtimeSource = source(runtime);
runtime = markRuntimeStreamOpen(runtime, runtimeSource);
const progress11 = decode(wireEvent({
  eventId: "EVENT-11",
  taskId: TASK_A,
  type: "task.progress",
  sequence: 11,
  payload: { progress: 0.5, progress_scale: "RATIO_0_1", stage: "analysis", message_code: "TASK_PROGRESS" }
}));
const afterProgress = reduceRuntimeEvent(runtime, progress11, runtimeSource);
check(afterProgress.committedSequence, 11, "snapshot at N accepts only N+1");
check(initial.tasks[0].progress, 0.1, "PATCH overlay does not mutate the canonical snapshot");
check(selectRunProjection(afterProgress).tasks[0].progress, 0.5, "valid frozen progress updates the selected projection");
check(selectRunProjection(afterProgress).tasks[0].status, "ACTIVE", "progress retains mapped task status");
check("terminal" in selectRunProjection(afterProgress).tasks[0], false, "Task terminal remains a derived map fact, not an invented field");
check(
  selectRunProjection(afterProgress).lifecycle.progress.fraction,
  0.1,
  "Task PATCH preserves backend-authoritative aggregate Run progress until snapshot refresh"
);

// Exact duplicate is an identity-preserving no-op; conflicts, old events and gaps recover without advancing.
check(reduceRuntimeEvent(afterProgress, progress11, runtimeSource), afterProgress, "exact duplicate is a no-op");
const conflicting11 = { ...progress11, eventId: "EVENT-11-CONFLICT" };
const conflictState = reduceRuntimeEvent(afterProgress, conflicting11, runtimeSource);
check(conflictState.committedSequence, 11, "conflicting duplicate does not advance cursor");
check(conflictState.quarantine.at(-1).reason, "CONFLICTING_DUPLICATE", "conflicting duplicate is quarantined");

const old10 = decode(wireEvent({ eventId: "EVENT-OLD-10", taskId: TASK_A, type: "task.ready", sequence: 10 }));
const oldState = reduceRuntimeEvent(startedState(), old10);
check(oldState.committedSequence, 10, "unseen old event does not advance cursor");
check(oldState.quarantine.at(-1).reason, "OLD_EVENT", "unseen old event is quarantined");

const gap13 = decode(wireEvent({ eventId: "EVENT-GAP-13", taskId: TASK_A, type: "task.ready", sequence: 13 }));
const beforeGap = startedState();
const gapSource = source(beforeGap);
const gapState = reduceRuntimeEvent(beforeGap, gap13, gapSource);
check(gapState.committedSequence, 10, "gap does not advance cursor");
check(gapState.connection.kind, "RECOVERING", "gap requires snapshot recovery");
check(gapState.connection.reason, "SEQUENCE_GAP", "gap retains its typed recovery reason");
const delayed11 = decode(wireEvent({ eventId: "EVENT-DELAYED-11", taskId: TASK_A, type: "task.ready", sequence: 11 }));
check(reduceRuntimeEvent(gapState, delayed11, gapSource), gapState, "old stream callback is inert after gap generation rotates");

const idConflict12 = { ...progress11, sequence: 12 };
const idConflictState = reduceRuntimeEvent(afterProgress, idConflict12, runtimeSource);
check(idConflictState.quarantine.at(-1).reason, "DUPLICATE_EVENT_ID", "event ID cannot move to another sequence");

// Decoder and ingestion guard exact-Run/Task/wire/sequence boundary.
const guard = new RuntimeEventIngestionGuard({
  runId: RUN_A,
  initialSequence: 10,
  authoritativeTaskIds: [TASK_A]
});
check(guard.ingest(wireEvent({ eventId: "GUARD-11", taskId: TASK_A, type: "task.ready", sequence: 11 }), {
  id: "11", event: "task.ready"
}).kind, "APPLIED", "guard applies exact next suffix event");
check(guard.ingest(wireEvent({ eventId: "GUARD-11", taskId: TASK_A, type: "task.ready", sequence: 11 }), {
  id: "11", event: "task.ready"
}).kind, "DUPLICATE", "guard suppresses exact replay");
throws(() => guard.ingest(wireEvent({ eventId: "GUARD-GAP", taskId: TASK_A, type: "task.ready", sequence: 13 })), expectIngestionReason("SEQUENCE_GAP"), "guard rejects gaps");
throws(() => guard.ingest(wireEvent({ eventId: "GUARD-OLD", taskId: TASK_A, type: "task.ready", sequence: 9 })), expectIngestionReason("STALE_EVENT"), "guard rejects unseen old events");
throws(() => decode(wireEvent({ eventId: "WRONG-RUN", runId: RUN_B, taskId: TASK_A, type: "task.ready", sequence: 11 })), expectIngestionReason("WRONG_RUN"), "decoder rejects another Run");
throws(() => decode({ ...wireEvent({ eventId: "MISSING-RUN", taskId: TASK_A, type: "task.ready", sequence: 11 }), run_id: undefined }), expectIngestionReason("MALFORMED_EVENT"), "decoder rejects missing runId");
throws(() => decode(wireEvent({ eventId: "WRONG-TASK", taskId: TASK_B, type: "task.started", sequence: 11, payload: { attempt: 1 } })), expectIngestionReason("WRONG_TASK"), "decoder rejects non-authoritative Task");
throws(() => decode(wireEvent({ eventId: "WIRE-ID", taskId: TASK_A, type: "task.ready", sequence: 11 }), { frameId: "12", frameType: "task.ready" }), expectIngestionReason("WIRE_ID_MISMATCH"), "SSE id must equal data.sequence");
throws(() => decode(wireEvent({ eventId: "WIRE-TYPE", taskId: TASK_A, type: "task.ready", sequence: 11 }), { frameId: "11", frameType: "task.started" }), expectIngestionReason("WIRE_TYPE_MISMATCH"), "SSE event name must equal data.type");
throws(() => decode(wireEvent({ eventId: "UNSUPPORTED", type: "replan.rejected", sequence: 11, effect: undefined })), expectIngestionReason("UNSUPPORTED_EVENT"), "frozen unsupported event is rejected explicitly");
throws(() => decode({ ...wireEvent({ eventId: "UNKNOWN", taskId: TASK_A, type: "task.ready", sequence: 11 }), type: "prototype.task.sparkled" }), expectIngestionReason("UNSUPPORTED_EVENT"), "prototype-only event is rejected");
throws(() => decode({ ...wireEvent({ eventId: "BAD-SEQUENCE", taskId: TASK_A, type: "task.ready", sequence: 11 }), sequence: 1.5 }), expectIngestionReason("MALFORMED_EVENT"), "fractional sequence is rejected");
throws(() => decode({ ...wireEvent({ eventId: "EXTRA-FIELD", taskId: TASK_A, type: "task.ready", sequence: 11 }), prototype_hint: "latest run" }), expectIngestionReason("MALFORMED_EVENT"), "unknown envelope field is rejected");

// Snapshot identity is exact across Run, Object, Task and Graph relations.
const wrongObject = projection();
wrongObject.run.researchObjectId = "OBJECT-FOREIGN";
throws(() => createRunRuntimeState(wrongObject, identity()), RuntimeProjectionError, "wrong Object relation rejects the snapshot");
const wrongTaskRun = projection();
wrongTaskRun.tasks[0].runId = RUN_B;
throws(() => createRunRuntimeState(wrongTaskRun, identity()), RuntimeProjectionError, "wrong Task/Run relation rejects the snapshot");
const wrongGraph = projection();
wrongGraph.actualGraph.graphId = "GRAPH-FOREIGN";
throws(() => createRunRuntimeState(wrongGraph, identity()), RuntimeProjectionError, "wrong actual Graph relation rejects the snapshot");
const fabricatedDependency = projection();
fabricatedDependency.tasks[0].dependencies = ["TASK-NOT-IN-RUN"];
throws(() => createRunRuntimeState(fabricatedDependency, identity()), RuntimeProjectionError, "unknown dependency cannot fabricate a Task");

// Stale/cross-Run callbacks are inert after exact Run/stream generation switch.
const runAState = startedState();
const staleSource = source(runAState);
const runBProjection = projection({
  runId: RUN_B,
  objectId: OBJECT_A,
  tasks: [task(TASK_A, RUN_B)]
});
const runBState = startedState(runBProjection);
const foreignNormalized = { ...progress11, runId: RUN_A };
check(reduceRuntimeEvent(runBState, foreignNormalized, staleSource), runBState, "prior Run source cannot mutate current Run");
const rotated = beginRuntimeStream(runAState, 2);
check(reduceRuntimeEvent(rotated, progress11, staleSource), rotated, "prior stream generation callback is inert");

// Transport state remains separate from authoritative Run business state.
const transportBase = startedState();
const transportSource = source(transportBase);
const envelope = {
  schemaVersion: "phase4-error/v1",
  error: { code: "TEMPORARY_UNAVAILABLE", message: "Try again", retryable: true, recovery: "RETRY" }
};
const backoff = markRuntimeBackoff(transportBase, transportSource, {
  attempt: 2,
  retryAt: "2026-09-05T00:00:10.000Z",
  error: envelope
});
check(backoff.connection.kind, "BACKOFF", "temporary disconnect becomes transport backoff");
check(selectRunProjection(backoff).lifecycle.status, "RESEARCHING", "transport backoff does not fail the Run");
const failedTransport = markRuntimeTransportFailed(transportBase, transportSource, envelope);
check(failedTransport.connection.kind, "FAILED", "non-retryable transport can fail independently");
check(selectRunProjection(failedTransport).lifecycle.status, "RESEARCHING", "transport failure does not overwrite business Run state");

// Gap refresh is an atomic whole-snapshot replacement and cannot mix generations.
const replacementTasks = [task(TASK_B)];
const recoveredSnapshot = projection({ sequence: 13, revision: 2, tasks: replacementTasks });
const recovered = reconcileRunRuntimeState(gapState, recoveredSnapshot);
check(recovered.committedSequence, 13, "replacement snapshot establishes the recovered cursor");
check(recovered.stale, false, "validated replacement clears stale state atomically");
check(recovered.taskOverlays, {}, "replacement clears prior overlays");
check(recovered.projection.tasks.map((item) => item.taskId), [TASK_B], "replacement does not mix Tasks across snapshot generations");
check(initial.tasks.map((item) => item.taskId), [TASK_A], "atomic replacement does not mutate prior snapshot");
throws(() => reconcileRunRuntimeState(gapState, projection({ sequence: 9, revision: 2 })), RuntimeProjectionError, "regressing replacement cursor is rejected");

// Self-Correction remains the same Task and same Graph; resolution is authoritative refresh.
let correctionState = startedState();
const correctionSource = source(correctionState);
const correctingEvent = decode(wireEvent({
  eventId: "CORRECTION-START-11",
  taskId: TASK_A,
  type: "task.self_correcting",
  sequence: 11,
  payload: { problem_code: "PERIOD_ALIGNMENT" }
}));
correctionState = reduceRuntimeEvent(correctionState, correctingEvent, correctionSource);
const correctingView = selectRunProjection(correctionState);
check(correctingView.tasks.length, 1, "Self-Correction creates no Task");
check(correctingView.tasks[0].taskId, TASK_A, "Self-Correction retains exact Task identity");
check(correctingView.tasks[0].status, "CORRECTING", "Self-Correction is visible on the same Task");
check(correctingView.graphVersion, 1, "Self-Correction does not mutate Graph version");
check(correctingView.actualGraph.graphId, ACTUAL_GRAPH_A, "Self-Correction does not replace Graph identity");

const correctionResolved = decode(wireEvent({
  eventId: "CORRECTION-RESOLVED-12",
  taskId: TASK_A,
  type: "task.correction_resolved",
  sequence: 12,
  payload: { correction_id: "CORRECTION-1" }
}));
const correctionPending = reduceRuntimeEvent(correctionState, correctionResolved, correctionSource);
check(selectRunProjection(correctionPending).pathChanges.length, 0, "refresh event does not synthesize correction history");
const correctionSnapshot = projection({
  sequence: 12,
  revision: 2,
  pathChanges: [correctionPathChange()],
  tasks: [task(TASK_A)]
});
const correctionCommitted = reconcileRunRuntimeState(correctionPending, correctionSnapshot);
check(correctionCommitted.projection.pathChanges[0].changeKind, "SELF_CORRECTION", "authoritative snapshot projects correction history");
check(correctionCommitted.projection.graphVersion, 1, "resolved correction retains same Graph");

// Pending/rejected Replan never mutates topology. Approved mutation appears only via replacement snapshot.
let replanState = startedState();
const replanSource = source(replanState);
const requested = decode(wireEvent({
  eventId: "REPLAN-REQUESTED-11",
  taskId: TASK_A,
  type: "replan.requested",
  sequence: 11,
  payload: { replan_id: "REPLAN-1", decision: "PENDING" }
}));
const requestedPending = reduceRuntimeEvent(replanState, requested, replanSource);
check(selectRunProjection(requestedPending).tasks.length, 1, "pending refresh cannot mutate Graph from event payload");
check(selectRunProjection(requestedPending).pathChanges.length, 0, "pending refresh cannot invent Replan decision");
const pendingSnapshot = projection({
  sequence: 11,
  revision: 2,
  pathChanges: [replanPathChange({ decision: "PENDING" })]
});
replanState = reconcileRunRuntimeState(requestedPending, pendingSnapshot);
check(replanState.projection.graphVersion, 1, "pending Replan retains Graph version");
check(replanState.projection.tasks.length, 1, "pending Replan retains Task set");

const rejectedSnapshot = projection({
  sequence: 11,
  revision: 2,
  pathChanges: [replanPathChange({ decision: "REJECTED" })]
});
const rejectedState = createRunRuntimeState(rejectedSnapshot, identity());
check(rejectedState.projection.graphVersion, 1, "rejected Replan retains Graph version");
check(rejectedState.projection.tasks.length, 1, "rejected Replan adds no Task");

replanState = beginRuntimeStream(replanState);
const approvedSource = source(replanState);
const approved = decode(wireEvent({
  eventId: "REPLAN-APPROVED-12",
  taskId: TASK_A,
  type: "replan.approved",
  sequence: 12,
  payload: { replan_id: "REPLAN-1", decided_by: "RESEARCH_LEAD" }
}));
const approvedPending = reduceRuntimeEvent(replanState, approved, approvedSource);
check(selectRunProjection(approvedPending).tasks.length, 1, "approved event alone cannot add a Task");
const mutatedSnapshot = projection({
  sequence: 12,
  revision: 3,
  graphVersion: 2,
  tasks: [task(TASK_A), task(TASK_B, RUN_A, [TASK_A])],
  pathChanges: [replanPathChange({ decision: "APPROVED", withMutation: true })]
});
const mutatedState = reconcileRunRuntimeState(approvedPending, mutatedSnapshot);
check(mutatedState.projection.tasks.map((item) => item.taskId), [TASK_A, TASK_B], "only authoritative replacement introduces dynamic Task");
check(mutatedState.projection.graphVersion, 2, "authoritative replacement advances Graph version");
check(mutatedState.projection.pathChanges[0].sourceKind, "REPLAN", "approved graph change retains Replan authority");

const badCorrection = projection({ pathChanges: [{ ...correctionPathChange(), graphVersionAfter: 2 }] });
throws(() => createRunRuntimeState(badCorrection, identity()), RuntimeProjectionError, "Self-Correction cannot mutate Graph identity");
const badRejected = projection({ pathChanges: [{ ...replanPathChange({ decision: "REJECTED" }), graphVersionAfter: 2 }] });
throws(() => createRunRuntimeState(badRejected, identity()), RuntimeProjectionError, "rejected Replan cannot mutate Graph identity");
const foreignPathTask = projection({ pathChanges: [{ ...replanPathChange({ decision: "PENDING" }), taskRefs: [TASK_B] }] });
throws(() => createRunRuntimeState(foreignPathTask, identity()), RuntimeProjectionError, "path mutation cannot borrow another Run's Task");

// Terminal is authoritative and immutable; no local task-completion heuristic is used.
const allTasksComplete = projection({
  tasks: [{ ...task(TASK_A, RUN_A, [], "COMPLETED"), progress: 1 }]
});
check(createRunRuntimeState(allTasksComplete, identity()).connection.kind, "IDLE", "all Tasks complete does not declare Run terminal");
let terminalState = startedState();
const terminalSource = source(terminalState);
const terminalEvent = decode(wireEvent({
  eventId: "RUN-COMPLETED-11",
  type: "run.completed",
  sequence: 11,
  payload: { status: "RELEASED" }
}));
const terminalPending = reduceRuntimeEvent(terminalState, terminalEvent, terminalSource);
check(terminalPending.connection.kind, "RECOVERING", "terminal event waits for authoritative snapshot");
check(selectRunProjection(terminalPending).lifecycle.status, "RESEARCHING", "terminal event cannot locally declare completion");
terminalState = reconcileRunRuntimeState(terminalPending, projection({
  sequence: 11,
  revision: 2,
  status: "RELEASED",
  terminalEventId: "RUN-COMPLETED-11"
}));
check(terminalState.connection.kind, "TERMINAL", "terminal snapshot closes runtime authoritatively");
check(terminalState.connection.outcome, "SUCCESS", "released terminal outcome is preserved");
const postTerminal = decode(wireEvent({ eventId: "POST-TERMINAL-12", taskId: TASK_A, type: "task.ready", sequence: 12 }));
const postTerminalState = reduceRuntimeEvent(terminalState, postTerminal, {
  runId: RUN_A,
  streamGeneration: terminalState.streamGeneration
});
check(postTerminalState.committedSequence, 11, "post-terminal event does not advance cursor");
check(postTerminalState.quarantine.at(-1).reason, "POST_TERMINAL_EVENT", "post-terminal event is quarantined");
check(postTerminalState.connection.kind, "TERMINAL", "post-terminal event cannot demote authoritative terminal state");

// Cursor syntax and exact accepted-event binding.
check(runtimeCursorHeaderV1(RUN_A, { initialSequence: 10, authoritativeTaskIds: [TASK_A] }), "10", "snapshot sequence is the default cursor");
const accepted10 = decode(wireEvent({ eventId: "OPAQUE.EVENT:10", taskId: TASK_A, type: "task.ready", sequence: 10 }));
check(runtimeCursorHeaderV1(RUN_A, {
  initialSequence: 10,
  resumeCursor: "OPAQUE.EVENT:10",
  authoritativeTaskIds: [TASK_A],
  acceptedEvents: [accepted10]
}), "OPAQUE.EVENT:10", "opaque cursor must bind exact accepted event/Run/sequence");
for (const invalidCursor of ["01", "+10", "10.0", " 10", "10 ", "opaque/bad", "UNKNOWN-OPAQUE"]) {
  throws(() => runtimeCursorHeaderV1(RUN_A, {
    initialSequence: 10,
    resumeCursor: invalidCursor,
    authoritativeTaskIds: [TASK_A],
    acceptedEvents: [accepted10]
  }), RuntimeIngestionError, `invalid cursor ${JSON.stringify(invalidCursor)} is rejected`);
}
throws(() => runtimeCursorHeaderV1(RUN_A, {
  initialSequence: 10,
  resumeCursor: "9",
  authoritativeTaskIds: [TASK_A]
}), expectIngestionReason("SEQUENCE_CONFLICT"), "numeric cursor cannot conflict with snapshot sequence");

// Incremental SSE framing: CR/LF, multiline data, comments and incomplete-frame rejection.
const parsedFrames = [];
const comments = [];
const parser = new SSEFrameParser({
  onFrame: (frame) => parsedFrames.push(frame),
  onComment: (comment) => comments.push(comment)
});
parser.push(": heart");
parser.push("beat\r\nid: 11\r\nevent: task.progress\r\ndata: {\"part\":\r\ndata: true}\r\n\r\n");
parser.finish();
check(comments, ["heartbeat"], "SSE comments survive split chunks");
check(parsedFrames, [{ id: "11", event: "task.progress", data: "{\"part\":\ntrue}" }], "SSE parser joins multiline data exactly");
const incompleteParser = new SSEFrameParser({ onFrame: () => {} });
incompleteParser.push("id: 1\ndata: {}");
throws(() => incompleteParser.finish(), expectIngestionReason("MALFORMED_EVENT"), "truncated SSE frame fails closed");

function terminalCursorResponse(sequence) {
  return new Response(null, {
    status: 200,
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      "X-Phase4-Contract-Version": "phase4-core/v1",
      "X-Phase4-Event-Contract-Version": "phase4-runtime-event/v1",
      "X-Run-Terminal": "true",
      "X-Terminal-Sequence": String(sequence)
    }
  });
}

function eventStreamResponse(events) {
  const encoder = new TextEncoder();
  const bytes = encoder.encode(events.map((event) => [
    `id: ${event.sequence}`,
    `event: ${event.type}`,
    `data: ${JSON.stringify(event)}`,
    "",
    ""
  ].join("\n")).join(""));
  return new Response(new ReadableStream({
    start(controller) {
      // One byte per chunk forces incremental UTF-8 handling across multibyte boundaries.
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
      controller.close();
    }
  }), {
    status: 200,
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      "X-Phase4-Contract-Version": "phase4-core/v1",
      "X-Phase4-Event-Contract-Version": "phase4-runtime-event/v1"
    }
  });
}

// Fetch-stream transport binds exact Run, resumes at N, decodes N+1 and closes on terminal.
const streamProgress11 = wireEvent({
  eventId: "STREAM-11",
  taskId: TASK_A,
  type: "task.progress",
  sequence: 11,
  payload: { progress: 0.6, progress_scale: "RATIO_0_1", message_code: "进展" }
});
const streamTerminal12 = wireEvent({
  eventId: "STREAM-12",
  type: "run.completed",
  sequence: 12,
  payload: { status: "RELEASED" }
});
let requestedUrl;
let requestedInit;
const transportEvents = [];
const transportStates = [];
const transportErrors = [];
const transport = new SSERuntimeTransport({
  basePath: "/api/",
  fetchImplementation: async (url, init) => {
    requestedUrl = String(url);
    requestedInit = init;
    return eventStreamResponse([streamProgress11, streamTerminal12]);
  }
});
const subscription = transport.subscribe(RUN_A, (event) => transportEvents.push(event), (error) => transportErrors.push(error), {
  initialSequence: 10,
  authoritativeTaskIds: [TASK_A],
  onStateChange: (connection) => transportStates.push(connection)
});
await subscription.closed;
check(requestedUrl, `/api/research-runs/${RUN_A}/events`, "transport connects to exact Run route");
check(requestedInit.headers["Last-Event-ID"], "10", "transport resumes from snapshot N");
check(requestedInit.headers["X-Phase4-Contract-Version"], "phase4-core/v1", "transport sends frozen contract version");
check(transportEvents.map((event) => event.sequence), [11, 12], "transport admits exact ordered suffix through terminal");
check(transportEvents[0].payload.messageCode, "进展", "incremental UTF-8 decoder preserves split multibyte text");
check(transportStates.at(-1).kind, "TERMINAL", "terminal event closes transport authoritatively");
check(transportErrors.length, 0, "valid terminal stream has no transport error");

// A pre-terminal EOF is transport backoff, never an invented Run failure/completion.
const disconnectStates = [];
const disconnectErrors = [];
const disconnectTransport = new SSERuntimeTransport({
  now: () => 0,
  fetchImplementation: async () => eventStreamResponse([streamProgress11])
});
const disconnectSubscription = disconnectTransport.subscribe(
  RUN_A,
  () => {},
  (error) => disconnectErrors.push(error),
  {
    initialSequence: 10,
    authoritativeTaskIds: [TASK_A],
    onStateChange: (connection) => disconnectStates.push(connection)
  }
);
await disconnectSubscription.closed;
check(disconnectStates.at(-1).kind, "BACKOFF", "pre-terminal EOF schedules transport backoff");
check(disconnectStates.at(-1).lastSequence, 11, "disconnect backoff retains the last accepted cursor");
check(disconnectErrors.length, 1, "pre-terminal EOF is surfaced once to composition");
check(disconnectErrors[0].code, "TRANSIENT_BACKEND_ERROR", "disconnect uses typed retryable transport error");

let reconnectHeader;
const reconnectEvents = [];
const reconnectStates = [];
const reconnectTransport = new SSERuntimeTransport({
  fetchImplementation: async (_url, init) => {
    reconnectHeader = init.headers["Last-Event-ID"];
    return eventStreamResponse([streamTerminal12]);
  }
});
const reconnectSubscription = reconnectTransport.subscribe(
  RUN_A,
  (event) => reconnectEvents.push(event),
  assert.fail,
  {
    initialSequence: 11,
    authoritativeTaskIds: [TASK_A],
    acceptedEvents: [decode(streamProgress11)],
    attempt: 2,
    onStateChange: (connection) => reconnectStates.push(connection)
  }
);
await reconnectSubscription.closed;
check(reconnectHeader, "11", "reconnect resumes at the last accepted cursor, not zero");
check(reconnectEvents.map((event) => event.sequence), [12], "reconnect applies only the strict remaining suffix");
check(reconnectStates[0].attempt, 2, "reconnect retains the caller-owned attempt number");
check(reconnectStates.at(-1).kind, "TERMINAL", "reconnected suffix reaches authoritative terminal");

// Pre-header cursor rejection remains typed and requests exact snapshot recovery.
const cursorErrorStates = [];
const cursorErrorTransport = new SSERuntimeTransport({
  fetchImplementation: async () => new Response(JSON.stringify({
    schema_version: "phase4-error/v1",
    error: {
      code: "CURSOR_AHEAD",
      message: "Cursor is ahead of the exact Run tail",
      retryable: false,
      recovery: "SNAPSHOT_RELOAD",
      request_id: null,
      resource: { type: "RESEARCH_RUN", id: RUN_A },
      details: {}
    }
  }), {
    status: 409,
    headers: { "content-type": "application/json" }
  })
});
const cursorErrorSubscription = cursorErrorTransport.subscribe(RUN_A, () => {}, () => {}, {
  initialSequence: 10,
  authoritativeTaskIds: [TASK_A],
  onStateChange: (connection) => cursorErrorStates.push(connection)
});
await cursorErrorSubscription.closed;
check(cursorErrorStates.at(-1).kind, "RECOVERING", "CURSOR_AHEAD enters snapshot recovery");
check(cursorErrorStates.at(-1).reason, "CURSOR_REJECTED", "cursor rejection retains typed recovery identity");

// Terminal-at-cursor handshake emits zero frames and closes cleanly.
let terminalAtCursor = null;
const cursorTransport = new SSERuntimeTransport({ fetchImplementation: async () => terminalCursorResponse(10) });
const cursorSubscription = cursorTransport.subscribe(RUN_A, () => assert.fail("terminal cursor emitted a frame"), assert.fail, {
  initialSequence: 10,
  authoritativeTaskIds: [TASK_A],
  onTerminalAtCursor: (sequence) => { terminalAtCursor = sequence; }
});
await cursorSubscription.closed;
check(terminalAtCursor, 10, "terminal-at-cursor metadata closes zero-frame response");

// A second exact-Run subscription invalidates delayed callbacks from the first stream.
let releaseFirst;
const firstResponse = new Promise((resolve) => { releaseFirst = resolve; });
let fetchCount = 0;
const staleEvents = [];
const switchedTerminalRuns = [];
const switchTransport = new SSERuntimeTransport({
  fetchImplementation: async () => {
    fetchCount += 1;
    return fetchCount === 1 ? firstResponse : terminalCursorResponse(10);
  }
});
const staleSubscription = switchTransport.subscribe(RUN_A, (event) => staleEvents.push(event), assert.fail, {
  initialSequence: 10,
  authoritativeTaskIds: [TASK_A]
});
const currentSubscription = switchTransport.subscribe(RUN_B, (event) => staleEvents.push(event), assert.fail, {
  initialSequence: 10,
  authoritativeTaskIds: [TASK_A],
  onTerminalAtCursor: () => switchedTerminalRuns.push(RUN_B)
});
await currentSubscription.closed;
releaseFirst(eventStreamResponse([
  wireEvent({ eventId: "STALE-A-11", runId: RUN_A, taskId: TASK_A, type: "task.ready", sequence: 11 }),
  wireEvent({ eventId: "STALE-A-12", runId: RUN_A, type: "run.completed", sequence: 12, payload: { status: "RELEASED" } })
]));
await staleSubscription.closed;
check(staleEvents.length, 0, "delayed prior-Run transport response is inert after switch");
check(switchedTerminalRuns, [RUN_B], "current exact Run retains transport ownership");

// Malformed/unsupported payloads and diagnostics fail closed without retaining secrets or hidden reasoning.
for (const [field, sentinel] of [["authorization", "Bearer C4-SENTINEL"], ["chain_of_thought", "C4-HIDDEN-REASONING"]]) {
  let failure;
  try {
    decode(wireEvent({
      eventId: `UNSAFE-${field}`,
      taskId: TASK_A,
      type: "task.started",
      sequence: 11,
      payload: { attempt: 1, [field]: sentinel }
    }));
  } catch (error) {
    failure = error;
  }
  ok(failure instanceof RuntimeIngestionError, `${field} payload is rejected`);
  check(JSON.stringify(failure.identity).includes(sentinel), false, `${field} value is absent from safe decoder diagnostics`);
}

const unsafeNormalized = {
  ...progress11,
  eventId: "UNSAFE-NORMALIZED",
  payload: { authorization: "Bearer C4-QUARANTINE-SECRET", chainOfThought: "C4-PRIVATE-COT" },
  effect: "WRONG_EFFECT"
};
const unsafeState = reduceRuntimeEvent(startedState(), unsafeNormalized);
const serializedDiagnostics = JSON.stringify({
  quarantine: unsafeState.quarantine,
  appliedEvents: unsafeState.appliedEvents
});
check(serializedDiagnostics.includes("C4-QUARANTINE-SECRET"), false, "quarantine diagnostics do not retain secret payloads");
check(serializedDiagnostics.includes("C4-PRIVATE-COT"), false, "quarantine diagnostics do not retain hidden reasoning");
ok(runtimeEventFingerprintV1(progress11).length <= 128, "runtime fingerprint is bounded diagnostics metadata");
check(runtimeEventFingerprintV1(progress11).includes("TASK_PROGRESS"), false, "runtime fingerprint does not reproduce event payload");

console.log(`Phase 4 exact-Run runtime acceptance PASS (${checks} checks)`);
