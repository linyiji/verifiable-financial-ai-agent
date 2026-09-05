import type { ConnectionState, NormalizedRuntimeEventV1 } from "../types/domain";

export const PHASE4_CONTRACT_VERSION = "phase4-core/v1" as const;
export const RUNTIME_EVENT_CONTRACT_VERSION = "phase4-runtime-event/v1" as const;
export const RUNTIME_PAYLOAD_SCHEMA_VERSION = 1 as const;

export const RUNTIME_EVENT_TYPES_V1 = [
  "run.created", "run.started", "run.status_changed", "run.completed", "run.failed",
  "scheme.generation_started", "scheme.generated", "scheme.confirmed", "plan.generated",
  "task.created", "task.ready", "task.started", "task.progress",
  "task.waiting_for_capability", "task.resumed", "task.self_correcting",
  "task.correction_resolved", "task.completed", "task.failed",
  "replan.requested", "replan.approved", "replan.rejected",
  "graph.task_added", "graph.edge_added", "graph.edge_removed", "graph.version_changed",
  "evidence.accepted", "evidence.conflict", "calculation.started", "calculation.completed",
  "capability.gap_detected", "capability.build_requested", "capability.build_started",
  "capability.generated", "capability.static_validated", "capability.sandbox_started",
  "capability.test_passed", "capability.test_failed", "capability.financial_validated",
  "capability.approved", "capability.registered", "capability.build_failed",
  "workspace.created", "capability.generation_started", "capability.tested",
  "capability.validated", "review.started", "review.required", "review.resolved",
  "proof.started", "proof.required", "proof.generated", "proof.verified", "proof.failed",
  "release.completed"
] as const;

export type RuntimeEventTypeV1 = typeof RUNTIME_EVENT_TYPES_V1[number];

export const UNSUPPORTED_RUNTIME_EVENT_TYPES_V1 = [
  "scheme.generation_started",
  "replan.rejected",
  "evidence.conflict",
  "workspace.created",
  "capability.generation_started",
  "capability.tested",
  "capability.validated",
  "review.required"
] as const satisfies readonly RuntimeEventTypeV1[];

export type UnsupportedRuntimeEventTypeV1 = typeof UNSUPPORTED_RUNTIME_EVENT_TYPES_V1[number];
export type SupportedRuntimeEventTypeV1 = Exclude<RuntimeEventTypeV1, UnsupportedRuntimeEventTypeV1>;

const UNSUPPORTED_EVENT_SET = new Set<RuntimeEventTypeV1>(UNSUPPORTED_RUNTIME_EVENT_TYPES_V1);
export const SUPPORTED_RUNTIME_EVENT_TYPES_V1 = Object.freeze(
  RUNTIME_EVENT_TYPES_V1.filter(
    (eventType): eventType is SupportedRuntimeEventTypeV1 => !UNSUPPORTED_EVENT_SET.has(eventType)
  )
);

export type RuntimeEventEffectV1 =
  | "PATCH_PROJECTION"
  | "REFRESH_PROJECTION"
  | "OBSERVATION_ONLY"
  | "TERMINAL";

export const RUNTIME_EVENT_EFFECT_BY_TYPE_V1 = Object.freeze({
  "run.started": "PATCH_PROJECTION",
  "run.status_changed": "PATCH_PROJECTION",
  "task.ready": "PATCH_PROJECTION",
  "task.started": "PATCH_PROJECTION",
  "task.progress": "PATCH_PROJECTION",
  "task.waiting_for_capability": "PATCH_PROJECTION",
  "task.resumed": "PATCH_PROJECTION",
  "task.self_correcting": "PATCH_PROJECTION",
  "task.completed": "PATCH_PROJECTION",
  "task.failed": "PATCH_PROJECTION",

  "run.created": "REFRESH_PROJECTION",
  "scheme.generated": "REFRESH_PROJECTION",
  "scheme.confirmed": "REFRESH_PROJECTION",
  "plan.generated": "REFRESH_PROJECTION",
  "task.created": "REFRESH_PROJECTION",
  "task.correction_resolved": "REFRESH_PROJECTION",
  "replan.requested": "REFRESH_PROJECTION",
  "replan.approved": "REFRESH_PROJECTION",
  "graph.task_added": "REFRESH_PROJECTION",
  "graph.edge_added": "REFRESH_PROJECTION",
  "graph.edge_removed": "REFRESH_PROJECTION",
  "graph.version_changed": "REFRESH_PROJECTION",
  "review.started": "REFRESH_PROJECTION",
  "review.resolved": "REFRESH_PROJECTION",
  "proof.required": "REFRESH_PROJECTION",
  "proof.started": "REFRESH_PROJECTION",
  "proof.generated": "REFRESH_PROJECTION",
  "proof.verified": "REFRESH_PROJECTION",
  "proof.failed": "REFRESH_PROJECTION",
  "release.completed": "REFRESH_PROJECTION",

  "evidence.accepted": "OBSERVATION_ONLY",
  "calculation.started": "OBSERVATION_ONLY",
  "calculation.completed": "OBSERVATION_ONLY",
  "capability.gap_detected": "OBSERVATION_ONLY",
  "capability.build_requested": "OBSERVATION_ONLY",
  "capability.build_started": "OBSERVATION_ONLY",
  "capability.generated": "OBSERVATION_ONLY",
  "capability.static_validated": "OBSERVATION_ONLY",
  "capability.sandbox_started": "OBSERVATION_ONLY",
  "capability.test_passed": "OBSERVATION_ONLY",
  "capability.test_failed": "OBSERVATION_ONLY",
  "capability.financial_validated": "OBSERVATION_ONLY",
  "capability.approved": "OBSERVATION_ONLY",
  "capability.registered": "OBSERVATION_ONLY",
  "capability.build_failed": "OBSERVATION_ONLY",

  "run.completed": "TERMINAL",
  "run.failed": "TERMINAL"
} satisfies Readonly<Record<SupportedRuntimeEventTypeV1, RuntimeEventEffectV1>>);

