import { createHash } from "node:crypto";

export const CONTRACT = Object.freeze({
  core: "phase4-core/v1",
  event: "phase4-runtime-event/v1",
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

export const PROOF_STATUSES = Object.freeze(new Set([
  "NOT_REQUIRED",
  "PENDING",
  "PROVING",
  "GENERATED_UNVERIFIED",
  "VERIFIED",
  "INVALID",
  "ERROR",
  "UNSUPPORTED"
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
const RFC3339_UTC_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?Z$/;
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const CANONICAL_DECIMAL_PATTERN = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/;
const FORBIDDEN_PUBLIC_KEYS = /(?:authorization|api[_-]?key|bearer|secret|prompt|chain[_-]?of[_-]?thought|scratch[_-]?reasoning|raw[_-]?provider|filesystem[_-]?path)/i;

const DRAFT_KEYS = Object.freeze([
  "schema_version", "draft_id", "draft_version", "status", "preview_kind",
  "planned_graph_availability", "object_id", "goal", "scheme_snapshot",
  "prepare_request_hash", "draft_hash", "created_at", "expires_at"
]);
const GOAL_KEYS = Object.freeze([
  "goal_id", "research_object_id", "goal_type", "goal_text", "as_of", "preferences", "created_at"
]);
const SCHEME_KEYS = Object.freeze([
  "scheme_id", "research_object_id", "goal_id", "research_scope", "data_requirements",
  "agent_requirements", "skill_requirements", "calculation_requirements", "assurance_requirements",
  "report_requirements", "limitations", "generated_by", "generated_model", "created_at", "confirmed_at"
]);
const SCHEME_ARRAY_KEYS = Object.freeze([
  "research_scope", "data_requirements", "agent_requirements", "skill_requirements",
  "calculation_requirements", "report_requirements", "limitations"
]);
const PROJECTION_KEYS = Object.freeze([
  "projection_schema_version", "projection_revision", "projection_sequence", "generated_at",
  "object", "run", "goal", "confirmed_scheme", "planned_graph", "actual_graph", "graph_version",
  "tasks", "path_changes", "activity", "lifecycle", "review", "result", "artifacts", "proof",
  "execution", "terminal"
]);
const OBJECT_KEYS = Object.freeze([
  "object_id", "symbol", "company_name", "object_type", "exchange", "sector", "currency",
  "identity_version"
]);
const RUN_KEYS = Object.freeze([
  "run_id", "research_object_id", "goal_id", "scheme_id", "status", "stage", "as_of",
  "planned_graph_id", "actual_graph_id", "execution_target", "created_at", "started_at",
  "completed_at", "updated_at"
]);
const PATH_CHANGE_KEYS = Object.freeze([
  "path_change_id", "source_kind", "source_id", "change_kind", "status", "decision", "reason_code",
  "task_refs", "operations", "graph_version_before", "graph_version_after", "created_at", "resolved_at"
]);
const TASK_KEYS = Object.freeze([
  "task_id", "run_id", "parent_task_id", "task_type", "goal", "assigned_agent", "skill_id",
  "dependencies", "origin", "reason_code", "status", "progress", "attempt_count",
  "task_input_evidence_ids", "task_output_evidence_ids", "evidence_acquisition_status",
  "evidence_source_coverage", "created_at"
]);
const ACTIVITY_REQUIRED_KEYS = Object.freeze([
  "event_id", "type", "sequence", "timestamp", "task_id", "message_code"
]);
const ACTIVITY_OPTIONAL_KEYS = Object.freeze([
  "status", "actor_id", "actor_type", "duration_ms", "input_refs", "output_refs",
  "evidence_refs", "calculation_refs", "claim_refs", "judgment_refs", "review_refs",
  "proof_refs", "artifact_refs", "trace_bundle_refs"
]);
const TERMINAL_OUTCOME_BY_STATUS = Object.freeze({
  RELEASED: "SUCCESS",
  FAILED: "FAILURE",
  CANCELLED: "CANCELLED"
});
const FAILURE_CODES_BY_STAGE = Object.freeze({
  PLANNING: new Set(["PLANNING_FAILED"]),
  DATA_EVIDENCE: new Set(["DATA_EVIDENCE_FAILED"]),
  TASK_EXECUTION: new Set(["TASK_EXECUTION_FAILED"]),
  GENERATED_CAPABILITY: new Set(["GENERATED_CAPABILITY_FAILED"]),
  FINANCIAL_REVIEW: new Set(["FINANCIAL_REVIEW_BLOCKED", "FINANCIAL_REVIEW_FAILED"]),
  PROOF: new Set(["PROOF_INVALID", "PROOF_FAILED"]),
  ARTIFACT_GENERATION: new Set(["REQUIRED_ARTIFACT_GENERATION_FAILED"]),
  RELEASE: new Set(["RELEASE_GATE_BLOCKED", "RELEASE_FAILED"]),
  POST_SCHEDULER: new Set(["POST_SCHEDULER_FAILED"]),
  PERSISTENCE: new Set(["PERSISTENCE_FINALIZATION_FAILED"]),
  CANCELLATION: new Set(["RUN_CANCELLED"])
});

export const PUBLIC_SURFACE_PATTERNS = Object.freeze([
  ["PROVIDER_QIJI", /\bqiji\b/i],
  ["PROVIDER_MIMO", /\bmimo\b/i],
  ["PROVIDER_TEAMOROUTER", /\bteamorouter\b/i],
  ["PROVIDER_FMP", /\bfmp\b/i],
  ["PROVIDER_LANGFUSE", /\blangfuse\b/i],
  ["CREDENTIAL_BEARER", /\bbearer(?:\s+|%20)[A-Za-z0-9._~+/=-]{8,}/i],
  ["CREDENTIAL_API_KEY", /\b(?:api[_ -]?key|authorization[_ -]?header|access[_ -]?token|secret[_ -]?key)\b/i],
  ["CREDENTIAL_TOKEN_SHAPE", /\b(?:sk|pk|api)[-_][A-Za-z0-9_-]{16,}\b/i],
  ["HIDDEN_REASONING", /\b(?:chain[_ -]?of[_ -]?thought|hidden[_ -]?reasoning|scratch(?:pad|[_ -]?reasoning)|system[_ -]?prompt)\b/i],
  ["RAW_PROVIDER_PAYLOAD", /\b(?:raw[_ -]?provider(?:[_ -]?(?:payload|body|response))?|provider[_ -]?payload|raw[_ -]?(?:completion|model[_ -]?response))\b/i],
  ["STACK_TRACE", /(?:Traceback \(most recent call last\)|\bat\s+\S+\s+\([^\n)]*:\d+:\d+\)|\b(?:stack[_ -]?trace|error\.stack)\b)/i],
  ["INTERNAL_PATH", /(?:\bartifact:\/\/|\bfile:\/\/|\/Users\/|\/home\/|[A-Za-z]:\\)/i],
  ["RAW_SQL", /\b(?:SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\S+\s+SET|DELETE\s+FROM)\b/i]
]);

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

function anyIntegerAt(value, path) {
  if (!Number.isInteger(value)) violation("SCHEMA_INCOMPATIBLE", path, "expected integer");
  return value;
}

function numberAt(value, path, minimum, maximum) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum || value > maximum) {
    violation("SCHEMA_INCOMPATIBLE", path, `expected finite number in ${minimum}..${maximum}`);
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
  const identifier = stringAt(value, path);
  if (!identifier.trim() || identifier.trim() !== identifier) {
    violation("SCHEMA_INCOMPATIBLE", path, "expected canonical non-blank identity");
  }
  return identifier;
}

function hashAt(value, path) {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    violation("SCHEMA_INCOMPATIBLE", path, "expected sha256:<64 lowercase hex>");
  }
  return value;
}

function timestampAt(value, path) {
  const match = typeof value === "string" ? RFC3339_UTC_PATTERN.exec(value) : null;
  if (!match) {
    violation("SCHEMA_INCOMPATIBLE", path, "expected RFC3339 UTC timestamp");
  }
  const [, yearText, monthText, dayText, hourText, minuteText, secondText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const daysInMonth = month >= 1 && month <= 12
    ? new Date(Date.UTC(year, month, 0)).getUTCDate()
    : 0;
  if (
    year === 0
    || month < 1 || month > 12
    || day < 1 || day > daysInMonth
    || hour > 23 || minute > 59 || second > 59
    || Number.isNaN(Date.parse(value))
  ) {
    violation("SCHEMA_INCOMPATIBLE", path, "expected a real RFC3339 UTC instant");
  }
  return value;
}

function nullableTimestampAt(value, path) {
  return value === null ? null : timestampAt(value, path);
}

function dateAt(value, path) {
  if (typeof value !== "string" || !ISO_DATE_PATTERN.test(value)) {
    violation("SCHEMA_INCOMPATIBLE", path, "expected YYYY-MM-DD");
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value) {
    violation("SCHEMA_INCOMPATIBLE", path, "expected a real calendar date");
  }
  return value;
}

function nullableIdAt(value, path) {
  return value === null ? null : idAt(value, path);
}

function exactKeysAt(value, expectedKeys, path) {
  const actual = Object.keys(value).sort();
  const expected = [...expectedKeys].sort();
  const missing = expected.filter((key) => !Object.hasOwn(value, key));
  const extra = actual.filter((key) => !expectedKeys.includes(key));
  if (missing.length || extra.length) {
    violation(
      "SCHEMA_INCOMPATIBLE",
      path,
      `exact fields required; missing=${missing.join(",") || "none"}; extra=${extra.join(",") || "none"}`
    );
  }
  return value;
}

function uniqueIdsAt(value, path, { allowEmpty = true } = {}) {
  const ids = arrayAt(value, path).map((item, index) => idAt(item, `${path}[${index}]`));
  if (!allowEmpty && ids.length === 0) violation("SCHEMA_INCOMPATIBLE", path, "expected at least one identity");
  if (new Set(ids).size !== ids.length) violation("SCHEMA_INCOMPATIBLE", path, "duplicate identity");
  return ids;
}

function nullableStringAt(value, path) {
  return stringAt(value, path, { nullable: true });
}

function equalAt(value, expected, path, code = "IDENTITY_MISMATCH") {
  if (expected !== undefined && value !== expected) {
    violation(code, path, `expected ${JSON.stringify(expected)}, received ${JSON.stringify(value)}`);
  }
  return value;
}

function equalJsonAt(value, expected, path) {
  if (expected !== undefined && JSON.stringify(value) !== JSON.stringify(expected)) {
    violation("IDENTITY_MISMATCH", path, "value differs from the exact request-bound JSON");
  }
  return value;
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const item of Object.values(value)) deepFreeze(item);
  }
  return value;
}

export function findPublicSurfaceLeaks(sourceEntries, exactSentinels = []) {
  const sentinels = exactSentinels.filter((value) => typeof value === "string" && value.length > 0);
  const findings = [];
  for (const { path, source } of sourceEntries) {
    const publicText = `${String(path)}\n${String(source)}`;
    if (sentinels.some((sentinel) => publicText.includes(sentinel))) {
      findings.push({ code: "EXACT_SECRET_SENTINEL", path });
    }
    for (const [code, pattern] of PUBLIC_SURFACE_PATTERNS) {
      if (pattern.test(publicText)) findings.push({ code, path });
    }
  }
  return findings;
}

export function assertNoPublicSurfaceLeaks(value, path = "public surface", exactSentinels = []) {
  const findings = findPublicSurfaceLeaks([{ path, source: String(value) }], exactSentinels);
  if (findings.length) {
    violation("PUBLIC_SURFACE_LEAK", path, findings.map((finding) => finding.code).join(","));
  }
}

export function decodeAvailability(value, path = "availability") {
  const record = objectAt(value, path);
  exactKeysAt(record, ["status", "reason_code", "retryable"], path);
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

function decodeGoal(value, path, expected = {}) {
  const goal = objectAt(value, path);
  exactKeysAt(goal, GOAL_KEYS, path);
  const goalId = equalAt(idAt(goal.goal_id, `${path}.goal_id`), expected.goalId, `${path}.goal_id`);
  const objectId = equalAt(
    idAt(goal.research_object_id, `${path}.research_object_id`),
    expected.objectId,
    `${path}.research_object_id`
  );
  literalAt(goal.goal_type, "comprehensive_equity_research", `${path}.goal_type`);
  const goalText = equalAt(
    stringAt(goal.goal_text, `${path}.goal_text`),
    expected.goalText,
    `${path}.goal_text`
  );
  const asOf = equalAt(dateAt(goal.as_of, `${path}.as_of`), expected.asOf, `${path}.as_of`);
  const preferences = objectAt(goal.preferences, `${path}.preferences`);
  assertSafePublicJson(preferences, `${path}.preferences`);
  equalJsonAt(preferences, expected.preferences, `${path}.preferences`);
  return {
    goalId,
    objectId,
    goalType: "comprehensive_equity_research",
    goalText,
    asOf,
    preferences: structuredClone(preferences),
    createdAt: equalAt(
      timestampAt(goal.created_at, `${path}.created_at`),
      expected.createdAt,
      `${path}.created_at`
    )
  };
}

function decodeScheme(value, path, expected = {}, { confirmed }) {
  const scheme = objectAt(value, path);
  exactKeysAt(scheme, SCHEME_KEYS, path);
  const schemeId = equalAt(idAt(scheme.scheme_id, `${path}.scheme_id`), expected.schemeId, `${path}.scheme_id`);
  const objectId = equalAt(
    idAt(scheme.research_object_id, `${path}.research_object_id`),
    expected.objectId,
    `${path}.research_object_id`
  );
  const goalId = equalAt(idAt(scheme.goal_id, `${path}.goal_id`), expected.goalId, `${path}.goal_id`);
  const arrays = {};
  for (const key of SCHEME_ARRAY_KEYS) {
    const entries = arrayAt(scheme[key], `${path}.${key}`);
    entries.forEach((item, index) => stringAt(item, `${path}.${key}[${index}]`));
    assertSafePublicJson(entries, `${path}.${key}`);
    arrays[key] = structuredClone(entries);
  }
  const assuranceRequirements = objectAt(scheme.assurance_requirements, `${path}.assurance_requirements`);
  assertSafePublicJson(assuranceRequirements, `${path}.assurance_requirements`);
  const confirmedAt = confirmed
    ? timestampAt(scheme.confirmed_at, `${path}.confirmed_at`)
    : literalAt(scheme.confirmed_at, null, `${path}.confirmed_at`);
  const normalized = {
    schemeId,
    objectId,
    goalId,
    researchScope: arrays.research_scope,
    dataRequirements: arrays.data_requirements,
    agentRequirements: arrays.agent_requirements,
    skillRequirements: arrays.skill_requirements,
    calculationRequirements: arrays.calculation_requirements,
    assuranceRequirements: structuredClone(assuranceRequirements),
    reportRequirements: arrays.report_requirements,
    limitations: arrays.limitations,
    generatedBy: stringAt(scheme.generated_by, `${path}.generated_by`),
    generatedModel: nullableStringAt(scheme.generated_model, `${path}.generated_model`),
    createdAt: timestampAt(scheme.created_at, `${path}.created_at`),
    confirmedAt
  };
  for (const key of [
    "researchScope", "dataRequirements", "agentRequirements", "skillRequirements",
    "calculationRequirements", "reportRequirements", "limitations"
  ]) equalJsonAt(normalized[key], expected[key], `${path}.${key}`);
  equalJsonAt(normalized.assuranceRequirements, expected.assuranceRequirements, `${path}.assurance_requirements`);
  equalAt(normalized.generatedBy, expected.generatedBy, `${path}.generated_by`);
  equalAt(normalized.generatedModel, expected.generatedModel, `${path}.generated_model`);
  equalAt(normalized.createdAt, expected.createdAt, `${path}.created_at`);
  return normalized;
}

export function decodePreparedResearchDraft(value, expected = {}) {
  const wire = objectAt(value, "draft");
  exactKeysAt(wire, DRAFT_KEYS, "draft");

  literalAt(wire.schema_version, CONTRACT.draft, "draft.schema_version");
  literalAt(wire.status, "AWAITING_CONFIRMATION", "draft.status");
  literalAt(wire.preview_kind, "SCHEME_ONLY", "draft.preview_kind");
  const draftId = idAt(wire.draft_id, "draft.draft_id");
  const draftVersion = integerAt(wire.draft_version, "draft.draft_version", 1);
  const objectId = equalAt(idAt(wire.object_id, "draft.object_id"), expected.objectId, "draft.object_id");
  const goal = decodeGoal(wire.goal, "draft.goal", {
    objectId,
    goalText: expected.goalText,
    asOf: expected.asOf,
    preferences: expected.preferences
  });
  const goalId = goal.goalId;
  const scheme = decodeScheme(wire.scheme_snapshot, "draft.scheme_snapshot", {
    objectId,
    goalId
  }, { confirmed: false });
  const schemeId = scheme.schemeId;

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
    goal,
    goalId,
    schemeSnapshot: scheme,
    schemeId,
    prepareRequestHash: hashAt(wire.prepare_request_hash, "draft.prepare_request_hash"),
    draftHash: hashAt(wire.draft_hash, "draft.draft_hash"),
    createdAt: timestampAt(wire.created_at, "draft.created_at"),
    expiresAt: timestampAt(wire.expires_at, "draft.expires_at")
  });
}

