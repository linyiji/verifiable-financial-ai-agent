import {
  createPhase4Mutation,
  type Phase4ConfirmResearchRunInput,
  type Phase4Mutation,
  type Phase4PrepareResearchRunInput
} from "../data/FrontendDataSource";
import type {
  ConfirmRunResponseV1,
  ErrorEnvelope,
  NormalizedObjectIdentity,
  PreparedResearchDraft,
  Phase4RunStatus,
  Phase4TaskStatus,
  ResponseMetaV1,
  RunAdmissionV1,
  RunProjection,
  RunStatus,
  TaskStatus
} from "../types/domain";

export interface StatusMeta {
  readonly label: string;
  readonly color: "amber" | "blue" | "green" | "red";
}

export const PHASE4_RUN_STATUS_META: Readonly<Record<Phase4RunStatus, StatusMeta>> = {
  PREPARING: { label: "研究准备中", color: "blue" },
  AWAITING_CONFIRMATION: { label: "等待确认", color: "amber" },
  PLANNING: { label: "研究计划中", color: "blue" },
  RESEARCHING: { label: "研究中", color: "blue" },
  REVIEWING: { label: "质量复核中", color: "amber" },
  PROVING: { label: "证明验证中", color: "blue" },
  COMPLETED: { label: "已完成", color: "green" },
  FAILED: { label: "失败", color: "red" },
  CANCELLED: { label: "已取消", color: "amber" }
};

export const PHASE4_TASK_STATUS_LABELS: Readonly<Record<Phase4TaskStatus, string>> = {
  QUEUED: "等待中",
  READY: "可执行",
  ACTIVE: "执行中",
  WAITING_SUPPORT: "等待能力准备",
  CORRECTING: "自我修正中",
  BLOCKED: "已阻塞",
  REVIEW: "复核中",
  COMPLETE: "已完成",
  FAILED: "失败",
  CANCELLED: "已取消"
};

/** @deprecated Approved V8 baseline compatibility; never use at the Phase 4 HTTP boundary. */
export const RUN_STATUS_META: Readonly<Record<RunStatus, StatusMeta>> = {
  PLANNING: { label: "研究计划中", color: "blue" },
  RESEARCHING: { label: "研究中", color: "blue" },
  REVIEWING: { label: "质量复核中", color: "amber" },
  GENERATING_REPORT: { label: "报告生成中", color: "blue" },
  RESULT_PREPARING: { label: "结果发布准备中", color: "amber" },
  ACTION_REQUIRED: { label: "需要处理", color: "amber" },
  COMPLETED: { label: "已完成", color: "green" },
  FAILED: { label: "失败", color: "red" }
};

/** @deprecated Approved V8 baseline compatibility; never use at the Phase 4 HTTP boundary. */
export const TASK_STATUS_LABELS: Readonly<Record<TaskStatus, string>> = {
  WAITING: "等待中",
  READY: "可执行",
  RUNNING: "执行中",
  SELF_CORRECTING: "自我修正中",
  COMPLETED: "已完成",
  BLOCKED: "已阻塞",
  FAILED: "失败"
};

export type Phase4FlowStep =
  | "OBJECT"
  | "GOAL"
  | "SCHEME"
  | "CONFIRM"
  | "WORKSPACE";

export type Phase4RequestKind = "OBJECT" | "PREPARE" | "CONFIRM" | "WORKSPACE";

export type Phase4RequestPhase =
  | "IDLE"
  | "LOADING"
  | "READY"
  | "ERROR"
  | "QUARANTINED";

export type Phase4AutoStartState =
  | "NOT_REQUESTED"
  | "ADMITTING"
  | "ADMITTED"
  | "FAILED";

export type Phase4QuarantineReason =
  | "STALE_REQUEST_TOKEN"
  | "OBJECT_IDENTITY_MISMATCH"
  | "DRAFT_IDENTITY_MISMATCH"
  | "CONFIRM_IDENTITY_MISMATCH"
  | "REPLAY_ADMISSION_MISMATCH"
  | "RUN_IDENTITY_MISMATCH"
  | "STALE_RUN_PROJECTION"
  | "PROJECTION_IDENTITY_CONFLICT"
  | "CONTRACT_RESPONSE_REJECTED"
  | "ERROR_RESOURCE_IDENTITY_MISMATCH";

export interface Phase4LocalFailure {
  readonly kind: "LOCAL";
  readonly code: "NETWORK" | "ABORTED" | "PROTOCOL";
  /** Must be a caller-authored safe message; never a raw response body. */
  readonly message: string;
  readonly retryable: boolean;
  readonly recovery: "NONE" | "RETRY" | "SNAPSHOT_RELOAD";
}

export type Phase4RequestFailure = ErrorEnvelope | Phase4LocalFailure;

export const phase4LocalFailures = {
  network: (): Phase4LocalFailure => ({
    kind: "LOCAL",
    code: "NETWORK",
    message: "The request outcome is unknown because the network response was not admitted.",
    retryable: true,
    recovery: "RETRY"
  }),
  aborted: (): Phase4LocalFailure => ({
    kind: "LOCAL",
    code: "ABORTED",
    message: "The request was cancelled before its outcome was admitted.",
    retryable: true,
    recovery: "RETRY"
  }),
  protocol: (): Phase4LocalFailure => ({
    kind: "LOCAL",
    code: "PROTOCOL",
    message: "The response was rejected by the Phase 4 contract boundary.",
    retryable: false,
    recovery: "NONE"
  })
} as const;

export interface Phase4RequestState {
  readonly phase: Phase4RequestPhase;
  /** Correlates one UI-side network attempt. This is not an Idempotency-Key. */
  readonly requestToken: string | null;
  readonly error: Phase4RequestFailure | null;
}

export interface Phase4QuarantinedResponse {
  readonly source: Phase4RequestKind;
  readonly reason: Phase4QuarantineReason;
  readonly requestToken: string;
  readonly expectedRequestToken: string | null;
  readonly expectedObjectId: string | null;
  readonly receivedObjectId: string | null;
  readonly expectedResourceId: string | null;
  readonly receivedResourceId: string | null;
}

export type Phase4VisibleAlert =
  | {
      readonly kind: "ERROR";
      readonly source: Phase4RequestKind;
      readonly error: Phase4RequestFailure;
    }
  | {
      readonly kind: "QUARANTINE";
      readonly item: Phase4QuarantinedResponse;
    };

export interface Phase4ObjectContextState {
  readonly requestedObjectId: string | null;
  readonly selected: NormalizedObjectIdentity | null;
  readonly request: Phase4RequestState;
}

export interface Phase4GoalAuthoringState {
  /** Author input only. The Backend-authored normalized Goal arrives in the draft. */
  readonly text: string;
  readonly revision: number;
}

