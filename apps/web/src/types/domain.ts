/**
 * Frozen Phase 4 V17 R2 consumer contracts.
 *
 * Backend JSON is snake_case and must enter the application through one of the
 * decoders in this module.  The exported values are immutable camelCase DTOs;
 * none of the legacy V8 demo shapes below participates in this boundary.
 */
export const PHASE4_CONTRACT_VERSION = "phase4-core/v1" as const;
export const RUN_HISTORY_COLLECTION_SCHEMA_VERSION = "phase4-run-history-collection/v1" as const;
export const RUN_DRAFT_SCHEMA_VERSION = "phase4-run-draft/v1" as const;
export const CONFIRM_RESPONSE_SCHEMA_VERSION = "phase4-confirm-response/v1" as const;
export const RUN_ADMISSION_SCHEMA_VERSION = "phase4-run-admission/v1" as const;
export const RESPONSE_META_SCHEMA_VERSION = "phase4-response-meta/v1" as const;
export const RUN_PROJECTION_SCHEMA_VERSION = "phase4-run-projection/v1" as const;
export const ERROR_SCHEMA_VERSION = "phase4-error/v1" as const;

export type JsonPrimitive = string | number | boolean | null;
export type SafeJsonValue = JsonPrimitive | readonly SafeJsonValue[] | SafeJsonObject;
export interface SafeJsonObject {
  readonly [key: string]: SafeJsonValue;
}

export type BackendRunStatus =
  | "DRAFT"
  | "SCHEME_GENERATING"
  | "AWAITING_CONFIRMATION"
  | "PLANNING"
  | "RUNNING"
  | "REVIEW"
  | "PROVING"
  | "RELEASED"
  | "FAILED"
  | "CANCELLED";

export type Phase4RunStatus =
  | "PREPARING"
  | "AWAITING_CONFIRMATION"
  | "PLANNING"
  | "RESEARCHING"
  | "REVIEWING"
  | "PROVING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";
export type NormalizedRunStatus = Phase4RunStatus;

export type Phase4RunStage =
  | "PREPARE"
  | "CONFIRM"
  | "PLANNING"
  | "RESEARCH"
  | "REVIEW"
  | "PROVING"
  | "COMPLETE"
  | "FAILED"
  | "CANCELLED";

export type BackendTaskStatus =
  | "CREATED"
  | "WAITING"
  | "READY"
  | "RUNNING"
  | "WAITING_FOR_CAPABILITY"
  | "SELF_CORRECTING"
  | "BLOCKED"
  | "REVIEW"
  | "COMPLETED"
  | "FAILED"
  | "CAPABILITY_BUILD_FAILED"
  | "CANCELLED";

export type Phase4TaskStatus =
  | "QUEUED"
  | "READY"
  | "ACTIVE"
  | "WAITING_SUPPORT"
  | "CORRECTING"
  | "BLOCKED"
  | "REVIEW"
  | "COMPLETE"
  | "FAILED"
  | "CANCELLED";
export type NormalizedTaskStatus = Phase4TaskStatus;

export type Phase4ReviewStatus = "PASS" | "REVIEW" | "BLOCK";
export type Phase4ProofStatus =
  | "NOT_REQUIRED"
  | "PENDING"
  | "PROVING"
  | "GENERATED_UNVERIFIED"
  | "VERIFIED"
  | "INVALID"
  | "ERROR"
  | "UNSUPPORTED";
export type AvailabilityStatus =
  | "PENDING"
  | "AVAILABLE"
  | "NOT_GENERATED"
  | "NOT_RELEASED"
  | "UNAVAILABLE"
  | "FAILED";

export interface Availability {
  readonly status: AvailabilityStatus;
  readonly reasonCode: string | null;
  readonly retryable: boolean;
}

export type ErrorCode =
  | "INVALID_CURSOR"
  | "UNAUTHENTICATED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "IDENTITY_MISMATCH"
  | "UNAVAILABLE"
  | "NOT_GENERATED"
  | "NOT_RELEASED"
  | "CONFLICT"
  | "CURSOR_AHEAD"
  | "SCHEMA_INCOMPATIBLE"
  | "UNSUPPORTED_EVENT"
  | "TERMINAL"
  | "REQUEST_VALIDATION_ERROR"
  | "INTEGRITY_FAILURE"
  | "INTERNAL_ERROR"
  | "TRANSIENT_BACKEND_ERROR";

export type ErrorRecovery = "NONE" | "RETRY" | "SNAPSHOT_RELOAD" | "REAUTHENTICATE";

/** Resource kinds are open strings in frozen R2; state admission still checks exact route pairs. */
export type ErrorResourceType = string;

export interface ErrorEnvelope {
  readonly schemaVersion: typeof ERROR_SCHEMA_VERSION;
  readonly error: {
    readonly code: ErrorCode;
    readonly message: string;
    readonly retryable: boolean;
    readonly recovery: ErrorRecovery;
    readonly requestId: string | null;
    readonly resource: Readonly<{ type: ErrorResourceType; id: string }> | null;
    readonly details: SafeJsonObject;
  };
}

export interface NormalizedObjectIdentity {
  readonly objectId: string;
  readonly symbol: string;
  readonly companyName: string;
  readonly objectType: string;
  readonly exchange: string;
  readonly sector: string | null;
  readonly currency: string;
  readonly identityVersion: number;
}

export interface NormalizedGoal {
  readonly goalId: string;
  readonly researchObjectId: string;
  readonly goalType: string;
  readonly goalText: string;
  readonly asOf: string;
  readonly preferences: SafeJsonObject;
  readonly createdAt: string;
}

export interface NormalizedScheme {
  readonly incrementalContext?: import("./incremental").IncrementalContext;
  readonly schemeId: string;
  readonly researchObjectId: string;
  readonly goalId: string;
  readonly researchScope: readonly string[];
  readonly dataRequirements: readonly string[];
  readonly agentRequirements: readonly string[];
  readonly skillRequirements: readonly string[];
  readonly calculationRequirements: readonly string[];
  readonly assuranceRequirements: SafeJsonObject;
  readonly reportRequirements: readonly string[];
  readonly limitations: readonly string[];
  readonly generatedBy: string;
  readonly generatedModel: string | null;
  readonly createdAt: string;
  readonly confirmedAt: string | null;
}

export interface SafeRuntimeActivity {
  readonly eventId: string;
  readonly type: string;
  readonly sequence: number;
  readonly timestamp: string;
  readonly taskId: string | null;
  readonly messageCode: string;
  readonly status?: string | null;
  readonly actorId?: string | null;
  readonly actorType?: string | null;
  readonly durationMs?: number | null;
  readonly inputRefs?: readonly string[];
  readonly outputRefs?: readonly string[];
  readonly evidenceRefs?: readonly string[];
  readonly calculationRefs?: readonly string[];
  readonly claimRefs?: readonly string[];
  readonly judgmentRefs?: readonly string[];
  readonly reviewRefs?: readonly string[];
  readonly proofRefs?: readonly string[];
  readonly artifactRefs?: readonly string[];
  readonly traceBundleRefs?: readonly string[];
}

export interface NormalizedRuntimeEventV1 {
  readonly eventContractVersion: "phase4-runtime-event/v1";
  readonly eventId: string;
  readonly runId: string;
  readonly taskId: string | null;
  readonly type: string;
  readonly timestamp: string;
  readonly sequence: number;
  readonly payloadSchemaVersion: 1;
  readonly payload: Readonly<Record<string, unknown>>;
  readonly graphVersion: number | null;
  readonly effect: "PATCH_PROJECTION" | "REFRESH_PROJECTION" | "OBSERVATION_ONLY" | "TERMINAL";
  readonly projectionRefreshRequired: boolean;
}

export type ConnectionState =
  | Readonly<{ kind: "IDLE"; runId: string; lastSequence: number }>
  | Readonly<{ kind: "CONNECTING"; runId: string; lastSequence: number; attempt: number }>
  | Readonly<{
      kind: "OPEN";
      runId: string;
      lastSequence: number;
      lastHeartbeatAt: string | null;
    }>
  | Readonly<{
      kind: "BACKOFF";
      runId: string;
      lastSequence: number;
      attempt: number;
      retryAt: string;
      error: ErrorEnvelope;
    }>
  | Readonly<{
      kind: "RECOVERING";
      runId: string;
      lastSequence: number;
      reason:
        | "CURSOR_REJECTED"
        | "SEQUENCE_GAP"
        | "UNKNOWN_EVENT"
        | "SCHEMA_INCOMPATIBLE"
        | "PROJECTION_MISMATCH";
    }>
  | Readonly<{ kind: "FAILED"; runId: string; lastSequence: number; error: ErrorEnvelope }>
  | Readonly<{
      kind: "TERMINAL";
      runId: string;
      lastSequence: number;
      outcome: "SUCCESS" | "FAILURE" | "CANCELLED";
    }>;

export interface Phase4ResearchObjectDetail {
  readonly object: NormalizedObjectIdentity;
  readonly latestReleasedRunId: string | null;
  readonly releasedResultAvailability: Availability;
  readonly runCount: number;
  readonly lastActivity: SafeRuntimeActivity | null;
  readonly createdAt: string;
  readonly updatedAt: string;
}

export interface ResearchObjectCollection {
  readonly items: readonly Phase4ResearchObjectDetail[];
  readonly nextCursor: string | null;
}

export interface PreparedResearchDraft {
  readonly schemaVersion: typeof RUN_DRAFT_SCHEMA_VERSION;
  readonly draftId: string;
  readonly draftVersion: number;
  readonly status: "AWAITING_CONFIRMATION";
  readonly previewKind: "SCHEME_ONLY";
  readonly plannedGraphAvailability: Availability;
  readonly objectId: string;
  readonly goal: NormalizedGoal;
  readonly schemeSnapshot: NormalizedScheme & Readonly<{ confirmedAt: null }>;
  readonly prepareRequestHash: string;
  readonly draftHash: string;
  readonly createdAt: string;
  readonly expiresAt: string;
}

export interface RunAdmissionV1 {
  readonly schemaVersion: typeof RUN_ADMISSION_SCHEMA_VERSION;
  readonly admissionId: string;
  readonly runId: string;
  readonly objectId: string;
  readonly draftId: string;
  readonly draftVersion: number;
  readonly draftHash: string;
  readonly goalId: string;
  readonly schemeId: string;
  readonly plannedGraphId: string;
  readonly backendStatus: "PLANNING";
  readonly status: "PLANNING";
  readonly autoStart: Readonly<{ required: true; admitted: true }>;
  readonly confirmationRequestHash: string;
  readonly admittedAt: string;
  readonly projectionRef: string;
  readonly eventsRef: string;
}

export interface ResponseMetaV1 {
  readonly schemaVersion: typeof RESPONSE_META_SCHEMA_VERSION;
  readonly requestId: string | null;
  readonly idempotencyReplayed: boolean;
}

export interface ConfirmRunResponseV1 {
  readonly schemaVersion: typeof CONFIRM_RESPONSE_SCHEMA_VERSION;
  /** Immutable business admission. Replay metadata must never be folded into this object. */
  readonly admission: RunAdmissionV1;
  /** Per-response transport metadata; it is excluded from the immutable admission hash. */
  readonly responseMeta: ResponseMetaV1;
}

export interface RunProgress {
  readonly method: "ACTUAL_TASK_MEAN_V1";
  readonly completedTasks: number;
  readonly totalTasks: number;
  readonly fraction: number;
  /** Exact presentation derivation: fraction * 100. Not backend business truth. */
  readonly percent: number;
}

/** Exact compact activity shape frozen for Run collection rows. */
export interface RunCollectionActivity {
  readonly eventId: string;
  readonly type: string;
  readonly sequence: number;
  readonly timestamp: string;
  readonly taskId: string | null;
  readonly messageCode: string;
}

export interface RunCollectionItem {
  readonly runId: string;
  readonly object: Readonly<{ objectId: string; symbol: string; companyName: string }>;
  readonly backendStatus: BackendRunStatus;
  readonly status: Phase4RunStatus;
  readonly stage: Phase4RunStage;
  readonly progress: RunProgress;
  readonly activity: RunCollectionActivity | null;
  readonly graphVersion: number | null;
  readonly projectionRevision: number;
  readonly projectionSequence: number;
  readonly asOf: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly startedAt: string | null;
  readonly completedAt: string | null;
  readonly terminal: boolean;
  readonly resultAvailability: Availability;
}

export interface AvailableRunHistoryItem {
  readonly availability: "AVAILABLE";
  readonly run: RunCollectionItem;
}

export interface UnavailableIncompatibleRunHistoryItem {
  readonly availability: "UNAVAILABLE_INCOMPATIBLE";
  readonly runId: string;
  readonly object: Readonly<{ objectId: string; symbol: string; companyName: string }>;
  readonly backendStatus: BackendRunStatus;
  readonly updatedAt: string;
  readonly reasonCode: "LEGACY_OR_INCOMPATIBLE";
}

export type RunHistoryItem = AvailableRunHistoryItem | UnavailableIncompatibleRunHistoryItem;

export interface GlobalRunCollectionProjection {
  readonly schemaVersion: typeof RUN_HISTORY_COLLECTION_SCHEMA_VERSION;
  readonly items: readonly RunHistoryItem[];
  readonly nextCursor: string | null;
}

export interface RunLineage {
  readonly baseRunId?: string | null;
  readonly baseResearchViewVersion?: string | null;
  readonly reexecutionOfRunId?: string | null;
}

export interface ResearchRunDetailV1 extends RunLineage {
  readonly runId: string;
  readonly researchObjectId: string;
  readonly goalId: string;
  readonly schemeId: string;
  readonly backendStatus: BackendRunStatus;
  readonly status: Phase4RunStatus;
  readonly stage: Phase4RunStage;
  readonly asOf: string;
  readonly plannedGraphId: string | null;
  readonly actualGraphId: string | null;
  readonly executionTarget: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly startedAt: string | null;
  readonly completedAt: string | null;
  readonly terminal: boolean;
  readonly projectionRevision: number;
  readonly projectionSequence: number;
}

/** Closed Run record with explicit optional knowledge/execution lineage. */
export type EmbeddedResearchRunV1 = Omit<
  ResearchRunDetailV1,
  "projectionRevision" | "projectionSequence"
>;

export interface RunTaskProjection {
  readonly taskId: string;
  readonly runId: string;
  readonly parentTaskId: string | null;
  readonly taskType: string;
  readonly goal: string;
  readonly assignedAgent: string;
  readonly skillId: string;
  readonly dependencies: readonly string[];
  readonly origin: "PLAN" | "REPLAN" | "REVIEW_FIX";
  readonly reasonCode: string | null;
  readonly backendStatus: BackendTaskStatus;
  readonly status: Phase4TaskStatus;
  readonly progress: number;
  readonly attemptCount: number;
  readonly taskInputEvidenceIds: readonly string[];
  readonly taskOutputEvidenceIds: readonly string[];
  readonly evidenceAcquisitionStatus:
    | "COMPLETED"
    | "PARTIAL"
    | "ENTITLEMENT_BLOCKED"
    | "FAILED"
    | null;
  readonly evidenceSourceCoverage: SafeJsonObject;
  readonly createdAt: string;
}

export interface NormalizedGraph {
  readonly graphId: string;
  readonly runId: string;
  readonly version: number;
  readonly tasks: readonly RunTaskProjection[];
}

export interface TypedGraphOperation {
  readonly operation: "add_node" | "add_edge" | "remove_edge";
  readonly taskId: string;
  readonly dependencyTaskId: string | null;
}

export interface PathChangeProjectionV1 {
  readonly pathChangeId: string;
  readonly sourceKind: "CORRECTION" | "REPLAN";
  readonly sourceId: string;
  readonly changeKind: "SELF_CORRECTION" | "ADD_TASK" | "CHANGE_DEPENDENCY";
  readonly status: string;
  readonly decision: string | null;
  readonly reasonCode: string | null;
  readonly taskRefs: readonly string[];
  readonly operations: readonly TypedGraphOperation[];
  readonly graphVersionBefore: number | null;
  readonly graphVersionAfter: number | null;
  readonly createdAt: string;
  readonly resolvedAt: string | null;
}

export type TerminalFailureStage =
  | "PLANNING"
  | "DATA_EVIDENCE"
  | "TASK_EXECUTION"
  | "GENERATED_CAPABILITY"
  | "FINANCIAL_REVIEW"
  | "PROOF"
  | "ARTIFACT_GENERATION"
  | "RELEASE"
  | "POST_SCHEDULER"
  | "PERSISTENCE"
  | "CANCELLATION";

export interface TerminalFailureV1 {
  readonly status: "FAILED" | "CANCELLED";
  readonly failureStage: TerminalFailureStage;
  readonly failureCode: string;
  readonly safeMessage: string | null;
}

export interface NormalizedRunLifecycle {
  readonly backendStatus: BackendRunStatus;
  readonly status: Phase4RunStatus;
  readonly stage: Phase4RunStage;
  readonly progress: RunProgress;
  readonly terminal: boolean;
  readonly terminalOutcome: "SUCCESS" | "FAILURE" | "CANCELLED" | null;
  readonly safeFailure: TerminalFailureV1 | null;
}

export interface ReviewSummary {
  readonly availability: Availability;
  readonly reviewId: string | null;
  readonly status: Phase4ReviewStatus | null;
}

export interface ResultSummary {
  readonly availability: Availability;
  readonly releasedResultId: string | null;
  readonly canonicalRecordId: string | null;
  readonly releasedAt: string | null;
}

export interface ArtifactSummary {
  readonly availability: Availability;
  readonly reportId: string | null;
  readonly representationIds: readonly string[];
}

export interface ExecutionSummary {
  readonly availability: Availability;
  readonly canonicalRecordId: string | null;
}

export interface NormalizedProofSummary {
  readonly availability: Availability;
  readonly policy: "NOT_REQUIRED" | "MUST_PROVE" | "MIXED" | "UNKNOWN";
  readonly status: Phase4ProofStatus | null;
  readonly proofRefs: readonly string[];
}

export interface NormalizedTerminalState {
  readonly isTerminal: boolean;
  readonly outcome: "SUCCESS" | "FAILURE" | "CANCELLED" | null;
  readonly eventId: string | null;
  readonly sequence: number | null;
}

export interface RunProjection {
  readonly projectionSchemaVersion: typeof RUN_PROJECTION_SCHEMA_VERSION;
  readonly projectionRevision: number;
  readonly projectionSequence: number;
  readonly generatedAt: string;
  readonly object: NormalizedObjectIdentity;
  readonly run: EmbeddedResearchRunV1;
  readonly goal: NormalizedGoal;
  readonly confirmedScheme: NormalizedScheme & Readonly<{ confirmedAt: string }>;
  readonly plannedGraph: NormalizedGraph;
  readonly actualGraph: NormalizedGraph | null;
  readonly graphVersion: number | null;
  readonly tasks: readonly RunTaskProjection[];
  readonly pathChanges: readonly PathChangeProjectionV1[];
  readonly activity: readonly SafeRuntimeActivity[];
  readonly lifecycle: NormalizedRunLifecycle;
  readonly review: ReviewSummary;
  readonly result: ResultSummary;
  readonly artifacts: ArtifactSummary;
  readonly proof: NormalizedProofSummary;
  readonly execution: ExecutionSummary;
  readonly terminal: NormalizedTerminalState;
}

export interface ReleasedFinancialMetricProjectionV1 {
  readonly runId: string;
  readonly metricId: string;
  readonly name: string;
  readonly canonicalValue: string;
  readonly canonicalUnit: string;
  readonly displayValue: string;
  readonly displayUnit: string;
  readonly period: string;
  readonly periodBasis: string;
  readonly actuality: string;
  readonly asOf: string;
  readonly currency: string | null;
  readonly formulaId: string;
  readonly capabilityId: string;
  readonly calculationId: string;
  readonly evidenceRefs: readonly string[];
  readonly claimRefs: readonly string[];
  readonly proof: Readonly<{
    policyId: string;
    requirement: "NOT_REQUIRED" | "MUST_PROVE";
    status: Phase4ProofStatus;
    proofRefs: readonly string[];
  }>;
  readonly methodMetadata: SafeJsonObject | null;
  readonly technicalPriceBasis: "ADJUSTED_CLOSE" | "RAW_CLOSE" | null;
  readonly corporateActionStatus: "NONE_DETECTED" | "RESOLVED" | "UNRESOLVED" | "UNASSESSED" | null;
  readonly corporateActionGuardRefs: readonly string[];
  readonly limitations: readonly string[];
}

export interface ReleasedClaimProjectionV1 {
  readonly claimId: string;
  readonly runId: string;
  readonly claimType: string;
  readonly statement: string;
  readonly metricId: string;
  readonly value: string;
  readonly unit: string;
  readonly period: string;
  readonly periodBasis: string;
  readonly actuality: string;
  readonly asOf: string;
  readonly currency: string | null;
  readonly calculationRefs: readonly string[];
  readonly evidenceRefs: readonly string[];
  readonly judgmentRefs: readonly string[];
}

export interface ReleasedResultProjectionV1 {
  readonly objectId: string;
  readonly runId: string;
  readonly releasedResultId: string;
  readonly canonicalRecordId: string;
  readonly releasedAt: string;
  readonly metrics: readonly ReleasedFinancialMetricProjectionV1[];
  readonly claims: readonly ReleasedClaimProjectionV1[];
  readonly materialCalculationDispositions: readonly SafeJsonObject[];
  readonly researchSourceCoverage: SafeJsonObject | null;
  readonly limitations: readonly string[];
  readonly availability: Availability;
}

export type ResultsSurfaceName =
  | "A_REPORT"
  | "B_FINANCIAL_REVIEW"
  | "C_EXECUTION_RECORD";
export type ResultsSurfaceStatus = "READY" | "PARTIAL" | "UNAVAILABLE";

export interface ResultsSurfaceAvailability {
  readonly status: ResultsSurfaceStatus;
  readonly reasonCode: string | null;
}

export interface ReviewCheckSelectorV1 {
  readonly reviewId: string;
  readonly checkCode: string;
  readonly subjectRefs: readonly string[];
}

export interface ResultsRelationRefV1 {
  readonly runId: string;
  readonly relationType: string;
  readonly status: "AVAILABLE" | "NOT_APPLICABLE" | "NOT_OBSERVED";
  readonly targetRef: string | null;
}

export interface ReportAnchorRefV1 {
  readonly runId: string;
  readonly reportId: string;
  readonly artifactId: string;
  readonly anchor: string;
}

export interface ReportContributionRefV1 {
  readonly runId: string;
  readonly reportId: string;
  readonly artifactId: string;
  readonly reportAnchor: string;
  readonly taskId: string;
  readonly actorId: string;
  readonly agentOutputId: string;
  readonly executionEventId: string | null;
  readonly calculationId: string | null;
  readonly evidenceRefs: readonly string[];
  readonly reviewId: string | null;
}

