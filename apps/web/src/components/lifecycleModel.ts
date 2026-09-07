import type {
  FinancialReviewSurfaceV1,
  ReleasedResultProjectionV1,
  ReportArtifactGroupV1,
  ReportSurfaceV1,
  RunProjection
} from "../types/domain";

export interface LifecycleReportTruth {
  readonly report: ReportSurfaceV1;
  readonly result: ReleasedResultProjectionV1;
  readonly artifacts: ReportArtifactGroupV1;
  readonly review: FinancialReviewSurfaceV1;
}

export function lifecycleReportTruthMatches(projection: RunProjection, truth: LifecycleReportTruth): boolean {
  const matchingArtifacts = truth.artifacts.representations.filter((representation) =>
    representation.availability.status === "AVAILABLE" && representation.artifactId === truth.report.artifactId
  );
  return matchingArtifacts.length === 1 &&
    truth.report.runId === truth.result.runId && truth.report.runId === truth.artifacts.runId && truth.report.runId === truth.review.runId &&
    truth.report.objectId === truth.result.objectId && truth.report.objectId === truth.artifacts.objectId && truth.report.objectId === truth.review.objectId &&
    truth.report.releasedResultId === truth.result.releasedResultId && truth.report.releasedResultId === truth.artifacts.releasedResultId &&
    truth.report.releasedResultId === truth.review.releasedResultId && truth.report.reportId === truth.artifacts.reportId &&
    truth.report.canonicalExecutionRecordId === truth.result.canonicalRecordId &&
    truth.report.canonicalExecutionRecordId === truth.artifacts.canonicalRecordId &&
    truth.report.canonicalExecutionRecordId === truth.review.canonicalExecutionRecordId &&
    truth.report.runId === projection.run.runId &&
    truth.report.objectId === projection.object.objectId &&
    truth.report.reportId === projection.artifacts.reportId &&
    truth.result.releasedResultId === projection.result.releasedResultId &&
    truth.report.canonicalExecutionRecordId === projection.execution.canonicalRecordId &&
    truth.review.reviewId === projection.review.reviewId;
}

export function proofClosed(projection: RunProjection): boolean {
  if (projection.proof.policy === "NOT_REQUIRED") return projection.proof.status === "NOT_REQUIRED";
  return projection.proof.availability.status === "AVAILABLE" && projection.proof.status === "VERIFIED";
}

export function releaseTruthSatisfied(projection: RunProjection, truth: LifecycleReportTruth | null): boolean {
  if (truth === null || !lifecycleReportTruthMatches(projection, truth)) return false;
  const hasEvent = (type: string) => projection.activity.some((event) => event.type === type);
  return truth.review.reviewId === projection.review.reviewId && truth.review.availability.status === "READY" &&
    truth.review.verdict === "PASS" && proofClosed(projection) &&
    projection.execution.availability.status === "AVAILABLE" && projection.execution.canonicalRecordId !== null &&
    truth.report.availability.status !== "UNAVAILABLE" && truth.artifacts.availability.status === "AVAILABLE" &&
    truth.result.availability.status === "AVAILABLE" && projection.run.backendStatus === "RELEASED" &&
    projection.terminal.isTerminal && projection.terminal.outcome === "SUCCESS" &&
    hasEvent("release.completed") && hasEvent("run.completed");
}
