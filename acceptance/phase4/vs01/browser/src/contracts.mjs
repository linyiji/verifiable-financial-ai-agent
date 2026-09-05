import { createHash } from "node:crypto";

export const CONTRACT = Object.freeze({
  core: "phase4-core/v1",
  draft: "phase4-run-draft/v1",
  confirm: "phase4-confirm-response/v1",
  admission: "phase4-run-admission/v1",
  responseMeta: "phase4-response-meta/v1",
  projection: "phase4-run-projection/v1",
  error: "phase4-error/v1"
});

export const RUN_STAGE_BY_STATUS = Object.freeze({
  DRAFT: "PREPARE",
  SCHEME_GENERATING: "PREPARE",
  AWAITING_CONFIRMATION: "CONFIRM",
  PLANNING: "PLANNING",
  RUNNING: "RESEARCH",
  REVIEW: "REVIEW",
  PROVING: "PROVING",
  RELEASED: "COMPLETE",
  FAILED: "FAILED",
  CANCELLED: "CANCELLED"
});

export const TASK_STATUSES = Object.freeze(new Set([
  "CREATED",
  "WAITING",
  "READY",
  "RUNNING",
  "WAITING_FOR_CAPABILITY",
  "SELF_CORRECTING",
  "BLOCKED",
  "REVIEW",
  "COMPLETED",
  "FAILED",
  "CAPABILITY_BUILD_FAILED",
  "CANCELLED"
]));

export const ERROR_PROTOCOL = Object.freeze({
  INVALID_CURSOR: [400, false, "SNAPSHOT_RELOAD"],
  UNAUTHENTICATED: [401, false, "REAUTHENTICATE"],
  FORBIDDEN: [403, false, "NONE"],
  NOT_FOUND: [404, false, "NONE"],
  IDENTITY_MISMATCH: [404, false, "NONE"],
  UNAVAILABLE: [409, false, "NONE"],
  NOT_GENERATED: [409, false, "NONE"],
  NOT_RELEASED: [409, false, "SNAPSHOT_RELOAD"],
  CONFLICT: [409, false, "NONE"],
  CURSOR_AHEAD: [409, false, "SNAPSHOT_RELOAD"],
  SCHEMA_INCOMPATIBLE: [409, false, "NONE"],
  UNSUPPORTED_EVENT: [409, false, "SNAPSHOT_RELOAD"],
  TERMINAL: [409, false, "NONE"],
  REQUEST_VALIDATION_ERROR: [422, false, "NONE"],
  INTEGRITY_FAILURE: [500, false, "SNAPSHOT_RELOAD"],
  INTERNAL_ERROR: [500, false, "NONE"],
  TRANSIENT_BACKEND_ERROR: [503, true, "RETRY"]
});

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/;
const RFC3339_UTC_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;
const FORBIDDEN_PUBLIC_KEYS = /(?:authorization|api[_-]?key|bearer|secret|prompt|chain[_-]?of[_-]?thought|scratch[_-]?reasoning|raw[_-]?provider|filesystem[_-]?path)/i;
const FORBIDDEN_PUBLIC_TEXT = /(?:\bartifact:\/\/|\/Users\/|\/home\/|[A-Za-z]:\\|Traceback \(most recent call last\)|\bat\s+\S+\s+\([^\n)]*:\d+:\d+\)|\b(?:SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\S+\s+SET|DELETE\s+FROM)\b|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}|\b(?:sk|pk|api)[-_][A-Za-z0-9_-]{16,}|system prompt|chain[- ]of[- ]thought|raw provider)/i;

export class ContractViolation extends Error {
  constructor(code, path, message) {
    super(`${code} at ${path}: ${message}`);
    this.name = "ContractViolation";
    this.code = code;
    this.path = path;
  }
}

function violation(code, path, message) {
  throw new ContractViolation(code, path, message);
}

function objectAt(value, path) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    violation("SCHEMA_INCOMPATIBLE", path, "expected object");
  }
  return value;
}