export type RuntimeIngestionFailureReason =
  | "MALFORMED_EVENT"
  | "UNSUPPORTED_EVENT"
  | "SCHEMA_INCOMPATIBLE"
  | "WRONG_RUN"
  | "WRONG_TASK"
  | "WIRE_ID_MISMATCH"
  | "WIRE_TYPE_MISMATCH"
  | "SEQUENCE_GAP"
  | "SEQUENCE_CONFLICT"
  | "STALE_EVENT"
  | "EVENT_ID_CONFLICT"
  | "EVENT_AFTER_TERMINAL"
  | "PROJECTION_REJECTED";

export interface SafeRuntimeEventIdentity {
  readonly eventId?: string;
  readonly runId?: string;
  readonly taskId?: string | null;
  readonly type?: string;
  readonly sequence?: number;
}

export class RuntimeIngestionError extends Error {
  readonly reason: RuntimeIngestionFailureReason;
  readonly identity: SafeRuntimeEventIdentity;

  constructor(
    reason: RuntimeIngestionFailureReason,
    message: string,
    identity: SafeRuntimeEventIdentity = {}
  ) {
    super(message);
    this.name = "RuntimeIngestionError";
    this.reason = reason;
    // Callers sometimes pass a validated event, which is structurally compatible
    // with SafeRuntimeEventIdentity but also carries a payload. Project the five
    // diagnostic fields explicitly so error/quarantine paths can never retain the
    // event body, even when a future payload producer misclassifies sensitive text.
    this.identity = Object.freeze({
      ...(typeof identity.eventId === "string" ? { eventId: identity.eventId } : {}),
      ...(typeof identity.runId === "string" ? { runId: identity.runId } : {}),
      ...(typeof identity.taskId === "string" || identity.taskId === null
        ? { taskId: identity.taskId }
        : {}),
      ...(typeof identity.type === "string" ? { type: identity.type } : {}),
      ...(typeof identity.sequence === "number" && Number.isSafeInteger(identity.sequence)
        ? { sequence: identity.sequence }
        : {})
    });
  }
}

export interface DecodeRuntimeEventContext {
  readonly expectedRunId: string;
  readonly authoritativeTaskIds: ReadonlySet<string> | readonly string[];
  readonly frameId?: string;
  readonly frameType?: string;
}

type UnknownRecord = Record<string, unknown>;
type Predicate = (value: unknown) => boolean;

const TOP_LEVEL_FIELDS = new Set([
  "event_contract_version",
  "event_id",
  "run_id",
  "task_id",
  "type",
  "timestamp",
  "sequence",
  "payload_schema_version",
  "payload",
  "graph_version",
  "effect",
  "projection_refresh_required"
]);

export const GRAPH_VERSION_RUNTIME_EVENT_TYPES_V1 = [
  "run.started",
  "graph.task_added",
  "graph.edge_added",
  "graph.edge_removed",
  "graph.version_changed"
] as const satisfies readonly SupportedRuntimeEventTypeV1[];
const GRAPH_VERSION_TYPES = new Set<SupportedRuntimeEventTypeV1>(
  GRAPH_VERSION_RUNTIME_EVENT_TYPES_V1
);

export const TASK_ID_REQUIRED_RUNTIME_EVENT_TYPES_V1 = [
  "task.created", "task.ready", "task.started", "task.progress",
  "task.waiting_for_capability", "task.resumed", "task.self_correcting",
  "task.correction_resolved", "task.completed", "task.failed",
  "replan.requested", "replan.approved", "graph.task_added", "graph.edge_added",
  "graph.edge_removed", "calculation.started", "calculation.completed",
  "capability.gap_detected", "capability.build_requested", "capability.build_started",
  "capability.generated", "capability.static_validated", "capability.sandbox_started",
  "capability.test_passed", "capability.test_failed", "capability.financial_validated",
  "capability.approved", "capability.registered", "capability.build_failed"
] as const satisfies readonly SupportedRuntimeEventTypeV1[];
const TASK_ID_REQUIRED_TYPES = new Set<SupportedRuntimeEventTypeV1>(
  TASK_ID_REQUIRED_RUNTIME_EVENT_TYPES_V1
);