export interface Phase4PrepareExpectation {
  readonly objectId: string;
  readonly goalText: string;
  readonly goalRevision: number;
  readonly asOf: string;
  /** Present only for regeneration; the next draft must not reuse this identity. */
  readonly previousDraftId: string | null;
  /** Present only for regeneration; the next Scheme must be independently generated. */
  readonly previousSchemeId: string | null;
}

export interface Phase4PrepareState {
  readonly expected: Phase4PrepareExpectation | null;
  /**
   * Retained unchanged for an ambiguous retry. A retry changes only the
   * requestToken, never this mutation object, key, or body.
   */
  readonly mutation: Phase4Mutation<Phase4PrepareResearchRunInput> | null;
  readonly draft: PreparedResearchDraft | null;
  readonly request: Phase4RequestState;
}

export interface Phase4ConfirmExpectation {
  readonly objectId: string;
  readonly draftId: string;
  readonly draftVersion: number;
  readonly draftHash: string;
  readonly goalId: string;
  readonly schemeId: string;
}

export interface Phase4ConfirmState {
  readonly expected: Phase4ConfirmExpectation | null;
  /**
   * Retained unchanged for ambiguous retry. A retry changes only requestToken,
   * never the mutation object, key, or body.
   */
  readonly mutation: Phase4Mutation<Phase4ConfirmResearchRunInput> | null;
  readonly admission: RunAdmissionV1 | null;
  /** Per-response transport diagnostics; never part of immutable admission. */
  readonly responseMeta: ResponseMetaV1 | null;
  readonly autoStart: Phase4AutoStartState;
  readonly request: Phase4RequestState;
}

export interface Phase4WorkspaceState {
  /** Initial atomic snapshot only. C owns subsequent SSE/runtime reduction. */
  readonly snapshot: RunProjection | null;
  readonly stale: boolean;
  readonly request: Phase4RequestState;
}

export interface Phase4ProductState {
  readonly step: Phase4FlowStep;
  readonly object: Phase4ObjectContextState;
  readonly goal: Phase4GoalAuthoringState;
  readonly prepare: Phase4PrepareState;
  readonly confirm: Phase4ConfirmState;
  readonly workspace: Phase4WorkspaceState;
  readonly alert: Phase4VisibleAlert | null;
  readonly quarantine: readonly Phase4QuarantinedResponse[];
}

export type Phase4ProductAction =
  | { readonly type: "flow/reset" }
  | { readonly type: "object/loadStarted"; readonly requestToken: string; readonly objectId: string }
  | { readonly type: "object/loadSucceeded"; readonly requestToken: string; readonly object: NormalizedObjectIdentity }
  | { readonly type: "object/loadFailed"; readonly requestToken: string; readonly error: Phase4RequestFailure }
  | { readonly type: "object/selected"; readonly object: NormalizedObjectIdentity }
  | { readonly type: "goal/changed"; readonly text: string }
  | {
      readonly type: "prepare/started";
      readonly requestToken: string;
      readonly mutation: Phase4Mutation<Phase4PrepareResearchRunInput>;
    }
  | { readonly type: "prepare/succeeded"; readonly requestToken: string; readonly draft: PreparedResearchDraft }
  | { readonly type: "prepare/failed"; readonly requestToken: string; readonly error: Phase4RequestFailure }
  | { readonly type: "confirm/started"; readonly requestToken: string; readonly idempotencyKey: string }
  | { readonly type: "confirm/succeeded"; readonly requestToken: string; readonly response: ConfirmRunResponseV1 }
  | { readonly type: "confirm/failed"; readonly requestToken: string; readonly error: Phase4RequestFailure }
  | { readonly type: "workspace/loadStarted"; readonly requestToken: string }
  | { readonly type: "workspace/loadSucceeded"; readonly requestToken: string; readonly snapshot: RunProjection }
  | { readonly type: "workspace/loadFailed"; readonly requestToken: string; readonly error: Phase4RequestFailure }
  | { readonly type: "request/retryStarted"; readonly request: Phase4RequestKind; readonly requestToken: string }
  | { readonly type: "alert/dismissed" };

const idleRequest = (): Phase4RequestState => ({ phase: "IDLE", requestToken: null, error: null });
const loadingRequest = (requestToken: string): Phase4RequestState => ({ phase: "LOADING", requestToken, error: null });
const readyRequest = (requestToken: string | null): Phase4RequestState => ({ phase: "READY", requestToken, error: null });
const failedRequest = (requestToken: string, error: Phase4RequestFailure): Phase4RequestState => ({ phase: "ERROR", requestToken, error });
const quarantinedRequest = (requestToken: string): Phase4RequestState => ({ phase: "QUARANTINED", requestToken, error: null });

const emptyPrepare = (): Phase4PrepareState => ({
  expected: null,
  mutation: null,
  draft: null,
  request: idleRequest()
});
const emptyConfirm = (): Phase4ConfirmState => ({
  expected: null,
  mutation: null,
  admission: null,
  responseMeta: null,
  autoStart: "NOT_REQUESTED",
  request: idleRequest()
});
const emptyWorkspace = (): Phase4WorkspaceState => ({ snapshot: null, stale: false, request: idleRequest() });

export function createInitialPhase4ProductState(): Phase4ProductState {
  return {
    step: "OBJECT",
    object: { requestedObjectId: null, selected: null, request: idleRequest() },
    goal: { text: "", revision: 0 },
    prepare: emptyPrepare(),
    confirm: emptyConfirm(),
    workspace: emptyWorkspace(),
    alert: null,
    quarantine: []
  };
}

const hasValue = (value: string): boolean => value.trim().length > 0;
const currentToken = (request: Phase4RequestState): string | null => request.requestToken;
const hasFreshRequestToken = (request: Phase4RequestState, requestToken: string): boolean =>
  hasValue(requestToken) && request.requestToken !== requestToken;
const isCurrentLoadingRequest = (request: Phase4RequestState, requestToken: string): boolean =>
  request.phase === "LOADING" && request.requestToken === requestToken;

function withFreshObjectTarget(
  state: Phase4ProductState,
  objectId: string,
  request: Phase4RequestState
): Phase4ProductState {
  return {
    ...state,
    step: "OBJECT",
    object: { requestedObjectId: objectId, selected: null, request },
    goal: { text: "", revision: state.goal.revision + 1 },
    prepare: emptyPrepare(),
    confirm: emptyConfirm(),
    workspace: emptyWorkspace(),
    alert: null
  };
}

function quarantineResponse(
  state: Phase4ProductState,
  item: Phase4QuarantinedResponse,
  updateRequest?: (request: Phase4RequestState) => Phase4ProductState
): Phase4ProductState {
  const base = updateRequest ? updateRequest(quarantinedRequest(item.requestToken)) : state;
  return {
    ...base,
    alert: { kind: "QUARANTINE", item },
    quarantine: [...base.quarantine.slice(-31), item]
  };
}

