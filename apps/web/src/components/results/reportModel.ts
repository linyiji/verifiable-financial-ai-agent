import type {
  ExecutionRecordSurfaceV1,
  FinancialReviewCheckV1,
  FinancialReviewSurfaceV1,
  ReleasedFinancialMetricProjectionV1,
  ReleasedResultProjectionV1,
  ReportArtifactGroupV1,
  ReportContributionRefV1,
  ReportSurfaceV1,
  ReviewCheckSelectorV1
} from "../../types/domain";

export const REVENUE_GROWTH_ANCHOR = "metric-revenue-growth";

export function reportBundleMatches(
  report: ReportSurfaceV1,
  result: ReleasedResultProjectionV1,
  artifacts: ReportArtifactGroupV1,
  review: FinancialReviewSurfaceV1
): boolean {
  return report.runId === result.runId && report.runId === artifacts.runId && report.runId === review.runId &&
    report.objectId === result.objectId && report.objectId === artifacts.objectId && report.objectId === review.objectId &&
    report.releasedResultId === result.releasedResultId && report.releasedResultId === artifacts.releasedResultId &&
    report.releasedResultId === review.releasedResultId && report.reportId === artifacts.reportId &&
    report.canonicalExecutionRecordId === result.canonicalRecordId &&
    report.canonicalExecutionRecordId === artifacts.canonicalRecordId &&
    report.canonicalExecutionRecordId === review.canonicalExecutionRecordId;
}

export function metricByName(result: ReleasedResultProjectionV1, name: string): ReleasedFinancialMetricProjectionV1 | null {
  return result.metrics.find((metric) => metric.name === name) ?? null;
}

export function claimForMetric(result: ReleasedResultProjectionV1, metricId: string) {
  return result.claims.find((claim) => claim.metricId === metricId) ?? null;
}

export function contributionForMetric(
  report: ReportSurfaceV1,
  metric: ReleasedFinancialMetricProjectionV1
): ReportContributionRefV1 | null {
  return report.sourceContributions.find((item) =>
    item.calculationId === metric.calculationId && item.reportAnchor === REVENUE_GROWTH_ANCHOR
  ) ?? null;
}

export function exactReviewCheck(
  review: FinancialReviewSurfaceV1,
  metric: ReleasedFinancialMetricProjectionV1
): FinancialReviewCheckV1 | null {
  const claim = metric.claimRefs[0];
  if (claim === undefined) return null;
  return review.checks.find((check) =>
    check.selector.reviewId === review.reviewId &&
    check.selector.checkCode === "FIN_CLAIM_SUPPORT" &&
    check.selector.subjectRefs.length === 2 &&
    check.selector.subjectRefs[0] === metric.calculationId &&
    check.selector.subjectRefs[1] === claim
  ) ?? null;
}

export function selectorMatches(left: ReviewCheckSelectorV1, right: ReviewCheckSelectorV1): boolean {
  return left.reviewId === right.reviewId && left.checkCode === right.checkCode &&
    left.subjectRefs.length === right.subjectRefs.length &&
    left.subjectRefs.every((ref, index) => ref === right.subjectRefs[index]);
}

export function executionFocusMatches(
  execution: ExecutionRecordSurfaceV1,
  actorId: string,
  outputId: string,
  eventId: string
) {
  const actor = execution.actors.find((item) => item.actorId === actorId);
  const detail = execution.actorDetails.find((item) => item.actorId === actorId);
  if (actor === undefined || detail === undefined) return null;
  const output = detail.outputs.find((item) => item.outputId === outputId);
  const event = detail.observableProcess.find((item) => item.eventId === eventId);
  const contribution = detail.reportContributions.find((item) =>
    item.agentOutputId === outputId && item.executionEventId === eventId
  );
  return output === undefined || event === undefined || contribution === undefined
    ? null
    : { actor, detail, output, event, contribution };
}
