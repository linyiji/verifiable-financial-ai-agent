import type {
  ExecutionView,
  FinancialMetric,
  ReportArtifact,
  ResearchClaim,
  ResearchObject,
  ResearchObjectDetail,
  ResearchPlan,
  ResearchRun,
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
