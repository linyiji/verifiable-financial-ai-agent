export type RunStatus =
  | "PLANNING"
  | "RESEARCHING"
  | "REVIEWING"
  | "GENERATING_REPORT"
  | "RESULT_PREPARING"
  | "ACTION_REQUIRED"
  | "COMPLETED"
  | "FAILED";

export type RunStage = "plan" | "research" | "review" | "report" | "completed";
export type ResearchStep = "collect" | "prepare" | "financial" | "analysis" | "synthesis";
export type TaskStatus = "WAITING" | "READY" | "RUNNING" | "SELF_CORRECTING" | "COMPLETED" | "BLOCKED" | "FAILED";
/**
 * Mutation types implemented by the pre-integration projection. Future human
 * gate / rollback types are intentionally not advertised until they have a
 * real event, state transition, recovery path, and regression journey.
 */
export type PathChangeType = "SELF_CORRECTION" | "ADD_TASK" | "CHANGE_DEPENDENCY";
export type ReviewStatus = "PASS" | "PASS_WITH_UNCERTAINTY" | "REVIEW" | "BLOCK" | "RESOLVED";
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