const NEW_TASK_REFERENCE_TYPES = new Set<SupportedRuntimeEventTypeV1>([
  "task.created",
  "graph.task_added"
]);

const RUN_STATUSES = new Set([
  "DRAFT", "SCHEME_GENERATING", "AWAITING_CONFIRMATION", "PLANNING", "RUNNING",
  "REVIEW", "PROVING", "RELEASED", "FAILED", "CANCELLED"
]);
const NONTERMINAL_RUN_STATUSES = new Set(
  [...RUN_STATUSES].filter((status) => !["RELEASED", "FAILED", "CANCELLED"].includes(status))
);
const FAILURE_STAGES = new Set([
  "PLANNING", "DATA_EVIDENCE", "TASK_EXECUTION", "GENERATED_CAPABILITY",
  "FINANCIAL_REVIEW", "PROOF", "ARTIFACT_GENERATION", "RELEASE",
  "POST_SCHEDULER", "PERSISTENCE", "CANCELLATION"
]);
const TASK_FAILURE_STATUSES = new Set(["FAILED", "CAPABILITY_BUILD_FAILED", "CANCELLED"]);
const REVIEW_STATUSES = new Set(["PASS", "REVIEW", "BLOCK"]);
const REPLAN_DECISIONS = new Set(["PENDING", "APPROVED", "REJECTED"]);
const CAPABILITY_SCOPES = new Set(["TASK", "RUN"]);
const PROOF_FAILURE_STATUSES = new Set([
  "INVALID", "FAILED", "ERROR", "UNSUPPORTED", "NOT_IMPLEMENTED"
]);

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isSafeString = (value: unknown): value is string =>
  typeof value === "string"
  && value.length > 0
  && value.length <= 4096
  && value.trim() === value
  && !/[\u0000-\u001f]/u.test(value);

const isNullableSafeString = (value: unknown) => value === null || isSafeString(value);
const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";
const isIntegerAtLeast = (minimum: number): Predicate => (value) =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= minimum;
const isPositiveInteger = isIntegerAtLeast(1);
const isNonnegativeInteger = isIntegerAtLeast(0);
const isRatio = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
const isOneOf = (values: ReadonlySet<string>): Predicate => (value) =>
  typeof value === "string" && values.has(value);
const isLiteral = (expected: string | number | boolean): Predicate => (value) => value === expected;
const isUtcTimestamp = (value: unknown): value is string => {
  if (typeof value !== "string") return false;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$/u.test(value)) return false;
  return Number.isFinite(Date.parse(value));
};

interface PayloadSpec {
  readonly required: Readonly<Record<string, Predicate>>;
  readonly optional?: Readonly<Record<string, Predicate>>;
}

const spec = (
  required: Readonly<Record<string, Predicate>>,
  optional: Readonly<Record<string, Predicate>> = {}
): PayloadSpec => ({ required, optional });

const EMPTY_PAYLOAD_TYPES = new Set<SupportedRuntimeEventTypeV1>([
  "run.started", "task.ready", "review.started"
]);

