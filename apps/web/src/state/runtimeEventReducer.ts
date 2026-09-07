import type {
  BackendRunStatus,
  BackendTaskStatus,
  ConnectionState,
  ErrorEnvelope,
  NormalizedRuntimeEventV1,
  RunProjection
} from "../types/domain";
import {
  RUN_STATUS_MAP,
  TASK_STATUS_MAP
} from "../types/domain";
import {
  RUNTIME_EVENT_EFFECT_BY_TYPE_V1,
  SUPPORTED_RUNTIME_EVENT_TYPES_V1,
  runtimeEventFingerprintV1
} from "../runtime/RuntimeTransport";
import type { SupportedRuntimeEventTypeV1 } from "../runtime/RuntimeTransport";

const RUN_PROJECTION_VERSION = "phase4-run-projection/v1";
const EVENT_CONTRACT_VERSION = "phase4-runtime-event/v1";
const MAX_EVENT_RECEIPTS = 512;
const MAX_QUARANTINE_RECORDS = 64;

const SUPPORTED_RUNTIME_EVENT_SET = new Set<string>(SUPPORTED_RUNTIME_EVENT_TYPES_V1);
const PATH_CHANGE_KINDS = new Set(["SELF_CORRECTION", "ADD_TASK", "CHANGE_DEPENDENCY"]);
const PATCH_TASK_EVENTS = new Set([
  "task.ready",
  "task.started",
  "task.progress",
  "task.waiting_for_capability",
  "task.resumed",
  "task.self_correcting",
  "task.completed",
  "task.failed"
]);
const GRAPH_EVENTS = new Set([
  "graph.task_added",
  "graph.edge_added",
  "graph.edge_removed",
  "graph.version_changed"
]);

type UnknownRecord = Record<string, unknown>;
type RunBackendStatus = BackendRunStatus;
type TaskBackendStatus = BackendTaskStatus;
type RunDisplayStatus = (typeof RUN_STATUS_MAP)[RunBackendStatus]["status"];
type RunStage = (typeof RUN_STATUS_MAP)[RunBackendStatus]["stage"];
type TaskDisplayStatus = (typeof TASK_STATUS_MAP)[TaskBackendStatus]["status"];
type RecoveryReason = Extract<ConnectionState, { kind: "RECOVERING" }>["reason"];

export interface ExactRunIdentity {
  readonly runId: string;
  readonly objectId?: string;
  readonly goalId?: string;
  readonly schemeId?: string;
  readonly plannedGraphId?: string;
  readonly actualGraphId?: string | null;
  readonly canonicalRecordId?: string | null;
}

export type RuntimeQuarantineReason =
  | "SCHEMA_INCOMPATIBLE"
  | "UNSUPPORTED_EVENT"
  | "WRONG_RUN"
  | "WRONG_TASK"
  | "SEQUENCE_GAP"
  | "OLD_EVENT"
  | "CONFLICTING_DUPLICATE"
  | "DUPLICATE_EVENT_ID"
  | "GRAPH_IDENTITY_MISMATCH"
  | "POST_TERMINAL_EVENT"
  | "PROJECTION_MISMATCH";

export interface RuntimeEventReceipt {
  readonly eventId: string;
  readonly sequence: number;
  readonly type: string;
  readonly fingerprint: string;
}

export interface RuntimeQuarantineRecord {
  readonly reason: RuntimeQuarantineReason;
  readonly expectedRunId: string;
  readonly eventId: string | null;
  readonly observedRunId: string | null;
  readonly sequence: number | null;
  readonly type: string | null;
  readonly fingerprint: string;
}

interface RuntimeTaskOverlay {
  readonly backendStatus?: TaskBackendStatus;
  readonly status?: TaskDisplayStatus;
  readonly progress?: number;
  readonly attemptCount?: number;
  readonly problemCode?: string;
}

interface RuntimeRunOverlay {
  readonly backendStatus: RunBackendStatus;
  readonly status: RunDisplayStatus;
  readonly stage: RunStage;
  readonly terminal: boolean;
}

interface PendingProjectionRefresh {
  readonly receipt: RuntimeEventReceipt;
  readonly graphVersion: number | null;
  readonly terminal: boolean;
}

export interface RunRuntimeState {
  /** Last atomically decoded Backend snapshot. It is never partially mutated. */
  readonly projection: RunProjection;
  readonly identity: ExactRunIdentity;
  readonly runId: string;
  readonly committedSequence: number;
  readonly streamGeneration: number;
  readonly connection: ConnectionState;
  readonly stale: boolean;
  readonly taskOverlays: Readonly<Record<string, RuntimeTaskOverlay>>;
  readonly runOverlay: RuntimeRunOverlay | null;
  readonly appliedEvents: readonly RuntimeEventReceipt[];
  readonly quarantine: readonly RuntimeQuarantineRecord[];
  readonly pendingRefresh: PendingProjectionRefresh | null;
}

export interface RuntimeEventSource {
  readonly runId: string;
  readonly streamGeneration: number;
}

export class RuntimeProjectionError extends Error {
  readonly code = "PROJECTION_MISMATCH";

  constructor(message: string) {
    super(message);
    this.name = "RuntimeProjectionError";
  }
}

/**
 * Establish one exact-Run runtime from a decoded AtomicRunProjectionV1.
 * This is a second identity gate, not a replacement for the B-owned wire decoder.
 */
export function createRunRuntimeState(
  projection: RunProjection,
  expected: ExactRunIdentity
): RunRuntimeState {
  const snapshot = inspectProjection(projection, expected);
  const connection: ConnectionState = snapshot.terminal
    ? {
        kind: "TERMINAL",
        runId: expected.runId,
        lastSequence: snapshot.sequence,
        outcome: snapshot.terminalOutcome
      }
    : { kind: "IDLE", runId: expected.runId, lastSequence: snapshot.sequence };

  return {
    projection,
    identity: Object.freeze({ ...expected, canonicalRecordId: snapshot.canonicalRecordId }),
    runId: expected.runId,
    committedSequence: snapshot.sequence,
    streamGeneration: 0,
    connection,
    stale: false,
    taskOverlays: Object.freeze({}),
    runOverlay: null,
    appliedEvents: Object.freeze([]),
    quarantine: Object.freeze([]),
    pendingRefresh: null
  };
}