function arrayAt(value, path) {
  if (!Array.isArray(value)) violation("SCHEMA_INCOMPATIBLE", path, "expected array");
  return value;
}

function stringAt(value, path, { nullable = false } = {}) {
  if (nullable && value === null) return null;
  if (typeof value !== "string" || value.length === 0) {
    violation("SCHEMA_INCOMPATIBLE", path, "expected non-empty string");
  }
  return value;
}

function booleanAt(value, path) {
  if (typeof value !== "boolean") violation("SCHEMA_INCOMPATIBLE", path, "expected boolean");
  return value;
}

function integerAt(value, path, minimum) {
  if (!Number.isInteger(value) || value < minimum) {
    violation("SCHEMA_INCOMPATIBLE", path, `expected integer >= ${minimum}`);
  }
  return value;
}

function literalAt(value, expected, path) {
  if (value !== expected) {
    violation("SCHEMA_INCOMPATIBLE", path, `expected ${JSON.stringify(expected)}`);
  }
  return value;
}

function idAt(value, path) {
  return stringAt(value, path);
}

function hashAt(value, path) {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    violation("SCHEMA_INCOMPATIBLE", path, "expected sha256:<64 lowercase hex>");
  }
  return value;
}

function timestampAt(value, path) {
  if (typeof value !== "string" || !RFC3339_UTC_PATTERN.test(value)) {
    violation("SCHEMA_INCOMPATIBLE", path, "expected RFC3339 UTC timestamp");
  }
  return value;
}

function equalAt(value, expected, path, code = "IDENTITY_MISMATCH") {
  if (expected !== undefined && value !== expected) {
    violation(code, path, `expected ${JSON.stringify(expected)}, received ${JSON.stringify(value)}`);
  }
  return value;
}

function forbidKeys(value, forbidden, path) {
  for (const key of forbidden) {
    if (Object.hasOwn(value, key)) {
      violation("SCHEMA_INCOMPATIBLE", `${path}.${key}`, "field is outside the frozen contract");
    }
  }
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const item of Object.values(value)) deepFreeze(item);
  }
  return value;
}

export function decodeAvailability(value, path = "availability") {
  const record = objectAt(value, path);
  const allowed = new Set(["PENDING", "AVAILABLE", "NOT_GENERATED", "NOT_RELEASED", "UNAVAILABLE", "FAILED"]);
  const status = stringAt(record.status, `${path}.status`);
  if (!allowed.has(status)) violation("SCHEMA_INCOMPATIBLE", `${path}.status`, "unsupported availability");
  const reasonCode = stringAt(record.reason_code, `${path}.reason_code`, { nullable: true });
  const retryable = booleanAt(record.retryable, `${path}.retryable`);
  if ((status === "AVAILABLE") !== (reasonCode === null)) {
    violation("SCHEMA_INCOMPATIBLE", path, "reason_code must be null iff AVAILABLE");
  }
  return deepFreeze({ status, reasonCode, retryable });
}