export interface ReportSurfaceV1 {
  readonly schemaVersion: "phase4.5-report-surface/v1";
  readonly runId: string;
  readonly objectId: string;
  readonly releasedResultId: string;
  readonly canonicalExecutionRecordId: string;
  readonly reportId: string;
  readonly artifactId: string;
  readonly title: string;
  readonly companyName: string;
  readonly symbol: string;
  readonly asOf: string;
  readonly sections: readonly Readonly<{
    sectionKey: string;
    title: string;
    anchor: ReportAnchorRefV1 | null;
  }>[];
  readonly anchors: readonly ReportAnchorRefV1[];
  readonly sourceContributions: readonly ReportContributionRefV1[];
  readonly availability: ResultsSurfaceAvailability;
}

export interface RendererIdentityV1 {
  readonly rendererId: string;
  readonly rendererVersion: string;
}

export interface ReportArtifactRepresentationV1 {
  readonly format: "HTML" | "PDF";
  readonly requiredForRelease: boolean;
  readonly contentType: "text/html; charset=utf-8" | "application/pdf";
  readonly availability: Availability;
  readonly artifactId: string | null;
  readonly generationAttemptCount: number;
  readonly authorizedRef: string | null;
  readonly renderer: RendererIdentityV1 | null;
}

export interface ReportArtifactGroupV1 {
  readonly schemaVersion: "phase4-report-artifacts/v1";
  readonly objectId: string;
  readonly runId: string;
  readonly reportId: string;
  readonly canonicalRecordId: string;
  readonly releasedResultId: string;
  readonly availability: Availability;
  readonly representations: readonly [ReportArtifactRepresentationV1, ReportArtifactRepresentationV1];
}

export interface FinancialReviewCheckV1 {
  readonly selector: ReviewCheckSelectorV1;
  readonly status: Phase4ReviewStatus;
  readonly safeExplanation: string | null;
  readonly inputRefs: readonly ResultsRelationRefV1[];
  readonly outputRefs: readonly ResultsRelationRefV1[];
}

export interface FinancialReviewSurfaceV1 {
  readonly schemaVersion: "phase4.5-financial-review-surface/v1";
  readonly runId: string;
  readonly objectId: string;
  readonly releasedResultId: string;
  readonly canonicalExecutionRecordId: string;
  readonly reviewId: string;
  readonly reviewer: string;
  readonly verdict: Phase4ReviewStatus;
  readonly checks: readonly FinancialReviewCheckV1[];
  readonly availability: ResultsSurfaceAvailability;
}

export interface ExecutionActorSummaryV1 {
  readonly runId: string;
  readonly actorId: string;
  readonly actorType: "RESEARCH_LEAD" | "SPECIALIST" | "SUPPORTING_EXECUTION";
  readonly displayRole: string;
  readonly status: string;
  readonly eventCount: number;
  readonly recordCount: number;
}

export interface ExecutionActorDetailV1 {
  readonly runId: string;
  readonly actorId: string;
  readonly actorType: "RESEARCH_LEAD" | "SPECIALIST" | "SUPPORTING_EXECUTION";
  readonly inputRefs: readonly Readonly<{ runId: string; refId: string }>[];
  readonly observableProcess: readonly Readonly<{
    runId: string;
    eventId: string;
    taskId: string | null;
    eventType: string;
    status: string;
  }>[];
  readonly outputs: readonly Readonly<{
    runId: string;
    outputId: string;
    taskId: string;
    status: "SUCCESS" | "FAILED";
    summary: string | null;
    keyFindings: readonly string[];
    risks: readonly string[];
    limitations: readonly string[];
  }>[];
  readonly reportContributions: readonly ReportContributionRefV1[];
  readonly quarantinedInputRefCount: number;
}

export interface ExecutionRecordSurfaceV1 {
  readonly schemaVersion: "phase4.5-execution-record-surface/v1";
  readonly runId: string;
  readonly objectId: string;
  readonly releasedResultId: string;
  readonly canonicalExecutionRecordId: string;
  readonly actors: readonly ExecutionActorSummaryV1[];
  readonly actorDetails: readonly ExecutionActorDetailV1[];
  readonly availability: ResultsSurfaceAvailability;
}

export interface CrossViewEndpointV1 {
  readonly surface: ResultsSurfaceName;
  readonly runId: string;
  readonly identityId: string;
  readonly artifactId: string | null;
  readonly targetAnchor: string | null;
  readonly checkSelector: ReviewCheckSelectorV1 | null;
}

export interface CrossViewRefV1 {
  readonly runId: string;
  readonly source: CrossViewEndpointV1;
  readonly target: CrossViewEndpointV1;
  readonly status: "AVAILABLE" | "UNAVAILABLE" | "NOT_APPLICABLE";
  readonly reasonCode: string | null;
}

export interface ResultsSurfaceRefV1 {
  readonly surface: ResultsSurfaceName;
  readonly runId: string;
  readonly objectId: string;
  readonly releasedResultId: string;
  readonly canonicalExecutionRecordId: string;
  readonly surfaceId: string;
  readonly href: string;
  readonly availability: ResultsSurfaceAvailability;
}

export interface ResultsWorkspaceV1 {
  readonly schemaVersion: "phase4.5-results-workspace/v1";
  readonly runId: string;
  readonly objectId: string;
  readonly asOf: string;
  readonly runStatus: BackendRunStatus;
  readonly releasedResultId: string;
  readonly canonicalExecutionRecordId: string;
  readonly reportSurface: ResultsSurfaceRefV1;
  readonly reviewSurface: ResultsSurfaceRefV1;
  readonly executionSurface: ResultsSurfaceRefV1;
  readonly crossViewRefs: readonly CrossViewRefV1[];
}

export interface ConfirmAdmissionExpectation {
  readonly objectId: string;
  readonly draftId: string;
  readonly draftVersion: number;
  readonly draftHash: string;
  readonly goalId?: string;
  readonly schemeId?: string;
}

export class ContractDecodeError extends Error {
  readonly name = "ContractDecodeError";

  constructor(readonly path: string, message: string) {
    super(`${path}: ${message}`);
  }
}

export const RUN_STATUS_MAP: Readonly<
  Record<
    BackendRunStatus,
    Readonly<{ status: Phase4RunStatus; stage: Phase4RunStage; terminal: boolean }>
  >
> = Object.freeze({
  DRAFT: { status: "PREPARING", stage: "PREPARE", terminal: false },
  SCHEME_GENERATING: { status: "PREPARING", stage: "PREPARE", terminal: false },
  AWAITING_CONFIRMATION: { status: "AWAITING_CONFIRMATION", stage: "CONFIRM", terminal: false },
  PLANNING: { status: "PLANNING", stage: "PLANNING", terminal: false },
  RUNNING: { status: "RESEARCHING", stage: "RESEARCH", terminal: false },
  REVIEW: { status: "REVIEWING", stage: "REVIEW", terminal: false },
  PROVING: { status: "PROVING", stage: "PROVING", terminal: false },
  RELEASED: { status: "COMPLETED", stage: "COMPLETE", terminal: true },
  FAILED: { status: "FAILED", stage: "FAILED", terminal: true },
  CANCELLED: { status: "CANCELLED", stage: "CANCELLED", terminal: true }
});

export const TASK_STATUS_MAP: Readonly<
  Record<BackendTaskStatus, Readonly<{ status: Phase4TaskStatus; terminal: boolean }>>
> = Object.freeze({
  CREATED: { status: "QUEUED", terminal: false },
  WAITING: { status: "QUEUED", terminal: false },
  READY: { status: "READY", terminal: false },
  RUNNING: { status: "ACTIVE", terminal: false },
  WAITING_FOR_CAPABILITY: { status: "WAITING_SUPPORT", terminal: false },
  SELF_CORRECTING: { status: "CORRECTING", terminal: false },
  BLOCKED: { status: "BLOCKED", terminal: false },
  REVIEW: { status: "REVIEW", terminal: false },
  COMPLETED: { status: "COMPLETE", terminal: true },
  FAILED: { status: "FAILED", terminal: true },
  CAPABILITY_BUILD_FAILED: { status: "FAILED", terminal: true },
  CANCELLED: { status: "CANCELLED", terminal: true }
});

type UnknownObject = Record<string, unknown>;
type Decoder<T> = (value: unknown, path: string) => T;

const RFC3339_UTC =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?Z$/u;
const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/u;
const SHA256 = /^sha256:[0-9a-f]{64}$/u;
const DECIMAL_STRING = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/u;
const SAFE_TEXT_CONTROL = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u;
const BEARER_VALUE = /\bauthorization\s*:\s*bearer\s+\S+/iu;
const SECRET_ASSIGNMENT =
  /\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password)\s*[:=]\s*\S+/iu;
const COMMON_CREDENTIAL_VALUE =
  /(?:\bsk-[a-z0-9_-]{16,}|\bsk_(?:live|test)_[a-z0-9]{16,}|\bgh[pousr]_[a-z0-9]{20,}|\bgithub_pat_[a-z0-9_]{20,}|\bglpat-[a-z0-9_-]{16,}|\bhf_[a-z0-9]{20,}|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{20,}|\bxox[baprs]-[0-9A-Za-z-]{16,}|\beyJ[0-9A-Za-z_-]{5,}\.[0-9A-Za-z_-]{5,}\.[0-9A-Za-z_-]{5,}\b)/iu;
const INTERNAL_LOCATOR = /(?:artifact|blob|file|gs|postgres|postgresql|s3|sqlite):\/\//iu;
const INTERNAL_PATH = /(?:^|[\s"'(=])(?:\/[Uu]sers\/|\/home\/|\/private\/|\/tmp\/|\/var\/|[a-z]:[\\/]|\.\.[\\/])/u;
const GENERIC_SAFE_JSON_LIMITS = Object.freeze({
  maxDepth: 16,
  maxItems: 10_000,
  maxStringLength: 65_536
});
const ERROR_DETAIL_LIMITS = Object.freeze({ maxDepth: 4, maxItems: 100, maxStringLength: 512 });

function fail(path: string, message: string): never {
  throw new ContractDecodeError(path, message);
}

function hasOwn(value: UnknownObject, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function field(value: UnknownObject, key: string, path: string): unknown {
  if (!hasOwn(value, key)) fail(`${path}.${key}`, "missing required field");
  return value[key];
}

function assertOnlyKeys(value: UnknownObject, keys: readonly string[], path: string): void {
  const allowed = new Set(keys);
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) fail(`${path}.${key}`, "unknown field");
  }
}

function freezeDeep<T>(value: T): Readonly<T> {
  if (typeof value !== "object" || value === null || Object.isFrozen(value)) return value;
  for (const nested of Object.values(value as Record<string, unknown>)) freezeDeep(nested);
  return Object.freeze(value);
}

export function decodeObject(value: unknown, path = "$" ): UnknownObject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return fail(path, "expected object");
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    return fail(path, "expected a plain JSON object");
  }
  return value as UnknownObject;
}

export function decodeArray(value: unknown, path = "$" ): readonly unknown[] {
  if (!Array.isArray(value)) return fail(path, "expected array");
  return value;
}

export function decodeNullable<T>(
  value: unknown,
  decoder: Decoder<T>,
  path = "$"
): T | null {
  return value === null ? null : decoder(value, path);
}

export function decodeEnum<const T extends string>(
  value: unknown,
  values: readonly T[],
  path = "$"
): T {
  if (typeof value !== "string" || !values.includes(value as T)) {
    return fail(path, `expected one of ${values.join(" | ")}`);
  }
  return value as T;
}

export function decodeNonBlankString(value: unknown, path = "$" ): string {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.trim() !== value ||
    /[\u0000-\u001f\u007f]/u.test(value)
  ) {
    return fail(path, "expected non-blank string without surrounding whitespace or controls");
  }
  return value;
}

/**
 * Validate human-facing public text without trimming or rewriting it. Normal
 * tab/newline/carriage-return characters are allowed; secret/internal shapes
 * and other controls fail closed.
 */
export function decodePublicText(
  value: unknown,
  path = "$",
  allowEmpty = false,
  maxLength = 65_536
): string {
  if (typeof value !== "string" || (!allowEmpty && value.trim().length === 0)) {
    return fail(path, allowEmpty ? "expected string" : "expected non-blank public text");
  }
  if (value.length > maxLength) return fail(path, `public text exceeds ${maxLength} characters`);
  const lower = value.toLowerCase();
  if (
    SAFE_TEXT_CONTROL.test(value) ||
    INTERNAL_LOCATOR.test(value) ||
    INTERNAL_PATH.test(value) ||
    lower.includes("-----begin private key-----") ||
    lower.includes("traceback (most recent call last)") ||
    BEARER_VALUE.test(value) ||
    SECRET_ASSIGNMENT.test(value) ||
    COMMON_CREDENTIAL_VALUE.test(value)
  ) {
    return fail(path, "text resembles protected internal or secret-bearing content");
  }
  return value;
}

export function decodeOpaqueId(value: unknown, path = "$" ): string {
  const id = decodeNonBlankString(value, path);
  if (id.length > 1024) return fail(path, "opaque identifier exceeds 1024 characters");
  return id;
}

function decodeNullableOpaqueId(value: unknown, path: string): string | null {
  return decodeNullable(value, decodeOpaqueId, path);
}

function decodeBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") return fail(path, "expected boolean");
  return value;
}

function decodeFiniteNumber(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fail(path, "expected finite number");
  }
  return value;
}

function decodeInteger(value: unknown, minimum: number, path: string): number {
  const decoded = decodeFiniteNumber(value, path);
  if (!Number.isSafeInteger(decoded) || decoded < minimum) {
    return fail(path, `expected safe integer >= ${minimum}`);
  }
  return decoded;
}

function decodeRatio(value: unknown, path: string): number {
  const decoded = decodeFiniteNumber(value, path);
  if (decoded < 0 || decoded > 1) return fail(path, "expected number in inclusive range 0..1");
  return decoded;
}

function validCalendarDate(year: number, month: number, day: number): boolean {
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

export function decodeDate(value: unknown, path = "$" ): string {
  if (typeof value !== "string") return fail(path, "expected YYYY-MM-DD date string");
  const match = DATE_ONLY.exec(value);
  if (match === null) return fail(path, "expected YYYY-MM-DD date string");
  if (!validCalendarDate(Number(match[1]), Number(match[2]), Number(match[3]))) {
    return fail(path, "invalid calendar date");
  }
  return value;
}

export function decodeRfc3339Utc(value: unknown, path = "$" ): string {
  if (typeof value !== "string") return fail(path, "expected RFC3339 UTC timestamp");
  const match = RFC3339_UTC.exec(value);
  if (match === null) return fail(path, "expected RFC3339 UTC timestamp ending in Z");
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  if (
    !validCalendarDate(year, month, day) ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    Number.isNaN(Date.parse(value))
  ) {
    return fail(path, "invalid RFC3339 UTC timestamp");
  }
  return value;
}

export function decodeSha256(value: unknown, path = "$" ): string {
  if (typeof value !== "string" || !SHA256.test(value)) {
    return fail(path, "expected sha256:<64 lowercase hex>");
  }
  return value;
}

/** Decimal contract values stay strings. This helper never accepts a JS number. */
export function decodeDecimalString(value: unknown, path = "$" ): string {
  if (typeof value !== "string" || !DECIMAL_STRING.test(value)) {
    return fail(path, "expected canonical Decimal string");
  }
  return value;
}

function normalizedSafeJsonKey(key: string): string {
  return key
    .replace(/(?<=[a-z0-9])(?=[A-Z])/gu, "_")
    .toLowerCase()
    .replace(/[^a-z0-9]+/gu, "_")
    .replace(/^_+|_+$/gu, "");
}

function safeJsonKey(key: string, path: string): void {
  const normalized = normalizedSafeJsonKey(key);
  const compact = normalized.replace(/_/gu, "");
  const parts = new Set(normalized.split("_").filter(Boolean));
  const protectedExact = new Set([
    "authorization",
    "cookie",
    "set_cookie",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "id_token",
    "auth_token",
    "api_token",
    "provider_token",
    "session_token",
    "bearer_token",
    "password",
    "passwd",
    "secret",
    "secrets",
    "client_secret",
    "private_key",
    "credentials",
    "credential",
    "path",
    "file_path",
    "filepath",
    "directory",
    "working_directory",
    "cwd",
    "home_directory",
    "temp_path",
    "source_locator",
    "storage_locator",
    "internal_ref",
    "internal_reference",
    "artifact_ref",
    "receipt_artifact_ref",
    "raw_artifact_ref",
    "source_ref",
    "storage_ref",
    "blob_ref",
    "file_ref",
    "receipt_ref",
    "proof_input_ref",
    "prompt",
    "prompts",
    "system_prompt",
    "user_prompt",
    "developer_prompt",
    "prompt_template",
    "messages",
    "chat_messages",
    "conversation",
    "chain_of_thought",
    "chainofthought",
    "cot",
    "scratchpad",
    "model_scratch",
    "hidden_reasoning",
    "reasoning",
    "reasoning_trace",
    "thought",
    "analysis_trace",
    "thoughts",
    "raw_provider",
    "raw_provider_payload",
    "provider_payload",
    "provider_body",
    "provider_request",
    "provider_response",
    "raw_payload",
    "raw_response",
    "response_body",
    "request_body",
    "sql",
    "sql_query",
    "stack",
    "stack_trace",
    "stacktrace",
    "traceback",
    "exception_detail"
  ]);
  const rawCarrier = parts.has("raw") &&
    ["provider", "payload", "response", "body", "artifact"].some((part) => parts.has(part));
  if (
    key === "__proto__" ||
    key === "prototype" ||
    key === "constructor" ||
    protectedExact.has(normalized) ||
    compact.includes("secret") ||
    compact.includes("password") ||
    compact.includes("passwd") ||
    compact.includes("credential") ||
    compact.includes("apikey") ||
    compact.includes("accesstoken") ||
    compact.includes("refreshtoken") ||
    compact.includes("prompt") ||
    compact.includes("chainofthought") ||
    compact === "cot" ||
    compact.includes("hiddenreasoning") ||
    compact.includes("reasoningtrace") ||
    compact.includes("scratch") ||
    compact.includes("locator") ||
    rawCarrier ||
    (parts.has("internal") && ["ref", "reference", "path", "locator"].some((part) => parts.has(part))) ||
    (parts.has("path") && normalized !== "path_change_id" && normalized !== "path_changes")
  ) {
    fail(`${path}.${key}`, "forbidden or secret-bearing JSON member");
  }
}

interface SafeJsonBudget {
  count: number;
  readonly active: WeakSet<object>;
}

interface SafeJsonLimits {
  readonly maxDepth: number;
  readonly maxItems: number;
  readonly maxStringLength: number;
}

function consumeSafeJsonBudget(budget: SafeJsonBudget, limits: SafeJsonLimits, path: string): void {
  budget.count += 1;
  if (budget.count > limits.maxItems) fail(path, "safe JSON exceeds maximum item count");
}

function decodeSafeJsonValue(
  value: unknown,
  path: string,
  depth: number,
  budget: SafeJsonBudget,
  limits: SafeJsonLimits
): SafeJsonValue {
  if (depth > limits.maxDepth) return fail(path, "safe JSON exceeds maximum nesting depth");
  consumeSafeJsonBudget(budget, limits, path);
  if (value === null) return null;
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    return decodePublicText(value, path, true, limits.maxStringLength);
  }
  if (typeof value === "number") return decodeFiniteNumber(value, path);
  if (Array.isArray(value)) {
    if (budget.active.has(value)) return fail(path, "recursive JSON array");
    budget.active.add(value);
    try {
      return freezeDeep(
        value.map((item, index) =>
          decodeSafeJsonValue(item, `${path}[${index}]`, depth + 1, budget, limits)
        )
      );
    } finally {
      budget.active.delete(value);
    }
  }
  const input = decodeObject(value, path);
  if (budget.active.has(input)) return fail(path, "recursive JSON object");
  budget.active.add(input);
  try {
    const output: Record<string, SafeJsonValue> = {};
    for (const [key, item] of Object.entries(input)) {
      safeJsonKey(key, path);
      output[key] = decodeSafeJsonValue(item, `${path}.${key}`, depth + 1, budget, limits);
    }
    return freezeDeep(output);
  } finally {
    budget.active.delete(input);
  }
}

export function decodeSafeJsonObject(value: unknown, path = "$" ): SafeJsonObject {
  const input = decodeObject(value, path);
  const decoded = decodeSafeJsonValue(
    input,
    path,
    0,
    { count: 0, active: new WeakSet<object>() },
    GENERIC_SAFE_JSON_LIMITS
  );
  return decoded as SafeJsonObject;
}

function decodeStringArray(value: unknown, path: string): readonly string[] {
  const input = decodeArray(value, path);
  const output = input.map((item, index) => decodeNonBlankString(item, `${path}[${index}]`));
  if (new Set(output).size !== output.length) return fail(path, "duplicate values are not allowed");
  return freezeDeep(output);
}

function decodePublicTextArray(value: unknown, path: string): readonly string[] {
  return freezeDeep(
    decodeArray(value, path).map((item, index) =>
      decodePublicText(item, `${path}[${index}]`)
    )
  );
}

const AVAILABILITY_VALUES = [
  "PENDING",
  "AVAILABLE",
  "NOT_GENERATED",
  "NOT_RELEASED",
  "UNAVAILABLE",
  "FAILED"
] as const;

export function decodeAvailability(value: unknown, path = "$" ): Availability {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["status", "reason_code", "retryable"], path);
  const status = decodeEnum(field(input, "status", path), AVAILABILITY_VALUES, `${path}.status`);
  const rawReason = field(input, "reason_code", path);
  const reasonCode = rawReason === null ? null : decodeNonBlankString(rawReason, `${path}.reason_code`);
  const retryable = decodeBoolean(field(input, "retryable", path), `${path}.retryable`);
  if (status === "AVAILABLE" && reasonCode !== null) {
    return fail(`${path}.reason_code`, "AVAILABLE requires null reason_code");
  }
  if (status !== "AVAILABLE" && reasonCode === null) {
    return fail(`${path}.reason_code`, "non-AVAILABLE status requires a stable reason_code");
  }
  return freezeDeep({ status, reasonCode, retryable });
}

const ERROR_PROTOCOL: Readonly<Record<ErrorCode, Readonly<{ retryable: boolean; recovery: ErrorRecovery }>>> =
  Object.freeze({
    INVALID_CURSOR: { retryable: false, recovery: "SNAPSHOT_RELOAD" },
    UNAUTHENTICATED: { retryable: false, recovery: "REAUTHENTICATE" },
    FORBIDDEN: { retryable: false, recovery: "NONE" },
    NOT_FOUND: { retryable: false, recovery: "NONE" },
    IDENTITY_MISMATCH: { retryable: false, recovery: "NONE" },
    UNAVAILABLE: { retryable: false, recovery: "NONE" },
    NOT_GENERATED: { retryable: false, recovery: "NONE" },
    NOT_RELEASED: { retryable: false, recovery: "SNAPSHOT_RELOAD" },
    CONFLICT: { retryable: false, recovery: "NONE" },
    CURSOR_AHEAD: { retryable: false, recovery: "SNAPSHOT_RELOAD" },
    SCHEMA_INCOMPATIBLE: { retryable: false, recovery: "NONE" },
    UNSUPPORTED_EVENT: { retryable: false, recovery: "SNAPSHOT_RELOAD" },
    TERMINAL: { retryable: false, recovery: "NONE" },
    REQUEST_VALIDATION_ERROR: { retryable: false, recovery: "NONE" },
    INTEGRITY_FAILURE: { retryable: false, recovery: "SNAPSHOT_RELOAD" },
    INTERNAL_ERROR: { retryable: false, recovery: "NONE" },
    TRANSIENT_BACKEND_ERROR: { retryable: true, recovery: "RETRY" }
  });