/** Rotate the exact-Run stream generation. Callbacks from older generations become inert. */
export function beginRuntimeStream(state: RunRuntimeState, attempt = 1): RunRuntimeState {
  if (state.connection.kind === "TERMINAL") return state;
  if (state.connection.kind === "RECOVERING" || state.pendingRefresh !== null) return state;
  const streamGeneration = state.streamGeneration + 1;
  return {
    ...state,
    streamGeneration,
    connection: {
      kind: "CONNECTING",
      runId: state.runId,
      lastSequence: state.committedSequence,
      attempt
    }
  };
}

export function markRuntimeStreamOpen(
  state: RunRuntimeState,
  source: RuntimeEventSource
): RunRuntimeState {
  if (!isCurrentSource(state, source) || state.connection.kind === "TERMINAL") return state;
  return {
    ...state,
    stale: false,
    connection: {
      kind: "OPEN",
      runId: state.runId,
      lastSequence: state.committedSequence,
      lastHeartbeatAt: null
    }
  };
}

export function recordRuntimeHeartbeat(
  state: RunRuntimeState,
  source: RuntimeEventSource,
  timestamp: string
): RunRuntimeState {
  if (!isCurrentSource(state, source) || state.connection.kind !== "OPEN") return state;
  if (!isUtcTimestamp(timestamp)) return state;
  return { ...state, connection: { ...state.connection, lastHeartbeatAt: timestamp } };
}

/** Transport loss changes only ConnectionState; authoritative Run lifecycle is retained. */
export function markRuntimeBackoff(
  state: RunRuntimeState,
  source: RuntimeEventSource,
  options: { readonly attempt: number; readonly retryAt: string; readonly error: ErrorEnvelope }
): RunRuntimeState {
  if (!isCurrentSource(state, source) || state.connection.kind === "TERMINAL") return state;
  return {
    ...state,
    stale: true,
    connection: {
      kind: "BACKOFF",
      runId: state.runId,
      lastSequence: state.committedSequence,
      attempt: options.attempt,
      retryAt: options.retryAt,
      error: options.error
    }
  };
}

export function markRuntimeTransportFailed(
  state: RunRuntimeState,
  source: RuntimeEventSource,
  error: ErrorEnvelope
): RunRuntimeState {
  if (!isCurrentSource(state, source) || state.connection.kind === "TERMINAL") return state;
  return {
    ...state,
    stale: true,
    connection: {
      kind: "FAILED",
      runId: state.runId,
      lastSequence: state.committedSequence,
      error
    }
  };
}

/**
 * Apply one already-decoded event. Exact duplicates are no-ops. Any identity/order/
 * schema conflict quarantines safe metadata, advances no cursor, and requests one
 * atomic snapshot recovery. Refresh/terminal events are held pending until that
 * snapshot is validated and installed by reconcileRunRuntimeState.
 */