function staleResponse(
  state: Phase4ProductState,
  source: Phase4RequestKind,
  requestToken: string,
  expectedRequestToken: string | null,
  expectedObjectId: string | null,
  receivedObjectId: string | null
): Phase4ProductState {
  return quarantineResponse(state, {
    source,
    reason: "STALE_REQUEST_TOKEN",
    requestToken,
    expectedRequestToken,
    expectedObjectId,
    receivedObjectId,
    expectedResourceId: null,
    receivedResourceId: null
  });
}

type Phase4ExpectedErrorResource = NonNullable<ErrorEnvelope["error"]["resource"]>;

function errorClosesTo(
  error: ErrorEnvelope,
  expectedResources: readonly Phase4ExpectedErrorResource[]
): boolean {
  const resource = error.error.resource;
  if (resource === null) return true;
  const requestOwned = expectedResources.filter((expected) => expected.type === resource.type);
  // resource.type is intentionally open for safe nested backend contexts such
  // as projection, graph, scheduler admission, and idempotency outcome. Only
  // a type that denotes an identity owned by this request can be ID-checked.
  return requestOwned.length === 0 || requestOwned.some(
    (expected) => expected.id === resource.id
  );
}

function objectErrorResources(objectId: string | null): readonly Phase4ExpectedErrorResource[] {
  return objectId === null ? [] : [{ type: "research_object", id: objectId }];
}

function confirmErrorResources(
  expected: Phase4ConfirmExpectation | null
): readonly Phase4ExpectedErrorResource[] {
  return expected === null
    ? []
    : [
        { type: "research_object", id: expected.objectId },
        { type: "draft", id: expected.draftId },
        { type: "research_run_draft", id: expected.draftId },
        { type: "research_goal", id: expected.goalId },
        { type: "research_scheme", id: expected.schemeId }
      ];
}

function workspaceErrorResources(
  admission: RunAdmissionV1 | null
): readonly Phase4ExpectedErrorResource[] {
  return admission === null
    ? []
    : [
        { type: "research_run", id: admission.runId },
        { type: "research_object", id: admission.objectId }
      ];
}

function isErrorEnvelope(error: Phase4RequestFailure): error is ErrorEnvelope {
  return !("kind" in error);
}

function protocolFailure(
  state: Phase4ProductState,
  source: Phase4RequestKind,
  requestToken: string,
  expectedObjectId: string | null,
  expectedResourceId: string | null,
  updateRequest: (request: Phase4RequestState) => Phase4ProductState
): Phase4ProductState {
  return quarantineResponse(
    state,
    {
      source,
      reason: "CONTRACT_RESPONSE_REJECTED",
      requestToken,
      expectedRequestToken: requestToken,
      expectedObjectId,
      receivedObjectId: null,
      expectedResourceId,
      receivedResourceId: null
    },
    updateRequest
  );
}

function wrongErrorResource(
  state: Phase4ProductState,
  source: Phase4RequestKind,
  requestToken: string,
  expectedObjectId: string | null,
  expectedResourceId: string | null,
  error: ErrorEnvelope,
  updateRequest: (request: Phase4RequestState) => Phase4ProductState
): Phase4ProductState {
  return quarantineResponse(
    state,
    {
      source,
      reason: "ERROR_RESOURCE_IDENTITY_MISMATCH",
      requestToken,
      expectedRequestToken: requestToken,
      expectedObjectId,
      receivedObjectId: null,
      expectedResourceId,
      receivedResourceId: error.error.resource?.id ?? null
    },
    updateRequest
  );
}

function sameJsonValue(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right) &&
      left.length === right.length &&
      left.every((value, index) => sameJsonValue(value, right[index]));
  }
  if (typeof left !== "object" || left === null ||
    typeof right !== "object" || right === null) return false;
  const leftRecord = left as Readonly<Record<string, unknown>>;
  const rightRecord = right as Readonly<Record<string, unknown>>;
  const leftKeys = Object.keys(leftRecord);
  const rightKeys = Object.keys(rightRecord);
  return leftKeys.length === rightKeys.length && leftKeys.every(
    (key) => Object.prototype.hasOwnProperty.call(rightRecord, key) &&
      sameJsonValue(leftRecord[key], rightRecord[key])
  );
}

function isDeepFrozen(value: unknown): boolean {
  if (typeof value !== "object" || value === null) return true;
  if (!Object.isFrozen(value)) return false;
  return Object.values(value).every(isDeepFrozen);
}

function prepareMutationClosesToAuthoring(
  mutation: Phase4Mutation<Phase4PrepareResearchRunInput>,
  selected: NormalizedObjectIdentity,
  goalText: string
): boolean {
  return Object.isFrozen(mutation) &&
    Object.isFrozen(mutation.input) &&
    isDeepFrozen(mutation.input.preferences) &&
    hasValue(mutation.idempotencyKey) &&
    !/[\r\n]/u.test(mutation.idempotencyKey) &&
    mutation.input.researchObjectId === selected.objectId &&
    mutation.input.researchGoal === goalText &&
    hasValue(mutation.input.asOf);
}

function draftClosesToExpectation(
  draft: PreparedResearchDraft,
  expected: Phase4PrepareExpectation,
  mutation: Phase4Mutation<Phase4PrepareResearchRunInput>
): boolean {
  return draft.objectId === expected.objectId &&
    (expected.previousDraftId === null || draft.draftId !== expected.previousDraftId) &&
    (expected.previousSchemeId === null ||
      draft.schemeSnapshot.schemeId !== expected.previousSchemeId) &&
    mutation.input.researchObjectId === expected.objectId &&
    mutation.input.researchGoal === expected.goalText &&
    mutation.input.asOf === expected.asOf &&
    draft.goal.researchObjectId === expected.objectId &&
    draft.goal.goalText === expected.goalText &&
    draft.goal.asOf === mutation.input.asOf &&
    sameJsonValue(draft.goal.preferences, mutation.input.preferences) &&
    draft.schemeSnapshot.researchObjectId === expected.objectId &&
    draft.schemeSnapshot.goalId === draft.goal.goalId &&
    draft.schemeSnapshot.confirmedAt === null;
}

function confirmExpectationFor(draft: PreparedResearchDraft): Phase4ConfirmExpectation {
  return {
    objectId: draft.objectId,
    draftId: draft.draftId,
    draftVersion: draft.draftVersion,
    draftHash: draft.draftHash,
    goalId: draft.goal.goalId,
    schemeId: draft.schemeSnapshot.schemeId
  };
}

function confirmMutationFor(
  draft: PreparedResearchDraft,
  idempotencyKey: string
): Phase4Mutation<Phase4ConfirmResearchRunInput> {
  return createPhase4Mutation(
    {
      draftId: draft.draftId,
      draftVersion: draft.draftVersion,
      draftHash: draft.draftHash,
      researchObjectId: draft.objectId,
      confirmScheme: true,
      expectedGoalId: draft.goal.goalId,
      expectedSchemeId: draft.schemeSnapshot.schemeId
    },
    idempotencyKey
  );
}