const ERROR_CODES = Object.freeze(Object.keys(ERROR_PROTOCOL) as ErrorCode[]);
const ERROR_RECOVERIES = ["NONE", "RETRY", "SNAPSHOT_RELOAD", "REAUTHENTICATE"] as const;

function decodeErrorDetails(value: unknown, path: string): SafeJsonObject {
  const input = decodeObject(value, path);
  return decodeSafeJsonValue(
    input,
    path,
    0,
    { count: 0, active: new WeakSet<object>() },
    ERROR_DETAIL_LIMITS
  ) as SafeJsonObject;
}

export function decodeErrorEnvelope(value: unknown): ErrorEnvelope {
  const path = "$";
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["schema_version", "error"], path);
  if (field(input, "schema_version", path) !== ERROR_SCHEMA_VERSION) {
    return fail("$.schema_version", `unsupported error schema; expected ${ERROR_SCHEMA_VERSION}`);
  }
  const rawError = decodeObject(field(input, "error", path), "$.error");
  assertOnlyKeys(
    rawError,
    ["code", "message", "retryable", "recovery", "request_id", "resource", "details"],
    "$.error"
  );
  const code = decodeEnum(field(rawError, "code", "$.error"), ERROR_CODES, "$.error.code");
  const retryable = decodeBoolean(field(rawError, "retryable", "$.error"), "$.error.retryable");
  const recovery = decodeEnum(
    field(rawError, "recovery", "$.error"),
    ERROR_RECOVERIES,
    "$.error.recovery"
  );
  const protocol = ERROR_PROTOCOL[code];
  if (retryable !== protocol.retryable || recovery !== protocol.recovery) {
    return fail("$.error", `retry/recovery tuple contradicts ${code}`);
  }
  const rawResource = field(rawError, "resource", "$.error");
  let resource: Readonly<{ type: ErrorResourceType; id: string }> | null = null;
  if (rawResource !== null) {
    const decoded = decodeObject(rawResource, "$.error.resource");
    assertOnlyKeys(decoded, ["type", "id"], "$.error.resource");
    resource = freezeDeep({
      type: decodeNonBlankString(
        field(decoded, "type", "$.error.resource"),
        "$.error.resource.type"
      ),
      id: decodeOpaqueId(field(decoded, "id", "$.error.resource"), "$.error.resource.id")
    });
  }
  return freezeDeep({
    schemaVersion: ERROR_SCHEMA_VERSION,
    error: {
      code,
      message: decodePublicText(
        field(rawError, "message", "$.error"),
        "$.error.message",
        false,
        4_096
      ),
      retryable,
      recovery,
      requestId: decodeNullableOpaqueId(field(rawError, "request_id", "$.error"), "$.error.request_id"),
      resource,
      details: decodeErrorDetails(field(rawError, "details", "$.error"), "$.error.details")
    }
  });
}

function decodeObjectIdentity(value: unknown, path: string): NormalizedObjectIdentity {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    [
      "object_id",
      "symbol",
      "company_name",
      "object_type",
      "exchange",
      "sector",
      "currency",
      "identity_version"
    ],
    path
  );
  const rawSector = field(input, "sector", path);
  return freezeDeep({
    objectId: decodeOpaqueId(field(input, "object_id", path), `${path}.object_id`),
    symbol: decodeNonBlankString(field(input, "symbol", path), `${path}.symbol`),
    companyName: decodePublicText(field(input, "company_name", path), `${path}.company_name`),
    objectType: decodeNonBlankString(field(input, "object_type", path), `${path}.object_type`),
    exchange: decodeNonBlankString(field(input, "exchange", path), `${path}.exchange`),
    sector:
      rawSector === null
        ? null
        : decodePublicText(rawSector, `${path}.sector`),
    currency: decodeNonBlankString(field(input, "currency", path), `${path}.currency`),
    identityVersion: decodeInteger(field(input, "identity_version", path), 1, `${path}.identity_version`)
  });
}

function decodeGoal(value: unknown, path: string): NormalizedGoal {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    [
      "goal_id",
      "research_object_id",
      "goal_type",
      "goal_text",
      "as_of",
      "preferences",
      "created_at"
    ],
    path
  );
  return freezeDeep({
    goalId: decodeOpaqueId(field(input, "goal_id", path), `${path}.goal_id`),
    researchObjectId: decodeOpaqueId(
      field(input, "research_object_id", path),
      `${path}.research_object_id`
    ),
    goalType: decodeNonBlankString(field(input, "goal_type", path), `${path}.goal_type`),
    goalText: decodePublicText(field(input, "goal_text", path), `${path}.goal_text`),
    asOf: decodeDate(field(input, "as_of", path), `${path}.as_of`),
    preferences: decodeSafeJsonObject(field(input, "preferences", path), `${path}.preferences`),
    createdAt: decodeRfc3339Utc(field(input, "created_at", path), `${path}.created_at`)
  });
}

export function decodeIncrementalContext(value: unknown, objectId: string): import("./incremental").IncrementalContext {
  const fail = () => {throw new Error("Incremental context identity mismatch");};
  const exact = (x: Record<string, unknown>, names: string[]) => {
    if(Object.keys(x).length!==names.length || names.some(n=>!Object.hasOwn(x,n))) fail();
  };
  const x=decodeObject(decodeSafeJsonObject(value));
  exact(x,["research_object_id","base_run_id","base_research_view_version","base_version_number","base_as_of","target_as_of","decisions",...(Object.hasOwn(x,"prior_summary")?["prior_summary"]:[])]);
  if(Object.hasOwn(x,"prior_summary")) decodePublicText(x.prior_summary);
  for(const k of ["research_object_id","base_run_id","base_research_view_version"]) decodeOpaqueId(x[k]);
  if(x.research_object_id!==objectId || typeof x.base_version_number!=="number" || !Number.isSafeInteger(x.base_version_number) || x.base_version_number<1) fail();
  for(const k of ["base_as_of","target_as_of"]) if(typeof x[k]!=="string" || !/^\d{4}-\d{2}-\d{2}$/.test(x[k] as string)) fail();
  if(String(x.target_as_of)<String(x.base_as_of)) fail();
  const decisions=decodeArray(x.decisions);
  if(decisions.length>32) fail();
  const policy: Record<string,readonly string[]>={VIEW_CONTEXT:["REUSE","UNKNOWN"],VERIFIED_METRIC:["REFRESH","REVALIDATE","UNKNOWN"],VERIFIED_CLAIM:["REFRESH","REVALIDATE","UNKNOWN"],RESOLVED_ISSUE:["PREVENT","UNKNOWN"]};
  const seen=new Set<string>();
  for(const value of decisions) {
    const d=decodeObject(value);
    exact(d,["decision","source_run_id","source_identity","category","statement","reason","authority"]);
    decodeOpaqueId(d.source_identity);decodePublicText(d.statement);decodePublicText(d.reason);
    if(d.source_run_id!==x.base_run_id || !Object.hasOwn(policy,String(d.category)) || !policy[String(d.category)].includes(String(d.decision)) || d.authority!=="phase5b-exact-memory-policy/v1") fail();
    if(d.category==="VIEW_CONTEXT" && d.source_identity!==x.base_research_view_version) fail();
    const key=String(d.source_identity);if(seen.has(key)) fail();seen.add(key);Object.freeze(d);
  }
  Object.freeze(decisions);return Object.freeze(x) as unknown as import("./incremental").IncrementalContext;
}

function decodeScheme(value: unknown, path: string): NormalizedScheme {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    [
      "scheme_id",
      "incremental_context",
      "research_object_id",
      "goal_id",
      "research_scope",
      "data_requirements",
      "agent_requirements",
      "skill_requirements",
      "calculation_requirements",
      "assurance_requirements",
      "report_requirements",
      "limitations",
      "generated_by",
      "generated_model",
      "created_at",
      "confirmed_at"
    ],
    path
  );
  const rawGeneratedModel = field(input, "generated_model", path);
  const rawConfirmedAt = field(input, "confirmed_at", path);
  return freezeDeep({
    schemeId: decodeOpaqueId(field(input, "scheme_id", path), `${path}.scheme_id`),
    ...(input.incremental_context === undefined ? {} : {incrementalContext: decodeIncrementalContext(input.incremental_context, decodeOpaqueId(input.research_object_id))}),
    researchObjectId: decodeOpaqueId(
      field(input, "research_object_id", path),
      `${path}.research_object_id`
    ),
    goalId: decodeOpaqueId(field(input, "goal_id", path), `${path}.goal_id`),
    researchScope: decodePublicTextArray(
      field(input, "research_scope", path),
      `${path}.research_scope`
    ),
    dataRequirements: decodePublicTextArray(
      field(input, "data_requirements", path),
      `${path}.data_requirements`
    ),
    agentRequirements: decodePublicTextArray(
      field(input, "agent_requirements", path),
      `${path}.agent_requirements`
    ),
    skillRequirements: decodePublicTextArray(
      field(input, "skill_requirements", path),
      `${path}.skill_requirements`
    ),
    calculationRequirements: decodePublicTextArray(
      field(input, "calculation_requirements", path),
      `${path}.calculation_requirements`
    ),
    assuranceRequirements: decodeSafeJsonObject(
      field(input, "assurance_requirements", path),
      `${path}.assurance_requirements`
    ),
    reportRequirements: decodePublicTextArray(
      field(input, "report_requirements", path),
      `${path}.report_requirements`
    ),
    limitations: decodePublicTextArray(field(input, "limitations", path), `${path}.limitations`),
    generatedBy: decodeNonBlankString(field(input, "generated_by", path), `${path}.generated_by`),
    generatedModel:
      rawGeneratedModel === null
        ? null
        : decodeNonBlankString(rawGeneratedModel, `${path}.generated_model`),
    createdAt: decodeRfc3339Utc(field(input, "created_at", path), `${path}.created_at`),
    confirmedAt:
      rawConfirmedAt === null
        ? null
        : decodeRfc3339Utc(rawConfirmedAt, `${path}.confirmed_at`)
  });
}

const ACTIVITY_OPTIONAL_KEYS = [
  "status",
  "actor_id",
  "actor_type",
  "duration_ms",
  "input_refs",
  "output_refs",
  "evidence_refs",
  "calculation_refs",
  "claim_refs",
  "judgment_refs",
  "review_refs",
  "proof_refs",
  "artifact_refs",
  "trace_bundle_refs"
] as const;

function decodeOptionalString(value: unknown, path: string): string | null {
  return value === null ? null : decodeNonBlankString(value, path);
}

function decodeActivity(value: unknown, path: string): SafeRuntimeActivity {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    ["event_id", "type", "sequence", "timestamp", "task_id", "message_code", ...ACTIVITY_OPTIONAL_KEYS],
    path
  );
  const output: {
    eventId: string;
    type: string;
    sequence: number;
    timestamp: string;
    taskId: string | null;
    messageCode: string;
    status?: string | null;
    actorId?: string | null;
    actorType?: string | null;
    durationMs?: number | null;
    inputRefs?: readonly string[];
    outputRefs?: readonly string[];
    evidenceRefs?: readonly string[];
    calculationRefs?: readonly string[];
    claimRefs?: readonly string[];
    judgmentRefs?: readonly string[];
    reviewRefs?: readonly string[];
    proofRefs?: readonly string[];
    artifactRefs?: readonly string[];
    traceBundleRefs?: readonly string[];
  } = {
    eventId: decodeOpaqueId(field(input, "event_id", path), `${path}.event_id`),
    type: decodeNonBlankString(field(input, "type", path), `${path}.type`),
    sequence: decodeInteger(field(input, "sequence", path), 1, `${path}.sequence`),
    timestamp: decodeRfc3339Utc(field(input, "timestamp", path), `${path}.timestamp`),
    taskId: decodeNullableOpaqueId(field(input, "task_id", path), `${path}.task_id`),
    messageCode: decodeNonBlankString(field(input, "message_code", path), `${path}.message_code`)
  };
  const optionalStringKeys = ["status", "actor_id", "actor_type"] as const;
  const optionalStringOutputs = ["status", "actorId", "actorType"] as const;
  optionalStringKeys.forEach((key, index) => {
    if (hasOwn(input, key)) {
      output[optionalStringOutputs[index]] = decodeOptionalString(input[key], `${path}.${key}`);
    }
  });
  if (hasOwn(input, "duration_ms")) {
    output.durationMs =
      input.duration_ms === null
        ? null
        : decodeInteger(input.duration_ms, 0, `${path}.duration_ms`);
  }
  const refKeys = [
    "input_refs",
    "output_refs",
    "evidence_refs",
    "calculation_refs",
    "claim_refs",
    "judgment_refs",
    "review_refs",
    "proof_refs",
    "artifact_refs",
    "trace_bundle_refs"
  ] as const;
  const refOutputs = [
    "inputRefs",
    "outputRefs",
    "evidenceRefs",
    "calculationRefs",
    "claimRefs",
    "judgmentRefs",
    "reviewRefs",
    "proofRefs",
    "artifactRefs",
    "traceBundleRefs"
  ] as const;
  refKeys.forEach((key, index) => {
    if (hasOwn(input, key)) output[refOutputs[index]] = decodeStringArray(input[key], `${path}.${key}`);
  });
  return freezeDeep(output);
}

function decodeRunCollectionActivity(value: unknown, path: string): RunCollectionActivity {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    ["event_id", "type", "sequence", "timestamp", "task_id", "message_code"],
    path
  );
  return freezeDeep({
    eventId: decodeOpaqueId(field(input, "event_id", path), `${path}.event_id`),
    type: decodeNonBlankString(field(input, "type", path), `${path}.type`),
    sequence: decodeInteger(field(input, "sequence", path), 1, `${path}.sequence`),
    timestamp: decodeRfc3339Utc(field(input, "timestamp", path), `${path}.timestamp`),
    taskId: decodeNullableOpaqueId(field(input, "task_id", path), `${path}.task_id`),
    messageCode: decodeNonBlankString(
      field(input, "message_code", path),
      `${path}.message_code`
    )
  });
}

function decodeResearchObjectDetailAt(value: unknown, path: string): Phase4ResearchObjectDetail {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    [
      "object",
      "latest_released_run_id",
      "released_result_availability",
      "run_count",
      "last_activity",
      "created_at",
      "updated_at"
    ],
    path
  );
  const rawActivity = field(input, "last_activity", path);
  const detail: Phase4ResearchObjectDetail = {
    object: decodeObjectIdentity(field(input, "object", path), `${path}.object`),
    latestReleasedRunId: decodeNullableOpaqueId(
      field(input, "latest_released_run_id", path),
      `${path}.latest_released_run_id`
    ),
    releasedResultAvailability: decodeAvailability(
      field(input, "released_result_availability", path),
      `${path}.released_result_availability`
    ),
    runCount: decodeInteger(field(input, "run_count", path), 0, `${path}.run_count`),
    lastActivity: rawActivity === null ? null : decodeActivity(rawActivity, `${path}.last_activity`),
    createdAt: decodeRfc3339Utc(field(input, "created_at", path), `${path}.created_at`),
    updatedAt: decodeRfc3339Utc(field(input, "updated_at", path), `${path}.updated_at`)
  };
  const releasePairCloses = detail.latestReleasedRunId === null
    ? ((detail.releasedResultAvailability.status === "NOT_GENERATED" &&
      detail.releasedResultAvailability.reasonCode === "MEMORY_NOT_MATERIALIZED" &&
      detail.releasedResultAvailability.retryable === false) ||
      (detail.releasedResultAvailability.status === "NOT_RELEASED" &&
      detail.releasedResultAvailability.reasonCode === "NO_RELEASED_RUN" &&
      detail.releasedResultAvailability.retryable === false) ||
      (detail.runCount > 0 && detail.releasedResultAvailability.status === "UNAVAILABLE" &&
       detail.releasedResultAvailability.reasonCode === "RELEASED_RUN_LATEST_UNAVAILABLE" &&
       detail.releasedResultAvailability.retryable === false))
    : detail.releasedResultAvailability.status === "AVAILABLE" &&
      detail.releasedResultAvailability.reasonCode === null &&
      detail.releasedResultAvailability.retryable === false;
  if (!releasePairCloses) {
    return fail(
      `${path}.released_result_availability`,
      "released result availability must close exactly to latest_released_run_id"
    );
  }
  return freezeDeep(detail);
}

export function decodeResearchObjectDetail(
  value: unknown,
  expectedObjectId?: string
): Phase4ResearchObjectDetail {
  const detail = decodeResearchObjectDetailAt(value, "$" );
  if (expectedObjectId !== undefined && detail.object.objectId !== decodeOpaqueId(expectedObjectId, "expectedObjectId")) {
    return fail("$.object.object_id", "response belongs to another Research Object");
  }
  return detail;
}

export function decodeResearchObjectCollection(value: unknown): ResearchObjectCollection {
  const input = decodeObject(value, "$" );
  assertOnlyKeys(input, ["items", "next_cursor"], "$" );
  const items = decodeArray(field(input, "items", "$" ), "$.items").map((item, index) =>
    decodeResearchObjectDetailAt(item, `$.items[${index}]`)
  );
  const identities = items.map((item) => item.object.objectId);
  if (new Set(identities).size !== identities.length) return fail("$.items", "duplicate Object identity");
  return freezeDeep({
    items,
    nextCursor: decodeNullableOpaqueId(field(input, "next_cursor", "$" ), "$.next_cursor")
  });
}

export function decodePreparedResearchDraft(
  value: unknown,
  expectedObjectId?: string
): PreparedResearchDraft {
  const input = decodeObject(value, "$" );
  assertOnlyKeys(
    input,
    [
      "schema_version",
      "draft_id",
      "draft_version",
      "status",
      "preview_kind",
      "planned_graph_availability",
      "object_id",
      "goal",
      "scheme_snapshot",
      "prepare_request_hash",
      "draft_hash",
      "created_at",
      "expires_at"
    ],
    "$"
  );
  if (field(input, "schema_version", "$" ) !== RUN_DRAFT_SCHEMA_VERSION) {
    return fail("$.schema_version", `unsupported draft schema; expected ${RUN_DRAFT_SCHEMA_VERSION}`);
  }
  if (field(input, "status", "$" ) !== "AWAITING_CONFIRMATION") {
    return fail("$.status", "expected AWAITING_CONFIRMATION");
  }
  if (field(input, "preview_kind", "$" ) !== "SCHEME_ONLY") {
    return fail("$.preview_kind", "expected SCHEME_ONLY");
  }
  const objectId = decodeOpaqueId(field(input, "object_id", "$" ), "$.object_id");
  if (expectedObjectId !== undefined && objectId !== decodeOpaqueId(expectedObjectId, "expectedObjectId")) {
    return fail("$.object_id", "response belongs to another Research Object");
  }
  const goal = decodeGoal(field(input, "goal", "$" ), "$.goal");
  const scheme = decodeScheme(field(input, "scheme_snapshot", "$" ), "$.scheme_snapshot");
  if (goal.researchObjectId !== objectId || scheme.researchObjectId !== objectId) {
    return fail("$", "draft Goal/Scheme does not close to its Research Object");
  }
  if (scheme.goalId !== goal.goalId) return fail("$.scheme_snapshot.goal_id", "Scheme belongs to another Goal");
  if (scheme.confirmedAt !== null) return fail("$.scheme_snapshot.confirmed_at", "prepared Scheme must be unconfirmed");
  const plannedGraphAvailability = decodeAvailability(
    field(input, "planned_graph_availability", "$" ),
    "$.planned_graph_availability"
  );
  if (
    plannedGraphAvailability.status !== "NOT_GENERATED" ||
    plannedGraphAvailability.reasonCode !== "PLAN_CREATED_ON_CONFIRM" ||
    plannedGraphAvailability.retryable
  ) {
    return fail(
      "$.planned_graph_availability",
      "prepare must expose NOT_GENERATED/PLAN_CREATED_ON_CONFIRM/non-retryable"
    );
  }
  const createdAt = decodeRfc3339Utc(field(input, "created_at", "$" ), "$.created_at");
  const expiresAt = decodeRfc3339Utc(field(input, "expires_at", "$" ), "$.expires_at");
  if (Date.parse(expiresAt) <= Date.parse(createdAt)) return fail("$.expires_at", "expiry must follow creation");
  return freezeDeep({
    schemaVersion: RUN_DRAFT_SCHEMA_VERSION,
    draftId: decodeOpaqueId(field(input, "draft_id", "$" ), "$.draft_id"),
    draftVersion: decodeInteger(field(input, "draft_version", "$" ), 1, "$.draft_version"),
    status: "AWAITING_CONFIRMATION" as const,
    previewKind: "SCHEME_ONLY" as const,
    plannedGraphAvailability,
    objectId,
    goal,
    schemeSnapshot: scheme as NormalizedScheme & Readonly<{ confirmedAt: null }>,
    prepareRequestHash: decodeSha256(field(input, "prepare_request_hash", "$" ), "$.prepare_request_hash"),
    draftHash: decodeSha256(field(input, "draft_hash", "$" ), "$.draft_hash"),
    createdAt,
    expiresAt
  });
}

function requireExpectedIdentity(actual: string | number, expected: string | number, path: string): void {
  if (actual !== expected) fail(path, "response identity does not match the submitted confirmation");
}

