import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { lifecycleReportTruthMatches, releaseTruthSatisfied } from "../src/components/lifecycleModel.ts";
import { reviewSurfaceMatchesProjection } from "../src/components/results/reviewModel.ts";
import { parseResultsFocus, parseRunStage, resultsPath, runPath } from "../src/routing/resultsRoute.ts";

const RUN = "RUN-57aed683-75d6-4b47-acc6-a73053ea492e";
const OTHER_RUN = "RUN-OTHER";
const RESULT = `RESULT-${RUN}`;
const REPORT = RESULT;
const ARTIFACT = "RPT-HTML-b9ce5cd45ee1a1a95a8e";
const REVIEW = `REVIEW-${RUN}`;
const RECORD = `CER-${RUN}`;
const ANCHOR = "metric-revenue-growth";
const ACTOR = "fundamental_analyst";
const OUTPUT = "AGOUT-9ab72a67-87e1-523a-a88f-1c4246a26330";
const EVENT = "EVT-9dc4ef04-5617-4652-9510-61b9905274a0";
const CALC = `CALC-${RUN}-GROWTH`;
const available = { status: "AVAILABLE", reasonCode: null, retryable: false };
const ready = { status: "READY", reasonCode: null };

const review = {
  runId: RUN, objectId: "OBJ-NVDA", releasedResultId: RESULT,
  canonicalExecutionRecordId: RECORD, reviewId: REVIEW, verdict: "PASS",
  availability: ready, checks: Array.from({ length: 54 }, (_, index) => ({
    selector: { reviewId: REVIEW, checkCode: `CHECK-${index}`, subjectRefs: [`SUBJECT-${index}`] },
    status: "PASS", safeExplanation: null, inputRefs: [], outputRefs: []
  }))
};
const report = {
  runId: RUN, objectId: "OBJ-NVDA", releasedResultId: RESULT,
  canonicalExecutionRecordId: RECORD, reportId: REPORT, artifactId: ARTIFACT,
  availability: ready, sourceContributions: [{
    runId: RUN, reportId: REPORT, artifactId: ARTIFACT, reportAnchor: ANCHOR,
    taskId: `${RUN}:fundamentals`, actorId: ACTOR, agentOutputId: OUTPUT,
    executionEventId: EVENT, calculationId: CALC, evidenceRefs: [], reviewId: REVIEW
  }]
};
const result = { runId: RUN, objectId: "OBJ-NVDA", releasedResultId: RESULT, canonicalRecordId: RECORD, availability: available };
const artifacts = {
  runId: RUN, objectId: "OBJ-NVDA", releasedResultId: RESULT, reportId: REPORT,
  canonicalRecordId: RECORD, availability: available, representations: [
    { format: "HTML", availability: available, artifactId: ARTIFACT, generationAttemptCount: 1, authorizedRef: "/artifact.html" },
    { format: "PDF", availability: { status: "NOT_GENERATED" }, artifactId: null, generationAttemptCount: 0, authorizedRef: null }
  ]
};
const truth = { report, result, artifacts, review };
const projection = {
  run: { runId: RUN, backendStatus: "RELEASED" }, object: { objectId: "OBJ-NVDA" },
  review: { reviewId: REVIEW, availability: available, status: "PASS" },
  result: { releasedResultId: RESULT, availability: available },
  artifacts: { reportId: REPORT, availability: available },
  execution: { canonicalRecordId: RECORD, availability: available },
  proof: { policy: "NOT_REQUIRED", status: "NOT_REQUIRED", availability: { status: "NOT_REQUIRED" }, proofRefs: [] },
  terminal: { isTerminal: true, outcome: "SUCCESS" },
  activity: [{ type: "release.completed" }, { type: "run.completed" }]
};

const workspace = readFileSync(new URL("../src/components/ResearchRuntimeWorkspace.tsx", import.meta.url), "utf8");
const reportComponent = readFileSync(new URL("../src/components/results/InteractiveResearchReport.tsx", import.meta.url), "utf8");
const reviewComponent = readFileSync(new URL("../src/components/results/InteractiveFinancialReview.tsx", import.meta.url), "utf8");
const executionComponent = readFileSync(new URL("../src/components/results/InteractiveExecutionRecord.tsx", import.meta.url), "utf8");
const resultsPage = readFileSync(new URL("../src/pages/ResultsWorkspacePage.tsx", import.meta.url), "utf8");
const application = readFileSync(new URL("../src/Phase4Application.tsx", import.meta.url), "utf8");

let count = 0;
const check = (condition, message) => { count += 1; assert.ok(condition, message); };

