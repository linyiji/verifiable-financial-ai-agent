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
  const matches = result.metrics.filter((metric) => metric.runId === result.runId && metric.name === name);
  return matches.length === 1 ? matches[0] : null;
}

export function claimForMetric(result: ReleasedResultProjectionV1, metricId: string) {
  const matches = result.claims.filter((claim) => claim.runId === result.runId && claim.metricId === metricId);
  return matches.length === 1 ? matches[0] : null;
}

export function contributionForMetric(
  report: ReportSurfaceV1,
  metric: ReleasedFinancialMetricProjectionV1
): ReportContributionRefV1 | null {
  const matches = report.sourceContributions.filter((item) =>
    item.runId === report.runId && item.reportId === report.reportId && item.artifactId === report.artifactId &&
    item.calculationId === metric.calculationId && item.reportAnchor === REVENUE_GROWTH_ANCHOR
  );
  return matches.length === 1 ? matches[0] : null;
}

export function exactReviewCheck(
  review: FinancialReviewSurfaceV1,
  metric: ReleasedFinancialMetricProjectionV1
): FinancialReviewCheckV1 | null {
  const claim = metric.claimRefs[0];
  if (claim === undefined) return null;
  const matches = review.checks.filter((check) =>
    check.selector.reviewId === review.reviewId &&
    check.selector.checkCode === "FIN_CLAIM_SUPPORT" &&
    check.selector.subjectRefs.length === 2 &&
    check.selector.subjectRefs[0] === metric.calculationId &&
    check.selector.subjectRefs[1] === claim
  );
  return matches.length === 1 ? matches[0] : null;
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
  const actors = execution.actors.filter((item) => item.runId === execution.runId && item.actorId === actorId);
  const details = execution.actorDetails.filter((item) => item.runId === execution.runId && item.actorId === actorId);
  if (actors.length !== 1 || details.length !== 1) return null;
  const actor = actors[0];
  const detail = details[0];
  const outputs = detail.outputs.filter((item) => item.runId === execution.runId && item.outputId === outputId);
  const events = detail.observableProcess.filter((item) => item.runId === execution.runId && item.eventId === eventId);
  const contributions = detail.reportContributions.filter((item) =>
    item.runId === execution.runId && item.actorId === actorId && item.agentOutputId === outputId && item.executionEventId === eventId
  );
  return outputs.length !== 1 || events.length !== 1 || contributions.length !== 1
    ? null
    : { actor, detail, output: outputs[0], event: events[0], contribution: contributions[0] };
}