export function decodeConfirmRunResponse(
  value: unknown,
  expected: ConfirmAdmissionExpectation
): ConfirmRunResponseV1 {
  const input = decodeObject(value, "$" );
  assertOnlyKeys(input, ["schema_version", "admission", "response_meta"], "$" );
  if (field(input, "schema_version", "$" ) !== CONFIRM_RESPONSE_SCHEMA_VERSION) {
    return fail(
      "$.schema_version",
      `unsupported confirm schema; expected ${CONFIRM_RESPONSE_SCHEMA_VERSION}`
    );
  }
  const rawAdmission = decodeObject(field(input, "admission", "$" ), "$.admission");
  assertOnlyKeys(
    rawAdmission,
    [
      "schema_version",
      "admission_id",
      "run_id",
      "object_id",
      "draft_id",
      "draft_version",
      "draft_hash",
      "goal_id",
      "scheme_id",
      "planned_graph_id",
      "status",
      "auto_start",
      "confirmation_request_hash",
      "admitted_at",
      "projection_ref",
      "events_ref"
    ],
    "$.admission"
  );
  if (field(rawAdmission, "schema_version", "$.admission") !== RUN_ADMISSION_SCHEMA_VERSION) {
    return fail(
      "$.admission.schema_version",
      `unsupported admission schema; expected ${RUN_ADMISSION_SCHEMA_VERSION}`
    );
  }
  if (field(rawAdmission, "status", "$.admission") !== "PLANNING") {
    return fail("$.admission.status", "successful admission must have raw status PLANNING");
  }
  const autoStart = decodeObject(field(rawAdmission, "auto_start", "$.admission"), "$.admission.auto_start");
  assertOnlyKeys(autoStart, ["required", "admitted"], "$.admission.auto_start");
  if (
    field(autoStart, "required", "$.admission.auto_start") !== true ||
    field(autoStart, "admitted", "$.admission.auto_start") !== true
  ) {
    return fail("$.admission.auto_start", "successful admission requires required=true and admitted=true");
  }
  const runId = decodeOpaqueId(field(rawAdmission, "run_id", "$.admission"), "$.admission.run_id");
  const objectId = decodeOpaqueId(
    field(rawAdmission, "object_id", "$.admission"),
    "$.admission.object_id"
  );
  const draftId = decodeOpaqueId(
    field(rawAdmission, "draft_id", "$.admission"),
    "$.admission.draft_id"
  );
  const draftVersion = decodeInteger(
    field(rawAdmission, "draft_version", "$.admission"),
    1,
    "$.admission.draft_version"
  );
  const draftHash = decodeSha256(
    field(rawAdmission, "draft_hash", "$.admission"),
    "$.admission.draft_hash"
  );
  const goalId = decodeOpaqueId(field(rawAdmission, "goal_id", "$.admission"), "$.admission.goal_id");
  const schemeId = decodeOpaqueId(
    field(rawAdmission, "scheme_id", "$.admission"),
    "$.admission.scheme_id"
  );
  requireExpectedIdentity(objectId, decodeOpaqueId(expected.objectId, "expected.objectId"), "$.admission.object_id");
  requireExpectedIdentity(draftId, decodeOpaqueId(expected.draftId, "expected.draftId"), "$.admission.draft_id");
  requireExpectedIdentity(
    draftVersion,
    decodeInteger(expected.draftVersion, 1, "expected.draftVersion"),
    "$.admission.draft_version"
  );
  requireExpectedIdentity(draftHash, decodeSha256(expected.draftHash, "expected.draftHash"), "$.admission.draft_hash");
  if (expected.goalId !== undefined) {
    requireExpectedIdentity(goalId, decodeOpaqueId(expected.goalId, "expected.goalId"), "$.admission.goal_id");
  }
  if (expected.schemeId !== undefined) {
    requireExpectedIdentity(
      schemeId,
      decodeOpaqueId(expected.schemeId, "expected.schemeId"),
      "$.admission.scheme_id"
    );
  }
  const projectionRef = decodeNonBlankString(
    field(rawAdmission, "projection_ref", "$.admission"),
    "$.admission.projection_ref"
  );
  const eventsRef = decodeNonBlankString(
    field(rawAdmission, "events_ref", "$.admission"),
    "$.admission.events_ref"
  );
  if (projectionRef !== `/api/research-runs/${runId}/projection`) {
    return fail("$.admission.projection_ref", "projection ref does not name the admitted Run");
  }
  if (eventsRef !== `/api/research-runs/${runId}/events`) {
    return fail("$.admission.events_ref", "events ref does not name the admitted Run");
  }
  const admission: RunAdmissionV1 = freezeDeep({
    schemaVersion: RUN_ADMISSION_SCHEMA_VERSION,
    admissionId: decodeOpaqueId(
      field(rawAdmission, "admission_id", "$.admission"),
      "$.admission.admission_id"
    ),
    runId,
    objectId,
    draftId,
    draftVersion,
    draftHash,
    goalId,
    schemeId,
    plannedGraphId: decodeOpaqueId(
      field(rawAdmission, "planned_graph_id", "$.admission"),
      "$.admission.planned_graph_id"
    ),
    backendStatus: "PLANNING" as const,
    status: "PLANNING" as const,
    autoStart: { required: true as const, admitted: true as const },
    confirmationRequestHash: decodeSha256(
      field(rawAdmission, "confirmation_request_hash", "$.admission"),
      "$.admission.confirmation_request_hash"
    ),
    admittedAt: decodeRfc3339Utc(
      field(rawAdmission, "admitted_at", "$.admission"),
      "$.admission.admitted_at"
    ),
    projectionRef,
    eventsRef
  });
  const rawMeta = decodeObject(field(input, "response_meta", "$" ), "$.response_meta");
  assertOnlyKeys(rawMeta, ["schema_version", "request_id", "idempotency_replayed"], "$.response_meta");
  if (field(rawMeta, "schema_version", "$.response_meta") !== RESPONSE_META_SCHEMA_VERSION) {
    return fail(
      "$.response_meta.schema_version",
      `unsupported response metadata schema; expected ${RESPONSE_META_SCHEMA_VERSION}`
    );
  }
  const responseMeta: ResponseMetaV1 = freezeDeep({
    schemaVersion: RESPONSE_META_SCHEMA_VERSION,
    requestId: decodeNullableOpaqueId(
      field(rawMeta, "request_id", "$.response_meta"),
      "$.response_meta.request_id"
    ),
    idempotencyReplayed: decodeBoolean(
      field(rawMeta, "idempotency_replayed", "$.response_meta"),
      "$.response_meta.idempotency_replayed"
    )
  });
  return freezeDeep({ schemaVersion: CONFIRM_RESPONSE_SCHEMA_VERSION, admission, responseMeta });
}

const BACKEND_RUN_STATUSES = Object.freeze(Object.keys(RUN_STATUS_MAP) as BackendRunStatus[]);
const RUN_STAGES = [
  "PREPARE",
  "CONFIRM",
  "PLANNING",
  "RESEARCH",
  "REVIEW",
  "PROVING",
  "COMPLETE",
  "FAILED",
  "CANCELLED"
] as const;
const BACKEND_TASK_STATUSES = Object.freeze(Object.keys(TASK_STATUS_MAP) as BackendTaskStatus[]);

function decodeRunProgress(value: unknown, path: string): RunProgress {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["method", "completed_tasks", "total_tasks", "fraction"], path);
  if (field(input, "method", path) !== "ACTUAL_TASK_MEAN_V1") {
    return fail(`${path}.method`, "expected ACTUAL_TASK_MEAN_V1");
  }
  const completedTasks = decodeInteger(
    field(input, "completed_tasks", path),
    0,
    `${path}.completed_tasks`
  );
  const totalTasks = decodeInteger(field(input, "total_tasks", path), 0, `${path}.total_tasks`);
  if (completedTasks > totalTasks) {
    return fail(`${path}.completed_tasks`, "completed task count exceeds total task count");
  }
  const fraction = decodeRatio(field(input, "fraction", path), `${path}.fraction`);
  return freezeDeep({
    method: "ACTUAL_TASK_MEAN_V1" as const,
    completedTasks,
    totalTasks,
    fraction,
    percent: fraction * 100
  });
}

function decodeRunStatusFields(
  input: UnknownObject,
  path: string
): Readonly<{
  backendStatus: BackendRunStatus;
  status: Phase4RunStatus;
  stage: Phase4RunStage;
  terminal: boolean;
}> {
  const backendStatus = decodeEnum(
    field(input, "status", path),
    BACKEND_RUN_STATUSES,
    `${path}.status`
  );
  const stage = decodeEnum(field(input, "stage", path), RUN_STAGES, `${path}.stage`);
  const terminal = decodeBoolean(field(input, "terminal", path), `${path}.terminal`);
  const expected = RUN_STATUS_MAP[backendStatus];
  if (stage !== expected.stage || terminal !== expected.terminal) {
    return fail(path, `stage/terminal contradict raw Run status ${backendStatus}`);
  }
  return freezeDeep({ backendStatus, status: expected.status, stage, terminal });
}

function decodeRunCollectionItem(value: unknown, path: string): RunCollectionItem {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    [
      "run_id",
      "object",
      "status",
      "stage",
      "progress",
      "activity",
      "graph_version",
      "projection_revision",
      "projection_sequence",
      "as_of",
      "created_at",
      "updated_at",
      "started_at",
      "completed_at",
      "terminal",
      "result_availability"
    ],
    path
  );
  const statusFields = decodeRunStatusFields(input, path);
  const rawObject = decodeObject(field(input, "object", path), `${path}.object`);
  assertOnlyKeys(rawObject, ["object_id", "symbol", "company_name"], `${path}.object`);
  const rawActivity = field(input, "activity", path);
  const rawGraphVersion = field(input, "graph_version", path);
  const activity =
    rawActivity === null ? null : decodeRunCollectionActivity(rawActivity, `${path}.activity`);
  const projectionSequence = decodeInteger(
    field(input, "projection_sequence", path),
    0,
    `${path}.projection_sequence`
  );
  if ((projectionSequence === 0) !== (activity === null)) {
    return fail(`${path}.activity`, "activity presence must match the projection watermark");
  }
  if (activity !== null && activity.sequence !== projectionSequence) {
    return fail(`${path}.activity.sequence`, "latest activity must equal the projection watermark");
  }
  if (
    statusFields.backendStatus === "RELEASED"
      ? activity?.type !== "run.completed"
      : statusFields.backendStatus === "FAILED" || statusFields.backendStatus === "CANCELLED"
        ? activity?.type !== "run.failed"
        : activity?.type === "run.completed" || activity?.type === "run.failed"
  ) {
    return fail(`${path}.activity.type`, "latest activity contradicts the Run terminal status");
  }
  const progress = decodeRunProgress(field(input, "progress", path), `${path}.progress`);
  if (
    statusFields.backendStatus !== "RELEASED" &&
    progress.totalTasks === 0 &&
    progress.fraction !== 0
  ) {
    return fail(`${path}.progress.fraction`, "Run with zero Tasks must have zero progress");
  }
  if (
    (statusFields.backendStatus === "FAILED" || statusFields.backendStatus === "CANCELLED") &&
    progress.totalTasks > 0 &&
    progress.completedTasks === progress.totalTasks &&
    progress.fraction !== 1
  ) {
    return fail(
      `${path}.progress.fraction`,
      "unsuccessful terminal Run with every Task completed must have complete progress"
    );
  }
  // Task execution may be complete while Review/Proof/release remain pending.
  // Explicit lifecycle status, not task progress, determines terminality.
  if (statusFields.backendStatus === "RELEASED" && progress.fraction !== 1) {
    return fail(`${path}.progress.fraction`, "RELEASED Run progress must be complete");
  }
  const createdAt = decodeRfc3339Utc(field(input, "created_at", path), `${path}.created_at`);
  const updatedAt = decodeRfc3339Utc(field(input, "updated_at", path), `${path}.updated_at`);
  const startedAt = decodeNullable(
    field(input, "started_at", path),
    decodeRfc3339Utc,
    `${path}.started_at`
  );
  const completedAt = decodeNullable(
    field(input, "completed_at", path),
    decodeRfc3339Utc,
    `${path}.completed_at`
  );
  if (
    activity?.type === "run.started" &&
    (statusFields.backendStatus !== "RUNNING" ||
      startedAt === null ||
      activity.timestamp !== startedAt)
  ) {
    return fail(
      `${path}.activity`,
      "run.started must close atomically to RUNNING status and started_at"
    );
  }
  if (statusFields.terminal !== (completedAt !== null)) {
    return fail(`${path}.completed_at`, "completion time must be present exactly for terminal Runs");
  }
  if (
    Date.parse(createdAt) > Date.parse(updatedAt) ||
    (startedAt !== null && Date.parse(startedAt) < Date.parse(createdAt)) ||
    (startedAt !== null && Date.parse(startedAt) > Date.parse(updatedAt)) ||
    (completedAt !== null &&
      (Date.parse(completedAt) < Date.parse(startedAt ?? createdAt) ||
        Date.parse(completedAt) > Date.parse(updatedAt)))
  ) {
    return fail(path, "Run collection timestamps contradict lifecycle order");
  }
  if (
    activity !== null &&
    (Date.parse(activity.timestamp) < Date.parse(createdAt) ||
      Date.parse(activity.timestamp) > Date.parse(updatedAt))
  ) {
    return fail(`${path}.activity.timestamp`, "latest activity falls outside the Run time bounds");
  }
  const resultAvailability = decodeAvailability(
    field(input, "result_availability", path),
    `${path}.result_availability`
  );
  if (statusFields.terminal && resultAvailability.status === "PENDING") {
    return fail(`${path}.result_availability`, "terminal Run resource cannot remain PENDING");
  }
  if (!statusFields.terminal && resultAvailability.status !== "PENDING") {
    return fail(`${path}.result_availability`, "nonterminal Run result must remain PENDING");
  }
  if (
    (statusFields.backendStatus === "RELEASED") !==
    (resultAvailability.status === "AVAILABLE")
  ) {
    return fail(`${path}.result_availability`, "available result must match RELEASED status exactly");
  }
  return freezeDeep({
    runId: decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`),
    object: {
      objectId: decodeOpaqueId(field(rawObject, "object_id", `${path}.object`), `${path}.object.object_id`),
      symbol: decodeNonBlankString(field(rawObject, "symbol", `${path}.object`), `${path}.object.symbol`),
      companyName: decodePublicText(
        field(rawObject, "company_name", `${path}.object`),
        `${path}.object.company_name`
      )
    },
    ...statusFields,
    progress,
    activity,
    graphVersion:
      rawGraphVersion === null
        ? null
        : decodeInteger(rawGraphVersion, 1, `${path}.graph_version`),
    projectionRevision: decodeInteger(
      field(input, "projection_revision", path),
      1,
      `${path}.projection_revision`
    ),
    projectionSequence,
    asOf: decodeDate(field(input, "as_of", path), `${path}.as_of`),
    createdAt,
    updatedAt,
    startedAt,
    completedAt,
    resultAvailability
  });
}

function decodeRunHistoryItem(value: unknown, path: string): RunHistoryItem {
  const input = decodeObject(value, path);
  const availability = field(input, "availability", path);
  if (availability === "AVAILABLE") {
    assertOnlyKeys(input, ["availability", "run"], path);
    return freezeDeep({
      availability,
      run: decodeRunCollectionItem(field(input, "run", path), `${path}.run`)
    });
  }
  if (availability !== "UNAVAILABLE_INCOMPATIBLE") {
    return fail(`${path}.availability`, "unsupported Run history availability variant");
  }
  assertOnlyKeys(
    input,
    ["availability", "run_id", "object", "status", "updated_at", "reason_code"],
    path
  );
  const rawObject = decodeObject(field(input, "object", path), `${path}.object`);
  assertOnlyKeys(rawObject, ["object_id", "symbol", "company_name"], `${path}.object`);
  const reasonCode = field(input, "reason_code", path);
  if (reasonCode !== "LEGACY_OR_INCOMPATIBLE") {
    return fail(`${path}.reason_code`, "unsupported incompatible history reason");
  }
  return freezeDeep({
    availability,
    runId: decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`),
    object: {
      objectId: decodeOpaqueId(field(rawObject, "object_id", `${path}.object`), `${path}.object.object_id`),
      symbol: decodeNonBlankString(field(rawObject, "symbol", `${path}.object`), `${path}.object.symbol`),
      companyName: decodePublicText(
        field(rawObject, "company_name", `${path}.object`),
        `${path}.object.company_name`
      )
    },
    backendStatus: decodeEnum(
      field(input, "status", path),
      BACKEND_RUN_STATUSES,
      `${path}.status`
    ),
    updatedAt: decodeRfc3339Utc(field(input, "updated_at", path), `${path}.updated_at`),
    reasonCode: "LEGACY_OR_INCOMPATIBLE" as const
  });
}

export function decodeRunCollection(
  value: unknown,
  expectedObjectId?: string
): GlobalRunCollectionProjection {
  const input = decodeObject(value, "$" );
  assertOnlyKeys(input, ["schema_version", "items", "next_cursor"], "$" );
  if (field(input, "schema_version", "$" ) !== RUN_HISTORY_COLLECTION_SCHEMA_VERSION) {
    return fail(
      "$.schema_version",
      `unsupported Run history collection schema; expected ${RUN_HISTORY_COLLECTION_SCHEMA_VERSION}`
    );
  }
  const items = decodeArray(field(input, "items", "$" ), "$.items").map((item, index) =>
    decodeRunHistoryItem(item, `$.items[${index}]`)
  );
  const runIds = items.map((item) => item.availability === "AVAILABLE" ? item.run.runId : item.runId);
  if (new Set(runIds).size !== runIds.length) return fail("$.items", "duplicate Run identity");
  if (expectedObjectId !== undefined) {
    const expected = decodeOpaqueId(expectedObjectId, "expectedObjectId");
    const mismatch = items.find((item) => (item.availability === "AVAILABLE" ? item.run.object.objectId : item.object.objectId) !== expected);
    if (mismatch !== undefined) return fail("$.items", "collection contains a Run from another Object");
  }
  return freezeDeep({
    schemaVersion: RUN_HISTORY_COLLECTION_SCHEMA_VERSION,
    items,
    nextCursor: decodeNullableOpaqueId(field(input, "next_cursor", "$" ), "$.next_cursor")
  });
}

const RUN_LINEAGE_FIELDS = ["base_run_id", "base_research_view_version", "reexecution_of_run_id"] as const;

function decodeRunLineage(input: Record<string, unknown>, path: string): RunLineage {
  const optionalId = (key: typeof RUN_LINEAGE_FIELDS[number]) => Object.hasOwn(input, key)
    ? decodeNullableOpaqueId(input[key], `${path}.${key}`) : undefined;
  const baseRunId = optionalId("base_run_id");
  const baseResearchViewVersion = optionalId("base_research_view_version");
  const reexecutionOfRunId = optionalId("reexecution_of_run_id");
  if ((baseRunId != null) !== (baseResearchViewVersion != null)) return fail(path, "knowledge base identities must be paired");
  if (baseRunId != null && baseRunId === input.run_id) return fail(path, "Run cannot be its own knowledge base");
  if (reexecutionOfRunId != null && (baseRunId == null || reexecutionOfRunId === input.run_id || reexecutionOfRunId === baseRunId)) {
    return fail(path, "execution predecessor must be distinct from Run and knowledge base");
  }
  return {
    ...(baseRunId !== undefined ? {baseRunId} : {}),
    ...(baseResearchViewVersion !== undefined ? {baseResearchViewVersion} : {}),
    ...(reexecutionOfRunId !== undefined ? {reexecutionOfRunId} : {}),
  };
}

function decodeResearchRunDetailAt(value: unknown, path: string): ResearchRunDetailV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    [
      "run_id",
      "research_object_id",
      "goal_id",
      "scheme_id",
      "status",
      "stage",
      "as_of",
      "planned_graph_id",
      "actual_graph_id",
      "execution_target",
      "created_at",
      "updated_at",
      "started_at",
      "completed_at",
      "terminal",
      "projection_revision",
      "projection_sequence",
      ...RUN_LINEAGE_FIELDS
    ],
    path
  );
  const statusFields = decodeRunStatusFields(input, path);
  const createdAt = decodeRfc3339Utc(field(input, "created_at", path), `${path}.created_at`);
  const updatedAt = decodeRfc3339Utc(field(input, "updated_at", path), `${path}.updated_at`);
  const startedAt = decodeNullable(
    field(input, "started_at", path),
    decodeRfc3339Utc,
    `${path}.started_at`
  );
  const completedAt = decodeNullable(
    field(input, "completed_at", path),
    decodeRfc3339Utc,
    `${path}.completed_at`
  );
  if (statusFields.terminal !== (completedAt !== null)) {
    return fail(`${path}.completed_at`, "completion time must be present exactly for terminal Runs");
  }
  if (
    Date.parse(createdAt) > Date.parse(updatedAt) ||
    (startedAt !== null && Date.parse(startedAt) < Date.parse(createdAt)) ||
    (startedAt !== null && Date.parse(startedAt) > Date.parse(updatedAt)) ||
    (completedAt !== null &&
      (Date.parse(completedAt) < Date.parse(startedAt ?? createdAt) ||
        Date.parse(completedAt) > Date.parse(updatedAt)))
  ) {
    return fail(path, "Run timestamps contradict lifecycle order");
  }
  return freezeDeep({
    runId: decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`),
    researchObjectId: decodeOpaqueId(
      field(input, "research_object_id", path),
      `${path}.research_object_id`
    ),
    goalId: decodeOpaqueId(field(input, "goal_id", path), `${path}.goal_id`),
    schemeId: decodeOpaqueId(field(input, "scheme_id", path), `${path}.scheme_id`),
    ...statusFields,
    asOf: decodeDate(field(input, "as_of", path), `${path}.as_of`),
    plannedGraphId: decodeNullableOpaqueId(
      field(input, "planned_graph_id", path),
      `${path}.planned_graph_id`
    ),
    actualGraphId: decodeNullableOpaqueId(
      field(input, "actual_graph_id", path),
      `${path}.actual_graph_id`
    ),
    executionTarget: decodeNonBlankString(
      field(input, "execution_target", path),
      `${path}.execution_target`
    ),
    createdAt,
    updatedAt,
    startedAt,
    completedAt,
    ...decodeRunLineage(input, path),
    projectionRevision: decodeInteger(
      field(input, "projection_revision", path),
      1,
      `${path}.projection_revision`
    ),
    projectionSequence: decodeInteger(
      field(input, "projection_sequence", path),
      0,
      `${path}.projection_sequence`
    )
  });
}

function decodeEmbeddedResearchRunAt(value: unknown, path: string): EmbeddedResearchRunV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    [
      "run_id",
      "research_object_id",
      "goal_id",
      "scheme_id",
      "status",
      "stage",
      "as_of",
      "planned_graph_id",
      "actual_graph_id",
      "execution_target",
      "created_at",
      "updated_at",
      "started_at",
      "completed_at",
      ...RUN_LINEAGE_FIELDS
    ],
    path
  );
  const statusFields = decodeRunStatusFields(
    { ...input, terminal: field(input, "completed_at", path) !== null },
    path
  );
  const createdAt = decodeRfc3339Utc(field(input, "created_at", path), `${path}.created_at`);
  const updatedAt = decodeRfc3339Utc(field(input, "updated_at", path), `${path}.updated_at`);
  const startedAt = decodeNullable(
    field(input, "started_at", path),
    decodeRfc3339Utc,
    `${path}.started_at`
  );
  const completedAt = decodeNullable(
    field(input, "completed_at", path),
    decodeRfc3339Utc,
    `${path}.completed_at`
  );
  if (statusFields.terminal !== (completedAt !== null)) {
    return fail(`${path}.completed_at`, "completion time must be present exactly for terminal Runs");
  }
  if (
    Date.parse(createdAt) > Date.parse(updatedAt) ||
    (startedAt !== null && Date.parse(startedAt) < Date.parse(createdAt)) ||
    (startedAt !== null && Date.parse(startedAt) > Date.parse(updatedAt)) ||
    (completedAt !== null &&
      (Date.parse(completedAt) < Date.parse(startedAt ?? createdAt) ||
        Date.parse(completedAt) > Date.parse(updatedAt)))
  ) {
    return fail(path, "Run timestamps contradict lifecycle order");
  }
  return freezeDeep({
    runId: decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`),
    researchObjectId: decodeOpaqueId(
      field(input, "research_object_id", path),
      `${path}.research_object_id`
    ),
    goalId: decodeOpaqueId(field(input, "goal_id", path), `${path}.goal_id`),
    schemeId: decodeOpaqueId(field(input, "scheme_id", path), `${path}.scheme_id`),
    ...statusFields,
    asOf: decodeDate(field(input, "as_of", path), `${path}.as_of`),
    plannedGraphId: decodeNullableOpaqueId(
      field(input, "planned_graph_id", path),
      `${path}.planned_graph_id`
    ),
    actualGraphId: decodeNullableOpaqueId(
      field(input, "actual_graph_id", path),
      `${path}.actual_graph_id`
    ),
    executionTarget: decodeNonBlankString(
      field(input, "execution_target", path),
      `${path}.execution_target`
    ),
    createdAt,
    updatedAt,
    startedAt,
    completedAt,
    ...decodeRunLineage(input, path)
  });
}

