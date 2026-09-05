import type {
  CreateResearchObjectInput,
  CreateResearchRunInput,
  FrontendDataSource,
  PrepareResearchRunInput
} from "./FrontendDataSource";
import type { RuntimeEvent } from "../types/domain";

/** Future-integration placeholder. It is deliberately not instantiated in PRE-INTEGRATION mode. */
export class HttpFrontendDataSource implements FrontendDataSource {
  readonly kind = "http" as const;

  private deferred(): Promise<never> {
    return Promise.reject(new Error("HttpFrontendDataSource is deferred until FRONTEND_V8_BACKEND_INTEGRATION"));
  }

  listObjects() { return this.deferred(); }
  searchObjects(_query: string) { return this.deferred(); }
  createObject(_input: CreateResearchObjectInput) { return this.deferred(); }
  getObjectDetail(_objectId: string) { return this.deferred(); }
  getObjectFinancials(_objectId: string) { return this.deferred(); }
  listObjectRuns(_objectId: string) { return this.deferred(); }
  listResearchRuns() { return this.deferred(); }
  getResearchRun(_runId: string) { return this.deferred(); }
  getRunProjection(_runId: string) { return this.deferred(); }
  applyRuntimeEvent(_runId: string, _event: RuntimeEvent) { return this.deferred(); }
  prepareResearchRun(_input: PrepareResearchRunInput) { return this.deferred(); }
  createResearchRun(_input: CreateResearchRunInput) { return this.deferred(); }
  getClaims(_runId: string) { return this.deferred(); }
  getClaim(_runId: string, _claimId: string) { return this.deferred(); }
  getReviewRecords(_runId: string) { return this.deferred(); }
  getExecutionView(_runId: string) { return this.deferred(); }
  getReportArtifact(_runId: string) { return this.deferred(); }
}