function admissionClosesToExpectation(
  admission: RunAdmissionV1,
  expected: Phase4ConfirmExpectation
): boolean {
  return admission.objectId === expected.objectId &&
    admission.draftId === expected.draftId &&
    admission.draftVersion === expected.draftVersion &&
    admission.draftHash === expected.draftHash &&
    admission.goalId === expected.goalId &&
    admission.schemeId === expected.schemeId &&
    admission.autoStart.required === true &&
    admission.autoStart.admitted === true;
}

function sameAdmission(left: RunAdmissionV1, right: RunAdmissionV1): boolean {
  return left.schemaVersion === right.schemaVersion &&
    left.admissionId === right.admissionId &&
    left.runId === right.runId &&
    left.objectId === right.objectId &&
    left.draftId === right.draftId &&
    left.draftVersion === right.draftVersion &&
    left.draftHash === right.draftHash &&
    left.goalId === right.goalId &&
    left.schemeId === right.schemeId &&
    left.plannedGraphId === right.plannedGraphId &&
    left.backendStatus === right.backendStatus &&
    left.status === right.status &&
    left.autoStart.required === right.autoStart.required &&
    left.autoStart.admitted === right.autoStart.admitted &&
    left.confirmationRequestHash === right.confirmationRequestHash &&
    left.admittedAt === right.admittedAt &&
    left.projectionRef === right.projectionRef &&
    left.eventsRef === right.eventsRef;
}

function snapshotClosesToAdmission(snapshot: RunProjection, admission: RunAdmissionV1): boolean {
  return snapshot.object.objectId === admission.objectId &&
    snapshot.run.runId === admission.runId &&
    snapshot.run.researchObjectId === admission.objectId &&
    snapshot.run.goalId === admission.goalId &&
    snapshot.run.schemeId === admission.schemeId &&
    snapshot.run.plannedGraphId === admission.plannedGraphId &&
    snapshot.goal.goalId === admission.goalId &&
    snapshot.goal.researchObjectId === admission.objectId &&
    snapshot.confirmedScheme.schemeId === admission.schemeId &&
    snapshot.confirmedScheme.goalId === admission.goalId &&
    snapshot.confirmedScheme.researchObjectId === admission.objectId &&
    snapshot.plannedGraph.graphId === admission.plannedGraphId &&
    snapshot.plannedGraph.runId === admission.runId;
}

function isOlderSnapshot(current: RunProjection, incoming: RunProjection): boolean {
  return incoming.projectionRevision < current.projectionRevision ||
    incoming.projectionSequence < current.projectionSequence;
}

function hasSameSnapshotWatermark(current: RunProjection, incoming: RunProjection): boolean {
  return incoming.projectionRevision === current.projectionRevision &&
    incoming.projectionSequence === current.projectionSequence;
}

function hasSameRevisionBoundFacts(current: RunProjection, incoming: RunProjection): boolean {
  return sameJsonValue(
    { ...current, generatedAt: null },
    { ...incoming, generatedAt: null }
  );
}

type Phase4RetryRecovery = "RETRY" | "SNAPSHOT_RELOAD";

function transientRetryRecovery(request: Phase4RequestState): "RETRY" | null {
  if (request.phase !== "ERROR" || request.error === null) return null;
  if (isErrorEnvelope(request.error)) {
    return request.error.error.code === "TRANSIENT_BACKEND_ERROR" &&
      request.error.error.retryable === true &&
      request.error.error.recovery === "RETRY"
      ? "RETRY"
      : null;
  }
  return (request.error.code === "NETWORK" || request.error.code === "ABORTED") &&
    request.error.retryable === true &&
    request.error.recovery === "RETRY"
    ? "RETRY"
    : null;
}

/**
 * A rejected mutation response can still follow a committed backend write.
 * Only the retained immutable mutation may cross this recovery boundary.
 */
function mutationRetryRecovery(request: Phase4RequestState): "RETRY" | null {
  return request.phase === "QUARANTINED" ? "RETRY" : transientRetryRecovery(request);
}

function workspaceRetryRecovery(request: Phase4RequestState): Phase4RetryRecovery | null {
  if (request.phase === "QUARANTINED") return "SNAPSHOT_RELOAD";
  if (request.phase !== "ERROR" || request.error === null) return null;
  const recovery = isErrorEnvelope(request.error)
    ? request.error.error.recovery
    : request.error.recovery;
  return recovery === "SNAPSHOT_RELOAD"
    ? "SNAPSHOT_RELOAD"
    : transientRetryRecovery(request);
}

function objectReadRetryRecovery(request: Phase4RequestState): Phase4RetryRecovery | null {
  if (request.phase === "QUARANTINED") return "SNAPSHOT_RELOAD";
  if (request.phase !== "ERROR" || request.error === null) return null;
  const recovery = isErrorEnvelope(request.error)
    ? request.error.error.recovery
    : request.error.recovery;
  return recovery === "SNAPSHOT_RELOAD"
    ? "SNAPSHOT_RELOAD"
    : transientRetryRecovery(request);
}

function prepareContextIsCurrent(
  state: Phase4ProductState,
  expected: Phase4PrepareExpectation,
  mutation: Phase4Mutation<Phase4PrepareResearchRunInput>
): boolean {
  const selected = state.object.selected;
  return selected !== null &&
    state.goal.revision === expected.goalRevision &&
    state.goal.text === expected.goalText &&
    prepareMutationClosesToAuthoring(mutation, selected, expected.goalText) &&
    mutation.input.asOf === expected.asOf;
}

function admissionContextIsCurrent(
  state: Phase4ProductState,
  expected: Phase4ConfirmExpectation
): boolean {
  const draft = state.prepare.draft;
  return state.object.selected?.objectId === expected.objectId &&
    draft !== null &&
    draft.draftId === expected.draftId &&
    draft.draftVersion === expected.draftVersion &&
    draft.draftHash === expected.draftHash &&
    draft.goal.goalId === expected.goalId &&
    draft.schemeSnapshot.schemeId === expected.schemeId;
}