export function reduceRuntimeEvent(
  state: RunRuntimeState,
  event: NormalizedRuntimeEventV1,
  source: RuntimeEventSource = {
    runId: state.runId,
    streamGeneration: state.streamGeneration
  }
): RunRuntimeState {
  if (!isCurrentSource(state, source)) return state;

  const envelope = recordOf(event);
  const eventId = optionalString(envelope, "eventId");
  const observedRunId = optionalString(envelope, "runId");
  const sequence = optionalInteger(envelope, "sequence");
  const type = optionalString(envelope, "type");
  const fingerprint = safeFingerprint(event);

  if (optionalString(envelope, "eventContractVersion") !== EVENT_CONTRACT_VERSION) {
    return quarantine(state, "SCHEMA_INCOMPATIBLE", event, fingerprint, "SCHEMA_INCOMPATIBLE");
  }
  if (envelope.payloadSchemaVersion !== 1 || !eventId || !observedRunId || !sequence || !type) {
    return quarantine(state, "SCHEMA_INCOMPATIBLE", event, fingerprint, "SCHEMA_INCOMPATIBLE");
  }
  if (observedRunId !== state.runId) {
    if (state.connection.kind === "TERMINAL") {
      return quarantineTerminalEvent(state, event, fingerprint, "WRONG_RUN");
    }
    return quarantine(state, "WRONG_RUN", event, fingerprint, "PROJECTION_MISMATCH");
  }

  const receiptAtSequence = state.appliedEvents.find((receipt) => receipt.sequence === sequence);
  if (
    receiptAtSequence
    && receiptAtSequence.eventId === eventId
    && receiptAtSequence.fingerprint === fingerprint
  ) {
    return state;
  }
  const receiptForId = state.appliedEvents.find((receipt) => receipt.eventId === eventId);
  if (state.connection.kind === "TERMINAL") {
    return quarantineTerminalEvent(
      state,
      event,
      fingerprint,
      receiptAtSequence
        ? "CONFLICTING_DUPLICATE"
        : receiptForId
          ? "DUPLICATE_EVENT_ID"
          : "POST_TERMINAL_EVENT"
    );
  }
  if (receiptAtSequence) {
    return quarantine(state, "CONFLICTING_DUPLICATE", event, fingerprint, "SEQUENCE_GAP");
  }
  if (receiptForId) {
    return quarantine(state, "DUPLICATE_EVENT_ID", event, fingerprint, "SEQUENCE_GAP");
  }
  if (sequence < state.committedSequence + 1) {
    return quarantine(state, "OLD_EVENT", event, fingerprint, "SEQUENCE_GAP");
  }
  if (sequence > state.committedSequence + 1) {
    return quarantine(state, "SEQUENCE_GAP", event, fingerprint, "SEQUENCE_GAP");
  }

  if (!SUPPORTED_RUNTIME_EVENT_SET.has(type)) {
    return quarantine(state, "UNSUPPORTED_EVENT", event, fingerprint, "UNKNOWN_EVENT");
  }
  const supportedType = type as SupportedRuntimeEventTypeV1;
  const expectedEffect = RUNTIME_EVENT_EFFECT_BY_TYPE_V1[supportedType];
  if (
    event.effect !== expectedEffect
    || event.projectionRefreshRequired !== (expectedEffect === "REFRESH_PROJECTION" || expectedEffect === "TERMINAL")
  ) {
    return quarantine(state, "SCHEMA_INCOMPATIBLE", event, fingerprint, "SCHEMA_INCOMPATIBLE");
  }

  const taskId = optionalString(envelope, "taskId");
  if (PATCH_TASK_EVENTS.has(type) && (!taskId || !projectionTaskIds(state.projection).has(taskId))) {
    return quarantine(state, "WRONG_TASK", event, fingerprint, "PROJECTION_MISMATCH");
  }

  const graphVersion = envelope.graphVersion === null ? null : optionalInteger(envelope, "graphVersion");
  if ((GRAPH_EVENTS.has(type) || type === "run.started") && graphVersion === null) {
    return quarantine(state, "GRAPH_IDENTITY_MISMATCH", event, fingerprint, "PROJECTION_MISMATCH");
  }
  if (!GRAPH_EVENTS.has(type) && type !== "run.started" && envelope.graphVersion !== null) {
    return quarantine(state, "GRAPH_IDENTITY_MISMATCH", event, fingerprint, "PROJECTION_MISMATCH");
  }
  const currentGraphVersion = projectionGraphVersion(state.projection);
  if (
    type === "run.started"
    && (currentGraphVersion === null || graphVersion !== currentGraphVersion)
  ) {
    return quarantine(state, "GRAPH_IDENTITY_MISMATCH", event, fingerprint, "PROJECTION_MISMATCH");
  }
  if (
    GRAPH_EVENTS.has(type)
    && currentGraphVersion !== null
    && graphVersion !== null
    && graphVersion < currentGraphVersion
  ) {
    return quarantine(state, "GRAPH_IDENTITY_MISMATCH", event, fingerprint, "PROJECTION_MISMATCH");
  }

  const receipt: RuntimeEventReceipt = Object.freeze({ eventId, sequence, type, fingerprint });
  if (expectedEffect === "REFRESH_PROJECTION" || expectedEffect === "TERMINAL") {
    return {
      ...state,
      streamGeneration: state.streamGeneration + 1,
      stale: true,
      pendingRefresh: { receipt, graphVersion, terminal: expectedEffect === "TERMINAL" },
      connection: {
        kind: "RECOVERING",
        runId: state.runId,
        lastSequence: state.committedSequence,
        reason: "PROJECTION_MISMATCH"
      }
    };
  }

  const taskOverlays = expectedEffect === "PATCH_PROJECTION"
    ? patchTaskOverlay(state.taskOverlays, event, taskId)
    : state.taskOverlays;
  const runOverlay = expectedEffect === "PATCH_PROJECTION"
    ? patchRunOverlay(state.runOverlay, event)
    : state.runOverlay;
  const appliedEvents = appendBounded(state.appliedEvents, receipt, MAX_EVENT_RECEIPTS);

  return {
    ...state,
    committedSequence: sequence,
    taskOverlays,
    runOverlay,
    appliedEvents,
    connection: advanceConnectionSequence(state.connection, sequence)
  };
}

/** Atomically replace the old snapshot after a refresh/gap/reconnect. */
export function reconcileRunRuntimeState(
  state: RunRuntimeState,
  replacement: RunProjection
): RunRuntimeState {
  const snapshot = inspectProjection(replacement, state.identity);
  const previous = inspectProjection(state.projection, state.identity);
  const requiredSequence = state.pendingRefresh?.receipt.sequence ?? state.committedSequence;

  if (snapshot.sequence < state.committedSequence || snapshot.sequence < requiredSequence) {
    throw new RuntimeProjectionError("replacement snapshot regresses the accepted Run cursor");
  }
  if (snapshot.revision < previous.revision) {
    throw new RuntimeProjectionError("replacement snapshot regresses projection revision");
  }
  if (snapshot.sequence > previous.sequence && snapshot.revision <= previous.revision) {
    throw new RuntimeProjectionError("advanced event watermark requires an advanced projection revision");
  }
  if (
    state.pendingRefresh?.graphVersion !== null
    && state.pendingRefresh?.graphVersion !== undefined
    && (snapshot.graphVersion === null || snapshot.graphVersion < state.pendingRefresh.graphVersion)
  ) {
    throw new RuntimeProjectionError("replacement snapshot does not include the graph event version");
  }
  if (state.pendingRefresh?.terminal && !snapshot.terminal) {
    throw new RuntimeProjectionError("terminal event requires an authoritative terminal snapshot");
  }

  const appliedEvents = state.pendingRefresh
    ? appendBounded(state.appliedEvents, state.pendingRefresh.receipt, MAX_EVENT_RECEIPTS)
    : state.appliedEvents;
  const connection: ConnectionState = snapshot.terminal
    ? {
        kind: "TERMINAL",
        runId: state.runId,
        lastSequence: snapshot.sequence,
        outcome: snapshot.terminalOutcome
      }
    : { kind: "IDLE", runId: state.runId, lastSequence: snapshot.sequence };

  return {
    ...state,
    projection: replacement,
    identity: Object.freeze({ ...state.identity, canonicalRecordId: snapshot.canonicalRecordId }),
    committedSequence: snapshot.sequence,
    streamGeneration: state.streamGeneration + 1,
    connection,
    stale: false,
    taskOverlays: Object.freeze({}),
    runOverlay: null,
    appliedEvents,
    pendingRefresh: null
  };
}

/** Build a view from the atomic snapshot plus validated PATCH overlays. */
export function selectRunProjection(state: RunRuntimeState): RunProjection {
  if (!state.runOverlay && Object.keys(state.taskOverlays).length === 0) return state.projection;
  const projection = structuredClone(state.projection);
  const root = requiredRecord(projection, "projection");

  if (state.runOverlay) {
    applyRunOverlay(requiredNestedRecord(root, "run", "projection"), state.runOverlay);
    applyRunOverlay(requiredNestedRecord(root, "lifecycle", "projection"), state.runOverlay);
  }

  applyTaskOverlays(root.tasks, state.taskOverlays);
  const actualGraph = recordOrNull(root.actualGraph);
  if (actualGraph) applyTaskOverlays(actualGraph.tasks, state.taskOverlays);
  return projection;
}