export function decodePreparedResearchDraft(value, expected = {}) {
  const wire = objectAt(value, "draft");
  forbidKeys(wire, ["mode", "goal_template_id", "tasks", "planned_graph", "run_id"], "draft");

  literalAt(wire.schema_version, CONTRACT.draft, "draft.schema_version");
  literalAt(wire.status, "AWAITING_CONFIRMATION", "draft.status");
  literalAt(wire.preview_kind, "SCHEME_ONLY", "draft.preview_kind");
  const draftId = idAt(wire.draft_id, "draft.draft_id");
  const draftVersion = integerAt(wire.draft_version, "draft.draft_version", 1);
  const objectId = equalAt(idAt(wire.object_id, "draft.object_id"), expected.objectId, "draft.object_id");
  const goal = objectAt(wire.goal, "draft.goal");
  const goalId = idAt(goal.goal_id, "draft.goal.goal_id");
  equalAt(idAt(goal.research_object_id, "draft.goal.research_object_id"), objectId, "draft.goal.research_object_id");
  if (expected.goalText !== undefined) {
    equalAt(stringAt(goal.goal_text, "draft.goal.goal_text"), expected.goalText, "draft.goal.goal_text");
  }
  const scheme = objectAt(wire.scheme_snapshot, "draft.scheme_snapshot");
  const schemeId = idAt(scheme.scheme_id, "draft.scheme_snapshot.scheme_id");
  equalAt(idAt(scheme.research_object_id, "draft.scheme_snapshot.research_object_id"), objectId, "draft.scheme_snapshot.research_object_id");
  equalAt(idAt(scheme.goal_id, "draft.scheme_snapshot.goal_id"), goalId, "draft.scheme_snapshot.goal_id");
  literalAt(scheme.confirmed_at, null, "draft.scheme_snapshot.confirmed_at");

  const plannedGraphAvailability = decodeAvailability(wire.planned_graph_availability, "draft.planned_graph_availability");
  literalAt(plannedGraphAvailability.status, "NOT_GENERATED", "draft.planned_graph_availability.status");
  literalAt(plannedGraphAvailability.reasonCode, "PLAN_CREATED_ON_CONFIRM", "draft.planned_graph_availability.reason_code");
  literalAt(plannedGraphAvailability.retryable, false, "draft.planned_graph_availability.retryable");

  return deepFreeze({
    schemaVersion: CONTRACT.draft,
    draftId,
    draftVersion,
    status: "AWAITING_CONFIRMATION",
    previewKind: "SCHEME_ONLY",
    plannedGraphAvailability,
    objectId,
    goal: structuredClone(goal),
    goalId,
    schemeSnapshot: structuredClone(scheme),
    schemeId,
    prepareRequestHash: hashAt(wire.prepare_request_hash, "draft.prepare_request_hash"),
    draftHash: hashAt(wire.draft_hash, "draft.draft_hash"),
    createdAt: timestampAt(wire.created_at, "draft.created_at"),
    expiresAt: timestampAt(wire.expires_at, "draft.expires_at")
  });
}

export function decodeConfirmRunResponse(value, expectedDraft) {
  const wire = objectAt(value, "confirm");
  literalAt(wire.schema_version, CONTRACT.confirm, "confirm.schema_version");
  const admission = objectAt(wire.admission, "confirm.admission");
  literalAt(admission.schema_version, CONTRACT.admission, "confirm.admission.schema_version");
  literalAt(admission.status, "PLANNING", "confirm.admission.status");

  const autoStart = objectAt(admission.auto_start, "confirm.admission.auto_start");
  literalAt(autoStart.required, true, "confirm.admission.auto_start.required");
  literalAt(autoStart.admitted, true, "confirm.admission.auto_start.admitted");

  const draftId = equalAt(idAt(admission.draft_id, "confirm.admission.draft_id"), expectedDraft?.draftId, "confirm.admission.draft_id");
  const draftVersion = equalAt(integerAt(admission.draft_version, "confirm.admission.draft_version", 1), expectedDraft?.draftVersion, "confirm.admission.draft_version");
  const draftHash = equalAt(hashAt(admission.draft_hash, "confirm.admission.draft_hash"), expectedDraft?.draftHash, "confirm.admission.draft_hash");
  const objectId = equalAt(idAt(admission.object_id, "confirm.admission.object_id"), expectedDraft?.objectId, "confirm.admission.object_id");
  const goalId = equalAt(idAt(admission.goal_id, "confirm.admission.goal_id"), expectedDraft?.goalId, "confirm.admission.goal_id");
  const schemeId = equalAt(idAt(admission.scheme_id, "confirm.admission.scheme_id"), expectedDraft?.schemeId, "confirm.admission.scheme_id");
  const runId = idAt(admission.run_id, "confirm.admission.run_id");
  const projectionRef = stringAt(admission.projection_ref, "confirm.admission.projection_ref");
  const eventsRef = stringAt(admission.events_ref, "confirm.admission.events_ref");
  if (!new URL(projectionRef, "http://contract.invalid").pathname.endsWith(`/research-runs/${encodeURIComponent(runId)}/projection`)) {
    violation("IDENTITY_MISMATCH", "confirm.admission.projection_ref", "reference does not identify admitted Run");
  }
  if (!new URL(eventsRef, "http://contract.invalid").pathname.endsWith(`/research-runs/${encodeURIComponent(runId)}/events`)) {
    violation("IDENTITY_MISMATCH", "confirm.admission.events_ref", "reference does not identify admitted Run");
  }

  const responseMeta = objectAt(wire.response_meta, "confirm.response_meta");
  literalAt(responseMeta.schema_version, CONTRACT.responseMeta, "confirm.response_meta.schema_version");
  const requestId = stringAt(responseMeta.request_id, "confirm.response_meta.request_id", { nullable: true });
  const idempotencyReplayed = booleanAt(responseMeta.idempotency_replayed, "confirm.response_meta.idempotency_replayed");

  return deepFreeze({
    schemaVersion: CONTRACT.confirm,
    admission: {
      schemaVersion: CONTRACT.admission,
      admissionId: idAt(admission.admission_id, "confirm.admission.admission_id"),
      runId,
      objectId,
      draftId,
      draftVersion,
      draftHash,
      goalId,
      schemeId,
      plannedGraphId: idAt(admission.planned_graph_id, "confirm.admission.planned_graph_id"),
      backendStatus: "PLANNING",
      status: "PLANNING",
      autoStart: { required: true, admitted: true },
      confirmationRequestHash: hashAt(admission.confirmation_request_hash, "confirm.admission.confirmation_request_hash"),
      admittedAt: timestampAt(admission.admitted_at, "confirm.admission.admitted_at"),
      projectionRef,
      eventsRef
    },
    responseMeta: { schemaVersion: CONTRACT.responseMeta, requestId, idempotencyReplayed }
  });
}