function retryRequest(
  state: Phase4ProductState,
  request: Phase4RequestKind,
  requestToken: string
): Phase4ProductState {
  if (!hasValue(requestToken)) return state;
  if (request === "OBJECT") {
    if (
      !state.object.requestedObjectId ||
      !hasFreshRequestToken(state.object.request, requestToken) ||
      objectReadRetryRecovery(state.object.request) === null
    ) return state;
    return { ...state, object: { ...state.object, request: loadingRequest(requestToken) }, alert: null };
  }
  if (request === "PREPARE") {
    const expected = state.prepare.expected;
    const mutation = state.prepare.mutation;
    if (!expected || !mutation ||
      !hasFreshRequestToken(state.prepare.request, requestToken) ||
      !prepareContextIsCurrent(state, expected, mutation) ||
      mutationRetryRecovery(state.prepare.request) === null) return state;
    return { ...state, prepare: { ...state.prepare, request: loadingRequest(requestToken) }, alert: null };
  }
  if (request === "CONFIRM") {
    const expected = state.confirm.expected;
    if (!expected || !state.confirm.mutation || !state.prepare.draft ||
      !hasFreshRequestToken(state.confirm.request, requestToken) ||
      state.confirm.admission !== null || !admissionContextIsCurrent(state, expected) ||
      mutationRetryRecovery(state.confirm.request) === null) return state;
    return {
      ...state,
      step: "CONFIRM",
      confirm: { ...state.confirm, autoStart: "ADMITTING", request: loadingRequest(requestToken) },
      alert: null
    };
  }
  if (!state.confirm.admission ||
    !hasFreshRequestToken(state.workspace.request, requestToken) ||
    workspaceRetryRecovery(state.workspace.request) === null) return state;
  return {
    ...state,
    step: "WORKSPACE",
    workspace: {
      ...state.workspace,
      stale: state.workspace.snapshot !== null,
      request: loadingRequest(requestToken)
    },
    alert: null
  };
}