function patchTaskOverlay(
  current: Readonly<Record<string, RuntimeTaskOverlay>>,
  event: NormalizedRuntimeEventV1,
  taskId: string | null
): Readonly<Record<string, RuntimeTaskOverlay>> {
  if (!taskId) return current;
  const payload = recordOf(event.payload);
  const previous = current[taskId] ?? {};
  let patch: RuntimeTaskOverlay = previous;

  switch (event.type) {
    case "task.ready":
      patch = taskStatusPatch("READY", previous);
      break;
    case "task.started":
      patch = {
        ...taskStatusPatch("RUNNING", previous),
        attemptCount: optionalInteger(payload, "attempt") ?? previous.attemptCount
      };
      break;
    case "task.progress":
      // The frozen PROGRESS form is discriminated structurally by `progress` and
      // `progressScale`; RETRY_SCHEDULED contains only `attempt` and `errorCode`.
      // C1 has already validated that exactly one of those forms is present.
      if ("progress" in payload) {
        const progress = optionalRatio(payload, "progress");
        patch = {
          ...taskStatusPatch("RUNNING", previous),
          ...(progress === null ? {} : { progress })
        };
      }
      break;
    case "task.waiting_for_capability":
      patch = taskStatusPatch("WAITING_FOR_CAPABILITY", previous);
      break;
    case "task.resumed":
      patch = taskStatusPatch("RUNNING", previous);
      break;
    case "task.self_correcting":
      patch = {
        ...taskStatusPatch("SELF_CORRECTING", previous),
        problemCode: optionalString(payload, "problemCode") ?? previous.problemCode
      };
      break;
    case "task.completed":
      patch = { ...taskStatusPatch("COMPLETED", previous), progress: 1 };
      break;
    case "task.failed": {
      const status = payload.status === "CAPABILITY_BUILD_FAILED"
        ? "CAPABILITY_BUILD_FAILED"
        : payload.status === "CANCELLED"
          ? "CANCELLED"
          : "FAILED";
      patch = taskStatusPatch(status, previous);
      break;
    }
  }
  return Object.freeze({ ...current, [taskId]: Object.freeze(patch) });
}

function patchRunOverlay(
  current: RuntimeRunOverlay | null,
  event: NormalizedRuntimeEventV1
): RuntimeRunOverlay | null {
  if (event.type === "run.started") return runStatusPatch("RUNNING");
  if (event.type !== "run.status_changed") return current;
  const status = optionalString(recordOf(event.payload), "status");
  return status && status in RUN_STATUS_MAP ? runStatusPatch(status as RunBackendStatus) : current;
}

function taskStatusPatch(status: TaskBackendStatus, previous: RuntimeTaskOverlay): RuntimeTaskOverlay {
  const mapped = TASK_STATUS_MAP[status];
  return {
    ...previous,
    backendStatus: status,
    status: mapped.status
  };
}

function runStatusPatch(status: RunBackendStatus): RuntimeRunOverlay {
  const mapped = RUN_STATUS_MAP[status];
  return {
    backendStatus: status,
    status: mapped.status,
    stage: mapped.stage,
    terminal: mapped.terminal
  };
}

function applyRunOverlay(target: UnknownRecord, patch: RuntimeRunOverlay) {
  target.backendStatus = patch.backendStatus;
  target.status = patch.status;
  target.stage = patch.stage;
  if ("terminal" in target && typeof target.terminal === "boolean") target.terminal = patch.terminal;
}

function applyTaskOverlays(value: unknown, overlays: Readonly<Record<string, RuntimeTaskOverlay>>) {
  if (!Array.isArray(value)) return;
  for (const candidate of value) {
    const task = recordOrNull(candidate);
    if (!task) continue;
    const taskId = optionalString(task, "taskId");
    if (!taskId) continue;
    const patch = overlays[taskId];
    if (!patch) continue;
    if (patch.backendStatus) {
      task.backendStatus = patch.backendStatus;
    }
    if (patch.status) task.status = patch.status;
    if (patch.progress !== undefined) {
      if (typeof task.progress === "number") task.progress = patch.progress;
      else {
        const progress = recordOrNull(task.progress);
        if (progress) {
          progress.fraction = patch.progress;
          progress.percent = patch.progress * 100;
        }
      }
    }
    if (patch.attemptCount !== undefined) task.attemptCount = patch.attemptCount;
  }
}