export function decodeConfirmRunResponse(value, expectedDraft) {
  const wire = objectAt(value, "confirm");
  exactKeysAt(wire, ["schema_version", "admission", "response_meta"], "confirm");
  literalAt(wire.schema_version, CONTRACT.confirm, "confirm.schema_version");
  const admission = objectAt(wire.admission, "confirm.admission");
  exactKeysAt(admission, [
    "schema_version", "admission_id", "run_id", "object_id", "draft_id", "draft_version",
    "draft_hash", "goal_id", "scheme_id", "planned_graph_id", "status", "auto_start",
    "confirmation_request_hash", "admitted_at", "projection_ref", "events_ref"
  ], "confirm.admission");
  literalAt(admission.schema_version, CONTRACT.admission, "confirm.admission.schema_version");
  literalAt(admission.status, "PLANNING", "confirm.admission.status");

  const autoStart = objectAt(admission.auto_start, "confirm.admission.auto_start");
  exactKeysAt(autoStart, ["required", "admitted"], "confirm.admission.auto_start");
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
  if (projectionRef !== `/api/research-runs/${encodeURIComponent(runId)}/projection`) {
    violation("IDENTITY_MISMATCH", "confirm.admission.projection_ref", "reference does not identify admitted Run");
  }
  if (eventsRef !== `/api/research-runs/${encodeURIComponent(runId)}/events`) {
    violation("IDENTITY_MISMATCH", "confirm.admission.events_ref", "reference does not identify admitted Run");
  }

  const responseMeta = objectAt(wire.response_meta, "confirm.response_meta");
  exactKeysAt(responseMeta, ["schema_version", "request_id", "idempotency_replayed"], "confirm.response_meta");
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

function readTask(value, path, expectedRunId, expectedObjectId) {
  const task = objectAt(value, path);
  exactKeysAt(task, TASK_KEYS, path);
  const taskId = idAt(task.task_id, `${path}.task_id`);
  const runId = equalAt(idAt(task.run_id, `${path}.run_id`), expectedRunId, `${path}.run_id`);
  void expectedObjectId;
  const status = stringAt(task.status, `${path}.status`);
  if (!TASK_STATUSES.has(status)) violation("SCHEMA_INCOMPATIBLE", `${path}.status`, "unsupported Task status");
  const progress = numberAt(task.progress, `${path}.progress`, 0, 1);
  const parentTaskId = nullableIdAt(task.parent_task_id, `${path}.parent_task_id`);
  const dependencyIds = uniqueIdsAt(task.dependencies, `${path}.dependencies`);
  stringAt(task.task_type, `${path}.task_type`);
  stringAt(task.goal, `${path}.goal`);
  stringAt(task.assigned_agent, `${path}.assigned_agent`);
  idAt(task.skill_id, `${path}.skill_id`);
  if (!new Set(["PLAN", "REPLAN", "REVIEW_FIX"]).has(stringAt(task.origin, `${path}.origin`))) {
    violation("SCHEMA_INCOMPATIBLE", `${path}.origin`, "unsupported Task origin");
  }
  nullableStringAt(task.reason_code, `${path}.reason_code`);
  integerAt(task.attempt_count, `${path}.attempt_count`, 0);
  uniqueIdsAt(task.task_input_evidence_ids, `${path}.task_input_evidence_ids`);
  uniqueIdsAt(task.task_output_evidence_ids, `${path}.task_output_evidence_ids`);
  nullableStringAt(task.evidence_acquisition_status, `${path}.evidence_acquisition_status`);
  objectAt(task.evidence_source_coverage, `${path}.evidence_source_coverage`);
  assertSafePublicJson(task.evidence_source_coverage, `${path}.evidence_source_coverage`);
  timestampAt(task.created_at, `${path}.created_at`);
  if (parentTaskId === taskId) violation("SCHEMA_INCOMPATIBLE", `${path}.parent_task_id`, "Task cannot parent itself");
  if (dependencyIds.includes(taskId)) violation("SCHEMA_INCOMPATIBLE", `${path}.dependencies`, "Task cannot depend on itself");
  assertSafePublicJson(task, path);
  return { taskId, runId, status, progress, parentTaskId, dependencyIds };
}

function validateTaskSet(tasks, path) {
  if (new Set(tasks.map((task) => task.taskId)).size !== tasks.length) {
    violation("SCHEMA_INCOMPATIBLE", path, "duplicate Task identity");
  }
  const knownTaskIds = new Set(tasks.map((task) => task.taskId));
  for (const [index, task] of tasks.entries()) {
    if (task.parentTaskId !== null && !knownTaskIds.has(task.parentTaskId)) {
      violation("IDENTITY_MISMATCH", `${path}[${index}].parent_task_id`, "parent is not a Task in the same Run");
    }
    for (const dependencyId of task.dependencyIds) {
      if (!knownTaskIds.has(dependencyId)) {
        violation("IDENTITY_MISMATCH", `${path}[${index}].dependencies`, `unknown same-Run dependency ${dependencyId}`);
      }
    }
  }
  const visiting = new Set();
  const visited = new Set();
  const byId = new Map(tasks.map((task) => [task.taskId, task]));
  const visit = (taskId) => {
    if (visiting.has(taskId)) violation("INTEGRITY_FAILURE", path, "Task dependency graph contains a cycle");
    if (visited.has(taskId)) return;
    visiting.add(taskId);
    for (const dependencyId of byId.get(taskId).dependencyIds) visit(dependencyId);
    visiting.delete(taskId);
    visited.add(taskId);
  };
  for (const task of tasks) visit(task.taskId);
}

function taskEdges(tasks) {
  return tasks.flatMap((task) => task.dependencyIds.map((dependencyId) => ({
    sourceTaskId: dependencyId,
    targetTaskId: task.taskId
  })));
}

function readGraph(value, path, expectedRunId, expectedObjectId, expectedGraphId, expectedVersion) {
  const graph = objectAt(value, path);
  exactKeysAt(graph, ["graph_id", "run_id", "version", "tasks"], path);
  assertSafePublicJson(graph, path);
  const graphId = equalAt(idAt(graph.graph_id, `${path}.graph_id`), expectedGraphId, `${path}.graph_id`);
  const runId = equalAt(idAt(graph.run_id, `${path}.run_id`), expectedRunId, `${path}.run_id`);
  const version = equalAt(integerAt(graph.version, `${path}.version`, 1), expectedVersion, `${path}.version`);
  const tasks = arrayAt(graph.tasks, `${path}.tasks`).map((item, index) =>
    readTask(item, `${path}.tasks[${index}]`, expectedRunId, expectedObjectId)
  );
  validateTaskSet(tasks, `${path}.tasks`);
  return {
    graphId,
    runId,
    version,
    tasks,
    taskIds: tasks.map((task) => task.taskId),
    edges: taskEdges(tasks)
  };
}

function readObject(value, expectedObjectId) {
  const object = objectAt(value, "projection.object");
  exactKeysAt(object, OBJECT_KEYS, "projection.object");
  const objectId = equalAt(idAt(object.object_id, "projection.object.object_id"), expectedObjectId, "projection.object.object_id");
  return {
    objectId,
    symbol: stringAt(object.symbol, "projection.object.symbol"),
    companyName: stringAt(object.company_name, "projection.object.company_name"),
    objectType: stringAt(object.object_type, "projection.object.object_type"),
    exchange: stringAt(object.exchange, "projection.object.exchange"),
    sector: nullableStringAt(object.sector, "projection.object.sector"),
    currency: stringAt(object.currency, "projection.object.currency"),
    identityVersion: anyIntegerAt(object.identity_version, "projection.object.identity_version")
  };
}

function readRun(value, expected = {}) {
  const run = objectAt(value, "projection.run");
  exactKeysAt(run, RUN_KEYS, "projection.run");
  const runId = equalAt(idAt(run.run_id, "projection.run.run_id"), expected.runId, "projection.run.run_id");
  const objectId = equalAt(idAt(run.research_object_id, "projection.run.research_object_id"), expected.objectId, "projection.run.research_object_id");
  const status = stringAt(run.status, "projection.run.status");
  const stage = RUN_STAGE_BY_STATUS[status];
  if (!stage) violation("SCHEMA_INCOMPATIBLE", "projection.run.status", "unsupported Run status");
  equalAt(stringAt(run.stage, "projection.run.stage"), stage, "projection.run.stage", "SCHEMA_INCOMPATIBLE");
  const completedAt = nullableTimestampAt(run.completed_at, "projection.run.completed_at");
  const terminal = Object.hasOwn(TERMINAL_OUTCOME_BY_STATUS, status);
  if (terminal !== (completedAt !== null)) {
    violation("SCHEMA_INCOMPATIBLE", "projection.run.completed_at", "completed_at must be non-null exactly for terminal Run status");
  }
  return {
    runId,
    objectId,
    goalId: idAt(run.goal_id, "projection.run.goal_id"),
    schemeId: idAt(run.scheme_id, "projection.run.scheme_id"),
    status,
    stage,
    asOf: dateAt(run.as_of, "projection.run.as_of"),
    plannedGraphId: idAt(run.planned_graph_id, "projection.run.planned_graph_id"),
    actualGraphId: nullableIdAt(run.actual_graph_id, "projection.run.actual_graph_id"),
    executionTarget: stringAt(run.execution_target, "projection.run.execution_target"),
    createdAt: timestampAt(run.created_at, "projection.run.created_at"),
    startedAt: nullableTimestampAt(run.started_at, "projection.run.started_at"),
    completedAt,
    updatedAt: timestampAt(run.updated_at, "projection.run.updated_at")
  };
}

function readPathChanges(value, tasks, graphVersion) {
  const knownTaskIds = new Set(tasks.map((task) => task.taskId));
  const identities = new Set();
  return arrayAt(value, "projection.path_changes").map((item, index) => {
    const path = `projection.path_changes[${index}]`;
    const change = objectAt(item, path);
    exactKeysAt(change, PATH_CHANGE_KEYS, path);
    const pathChangeId = idAt(change.path_change_id, `${path}.path_change_id`);
    equalAt(idAt(change.source_id, `${path}.source_id`), pathChangeId, `${path}.source_id`, "INTEGRITY_FAILURE");
    if (identities.has(pathChangeId)) violation("INTEGRITY_FAILURE", `${path}.path_change_id`, "duplicate PathChange identity");
    identities.add(pathChangeId);
    const sourceKind = stringAt(change.source_kind, `${path}.source_kind`);
    if (!new Set(["CORRECTION", "REPLAN"]).has(sourceKind)) violation("SCHEMA_INCOMPATIBLE", `${path}.source_kind`, "unsupported source kind");
    const changeKind = stringAt(change.change_kind, `${path}.change_kind`);
    if (!new Set(["SELF_CORRECTION", "ADD_TASK", "CHANGE_DEPENDENCY"]).has(changeKind)) {
      violation("SCHEMA_INCOMPATIBLE", `${path}.change_kind`, "unsupported change kind");
    }
    if ((sourceKind === "CORRECTION") !== (changeKind === "SELF_CORRECTION")) {
      violation("INTEGRITY_FAILURE", path, "Correction/Replan kind combination is impossible");
    }
    const taskRefs = uniqueIdsAt(change.task_refs, `${path}.task_refs`);
    for (const taskId of taskRefs) {
      if (!knownTaskIds.has(taskId)) violation("IDENTITY_MISMATCH", `${path}.task_refs`, `unknown same-Run Task ${taskId}`);
    }
    const operations = arrayAt(change.operations, `${path}.operations`).map((rawOperation, operationIndex) => {
      const operationPath = `${path}.operations[${operationIndex}]`;
      const operation = objectAt(rawOperation, operationPath);
      const kind = stringAt(operation.operation, `${operationPath}.operation`);
      if (kind === "add_node") {
        exactKeysAt(operation, ["operation", "task_id"], operationPath);
        const taskId = idAt(operation.task_id, `${operationPath}.task_id`);
        if (!knownTaskIds.has(taskId) || !taskRefs.includes(taskId)) {
          violation("IDENTITY_MISMATCH", operationPath, "add_node Task must be in the same Run and PathChange refs");
        }
        return { operation: kind, taskId };
      }
      if (kind === "add_edge" || kind === "remove_edge") {
        exactKeysAt(operation, ["operation", "task_id", "dependency_task_id"], operationPath);
        const taskId = idAt(operation.task_id, `${operationPath}.task_id`);
        const dependencyTaskId = idAt(
          operation.dependency_task_id,
          `${operationPath}.dependency_task_id`
        );
        if (
          !knownTaskIds.has(taskId) || !knownTaskIds.has(dependencyTaskId) ||
          !taskRefs.includes(taskId) || !taskRefs.includes(dependencyTaskId)
        ) {
          violation(
            "IDENTITY_MISMATCH",
            operationPath,
            "edge-operation Tasks must be in the same Run and PathChange refs"
          );
        }
        return { operation: kind, taskId, dependencyTaskId };
      }
      violation("SCHEMA_INCOMPATIBLE", `${operationPath}.operation`, "unsupported graph operation");
    });
    const graphVersionBefore = change.graph_version_before === null
      ? null
      : integerAt(change.graph_version_before, `${path}.graph_version_before`, 1);
    const graphVersionAfter = change.graph_version_after === null
      ? null
      : integerAt(change.graph_version_after, `${path}.graph_version_after`, 1);
    if (graphVersionAfter !== null && graphVersion !== null && graphVersionAfter > graphVersion) {
      violation("INTEGRITY_FAILURE", `${path}.graph_version_after`, "PathChange version is beyond the atomic graph version");
    }
    return {
      pathChangeId,
      sourceId: pathChangeId,
      sourceKind,
      changeKind,
      status: stringAt(change.status, `${path}.status`),
      decision: nullableStringAt(change.decision, `${path}.decision`),
      reasonCode: nullableStringAt(change.reason_code, `${path}.reason_code`),
      taskRefs,
      operations,
      graphVersionBefore,
      graphVersionAfter,
      createdAt: timestampAt(change.created_at, `${path}.created_at`),
      resolvedAt: nullableTimestampAt(change.resolved_at, `${path}.resolved_at`)
    };
  });
}

function readLifecycle(value, run, tasks) {
  const lifecycle = objectAt(value, "projection.lifecycle");
  exactKeysAt(lifecycle, ["status", "stage", "progress", "terminal", "terminal_outcome", "safe_failure"], "projection.lifecycle");
  equalAt(stringAt(lifecycle.status, "projection.lifecycle.status"), run.status, "projection.lifecycle.status", "INTEGRITY_FAILURE");
  equalAt(stringAt(lifecycle.stage, "projection.lifecycle.stage"), run.stage, "projection.lifecycle.stage", "INTEGRITY_FAILURE");
  const progress = objectAt(lifecycle.progress, "projection.lifecycle.progress");
  exactKeysAt(progress, ["method", "completed_tasks", "total_tasks", "fraction"], "projection.lifecycle.progress");
  literalAt(progress.method, "ACTUAL_TASK_MEAN_V1", "projection.lifecycle.progress.method");
  const completedTasks = integerAt(progress.completed_tasks, "projection.lifecycle.progress.completed_tasks", 0);
  const totalTasks = integerAt(progress.total_tasks, "projection.lifecycle.progress.total_tasks", 0);
  equalAt(totalTasks, tasks.length, "projection.lifecycle.progress.total_tasks", "INTEGRITY_FAILURE");
  equalAt(
    completedTasks,
    tasks.filter((task) => task.status === "COMPLETED").length,
    "projection.lifecycle.progress.completed_tasks",
    "INTEGRITY_FAILURE"
  );
  const fraction = numberAt(progress.fraction, "projection.lifecycle.progress.fraction", 0, 1);
  const terminalTaskStatuses = new Set(["COMPLETED", "FAILED", "CAPABILITY_BUILD_FAILED", "CANCELLED"]);
  const allTasksTerminal = tasks.every((task) => terminalTaskStatuses.has(task.status));
  const expectedFraction = run.status === "RELEASED"
    || (new Set(["FAILED", "CANCELLED"]).has(run.status) && allTasksTerminal)
    ? 1
    : tasks.length === 0
      ? 0
      : tasks.reduce((sum, task) => sum + task.progress, 0) / tasks.length;
  if (Math.abs(fraction - expectedFraction) > Number.EPSILON * Math.max(1, tasks.length)) {
    violation("INTEGRITY_FAILURE", "projection.lifecycle.progress.fraction", "fraction is not the authoritative Task mean");
  }
  const terminal = booleanAt(lifecycle.terminal, "projection.lifecycle.terminal");
  const expectedOutcome = TERMINAL_OUTCOME_BY_STATUS[run.status] ?? null;
  equalAt(terminal, expectedOutcome !== null, "projection.lifecycle.terminal", "INTEGRITY_FAILURE");
  equalAt(nullableStringAt(lifecycle.terminal_outcome, "projection.lifecycle.terminal_outcome"), expectedOutcome, "projection.lifecycle.terminal_outcome", "INTEGRITY_FAILURE");
  if (lifecycle.safe_failure !== null) {
    const failure = objectAt(lifecycle.safe_failure, "projection.lifecycle.safe_failure");
    exactKeysAt(
      failure,
      ["status", "failure_stage", "failure_code", "safe_message"],
      "projection.lifecycle.safe_failure"
    );
    equalAt(stringAt(failure.status, "projection.lifecycle.safe_failure.status"), run.status, "projection.lifecycle.safe_failure.status", "INTEGRITY_FAILURE");
    const stage = stringAt(failure.failure_stage, "projection.lifecycle.safe_failure.failure_stage");
    const code = stringAt(failure.failure_code, "projection.lifecycle.safe_failure.failure_code");
    if (run.status === "CANCELLED") {
      if (stage !== "CANCELLATION" || code !== "RUN_CANCELLED") {
        violation("INTEGRITY_FAILURE", "projection.lifecycle.safe_failure", "CANCELLED failure tuple is invalid");
      }
    } else if (!FAILURE_CODES_BY_STAGE[stage]?.has(code)) {
      violation("SCHEMA_INCOMPATIBLE", "projection.lifecycle.safe_failure", "unsupported failure stage/code tuple");
    }
    nullableStringAt(failure.safe_message, "projection.lifecycle.safe_failure.safe_message");
    assertSafePublicJson(failure, "projection.lifecycle.safe_failure");
  }
  if (new Set(["FAILED", "CANCELLED"]).has(run.status) && lifecycle.safe_failure === null) {
    violation("INTEGRITY_FAILURE", "projection.lifecycle.safe_failure", "unsuccessful terminal Run requires a safe failure fact");
  }
  if (!terminal && lifecycle.safe_failure !== null) {
    violation("INTEGRITY_FAILURE", "projection.lifecycle.safe_failure", "nonterminal Run cannot carry a terminal safe failure fact");
  }
  return {
    status: run.status,
    stage: run.stage,
    progress: { method: "ACTUAL_TASK_MEAN_V1", completedTasks, totalTasks, fraction },
    terminal,
    terminalOutcome: expectedOutcome,
    safeFailure: structuredClone(lifecycle.safe_failure)
  };
}

function readOwnedSummaries(wire, run) {
  const review = objectAt(wire.review, "projection.review");
  exactKeysAt(review, ["availability", "review_id", "status"], "projection.review");
  const reviewAvailability = decodeAvailability(review.availability, "projection.review.availability");
  const reviewId = nullableIdAt(review.review_id, "projection.review.review_id");
  const reviewStatus = nullableStringAt(review.status, "projection.review.status");
  if (reviewStatus !== null && !new Set(["PASS", "REVIEW", "BLOCK"]).has(reviewStatus)) {
    violation("SCHEMA_INCOMPATIBLE", "projection.review.status", "unsupported Review status");
  }
  if (reviewAvailability.status === "AVAILABLE" && (reviewId === null || reviewStatus === null)) {
    violation("INTEGRITY_FAILURE", "projection.review", "available Review requires explicit identity and status");
  }
  if ((reviewAvailability.status === "AVAILABLE") !== (reviewId !== null)) {
    violation("INTEGRITY_FAILURE", "projection.review", "Review identity/status must be present exactly when AVAILABLE");
  }

  const result = objectAt(wire.result, "projection.result");
  exactKeysAt(result, ["availability", "released_result_id", "canonical_record_id", "released_at"], "projection.result");
  const resultAvailability = decodeAvailability(result.availability, "projection.result.availability");
  const releasedResultId = nullableIdAt(result.released_result_id, "projection.result.released_result_id");
  const canonicalRecordId = nullableIdAt(result.canonical_record_id, "projection.result.canonical_record_id");
  const releasedAt = nullableTimestampAt(result.released_at, "projection.result.released_at");
  const resultTuplePresent = [releasedResultId, canonicalRecordId, releasedAt].filter((item) => item !== null).length;
  if (resultTuplePresent !== 0 && resultTuplePresent !== 3) {
    violation("INTEGRITY_FAILURE", "projection.result", "released result identity/time tuple must be wholly present or absent");
  }
  if (resultAvailability.status === "AVAILABLE" && resultTuplePresent !== 3) {
    violation("INTEGRITY_FAILURE", "projection.result", "available result requires full released identity tuple");
  }
  if ((resultAvailability.status === "AVAILABLE") !== (resultTuplePresent === 3)) {
    violation("INTEGRITY_FAILURE", "projection.result", "result identity/time must be present exactly when AVAILABLE");
  }
  if (run.status !== "RELEASED" && resultTuplePresent !== 0) {
    violation("INTEGRITY_FAILURE", "projection.result", "non-RELEASED Run cannot expose a released result identity tuple");
  }

  const artifacts = objectAt(wire.artifacts, "projection.artifacts");
  exactKeysAt(artifacts, ["availability", "report_id", "representation_ids"], "projection.artifacts");
  const artifactsAvailability = decodeAvailability(artifacts.availability, "projection.artifacts.availability");
  const reportId = nullableIdAt(artifacts.report_id, "projection.artifacts.report_id");
  const representationIds = uniqueIdsAt(artifacts.representation_ids, "projection.artifacts.representation_ids");
  if (artifactsAvailability.status === "AVAILABLE" && (reportId === null || representationIds.length === 0)) {
    violation("INTEGRITY_FAILURE", "projection.artifacts", "available artifacts require report and representation identities");
  }
  if ((reportId === null) !== (representationIds.length === 0)) {
    violation("INTEGRITY_FAILURE", "projection.artifacts", "artifact report and representation identities are partial");
  }
  if ((artifactsAvailability.status === "AVAILABLE") !== (reportId !== null)) {
    violation("INTEGRITY_FAILURE", "projection.artifacts", "artifact identities must be present exactly when AVAILABLE");
  }

  const proof = objectAt(wire.proof, "projection.proof");
  exactKeysAt(proof, ["availability", "policy", "status", "proof_refs"], "projection.proof");
  const proofAvailability = decodeAvailability(proof.availability, "projection.proof.availability");
  const policy = stringAt(proof.policy, "projection.proof.policy");
  if (!new Set(["NOT_REQUIRED", "MUST_PROVE", "MIXED", "UNKNOWN"]).has(policy)) {
    violation("SCHEMA_INCOMPATIBLE", "projection.proof.policy", "unsupported proof policy");
  }
  const proofStatus = nullableStringAt(proof.status, "projection.proof.status");
  if (proofStatus !== null && !PROOF_STATUSES.has(proofStatus)) {
    violation("SCHEMA_INCOMPATIBLE", "projection.proof.status", "unsupported proof status");
  }
  const proofRefs = uniqueIdsAt(proof.proof_refs, "projection.proof.proof_refs");
  if (proofAvailability.status === "AVAILABLE" && proofStatus === null) {
    violation("INTEGRITY_FAILURE", "projection.proof.status", "available proof requires explicit status");
  }

  const execution = objectAt(wire.execution, "projection.execution");
  exactKeysAt(execution, ["availability", "canonical_record_id"], "projection.execution");
  const executionAvailability = decodeAvailability(execution.availability, "projection.execution.availability");
  const executionCanonicalRecordId = nullableIdAt(execution.canonical_record_id, "projection.execution.canonical_record_id");
  if (executionAvailability.status === "AVAILABLE" && executionCanonicalRecordId === null) {
    violation("INTEGRITY_FAILURE", "projection.execution", "available execution requires canonical identity");
  }
  if ((executionAvailability.status === "AVAILABLE") !== (executionCanonicalRecordId !== null)) {
    violation("INTEGRITY_FAILURE", "projection.execution", "execution identity must be present exactly when AVAILABLE");
  }
  if (executionCanonicalRecordId !== null && canonicalRecordId !== null) {
    equalAt(executionCanonicalRecordId, canonicalRecordId, "projection.execution.canonical_record_id", "INTEGRITY_FAILURE");
  }
  if (Object.hasOwn(TERMINAL_OUTCOME_BY_STATUS, run.status)) {
    for (const [name, availability] of [
      ["review", reviewAvailability],
      ["result", resultAvailability],
      ["artifacts", artifactsAvailability],
      ["proof", proofAvailability],
      ["execution", executionAvailability]
    ]) {
      if (availability.status === "PENDING") {
        violation("INTEGRITY_FAILURE", `projection.${name}.availability`, "terminal Run cannot retain PENDING availability");
      }
    }
  }
  return {
    review: { availability: reviewAvailability, reviewId, status: reviewStatus },
    result: { availability: resultAvailability, releasedResultId, canonicalRecordId, releasedAt },
    artifacts: { availability: artifactsAvailability, reportId, representationIds },
    proof: { availability: proofAvailability, policy, status: proofStatus, proofRefs },
    execution: { availability: executionAvailability, canonicalRecordId: executionCanonicalRecordId }
  };
}

function readTerminal(value, run, projectionSequence) {
  const terminal = objectAt(value, "projection.terminal");
  exactKeysAt(terminal, ["is_terminal", "outcome", "event_id", "sequence"], "projection.terminal");
  const isTerminal = booleanAt(terminal.is_terminal, "projection.terminal.is_terminal");
  const expectedOutcome = TERMINAL_OUTCOME_BY_STATUS[run.status] ?? null;
  equalAt(isTerminal, expectedOutcome !== null, "projection.terminal.is_terminal", "INTEGRITY_FAILURE");
  const outcome = nullableStringAt(terminal.outcome, "projection.terminal.outcome");
  equalAt(outcome, expectedOutcome, "projection.terminal.outcome", "INTEGRITY_FAILURE");
  const eventId = nullableIdAt(terminal.event_id, "projection.terminal.event_id");
  const sequence = terminal.sequence === null ? null : integerAt(terminal.sequence, "projection.terminal.sequence", 1);
  if (isTerminal) {
    if (eventId === null || sequence === null || sequence !== projectionSequence) {
      violation("INTEGRITY_FAILURE", "projection.terminal", "terminal event identity/sequence is invalid");
    }
  } else if (eventId !== null || sequence !== null) {
    violation("INTEGRITY_FAILURE", "projection.terminal", "nonterminal projection cannot carry terminal metadata");
  }
  return { isTerminal, outcome, eventId, sequence };
}

function readActivity(value, path, expectedRunTaskIds) {
  const activity = objectAt(value, path);
  const presentOptional = ACTIVITY_OPTIONAL_KEYS.filter((key) => Object.hasOwn(activity, key));
  exactKeysAt(activity, [...ACTIVITY_REQUIRED_KEYS, ...presentOptional], path);
  const eventId = idAt(activity.event_id, `${path}.event_id`);
  const type = stringAt(activity.type, `${path}.type`);
  const sequence = integerAt(activity.sequence, `${path}.sequence`, 1);
  const timestamp = timestampAt(activity.timestamp, `${path}.timestamp`);
  const taskId = nullableIdAt(activity.task_id, `${path}.task_id`);
  if (taskId !== null && !expectedRunTaskIds.has(taskId)) {
    violation("IDENTITY_MISMATCH", `${path}.task_id`, "activity references an unknown Task");
  }
  stringAt(activity.message_code, `${path}.message_code`);
  for (const key of ["status", "actor_id", "actor_type"]) {
    if (Object.hasOwn(activity, key)) nullableStringAt(activity[key], `${path}.${key}`);
  }
  if (Object.hasOwn(activity, "duration_ms") && activity.duration_ms !== null) {
    integerAt(activity.duration_ms, `${path}.duration_ms`, 0);
  }
  for (const key of ACTIVITY_OPTIONAL_KEYS.filter((key) => key.endsWith("_refs"))) {
    if (Object.hasOwn(activity, key)) uniqueIdsAt(activity[key], `${path}.${key}`);
  }
  assertSafePublicJson(activity, path);
  return { eventId, type, sequence, timestamp, taskId, status: activity.status ?? null };
}

export function decodeAtomicRunProjection(value, expectedAdmission = {}) {
  const wire = objectAt(value, "projection");
  exactKeysAt(wire, PROJECTION_KEYS, "projection");
  literalAt(wire.projection_schema_version, CONTRACT.projection, "projection.projection_schema_version");
  const projectionRevision = integerAt(wire.projection_revision, "projection.projection_revision", 1);
  const projectionSequence = integerAt(wire.projection_sequence, "projection.projection_sequence", 0);
  const generatedAt = timestampAt(wire.generated_at, "projection.generated_at");
  const object = readObject(wire.object, expectedAdmission?.objectId);
  const run = readRun(wire.run, { runId: expectedAdmission?.runId, objectId: object.objectId });
  const goal = decodeGoal(wire.goal, "projection.goal", {
    goalId: expectedAdmission?.goalId ?? run.goalId,
    objectId: object.objectId,
    asOf: run.asOf,
    goalText: expectedAdmission?.goal?.goalText,
    preferences: expectedAdmission?.goal?.preferences,
    createdAt: expectedAdmission?.goal?.createdAt
  });
  equalAt(run.goalId, goal.goalId, "projection.run.goal_id");
  const scheme = decodeScheme(wire.confirmed_scheme, "projection.confirmed_scheme", {
    schemeId: expectedAdmission?.schemeId ?? run.schemeId,
    objectId: object.objectId,
    goalId: goal.goalId,
    researchScope: expectedAdmission?.schemeSnapshot?.researchScope,
    dataRequirements: expectedAdmission?.schemeSnapshot?.dataRequirements,
    agentRequirements: expectedAdmission?.schemeSnapshot?.agentRequirements,
    skillRequirements: expectedAdmission?.schemeSnapshot?.skillRequirements,
    calculationRequirements: expectedAdmission?.schemeSnapshot?.calculationRequirements,
    assuranceRequirements: expectedAdmission?.schemeSnapshot?.assuranceRequirements,
    reportRequirements: expectedAdmission?.schemeSnapshot?.reportRequirements,
    limitations: expectedAdmission?.schemeSnapshot?.limitations,
    generatedBy: expectedAdmission?.schemeSnapshot?.generatedBy,
    generatedModel: expectedAdmission?.schemeSnapshot?.generatedModel,
    createdAt: expectedAdmission?.schemeSnapshot?.createdAt
  }, { confirmed: true });
  equalAt(run.schemeId, scheme.schemeId, "projection.run.scheme_id");

  const graphVersion = wire.graph_version === null ? null : integerAt(wire.graph_version, "projection.graph_version", 1);
  const plannedGraph = readGraph(
    wire.planned_graph,
    "projection.planned_graph",
    run.runId,
    object.objectId,
    expectedAdmission?.plannedGraphId ?? run.plannedGraphId,
    undefined
  );
  equalAt(plannedGraph.graphId, run.plannedGraphId, "projection.run.planned_graph_id", "INTEGRITY_FAILURE");

  let actualGraph = null;
  if (wire.actual_graph !== null) {
    if (graphVersion === null || run.actualGraphId === null) {
      violation("SCHEMA_INCOMPATIBLE", "projection.actual_graph", "actual graph requires graph ID and version");
    }
    actualGraph = readGraph(
      wire.actual_graph,
      "projection.actual_graph",
      run.runId,
      object.objectId,
      run.actualGraphId,
      graphVersion
    );
  } else if (graphVersion !== null || run.actualGraphId !== null) {
    violation("SCHEMA_INCOMPATIBLE", "projection.actual_graph", "actual graph/id/version nullability is inconsistent");
  }

  const tasks = arrayAt(wire.tasks, "projection.tasks").map((item, index) =>
    readTask(item, `projection.tasks[${index}]`, run.runId, object.objectId)
  );
  validateTaskSet(tasks, "projection.tasks");
  const activeGraph = actualGraph ?? plannedGraph;
  const projectedIds = new Set(tasks.map((task) => task.taskId));
  const activeIds = new Set(activeGraph.taskIds);
  if (projectedIds.size !== activeIds.size || [...projectedIds].some((taskId) => !activeIds.has(taskId))) {
    violation("IDENTITY_MISMATCH", "projection.tasks", "Task identities disagree with the active Graph");
  }
  const activeTasks = new Map(activeGraph.tasks.map((task) => [task.taskId, task]));
  for (const [index, task] of tasks.entries()) {
    const graphed = activeTasks.get(task.taskId);
    if (
      graphed.status !== task.status
      || graphed.progress !== task.progress
      || graphed.parentTaskId !== task.parentTaskId
      || JSON.stringify(graphed.dependencyIds) !== JSON.stringify(task.dependencyIds)
    ) {
      violation("IDENTITY_MISMATCH", `projection.tasks[${index}]`, "Task truth disagrees with the active Graph");
    }
  }
  if (actualGraph) {
    const actualIds = new Set(actualGraph.taskIds);
    for (const taskId of plannedGraph.taskIds) {
      if (!actualIds.has(taskId)) violation("IDENTITY_MISMATCH", "projection.actual_graph.tasks", `actual Graph omits planned Task ${taskId}`);
    }
  }

  const pathChanges = readPathChanges(wire.path_changes, tasks, graphVersion);
  const taskIds = new Set(tasks.map((task) => task.taskId));
  const activity = arrayAt(wire.activity, "projection.activity").map((item, index) =>
    readActivity(item, `projection.activity[${index}]`, taskIds)
  );
  if (new Set(activity.map((item) => item.eventId)).size !== activity.length) {
    violation("SCHEMA_INCOMPATIBLE", "projection.activity", "duplicate RuntimeEvent identity");
  }
  for (const [index, item] of activity.entries()) {
    if (item.sequence > projectionSequence || (index > 0 && item.sequence <= activity[index - 1].sequence)) {
      violation("INTEGRITY_FAILURE", `projection.activity[${index}].sequence`, "activity sequence is not strictly ordered within projection watermark");
    }
  }
  const lifecycle = readLifecycle(wire.lifecycle, run, tasks);
  const summaries = readOwnedSummaries(wire, run);
  const terminal = readTerminal(wire.terminal, run, projectionSequence);
  equalAt(lifecycle.terminal, terminal.isTerminal, "projection.lifecycle.terminal", "INTEGRITY_FAILURE");
  if (terminal.isTerminal) {
    const finalActivity = activity.at(-1);
    if (!finalActivity || finalActivity.eventId !== terminal.eventId || finalActivity.sequence !== terminal.sequence) {
      violation("INTEGRITY_FAILURE", "projection.terminal", "terminal state does not close to final activity");
    }
    const expectedType = run.status === "RELEASED" ? "run.completed" : "run.failed";
    if (finalActivity.type !== expectedType || finalActivity.status !== run.status) {
      violation("INTEGRITY_FAILURE", "projection.activity", "terminal activity contradicts Run status");
    }
  }
  if (run.status === "RELEASED") {
    for (const [name, availability] of [
      ["review", summaries.review.availability],
      ["result", summaries.result.availability],
      ["artifacts", summaries.artifacts.availability],
      ["proof", summaries.proof.availability],
      ["execution", summaries.execution.availability]
    ]) {
      if (availability.status !== "AVAILABLE") {
        violation("INTEGRITY_FAILURE", `projection.${name}.availability`, "RELEASED Run requires complete release closure");
      }
    }
    if (summaries.review.status !== "PASS") {
      violation("INTEGRITY_FAILURE", "projection.review.status", "RELEASED Run requires PASS Review");
    }
    const expectedProofStatus = summaries.proof.policy === "NOT_REQUIRED" ? "NOT_REQUIRED" : "VERIFIED";
    if (
      summaries.proof.policy === "UNKNOWN"
      || summaries.proof.status !== expectedProofStatus
      || (summaries.proof.policy !== "NOT_REQUIRED" && summaries.proof.proofRefs.length === 0)
    ) {
      violation("INTEGRITY_FAILURE", "projection.proof", "RELEASED Run requires explicit satisfied proof policy");
    }
    if (lifecycle.safeFailure !== null) {
      violation("INTEGRITY_FAILURE", "projection.lifecycle.safe_failure", "successful release cannot carry safe failure");
    }
  } else if (summaries.result.availability.status === "AVAILABLE") {
    violation("INTEGRITY_FAILURE", "projection.result.availability", "only RELEASED Run may expose available Results");
  }
  if (new Set(["FAILED", "CANCELLED"]).has(run.status)
      && summaries.artifacts.availability.status === "AVAILABLE") {
    violation("INTEGRITY_FAILURE", "projection.artifacts.availability", "unsuccessful terminal Run cannot expose available artifacts");
  }

  return deepFreeze({
    projectionSchemaVersion: CONTRACT.projection,
    projectionRevision,
    projectionSequence,
    generatedAt,
    object,
    objectId: object.objectId,
    run,
    runId: run.runId,
    goal,
    goalId: goal.goalId,
    confirmedScheme: scheme,
    schemeId: scheme.schemeId,
    plannedGraph,
    plannedGraphId: plannedGraph.graphId,
    actualGraph,
    graphVersion,
    tasks: tasks.map((task) => ({ ...task, dependencyIds: [...task.dependencyIds] })),
    taskIds: tasks.map((task) => task.taskId),
    taskEdges: taskEdges(tasks),
    pathChanges,
    activity: structuredClone(activity),
    lifecycle,
    ...summaries,
    terminal,
    status: run.status,
    stage: run.stage
  });
}

export function expectedAtomicProjectionEtag(projection) {
  const record = objectAt(projection, "projection");
  const runId = idAt(record.runId, "projection.runId");
  const revision = integerAt(record.projectionRevision, "projection.projectionRevision", 1);
  const sequence = integerAt(record.projectionSequence, "projection.projectionSequence", 0);
  return `"p4:${runId}:${revision}:${sequence}"`;
}

export function assertAtomicProjectionEtag(headerValue, projection) {
  equalAt(
    stringAt(headerValue, "headers.etag"),
    expectedAtomicProjectionEtag(projection),
    "headers.etag",
    "INTEGRITY_FAILURE"
  );
}

export function decodeErrorEnvelope(value, httpStatus) {
  const wire = objectAt(value, "errorEnvelope");
  exactKeysAt(wire, ["schema_version", "error"], "errorEnvelope");
  literalAt(wire.schema_version, CONTRACT.error, "errorEnvelope.schema_version");
  const error = objectAt(wire.error, "errorEnvelope.error");
  exactKeysAt(
    error,
    ["code", "message", "retryable", "recovery", "request_id", "resource", "details"],
    "errorEnvelope.error"
  );
  const code = stringAt(error.code, "errorEnvelope.error.code");
  const protocol = ERROR_PROTOCOL[code];
  if (!protocol) violation("SCHEMA_INCOMPATIBLE", "errorEnvelope.error.code", "unsupported error code");
  if (httpStatus !== undefined) equalAt(httpStatus, protocol[0], "http.status", "SCHEMA_INCOMPATIBLE");
  equalAt(booleanAt(error.retryable, "errorEnvelope.error.retryable"), protocol[1], "errorEnvelope.error.retryable", "SCHEMA_INCOMPATIBLE");
  equalAt(stringAt(error.recovery, "errorEnvelope.error.recovery"), protocol[2], "errorEnvelope.error.recovery", "SCHEMA_INCOMPATIBLE");
  const resource = error.resource === null ? null : objectAt(error.resource, "errorEnvelope.error.resource");
  if (resource) {
    exactKeysAt(resource, ["type", "id"], "errorEnvelope.error.resource");
    idAt(resource.type, "errorEnvelope.error.resource.type");
    idAt(resource.id, "errorEnvelope.error.resource.id");
  }
  assertNoPublicSurfaceLeaks(error.message, "errorEnvelope.error.message");
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
    const findings = findPublicSurfaceLeaks([{ path, source: value }]);
    if (findings.length) violation("UNSAFE_PUBLIC_CONTENT", path, findings.map((finding) => finding.code).join(","));
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

export function assertNoSecondStartRequest(requests, confirmPathname = "/api/research-runs") {
  const mutations = requests.filter((request) => request.method !== "GET" && request.method !== "HEAD" && request.method !== "OPTIONS");
  const confirm = mutations.filter((request) => request.method === "POST" && request.pathname === confirmPathname);
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

export const ADVERSARIAL_CANONICAL_DECIMAL_PROPERTY = "NUMBER_STRING_ROUNDTRIP_CHANGES";

export function isAdversarialCanonicalDecimal(value) {
  if (typeof value !== "string" || !CANONICAL_DECIMAL_PATTERN.test(value)) return false;
  if (value === "-0" || /^-0\.0+$/.test(value)) return false;
  const numeric = Number(value);
  return Number.isFinite(numeric) && String(numeric) !== value;
}

export function decodeReleasedFinancialMetricEvidence(value, expected = {}) {
  const root = objectAt(value, "releasedResult");
  exactKeysAt(root, [
    "object_id", "run_id", "released_result_id", "canonical_record_id", "released_at", "metrics",
    "claims", "material_calculation_dispositions", "research_source_coverage", "limitations", "availability"
  ], "releasedResult");
  const rootRunId = equalAt(idAt(root.run_id, "releasedResult.run_id"), expected.runId, "releasedResult.run_id");
  const objectId = equalAt(idAt(root.object_id, "releasedResult.object_id"), expected.objectId, "releasedResult.object_id");
  idAt(root.released_result_id, "releasedResult.released_result_id");
  idAt(root.canonical_record_id, "releasedResult.canonical_record_id");
  timestampAt(root.released_at, "releasedResult.released_at");
  const availability = decodeAvailability(root.availability, "releasedResult.availability");
  if (availability.status !== "AVAILABLE") {
    violation("INTEGRITY_FAILURE", "releasedResult.availability", "released result body must be AVAILABLE");
  }
  const metrics = arrayAt(root.metrics, "releasedResult.metrics");
  const candidates = metrics
    .map((item, index) => ({ item: objectAt(item, `releasedResult.metrics[${index}]`), path: `releasedResult.metrics[${index}]` }))
    .filter(({ item }) => item.metric_id === expected.metricId);
  if (candidates.length !== 1) {
    violation("INTEGRITY_FAILURE", "releasedResult", `expected exactly one metric ${expected.metricId}; found ${candidates.length}`);
  }
  const { item: metric, path } = candidates[0];
  exactKeysAt(metric, [
    "run_id", "metric_id", "name", "canonical_value", "canonical_unit", "display_value", "display_unit",
    "period", "period_basis", "actuality", "as_of", "currency", "formula_id", "capability_id",
    "calculation_id", "evidence_refs", "claim_refs", "proof", "method_metadata", "technical_price_basis",
    "corporate_action_status", "corporate_action_guard_refs", "limitations"
  ], path);
  const runId = equalAt(idAt(metric.run_id, `${path}.run_id`), expected.runId, `${path}.run_id`);
  equalAt(runId, rootRunId, `${path}.run_id`, "INTEGRITY_FAILURE");
  const metricId = equalAt(idAt(metric.metric_id, `${path}.metric_id`), expected.metricId, `${path}.metric_id`);
  const canonicalValue = stringAt(metric.canonical_value, `${path}.canonical_value`);
  if (!CANONICAL_DECIMAL_PATTERN.test(canonicalValue)) {
    violation("SCHEMA_INCOMPATIBLE", `${path}.canonical_value`, "expected canonical non-exponent decimal string");
  }
  if (expected.adversarialProperty === ADVERSARIAL_CANONICAL_DECIMAL_PROPERTY
      && !isAdversarialCanonicalDecimal(canonicalValue)) {
    violation(
      "INTEGRITY_FAILURE",
      `${path}.canonical_value`,
      "real wire decimal is not adversarial to JavaScript Number string round-trip"
    );
  }
  const canonicalUnit = stringAt(metric.canonical_unit, `${path}.canonical_unit`);
  if (!new Set(["RATIO", "PERCENT", "CURRENCY", "COUNT", "SHARES", "INDEX", "MULTIPLE"]).has(canonicalUnit)) {
    violation("SCHEMA_INCOMPATIBLE", `${path}.canonical_unit`, "unsupported financial unit");
  }
  const periodBasis = stringAt(metric.period_basis, `${path}.period_basis`);
  if (!new Set(["FY", "QUARTER", "TTM", "LTM", "CURRENT", "DAILY"]).has(periodBasis)) {
    violation("SCHEMA_INCOMPATIBLE", `${path}.period_basis`, "unsupported period basis");
  }
  const actuality = stringAt(metric.actuality, `${path}.actuality`);
  if (!new Set(["UNKNOWN", "ACTUAL", "ESTIMATE"]).has(actuality)) {
    violation("SCHEMA_INCOMPATIBLE", `${path}.actuality`, "unsupported actuality");
  }
  const proof = objectAt(metric.proof, `${path}.proof`);
  exactKeysAt(proof, ["policy_id", "requirement", "status", "proof_refs"], `${path}.proof`);
  const proofRequirement = stringAt(proof.requirement, `${path}.proof.requirement`);
  if (!new Set(["NOT_REQUIRED", "MUST_PROVE"]).has(proofRequirement)) {
    violation("SCHEMA_INCOMPATIBLE", `${path}.proof.requirement`, "unsupported proof requirement");
  }
  const evidenceRefs = uniqueIdsAt(metric.evidence_refs, `${path}.evidence_refs`, { allowEmpty: false });
  const claimRefs = uniqueIdsAt(metric.claim_refs, `${path}.claim_refs`, { allowEmpty: false });
  const proofRefs = uniqueIdsAt(proof.proof_refs, `${path}.proof.proof_refs`);
  const proofStatus = stringAt(proof.status, `${path}.proof.status`);
  if (!PROOF_STATUSES.has(proofStatus)) {
    violation("SCHEMA_INCOMPATIBLE", `${path}.proof.status`, "unsupported proof status");
  }
  if (proofRequirement === "MUST_PROVE" && (proofStatus !== "VERIFIED" || proofRefs.length === 0)) {
    violation("INTEGRITY_FAILURE", `${path}.proof`, "released MUST_PROVE metric requires VERIFIED status and proof refs");
  }
  if (proofRequirement === "NOT_REQUIRED" && (proofStatus !== "NOT_REQUIRED" || proofRefs.length !== 0)) {
    violation("INTEGRITY_FAILURE", `${path}.proof`, "released NOT_REQUIRED metric requires NOT_REQUIRED status and no proof refs");
  }
  const corporateActionGuardRefs = uniqueIdsAt(metric.corporate_action_guard_refs, `${path}.corporate_action_guard_refs`);
  const limitations = arrayAt(metric.limitations, `${path}.limitations`);
  limitations.forEach((item, index) => stringAt(item, `${path}.limitations[${index}]`));
  for (const [key, item] of [
    ["method_metadata", metric.method_metadata],
    ["technical_price_basis", metric.technical_price_basis],
    ["corporate_action_status", metric.corporate_action_status]
  ]) {
    if (item !== null) assertSafePublicJson(item, `${path}.${key}`);
  }
  for (const [name, collection] of [
    ["claims", root.claims],
    ["material_calculation_dispositions", root.material_calculation_dispositions],
    ["limitations", root.limitations]
  ]) {
    arrayAt(collection, `releasedResult.${name}`);
    assertSafePublicJson(collection, `releasedResult.${name}`);
  }
  if (root.research_source_coverage !== null) {
    objectAt(root.research_source_coverage, "releasedResult.research_source_coverage");
    assertSafePublicJson(root.research_source_coverage, "releasedResult.research_source_coverage");
  }
  return deepFreeze({
    runId,
    metricId,
    name: stringAt(metric.name, `${path}.name`),
    canonicalValue,
    canonicalUnit,
    displayValue: stringAt(metric.display_value, `${path}.display_value`),
    displayUnit: stringAt(metric.display_unit, `${path}.display_unit`),
    period: stringAt(metric.period, `${path}.period`),
    periodBasis,
    actuality,
    asOf: dateAt(metric.as_of, `${path}.as_of`),
    currency: nullableStringAt(metric.currency, `${path}.currency`),
    formulaId: idAt(metric.formula_id, `${path}.formula_id`),
    capabilityId: idAt(metric.capability_id, `${path}.capability_id`),
    calculationId: idAt(metric.calculation_id, `${path}.calculation_id`),
    evidenceRefs,
    claimRefs,
    proof: {
      policyId: idAt(proof.policy_id, `${path}.proof.policy_id`),
      requirement: proofRequirement,
      status: proofStatus,
      proofRefs
    },
    methodMetadata: structuredClone(metric.method_metadata),
    technicalPriceBasis: structuredClone(metric.technical_price_basis),
    corporateActionStatus: structuredClone(metric.corporate_action_status),
    corporateActionGuardRefs,
    limitations: structuredClone(limitations)
  });
}

export function sha256Text(value) {
  return createHash("sha256").update(String(value), "utf8").digest("hex");
}

export function sha256Bytes(value) {
  return createHash("sha256").update(value).digest("hex");
}