export function phase4ProductReducer(
  state: Phase4ProductState,
  action: Phase4ProductAction
): Phase4ProductState {
  switch (action.type) {
    case "flow/reset":
      return { ...createInitialPhase4ProductState(), quarantine: state.quarantine };
    case "object/loadStarted":
      if (!hasFreshRequestToken(state.object.request, action.requestToken) ||
        !hasValue(action.objectId)) return state;
      return withFreshObjectTarget(state, action.objectId, loadingRequest(action.requestToken));
    case "object/loadSucceeded": {
      if (!isCurrentLoadingRequest(state.object.request, action.requestToken)) {
        return staleResponse(state, "OBJECT", action.requestToken, currentToken(state.object.request), state.object.requestedObjectId, action.object.objectId);
      }
      if (action.object.objectId !== state.object.requestedObjectId) {
        const item: Phase4QuarantinedResponse = {
          source: "OBJECT",
          reason: "OBJECT_IDENTITY_MISMATCH",
          requestToken: action.requestToken,
          expectedRequestToken: action.requestToken,
          expectedObjectId: state.object.requestedObjectId,
          receivedObjectId: action.object.objectId,
          expectedResourceId: state.object.requestedObjectId,
          receivedResourceId: action.object.objectId
        };
        return quarantineResponse(state, item, (request) => ({
          ...state,
          object: { ...state.object, selected: null, request }
        }));
      }
      return {
        ...state,
        step: "GOAL",
        object: { requestedObjectId: action.object.objectId, selected: action.object, request: readyRequest(action.requestToken) },
        alert: null
      };
    }
    case "object/loadFailed": {
      if (!isCurrentLoadingRequest(state.object.request, action.requestToken)) {
        return staleResponse(state, "OBJECT", action.requestToken, currentToken(state.object.request), state.object.requestedObjectId, null);
      }
      const expectedId = state.object.requestedObjectId;
      if (!isErrorEnvelope(action.error) && action.error.code === "PROTOCOL") {
        return protocolFailure(state, "OBJECT", action.requestToken, expectedId, expectedId,
          (request) => ({ ...state, object: { ...state.object, selected: null, request } }));
      }
      if (isErrorEnvelope(action.error) &&
        !errorClosesTo(action.error, objectErrorResources(expectedId))) {
        return wrongErrorResource(state, "OBJECT", action.requestToken, expectedId, expectedId, action.error,
          (request) => ({ ...state, object: { ...state.object, request } }));
      }
      return {
        ...state,
        object: { ...state.object, request: failedRequest(action.requestToken, action.error) },
        alert: { kind: "ERROR", source: "OBJECT", error: action.error }
      };
    }
    case "object/selected":
      if (state.object.selected?.objectId === action.object.objectId) {
        return {
          ...state,
          object: { requestedObjectId: action.object.objectId, selected: action.object, request: readyRequest(null) },
          alert: null
        };
      }
      return {
        ...withFreshObjectTarget(state, action.object.objectId, readyRequest(null)),
        step: "GOAL",
        object: { requestedObjectId: action.object.objectId, selected: action.object, request: readyRequest(null) }
      };
    case "goal/changed":
      if (!state.object.selected || action.text === state.goal.text) return state;
      return {
        ...state,
        step: "GOAL",
        goal: { text: action.text, revision: state.goal.revision + 1 },
        prepare: emptyPrepare(),
        confirm: emptyConfirm(),
        workspace: emptyWorkspace(),
        alert: null
      };
    case "prepare/started": {
      const selected = state.object.selected;
      const goalText = state.goal.text;
      const previousDraft = state.prepare.draft;
      if (!hasFreshRequestToken(state.prepare.request, action.requestToken) ||
        !selected || !hasValue(goalText) ||
        !prepareMutationClosesToAuthoring(action.mutation, selected, goalText) ||
        state.prepare.request.phase === "LOADING" ||
        (state.prepare.mutation !== null &&
          (state.prepare.request.phase !== "READY" ||
            state.prepare.mutation.idempotencyKey === action.mutation.idempotencyKey)) ||
        state.confirm.mutation !== null || state.confirm.request.phase === "LOADING" ||
        state.confirm.admission !== null) return state;
      return {
        ...state,
        step: "SCHEME",
        prepare: {
          expected: {
            objectId: selected.objectId,
            goalText,
            goalRevision: state.goal.revision,
            asOf: action.mutation.input.asOf,
            previousDraftId: previousDraft?.draftId ?? null,
            previousSchemeId: previousDraft?.schemeSnapshot.schemeId ?? null
          },
          mutation: action.mutation,
          draft: null,
          request: loadingRequest(action.requestToken)
        },
        confirm: emptyConfirm(),
        workspace: emptyWorkspace(),
        alert: null
      };
    }
    case "prepare/succeeded": {
      const expected = state.prepare.expected;
      const mutation = state.prepare.mutation;
      if (!isCurrentLoadingRequest(state.prepare.request, action.requestToken)) {
        return staleResponse(state, "PREPARE", action.requestToken, currentToken(state.prepare.request), expected?.objectId ?? state.object.selected?.objectId ?? null, action.draft.objectId);
      }
      if (!expected || !mutation || !draftClosesToExpectation(action.draft, expected, mutation)) {
        const item: Phase4QuarantinedResponse = {
          source: "PREPARE",
          reason: "DRAFT_IDENTITY_MISMATCH",
          requestToken: action.requestToken,
          expectedRequestToken: action.requestToken,
          expectedObjectId: expected?.objectId ?? null,
          receivedObjectId: action.draft.objectId,
          expectedResourceId: expected?.objectId ?? null,
          receivedResourceId: action.draft.draftId
        };
        return quarantineResponse(state, item, (request) => ({
          ...state,
          prepare: { ...state.prepare, draft: null, request }
        }));
      }
      return {
        ...state,
        step: "SCHEME",
        prepare: { expected, mutation, draft: action.draft, request: readyRequest(action.requestToken) },
        alert: null
      };
    }
    case "prepare/failed": {
      const expected = state.prepare.expected;
      if (!isCurrentLoadingRequest(state.prepare.request, action.requestToken)) {
        return staleResponse(state, "PREPARE", action.requestToken, currentToken(state.prepare.request), expected?.objectId ?? null, null);
      }
      if (!isErrorEnvelope(action.error) && action.error.code === "PROTOCOL") {
        return protocolFailure(state, "PREPARE", action.requestToken, expected?.objectId ?? null, expected?.objectId ?? null,
          (request) => ({ ...state, prepare: { ...state.prepare, draft: null, request } }));
      }
      if (isErrorEnvelope(action.error) &&
        !errorClosesTo(action.error, objectErrorResources(expected?.objectId ?? null))) {
        return wrongErrorResource(state, "PREPARE", action.requestToken, expected?.objectId ?? null, expected?.objectId ?? null, action.error,
          (request) => ({ ...state, prepare: { ...state.prepare, request } }));
      }
      return {
        ...state,
        prepare: { ...state.prepare, draft: null, request: failedRequest(action.requestToken, action.error) },
        alert: { kind: "ERROR", source: "PREPARE", error: action.error }
      };
    }
    case "confirm/started": {
      const draft = state.prepare.draft;
      const prepareExpected = state.prepare.expected;
      const prepareMutation = state.prepare.mutation;
      if (!hasFreshRequestToken(state.confirm.request, action.requestToken) ||
        !hasValue(action.idempotencyKey) || !draft ||
        !prepareExpected || !prepareMutation ||
        !prepareContextIsCurrent(state, prepareExpected, prepareMutation) ||
        !draftClosesToExpectation(draft, prepareExpected, prepareMutation) ||
        state.confirm.mutation !== null || state.confirm.request.phase === "LOADING" ||
        state.confirm.admission !== null ||
        state.object.selected?.objectId !== draft.objectId) return state;
      return {
        ...state,
        step: "CONFIRM",
        confirm: {
          expected: confirmExpectationFor(draft),
          mutation: confirmMutationFor(draft, action.idempotencyKey),
          admission: null,
          responseMeta: null,
          autoStart: "ADMITTING",
          request: loadingRequest(action.requestToken)
        },
        workspace: emptyWorkspace(),
        alert: null
      };
    }
    case "confirm/succeeded": {
      const expected = state.confirm.expected;
      const isPendingResponse = isCurrentLoadingRequest(state.confirm.request, action.requestToken);
      const isRepeatedAcceptedResponse = state.confirm.request.phase === "READY" &&
        state.confirm.request.requestToken === action.requestToken && state.confirm.admission !== null;
      if (!isPendingResponse && !isRepeatedAcceptedResponse) {
        return staleResponse(state, "CONFIRM", action.requestToken, currentToken(state.confirm.request), expected?.objectId ?? null, action.response.admission.objectId);
      }
      if (!expected || !admissionClosesToExpectation(action.response.admission, expected)) {
        const item: Phase4QuarantinedResponse = {
          source: "CONFIRM",
          reason: "CONFIRM_IDENTITY_MISMATCH",
          requestToken: action.requestToken,
          expectedRequestToken: currentToken(state.confirm.request),
          expectedObjectId: expected?.objectId ?? null,
          receivedObjectId: action.response.admission.objectId,
          expectedResourceId: expected?.draftId ?? null,
          receivedResourceId: action.response.admission.draftId
        };
        return quarantineResponse(state, item, (request) => ({
          ...state,
          confirm: { ...state.confirm, autoStart: state.confirm.admission ? "ADMITTED" : "FAILED", request }
        }));
      }
      if (state.confirm.admission) {
        if (!sameAdmission(state.confirm.admission, action.response.admission)) {
          const item: Phase4QuarantinedResponse = {
            source: "CONFIRM",
            reason: "REPLAY_ADMISSION_MISMATCH",
            requestToken: action.requestToken,
            expectedRequestToken: currentToken(state.confirm.request),
            expectedObjectId: state.confirm.admission.objectId,
            receivedObjectId: action.response.admission.objectId,
            expectedResourceId: state.confirm.admission.runId,
            receivedResourceId: action.response.admission.runId
          };
          return quarantineResponse(state, item);
        }
        return {
          ...state,
          confirm: {
            ...state.confirm,
            responseMeta: action.response.responseMeta,
            autoStart: "ADMITTED",
            request: readyRequest(action.requestToken)
          },
          alert: null
        };
      }
      return {
        ...state,
        step: "WORKSPACE",
        confirm: {
          ...state.confirm,
          admission: action.response.admission,
          responseMeta: action.response.responseMeta,
          autoStart: "ADMITTED",
          request: readyRequest(action.requestToken)
        },
        workspace: emptyWorkspace(),
        alert: null
      };
    }
    case "confirm/failed": {
      const expected = state.confirm.expected;
      if (!isCurrentLoadingRequest(state.confirm.request, action.requestToken)) {
        return staleResponse(state, "CONFIRM", action.requestToken, currentToken(state.confirm.request), expected?.objectId ?? null, null);
      }
      if (!isErrorEnvelope(action.error) && action.error.code === "PROTOCOL") {
        return protocolFailure(state, "CONFIRM", action.requestToken, expected?.objectId ?? null, expected?.draftId ?? null,
          (request) => ({ ...state, confirm: { ...state.confirm, autoStart: "FAILED", request } }));
      }
      if (isErrorEnvelope(action.error) &&
        !errorClosesTo(action.error, confirmErrorResources(expected))) {
        return wrongErrorResource(state, "CONFIRM", action.requestToken, expected?.objectId ?? null, expected?.draftId ?? null, action.error,
          (request) => ({ ...state, confirm: { ...state.confirm, autoStart: "FAILED", request } }));
      }
      return {
        ...state,
        confirm: { ...state.confirm, autoStart: "FAILED", request: failedRequest(action.requestToken, action.error) },
        alert: { kind: "ERROR", source: "CONFIRM", error: action.error }
      };
    }
    case "workspace/loadStarted":
      if (!hasFreshRequestToken(state.workspace.request, action.requestToken) ||
        !state.confirm.admission || state.workspace.request.phase === "LOADING") return state;
      return {
        ...state,
        step: "WORKSPACE",
        workspace: { ...state.workspace, stale: state.workspace.snapshot !== null, request: loadingRequest(action.requestToken) },
        alert: null
      };
    case "workspace/loadSucceeded": {
      const admission = state.confirm.admission;
      if (!isCurrentLoadingRequest(state.workspace.request, action.requestToken)) {
        return staleResponse(state, "WORKSPACE", action.requestToken, currentToken(state.workspace.request), admission?.objectId ?? null, action.snapshot.object.objectId);
      }
      if (!admission || !snapshotClosesToAdmission(action.snapshot, admission)) {
        const item: Phase4QuarantinedResponse = {
          source: "WORKSPACE",
          reason: "RUN_IDENTITY_MISMATCH",
          requestToken: action.requestToken,
          expectedRequestToken: action.requestToken,
          expectedObjectId: admission?.objectId ?? null,
          receivedObjectId: action.snapshot.object.objectId,
          expectedResourceId: admission?.runId ?? null,
          receivedResourceId: action.snapshot.run.runId
        };
        return quarantineResponse(state, item, (request) => ({
          ...state,
          workspace: { ...state.workspace, stale: state.workspace.snapshot !== null, request }
        }));
      }
      if (state.workspace.snapshot && isOlderSnapshot(state.workspace.snapshot, action.snapshot)) {
        const item: Phase4QuarantinedResponse = {
          source: "WORKSPACE",
          reason: "STALE_RUN_PROJECTION",
          requestToken: action.requestToken,
          expectedRequestToken: action.requestToken,
          expectedObjectId: admission.objectId,
          receivedObjectId: action.snapshot.object.objectId,
          expectedResourceId: admission.runId,
          receivedResourceId: action.snapshot.run.runId
        };
        return quarantineResponse(state, item, (request) => ({
          ...state,
          workspace: { ...state.workspace, stale: true, request }
        }));
      }
      if (
        state.workspace.snapshot &&
        action.snapshot.projectionRevision === state.workspace.snapshot.projectionRevision &&
        action.snapshot.projectionSequence !== state.workspace.snapshot.projectionSequence
      ) {
        const item: Phase4QuarantinedResponse = {
          source: "WORKSPACE",
          reason: "PROJECTION_IDENTITY_CONFLICT",
          requestToken: action.requestToken,
          expectedRequestToken: action.requestToken,
          expectedObjectId: admission.objectId,
          receivedObjectId: action.snapshot.object.objectId,
          expectedResourceId: admission.runId,
          receivedResourceId: action.snapshot.run.runId
        };
        return quarantineResponse(state, item, (request) => ({
          ...state,
          workspace: { ...state.workspace, stale: true, request }
        }));
      }
      if (state.workspace.snapshot && hasSameSnapshotWatermark(state.workspace.snapshot, action.snapshot)) {
        if (!hasSameRevisionBoundFacts(state.workspace.snapshot, action.snapshot)) {
          const item: Phase4QuarantinedResponse = {
            source: "WORKSPACE",
            reason: "PROJECTION_IDENTITY_CONFLICT",
            requestToken: action.requestToken,
            expectedRequestToken: action.requestToken,
            expectedObjectId: admission.objectId,
            receivedObjectId: action.snapshot.object.objectId,
            expectedResourceId: admission.runId,
            receivedResourceId: action.snapshot.run.runId
          };
          return quarantineResponse(state, item, (request) => ({
            ...state,
            workspace: { ...state.workspace, stale: true, request }
          }));
        }
        return {
          ...state,
          workspace: {
            snapshot: state.workspace.snapshot,
            stale: false,
            request: readyRequest(action.requestToken)
          },
          alert: null
        };
      }
      return {
        ...state,
        step: "WORKSPACE",
        workspace: { snapshot: action.snapshot, stale: false, request: readyRequest(action.requestToken) },
        alert: null
      };
    }
    case "workspace/loadFailed": {
      const admission = state.confirm.admission;
      if (!isCurrentLoadingRequest(state.workspace.request, action.requestToken)) {
        return staleResponse(state, "WORKSPACE", action.requestToken, currentToken(state.workspace.request), admission?.objectId ?? null, null);
      }
      if (!isErrorEnvelope(action.error) && action.error.code === "PROTOCOL") {
        return protocolFailure(state, "WORKSPACE", action.requestToken, admission?.objectId ?? null, admission?.runId ?? null,
          (request) => ({ ...state, workspace: { ...state.workspace, stale: state.workspace.snapshot !== null, request } }));
      }
      if (isErrorEnvelope(action.error) &&
        !errorClosesTo(action.error, workspaceErrorResources(admission))) {
        return wrongErrorResource(state, "WORKSPACE", action.requestToken, admission?.objectId ?? null, admission?.runId ?? null, action.error,
          (request) => ({ ...state, workspace: { ...state.workspace, stale: state.workspace.snapshot !== null, request } }));
      }
      return {
        ...state,
        workspace: {
          ...state.workspace,
          stale: state.workspace.snapshot !== null,
          request: failedRequest(action.requestToken, action.error)
        },
        alert: { kind: "ERROR", source: "WORKSPACE", error: action.error }
      };
    }
    case "request/retryStarted":
      return retryRequest(state, action.request, action.requestToken);
    case "alert/dismissed":
      return state.alert === null ? state : { ...state, alert: null };
  }
}