function inspectProjection(projection: RunProjection, expected: ExactRunIdentity) {
  const root = requiredRecord(projection, "projection");
  if (root.projectionSchemaVersion !== RUN_PROJECTION_VERSION) {
    throw new RuntimeProjectionError("unexpected Run projection schema version");
  }
  const revision = requiredPositiveInteger(root, "projectionRevision", "projection");
  const sequence = requiredNonNegativeInteger(root, "projectionSequence", "projection");
  requiredUtcTimestamp(root, "generatedAt", "projection");

  const object = requiredNestedRecord(root, "object", "projection");
  const run = requiredNestedRecord(root, "run", "projection");
  const goal = requiredNestedRecord(root, "goal", "projection");
  const scheme = requiredNestedRecord(root, "confirmedScheme", "projection");
  const plannedGraph = requiredNestedRecord(root, "plannedGraph", "projection");
  const objectId = requiredString(object, "objectId", "projection.object");
  const runId = requiredString(run, "runId", "projection.run");
  const goalId = requiredString(run, "goalId", "projection.run");
  const schemeId = requiredString(run, "schemeId", "projection.run");
  const plannedGraphId = requiredString(run, "plannedGraphId", "projection.run");

  requireEqual(runId, expected.runId, "route Run and projection Run");
  requireEqual(requiredString(run, "researchObjectId", "projection.run"), objectId, "Run and Object");
  requireEqual(requiredString(goal, "goalId", "projection.goal"), goalId, "Run and Goal");
  requireEqual(requiredString(goal, "researchObjectId", "projection.goal"), objectId, "Goal and Object");
  requireEqual(requiredString(scheme, "schemeId", "projection.confirmedScheme"), schemeId, "Run and Scheme");
  requireEqual(requiredString(scheme, "goalId", "projection.confirmedScheme"), goalId, "Scheme and Goal");
  requireEqual(
    requiredString(scheme, "researchObjectId", "projection.confirmedScheme"),
    objectId,
    "Scheme and Object"
  );
  requireEqual(requiredString(plannedGraph, "graphId", "projection.plannedGraph"), plannedGraphId, "Run and planned Graph");
  requireEqual(requiredString(plannedGraph, "runId", "projection.plannedGraph"), runId, "planned Graph and Run");

  const runBackendStatus = requiredBackendRunStatus(run, "backendStatus", "projection.run");
  const mappedRun = RUN_STATUS_MAP[runBackendStatus];
  requireEqual(requiredString(run, "status", "projection.run"), mappedRun.status, "Run status map");
  requireEqual(requiredString(run, "stage", "projection.run"), mappedRun.stage, "Run stage map");
  requireEqual(requiredBoolean(run, "terminal", "projection.run"), mappedRun.terminal, "Run terminal map");

  if (expected.objectId) requireEqual(objectId, expected.objectId, "expected Object");
  if (expected.goalId) requireEqual(goalId, expected.goalId, "expected Goal");
  if (expected.schemeId) requireEqual(schemeId, expected.schemeId, "expected Scheme");
  if (expected.plannedGraphId) requireEqual(plannedGraphId, expected.plannedGraphId, "expected planned Graph");

  const tasks = requiredArray(root, "tasks", "projection");
  const taskIds = new Set<string>();
  const dependencies = new Map<string, readonly string[]>();
  for (const value of tasks) {
    const task = requiredRecord(value, "projection task");
    const taskId = requiredString(task, "taskId", "projection task");
    if (taskIds.has(taskId)) throw new RuntimeProjectionError("projection contains duplicate Task identity");
    taskIds.add(taskId);
    requireEqual(requiredString(task, "runId", "projection task"), runId, "Task and Run");
    const rawStatus = requiredBackendTaskStatus(task, "backendStatus", "projection task");
    const mappedTask = TASK_STATUS_MAP[rawStatus];
    requireEqual(requiredString(task, "status", "projection task"), mappedTask.status, "Task status map");
    requiredRatio(task, "progress", "projection task");
    requiredNonNegativeInteger(task, "attemptCount", "projection task");
    dependencies.set(taskId, requiredStringArray(task, "dependencies", "projection task"));
  }
  for (const [taskId, taskDependencies] of dependencies) {
    if (taskDependencies.some((dependency) => !taskIds.has(dependency))) {
      throw new RuntimeProjectionError(`Task ${taskId} has an unknown dependency`);
    }
  }
  requiredPositiveInteger(plannedGraph, "version", "projection.plannedGraph");
  validateGraphTaskClosure(plannedGraph, runId, "projection.plannedGraph");

  const actualGraph = recordOrNull(root.actualGraph);
  const graphVersion = root.graphVersion === null
    ? null
    : requiredPositiveInteger(root, "graphVersion", "projection");
  if (actualGraph === null) {
    if (root.actualGraph !== null || graphVersion !== null) {
      throw new RuntimeProjectionError("actual Graph and graph version nullability disagree");
    }
    if (run.actualGraphId !== null) {
      throw new RuntimeProjectionError("Run exposes an actual Graph ID without an actual Graph");
    }
    if (expected.actualGraphId) throw new RuntimeProjectionError("expected actual Graph is unavailable");
  } else {
    if (expected.actualGraphId === null) {
      throw new RuntimeProjectionError("projection unexpectedly exposes an actual Graph");
    }
    const actualGraphId = requiredString(actualGraph, "graphId", "projection.actualGraph");
    requireEqual(requiredString(actualGraph, "runId", "projection.actualGraph"), runId, "actual Graph and Run");
    requireEqual(requiredString(run, "actualGraphId", "projection.run"), actualGraphId, "Run and actual Graph");
    requireEqual(requiredPositiveInteger(actualGraph, "version", "projection.actualGraph"), graphVersion, "actual Graph version");
    if (expected.actualGraphId) requireEqual(actualGraphId, expected.actualGraphId, "expected actual Graph");
    validateActualGraphTasks(actualGraph, tasks, runId);
  }

  for (const value of requiredArray(root, "pathChanges", "projection")) {
    validatePathChange(value, taskIds, graphVersion);
  }
  const canonicalRecordId = validateCanonicalRecord(root, expected.canonicalRecordId);

  const lifecycle = requiredNestedRecord(root, "lifecycle", "projection");
  const terminalState = requiredNestedRecord(root, "terminal", "projection");
  const backendStatus = requiredBackendRunStatus(
    lifecycle,
    "backendStatus",
    "projection.lifecycle"
  );
  const mappedLifecycle = RUN_STATUS_MAP[backendStatus];
  requireEqual(backendStatus, runBackendStatus, "Run and lifecycle backend status");
  requireEqual(
    requiredString(lifecycle, "status", "projection.lifecycle"),
    mappedLifecycle.status,
    "lifecycle status map"
  );
  requireEqual(
    requiredString(lifecycle, "stage", "projection.lifecycle"),
    mappedLifecycle.stage,
    "lifecycle stage map"
  );
  const terminal = requiredBoolean(terminalState, "isTerminal", "projection.terminal");
  if (terminal !== requiredBoolean(lifecycle, "terminal", "projection.lifecycle")) {
    throw new RuntimeProjectionError("terminal projections disagree");
  }
  if (terminal !== mappedLifecycle.terminal) {
    throw new RuntimeProjectionError("Run status and terminal marker disagree");
  }

  let terminalOutcome: "SUCCESS" | "FAILURE" | "CANCELLED";
  if (terminal) {
    terminalOutcome = backendStatus === "RELEASED"
      ? "SUCCESS"
      : backendStatus === "CANCELLED"
        ? "CANCELLED"
        : "FAILURE";
    if (terminalState.outcome !== terminalOutcome || lifecycle.terminalOutcome !== terminalOutcome) {
      throw new RuntimeProjectionError("Run terminal outcome is inconsistent");
    }
    if (requiredPositiveInteger(terminalState, "sequence", "projection.terminal") !== sequence) {
      throw new RuntimeProjectionError("terminal event must be the projection tail");
    }
    requiredString(terminalState, "eventId", "projection.terminal");
    validateTerminalAvailability(root);
  } else {
    terminalOutcome = "FAILURE";
    if (
      terminalState.outcome !== null
      || terminalState.eventId !== null
      || terminalState.sequence !== null
      || lifecycle.terminalOutcome !== null
    ) {
      throw new RuntimeProjectionError("nonterminal Run contains terminal identity");
    }
  }

  return { revision, sequence, graphVersion, terminal, terminalOutcome, canonicalRecordId };
}

