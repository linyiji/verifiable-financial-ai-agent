import type {
  AvailabilityStatus,
  ConfirmRunResponseV1,
  ExecutionView,
  ExecutionRecordSurfaceV1,
  FinancialReviewSurfaceV1,
  FinancialMetric,
  GlobalRunCollectionProjection,
  Phase4ResearchObjectDetail,
  PreparedResearchDraft,
  ReportArtifact,
  ReportArtifactGroupV1,
  ReportSurfaceV1,
  ResearchClaim,
  ResearchObject,
  ResearchObjectCollection,
  ResearchObjectDetail,
  ResearchPlan,
  ResearchRun,
  ResearchRunDetailV1,
  ReleasedResultProjectionV1,
  ResultsWorkspaceV1,
  RunProjection,
  RuntimeEvent,
  RuntimeProjection,
  ReviewRecord
} from "../types/domain";

export interface PrepareResearchRunInput {
  objectId: string;
  goal: string;
  template: "COMPREHENSIVE" | "VALUATION" | "RISK" | "CUSTOM";
  mode?: "FULL" | "INCREMENTAL";
}

export interface CreateResearchRunInput {
  objectId: string;
  goal: string;
  planId: string;
}

export interface CreateResearchObjectInput {
  name: string;
  symbol: string;
  exchange: string;
  sector?: string;
  industry?: string;
  currency?: string;
  country?: string;
}

export interface ReportArtifactSource {
  getReportArtifact(runId: string): Promise<ReportArtifact>;
}

export interface FrontendDataSource extends ReportArtifactSource {
  readonly kind: "demo" | "http";
  listObjects(): Promise<ResearchObject[]>;
  searchObjects(query: string): Promise<ResearchObject[]>;
  createObject(input: CreateResearchObjectInput): Promise<ResearchObject>;
  getObjectDetail(objectId: string): Promise<ResearchObjectDetail>;
  getObjectFinancials(objectId: string): Promise<FinancialMetric[]>;
  listObjectRuns(objectId: string): Promise<ResearchRun[]>;
  listResearchRuns(): Promise<ResearchRun[]>;
  getResearchRun(runId: string): Promise<ResearchRun>;
  getRunProjection(runId: string): Promise<RuntimeProjection>;
  applyRuntimeEvent(runId: string, event: RuntimeEvent): Promise<RuntimeProjection>;
  prepareResearchRun(input: PrepareResearchRunInput): Promise<ResearchPlan>;
  createResearchRun(input: CreateResearchRunInput): Promise<ResearchRun>;
  getClaims(runId: string): Promise<ResearchClaim[]>;
  getClaim(runId: string, claimId: string): Promise<ResearchClaim>;
  getReviewRecords(runId: string): Promise<ReviewRecord[]>;
  getExecutionView(runId: string): Promise<ExecutionView>;
}

export type Phase4JsonPrimitive = string | number | boolean | null;
export type Phase4JsonValue =
  | Phase4JsonPrimitive
  | readonly Phase4JsonValue[]
  | Phase4JsonObject;
export interface Phase4JsonObject {
  readonly [key: string]: Phase4JsonValue;
}

export type Phase4BackendRunStatus =
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

export interface Phase4RequestOptions {
  readonly signal?: AbortSignal;
}

export interface Phase4Mutation<TInput> {
  readonly idempotencyKey: string;
  readonly input: Readonly<TInput>;
}

export interface Phase4CreateResearchObjectInput {
  readonly symbol: string;
  readonly companyName: string;
  readonly exchange: string;
  readonly sector: string | null;
  readonly currency: string;
}

export interface Phase4PrepareResearchRunInput {
  readonly baseRunId?: string;
  readonly baseResearchViewVersion?: string;
  readonly researchObjectId: string;
  readonly researchGoal: string;
  readonly asOf: string;
  readonly preferences: Phase4JsonObject;
}

export interface Phase4ConfirmResearchRunInput {
  readonly draftId: string;
  readonly draftVersion: number;
  readonly draftHash: string;
  readonly researchObjectId: string;
  readonly confirmScheme: true;
  /** Admission guard; this is not serialized into the request body. */
  readonly expectedGoalId: string;
  /** Admission guard; this is not serialized into the request body. */
  readonly expectedSchemeId: string;
}