const PAYLOAD_SPECS = Object.freeze({
  "run.created": spec({ object_id: isSafeString }),
  "run.status_changed": spec({ status: isOneOf(NONTERMINAL_RUN_STATUSES) }),
  "run.completed": spec({ status: isLiteral("RELEASED") }),
  "run.failed": spec(
    { status: isOneOf(new Set(["FAILED", "CANCELLED"])), failure_stage: isOneOf(FAILURE_STAGES), failure_code: isSafeString },
    { safe_message: isNullableSafeString }
  ),
  "scheme.generated": spec({
    scheme_id: isSafeString,
    generated_by: isSafeString,
    generated_at: isUtcTimestamp,
    generation_stage: isSafeString,
    retrospective: isBoolean
  }),
  "scheme.confirmed": spec({ scheme_id: isSafeString }),
  "plan.generated": spec({ graph_id: isSafeString, task_count: isNonnegativeInteger }),
  "task.created": spec({ task_type: isSafeString }),
  "task.started": spec({ attempt: isPositiveInteger }),
  "task.waiting_for_capability": spec({ gap_id: isSafeString }),
  "task.resumed": spec({ gap_id: isSafeString, registration_id: isSafeString, status: isLiteral("RUNNING") }),
  "task.self_correcting": spec({ problem_code: isSafeString }),
  "task.correction_resolved": spec({ correction_id: isSafeString }),
  "task.completed": spec({ attempt: isPositiveInteger }, { result_ref: isNullableSafeString }),
  "task.failed": spec(
    { attempt: isPositiveInteger, failure_code: isSafeString },
    { status: isOneOf(TASK_FAILURE_STATUSES), retry_suppressed: isBoolean }
  ),
  "replan.requested": spec({ replan_id: isSafeString, decision: isOneOf(REPLAN_DECISIONS) }),
  "replan.approved": spec({ replan_id: isSafeString, decided_by: isSafeString }),
  "graph.task_added": spec({ replan_id: isSafeString }),
  "graph.edge_added": spec({ replan_id: isSafeString, source_task_id: isSafeString, target_task_id: isSafeString }),
  "graph.edge_removed": spec({ replan_id: isSafeString, source_task_id: isSafeString, target_task_id: isSafeString }),
  "graph.version_changed": spec({ replan_id: isSafeString, version_before: isPositiveInteger }),
  "evidence.accepted": spec(
    { evidence_id: isSafeString, field: isSafeString },
    { producer_task_id: isSafeString, source_endpoint: isSafeString, evidence_purpose: isSafeString, evidence_category: isSafeString }
  ),
  "calculation.started": spec({ capability_id: isSafeString }),
  "calculation.completed": spec({ calculation_id: isSafeString }, { capability_id: isSafeString }),
  "capability.gap_detected": spec({ gap_id: isSafeString, capability_id: isSafeString, skill_id: isSafeString, requested_by: isSafeString }),
  "capability.build_requested": spec({ gap_id: isSafeString, build_id: isSafeString, attempt: isPositiveInteger, max_attempts: isPositiveInteger, approved_by: isSafeString }),
  "capability.build_started": spec({ build_id: isSafeString, attempt: isPositiveInteger }),
  "capability.generated": spec({ build_id: isSafeString, generated_capability_id: isSafeString, implementation_hash: isSafeString }),
  "capability.static_validated": spec({ build_id: isSafeString, implementation_hash: isSafeString }),
  "capability.sandbox_started": spec({ build_id: isSafeString, implementation_hash: isSafeString }),
  "capability.test_passed": spec({ build_id: isSafeString, implementation_hash: isSafeString }),
  "capability.test_failed": spec({ build_id: isSafeString, attempt: isPositiveInteger, failure_code: isSafeString }),
  "capability.financial_validated": spec({ build_id: isSafeString, implementation_hash: isSafeString }),
  "capability.approved": spec({ build_id: isSafeString, registration_id: isSafeString, approved_by: isSafeString, scope: isOneOf(CAPABILITY_SCOPES) }),
  "capability.registered": spec({ registration_id: isSafeString, capability_id: isSafeString, capability_version: isSafeString, scope: isOneOf(CAPABILITY_SCOPES) }),
  "capability.build_failed": spec(
    { failure_code: isSafeString, terminal: isBoolean },
    { gap_id: isSafeString, build_id: isSafeString, attempt: isPositiveInteger, max_attempts: isPositiveInteger }
  ),
  "review.resolved": spec({ review_id: isSafeString, status: isOneOf(REVIEW_STATUSES) }),
  "proof.required": spec({ proof_id: isSafeString, calculation_id: isSafeString, formula_id: isSafeString, policy_id: isSafeString }),
  "proof.started": spec({ proof_id: isSafeString, backend: isSafeString }),
  "proof.generated": spec({ proof_id: isSafeString, backend: isSafeString }),
  "proof.verified": spec({ proof_id: isSafeString, image_id: isSafeString, receipt_hash: isSafeString, journal_hash: isSafeString, verified: isLiteral(true), dev_mode: isBoolean }),
  "proof.failed": spec({ proof_id: isSafeString, failure_code: isSafeString, status: isOneOf(PROOF_FAILURE_STATUSES) }),
  "release.completed": spec({ canonical_record_id: isSafeString, result_id: isSafeString })
} satisfies Readonly<Record<Exclude<SupportedRuntimeEventTypeV1, "run.started" | "task.ready" | "task.progress" | "review.started">, PayloadSpec>>);

function eventIdentity(record: UnknownRecord): SafeRuntimeEventIdentity {
  return {
    eventId: typeof record.event_id === "string" ? record.event_id : undefined,
    runId: typeof record.run_id === "string" ? record.run_id : undefined,
    taskId: typeof record.task_id === "string" || record.task_id === null ? record.task_id : undefined,
    type: typeof record.type === "string" ? record.type : undefined,
    sequence: typeof record.sequence === "number" && Number.isSafeInteger(record.sequence)
      ? record.sequence
      : undefined
  };
}

function malformed(message: string, identity: SafeRuntimeEventIdentity = {}): never {
  throw new RuntimeIngestionError("MALFORMED_EVENT", message, identity);
}