function validatePathChange(
  value: unknown,
  taskIds: ReadonlySet<string>,
  currentGraphVersion: number | null
) {
  const change = requiredRecord(value, "path change");
  const pathChangeId = requiredString(change, "pathChangeId", "path change");
  requireEqual(requiredString(change, "sourceId", "path change"), pathChangeId, "path change source");
  const sourceKind = requiredString(change, "sourceKind", "path change");
  if (sourceKind !== "CORRECTION" && sourceKind !== "REPLAN") {
    throw new RuntimeProjectionError("unknown path change source kind");
  }
  const changeKind = requiredString(change, "changeKind", "path change");
  if (!PATH_CHANGE_KINDS.has(changeKind)) throw new RuntimeProjectionError("unknown path change kind");
  const taskRefs = requiredStringArray(change, "taskRefs", "path change");
  if (new Set(taskRefs).size !== taskRefs.length) {
    throw new RuntimeProjectionError("path change repeats a Task reference");
  }
  if (taskRefs.some((taskId) => !taskIds.has(taskId))) {
    throw new RuntimeProjectionError("path change references an unknown Task");
  }
  const operations = requiredArray(change, "operations", "path change");
  const operationRefs: string[] = [];
  for (const candidate of operations) {
    const operation = requiredRecord(candidate, "path change operation");
    const kind = requiredString(operation, "operation", "path change operation");
    if (kind !== "add_node" && kind !== "add_edge" && kind !== "remove_edge") {
      throw new RuntimeProjectionError("path change contains an unknown graph operation");
    }
    const taskId = requiredString(operation, "taskId", "path change operation");
    operationRefs.push(taskId);
    if (kind === "add_node") {
      if (operation.dependencyTaskId !== null) {
        throw new RuntimeProjectionError("add_node cannot carry a dependency Task");
      }
    } else {
      const dependencyTaskId = requiredString(
        operation,
        "dependencyTaskId",
        "path change operation"
      );
      operationRefs.push(dependencyTaskId);
    }
  }
  const graphVersionBefore = nullablePositiveInteger(
    change,
    "graphVersionBefore",
    "path change"
  );
  const graphVersionAfter = nullablePositiveInteger(
    change,
    "graphVersionAfter",
    "path change"
  );
  requiredUtcTimestamp(change, "createdAt", "path change");
  if (change.resolvedAt !== null) requiredUtcTimestamp(change, "resolvedAt", "path change");
  if (sourceKind === "CORRECTION") {
    if (changeKind !== "SELF_CORRECTION") {
      throw new RuntimeProjectionError("Correction cannot become a graph mutation");
    }
    if (taskRefs.length !== 1 || operations.length !== 0) {
      throw new RuntimeProjectionError("Self-Correction must remain on one existing Task");
    }
    if (change.decision !== null) {
      throw new RuntimeProjectionError("Correction cannot carry a Replan decision");
    }
    if (graphVersionBefore !== null || graphVersionAfter !== null) {
      throw new RuntimeProjectionError("Self-Correction must retain the same Graph identity");
    }
    return;
  }

  if (changeKind === "SELF_CORRECTION") {
    throw new RuntimeProjectionError("Replan cannot masquerade as Self-Correction");
  }
  const decision = requiredString(change, "decision", "path change");
  if (decision !== "PENDING" && decision !== "APPROVED" && decision !== "REJECTED") {
    throw new RuntimeProjectionError("unknown Replan decision");
  }
  if (decision !== "APPROVED") {
    if (graphVersionAfter !== null) {
      throw new RuntimeProjectionError("pending/rejected Replan cannot mutate the Graph");
    }
    return;
  }
  if (
    graphVersionBefore === null
    || graphVersionAfter === null
    || graphVersionAfter <= graphVersionBefore
    || currentGraphVersion === null
    || graphVersionAfter > currentGraphVersion
  ) {
    throw new RuntimeProjectionError("approved Replan has invalid Graph version closure");
  }
  if (operations.length === 0 || operationRefs.some((taskId) => !taskIds.has(taskId))) {
    throw new RuntimeProjectionError("approved Replan operation references an unknown Task");
  }
}

function validateCanonicalRecord(root: UnknownRecord, expected: string | null | undefined) {
  const observed = new Set<string>();
  for (const key of ["result", "execution"] as const) {
    const component = recordOrNull(root[key]);
    const canonicalRecordId = component ? optionalString(component, "canonicalRecordId") : null;
    if (canonicalRecordId) observed.add(canonicalRecordId);
  }
  if (observed.size > 1) throw new RuntimeProjectionError("canonical record identities disagree");
  if (expected) {
    if (observed.size !== 1 || !observed.has(expected)) {
      throw new RuntimeProjectionError("projection does not match the expected canonical record");
    }
  }
  const canonicalRecordId = observed.values().next().value ?? null;
  if (canonicalRecordId !== null) {
    // Null before release means not materialized, not permanently forbidden.
    // Ownership is established by the decoded exact-Run backend projection;
    // canonical IDs are opaque and must not be parsed as Run identifiers.
    const run = requiredNestedRecord(root, "run", "projection");
    const terminal = requiredNestedRecord(root, "terminal", "projection");
    const result = requiredNestedRecord(root, "result", "projection");
    const execution = requiredNestedRecord(root, "execution", "projection");
    if (
      run.backendStatus !== "RELEASED"
      || terminal.isTerminal !== true
      || terminal.outcome !== "SUCCESS"
      || result.canonicalRecordId !== canonicalRecordId
      || execution.canonicalRecordId !== canonicalRecordId
      || recordOrNull(result.availability)?.status !== "AVAILABLE"
      || recordOrNull(execution.availability)?.status !== "AVAILABLE"
    ) {
      throw new RuntimeProjectionError("canonical record requires exact released result closure");
    }
  }
  return canonicalRecordId;
}