function readGraph(value, path, expectedRunId, expectedGraphId, expectedVersion) {
  const graph = objectAt(value, path);
  const graphId = equalAt(idAt(graph.graph_id, `${path}.graph_id`), expectedGraphId, `${path}.graph_id`);
  equalAt(idAt(graph.run_id, `${path}.run_id`), expectedRunId, `${path}.run_id`);
  const version = integerAt(graph.version, `${path}.version`, 1);
  equalAt(version, expectedVersion, `${path}.version`);
  const taskIds = arrayAt(graph.task_ids, `${path}.task_ids`).map((item, index) => idAt(item, `${path}.task_ids[${index}]`));
  if (new Set(taskIds).size !== taskIds.length) violation("SCHEMA_INCOMPATIBLE", `${path}.task_ids`, "duplicate task identity");
  arrayAt(graph.edges, `${path}.edges`);
  return { graphId, version, taskIds };
}

export function decodeAtomicRunProjection(value, expectedAdmission) {
  const wire = objectAt(value, "projection");
  literalAt(wire.projection_schema_version, CONTRACT.projection, "projection.projection_schema_version");
  const object = objectAt(wire.object, "projection.object");
  const run = objectAt(wire.run, "projection.run");
  const goal = objectAt(wire.goal, "projection.goal");
  const scheme = objectAt(wire.confirmed_scheme, "projection.confirmed_scheme");

  const objectId = equalAt(idAt(object.object_id, "projection.object.object_id"), expectedAdmission?.objectId, "projection.object.object_id");
  const runId = equalAt(idAt(run.run_id, "projection.run.run_id"), expectedAdmission?.runId, "projection.run.run_id");
  equalAt(idAt(run.research_object_id, "projection.run.research_object_id"), objectId, "projection.run.research_object_id");
  const goalId = equalAt(idAt(goal.goal_id, "projection.goal.goal_id"), expectedAdmission?.goalId, "projection.goal.goal_id");
  equalAt(idAt(goal.research_object_id, "projection.goal.research_object_id"), objectId, "projection.goal.research_object_id");
  equalAt(idAt(run.goal_id, "projection.run.goal_id"), goalId, "projection.run.goal_id");
  const schemeId = equalAt(idAt(scheme.scheme_id, "projection.confirmed_scheme.scheme_id"), expectedAdmission?.schemeId, "projection.confirmed_scheme.scheme_id");
  equalAt(idAt(scheme.goal_id, "projection.confirmed_scheme.goal_id"), goalId, "projection.confirmed_scheme.goal_id");
  equalAt(idAt(scheme.research_object_id, "projection.confirmed_scheme.research_object_id"), objectId, "projection.confirmed_scheme.research_object_id");
  equalAt(idAt(run.scheme_id, "projection.run.scheme_id"), schemeId, "projection.run.scheme_id");
  if (scheme.confirmed_at === null) violation("SCHEMA_INCOMPATIBLE", "projection.confirmed_scheme.confirmed_at", "confirmed Scheme must be confirmed");

  const status = stringAt(run.status, "projection.run.status");
  const expectedStage = RUN_STAGE_BY_STATUS[status];
  if (!expectedStage) violation("SCHEMA_INCOMPATIBLE", "projection.run.status", "unsupported Run status");
  equalAt(stringAt(run.stage, "projection.run.stage"), expectedStage, "projection.run.stage", "SCHEMA_INCOMPATIBLE");
  const graphVersion = wire.graph_version === null ? null : integerAt(wire.graph_version, "projection.graph_version", 1);
  const plannedGraph = readGraph(
    wire.planned_graph,
    "projection.planned_graph",
    runId,
    expectedAdmission?.plannedGraphId,
    undefined
  );
  equalAt(plannedGraph.graphId, idAt(run.planned_graph_id, "projection.run.planned_graph_id"), "projection.run.planned_graph_id");

  let actualGraph = null;
  if (wire.actual_graph !== null) {
    if (graphVersion === null) violation("SCHEMA_INCOMPATIBLE", "projection.graph_version", "actual graph requires graph version");
    actualGraph = readGraph(wire.actual_graph, "projection.actual_graph", runId, run.actual_graph_id, graphVersion);
  } else if (graphVersion !== null || run.actual_graph_id !== null) {
    violation("SCHEMA_INCOMPATIBLE", "projection.actual_graph", "actual graph/id/version nullability is inconsistent");
  }

  const tasks = arrayAt(wire.tasks, "projection.tasks").map((item, index) => {
    const task = objectAt(item, `projection.tasks[${index}]`);
    const taskId = idAt(task.task_id, `projection.tasks[${index}].task_id`);
    equalAt(idAt(task.run_id, `projection.tasks[${index}].run_id`), runId, `projection.tasks[${index}].run_id`);
    if (Object.hasOwn(task, "research_object_id")) {
      equalAt(idAt(task.research_object_id, `projection.tasks[${index}].research_object_id`), objectId, `projection.tasks[${index}].research_object_id`);
    }
    if (Object.hasOwn(task, "status") && !TASK_STATUSES.has(task.status)) {
      violation("SCHEMA_INCOMPATIBLE", `projection.tasks[${index}].status`, "unsupported Task status");
    }
    return { taskId, wire: structuredClone(task) };
  });
  if (new Set(tasks.map((task) => task.taskId)).size !== tasks.length) {
    violation("SCHEMA_INCOMPATIBLE", "projection.tasks", "duplicate Task identity");
  }
  const projectedTaskIds = new Set(tasks.map((task) => task.taskId));
  for (const taskId of plannedGraph.taskIds) {
    if (!projectedTaskIds.has(taskId)) violation("IDENTITY_MISMATCH", "projection.planned_graph.task_ids", `missing Task ${taskId}`);
  }
  if (actualGraph) {
    for (const taskId of actualGraph.taskIds) {
      if (!projectedTaskIds.has(taskId)) violation("IDENTITY_MISMATCH", "projection.actual_graph.task_ids", `missing Task ${taskId}`);
    }
  }
  const graphedTaskIds = new Set([
    ...plannedGraph.taskIds,
    ...(actualGraph?.taskIds ?? [])
  ]);
  for (const taskId of projectedTaskIds) {
    if (!graphedTaskIds.has(taskId)) {
      violation("IDENTITY_MISMATCH", "projection.tasks", `Task ${taskId} is absent from both graphs`);
    }
  }

  const lifecycle = objectAt(wire.lifecycle, "projection.lifecycle");
  equalAt(stringAt(lifecycle.status, "projection.lifecycle.status"), status, "projection.lifecycle.status");
  equalAt(stringAt(lifecycle.stage, "projection.lifecycle.stage"), expectedStage, "projection.lifecycle.stage", "SCHEMA_INCOMPATIBLE");
  arrayAt(wire.path_changes, "projection.path_changes");
  arrayAt(wire.activity, "projection.activity");
  for (const name of ["review", "result", "artifacts", "proof", "execution", "terminal"]) objectAt(wire[name], `projection.${name}`);

  return deepFreeze({
    projectionSchemaVersion: CONTRACT.projection,
    projectionRevision: integerAt(wire.projection_revision, "projection.projection_revision", 1),
    projectionSequence: integerAt(wire.projection_sequence, "projection.projection_sequence", 0),
    generatedAt: timestampAt(wire.generated_at, "projection.generated_at"),
    objectId,
    runId,
    goalId,
    schemeId,
    plannedGraphId: plannedGraph.graphId,
    graphVersion,
    taskIds: tasks.map((task) => task.taskId),
    status,
    stage: expectedStage
  });
}