export interface ObjectCollectionQuery {
  readonly symbol?: string;
  readonly query?: string;
  readonly cursor?: string;
  readonly limit?: number;
}

interface RunCollectionQueryBase {
  readonly objectId?: string;
  readonly cursor?: string;
  readonly limit?: number;
}

export type RunCollectionQuery = RunCollectionQueryBase &
  (
    | {
        readonly statuses?: readonly Phase4BackendRunStatus[];
        readonly resultAvailability?: never;
      }
    | {
        readonly statuses?: never;
        readonly resultAvailability?: AvailabilityStatus;
      }
  );

export interface ObjectRunCollectionQuery {
  readonly cursor?: string;
  readonly limit?: number;
}

function generatedIdempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID !== "function") {
    throw new Error("Secure UUID generation is unavailable; supply an explicit Idempotency-Key");
  }
  return globalThis.crypto.randomUUID();
}

function deepFreeze<T>(value: T): Readonly<T> {
  if (typeof value !== "object" || value === null || Object.isFrozen(value)) {
    return value;
  }
  for (const child of Object.values(value)) {
    deepFreeze(child);
  }
  return Object.freeze(value);
}

/**
 * Create once per logical mutation and retain the returned value across an
 * ambiguous retry. Regeneration is a new logical prepare and therefore uses a
 * new mutation/key.
 */
export function createPhase4Mutation<TInput>(
  input: TInput,
  idempotencyKey: string = generatedIdempotencyKey()
): Phase4Mutation<TInput> {
  if (idempotencyKey.trim().length === 0 || /[\r\n]/u.test(idempotencyKey)) {
    throw new TypeError("A non-empty Idempotency-Key is required");
  }
  const retainedInput = deepFreeze(structuredClone(input));
  return Object.freeze({ idempotencyKey, input: retainedInput });
}

/** Contract-authoritative production data source for the Phase 4 Wave 1 flow. */
export interface Phase4FrontendDataSource {
  getResearchMemory(objectId: string, options?: Phase4RequestOptions): Promise<import("../types/researchMemory").ResearchMemorySnapshot>;
  readonly kind: "http";

  listResearchObjects(
    query?: ObjectCollectionQuery,
    options?: Phase4RequestOptions
  ): Promise<ResearchObjectCollection>;
  createResearchObject(
    mutation: Phase4Mutation<Phase4CreateResearchObjectInput>,
    options?: Phase4RequestOptions
  ): Promise<Phase4ResearchObjectDetail>;
  getResearchObject(
    objectId: string,
    options?: Phase4RequestOptions
  ): Promise<Phase4ResearchObjectDetail>;

  listResearchRuns(
    query?: RunCollectionQuery,
    options?: Phase4RequestOptions
  ): Promise<GlobalRunCollectionProjection>;
  listResearchObjectRuns(
    objectId: string,
    query?: ObjectRunCollectionQuery,
    options?: Phase4RequestOptions
  ): Promise<GlobalRunCollectionProjection>;
  getResearchRun(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<ResearchRunDetailV1>;
  getRunProjection(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<RunProjection>;
  getReleasedResult(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<ReleasedResultProjectionV1>;
  getResultsWorkspace(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<ResultsWorkspaceV1>;
  getReportSurface(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<ReportSurfaceV1>;
  getReportArtifacts(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<ReportArtifactGroupV1>;
  getFinancialReviewSurface(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<FinancialReviewSurfaceV1>;
  getExecutionRecordSurface(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<ExecutionRecordSurfaceV1>;

  prepareResearchRun(
    mutation: Phase4Mutation<Phase4PrepareResearchRunInput>,
    options?: Phase4RequestOptions
  ): Promise<PreparedResearchDraft>;
  confirmResearchRun(
    mutation: Phase4Mutation<Phase4ConfirmResearchRunInput>,
    options?: Phase4RequestOptions
  ): Promise<ConfirmRunResponseV1>;
}