export function decodeResearchRunDetail(
  value: unknown,
  expectedRunId: string,
  expectedObjectId?: string
): ResearchRunDetailV1 {
  const detail = decodeResearchRunDetailAt(value, "$" );
  if (detail.runId !== decodeOpaqueId(expectedRunId, "expectedRunId")) {
    return fail("$.run_id", "response belongs to another Run");
  }
  if (
    expectedObjectId !== undefined &&
    detail.researchObjectId !== decodeOpaqueId(expectedObjectId, "expectedObjectId")
  ) {
    return fail("$.research_object_id", "response belongs to another Research Object");
  }
  return detail;
}

const TASK_ORIGINS = ["PLAN", "REPLAN", "REVIEW_FIX"] as const;
const EVIDENCE_ACQUISITION_STATUSES = [
  "COMPLETED",
  "PARTIAL",
  "ENTITLEMENT_BLOCKED",
  "FAILED"
] as const;

function decodeTask(value: unknown, path: string): RunTaskProjection {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    [
      "task_id",
      "run_id",
      "parent_task_id",
      "task_type",
      "goal",
      "assigned_agent",
      "skill_id",
      "dependencies",
      "origin",
      "reason_code",
      "status",
      "progress",
      "attempt_count",
      "task_input_evidence_ids",
      "task_output_evidence_ids",
      "evidence_acquisition_status",
      "evidence_source_coverage",
      "created_at"
    ],
    path
  );
  const backendStatus = decodeEnum(
    field(input, "status", path),
    BACKEND_TASK_STATUSES,
    `${path}.status`
  );
  const rawEvidenceStatus = field(input, "evidence_acquisition_status", path);
  return freezeDeep({
    taskId: decodeOpaqueId(field(input, "task_id", path), `${path}.task_id`),
    runId: decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`),
    parentTaskId: decodeNullableOpaqueId(
      field(input, "parent_task_id", path),
      `${path}.parent_task_id`
    ),
    taskType: decodeNonBlankString(field(input, "task_type", path), `${path}.task_type`),
    goal: decodePublicText(field(input, "goal", path), `${path}.goal`),
    assignedAgent: decodeOpaqueId(field(input, "assigned_agent", path), `${path}.assigned_agent`),
    skillId: decodeOpaqueId(field(input, "skill_id", path), `${path}.skill_id`),
    dependencies: decodeStringArray(field(input, "dependencies", path), `${path}.dependencies`),
    origin: decodeEnum(field(input, "origin", path), TASK_ORIGINS, `${path}.origin`),
    reasonCode: decodeOptionalString(field(input, "reason_code", path), `${path}.reason_code`),
    backendStatus,
    status: TASK_STATUS_MAP[backendStatus].status,
    progress: decodeRatio(field(input, "progress", path), `${path}.progress`),
    attemptCount: decodeInteger(field(input, "attempt_count", path), 0, `${path}.attempt_count`),
    taskInputEvidenceIds: decodeStringArray(
      field(input, "task_input_evidence_ids", path),
      `${path}.task_input_evidence_ids`
    ),
    taskOutputEvidenceIds: decodeStringArray(
      field(input, "task_output_evidence_ids", path),
      `${path}.task_output_evidence_ids`
    ),
    evidenceAcquisitionStatus:
      rawEvidenceStatus === null
        ? null
        : decodeEnum(
            rawEvidenceStatus,
            EVIDENCE_ACQUISITION_STATUSES,
            `${path}.evidence_acquisition_status`
          ),
    evidenceSourceCoverage: decodeSafeJsonObject(
      field(input, "evidence_source_coverage", path),
      `${path}.evidence_source_coverage`
    ),
    createdAt: decodeRfc3339Utc(field(input, "created_at", path), `${path}.created_at`)
  });
}

function assertUniqueTasks(tasks: readonly RunTaskProjection[], path: string): void {
  const ids = tasks.map((task) => task.taskId);
  if (new Set(ids).size !== ids.length) fail(path, "duplicate Task identity");
}

function decodeGraph(value: unknown, path: string): NormalizedGraph {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["graph_id", "run_id", "version", "tasks"], path);
  const tasks = decodeArray(field(input, "tasks", path), `${path}.tasks`).map((task, index) =>
    decodeTask(task, `${path}.tasks[${index}]`)
  );
  assertUniqueTasks(tasks, `${path}.tasks`);
  const runId = decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`);
  const knownTasks = new Set(tasks.map((task) => task.taskId));
  for (const [index, task] of tasks.entries()) {
    if (task.runId !== runId) fail(`${path}.tasks[${index}].run_id`, "Task belongs to another Run");
    if (task.parentTaskId !== null && !knownTasks.has(task.parentTaskId)) {
      fail(`${path}.tasks[${index}].parent_task_id`, "Task parent does not resolve in graph");
    }
    if (task.dependencies.includes(task.taskId)) {
      fail(`${path}.tasks[${index}].dependencies`, "Task cannot depend on itself");
    }
    if (task.dependencies.some((dependency) => !knownTasks.has(dependency))) {
      fail(`${path}.tasks[${index}].dependencies`, "Task dependency does not resolve in graph");
    }
  }
  const remainingDependencies = new Map(
    tasks.map((task) => [task.taskId, task.dependencies.length])
  );
  const dependents = new Map<string, string[]>();
  for (const task of tasks) {
    for (const dependency of task.dependencies) {
      dependents.set(dependency, [...(dependents.get(dependency) ?? []), task.taskId]);
    }
  }
  const ready = tasks
    .filter((task) => task.dependencies.length === 0)
    .map((task) => task.taskId);
  let visited = 0;
  while (ready.length > 0) {
    const taskId = ready.pop();
    if (taskId === undefined) break;
    visited += 1;
    for (const dependent of dependents.get(taskId) ?? []) {
      const next = (remainingDependencies.get(dependent) ?? 0) - 1;
      remainingDependencies.set(dependent, next);
      if (next === 0) ready.push(dependent);
    }
  }
  if (visited !== tasks.length) return fail(`${path}.tasks`, "Task dependency graph contains a cycle");
  return freezeDeep({
    graphId: decodeOpaqueId(field(input, "graph_id", path), `${path}.graph_id`),
    runId,
    version: decodeInteger(field(input, "version", path), 1, `${path}.version`),
    tasks
  });
}

const GRAPH_OPERATIONS = ["add_node", "add_edge", "remove_edge"] as const;

function decodeGraphOperation(value: unknown, path: string): TypedGraphOperation {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["operation", "task_id", "dependency_task_id"], path);
  const operation = decodeEnum(
    field(input, "operation", path),
    GRAPH_OPERATIONS,
    `${path}.operation`
  );
  if (operation !== "add_node" && !hasOwn(input, "dependency_task_id")) {
    return fail(`${path}.dependency_task_id`, `${operation} requires a dependency Task`);
  }
  const rawDependencyTaskId = hasOwn(input, "dependency_task_id")
    ? input.dependency_task_id
    : null;
  const dependencyTaskId = decodeNullableOpaqueId(rawDependencyTaskId, `${path}.dependency_task_id`);
  if (operation === "add_node" && dependencyTaskId !== null) {
    return fail(`${path}.dependency_task_id`, "add_node cannot carry a dependency Task");
  }
  if (operation !== "add_node" && dependencyTaskId === null) {
    return fail(`${path}.dependency_task_id`, `${operation} requires a dependency Task`);
  }
  return freezeDeep({
    operation,
    taskId: decodeOpaqueId(field(input, "task_id", path), `${path}.task_id`),
    dependencyTaskId
  });
}

const PATH_SOURCE_KINDS = ["CORRECTION", "REPLAN"] as const;
const PATH_CHANGE_KINDS = ["SELF_CORRECTION", "ADD_TASK", "CHANGE_DEPENDENCY"] as const;

function decodePathChange(value: unknown, path: string): PathChangeProjectionV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    [
      "path_change_id",
      "source_kind",
      "source_id",
      "change_kind",
      "status",
      "decision",
      "reason_code",
      "task_refs",
      "operations",
      "graph_version_before",
      "graph_version_after",
      "created_at",
      "resolved_at"
    ],
    path
  );
  const pathChangeId = decodeOpaqueId(
    field(input, "path_change_id", path),
    `${path}.path_change_id`
  );
  const sourceId = decodeOpaqueId(field(input, "source_id", path), `${path}.source_id`);
  if (pathChangeId !== sourceId) return fail(path, "path change and source identity must be identical");
  const sourceKind = decodeEnum(
    field(input, "source_kind", path),
    PATH_SOURCE_KINDS,
    `${path}.source_kind`
  );
  const changeKind = decodeEnum(
    field(input, "change_kind", path),
    PATH_CHANGE_KINDS,
    `${path}.change_kind`
  );
  const decision = decodeOptionalString(field(input, "decision", path), `${path}.decision`);
  const reasonCode = decodeOptionalString(field(input, "reason_code", path), `${path}.reason_code`);
  const taskRefs = decodeStringArray(field(input, "task_refs", path), `${path}.task_refs`);
  const operations = decodeArray(field(input, "operations", path), `${path}.operations`).map(
    (operation, index) => decodeGraphOperation(operation, `${path}.operations[${index}]`)
  );
  if (sourceKind === "CORRECTION") {
    if (
      changeKind !== "SELF_CORRECTION" ||
      decision !== null ||
      operations.length !== 0 ||
      taskRefs.length !== 1 ||
      reasonCode === null
    ) {
      return fail(path, "Correction path change does not match its frozen one-Task shape");
    }
  } else if (changeKind === "SELF_CORRECTION" || operations.length === 0) {
    return fail(path, "Replan path change requires nonempty typed replan operations");
  }
  const pathTaskIds = new Set(taskRefs);
  for (const [index, operation] of operations.entries()) {
    if (
      !pathTaskIds.has(operation.taskId) ||
      (operation.dependencyTaskId !== null && !pathTaskIds.has(operation.dependencyTaskId))
    ) {
      return fail(`${path}.operations[${index}]`, "operation references a Task outside task_refs");
    }
  }
  const rawBefore = field(input, "graph_version_before", path);
  const rawAfter = field(input, "graph_version_after", path);
  const rawResolvedAt = field(input, "resolved_at", path);
  return freezeDeep({
    pathChangeId,
    sourceKind,
    sourceId,
    changeKind,
    status: decodeNonBlankString(field(input, "status", path), `${path}.status`),
    decision,
    reasonCode,
    taskRefs,
    operations,
    graphVersionBefore:
      rawBefore === null ? null : decodeInteger(rawBefore, 1, `${path}.graph_version_before`),
    graphVersionAfter:
      rawAfter === null ? null : decodeInteger(rawAfter, 1, `${path}.graph_version_after`),
    createdAt: decodeRfc3339Utc(field(input, "created_at", path), `${path}.created_at`),
    resolvedAt:
      rawResolvedAt === null ? null : decodeRfc3339Utc(rawResolvedAt, `${path}.resolved_at`)
  });
}

const TERMINAL_OUTCOMES = ["SUCCESS", "FAILURE", "CANCELLED"] as const;
const TERMINAL_FAILURE_STATUSES = ["FAILED", "CANCELLED"] as const;
const TERMINAL_FAILURE_STAGES = [
  "PLANNING",
  "DATA_EVIDENCE",
  "TASK_EXECUTION",
  "GENERATED_CAPABILITY",
  "FINANCIAL_REVIEW",
  "PROOF",
  "ARTIFACT_GENERATION",
  "RELEASE",
  "POST_SCHEDULER",
  "PERSISTENCE",
  "CANCELLATION"
] as const;

function decodeTerminalFailure(value: unknown, path: string): TerminalFailureV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["status", "failure_stage", "failure_code", "safe_message"], path);
  const rawSafeMessage = field(input, "safe_message", path);
  return freezeDeep({
    status: decodeEnum(field(input, "status", path), TERMINAL_FAILURE_STATUSES, `${path}.status`),
    failureStage: decodeEnum(
      field(input, "failure_stage", path),
      TERMINAL_FAILURE_STAGES,
      `${path}.failure_stage`
    ),
    failureCode: decodeNonBlankString(
      field(input, "failure_code", path),
      `${path}.failure_code`
    ),
    safeMessage:
      rawSafeMessage === null
        ? null
        : decodePublicText(rawSafeMessage, `${path}.safe_message`, true, 4_096)
  });
}

function decodeLifecycle(value: unknown, path: string): NormalizedRunLifecycle {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    ["status", "stage", "progress", "terminal", "terminal_outcome", "safe_failure"],
    path
  );
  const statusFields = decodeRunStatusFields(input, path);
  const rawOutcome = field(input, "terminal_outcome", path);
  const terminalOutcome =
    rawOutcome === null
      ? null
      : decodeEnum(rawOutcome, TERMINAL_OUTCOMES, `${path}.terminal_outcome`);
  if (statusFields.terminal !== (terminalOutcome !== null)) {
    return fail(`${path}.terminal_outcome`, "terminal outcome must be present exactly for terminal Runs");
  }
  const expectedTerminalOutcome =
    statusFields.backendStatus === "RELEASED"
      ? "SUCCESS"
      : statusFields.backendStatus === "FAILED"
        ? "FAILURE"
        : statusFields.backendStatus === "CANCELLED"
          ? "CANCELLED"
          : null;
  if (terminalOutcome !== expectedTerminalOutcome) {
    return fail(`${path}.terminal_outcome`, "terminal outcome contradicts raw Run status");
  }
  const rawFailure = field(input, "safe_failure", path);
  const safeFailure =
    rawFailure === null ? null : decodeTerminalFailure(rawFailure, `${path}.safe_failure`);
  const requiresSafeFailure =
    statusFields.backendStatus === "FAILED" || statusFields.backendStatus === "CANCELLED";
  if (requiresSafeFailure !== (safeFailure !== null)) {
    return fail(`${path}.safe_failure`, "safe failure presence contradicts raw Run status");
  }
  if (safeFailure !== null && safeFailure.status !== statusFields.backendStatus) {
    return fail(`${path}.safe_failure.status`, "safe failure status contradicts raw Run status");
  }
  return freezeDeep({
    backendStatus: statusFields.backendStatus,
    status: statusFields.status,
    stage: statusFields.stage,
    progress: decodeRunProgress(field(input, "progress", path), `${path}.progress`),
    terminal: statusFields.terminal,
    terminalOutcome,
    safeFailure
  });
}

function decodeReviewSummary(value: unknown, path: string): ReviewSummary {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["availability", "review_id", "status"], path);
  const rawStatus = field(input, "status", path);
  const summary = {
    availability: decodeAvailability(field(input, "availability", path), `${path}.availability`),
    reviewId: decodeNullableOpaqueId(field(input, "review_id", path), `${path}.review_id`),
    status: rawStatus === null
      ? null
      : decodeEnum(rawStatus, ["PASS", "REVIEW", "BLOCK"] as const, `${path}.status`)
  };
  if ((summary.reviewId === null) !== (summary.status === null)) {
    return fail(path, "Review summary identity/status must be jointly present");
  }
  if ((summary.availability.status === "AVAILABLE") !== (summary.reviewId !== null)) {
    return fail(path, "Review summary identity/status must be present exactly when AVAILABLE");
  }
  return freezeDeep(summary);
}

function decodeResultSummary(value: unknown, path: string): ResultSummary {
  const input = decodeObject(value, path);
  assertOnlyKeys(
    input,
    ["availability", "released_result_id", "canonical_record_id", "released_at"],
    path
  );
  const summary = {
    availability: decodeAvailability(field(input, "availability", path), `${path}.availability`),
    releasedResultId: decodeNullableOpaqueId(
      field(input, "released_result_id", path),
      `${path}.released_result_id`
    ),
    canonicalRecordId: decodeNullableOpaqueId(
      field(input, "canonical_record_id", path),
      `${path}.canonical_record_id`
    ),
    releasedAt: decodeNullable(
      field(input, "released_at", path),
      decodeRfc3339Utc,
      `${path}.released_at`
    )
  };
  const present = [summary.releasedResultId, summary.canonicalRecordId, summary.releasedAt]
    .filter((item) => item !== null).length;
  if (present !== 0 && present !== 3) return fail(path, "Result summary identity/time tuple is partial");
  if ((summary.availability.status === "AVAILABLE") !== (present === 3)) {
    return fail(path, "Result summary identity/time must be present exactly when AVAILABLE");
  }
  return freezeDeep(summary);
}

function decodeArtifactSummary(value: unknown, path: string): ArtifactSummary {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["availability", "report_id", "representation_ids"], path);
  const summary = {
    availability: decodeAvailability(field(input, "availability", path), `${path}.availability`),
    reportId: decodeNullableOpaqueId(field(input, "report_id", path), `${path}.report_id`),
    representationIds: decodeStringArray(
      field(input, "representation_ids", path),
      `${path}.representation_ids`
    )
  };
  if ((summary.reportId === null) !== (summary.representationIds.length === 0)) {
    return fail(path, "Artifact summary report and representation identities are partial");
  }
  if ((summary.availability.status === "AVAILABLE") !== (summary.reportId !== null)) {
    return fail(path, "Artifact summary identities must be present exactly when AVAILABLE");
  }
  return freezeDeep(summary);
}

function decodeExecutionSummary(value: unknown, path: string): ExecutionSummary {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["availability", "canonical_record_id"], path);
  const summary = {
    availability: decodeAvailability(field(input, "availability", path), `${path}.availability`),
    canonicalRecordId: decodeNullableOpaqueId(
      field(input, "canonical_record_id", path),
      `${path}.canonical_record_id`
    )
  };
  if ((summary.availability.status === "AVAILABLE") !== (summary.canonicalRecordId !== null)) {
    return fail(path, "Execution identity must be present exactly when AVAILABLE");
  }
  return freezeDeep(summary);
}

const PROOF_POLICIES = ["NOT_REQUIRED", "MUST_PROVE", "MIXED", "UNKNOWN"] as const;
const PROOF_STATUSES = [
  "NOT_REQUIRED",
  "PENDING",
  "PROVING",
  "GENERATED_UNVERIFIED",
  "VERIFIED",
  "INVALID",
  "ERROR",
  "UNSUPPORTED"
] as const;

function decodeProofSummary(value: unknown, path: string): NormalizedProofSummary {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["availability", "policy", "status", "proof_refs"], path);
  const rawStatus = field(input, "status", path);
  return freezeDeep({
    availability: decodeAvailability(field(input, "availability", path), `${path}.availability`),
    policy: decodeEnum(field(input, "policy", path), PROOF_POLICIES, `${path}.policy`),
    status:
      rawStatus === null
        ? null
        : decodeEnum(rawStatus, PROOF_STATUSES, `${path}.status`),
    proofRefs: decodeStringArray(field(input, "proof_refs", path), `${path}.proof_refs`)
  });
}

function decodeTerminalState(value: unknown, path: string): NormalizedTerminalState {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["is_terminal", "outcome", "event_id", "sequence"], path);
  const isTerminal = decodeBoolean(field(input, "is_terminal", path), `${path}.is_terminal`);
  const rawOutcome = field(input, "outcome", path);
  const outcome =
    rawOutcome === null ? null : decodeEnum(rawOutcome, TERMINAL_OUTCOMES, `${path}.outcome`);
  const eventId = decodeNullableOpaqueId(field(input, "event_id", path), `${path}.event_id`);
  const rawSequence = field(input, "sequence", path);
  const sequence =
    rawSequence === null ? null : decodeInteger(rawSequence, 1, `${path}.sequence`);
  if (isTerminal !== (outcome !== null && eventId !== null && sequence !== null)) {
    return fail(path, "outcome/event/sequence must be present exactly for terminal state");
  }
  return freezeDeep({ isTerminal, outcome, eventId, sequence });
}

function requireAvailableIdentity(
  ref: Readonly<{ availability: Availability }>,
  identity: string | null,
  path: string,
  label: string
): void {
  if (ref.availability.status === "AVAILABLE" && identity === null) {
    fail(path, `AVAILABLE ${label} requires its exact identity`);
  }
}

function sameStringSet(left: readonly string[], right: readonly string[]): boolean {
  if (left.length !== right.length) return false;
  const values = new Set(left);
  return values.size === left.length && right.every((item) => values.has(item));
}

function sameDecodedValue(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right) &&
      left.length === right.length &&
      left.every((value, index) => sameDecodedValue(value, right[index]));
  }
  if (
    typeof left !== "object" || left === null ||
    typeof right !== "object" || right === null
  ) return false;
  const leftRecord = left as Readonly<Record<string, unknown>>;
  const rightRecord = right as Readonly<Record<string, unknown>>;
  const leftKeys = Object.keys(leftRecord);
  const rightKeys = Object.keys(rightRecord);
  return leftKeys.length === rightKeys.length && leftKeys.every(
    (key) => hasOwn(rightRecord as UnknownObject, key) &&
      sameDecodedValue(leftRecord[key], rightRecord[key])
  );
}

