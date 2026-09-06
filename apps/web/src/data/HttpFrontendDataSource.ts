import {
  Phase4ApiClient,
  Phase4ProtocolError,
  phase4ApiRoutes,
  type Phase4ApiClientOptions
} from "../api/client";
import {
  decodeConfirmRunResponse,
  decodeExecutionRecordSurface,
  decodeFinancialReviewSurface,
  decodePreparedResearchDraft,
  decodeReportSurface,
  decodeResearchObjectCollection,
  decodeResearchObjectDetail,
  decodeResearchRunDetail,
  decodeReleasedResultProjection,
  decodeRunCollection,
  decodeRunProjection,
  decodeResultsWorkspace,
  decodeSafeJsonObject,
  type ConfirmRunResponseV1,
  type ExecutionRecordSurfaceV1,
  type FinancialReviewSurfaceV1,
  type GlobalRunCollectionProjection,
  type Phase4ResearchObjectDetail,
  type PreparedResearchDraft,
  type ReportSurfaceV1,
  type ResearchObjectCollection,
  type ResearchRunDetailV1,
  type ReleasedResultProjectionV1,
  type ResultsWorkspaceV1,
  type RunProjection
} from "../types/domain";
import type {
  ObjectCollectionQuery,
  ObjectRunCollectionQuery,
  Phase4ConfirmResearchRunInput,
  Phase4CreateResearchObjectInput,
  Phase4FrontendDataSource,
  Phase4Mutation,
  Phase4PrepareResearchRunInput,
  Phase4RequestOptions,
  RunCollectionQuery
} from "./FrontendDataSource";

function requiredText(value: string, name: string): string {
  if (value.length === 0) {
    throw new TypeError(`${name} must be non-empty`);
  }
  return value;
}

function positiveLimit(value: number | undefined): number | undefined {
  if (value === undefined) return undefined;
  if (!Number.isInteger(value) || value < 1 || value > 100) {
    throw new TypeError("limit must be an integer from 1 through 100");
  }
  return value;
}

function queryPath(
  path: string,
  entries: readonly (readonly [string, string | number | undefined])[]
): string {
  const query = new URLSearchParams();
  for (const [name, value] of entries) {
    if (value !== undefined) query.append(name, String(value));
  }
  const suffix = query.toString();
  return suffix.length === 0 ? path : `${path}?${suffix}`;
}

function objectCollectionPath(query: ObjectCollectionQuery | undefined): string {
  return queryPath(phase4ApiRoutes.objects, [
    ["symbol", query?.symbol],
    ["query", query?.query],
    ["cursor", query?.cursor],
    ["limit", positiveLimit(query?.limit)]
  ]);
}

function runCollectionPath(
  path: string,
  query: RunCollectionQuery | undefined
): string {
  if (query?.statuses !== undefined && query.resultAvailability !== undefined) {
    throw new TypeError("status and result_availability filters are mutually exclusive");
  }
  const entries: Array<readonly [string, string | number | undefined]> = [];
  if (query !== undefined && "objectId" in query) {
    entries.push(["object_id", query.objectId]);
  }
  for (const status of query?.statuses ?? []) entries.push(["status", status]);
  entries.push(
    ["result_availability", query?.resultAvailability],
    ["cursor", query?.cursor],
    ["limit", positiveLimit(query?.limit)]
  );
  return queryPath(path, entries);
}

function objectRunCollectionPath(
  path: string,
  query: ObjectRunCollectionQuery | undefined
): string {
  return queryPath(path, [
    ["cursor", query?.cursor],
    ["limit", positiveLimit(query?.limit)]
  ]);
}

function jsonBody(value: unknown): string {
  const body = JSON.stringify(value);
  if (body === undefined) {
    throw new TypeError("Phase 4 mutation input is not JSON serializable");
  }
  return body;
}

function createObjectBody(input: Readonly<Phase4CreateResearchObjectInput>): string {
  return jsonBody({
    symbol: requiredText(input.symbol, "symbol"),
    company_name: requiredText(input.companyName, "companyName"),
    exchange: input.exchange,
    sector: input.sector,
    currency: input.currency
  });
}