function assertExactFields(
  eventType: SupportedRuntimeEventTypeV1,
  payload: UnknownRecord,
  payloadSpec: PayloadSpec,
  identity: SafeRuntimeEventIdentity
) {
  const optional = payloadSpec.optional ?? {};
  const allowed = new Set([...Object.keys(payloadSpec.required), ...Object.keys(optional)]);
  const missing = Object.keys(payloadSpec.required).filter((field) => !(field in payload));
  const unknown = Object.keys(payload).filter((field) => !allowed.has(field));
  if (missing.length > 0) malformed(`${eventType} payload is missing required fields`, identity);
  if (unknown.length > 0) malformed(`${eventType} payload contains unsupported fields`, identity);
  for (const [field, predicate] of Object.entries({ ...payloadSpec.required, ...optional })) {
    if (field in payload && !predicate(payload[field])) {
      malformed(`${eventType} payload field ${field} is invalid`, identity);
    }
  }
  if (
    (eventType === "capability.build_requested" || eventType === "capability.build_failed")
    && typeof payload.attempt === "number"
    && typeof payload.max_attempts === "number"
    && payload.attempt > payload.max_attempts
  ) {
    malformed(`${eventType} attempt exceeds max_attempts`, identity);
  }
}

function validateTaskProgress(payload: UnknownRecord, identity: SafeRuntimeEventIdentity) {
  const keys = new Set(Object.keys(payload));
  const progressAllowed = new Set(["progress", "progress_scale", "stage", "message_code"]);
  const progressForm = keys.has("progress")
    && keys.has("progress_scale")
    && [...keys].every((key) => progressAllowed.has(key));
  if (progressForm) {
    if (!isRatio(payload.progress) || payload.progress_scale !== "RATIO_0_1") {
      malformed("task.progress PROGRESS payload is invalid", identity);
    }
    if ("stage" in payload && !isSafeString(payload.stage)) malformed("task.progress stage is invalid", identity);
    if ("message_code" in payload && !isSafeString(payload.message_code)) malformed("task.progress message_code is invalid", identity);
    return;
  }
  if (keys.size === 2 && keys.has("attempt") && keys.has("error_code")) {
    if (!isPositiveInteger(payload.attempt) || !isSafeString(payload.error_code)) {
      malformed("task.progress RETRY_SCHEDULED payload is invalid", identity);
    }
    return;
  }
  malformed("task.progress payload is not a frozen PROGRESS or RETRY_SCHEDULED form", identity);
}

function validatePayload(
  eventType: SupportedRuntimeEventTypeV1,
  payload: UnknownRecord,
  identity: SafeRuntimeEventIdentity
) {
  if (eventType === "task.progress") {
    validateTaskProgress(payload, identity);
    return;
  }
  if (EMPTY_PAYLOAD_TYPES.has(eventType)) {
    if (Object.keys(payload).length > 0) malformed(`${eventType} payload must be empty`, identity);
    return;
  }
  const payloadSpec = (PAYLOAD_SPECS as Partial<
    Readonly<Record<SupportedRuntimeEventTypeV1, PayloadSpec>>
  >)[eventType];
  if (payloadSpec === undefined) malformed(`${eventType} has no frozen payload schema`, identity);
  assertExactFields(eventType, payload, payloadSpec, identity);
}

function camelCaseKey(value: string) {
  return value.replace(/_([a-z])/gu, (_match, letter: string) => letter.toUpperCase());
}

function normalizedPayload(payload: UnknownRecord): Readonly<Record<string, unknown>> {
  const normalized: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) normalized[camelCaseKey(key)] = value;
  return Object.freeze(normalized);
}

function isRuntimeEventType(value: unknown): value is RuntimeEventTypeV1 {
  return typeof value === "string" && (RUNTIME_EVENT_TYPES_V1 as readonly string[]).includes(value);
}

function isEffect(value: unknown): value is RuntimeEventEffectV1 {
  return value === "PATCH_PROJECTION"
    || value === "REFRESH_PROJECTION"
    || value === "OBSERVATION_ONLY"
    || value === "TERMINAL";
}

/**
 * Decode one complete public SSE data object. It accepts unknown input, validates
 * the closed V1 envelope/payload, and returns only the safe camelCase consumer DTO.
 */