export function decodeRunProjection(
  value: unknown,
  expectedRunId: string,
  expectedObjectId?: string
): RunProjection {
  const input = decodeObject(value, "$" );
  assertOnlyKeys(
    input,
    [
      "projection_schema_version",
      "projection_revision",
      "projection_sequence",
      "generated_at",
      "object",
      "run",
      "goal",
      "confirmed_scheme",
      "planned_graph",
      "actual_graph",
      "graph_version",
      "tasks",
      "path_changes",
      "activity",
      "lifecycle",
      "review",
      "result",
      "artifacts",
      "proof",
      "execution",
      "terminal"
    ],
    "$"
  );
  if (field(input, "projection_schema_version", "$" ) !== RUN_PROJECTION_SCHEMA_VERSION) {
    return fail(
      "$.projection_schema_version",
      `unsupported Run projection schema; expected ${RUN_PROJECTION_SCHEMA_VERSION}`
    );
  }
  const projectionRevision = decodeInteger(
    field(input, "projection_revision", "$" ),
    1,
    "$.projection_revision"
  );
  const projectionSequence = decodeInteger(
    field(input, "projection_sequence", "$" ),
    0,
    "$.projection_sequence"
  );
  const object = decodeObjectIdentity(field(input, "object", "$" ), "$.object");
  const run = decodeEmbeddedResearchRunAt(field(input, "run", "$" ), "$.run");
  const expectedRun = decodeOpaqueId(expectedRunId, "expectedRunId");
  if (run.runId !== expectedRun) return fail("$.run.run_id", "projection belongs to another Run");
  if (run.researchObjectId !== object.objectId) {
    return fail("$.run.research_object_id", "Run belongs to another Research Object");
  }
  if (
    expectedObjectId !== undefined &&
    object.objectId !== decodeOpaqueId(expectedObjectId, "expectedObjectId")
  ) {
    return fail("$.object.object_id", "projection belongs to another Research Object");
  }
  const goal = decodeGoal(field(input, "goal", "$" ), "$.goal");
  if (goal.goalId !== run.goalId || goal.researchObjectId !== object.objectId) {
    return fail("$.goal", "Goal identity does not close to the Run/Object");
  }
  const confirmedScheme = decodeScheme(field(input, "confirmed_scheme", "$" ), "$.confirmed_scheme");
  if (
    confirmedScheme.schemeId !== run.schemeId ||
    confirmedScheme.goalId !== run.goalId ||
    confirmedScheme.researchObjectId !== object.objectId
  ) {
    return fail("$.confirmed_scheme", "Scheme identity does not close to the Run/Goal/Object");
  }
  if (confirmedScheme.confirmedAt === null) {
    return fail("$.confirmed_scheme.confirmed_at", "Run projection requires a confirmed Scheme");
  }
  const plannedGraph = decodeGraph(field(input, "planned_graph", "$" ), "$.planned_graph");
  if (plannedGraph.runId !== run.runId || run.plannedGraphId !== plannedGraph.graphId) {
    return fail("$.planned_graph", "planned Graph identity does not close to the Run");
  }
  const rawActualGraph = field(input, "actual_graph", "$" );
  const actualGraph =
    rawActualGraph === null ? null : decodeGraph(rawActualGraph, "$.actual_graph");
  const rawGraphVersion = field(input, "graph_version", "$" );
  const graphVersion =
    rawGraphVersion === null ? null : decodeInteger(rawGraphVersion, 1, "$.graph_version");
  if ((actualGraph === null) !== (graphVersion === null)) {
    return fail("$.graph_version", "actual Graph and graph version must be available together");
  }
  if (actualGraph === null) {
    if (run.actualGraphId !== null) {
      return fail("$.run.actual_graph_id", "Run references an unavailable actual Graph");
    }
  } else if (
    actualGraph.runId !== run.runId ||
    run.actualGraphId !== actualGraph.graphId ||
    actualGraph.version !== graphVersion
  ) {
    return fail("$.actual_graph", "actual Graph identity/version does not close to the Run");
  }
  const tasks = decodeArray(field(input, "tasks", "$" ), "$.tasks").map((task, index) =>
    decodeTask(task, `$.tasks[${index}]`)
  );
  assertUniqueTasks(tasks, "$.tasks");
  tasks.forEach((task, index) => {
    if (task.runId !== run.runId) fail(`$.tasks[${index}].run_id`, "Task belongs to another Run");
  });
  const activeGraph = actualGraph ?? plannedGraph;
  const authoritativeGraphTasks = activeGraph.tasks.map((task) => task.taskId);
  if (!sameStringSet(tasks.map((task) => task.taskId), authoritativeGraphTasks)) {
    return fail("$.tasks", "Task identities disagree with the active Graph");
  }
  const activeTasksById = new Map(activeGraph.tasks.map((task) => [task.taskId, task]));
  if (tasks.some((task) => !sameDecodedValue(task, activeTasksById.get(task.taskId)))) {
    return fail("$.tasks", "Task content disagrees with the active Graph");
  }
  if (actualGraph !== null) {
    const actualTaskIds = new Set(actualGraph.tasks.map((task) => task.taskId));
    if (plannedGraph.tasks.some((task) => !actualTaskIds.has(task.taskId))) {
      return fail("$.actual_graph.tasks", "actual Graph omits an immutable planned Task");
    }
  }
  const pathChanges = decodeArray(field(input, "path_changes", "$" ), "$.path_changes").map(
    (change, index) => decodePathChange(change, `$.path_changes[${index}]`)
  );
  const pathIds = pathChanges.map((change) => change.pathChangeId);
  if (new Set(pathIds).size !== pathIds.length) return fail("$.path_changes", "duplicate PathChange identity");
  const taskIds = new Set(tasks.map((task) => task.taskId));
  pathChanges.forEach((change, index) => {
    if (change.taskRefs.some((taskId) => !taskIds.has(taskId))) {
      fail(`$.path_changes[${index}].task_refs`, "PathChange references an unknown Task");
    }
    for (const [operationIndex, operation] of change.operations.entries()) {
      if (!taskIds.has(operation.taskId)) {
        fail(
          `$.path_changes[${index}].operations[${operationIndex}].task_id`,
          "graph operation references an unknown Task"
        );
      }
      if (operation.dependencyTaskId !== null && !taskIds.has(operation.dependencyTaskId)) {
        fail(
          `$.path_changes[${index}].operations[${operationIndex}].dependency_task_id`,
          "graph operation references an unknown dependency Task"
        );
      }
    }
  });
  const activity = decodeArray(field(input, "activity", "$" ), "$.activity").map((item, index) =>
    decodeActivity(item, `$.activity[${index}]`)
  );
  const eventIds = activity.map((item) => item.eventId);
  if (new Set(eventIds).size !== eventIds.length) return fail("$.activity", "duplicate RuntimeEvent identity");
  for (const [index, item] of activity.entries()) {
    if (item.sequence > projectionSequence) {
      return fail(`$.activity[${index}].sequence`, "activity sequence exceeds projection watermark");
    }
    if (index > 0 && item.sequence <= activity[index - 1].sequence) {
      return fail(`$.activity[${index}].sequence`, "activity sequence must be strictly increasing");
    }
    if (item.taskId !== null && !taskIds.has(item.taskId)) {
      return fail(`$.activity[${index}].task_id`, "activity references an unknown Task");
    }
  }
  const lifecycle = decodeLifecycle(field(input, "lifecycle", "$" ), "$.lifecycle");
  if (
    lifecycle.backendStatus !== run.backendStatus ||
    lifecycle.status !== run.status ||
    lifecycle.stage !== run.stage ||
    lifecycle.terminal !== run.terminal
  ) {
    return fail("$.lifecycle", "lifecycle contradicts canonical Run record");
  }
  const review = decodeReviewSummary(field(input, "review", "$" ), "$.review");
  const result = decodeResultSummary(field(input, "result", "$" ), "$.result");
  const artifacts = decodeArtifactSummary(field(input, "artifacts", "$" ), "$.artifacts");
  const proof = decodeProofSummary(field(input, "proof", "$" ), "$.proof");
  const execution = decodeExecutionSummary(field(input, "execution", "$" ), "$.execution");
  const terminal = decodeTerminalState(field(input, "terminal", "$" ), "$.terminal");
  if (
    review.status !== null &&
    !(["PASS", "REVIEW", "BLOCK"] as const).includes(review.status as Phase4ReviewStatus)
  ) {
    return fail("$.review.status", "unknown Review status");
  }
  requireAvailableIdentity(review, review.reviewId, "$.review.review_id", "Review");
  requireAvailableIdentity(review, review.status, "$.review.status", "Review status");
  requireAvailableIdentity(result, result.releasedResultId, "$.result.released_result_id", "result");
  requireAvailableIdentity(
    result,
    result.canonicalRecordId,
    "$.result.canonical_record_id",
    "result canonical record"
  );
  requireAvailableIdentity(result, result.releasedAt, "$.result.released_at", "result release time");
  requireAvailableIdentity(artifacts, artifacts.reportId, "$.artifacts.report_id", "artifact group");
  requireAvailableIdentity(
    execution,
    execution.canonicalRecordId,
    "$.execution.canonical_record_id",
    "execution record"
  );
  if (artifacts.availability.status === "AVAILABLE" && artifacts.representationIds.length === 0) {
    return fail("$.artifacts.representation_ids", "available artifact group requires a representation");
  }
  if (proof.availability.status === "AVAILABLE" && proof.status === null) {
    return fail("$.proof.status", "available Proof summary requires status");
  }
  if (
    run.backendStatus !== "RELEASED" &&
    (result.availability.status === "AVAILABLE" || artifacts.availability.status === "AVAILABLE")
  ) {
    return fail("$.result", "non-RELEASED Run cannot expose released result or artifacts");
  }
  const releaseProofCloses =
    proof.availability.status === "AVAILABLE" &&
    ((proof.policy === "NOT_REQUIRED" &&
      proof.status === "NOT_REQUIRED" &&
      proof.proofRefs.length === 0) ||
      ((proof.policy === "MUST_PROVE" || proof.policy === "MIXED") &&
        proof.status === "VERIFIED" &&
        proof.proofRefs.length > 0));
  const releaseSummaryCloses =
    review.availability.status === "AVAILABLE" &&
    review.reviewId !== null &&
    review.status === "PASS" &&
    result.availability.status === "AVAILABLE" &&
    result.releasedResultId !== null &&
    result.canonicalRecordId !== null &&
    result.releasedAt !== null &&
    artifacts.availability.status === "AVAILABLE" &&
    artifacts.reportId !== null &&
    artifacts.representationIds.length > 0 &&
    artifacts.reportId === result.releasedResultId &&
    execution.availability.status === "AVAILABLE" &&
    execution.canonicalRecordId !== null &&
    execution.canonicalRecordId === result.canonicalRecordId &&
    releaseProofCloses;
  if (run.backendStatus === "RELEASED" && !releaseSummaryCloses) {
    return fail("$", "RELEASED Run lacks complete Review/Result/Artifact/Proof/Execution closure");
  }
  const completedTasks = tasks.filter((task) => task.backendStatus === "COMPLETED").length;
  const allTasksTerminal = tasks.length > 0 && tasks.every(
    (task) => TASK_STATUS_MAP[task.backendStatus].terminal
  );
  const expectedFraction =
    run.backendStatus === "RELEASED"
      ? 1
      : (run.backendStatus === "FAILED" || run.backendStatus === "CANCELLED") && allTasksTerminal
        ? 1
        : tasks.length === 0
          ? 0
          : tasks.reduce((sum, task) => sum + task.progress, 0) / tasks.length;
  const fractionTolerance = Number.EPSILON * Math.max(1, tasks.length, Math.abs(expectedFraction));
  if (
    lifecycle.progress.totalTasks !== tasks.length ||
    lifecycle.progress.completedTasks !== completedTasks ||
    Math.abs(lifecycle.progress.fraction - expectedFraction) > fractionTolerance
  ) {
    return fail("$.lifecycle.progress", "Run progress contradicts authoritative Tasks/status");
  }
  if (
    terminal.isTerminal !== run.terminal ||
    terminal.outcome !== lifecycle.terminalOutcome ||
    (terminal.sequence !== null && terminal.sequence > projectionSequence)
  ) {
    return fail("$.terminal", "terminal state contradicts Run/lifecycle/watermark");
  }
  if (terminal.isTerminal) {
    const finalActivity = activity.at(-1);
    const completedActivityCount = activity.filter(
      (event) => event.type === "run.completed"
    ).length;
    const failedActivityCount = activity.filter((event) => event.type === "run.failed").length;
    if (
      finalActivity === undefined ||
      finalActivity.eventId !== terminal.eventId ||
      finalActivity.sequence !== terminal.sequence ||
      terminal.sequence !== projectionSequence
    ) {
      return fail("$.terminal", "terminal state must close to the final activity and watermark");
    }
    if (run.backendStatus === "RELEASED") {
      if (
        finalActivity.type !== "run.completed" ||
        finalActivity.status !== "RELEASED" ||
        completedActivityCount !== 1 ||
        failedActivityCount !== 0
      ) {
        return fail("$.activity", "RELEASED terminal activity has contradictory semantics");
      }
    } else if (
      finalActivity.type !== "run.failed" ||
      finalActivity.status !== run.backendStatus ||
      failedActivityCount !== 1 ||
      completedActivityCount !== 0
    ) {
      return fail("$.activity", "unsuccessful terminal activity has contradictory semantics");
    }
  }
  for (const [name, availability] of [
    ["review", review.availability],
    ["result", result.availability],
    ["artifacts", artifacts.availability],
    ["proof", proof.availability],
    ["execution", execution.availability]
  ] as const) {
    if (run.terminal && availability.status === "PENDING") {
      return fail(`$.${name}.availability`, "terminal Run resource cannot remain PENDING");
    }
  }
  return freezeDeep({
    projectionSchemaVersion: RUN_PROJECTION_SCHEMA_VERSION,
    projectionRevision,
    projectionSequence,
    generatedAt: decodeRfc3339Utc(field(input, "generated_at", "$" ), "$.generated_at"),
    object,
    run,
    goal,
    confirmedScheme: confirmedScheme as NormalizedScheme & Readonly<{ confirmedAt: string }>,
    plannedGraph,
    actualGraph,
    graphVersion,
    tasks,
    pathChanges,
    activity,
    lifecycle,
    review,
    result,
    artifacts,
    proof,
    execution,
    terminal
  });
}

const FINANCIAL_UNITS = ["RATIO", "PERCENT", "CURRENCY", "COUNT", "SHARES", "INDEX", "MULTIPLE"] as const;
const FINANCIAL_PERIOD_BASES = ["FY", "QUARTER", "TTM", "LTM", "CURRENT", "DAILY"] as const;
const FINANCIAL_ACTUALITIES = ["UNKNOWN", "ACTUAL", "ESTIMATE"] as const;
const TECHNICAL_PRICE_BASES = ["ADJUSTED_CLOSE", "RAW_CLOSE"] as const;
const CORPORATE_ACTION_STATUSES = ["NONE_DETECTED", "RESOLVED", "UNRESOLVED", "UNASSESSED"] as const;

function decodeMethodMetadata(value: unknown, path: string): SafeJsonObject {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, [
    "method", "parameters", "observation_count", "warmup_required", "warmup_satisfied",
    "first_as_of", "last_as_of", "is_wilder", "ema_adjust"
  ], path);
  decodeNonBlankString(field(input, "method", path), `${path}.method`);
  decodeArray(field(input, "parameters", path), `${path}.parameters`).forEach((item, index) => {
    const parameterPath = `${path}.parameters[${index}]`;
    const parameter = decodeObject(item, parameterPath);
    assertOnlyKeys(parameter, ["name", "value"], parameterPath);
    decodeNonBlankString(field(parameter, "name", parameterPath), `${parameterPath}.name`);
    decodeNonBlankString(field(parameter, "value", parameterPath), `${parameterPath}.value`);
  });
  for (const key of ["observation_count", "warmup_required"] as const) {
    const raw = field(input, key, path);
    if (raw !== null) decodeInteger(raw, 1, `${path}.${key}`);
  }
  for (const key of ["warmup_satisfied", "is_wilder", "ema_adjust"] as const) {
    const raw = field(input, key, path);
    if (raw !== null) decodeBoolean(raw, `${path}.${key}`);
  }
  for (const key of ["first_as_of", "last_as_of"] as const) {
    const raw = field(input, key, path);
    if (raw !== null) decodeDate(raw, `${path}.${key}`);
  }
  return decodeSafeJsonObject(input, path);
}

function decodeReleasedMetric(
  value: unknown,
  path: string,
  expectedRunId: string
): ReleasedFinancialMetricProjectionV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, [
    "run_id", "metric_id", "name", "canonical_value", "canonical_unit", "display_value",
    "display_unit", "period", "period_basis", "actuality", "as_of", "currency", "formula_id",
    "capability_id", "calculation_id", "evidence_refs", "claim_refs", "proof", "method_metadata",
    "technical_price_basis", "corporate_action_status", "corporate_action_guard_refs", "limitations"
  ], path);
  const runId = decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`);
  if (runId !== expectedRunId) return fail(`${path}.run_id`, "metric belongs to another Run");
  const proofPath = `${path}.proof`;
  const proofInput = decodeObject(field(input, "proof", path), proofPath);
  assertOnlyKeys(proofInput, ["policy_id", "requirement", "status", "proof_refs"], proofPath);
  const rawMethodMetadata = field(input, "method_metadata", path);
  const rawTechnicalPriceBasis = field(input, "technical_price_basis", path);
  const rawCorporateActionStatus = field(input, "corporate_action_status", path);
  const rawCurrency = field(input, "currency", path);
  return freezeDeep({
    runId,
    metricId: decodeOpaqueId(field(input, "metric_id", path), `${path}.metric_id`),
    name: decodeNonBlankString(field(input, "name", path), `${path}.name`),
    canonicalValue: decodeNonBlankString(field(input, "canonical_value", path), `${path}.canonical_value`),
    canonicalUnit: decodeEnum(field(input, "canonical_unit", path), FINANCIAL_UNITS, `${path}.canonical_unit`),
    displayValue: decodeNonBlankString(field(input, "display_value", path), `${path}.display_value`),
    displayUnit: decodeNonBlankString(field(input, "display_unit", path), `${path}.display_unit`),
    period: decodeNonBlankString(field(input, "period", path), `${path}.period`),
    periodBasis: decodeEnum(field(input, "period_basis", path), FINANCIAL_PERIOD_BASES, `${path}.period_basis`),
    actuality: decodeEnum(field(input, "actuality", path), FINANCIAL_ACTUALITIES, `${path}.actuality`),
    asOf: decodeDate(field(input, "as_of", path), `${path}.as_of`),
    currency: rawCurrency === null ? null : decodeNonBlankString(rawCurrency, `${path}.currency`),
    formulaId: decodeOpaqueId(field(input, "formula_id", path), `${path}.formula_id`),
    capabilityId: decodeOpaqueId(field(input, "capability_id", path), `${path}.capability_id`),
    calculationId: decodeOpaqueId(field(input, "calculation_id", path), `${path}.calculation_id`),
    evidenceRefs: decodeStringArray(field(input, "evidence_refs", path), `${path}.evidence_refs`),
    claimRefs: decodeStringArray(field(input, "claim_refs", path), `${path}.claim_refs`),
    proof: freezeDeep({
      policyId: decodeOpaqueId(field(proofInput, "policy_id", proofPath), `${proofPath}.policy_id`),
      requirement: decodeEnum(field(proofInput, "requirement", proofPath), ["NOT_REQUIRED", "MUST_PROVE"] as const, `${proofPath}.requirement`),
      status: decodeEnum(field(proofInput, "status", proofPath), PROOF_STATUSES, `${proofPath}.status`),
      proofRefs: decodeStringArray(field(proofInput, "proof_refs", proofPath), `${proofPath}.proof_refs`)
    }),
    methodMetadata: rawMethodMetadata === null ? null : decodeMethodMetadata(rawMethodMetadata, `${path}.method_metadata`),
    technicalPriceBasis: rawTechnicalPriceBasis === null ? null : decodeEnum(rawTechnicalPriceBasis, TECHNICAL_PRICE_BASES, `${path}.technical_price_basis`),
    corporateActionStatus: rawCorporateActionStatus === null ? null : decodeEnum(rawCorporateActionStatus, CORPORATE_ACTION_STATUSES, `${path}.corporate_action_status`),
    corporateActionGuardRefs: decodeStringArray(field(input, "corporate_action_guard_refs", path), `${path}.corporate_action_guard_refs`),
    limitations: decodePublicTextArray(field(input, "limitations", path), `${path}.limitations`)
  });
}

function decodeReleasedClaim(value: unknown, path: string, expectedRunId: string): ReleasedClaimProjectionV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, [
    "claim_id", "run_id", "claim_type", "statement", "metric_id", "value", "unit", "period",
    "period_basis", "actuality", "as_of", "currency", "calculation_refs", "evidence_refs", "judgment_refs"
  ], path);
  const runId = decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`);
  if (runId !== expectedRunId) return fail(`${path}.run_id`, "claim belongs to another Run");
  const claimId = decodeOpaqueId(field(input, "claim_id", path), `${path}.claim_id`);
  const claimType = decodeNonBlankString(field(input, "claim_type", path), `${path}.claim_type`);
  const statement = decodePublicText(field(input, "statement", path), `${path}.statement`, false, 4000);
  const metricId = decodeOpaqueId(field(input, "metric_id", path), `${path}.metric_id`);
  const claimValue = decodeNonBlankString(field(input, "value", path), `${path}.value`);
  const period = decodeNonBlankString(field(input, "period", path), `${path}.period`);
  const unit = decodeEnum(field(input, "unit", path), FINANCIAL_UNITS, `${path}.unit`);
  const periodBasis = decodeEnum(field(input, "period_basis", path), FINANCIAL_PERIOD_BASES, `${path}.period_basis`);
  const actuality = decodeEnum(field(input, "actuality", path), FINANCIAL_ACTUALITIES, `${path}.actuality`);
  const asOf = decodeDate(field(input, "as_of", path), `${path}.as_of`);
  const currency = field(input, "currency", path);
  const decodedCurrency = currency === null ? null : decodeNonBlankString(currency, `${path}.currency`);
  const refs = (key: "calculation_refs" | "evidence_refs" | "judgment_refs") =>
    decodeStringArray(field(input, key, path), `${path}.${key}`);
  return freezeDeep({
    claimId, runId, claimType, statement, metricId, value: claimValue, unit, period,
    periodBasis, actuality, asOf, currency: decodedCurrency,
    calculationRefs: refs("calculation_refs"), evidenceRefs: refs("evidence_refs"),
    judgmentRefs: refs("judgment_refs")
  });
}

export function decodeReleasedResultProjection(
  value: unknown,
  expectedRunId: string,
  expectedObjectId?: string
): ReleasedResultProjectionV1 {
  const path = "$";
  const input = decodeObject(value, path);
  assertOnlyKeys(input, [
    "object_id", "run_id", "released_result_id", "canonical_record_id", "released_at", "metrics",
    "claims", "material_calculation_dispositions", "research_source_coverage", "limitations", "availability"
  ], path);
  const runId = decodeOpaqueId(field(input, "run_id", path), "$.run_id");
  if (runId !== decodeOpaqueId(expectedRunId, "expectedRunId")) {
    return fail("$.run_id", "released result belongs to another Run");
  }
  const objectId = decodeOpaqueId(field(input, "object_id", path), "$.object_id");
  if (expectedObjectId !== undefined && objectId !== decodeOpaqueId(expectedObjectId, "expectedObjectId")) {
    return fail("$.object_id", "released result belongs to another Research Object");
  }
  const metrics = decodeArray(field(input, "metrics", path), "$.metrics").map((item, index) =>
    decodeReleasedMetric(item, `$.metrics[${index}]`, runId)
  );
  const claims = decodeArray(field(input, "claims", path), "$.claims").map((item, index) =>
    decodeReleasedClaim(item, `$.claims[${index}]`, runId)
  );
  const dispositions = decodeArray(
    field(input, "material_calculation_dispositions", path),
    "$.material_calculation_dispositions"
  ).map((item, index) => decodeSafeJsonObject(item, `$.material_calculation_dispositions[${index}]`));
  const rawCoverage = field(input, "research_source_coverage", path);
  const availability = decodeAvailability(field(input, "availability", path), "$.availability");
  if (availability.status !== "AVAILABLE") {
    return fail("$.availability.status", "released result body requires AVAILABLE");
  }
  return freezeDeep({
    objectId,
    runId,
    releasedResultId: decodeOpaqueId(field(input, "released_result_id", path), "$.released_result_id"),
    canonicalRecordId: decodeOpaqueId(field(input, "canonical_record_id", path), "$.canonical_record_id"),
    releasedAt: decodeRfc3339Utc(field(input, "released_at", path), "$.released_at"),
    metrics,
    claims,
    materialCalculationDispositions: dispositions,
    researchSourceCoverage: rawCoverage === null ? null : decodeSafeJsonObject(rawCoverage, "$.research_source_coverage"),
    limitations: decodePublicTextArray(field(input, "limitations", path), "$.limitations"),
    availability
  });
}