function prepareBody(input: Readonly<Phase4PrepareResearchRunInput>): string {
  return jsonBody({
    research_object_id: requiredText(input.researchObjectId, "researchObjectId"),
    research_goal: requiredText(input.researchGoal, "researchGoal"),
    as_of: requiredText(input.asOf, "asOf"),
    preferences: decodeSafeJsonObject(input.preferences, "$.preferences")
  });
}

function confirmBody(input: Readonly<Phase4ConfirmResearchRunInput>): string {
  if (input.confirmScheme !== true) {
    throw new TypeError("Phase 4 confirmation requires confirmScheme=true");
  }
  if (!Number.isInteger(input.draftVersion) || input.draftVersion < 1) {
    throw new TypeError("draftVersion must be an integer greater than or equal to one");
  }
  return jsonBody({
    draft_id: requiredText(input.draftId, "draftId"),
    draft_version: input.draftVersion,
    draft_hash: requiredText(input.draftHash, "draftHash"),
    research_object_id: requiredText(input.researchObjectId, "researchObjectId"),
    confirm_scheme: true
  });
}

export class HttpFrontendDataSource implements Phase4FrontendDataSource {
  readonly kind = "http" as const;
  private readonly client: Phase4ApiClient;
  private readonly createdObjectIdentities = new Map<string, string>();
  private readonly preparedDrafts = new Map<string, string>();
  private readonly confirmExpectations = new Map<string, string>();
  private readonly confirmAdmissions = new Map<string, string>();

  constructor(options: Phase4ApiClientOptions = {}) {
    this.client = new Phase4ApiClient(options);
  }

  listResearchObjects(
    query?: ObjectCollectionQuery,
    options?: Phase4RequestOptions
  ): Promise<ResearchObjectCollection> {
    return this.client.requestJson({
      method: "GET",
      path: objectCollectionPath(query),
      expectedStatuses: [200],
      signal: options?.signal,
      decode: decodeResearchObjectCollection
    });
  }

  async createResearchObject(
    mutation: Phase4Mutation<Phase4CreateResearchObjectInput>,
    options?: Phase4RequestOptions
  ): Promise<Phase4ResearchObjectDetail> {
    const result = await this.client.requestJson({
      method: "POST",
      path: phase4ApiRoutes.objects,
      expectedStatuses: [201],
      idempotencyKey: mutation.idempotencyKey,
      body: createObjectBody(mutation.input),
      signal: options?.signal,
      decode: decodeResearchObjectDetail
    });
    const expectedObject = mutation.input;
    if (
      result.object.symbol !== expectedObject.symbol.trim().toUpperCase() ||
      result.object.companyName !== expectedObject.companyName ||
      result.object.exchange !== expectedObject.exchange ||
      result.object.sector !== expectedObject.sector ||
      result.object.currency !== expectedObject.currency
    ) {
      throw new Phase4ProtocolError(
        "Object creation response does not close to the normalized request identity",
        { method: "POST", path: phase4ApiRoutes.objects },
        201
      );
    }
    this.retainImmutableResponse(
      this.createdObjectIdentities,
      mutation.idempotencyKey,
      result.object,
      "An Object creation replay changed the immutable Object identity",
      phase4ApiRoutes.objects
    );
    return result;
  }

  getResearchObject(
    objectId: string,
    options?: Phase4RequestOptions
  ): Promise<Phase4ResearchObjectDetail> {
    const expectedObjectId = requiredText(objectId, "objectId");
    return this.client.requestJson({
      method: "GET",
      path: phase4ApiRoutes.object(expectedObjectId),
      expectedStatuses: [200],
      signal: options?.signal,
      decode: (value) => decodeResearchObjectDetail(value, expectedObjectId)
    });
  }

  listResearchRuns(
    query?: RunCollectionQuery,
    options?: Phase4RequestOptions
  ): Promise<GlobalRunCollectionProjection> {
    return this.client.requestJson({
      method: "GET",
      path: runCollectionPath(phase4ApiRoutes.runs, query),
      expectedStatuses: [200],
      signal: options?.signal,
      decode: (value) => decodeRunCollection(value, query?.objectId)
    });
  }