export const phase4ProductActions = {
  flowReset: (): Phase4ProductAction => ({ type: "flow/reset" }),
  objectLoadStarted: (requestToken: string, objectId: string): Phase4ProductAction => ({ type: "object/loadStarted", requestToken, objectId }),
  objectLoadSucceeded: (requestToken: string, object: NormalizedObjectIdentity): Phase4ProductAction => ({ type: "object/loadSucceeded", requestToken, object }),
  objectLoadFailed: (requestToken: string, error: Phase4RequestFailure): Phase4ProductAction => ({ type: "object/loadFailed", requestToken, error }),
  objectSelected: (object: NormalizedObjectIdentity): Phase4ProductAction => ({ type: "object/selected", object }),
  goalChanged: (text: string): Phase4ProductAction => ({ type: "goal/changed", text }),
  prepareStarted: (
    requestToken: string,
    mutation: Phase4Mutation<Phase4PrepareResearchRunInput>
  ): Phase4ProductAction => ({ type: "prepare/started", requestToken, mutation }),
  prepareSucceeded: (requestToken: string, draft: PreparedResearchDraft): Phase4ProductAction => ({ type: "prepare/succeeded", requestToken, draft }),
  prepareFailed: (requestToken: string, error: Phase4RequestFailure): Phase4ProductAction => ({ type: "prepare/failed", requestToken, error }),
  confirmStarted: (requestToken: string, idempotencyKey: string): Phase4ProductAction => ({ type: "confirm/started", requestToken, idempotencyKey }),
  confirmSucceeded: (requestToken: string, response: ConfirmRunResponseV1): Phase4ProductAction => ({ type: "confirm/succeeded", requestToken, response }),
  confirmFailed: (requestToken: string, error: Phase4RequestFailure): Phase4ProductAction => ({ type: "confirm/failed", requestToken, error }),
  workspaceLoadStarted: (requestToken: string): Phase4ProductAction => ({ type: "workspace/loadStarted", requestToken }),
  workspaceLoadSucceeded: (requestToken: string, snapshot: RunProjection): Phase4ProductAction => ({ type: "workspace/loadSucceeded", requestToken, snapshot }),
  workspaceLoadFailed: (requestToken: string, error: Phase4RequestFailure): Phase4ProductAction => ({ type: "workspace/loadFailed", requestToken, error }),
  retryStarted: (request: Phase4RequestKind, requestToken: string): Phase4ProductAction => ({ type: "request/retryStarted", request, requestToken }),
  errorDismissed: (): Phase4ProductAction => ({ type: "alert/dismissed" })
} as const;