const RESULTS_SURFACES = ["A_REPORT", "B_FINANCIAL_REVIEW", "C_EXECUTION_RECORD"] as const;
const RESULTS_SURFACE_STATUSES = ["READY", "PARTIAL", "UNAVAILABLE"] as const;
const RESULTS_RELATION_STATUSES = ["AVAILABLE", "UNAVAILABLE", "NOT_APPLICABLE"] as const;
const REVIEW_RELATION_STATUSES = ["AVAILABLE", "NOT_APPLICABLE", "NOT_OBSERVED"] as const;
const EXECUTION_ACTOR_TYPES = ["RESEARCH_LEAD", "SPECIALIST", "SUPPORTING_EXECUTION"] as const;

function decodeResultsAvailability(value: unknown, path: string): ResultsSurfaceAvailability {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["status", "reason_code"], path);
  const status = decodeEnum(field(input, "status", path), RESULTS_SURFACE_STATUSES, `${path}.status`);
  const rawReason = field(input, "reason_code", path);
  const reasonCode = rawReason === null ? null : decodeOpaqueId(rawReason, `${path}.reason_code`);
  if ((status === "READY") !== (reasonCode === null)) {
    return fail(path, "READY has no reason; PARTIAL/UNAVAILABLE require one");
  }
  return freezeDeep({ status, reasonCode });
}

function decodeReviewCheckSelector(value: unknown, path: string): ReviewCheckSelectorV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["review_id", "check_code", "subject_refs"], path);
  const subjectRefs = decodeStringArray(field(input, "subject_refs", path), `${path}.subject_refs`);
  const canonical = [...subjectRefs].sort();
  if (subjectRefs.some((item, index) => item !== canonical[index])) {
    return fail(`${path}.subject_refs`, "selector refs must use deterministic exact ordering");
  }
  return freezeDeep({
    reviewId: decodeOpaqueId(field(input, "review_id", path), `${path}.review_id`),
    checkCode: decodeOpaqueId(field(input, "check_code", path), `${path}.check_code`),
    subjectRefs
  });
}

function decodeResultsRelation(value: unknown, path: string, expectedRunId: string): ResultsRelationRefV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["run_id", "relation_type", "status", "target_ref"], path);
  const runId = decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`);
  if (runId !== expectedRunId) return fail(`${path}.run_id`, "relation belongs to another Run");
  const status = decodeEnum(field(input, "status", path), REVIEW_RELATION_STATUSES, `${path}.status`);
  const rawTarget = field(input, "target_ref", path);
  const targetRef = rawTarget === null ? null : decodeOpaqueId(rawTarget, `${path}.target_ref`);
  if ((status === "AVAILABLE") !== (targetRef !== null)) {
    return fail(path, "relation target is present exactly when AVAILABLE");
  }
  return freezeDeep({
    runId,
    relationType: decodeEnum(field(input, "relation_type", path), [
      "REVIEW_SUBJECT", "CORRECTION", "REPLAN", "PROOF", "TASK", "AGENT_OUTPUT",
      "EXECUTION_EVENT", "REPORT_CONTRIBUTION"
    ] as const, `${path}.relation_type`),
    status,
    targetRef
  });
}

function decodeReportAnchor(value: unknown, path: string, expectedRunId: string): ReportAnchorRefV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["run_id", "report_id", "artifact_id", "anchor"], path);
  const runId = decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`);
  if (runId !== expectedRunId) return fail(`${path}.run_id`, "Report anchor belongs to another Run");
  return freezeDeep({
    runId,
    reportId: decodeOpaqueId(field(input, "report_id", path), `${path}.report_id`),
    artifactId: decodeOpaqueId(field(input, "artifact_id", path), `${path}.artifact_id`),
    anchor: decodeOpaqueId(field(input, "anchor", path), `${path}.anchor`)
  });
}

function decodeReportContribution(
  value: unknown,
  path: string,
  expectedRunId: string
): ReportContributionRefV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, [
    "run_id", "report_id", "artifact_id", "report_anchor", "task_id", "actor_id",
    "agent_output_id", "execution_event_id", "calculation_id", "evidence_refs", "review_id"
  ], path);
  const runId = decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`);
  if (runId !== expectedRunId) return fail(`${path}.run_id`, "Report contribution belongs to another Run");
  const nullableId = (key: string) => {
    const raw = field(input, key, path);
    return raw === null ? null : decodeOpaqueId(raw, `${path}.${key}`);
  };
  return freezeDeep({
    runId,
    reportId: decodeOpaqueId(field(input, "report_id", path), `${path}.report_id`),
    artifactId: decodeOpaqueId(field(input, "artifact_id", path), `${path}.artifact_id`),
    reportAnchor: decodeOpaqueId(field(input, "report_anchor", path), `${path}.report_anchor`),
    taskId: decodeOpaqueId(field(input, "task_id", path), `${path}.task_id`),
    actorId: decodeOpaqueId(field(input, "actor_id", path), `${path}.actor_id`),
    agentOutputId: decodeOpaqueId(field(input, "agent_output_id", path), `${path}.agent_output_id`),
    executionEventId: nullableId("execution_event_id"),
    calculationId: nullableId("calculation_id"),
    evidenceRefs: decodeStringArray(field(input, "evidence_refs", path), `${path}.evidence_refs`).map(
      (item, index) => decodeOpaqueId(item, `${path}.evidence_refs[${index}]`)
    ),
    reviewId: nullableId("review_id")
  });
}

export function decodeReportSurface(
  value: unknown,
  expectedRunId: string,
  expectedObjectId?: string
): ReportSurfaceV1 {
  const path = "$";
  const input = decodeObject(value, path);
  assertOnlyKeys(input, [
    "schema_version", "run_id", "object_id", "released_result_id",
    "canonical_execution_record_id", "report_id", "artifact_id", "title", "company_name",
    "symbol", "as_of", "sections", "anchors", "source_contributions", "availability"
  ], path);
  if (field(input, "schema_version", path) !== "phase4.5-report-surface/v1") {
    return fail("$.schema_version", "unsupported Report surface schema");
  }
  const runId = decodeOpaqueId(field(input, "run_id", path), "$.run_id");
  if (runId !== decodeOpaqueId(expectedRunId, "expectedRunId")) return fail("$.run_id", "Report belongs to another Run");
  const objectId = decodeOpaqueId(field(input, "object_id", path), "$.object_id");
  if (expectedObjectId !== undefined && objectId !== decodeOpaqueId(expectedObjectId, "expectedObjectId")) {
    return fail("$.object_id", "Report belongs to another Object");
  }
  const reportId = decodeOpaqueId(field(input, "report_id", path), "$.report_id");
  const releasedResultId = decodeOpaqueId(field(input, "released_result_id", path), "$.released_result_id");
  const artifactId = decodeOpaqueId(field(input, "artifact_id", path), "$.artifact_id");
  if (reportId !== releasedResultId) return fail("$.report_id", "Report and ReleasedResult identities differ");
  const anchors = decodeArray(field(input, "anchors", path), "$.anchors").map((item, index) =>
    decodeReportAnchor(item, `$.anchors[${index}]`, runId)
  );
  if (new Set(anchors.map((item) => item.anchor)).size !== anchors.length) {
    return fail("$.anchors", "duplicate representation anchor identity");
  }
  if (anchors.some((item) => item.reportId !== reportId || item.artifactId !== artifactId)) {
    return fail("$.anchors", "Report anchor crossed Report/artifact identity");
  }
  const contributions = decodeArray(field(input, "source_contributions", path), "$.source_contributions").map((item, index) =>
    decodeReportContribution(item, `$.source_contributions[${index}]`, runId)
  );
  if (contributions.some((item) => item.reportId !== reportId || item.artifactId !== artifactId)) {
    return fail("$.source_contributions", "Report contribution crossed Report/artifact identity");
  }
  const sections = decodeArray(field(input, "sections", path), "$.sections").map((item, index) => {
    const sectionPath = `$.sections[${index}]`;
    const section = decodeObject(item, sectionPath);
    assertOnlyKeys(section, ["section_key", "title", "anchor"], sectionPath);
    const rawAnchor = field(section, "anchor", sectionPath);
    return freezeDeep({
      sectionKey: decodeOpaqueId(field(section, "section_key", sectionPath), `${sectionPath}.section_key`),
      title: decodePublicText(field(section, "title", sectionPath), `${sectionPath}.title`, false, 800),
      anchor: rawAnchor === null ? null : decodeReportAnchor(rawAnchor, `${sectionPath}.anchor`, runId)
    });
  });
  if (sections.some((item) => item.anchor !== null &&
    (item.anchor.reportId !== reportId || item.anchor.artifactId !== artifactId))) {
    return fail("$.sections", "Report section anchor crossed Report/artifact identity");
  }
  return freezeDeep({
    schemaVersion: "phase4.5-report-surface/v1",
    runId, objectId, releasedResultId,
    canonicalExecutionRecordId: decodeOpaqueId(field(input, "canonical_execution_record_id", path), "$.canonical_execution_record_id"),
    reportId, artifactId,
    title: decodePublicText(field(input, "title", path), "$.title", false, 800),
    companyName: decodePublicText(field(input, "company_name", path), "$.company_name", false, 800),
    symbol: decodeOpaqueId(field(input, "symbol", path), "$.symbol"),
    asOf: decodeDate(field(input, "as_of", path), "$.as_of"),
    sections, anchors, sourceContributions: contributions,
    availability: decodeResultsAvailability(field(input, "availability", path), "$.availability")
  });
}

export function decodeReportArtifactGroup(
  value: unknown,
  expectedRunId: string,
  expectedObjectId?: string
): ReportArtifactGroupV1 {
  const path = "$";
  const input = decodeObject(value, path);
  assertOnlyKeys(input, [
    "schema_version", "object_id", "run_id", "report_id", "canonical_record_id",
    "released_result_id", "release_policy_version", "artifact_policy_version",
    "anchor_manifest_id", "anchor_manifest_sha256", "availability", "representations"
  ], path);
  if (field(input, "schema_version", path) !== "phase4-report-artifacts/v1") {
    return fail("$.schema_version", "unsupported Report artifact schema");
  }
  const runId = decodeOpaqueId(field(input, "run_id", path), "$.run_id");
  if (runId !== decodeOpaqueId(expectedRunId, "expectedRunId")) return fail("$.run_id", "artifacts belong to another Run");
  const objectId = decodeOpaqueId(field(input, "object_id", path), "$.object_id");
  if (expectedObjectId !== undefined && objectId !== decodeOpaqueId(expectedObjectId, "expectedObjectId")) {
    return fail("$.object_id", "artifacts belong to another Object");
  }
  const reportId = decodeOpaqueId(field(input, "report_id", path), "$.report_id");
  const releasedResultId = decodeOpaqueId(field(input, "released_result_id", path), "$.released_result_id");
  if (reportId !== releasedResultId) return fail("$.report_id", "Report and ReleasedResult identities differ");
  if (field(input, "release_policy_version", path) !== "phase4-release-eligibility/v1" ||
      field(input, "artifact_policy_version", path) !== "phase4-html-required-pdf-optional/v1") {
    return fail(path, "unsupported Report artifact policy");
  }
  const rawRepresentations = decodeArray(field(input, "representations", path), "$.representations");
  if (rawRepresentations.length !== 2) return fail("$.representations", "exact HTML/PDF slots are required");
  const representations = rawRepresentations.map((item, index): ReportArtifactRepresentationV1 => {
    const itemPath = `$.representations[${index}]`;
    const representation = decodeObject(item, itemPath);
    assertOnlyKeys(representation, [
      "format", "required_for_release", "content_type", "availability", "artifact_id",
      "safe_failure_code", "generation_attempt_id", "generation_attempt_count", "sha256",
      "size_bytes", "renderer", "generated_at", "authorized_ref"
    ], itemPath);
    const format = decodeEnum(field(representation, "format", itemPath), ["HTML", "PDF"] as const, `${itemPath}.format`);
    const availability = decodeAvailability(field(representation, "availability", itemPath), `${itemPath}.availability`);
    const nullableText = (key: string) => {
      const raw = field(representation, key, itemPath);
      return raw === null ? null : decodeNonBlankString(raw, `${itemPath}.${key}`);
    };
    const rawRenderer = field(representation, "renderer", itemPath);
    let renderer: RendererIdentityV1 | null = null;
    if (rawRenderer !== null) {
      const rendererInput = decodeObject(rawRenderer, `${itemPath}.renderer`);
      assertOnlyKeys(rendererInput, ["renderer_id", "renderer_version"], `${itemPath}.renderer`);
      renderer = freezeDeep({
        rendererId: decodeOpaqueId(field(rendererInput, "renderer_id", `${itemPath}.renderer`), `${itemPath}.renderer.renderer_id`),
        rendererVersion: decodeNonBlankString(field(rendererInput, "renderer_version", `${itemPath}.renderer`), `${itemPath}.renderer.renderer_version`)
      });
    }
    const requiredForRelease = decodeBoolean(field(representation, "required_for_release", itemPath), `${itemPath}.required_for_release`);
    const contentType = decodeEnum(field(representation, "content_type", itemPath), ["text/html; charset=utf-8", "application/pdf"] as const, `${itemPath}.content_type`);
    if ((format === "HTML") !== requiredForRelease || (format === "HTML") !== (contentType === "text/html; charset=utf-8")) {
      return fail(itemPath, "representation format policy mismatch");
    }
    const artifactId = nullableText("artifact_id");
    const authorizedRef = nullableText("authorized_ref");
    const attempts = decodeInteger(field(representation, "generation_attempt_count", itemPath), 0, `${itemPath}.generation_attempt_count`);
    if (availability.status === "AVAILABLE" && (artifactId === null || authorizedRef === null || attempts < 1 || renderer === null)) {
      return fail(itemPath, "AVAILABLE representation lacks immutable metadata");
    }
    if (authorizedRef !== null && (!authorizedRef.startsWith(`/api/research-runs/${encodeURIComponent(runId)}/`) || authorizedRef.includes("://") || authorizedRef.includes("?"))) {
      return fail(`${itemPath}.authorized_ref`, "authorized_ref must be an exact same-origin Run resource");
    }
    return freezeDeep({ format, requiredForRelease, contentType, availability, artifactId,
      generationAttemptCount: attempts, authorizedRef, renderer });
  });
  if (representations[0].format !== "HTML" || representations[1].format !== "PDF") {
    return fail("$.representations", "representations are not in canonical HTML/PDF order");
  }
  return freezeDeep({
    schemaVersion: "phase4-report-artifacts/v1", objectId, runId, reportId,
    canonicalRecordId: decodeOpaqueId(field(input, "canonical_record_id", path), "$.canonical_record_id"),
    releasedResultId, availability: decodeAvailability(field(input, "availability", path), "$.availability"),
    representations: representations as unknown as readonly [ReportArtifactRepresentationV1, ReportArtifactRepresentationV1]
  });
}

export function decodeFinancialReviewSurface(
  value: unknown,
  expectedRunId: string,
  expectedObjectId?: string
): FinancialReviewSurfaceV1 {
  const path = "$";
  const input = decodeObject(value, path);
  assertOnlyKeys(input, [
    "schema_version", "run_id", "object_id", "released_result_id",
    "canonical_execution_record_id", "review_id", "reviewer", "verdict", "checks", "availability"
  ], path);
  if (field(input, "schema_version", path) !== "phase4.5-financial-review-surface/v1") {
    return fail("$.schema_version", "unsupported Financial Review surface schema");
  }
  const runId = decodeOpaqueId(field(input, "run_id", path), "$.run_id");
  if (runId !== decodeOpaqueId(expectedRunId, "expectedRunId")) return fail("$.run_id", "Review belongs to another Run");
  const objectId = decodeOpaqueId(field(input, "object_id", path), "$.object_id");
  if (expectedObjectId !== undefined && objectId !== decodeOpaqueId(expectedObjectId, "expectedObjectId")) return fail("$.object_id", "Review belongs to another Object");
  const reviewId = decodeOpaqueId(field(input, "review_id", path), "$.review_id");
  const selectors = new Set<string>();
  const checks = decodeArray(field(input, "checks", path), "$.checks").map((item, index) => {
    const checkPath = `$.checks[${index}]`;
    const check = decodeObject(item, checkPath);
    assertOnlyKeys(check, ["selector", "status", "safe_explanation", "input_refs", "output_refs"], checkPath);
    const selector = decodeReviewCheckSelector(field(check, "selector", checkPath), `${checkPath}.selector`);
    if (selector.reviewId !== reviewId) return fail(`${checkPath}.selector.review_id`, "selector names another ReviewRecord");
    const key = JSON.stringify([selector.checkCode, selector.subjectRefs]);
    if (selectors.has(key)) return fail(`${checkPath}.selector`, "ambiguous scoped selector");
    selectors.add(key);
    const explanation = field(check, "safe_explanation", checkPath);
    return freezeDeep({
      selector,
      status: decodeEnum(field(check, "status", checkPath), ["PASS", "REVIEW", "BLOCK"] as const, `${checkPath}.status`),
      safeExplanation: explanation === null ? null : decodePublicText(explanation, `${checkPath}.safe_explanation`, false, 800),
      inputRefs: decodeArray(field(check, "input_refs", checkPath), `${checkPath}.input_refs`).map((ref, refIndex) => decodeResultsRelation(ref, `${checkPath}.input_refs[${refIndex}]`, runId)),
      outputRefs: decodeArray(field(check, "output_refs", checkPath), `${checkPath}.output_refs`).map((ref, refIndex) => decodeResultsRelation(ref, `${checkPath}.output_refs[${refIndex}]`, runId))
    });
  });
  if (checks.length === 0) return fail("$.checks", "Financial Review requires persisted checks");
  return freezeDeep({
    schemaVersion: "phase4.5-financial-review-surface/v1",
    runId, objectId,
    releasedResultId: decodeOpaqueId(field(input, "released_result_id", path), "$.released_result_id"),
    canonicalExecutionRecordId: decodeOpaqueId(field(input, "canonical_execution_record_id", path), "$.canonical_execution_record_id"),
    reviewId,
    reviewer: decodePublicText(field(input, "reviewer", path), "$.reviewer", false, 800),
    verdict: decodeEnum(field(input, "verdict", path), ["PASS", "REVIEW", "BLOCK"] as const, "$.verdict"),
    checks,
    availability: decodeResultsAvailability(field(input, "availability", path), "$.availability")
  });
}

function decodeExecutionActorSummary(value: unknown, path: string, runId: string): ExecutionActorSummaryV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["run_id", "actor_id", "actor_type", "display_role", "status", "event_count", "record_count"], path);
  const ownedRunId = decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`);
  if (ownedRunId !== runId) return fail(`${path}.run_id`, "actor belongs to another Run");
  return freezeDeep({
    runId: ownedRunId,
    actorId: decodeOpaqueId(field(input, "actor_id", path), `${path}.actor_id`),
    actorType: decodeEnum(field(input, "actor_type", path), EXECUTION_ACTOR_TYPES, `${path}.actor_type`),
    displayRole: decodePublicText(field(input, "display_role", path), `${path}.display_role`, false, 800),
    status: decodeOpaqueId(field(input, "status", path), `${path}.status`),
    eventCount: decodeInteger(field(input, "event_count", path), 0, `${path}.event_count`),
    recordCount: decodeInteger(field(input, "record_count", path), 0, `${path}.record_count`)
  });
}