function validateTerminalAvailability(root: UnknownRecord) {
  for (const key of ["review", "result", "artifacts", "proof", "execution"] as const) {
    const component = requiredNestedRecord(root, key, "projection");
    const availability = requiredNestedRecord(component, "availability", `projection.${key}`);
    if (availability.status === "PENDING") {
      throw new RuntimeProjectionError("terminal Run retains a PENDING component");
    }
  }
}

function quarantine(
  state: RunRuntimeState,
  reason: RuntimeQuarantineReason,
  event: NormalizedRuntimeEventV1,
  fingerprint: string,
  recoveryReason: RecoveryReason
): RunRuntimeState {
  if (state.connection.kind === "TERMINAL") {
    return quarantineTerminalEvent(state, event, fingerprint, reason);
  }
  const envelope = recordOf(event);
  const record: RuntimeQuarantineRecord = Object.freeze({
    reason,
    expectedRunId: state.runId,
    eventId: optionalString(envelope, "eventId"),
    observedRunId: optionalString(envelope, "runId"),
    sequence: optionalInteger(envelope, "sequence"),
    type: optionalString(envelope, "type"),
    fingerprint
  });
  return {
    ...state,
    streamGeneration: state.streamGeneration + 1,
    stale: true,
    quarantine: appendBounded(state.quarantine, record, MAX_QUARANTINE_RECORDS),
    connection: {
      kind: "RECOVERING",
      runId: state.runId,
      lastSequence: state.committedSequence,
      reason: recoveryReason
    }
  };
}

/**
 * A terminal snapshot is authoritative and never re-enters reconnect/recovery.
 * Record only bounded safe metadata for an impossible late business frame while
 * retaining the terminal connection, cursor, and projection unchanged.
 */
function quarantineTerminalEvent(
  state: RunRuntimeState,
  event: NormalizedRuntimeEventV1,
  fingerprint: string,
  reason: RuntimeQuarantineReason
): RunRuntimeState {
  const envelope = recordOf(event);
  const record: RuntimeQuarantineRecord = Object.freeze({
    reason,
    expectedRunId: state.runId,
    eventId: optionalString(envelope, "eventId"),
    observedRunId: optionalString(envelope, "runId"),
    sequence: optionalInteger(envelope, "sequence"),
    type: optionalString(envelope, "type"),
    fingerprint
  });
  return {
    ...state,
    quarantine: appendBounded(state.quarantine, record, MAX_QUARANTINE_RECORDS)
  };
}

function advanceConnectionSequence(connection: ConnectionState, sequence: number): ConnectionState {
  switch (connection.kind) {
    case "OPEN":
    case "CONNECTING":
    case "IDLE":
      return { ...connection, lastSequence: sequence };
    default:
      return connection;
  }
}

function projectionTaskIds(projection: RunProjection): ReadonlySet<string> {
  const root = recordOf(projection);
  if (!Array.isArray(root.tasks)) return new Set();
  return new Set(
    root.tasks
      .map((task) => optionalString(recordOf(task), "taskId"))
      .filter((taskId): taskId is string => taskId !== null)
  );
}

function projectionGraphVersion(projection: RunProjection): number | null {
  const value = recordOf(projection).graphVersion;
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 1
    ? value
    : null;
}

function validateActualGraphTasks(
  actualGraph: UnknownRecord,
  projectedTasks: readonly unknown[],
  runId: string
) {
  const graphTasks = validateGraphTaskClosure(
    actualGraph,
    runId,
    "projection.actualGraph"
  );
  const projectedById = new Map<string, UnknownRecord>();
  for (const candidate of projectedTasks) {
    const task = requiredRecord(candidate, "projection task");
    projectedById.set(requiredString(task, "taskId", "projection task"), task);
  }
  if (graphTasks.size !== projectedById.size) {
    throw new RuntimeProjectionError("actual Graph and Task projection identity sets disagree");
  }
  for (const [taskId, graphTask] of graphTasks) {
    const projectedTask = projectedById.get(taskId);
    if (!projectedTask || canonicalProjectionValue(graphTask) !== canonicalProjectionValue(projectedTask)) {
      throw new RuntimeProjectionError(`Task ${taskId} disagrees with the actual Graph snapshot`);
    }
  }
}

function validateGraphTaskClosure(
  graph: UnknownRecord,
  runId: string,
  label: string
): ReadonlyMap<string, UnknownRecord> {
  const graphTasks = requiredArray(graph, "tasks", label);
  const taskById = new Map<string, UnknownRecord>();
  const dependencies = new Map<string, readonly string[]>();
  for (const candidate of graphTasks) {
    const task = requiredRecord(candidate, `${label} task`);
    const taskId = requiredString(task, "taskId", `${label} task`);
    if (taskById.has(taskId)) {
      throw new RuntimeProjectionError(`${label} contains duplicate Task identity`);
    }
    requireEqual(requiredString(task, "runId", `${label} task`), runId, `${label} Task and Run`);
    const backendStatus = requiredBackendTaskStatus(
      task,
      "backendStatus",
      `${label} task`
    );
    const mapped = TASK_STATUS_MAP[backendStatus];
    requireEqual(requiredString(task, "status", `${label} task`), mapped.status, `${label} Task status map`);
    requiredRatio(task, "progress", `${label} task`);
    requiredNonNegativeInteger(task, "attemptCount", `${label} task`);
    const refs = requiredStringArray(task, "dependencies", `${label} task`);
    if (new Set(refs).size !== refs.length || refs.includes(taskId)) {
      throw new RuntimeProjectionError(`${label} Task ${taskId} has invalid dependencies`);
    }
    taskById.set(taskId, task);
    dependencies.set(taskId, refs);
  }
  for (const [taskId, refs] of dependencies) {
    if (refs.some((dependency) => !taskById.has(dependency))) {
      throw new RuntimeProjectionError(`${label} Task ${taskId} has an unknown dependency`);
    }
  }
  const remaining = new Set(taskById.keys());
  const resolved = new Set<string>();
  while (remaining.size > 0) {
    const ready = [...remaining].filter((taskId) =>
      (dependencies.get(taskId) ?? []).every((dependency) => resolved.has(dependency))
    );
    if (ready.length === 0) throw new RuntimeProjectionError(`${label} contains a dependency cycle`);
    for (const taskId of ready) {
      remaining.delete(taskId);
      resolved.add(taskId);
    }
  }
  return taskById;
}