export interface Phase4WorkspaceRunIdentity {
  readonly admissionId: string;
  readonly runId: string;
  readonly objectId: string;
  readonly goalId: string;
  readonly schemeId: string;
  readonly plannedGraphId: string;
  readonly projectionRef: string;
  readonly eventsRef: string;
}

export interface Phase4RetryState {
  readonly request: Phase4RequestKind;
  readonly previousRequestToken: string | null;
  readonly recovery: "RETRY" | "SNAPSHOT_RELOAD";
  readonly objectId: string | null;
  readonly runId: string | null;
  readonly prepareMutation: Phase4Mutation<Phase4PrepareResearchRunInput> | null;
  readonly confirmMutation: Phase4Mutation<Phase4ConfirmResearchRunInput> | null;
}

function retryStateFor(
  request: Phase4RequestKind,
  requestState: Phase4RequestState,
  recovery: Phase4RetryRecovery | null,
  objectId: string | null,
  runId: string | null,
  prepareMutation: Phase4Mutation<Phase4PrepareResearchRunInput> | null = null,
  confirmMutation: Phase4Mutation<Phase4ConfirmResearchRunInput> | null = null
): Phase4RetryState | null {
  if (recovery === null) return null;
  return {
    request,
    previousRequestToken: requestState.requestToken,
    recovery,
    objectId,
    runId,
    prepareMutation,
    confirmMutation
  };
}

export const selectProductFlowStep = (state: Phase4ProductState): Phase4FlowStep => state.step;
export const selectSelectedObject = (state: Phase4ProductState): NormalizedObjectIdentity | null => state.object.selected;
export const selectGoalText = (state: Phase4ProductState): string => state.goal.text;
export const selectPreparedDraft = (state: Phase4ProductState): PreparedResearchDraft | null => state.prepare.draft;
export const selectPrepareMutation = (
  state: Phase4ProductState
): Phase4Mutation<Phase4PrepareResearchRunInput> | null => state.prepare.mutation;
export const selectConfirmPending = (state: Phase4ProductState): boolean => state.confirm.request.phase === "LOADING";
export const selectConfirmAdmission = (state: Phase4ProductState): RunAdmissionV1 | null => state.confirm.admission;
export const selectConfirmResponseMeta = (state: Phase4ProductState): ResponseMetaV1 | null => state.confirm.responseMeta;
export const selectConfirmMutation = (state: Phase4ProductState): Phase4Mutation<Phase4ConfirmResearchRunInput> | null => state.confirm.mutation;
export const selectCanPrepare = (state: Phase4ProductState): boolean =>
  state.object.selected !== null && hasValue(state.goal.text) &&
  state.prepare.request.phase !== "LOADING" && state.confirm.request.phase !== "LOADING" &&
  (state.prepare.mutation === null || state.prepare.request.phase === "READY") &&
  state.confirm.mutation === null && state.confirm.admission === null;

export const selectCanConfirm = (state: Phase4ProductState): boolean => {
  const draft = state.prepare.draft;
  if (!draft || state.confirm.mutation !== null || state.confirm.request.phase === "LOADING" ||
    state.confirm.admission !== null ||
    state.object.selected?.objectId !== draft.objectId) return false;
  const expected = state.prepare.expected;
  const mutation = state.prepare.mutation;
  return expected !== null && mutation !== null &&
    prepareContextIsCurrent(state, expected, mutation) &&
    draftClosesToExpectation(draft, expected, mutation);
};

export const selectAutoStartState = (state: Phase4ProductState): Phase4AutoStartState => state.confirm.autoStart;
export const selectWorkspaceShell = (state: Phase4ProductState): Phase4WorkspaceState => state.workspace;

export function selectWorkspaceRunIdentity(state: Phase4ProductState): Phase4WorkspaceRunIdentity | null {
  const admission = state.confirm.admission;
  if (!admission) return null;
  return {
    admissionId: admission.admissionId,
    runId: admission.runId,
    objectId: admission.objectId,
    goalId: admission.goalId,
    schemeId: admission.schemeId,
    plannedGraphId: admission.plannedGraphId,
    projectionRef: admission.projectionRef,
    eventsRef: admission.eventsRef
  };
}

export const selectVisibleError = (state: Phase4ProductState): Phase4VisibleAlert | null => state.alert;

export function selectRetryState(state: Phase4ProductState): Phase4RetryState | null {
  const admission = state.confirm.admission;
  const workspaceRetry = admission === null
    ? null
    : retryStateFor(
        "WORKSPACE",
        state.workspace.request,
        workspaceRetryRecovery(state.workspace.request),
        admission.objectId,
        admission.runId
      );
  const confirmExpected = state.confirm.expected;
  const confirmMutation = state.confirm.mutation;
  const confirmRetry = confirmExpected === null || confirmMutation === null ||
    admission !== null || !admissionContextIsCurrent(state, confirmExpected)
    ? null
    : retryStateFor(
        "CONFIRM",
        state.confirm.request,
        mutationRetryRecovery(state.confirm.request),
        confirmExpected.objectId,
        null,
        null,
        confirmMutation
      );
  const prepareExpected = state.prepare.expected;
  const prepareMutation = state.prepare.mutation;
  const prepareRetry = prepareExpected === null || prepareMutation === null ||
    !prepareContextIsCurrent(state, prepareExpected, prepareMutation)
    ? null
    : retryStateFor(
        "PREPARE",
        state.prepare.request,
        mutationRetryRecovery(state.prepare.request),
        prepareExpected.objectId,
        null,
        prepareMutation
      );
  const objectRetry = state.object.requestedObjectId === null
    ? null
    : retryStateFor(
        "OBJECT",
        state.object.request,
        objectReadRetryRecovery(state.object.request),
        state.object.requestedObjectId,
        null
      );
  return workspaceRetry ?? confirmRetry ?? prepareRetry ?? objectRetry;
}

export const selectQuarantine = (state: Phase4ProductState): readonly Phase4QuarantinedResponse[] => state.quarantine;
export const selectIsLoading = (state: Phase4ProductState): boolean =>
  state.object.request.phase === "LOADING" || state.prepare.request.phase === "LOADING" ||
  state.confirm.request.phase === "LOADING" || state.workspace.request.phase === "LOADING";