export function decodeErrorEnvelope(value, httpStatus) {
  const wire = objectAt(value, "errorEnvelope");
  literalAt(wire.schema_version, CONTRACT.error, "errorEnvelope.schema_version");
  const error = objectAt(wire.error, "errorEnvelope.error");
  const code = stringAt(error.code, "errorEnvelope.error.code");
  const protocol = ERROR_PROTOCOL[code];
  if (!protocol) violation("SCHEMA_INCOMPATIBLE", "errorEnvelope.error.code", "unsupported error code");
  if (httpStatus !== undefined) equalAt(httpStatus, protocol[0], "http.status", "SCHEMA_INCOMPATIBLE");
  equalAt(booleanAt(error.retryable, "errorEnvelope.error.retryable"), protocol[1], "errorEnvelope.error.retryable", "SCHEMA_INCOMPATIBLE");
  equalAt(stringAt(error.recovery, "errorEnvelope.error.recovery"), protocol[2], "errorEnvelope.error.recovery", "SCHEMA_INCOMPATIBLE");
  const resource = error.resource === null ? null : objectAt(error.resource, "errorEnvelope.error.resource");
  if (resource) {
    idAt(resource.type, "errorEnvelope.error.resource.type");
    idAt(resource.id, "errorEnvelope.error.resource.id");
  }
  assertSafePublicJson(error.details, "errorEnvelope.error.details");
  return deepFreeze({
    schemaVersion: CONTRACT.error,
    code,
    message: stringAt(error.message, "errorEnvelope.error.message"),
    retryable: protocol[1],
    recovery: protocol[2],
    requestId: stringAt(error.request_id, "errorEnvelope.error.request_id", { nullable: true }),
    resource: resource ? { type: resource.type, id: resource.id } : null,
    details: structuredClone(error.details)
  });
}