export function decodeRuntimeEventV1(
  input: unknown,
  context: DecodeRuntimeEventContext
): NormalizedRuntimeEventV1 {
  if (!isSafeString(context.expectedRunId)) {
    throw new RuntimeIngestionError("WRONG_RUN", "An exact non-empty Run identity is required");
  }
  if (!isRecord(input)) malformed("Runtime event must be an object");
  const identity = eventIdentity(input);
  const unknownTopLevel = Object.keys(input).filter((field) => !TOP_LEVEL_FIELDS.has(field));
  const missingTopLevel = [...TOP_LEVEL_FIELDS].filter((field) => !(field in input));
  if (missingTopLevel.length > 0) malformed("Runtime event is missing frozen envelope fields", identity);
  if (unknownTopLevel.length > 0) malformed("Runtime event contains unsupported envelope fields", identity);
  if (input.event_contract_version !== RUNTIME_EVENT_CONTRACT_VERSION) {
    throw new RuntimeIngestionError("UNSUPPORTED_EVENT", "Unsupported in-stream runtime event contract version", identity);
  }
  if (input.payload_schema_version !== RUNTIME_PAYLOAD_SCHEMA_VERSION) {
    throw new RuntimeIngestionError("UNSUPPORTED_EVENT", "Unsupported in-stream runtime payload schema version", identity);
  }
  if (!isSafeString(input.event_id)) malformed("Runtime event_id is invalid", identity);
  if (!isSafeString(input.run_id)) malformed("Runtime run_id is invalid", identity);
  if (input.run_id !== context.expectedRunId) {
    throw new RuntimeIngestionError("WRONG_RUN", "Runtime event belongs to a different Run", identity);
  }
  if (input.task_id !== null && !isSafeString(input.task_id)) malformed("Runtime task_id is invalid", identity);
  if (!isRuntimeEventType(input.type)) {
    throw new RuntimeIngestionError("UNSUPPORTED_EVENT", "Unknown runtime event type", identity);
  }
  if (UNSUPPORTED_EVENT_SET.has(input.type)) {
    throw new RuntimeIngestionError("UNSUPPORTED_EVENT", "Runtime event type is unsupported in V1", identity);
  }
  const eventType = input.type as SupportedRuntimeEventTypeV1;
  if (!isUtcTimestamp(input.timestamp)) malformed("Runtime timestamp must be an RFC 3339 UTC instant", identity);
  if (!isPositiveInteger(input.sequence)) malformed("Runtime sequence must be a positive safe integer", identity);
  if (!isRecord(input.payload)) malformed("Runtime payload must be an object", identity);
  if (!isEffect(input.effect) || input.effect !== RUNTIME_EVENT_EFFECT_BY_TYPE_V1[eventType]) {
    malformed("Runtime effect conflicts with the frozen event disposition", identity);
  }
  const expectedRefresh = input.effect === "REFRESH_PROJECTION" || input.effect === "TERMINAL";
  if (input.projection_refresh_required !== expectedRefresh) {
    malformed("projection_refresh_required conflicts with runtime effect", identity);
  }
  const requiresGraphVersion = GRAPH_VERSION_TYPES.has(eventType);
  if (requiresGraphVersion) {
    if (!isPositiveInteger(input.graph_version)) malformed(`${eventType} requires graph_version`, identity);
  } else if (input.graph_version !== null) {
    malformed(`${eventType} requires null graph_version`, identity);
  }

  const authoritativeTaskIds = context.authoritativeTaskIds instanceof Set
    ? context.authoritativeTaskIds
    : new Set(context.authoritativeTaskIds);
  if (TASK_ID_REQUIRED_TYPES.has(eventType) && input.task_id === null) {
    throw new RuntimeIngestionError("WRONG_TASK", `${eventType} requires an exact Task identity`, identity);
  }
  if (
    input.task_id !== null
    && !authoritativeTaskIds.has(input.task_id)
    && !NEW_TASK_REFERENCE_TYPES.has(eventType)
  ) {
    throw new RuntimeIngestionError("WRONG_TASK", "Runtime event Task is absent from the exact Run snapshot", identity);
  }
  if (context.frameId !== undefined && context.frameId !== String(input.sequence)) {
    throw new RuntimeIngestionError("WIRE_ID_MISMATCH", "SSE id does not equal data.sequence", identity);
  }
  if (context.frameType !== undefined && context.frameType !== eventType) {
    throw new RuntimeIngestionError("WIRE_TYPE_MISMATCH", "SSE event does not equal data.type", identity);
  }

  validatePayload(eventType, input.payload, identity);
  if (eventType === "graph.edge_added" || eventType === "graph.edge_removed") {
    for (const field of ["source_task_id", "target_task_id"] as const) {
      const referencedTaskId = input.payload[field];
      if (typeof referencedTaskId !== "string" || !authoritativeTaskIds.has(referencedTaskId)) {
        throw new RuntimeIngestionError(
          "WRONG_TASK",
          `${eventType} ${field} is absent from the exact Run snapshot`,
          identity
        );
      }
    }
  }
  if (
    eventType === "evidence.accepted"
    && "producer_task_id" in input.payload
    && !authoritativeTaskIds.has(input.payload.producer_task_id as string)
  ) {
    throw new RuntimeIngestionError(
      "WRONG_TASK",
      "evidence.accepted producer_task_id is absent from the exact Run snapshot",
      identity
    );
  }
  const event = {
    eventContractVersion: RUNTIME_EVENT_CONTRACT_VERSION,
    eventId: input.event_id,
    runId: input.run_id,
    taskId: input.task_id,
    type: eventType,
    timestamp: input.timestamp,
    sequence: input.sequence,
    payloadSchemaVersion: RUNTIME_PAYLOAD_SCHEMA_VERSION,
    payload: normalizedPayload(input.payload),
    graphVersion: input.graph_version,
    effect: input.effect,
    projectionRefreshRequired: input.projection_refresh_required
  };
  return Object.freeze(event) as NormalizedRuntimeEventV1;
}

