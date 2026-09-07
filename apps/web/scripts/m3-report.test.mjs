import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

import {
  parseResultsFocus,
  resultsPath
} from "../src/routing/resultsRoute.ts";
import {
  REVENUE_GROWTH_ANCHOR,
  claimForMetric,
  contributionForMetric,
  exactReviewCheck,
  executionFocusMatches,
  metricByName,
  reportBundleMatches,
  selectorMatches
} from "../src/components/results/reportModel.ts";

const RUN = "RUN-57aed683-75d6-4b47-acc6-a73053ea492e";
const CALC = `${RUN.replace("RUN-", "CALC-RUN-")}-GROWTH`;
const CLAIM = `CLAIM-${CALC}`;
const ACTOR = "fundamental_analyst";
const OUTPUT = "AGOUT-9ab72a67-87e1-523a-a88f-1c4246a26330";
const EVENT = "EVT-9dc4ef04-5617-4652-9510-61b9905274a0";
const REVIEW = `REVIEW-${RUN}`;
const metric = { runId: RUN, metricId: `METRIC-${CALC}`, name: "Revenue Growth", calculationId: CALC, claimRefs: [CLAIM] };
const claim = { runId: RUN, claimId: CLAIM, metricId: metric.metricId, statement: "Revenue increased from the exact result." };
const contribution = { runId: RUN, reportAnchor: REVENUE_GROWTH_ANCHOR, actorId: ACTOR, agentOutputId: OUTPUT, executionEventId: EVENT, calculationId: CALC };
const selector = { reviewId: REVIEW, checkCode: "FIN_CLAIM_SUPPORT", subjectRefs: [CALC, CLAIM] };
const result = { runId: RUN, metrics: [metric], claims: [claim] };
const report = { runId: RUN, sourceContributions: [contribution] };
const review = { runId: RUN, reviewId: REVIEW, checks: [{ selector, status: "PASS" }] };
const execution = {
  runId: RUN,
  actors: [{ runId: RUN, actorId: ACTOR, displayRole: "Fundamental Analyst" }],
  actorDetails: [{
    runId: RUN, actorId: ACTOR,
    outputs: [{ runId: RUN, outputId: OUTPUT, status: "SUCCESS" }],
    observableProcess: [{ runId: RUN, eventId: EVENT, status: "COMPLETED" }],
    reportContributions: [contribution]
  }]
};
const component = readFileSync(new URL("../src/components/results/InteractiveResearchReport.tsx", import.meta.url), "utf8");
const page = readFileSync(new URL("../src/pages/ResultsWorkspacePage.tsx", import.meta.url), "utf8");

let checks = 0;
const check = (condition, message) => { checks += 1; assert.ok(condition, message); };

check(page.includes("<InteractiveResearchReport"), "A directly renders the report document");
check(!page.includes("打开报告"), "A has no extra Open Report gate");
check(component.includes("导出 HTML") && component.includes("下载 PDF · 暂未生成"), "exports are secondary report actions");
check(!/(DOMParser|<iframe|dangerouslySetInnerHTML)/u.test(component + page), "product authority never parses or embeds HTML");
check(metricByName(result, "Revenue Growth") === metric && claimForMetric(result, metric.metricId) === claim, "values select structured exact-run DTOs");

const executionUrl = resultsPath(RUN, "execution", { runId: RUN, actorId: ACTOR, outputId: OUTPUT, eventId: EVENT, returnAnchor: REVENUE_GROWTH_ANCHOR });
check(executionUrl.startsWith(`/runs/${RUN}/results/execution?`), "source navigation preserves exact run_id");
const executionFocus = parseResultsFocus(RUN, "execution", executionUrl.slice(executionUrl.indexOf("?")));
check(executionFocus?.actorId === ACTOR && executionFocus.outputId === OUTPUT && executionFocus.eventId === EVENT, "C focus carries exact actor/output/event");
check(contributionForMetric(report, metric) === contribution && contribution.reportAnchor === "metric-revenue-growth", "Revenue Growth resolves the accepted hero contribution");
check(exactReviewCheck(review, metric)?.selector === selector && selectorMatches(selector, { ...selector, subjectRefs: [...selector.subjectRefs] }), "Report to Review uses exact scoped selector");
check(executionFocus?.returnAnchor === REVENUE_GROWTH_ANCHOR && component.includes("scrollIntoView"), "round-trip state restores the report anchor");