export function assertSafePublicJson(value, path = "value") {
  if (typeof value === "string") {
    if (FORBIDDEN_PUBLIC_TEXT.test(value)) {
      violation("UNSAFE_PUBLIC_CONTENT", path, "forbidden public text");
    }
    return;
  }
  if (value === null || ["number", "boolean"].includes(typeof value)) return;
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertSafePublicJson(item, `${path}[${index}]`));
    return;
  }
  const object = objectAt(value, path);
  for (const [key, item] of Object.entries(object)) {
    if (FORBIDDEN_PUBLIC_KEYS.test(key)) violation("UNSAFE_PUBLIC_CONTENT", `${path}.${key}`, "forbidden public key");
    assertSafePublicJson(item, `${path}.${key}`);
  }
}

export function admitContextProjection(current, candidate, context) {
  if (candidate.requestEpoch !== context.currentRequestEpoch) {
    return deepFreeze({ accepted: false, reason: "STALE_RESPONSE", projection: current });
  }
  if (candidate.objectId !== context.objectId || candidate.runId !== context.runId) {
    return deepFreeze({ accepted: false, reason: "IDENTITY_MISMATCH", projection: current });
  }
  return deepFreeze({ accepted: true, reason: null, projection: candidate.projection });
}

export function assertAdmissionReplayStable(first, replay) {
  const firstAdmission = objectAt(first.admission, "first.admission");
  const replayAdmission = objectAt(replay.admission, "replay.admission");
  if (JSON.stringify(firstAdmission) !== JSON.stringify(replayAdmission)) {
    violation("CONFLICT", "replay.admission", "immutable admission changed across replay");
  }
  literalAt(first.responseMeta.idempotencyReplayed, false, "first.responseMeta.idempotencyReplayed");
  literalAt(replay.responseMeta.idempotencyReplayed, true, "replay.responseMeta.idempotencyReplayed");
}