function canonicalize(value: unknown): string {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("Cannot fingerprint a non-finite number");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(",")}]`;
  if (isRecord(value)) {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`).join(",")}}`;
  }
  throw new TypeError("Cannot fingerprint a non-JSON runtime event value");
}

const SHA256_ROUND_CONSTANTS = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
]);

function rotateRight(value: number, shift: number) {
  return (value >>> shift) | (value << (32 - shift));
}

function sha256(value: string) {
  const input = new TextEncoder().encode(value);
  const paddedLength = Math.ceil((input.length + 9) / 64) * 64;
  const bytes = new Uint8Array(paddedLength);
  bytes.set(input);
  bytes[input.length] = 0x80;
  const bitLength = input.length * 8;
  for (let index = 0; index < 8; index += 1) {
    bytes[paddedLength - 1 - index] = Math.floor(bitLength / (2 ** (index * 8))) & 0xff;
  }

  const digest = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
  ]);
  const words = new Uint32Array(64);
  for (let offset = 0; offset < bytes.length; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      const wordOffset = offset + (index * 4);
      words[index] = (
        (bytes[wordOffset] << 24)
        | (bytes[wordOffset + 1] << 16)
        | (bytes[wordOffset + 2] << 8)
        | bytes[wordOffset + 3]
      ) >>> 0;
    }
    for (let index = 16; index < 64; index += 1) {
      const previous15 = words[index - 15];
      const previous2 = words[index - 2];
      const sigma0 = rotateRight(previous15, 7) ^ rotateRight(previous15, 18) ^ (previous15 >>> 3);
      const sigma1 = rotateRight(previous2, 17) ^ rotateRight(previous2, 19) ^ (previous2 >>> 10);
      words[index] = (words[index - 16] + sigma0 + words[index - 7] + sigma1) >>> 0;
    }

    let [a, b, c, d, e, f, g, h] = digest;
    for (let index = 0; index < 64; index += 1) {
      const sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choose = (e & f) ^ (~e & g);
      const temporary1 = (h + sum1 + choose + SHA256_ROUND_CONSTANTS[index] + words[index]) >>> 0;
      const sum0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temporary2 = (sum0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temporary1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temporary1 + temporary2) >>> 0;
    }
    digest[0] = (digest[0] + a) >>> 0;
    digest[1] = (digest[1] + b) >>> 0;
    digest[2] = (digest[2] + c) >>> 0;
    digest[3] = (digest[3] + d) >>> 0;
    digest[4] = (digest[4] + e) >>> 0;
    digest[5] = (digest[5] + f) >>> 0;
    digest[6] = (digest[6] + g) >>> 0;
    digest[7] = (digest[7] + h) >>> 0;
  }
  return [...digest].map((word) => word.toString(16).padStart(8, "0")).join("");
}

/** Deterministic, bounded and non-payload-bearing digest over a decoded safe event. */
export function runtimeEventFingerprintV1(event: NormalizedRuntimeEventV1): string {
  return `sha256:${sha256(canonicalize(event))}`;
}

export type RuntimeEventIngestionResult =
  | { readonly kind: "APPLIED"; readonly event: NormalizedRuntimeEventV1; readonly lastSequence: number }
  | { readonly kind: "DUPLICATE"; readonly event: NormalizedRuntimeEventV1; readonly lastSequence: number };

export interface RuntimeEventIngestionGuardOptions {
  readonly runId: string;
  readonly initialSequence: number;
  readonly authoritativeTaskIds: ReadonlySet<string> | readonly string[];
  readonly acceptedEvents?: readonly NormalizedRuntimeEventV1[];
}

/** Stateful exact-Run sequence, event-id and canonical-content admission guard. */
export class RuntimeEventIngestionGuard {
  readonly runId: string;
  private readonly authoritativeTaskIds: ReadonlySet<string>;
  private readonly fingerprintBySequence = new Map<number, string>();
  private readonly sequenceByEventId = new Map<string, number>();
  private terminalSequence: number | null = null;
  private committedSequence: number;

  constructor(options: RuntimeEventIngestionGuardOptions) {
    if (!isSafeString(options.runId)) {
      throw new RuntimeIngestionError("WRONG_RUN", "An exact non-empty Run identity is required");
    }
    if (!isNonnegativeInteger(options.initialSequence)) {
      throw new RuntimeIngestionError("MALFORMED_EVENT", "Initial sequence must be a nonnegative safe integer");
    }
    this.runId = options.runId;
    this.committedSequence = options.initialSequence;
    this.authoritativeTaskIds = new Set(options.authoritativeTaskIds);
    for (const event of options.acceptedEvents ?? []) this.seedAcceptedEvent(event);
  }

  get lastSequence() {
    return this.committedSequence;
  }

  ingest(
    input: unknown,
    frame: { readonly id?: string; readonly event?: string } = {},
    applyBeforeCommit?: (event: NormalizedRuntimeEventV1) => void
  ): RuntimeEventIngestionResult {
    const event = decodeRuntimeEventV1(input, {
      expectedRunId: this.runId,
      authoritativeTaskIds: this.authoritativeTaskIds,
      frameId: frame.id,
      frameType: frame.event
    });
    const fingerprint = runtimeEventFingerprintV1(event);
    const existingFingerprint = this.fingerprintBySequence.get(event.sequence);
    const existingSequence = this.sequenceByEventId.get(event.eventId);

    if (this.terminalSequence !== null && event.sequence > this.terminalSequence) {
      throw new RuntimeIngestionError(
        "EVENT_AFTER_TERMINAL",
        "A business event followed the terminal event",
        event
      );
    }
    if (existingFingerprint !== undefined || existingSequence !== undefined) {
      if (
        existingFingerprint === fingerprint
        && existingSequence === event.sequence
        && event.sequence <= this.committedSequence
      ) {
        return { kind: "DUPLICATE", event, lastSequence: this.committedSequence };
      }
      const reason = existingSequence !== undefined && existingSequence !== event.sequence
        ? "EVENT_ID_CONFLICT"
        : "SEQUENCE_CONFLICT";
      throw new RuntimeIngestionError(reason, "Runtime event identity conflicts with accepted history", event);
    }
    if (event.sequence <= this.committedSequence) {
      throw new RuntimeIngestionError("STALE_EVENT", "Unseen stale runtime event cannot be applied", event);
    }
    if (event.sequence !== this.committedSequence + 1) {
      throw new RuntimeIngestionError("SEQUENCE_GAP", "Runtime event sequence is not the next suffix item", event);
    }

    try {
      applyBeforeCommit?.(event);
    } catch {
      throw new RuntimeIngestionError(
        "PROJECTION_REJECTED",
        "The projection consumer rejected the runtime event",
        event
      );
    }
    this.fingerprintBySequence.set(event.sequence, fingerprint);
    this.sequenceByEventId.set(event.eventId, event.sequence);
    this.committedSequence = event.sequence;
    if (event.effect === "TERMINAL") this.terminalSequence = event.sequence;
    return { kind: "APPLIED", event, lastSequence: this.committedSequence };
  }

  private seedAcceptedEvent(event: NormalizedRuntimeEventV1) {
    if (event.runId !== this.runId || event.sequence > this.committedSequence) {
      throw new RuntimeIngestionError(
        event.runId === this.runId ? "SEQUENCE_GAP" : "WRONG_RUN",
        "Accepted event history does not belong to the committed cursor",
        event
      );
    }
    const fingerprint = runtimeEventFingerprintV1(event);
    const priorFingerprint = this.fingerprintBySequence.get(event.sequence);
    const priorSequence = this.sequenceByEventId.get(event.eventId);
    if (
      (priorFingerprint !== undefined && priorFingerprint !== fingerprint)
      || (priorSequence !== undefined && priorSequence !== event.sequence)
    ) {
      throw new RuntimeIngestionError("SEQUENCE_CONFLICT", "Accepted event history conflicts", event);
    }
    this.fingerprintBySequence.set(event.sequence, fingerprint);
    this.sequenceByEventId.set(event.eventId, event.sequence);
    if (event.effect === "TERMINAL") this.terminalSequence = event.sequence;
  }
}

export interface RuntimeSubscription {
  readonly closed?: Promise<void>;
  unsubscribe(): void;
}

export interface RuntimeSubscriptionOptions {
  readonly initialSequence: number;
  /** Exact numeric sequence or an opaque event ID already bound to this Run/cursor. */
  readonly resumeCursor?: string;
  readonly authoritativeTaskIds: ReadonlySet<string> | readonly string[];
  readonly acceptedEvents?: readonly NormalizedRuntimeEventV1[];
  readonly signal?: AbortSignal;
  readonly attempt?: number;
  readonly onStateChange?: (state: ConnectionState) => void;
  readonly onHeartbeat?: (receivedAt: string) => void;
  readonly onDuplicate?: (event: NormalizedRuntimeEventV1) => void;
  readonly onTerminalAtCursor?: (terminalSequence: number) => void;
}

export interface RuntimeTransport {
  readonly kind: "sse";
  subscribe(
    runId: string,
    onEvent: (event: NormalizedRuntimeEventV1) => void,
    onError: ((error: Error) => void) | undefined,
    options: RuntimeSubscriptionOptions
  ): RuntimeSubscription;
}