const reportUrl = resultsPath(RUN, "report", { runId: RUN, anchor: REVENUE_GROWTH_ANCHOR });
check(parseResultsFocus(RUN, "report", reportUrl.slice(reportUrl.indexOf("?")))?.anchor === REVENUE_GROWTH_ANCHOR, "refresh preserves A report focus");
check(!component.includes("65.47") && !component.includes("AGOUT-9ab72a67"), "report has no fixture value or identity fallback");
check(contributionForMetric({ ...report, sourceContributions: [{ ...contribution, calculationId: "CALC-OTHER" }] }, metric) === null &&
  !reportBundleMatches(
    { ...report, objectId: "OBJ", releasedResultId: "RESULT", reportId: "RESULT", canonicalExecutionRecordId: "CER" },
    { ...result, objectId: "OBJ", releasedResultId: "RESULT", canonicalRecordId: "CER" },
    { runId: "RUN-OTHER", objectId: "OBJ", releasedResultId: "RESULT", reportId: "RESULT", canonicalRecordId: "CER" },
    { ...review, objectId: "OBJ", releasedResultId: "RESULT", canonicalExecutionRecordId: "CER" }
  ), "no approximate or cross-run source fallback");
check(executionFocusMatches(execution, ACTOR, OUTPUT, EVENT)?.actor.actorId === ACTOR && !/(inputRefs\.map|observableProcess\.map|JSON\.stringify)/u.test(component), "C handoff validates exact observable refs without hidden CoT");

assert.equal(checks, 14);
console.log(`M3 focused interaction checks: ${checks}/14 PASS`);

// Render the actual component in memory using the existing Vite/React
// toolchain. These alternate statements are test data, never production Runs.
const renderer = await createServer({ server: { middlewareMode: true }, appType: "custom" });
let ReportComponent;
try {
  ({ InteractiveResearchReport: ReportComponent } = await renderer.ssrLoadModule("/src/components/results/InteractiveResearchReport.tsx"));
} finally {
  await renderer.close();
}
const renderSummary = (claims) => {
  const markup = renderToStaticMarkup(createElement(ReportComponent, {
    report: { ...report, anchors: [], availability: { reasonCode: "REPORT_SOURCE_MAP_PARTIAL" } },
    result: { ...result, claims: claims.map((item) => ({ ...item, calculationRefs: [], evidenceRefs: [] })), releasedAt: "2026-01-01", limitations: [], metrics: [{ ...metric, proof: { status: "VERIFIED" } }] },
    artifacts: { representations: [] }, review, backendOrigin: "", requestedAnchor: null,
    onOpenExecution: () => {}, onOpenReview: () => {}
  }));
  const summary = markup.match(/<section class="report-summary"[^>]*>([\s\S]*?)<\/section>/u);
  assert.ok(summary, "actual component renders the prominent summary");
  return summary[1];
};
const originalSummary = renderSummary([claim]);
const changedSummary = renderSummary([{ ...claim, statement: "Released test claim: revenue declined." }]);
const missingSummary = renderSummary([]);
const neutralBody = "<p>当前没有可展示的已发布核心结论。</p>";
check(originalSummary.includes(`<p>${claim.statement}</p>`), "summary renders the authoritative released claim");
check(!component.includes("财务增长强劲；估值、竞争和外部事件仍需独立证据。"), "old authored financial conclusion is absent from production component");
check(changedSummary.includes("<p>Released test claim: revenue declined.</p>") && !changedSummary.includes(claim.statement), "changed authoritative data changes the rendered conclusion");
check(missingSummary.includes(neutralBody), "missing claim renders a neutral unavailable state");
check(missingSummary === '<span>RELEASED RESEARCH SUMMARY</span><h3 id="report-summary-heading">核心研究结论</h3>' + neutralBody, "missing summary contains no manufactured financial conclusion");
check(renderSummary([{ ...claim, runId: "RUN-OTHER" }]) === missingSummary, "foreign-run claim cannot become a summary fallback");
assert.equal(checks, 20);
console.log("M7-R1 rendered summary provenance checks: 6/6 PASS");