export function assertNoSecondStartRequest(requests) {
  const mutations = requests.filter((request) => request.method !== "GET" && request.method !== "HEAD" && request.method !== "OPTIONS");
  const confirm = mutations.filter((request) => request.method === "POST" && request.pathname === "/api/research-runs");
  if (confirm.length !== 1) violation("CONFIRM_COUNT", "network", `expected one Confirm request, received ${confirm.length}`);
  const forbidden = mutations.filter((request) => /\/(?:start|execute|execution)(?:\/|$)/i.test(request.pathname));
  if (forbidden.length) violation("SECOND_START", "network", "separate start/execute mutation observed");
}

export function assertContractVersionHeader(headers, headerName = "x-phase4-contract-version") {
  const normalized = Object.fromEntries(Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]));
  literalAt(normalized[headerName], CONTRACT.core, `headers.${headerName}`);
}

export function assertNoDemoFallback(text, path = "surface") {
  const forbidden = [
    "DemoFrontendDataSource",
    "DemoRuntimeTransport",
    "DemoScenarioStore",
    "RUN-DEMO",
    "Demo Runtime",
    "Frontend Demo",
    "Demo company catalog"
  ];
  for (const marker of forbidden) {
    if (text.includes(marker)) violation("DEMO_FALLBACK", path, `found ${marker}`);
  }
}

const FINANCIAL_AUTHORITY_PATTERNS = Object.freeze([
  ["CANONICAL_NUMERIC_COERCION", /\b(?:Number|parseFloat|parseInt)\s*\([^)]{0,160}(?:canonical_value|canonicalValue)/i],
  ["CANONICAL_ARITHMETIC", /(?:canonical_value|canonicalValue)[^;\n]{0,160}(?:\*|\/|\+|-)\s*(?:100|\w+)/i],
  ["RATIO_TO_PERCENT", /(?:ratio|canonicalValue|canonical_value)[^;\n]{0,120}\*\s*100/i],
  ["REVENUE_GROWTH_FORMULA", /(?:currentRevenue|current_revenue)\s*-\s*(?:priorRevenue|prior_revenue)/i],
  ["EBITDA_MARGIN_FORMULA", /(?:ebitda)\s*\/\s*(?:revenue)/i],
  ["CLIENT_FINANCIAL_CALCULATOR", /\b(?:calculate|compute)(?:RevenueGrowth|EbitdaMargin|FreeCashFlow|Sma|Rsi|Macd)\b/i]
]);

export function findFrontendFinancialAuthority(sourceEntries) {
  const findings = [];
  for (const { path, source } of sourceEntries) {
    const withoutComments = String(source)
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/(^|[^:])\/\/.*$/gm, "$1");
    for (const [code, pattern] of FINANCIAL_AUTHORITY_PATTERNS) {
      if (pattern.test(withoutComments)) findings.push({ code, path });
    }
  }
  return findings;
}

export function sha256Text(value) {
  return createHash("sha256").update(String(value), "utf8").digest("hex");
}