function decodeExecutionActorDetail(value: unknown, path: string, runId: string): ExecutionActorDetailV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, [
    "run_id", "actor_id", "actor_type", "input_refs", "observable_process", "outputs",
    "report_contributions", "quarantined_input_ref_count"
  ], path);
  const ownedRunId = decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`);
  if (ownedRunId !== runId) return fail(`${path}.run_id`, "actor detail belongs to another Run");
  const inputRefs = decodeArray(field(input, "input_refs", path), `${path}.input_refs`).map((item, index) => {
    const itemPath = `${path}.input_refs[${index}]`;
    const ref = decodeObject(item, itemPath);
    assertOnlyKeys(ref, ["run_id", "ref_id"], itemPath);
    const refRunId = decodeOpaqueId(field(ref, "run_id", itemPath), `${itemPath}.run_id`);
    if (refRunId !== runId) return fail(`${itemPath}.run_id`, "input ref belongs to another Run");
    return freezeDeep({ runId: refRunId, refId: decodeOpaqueId(field(ref, "ref_id", itemPath), `${itemPath}.ref_id`) });
  });
  const observableProcess = decodeArray(field(input, "observable_process", path), `${path}.observable_process`).map((item, index) => {
    const itemPath = `${path}.observable_process[${index}]`;
    const record = decodeObject(item, itemPath);
    assertOnlyKeys(record, ["run_id", "event_id", "task_id", "event_type", "status"], itemPath);
    const recordRunId = decodeOpaqueId(field(record, "run_id", itemPath), `${itemPath}.run_id`);
    if (recordRunId !== runId) return fail(`${itemPath}.run_id`, "process record belongs to another Run");
    const rawTask = field(record, "task_id", itemPath);
    return freezeDeep({
      runId: recordRunId,
      eventId: decodeOpaqueId(field(record, "event_id", itemPath), `${itemPath}.event_id`),
      taskId: rawTask === null ? null : decodeOpaqueId(rawTask, `${itemPath}.task_id`),
      eventType: decodeOpaqueId(field(record, "event_type", itemPath), `${itemPath}.event_type`),
      status: decodeOpaqueId(field(record, "status", itemPath), `${itemPath}.status`)
    });
  });
  const outputs = decodeArray(field(input, "outputs", path), `${path}.outputs`).map((item, index) => {
    const itemPath = `${path}.outputs[${index}]`;
    const output = decodeObject(item, itemPath);
    assertOnlyKeys(output, ["run_id", "output_id", "task_id", "status", "summary", "key_findings", "risks", "limitations"], itemPath);
    const outputRunId = decodeOpaqueId(field(output, "run_id", itemPath), `${itemPath}.run_id`);
    if (outputRunId !== runId) return fail(`${itemPath}.run_id`, "output belongs to another Run");
    const rawSummary = field(output, "summary", itemPath);
    return freezeDeep({
      runId: outputRunId,
      outputId: decodeOpaqueId(field(output, "output_id", itemPath), `${itemPath}.output_id`),
      taskId: decodeOpaqueId(field(output, "task_id", itemPath), `${itemPath}.task_id`),
      status: decodeEnum(field(output, "status", itemPath), ["SUCCESS", "FAILED"] as const, `${itemPath}.status`),
      summary: rawSummary === null ? null : decodePublicText(rawSummary, `${itemPath}.summary`, false, 800),
      keyFindings: decodePublicTextArray(field(output, "key_findings", itemPath), `${itemPath}.key_findings`),
      risks: decodePublicTextArray(field(output, "risks", itemPath), `${itemPath}.risks`),
      limitations: decodePublicTextArray(field(output, "limitations", itemPath), `${itemPath}.limitations`)
    });
  });
  const actorId = decodeOpaqueId(field(input, "actor_id", path), `${path}.actor_id`);
  const reportContributions = decodeArray(
    field(input, "report_contributions", path),
    `${path}.report_contributions`
  ).map((item, index) =>
    decodeReportContribution(item, `${path}.report_contributions[${index}]`, runId)
  );
  if (reportContributions.some((item) => item.actorId !== actorId)) {
    return fail(`${path}.report_contributions`, "Report contribution belongs to another actor");
  }
  return freezeDeep({
    runId: ownedRunId,
    actorId,
    actorType: decodeEnum(field(input, "actor_type", path), EXECUTION_ACTOR_TYPES, `${path}.actor_type`),
    inputRefs,
    observableProcess,
    outputs,
    reportContributions,
    quarantinedInputRefCount: decodeInteger(field(input, "quarantined_input_ref_count", path), 0, `${path}.quarantined_input_ref_count`)
  });
}

export function decodeExecutionRecordSurface(
  value: unknown,
  expectedRunId: string,
  expectedObjectId?: string
): ExecutionRecordSurfaceV1 {
  const path = "$";
  const input = decodeObject(value, path);
  assertOnlyKeys(input, [
    "schema_version", "run_id", "object_id", "released_result_id",
    "canonical_execution_record_id", "actors", "actor_details", "availability"
  ], path);
  if (field(input, "schema_version", path) !== "phase4.5-execution-record-surface/v1") return fail("$.schema_version", "unsupported Execution surface schema");
  const runId = decodeOpaqueId(field(input, "run_id", path), "$.run_id");
  if (runId !== decodeOpaqueId(expectedRunId, "expectedRunId")) return fail("$.run_id", "Execution belongs to another Run");
  const objectId = decodeOpaqueId(field(input, "object_id", path), "$.object_id");
  if (expectedObjectId !== undefined && objectId !== decodeOpaqueId(expectedObjectId, "expectedObjectId")) return fail("$.object_id", "Execution belongs to another Object");
  const actors = decodeArray(field(input, "actors", path), "$.actors").map((item, index) => decodeExecutionActorSummary(item, `$.actors[${index}]`, runId));
  const actorKeys = new Set(actors.map((item) => `${item.actorType}:${item.actorId}`));
  if (actorKeys.size !== actors.length) return fail("$.actors", "duplicate execution actor identity");
  const actorDetails = decodeArray(field(input, "actor_details", path), "$.actor_details").map((item, index) => decodeExecutionActorDetail(item, `$.actor_details[${index}]`, runId));
  const detailKeys = new Set(actorDetails.map((item) => `${item.actorType}:${item.actorId}`));
  if (detailKeys.size !== actorDetails.length) return fail("$.actor_details", "duplicate actor detail identity");
  if (actorDetails.some((item) => !actorKeys.has(`${item.actorType}:${item.actorId}`))) return fail("$.actor_details", "actor detail is absent from catalog");
  return freezeDeep({
    schemaVersion: "phase4.5-execution-record-surface/v1",
    runId, objectId,
    releasedResultId: decodeOpaqueId(field(input, "released_result_id", path), "$.released_result_id"),
    canonicalExecutionRecordId: decodeOpaqueId(field(input, "canonical_execution_record_id", path), "$.canonical_execution_record_id"),
    actors, actorDetails,
    availability: decodeResultsAvailability(field(input, "availability", path), "$.availability")
  });
}

function decodeCrossViewEndpoint(value: unknown, path: string, runId: string): CrossViewEndpointV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["surface", "run_id", "identity_id", "artifact_id", "target_anchor", "check_selector"], path);
  const ownedRunId = decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`);
  if (ownedRunId !== runId) return fail(`${path}.run_id`, "CrossView endpoint belongs to another Run");
  const nullableId = (key: string) => {
    const raw = field(input, key, path);
    return raw === null ? null : decodeOpaqueId(raw, `${path}.${key}`);
  };
  const surface = decodeEnum(field(input, "surface", path), RESULTS_SURFACES, `${path}.surface`);
  const identityId = decodeOpaqueId(field(input, "identity_id", path), `${path}.identity_id`);
  const artifactId = nullableId("artifact_id");
  const targetAnchor = nullableId("target_anchor");
  const rawSelector = field(input, "check_selector", path);
  const checkSelector = rawSelector === null ? null : decodeReviewCheckSelector(rawSelector, `${path}.check_selector`);
  if (artifactId !== null && surface !== "A_REPORT") return fail(path, "Report artifact identity belongs on another surface");
  if (targetAnchor !== null && (surface !== "A_REPORT" || artifactId === null)) return fail(path, "Report anchor lacks representation identity");
  if (checkSelector !== null && (surface !== "B_FINANCIAL_REVIEW" || checkSelector.reviewId !== identityId)) return fail(path, "selector names another Review endpoint");
  return freezeDeep({ surface, runId: ownedRunId, identityId, artifactId, targetAnchor, checkSelector });
}

function decodeSurfaceRef(value: unknown, path: string, runId: string, objectId: string, resultId: string, canonicalId: string): ResultsSurfaceRefV1 {
  const input = decodeObject(value, path);
  assertOnlyKeys(input, ["surface", "run_id", "object_id", "released_result_id", "canonical_execution_record_id", "surface_id", "href", "availability"], path);
  const ownedRunId = decodeOpaqueId(field(input, "run_id", path), `${path}.run_id`);
  const ownedObjectId = decodeOpaqueId(field(input, "object_id", path), `${path}.object_id`);
  const ownedResultId = decodeOpaqueId(field(input, "released_result_id", path), `${path}.released_result_id`);
  const ownedCanonicalId = decodeOpaqueId(field(input, "canonical_execution_record_id", path), `${path}.canonical_execution_record_id`);
  if (ownedRunId !== runId || ownedObjectId !== objectId || ownedResultId !== resultId || ownedCanonicalId !== canonicalId) return fail(path, "Results surface crossed workspace identity");
  const surface = decodeEnum(field(input, "surface", path), RESULTS_SURFACES, `${path}.surface`);
  const href = decodeNonBlankString(field(input, "href", path), `${path}.href`);
  const suffix = surface === "A_REPORT" ? "report-view" :
    surface === "B_FINANCIAL_REVIEW" ? "review-view" : "execution-view";
  if (href !== `/api/research-runs/${encodeURIComponent(runId)}/${suffix}`) {
    return fail(`${path}.href`, "surface href must be exact-run same-origin");
  }
  return freezeDeep({
    surface,
    runId: ownedRunId, objectId: ownedObjectId, releasedResultId: ownedResultId,
    canonicalExecutionRecordId: ownedCanonicalId,
    surfaceId: decodeOpaqueId(field(input, "surface_id", path), `${path}.surface_id`),
    href,
    availability: decodeResultsAvailability(field(input, "availability", path), `${path}.availability`)
  });
}

export function decodeResultsWorkspace(
  value: unknown,
  expectedRunId: string,
  expectedObjectId?: string
): ResultsWorkspaceV1 {
  const path = "$";
  const input = decodeObject(value, path);
  assertOnlyKeys(input, [
    "schema_version", "run_id", "object_id", "as_of", "run_status", "released_result_id",
    "canonical_execution_record_id", "report_surface", "review_surface", "execution_surface", "cross_view_refs"
  ], path);
  if (field(input, "schema_version", path) !== "phase4.5-results-workspace/v1") return fail("$.schema_version", "unsupported Results Workspace schema");
  const runId = decodeOpaqueId(field(input, "run_id", path), "$.run_id");
  if (runId !== decodeOpaqueId(expectedRunId, "expectedRunId")) return fail("$.run_id", "Results Workspace belongs to another Run");
  const objectId = decodeOpaqueId(field(input, "object_id", path), "$.object_id");
  if (expectedObjectId !== undefined && objectId !== decodeOpaqueId(expectedObjectId, "expectedObjectId")) return fail("$.object_id", "Results Workspace belongs to another Object");
  const resultId = decodeOpaqueId(field(input, "released_result_id", path), "$.released_result_id");
  const canonicalId = decodeOpaqueId(field(input, "canonical_execution_record_id", path), "$.canonical_execution_record_id");
  const reportSurface = decodeSurfaceRef(field(input, "report_surface", path), "$.report_surface", runId, objectId, resultId, canonicalId);
  const reviewSurface = decodeSurfaceRef(field(input, "review_surface", path), "$.review_surface", runId, objectId, resultId, canonicalId);
  const executionSurface = decodeSurfaceRef(field(input, "execution_surface", path), "$.execution_surface", runId, objectId, resultId, canonicalId);
  if (reportSurface.surface !== "A_REPORT" || reviewSurface.surface !== "B_FINANCIAL_REVIEW" || executionSurface.surface !== "C_EXECUTION_RECORD") return fail("$", "Results surfaces occupy incorrect slots");
  const crossViewRefs = decodeArray(field(input, "cross_view_refs", path), "$.cross_view_refs").map((item, index) => {
    const refPath = `$.cross_view_refs[${index}]`;
    const ref = decodeObject(item, refPath);
    assertOnlyKeys(ref, ["run_id", "source", "target", "status", "reason_code"], refPath);
    const refRunId = decodeOpaqueId(field(ref, "run_id", refPath), `${refPath}.run_id`);
    if (refRunId !== runId) return fail(`${refPath}.run_id`, "CrossViewRef belongs to another Run");
    const status = decodeEnum(field(ref, "status", refPath), RESULTS_RELATION_STATUSES, `${refPath}.status`);
    const rawReason = field(ref, "reason_code", refPath);
    const reasonCode = rawReason === null ? null : decodeOpaqueId(rawReason, `${refPath}.reason_code`);
    if ((status === "AVAILABLE") !== (reasonCode === null)) return fail(refPath, "CrossView status/reason mismatch");
    return freezeDeep({
      runId: refRunId,
      source: decodeCrossViewEndpoint(field(ref, "source", refPath), `${refPath}.source`, runId),
      target: decodeCrossViewEndpoint(field(ref, "target", refPath), `${refPath}.target`, runId),
      status,
      reasonCode
    });
  });
  const surfaceIds: Readonly<Record<ResultsSurfaceName, string>> = {
    A_REPORT: reportSurface.surfaceId,
    B_FINANCIAL_REVIEW: reviewSurface.surfaceId,
    C_EXECUTION_RECORD: executionSurface.surfaceId
  };
  if (crossViewRefs.some((item) =>
    item.source.identityId !== surfaceIds[item.source.surface] ||
    item.target.identityId !== surfaceIds[item.target.surface]
  )) return fail("$.cross_view_refs", "CrossViewRef names another surface identity");
  return freezeDeep({
    schemaVersion: "phase4.5-results-workspace/v1",
    runId, objectId,
    asOf: decodeDate(field(input, "as_of", path), "$.as_of"),
    runStatus: decodeEnum(field(input, "run_status", path), BACKEND_RUN_STATUSES, "$.run_status"),
    releasedResultId: resultId,
    canonicalExecutionRecordId: canonicalId,
    reportSurface, reviewSurface, executionSurface, crossViewRefs
  });
}

/** @deprecated V8 demo-only compatibility. Never use at the Phase 4 HTTP boundary. */
export type RunStatus =
  | "PLANNING"
  | "RESEARCHING"
  | "REVIEWING"
  | "GENERATING_REPORT"
  | "RESULT_PREPARING"
  | "ACTION_REQUIRED"
  | "COMPLETED"
  | "FAILED";

/** @deprecated V8 demo-only compatibility. Never use at the Phase 4 HTTP boundary. */
export type RunStage = "plan" | "research" | "review" | "report" | "completed";
export type ResearchStep = "collect" | "prepare" | "financial" | "analysis" | "synthesis";
/** @deprecated V8 demo-only compatibility. Never use at the Phase 4 HTTP boundary. */
export type TaskStatus = "WAITING" | "READY" | "RUNNING" | "SELF_CORRECTING" | "COMPLETED" | "BLOCKED" | "FAILED";
/**
 * Mutation types implemented by the pre-integration projection. Future human
 * gate / rollback types are intentionally not advertised until they have a
 * real event, state transition, recovery path, and regression journey.
 */
export type PathChangeType = "SELF_CORRECTION" | "ADD_TASK" | "CHANGE_DEPENDENCY";
/** @deprecated V8 demo-only compatibility. `PASS_WITH_UNCERTAINTY` is not a frozen Phase 4 verdict. */
export type ReviewStatus = "PASS" | "PASS_WITH_UNCERTAINTY" | "REVIEW" | "BLOCK" | "RESOLVED";
/** @deprecated V8 demo-only compatibility. */
export type ProofStatus = "NOT_REQUIRED" | "REQUIRED_PENDING" | "PROVING" | "VALID" | "INVALID" | "ERROR";
export type ScenarioId = "scene-01-full" | "scene-02-dynamic" | "scene-03-correction" | "scene-04-trace" | "scene-05-object-history" | "scene-06-incremental" | "subject-safe";

export interface OwnedIdentity {
  objectId: string;
  symbol: string;
  runId: string;
}

export interface TraceContext extends OwnedIdentity {
  claimId: string;
  taskId?: string;
  originView: "run" | "results" | "object";
  originTab?: "report" | "review" | "execution" | "overview" | "history" | "view";
  reportAnchor?: string;
  reviewAnchor?: string;
  executionAnchor?: string;
  taskAnchor?: string;
}

export interface ResearchObject {
  id: string;
  symbol: string;
  name: string;
  exchange: string;
  sector?: string;
  industry?: string;
  currency?: string;
  country?: string;
  dataStatus: "READY" | "REVIEW" | "PENDING";
  price?: string;
  revenue?: string;
  revenueGrowth?: string;
  forwardPe?: string;
  runCount: number;
  latestRunStatus?: RunStatus;
  latestReleasedRunId?: string;
}

export interface ResearchTaskDraft {
  id: string;
  name: string;
  agentLabel?: string;
  question?: string;
  dataRefs?: string[];
  dependsOn?: string[];
}

export interface ResearchMemory {
  sourceRunId: string;
  reviewedClaims: number;
  verifiedMetrics: string[];
  historicalIssues: string[];
  priorPathAdjustments: string[];
}

export interface IncrementalStrategy {
  reuse: string[];
  refresh: string[];
  revalidate: string[];
  prevent: string[];
  metrics: Array<{ label: string; previous?: string; current: string }>;
}

export interface ResearchPlan {
  planId: string;
  objectId: string;
  symbol: string;
  goal: string;
  title: string;
  mode: "FULL" | "INCREMENTAL";
  questions: string[];
  scopes: string[];
  dataRequirements: string[];
  methods: string[];
  tasks: ResearchTaskDraft[];
  generatedAt: string;
  memory?: ResearchMemory;
  incrementalStrategy?: IncrementalStrategy;
}

export interface ObservableTaskEvent {
  id: string;
  title: string;
  meta?: string;
  status: "DONE" | "LIVE" | "WAITING" | "WARNING";
  timestamp?: string;
  anchor?: string;
}

export interface CapabilityLifecycleStep {
  status: "PREPARING" | "VALIDATING" | "APPROVED" | "FAILED" | "RESUMED";
  label: string;
  timestamp?: string;
}

export interface SupportingRuntimeActivity {
  capabilityId: string;
  kind: "CAPABILITY_GAP" | "CAPABILITY_PREPARATION" | "CAPABILITY_VALIDATION" | "WAITING_FOR_CAPABILITY";
  label: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  lifecycle: CapabilityLifecycleStep[];
}

export interface ResearchTask extends OwnedIdentity {
  id: string;
  name: string;
  agentLabel?: string;
  skillLabel?: string;
  toolLabels?: string[];
  status: TaskStatus;
  progress?: number;
  duration?: string;
  summary?: string;
  question?: string;
  dataRefs?: string[];
  evidenceRefs?: string[];
  calculationRefs?: string[];
  analysisSummary?: string;
  conclusion?: string;
  correctionSummary?: string;
  replanSummary?: string;
  errorSummary?: string;
  isDynamic?: boolean;
  dependsOn?: string[];
  supportingActivity?: SupportingRuntimeActivity;
  observableEvents?: ObservableTaskEvent[];
}

export interface PathChange {
  changeId: string;
  type: PathChangeType;
  reason: string;
  status: "OPEN" | "APPROVED" | "APPLIED" | "RESOLVED";
  triggerTaskId?: string;
  addedTaskIds?: string[];
  affectedTaskIds?: string[];
  createdAt: string;
  resolvedAt?: string;
}

export interface ProjectionFact {
  label: string;
  value: string;
  status: "AVAILABLE" | "PENDING" | "UNAVAILABLE";
}

export interface ResearchRun {
  id: string;
  objectId: string;
  company: string;
  symbol: string;
  scenarioId: ScenarioId;
  mode: "FULL" | "INCREMENTAL";
  title: string;
  goal: string;
  status: RunStatus;
  stage: RunStage;
  researchStep: ResearchStep;
  progress: number;
  currentActivity?: string;
  initialTasks: ResearchTask[];
  tasks: ResearchTask[];
  pathChanges: PathChange[];
  graphVersion: number;
  createdAt: string;
  updatedAt: string;
  proofStatus: ProofStatus;
  projectionFacts: ProjectionFact[];
  memory?: ResearchMemory;
  incrementalStrategy?: IncrementalStrategy;
  writeback?: { status: "PENDING" | "COMPLETED"; items: string[]; note: string };
}

export interface ResearchClaim extends OwnedIdentity {
  claimId: string;
  title: string;
  claimType: "DETERMINISTIC_CALCULATION" | "AI_FINANCIAL_JUDGMENT";
  summary: string;
  reportAnchor?: string;
  reviewAnchor?: string;
  executionAnchor?: string;
  taskAnchor?: string;
  taskId: string;
  evidenceRefs: string[];
  calculationRefs: string[];
  reviewStatus: Exclude<ReviewStatus, "RESOLVED">;
  proofStatus: ProofStatus;
}

export interface ReviewRecord extends OwnedIdentity {
  reviewId: string;
  claimId?: string;
  title: string;
  status: ReviewStatus;
  kind: "CLAIM" | "EXCEPTION";
  summary: string;
  taskId?: string;
  anchor: string;
  correctionPath?: string[];
  resolvedAt?: string;
}

export interface FinancialMetric {
  key: string;
  label: string;
  values: Array<{ period: string; value: string; estimate: boolean }>;
}

export interface ResearchViewVersion {
  runId: string;
  asOf: string;
  growth: string;
  profitability: string;
  valuation: string;
  risk: string;
  catalysts: string[];
}

export interface ObjectComparisonItem {
  id: string;
  category: "METRIC_CHANGED" | "JUDGMENT_CHANGED" | "CLAIM_REVISED" | "CLAIM_UNCHANGED" | "NEW_RISK" | "NEW_CATALYST";
  label: string;
  previousValue?: string;
  currentValue: string;
  explanation: string;
  claimId?: string;
  sourceRunId: string;
}

/** @deprecated V8 demo-only compatibility. */
export interface ResearchObjectDetail {
  object: ResearchObject;
  latestReleasedRunId?: string;
  financials: FinancialMetric[];
  runs: ResearchRun[];
  researchViews: ResearchViewVersion[];
  comparison: { previousRunId: string; currentRunId: string; items: ObjectComparisonItem[] };
}

export interface ReportSection {
  id: string;
  title: string;
  paragraphs?: Array<{ text: string; claimId?: string }>;
  table?: { headers: string[]; rows: string[][] };
}

export interface ReportArtifact extends OwnedIdentity {
  artifactId: string;
  source: "DEMO" | "BACKEND";
  status: "PENDING" | "READY" | "ERROR" | "NOT_GENERATED";
  renderer: string;
  generatedAt?: string;
  htmlDownloadUrl?: string;
  htmlFilename?: string;
  pdfDownloadUrl?: string;
  pdfFilename?: string;
  pdfUnavailableReason?: string;
  preview: {
    company: string;
    symbol: string;
    date: string;
    rating: string;
    price: string;
    target: string;
    thesisClaimId?: string;
    thesis: string;
    metrics: Array<{ label: string; value: string; claimId?: string }>;
    risks: Array<{ text: string; claimId?: string }>;
    sections: ReportSection[];
  };
}

export interface ExecutionEntry {
  taskId: string;
  title: string;
  summary: string;
  anchor: string;
  claimIds: string[];
}

export interface ExecutionView extends OwnedIdentity {
  canonicalRecordId: string;
  status: "NOT_STARTED" | "IN_PROGRESS" | "TERMINAL" | "RELEASED" | "FAILED";
  plannedTaskCount: number;
  actualTaskCount: number;
  runtimeEventCount: number;
  evidenceCoverage: string;
  releaseGate: "NOT_STARTED" | "PENDING" | "PASSED" | "FAILED";
  entries: ExecutionEntry[];
}

export interface ReleasedResult extends OwnedIdentity {
  status: "UNAVAILABLE" | "PREPARING" | "AVAILABLE";
  releasedAt?: string;
}

export type RuntimeEventType =
  | "plan.generated" | "task.created" | "task.started" | "task.progress"
  | "task.waiting_for_capability" | "capability.validating" | "capability.approved"
  | "task.self_correcting" | "correction.resolved" | "replan.requested" | "replan.approved"
  | "graph.task_added" | "graph.version_changed" | "task.completed" | "review.started"
  | "claim.materialized" | "review.required" | "review.resolved" | "report.started"
  | "result.prepared" | "release.completed";

export interface RuntimeEvent<T extends Record<string, unknown> = Record<string, unknown>> {
  event_id: string;
  run_id: string;
  task_id?: string;
  type: RuntimeEventType;
  timestamp: string;
  sequence: number;
  payload: T;
}

export interface RuntimeProjection {
  run: ResearchRun;
  claims: ResearchClaim[];
  reviews: ReviewRecord[];
  reportArtifact: ReportArtifact;
  execution: ExecutionView;
  releasedResult: ReleasedResult;
  events: RuntimeEvent[];
  lastSequence: number;
}

export interface DemoScenario {
  id: ScenarioId;
  name: string;
  purpose: string;
  object: ResearchObject;
  initialProjection: RuntimeProjection;
  events: RuntimeEvent[];
}