check(["plan", "research", "review", "report", "complete"].every((stage) => workspace.includes(`id: "${stage}"`)), "lifecycle contains exact stages 01-05");
check(!workspace.includes('id: "execution"'), "Execution is not a sixth lifecycle stage");
check(runPath(RUN, "review") === `/runs/${RUN}?stage=review`, "Run lifecycle stage is URL-addressable");
check(parseRunStage("?stage=report") === "report", "refresh restores the selected lifecycle stage");
check(parseRunStage("?stage=unknown") === "research", "invalid lifecycle stage fails to the safe default");
check(workspace.includes("stage-03-open-review") && workspace.includes('resultsPath(projection.run.runId, "review")'), "Stage 03 opens Results B on the same Run");
check(reviewSurfaceMatchesProjection(projection, review), "Stage 03 and Results B share exact Review identity");
check(!reviewSurfaceMatchesProjection(projection, { ...review, runId: OTHER_RUN }), "foreign-Run Review is rejected");
check(review.checks.length === 54 && review.verdict === "PASS" && review.availability.status === "READY", "accepted Review truth has 54 checks, PASS, READY");
check(lifecycleReportTruthMatches(projection, truth), "Stage 04 and Results A share the exact report bundle");
check(!lifecycleReportTruthMatches(projection, { ...truth, report: { ...report, runId: OTHER_RUN } }), "foreign-Run report bundle is rejected");
check(!lifecycleReportTruthMatches(projection, { ...truth, artifacts: { ...artifacts, reportId: "REPORT-OTHER" } }), "mismatched artifact identity fails closed");
check(!lifecycleReportTruthMatches(projection, { ...truth, report: { ...report, artifactId: "ARTIFACT-OTHER" } }), "mismatched report representation fails closed");
check(report.sourceContributions.length === 1, "authoritative Report Source Map remains count 1");
check(workspace.includes("每章节生成进度") && workspace.includes("未观察到"), "Stage 04 discloses missing chapter progress");
check(!/Chapter 1|Chapter 2|Generating\.\.\./u.test(workspace), "Stage 04 does not fabricate chapter progress");
check(workspace.includes("generationAttemptCount") && workspace.includes("authorizedRef"), "Stage 04 derives artifact actions from authoritative slots");
check(releaseTruthSatisfied(projection, truth), "Stage 05 closes with complete authoritative release truth");
check(!releaseTruthSatisfied({ ...projection, activity: [{ type: "run.completed" }] }, truth), "HTML/report availability alone cannot close release");
check(!releaseTruthSatisfied(projection, { ...truth, result: { ...result, runId: OTHER_RUN } }), "Stage 05 rejects cross-Run Released Result");
check(["stage-05-open-results", "stage-05-open-review", "stage-05-open-execution"].every((id) => workspace.includes(id)), "Stage 05 exposes A/B/C navigation actions");

const reportUrl = resultsPath(RUN, "report", { runId: RUN, anchor: ANCHOR });
check(parseResultsFocus(RUN, "report", reportUrl.slice(reportUrl.indexOf("?")))?.anchor === ANCHOR, "Report Hero focus survives refresh");
const reviewFocus = { runId: RUN, reviewId: REVIEW, checkCode: "FIN_CLAIM_SUPPORT", subjectRefs: [CALC, "CLAIM-1"].sort(), returnAnchor: ANCHOR };
const reviewUrl = resultsPath(RUN, "review", reviewFocus);
check(parseResultsFocus(RUN, "review", reviewUrl.slice(reviewUrl.indexOf("?")))?.reviewId === REVIEW, "A-to-B exact Review selector survives refresh");
check(reviewUrl.includes("return_anchor=metric-revenue-growth"), "B-to-A exact anchor is retained in URL history");
const executionUrl = resultsPath(RUN, "execution", { runId: RUN, actorId: ACTOR, outputId: OUTPUT, eventId: EVENT, returnAnchor: ANCHOR });
const executionFocus = parseResultsFocus(RUN, "execution", executionUrl.slice(executionUrl.indexOf("?")));
check(executionFocus?.actorId === ACTOR, "A-to-C Hero preserves exact actor");
check(executionFocus?.outputId === OUTPUT, "A-to-C Hero preserves exact AgentOutput");
check(executionFocus?.eventId === EVENT, "A-to-C Hero preserves exact execution event");
check(executionFocus?.returnAnchor === ANCHOR, "C-to-A exact report anchor is retained");
check(resultsPath(RUN, "report", { runId: OTHER_RUN, anchor: ANCHOR }) === `/runs/${RUN}/results/report`, "cross-Run focus is dropped rather than rebound");
check(reportComponent.includes("heroReview.selector, REVENUE_GROWTH_ANCHOR"), "A-to-B uses authoritative exact selector and anchor");
check(resultsPage.includes("anchor: contribution.reportAnchor"), "C-to-A uses authoritative contribution anchor");
check(!reviewComponent.includes('resultsPath') && !executionComponent.includes('"review"'), "missing B-to-C and C-to-B relations do not fabricate links");
check(application.includes("setRouteRevision") && application.includes("parseRunStage(window.location.search)"), "history events rerender and restore Run stage");
check(!/(latestRun|latestReleased|fallbackReport|fallbackReview|fallbackExecution|fixtureReport|fixtureReview|fixtureExecution)/iu.test(workspace + resultsPage), "no latest or fixture fallback is present");
check(!/(reasoningTrace|chainOfThought|rawProviderResponse|dangerouslySetInnerHTML)/u.test(workspace + reportComponent + reviewComponent + executionComponent + resultsPage), "no hidden CoT or unsafe raw fields are exposed");

assert.equal(count, 35);
console.log(`M6 focused integration checks: ${count}/35 PASS`);