  listResearchObjectRuns(
    objectId: string,
    query?: ObjectRunCollectionQuery,
    options?: Phase4RequestOptions
  ): Promise<GlobalRunCollectionProjection> {
    const expectedObjectId = requiredText(objectId, "objectId");
    return this.client.requestJson({
      method: "GET",
      path: objectRunCollectionPath(phase4ApiRoutes.objectRuns(expectedObjectId), query),
      expectedStatuses: [200],
      signal: options?.signal,
      decode: (value) => decodeRunCollection(value, expectedObjectId)
    });
  }

  getResearchRun(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<ResearchRunDetailV1> {
    const expectedRunId = requiredText(runId, "runId");
    return this.client.requestJson({
      method: "GET",
      path: phase4ApiRoutes.run(expectedRunId),
      expectedStatuses: [200],
      signal: options?.signal,
      decode: (value) => decodeResearchRunDetail(value, expectedRunId, expectedObjectId)
    });
  }

  getRunProjection(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<RunProjection> {
    const expectedRunId = requiredText(runId, "runId");
    const path = phase4ApiRoutes.runProjection(expectedRunId);
    return this.client.requestJson({
      method: "GET",
      path,
      expectedStatuses: [200],
      signal: options?.signal,
      decode: (value) => decodeRunProjection(value, expectedRunId, expectedObjectId),
      validateSuccess: (projection, _status, response) => {
        const expectedEtag =
          `"p4:${expectedRunId}:${projection.projectionRevision}:${projection.projectionSequence}"`;
        if (response.headers.get("ETag") !== expectedEtag) {
          throw new Phase4ProtocolError(
            "Run projection ETag does not match its exact identity and watermarks",
            { method: "GET", path },
            response.status
          );
        }
      }
    });
  }

  getReleasedResult(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<ReleasedResultProjectionV1> {
    const expectedRunId = requiredText(runId, "runId");
    return this.client.requestJson({
      method: "GET",
      path: phase4ApiRoutes.runResult(expectedRunId),
      expectedStatuses: [200],
      signal: options?.signal,
      decode: (value) => decodeReleasedResultProjection(value, expectedRunId, expectedObjectId)
    });
  }

  getResultsWorkspace(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<ResultsWorkspaceV1> {
    const expectedRunId = requiredText(runId, "runId");
    return this.client.requestJson({
      method: "GET",
      path: phase4ApiRoutes.runResults(expectedRunId),
      expectedStatuses: [200],
      signal: options?.signal,
      decode: (value) => decodeResultsWorkspace(value, expectedRunId, expectedObjectId)
    });
  }

  getReportSurface(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<ReportSurfaceV1> {
    const expectedRunId = requiredText(runId, "runId");
    return this.client.requestJson({
      method: "GET",
      path: phase4ApiRoutes.runReport(expectedRunId),
      expectedStatuses: [200],
      signal: options?.signal,
      decode: (value) => decodeReportSurface(value, expectedRunId, expectedObjectId)
    });
  }

  getFinancialReviewSurface(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<FinancialReviewSurfaceV1> {
    const expectedRunId = requiredText(runId, "runId");
    return this.client.requestJson({
      method: "GET",
      path: phase4ApiRoutes.runReview(expectedRunId),
      expectedStatuses: [200],
      signal: options?.signal,
      decode: (value) => decodeFinancialReviewSurface(value, expectedRunId, expectedObjectId)
    });
  }

  getExecutionRecordSurface(
    runId: string,
    expectedObjectId?: string,
    options?: Phase4RequestOptions
  ): Promise<ExecutionRecordSurfaceV1> {
    const expectedRunId = requiredText(runId, "runId");
    return this.client.requestJson({
      method: "GET",
      path: phase4ApiRoutes.runExecution(expectedRunId),
      expectedStatuses: [200],
      signal: options?.signal,
      decode: (value) => decodeExecutionRecordSurface(value, expectedRunId, expectedObjectId)
    });
  }

  async prepareResearchRun(
    mutation: Phase4Mutation<Phase4PrepareResearchRunInput>,
    options?: Phase4RequestOptions
  ): Promise<PreparedResearchDraft> {
    const expectedObjectId = requiredText(
      mutation.input.researchObjectId,
      "researchObjectId"
    );
    const result = await this.client.requestJson({
      method: "POST",
      path: phase4ApiRoutes.prepareRun,
      expectedStatuses: [201],
      idempotencyKey: mutation.idempotencyKey,
      body: prepareBody(mutation.input),
      signal: options?.signal,
      decode: (value) => decodePreparedResearchDraft(value, expectedObjectId)
    });
    this.retainImmutableResponse(
      this.preparedDrafts,
      mutation.idempotencyKey,
      result,
      "A prepare replay changed the decoded Research Draft",
      phase4ApiRoutes.prepareRun
    );
    return result;
  }

  async confirmResearchRun(
    mutation: Phase4Mutation<Phase4ConfirmResearchRunInput>,
    options?: Phase4RequestOptions
  ): Promise<ConfirmRunResponseV1> {
    const input = mutation.input;
    const body = confirmBody(input);
    const expectedIdentity = JSON.stringify({
      objectId: input.researchObjectId,
      draftId: input.draftId,
      draftVersion: input.draftVersion,
      draftHash: input.draftHash,
      goalId: input.expectedGoalId,
      schemeId: input.expectedSchemeId
    });
    const retainedIdentity = this.confirmExpectations.get(mutation.idempotencyKey);
    if (retainedIdentity !== undefined && retainedIdentity !== expectedIdentity) {
      throw new Phase4ProtocolError(
        "A confirmation Idempotency-Key cannot be reused with different admission expectations",
        { method: "POST", path: phase4ApiRoutes.runs }
      );
    }
    this.confirmExpectations.set(mutation.idempotencyKey, expectedIdentity);

    const result = await this.client.requestJson({
      method: "POST",
      path: phase4ApiRoutes.runs,
      expectedStatuses: [200, 201],
      idempotencyKey: mutation.idempotencyKey,
      body,
      signal: options?.signal,
      decode: (value) =>
        decodeConfirmRunResponse(value, {
          objectId: input.researchObjectId,
          draftId: input.draftId,
          draftVersion: input.draftVersion,
          draftHash: input.draftHash,
          goalId: input.expectedGoalId,
          schemeId: input.expectedSchemeId
        }),
      validateSuccess: (result, status) => {
        const firstAdmission =
          status === 201 && result.responseMeta.idempotencyReplayed === false;
        const replay = status === 200 && result.responseMeta.idempotencyReplayed === true;
        if (!firstAdmission && !replay) {
          throw new Phase4ProtocolError(
            "Confirmation status contradicts responseMeta.idempotencyReplayed",
            { method: "POST", path: phase4ApiRoutes.runs },
            status
          );
        }
      }
    });

    // responseMeta varies per attempt. The immutable admission must not.
    const serializedAdmission = JSON.stringify(result.admission);
    const retainedAdmission = this.confirmAdmissions.get(mutation.idempotencyKey);
    if (retainedAdmission !== undefined && retainedAdmission !== serializedAdmission) {
      throw new Phase4ProtocolError(
        "A confirmation replay changed the immutable Run admission",
        { method: "POST", path: phase4ApiRoutes.runs }
      );
    }
    this.confirmAdmissions.set(mutation.idempotencyKey, serializedAdmission);
    return result;
  }

  private retainImmutableResponse(
    retainedResponses: Map<string, string>,
    idempotencyKey: string,
    result: unknown,
    message: string,
    path: string
  ): void {
    const serializedResult = JSON.stringify(result);
    const retainedResult = retainedResponses.get(idempotencyKey);
    if (retainedResult !== undefined && retainedResult !== serializedResult) {
      throw new Phase4ProtocolError(message, { method: "POST", path });
    }
    retainedResponses.set(idempotencyKey, serializedResult);
  }
}