function canonicalProjectionValue(value: unknown): string {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new RuntimeProjectionError("projection contains a non-finite number");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalProjectionValue(item)).join(",")}]`;
  }
  const record = recordOrNull(value);
  if (record) {
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalProjectionValue(record[key])}`)
      .join(",")}}`;
  }
  throw new RuntimeProjectionError("projection contains a non-JSON value");
}

function safeFingerprint(event: NormalizedRuntimeEventV1) {
  try {
    return runtimeEventFingerprintV1(event);
  } catch {
    return "invalid-event";
  }
}

function appendBounded<T>(items: readonly T[], item: T, limit: number): readonly T[] {
  const appended = [...items, item];
  return Object.freeze(appended.length > limit ? appended.slice(appended.length - limit) : appended);
}

function isCurrentSource(state: RunRuntimeState, source: RuntimeEventSource) {
  return source.runId === state.runId && source.streamGeneration === state.streamGeneration;
}

function recordOf(value: unknown): UnknownRecord {
  return recordOrNull(value) ?? {};
}

function recordOrNull(value: unknown): UnknownRecord | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as UnknownRecord
    : null;
}

function requiredRecord(value: unknown, label: string): UnknownRecord {
  const record = recordOrNull(value);
  if (!record) throw new RuntimeProjectionError(`${label} must be an object`);
  return record;
}

function requiredNestedRecord(parent: UnknownRecord, key: string, label: string): UnknownRecord {
  return requiredRecord(parent[key], `${label}.${key}`);
}

function requiredArray(parent: UnknownRecord, key: string, label: string): readonly unknown[] {
  const value = parent[key];
  if (!Array.isArray(value)) throw new RuntimeProjectionError(`${label}.${key} must be an array`);
  return value;
}

function requiredString(parent: UnknownRecord, key: string, label: string): string {
  const value = optionalString(parent, key);
  if (!value) throw new RuntimeProjectionError(`${label}.${key} must be a non-empty string`);
  return value;
}

function optionalString(parent: UnknownRecord, key: string): string | null {
  const value = parent[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function requiredStringArray(parent: UnknownRecord, key: string, label: string): readonly string[] {
  const value = parent[key];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || item.length === 0)) {
    throw new RuntimeProjectionError(`${label}.${key} must be a string array`);
  }
  return value;
}

function requiredBoolean(parent: UnknownRecord, key: string, label: string): boolean {
  const value = parent[key];
  if (typeof value !== "boolean") throw new RuntimeProjectionError(`${label}.${key} must be boolean`);
  return value;
}

function requiredBackendRunStatus(
  parent: UnknownRecord,
  key: string,
  label: string
): RunBackendStatus {
  const value = requiredString(parent, key, label);
  if (!(value in RUN_STATUS_MAP)) {
    throw new RuntimeProjectionError(`${label}.${key} is not a frozen Run status`);
  }
  return value as RunBackendStatus;
}

function requiredBackendTaskStatus(
  parent: UnknownRecord,
  key: string,
  label: string
): TaskBackendStatus {
  const value = requiredString(parent, key, label);
  if (!(value in TASK_STATUS_MAP)) {
    throw new RuntimeProjectionError(`${label}.${key} is not a frozen Task status`);
  }
  return value as TaskBackendStatus;
}

function optionalInteger(parent: UnknownRecord, key: string): number | null {
  const value = parent[key];
  return typeof value === "number" && Number.isSafeInteger(value) ? value : null;
}

function requiredPositiveInteger(parent: UnknownRecord, key: string, label: string): number {
  const value = optionalInteger(parent, key);
  if (value === null || value < 1) {
    throw new RuntimeProjectionError(`${label}.${key} must be a positive integer`);
  }
  return value;
}

function requiredNonNegativeInteger(parent: UnknownRecord, key: string, label: string): number {
  const value = optionalInteger(parent, key);
  if (value === null || value < 0) {
    throw new RuntimeProjectionError(`${label}.${key} must be a non-negative integer`);
  }
  return value;
}

function nullablePositiveInteger(
  parent: UnknownRecord,
  key: string,
  label: string
): number | null {
  if (parent[key] === null) return null;
  return requiredPositiveInteger(parent, key, label);
}

function optionalRatio(parent: UnknownRecord, key: string): number | null {
  const value = parent[key];
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1
    ? value
    : null;
}

function requiredRatio(parent: UnknownRecord, key: string, label: string): number {
  const value = optionalRatio(parent, key);
  if (value === null) throw new RuntimeProjectionError(`${label}.${key} must be a ratio`);
  return value;
}

function requiredUtcTimestamp(parent: UnknownRecord, key: string, label: string): string {
  const value = requiredString(parent, key, label);
  if (!isUtcTimestamp(value)) throw new RuntimeProjectionError(`${label}.${key} must be RFC3339 UTC`);
  return value;
}

function isUtcTimestamp(value: string) {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$/u.test(value)
    && !Number.isNaN(Date.parse(value));
}

function requireEqual(left: unknown, right: unknown, label: string) {
  if (left !== right) throw new RuntimeProjectionError(`${label} identities disagree`);
}
