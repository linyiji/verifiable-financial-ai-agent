import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { parseResultsFocus, resultsPath } from "../src/routing/resultsRoute.ts";
import {
  checkPresentation,
  exceptionReviewChecks,
  groupFinancialReview,
  resolveExactReviewCheck,
  reviewGateSatisfied,
  reviewHasObservableMachineRelation,
  reviewSelectorKey
} from "../src/components/results/reviewModel.ts";

const RUN = "RUN-57aed683-75d6-4b47-acc6-a73053ea492e";
const OBJECT = "OBJ-NVDA";
const REVIEW = `REVIEW-${RUN}`;
const codes = [
  ...Array(10).fill("FIN_CALCULATION_IDENTITY"),
  ...Array(10).fill("FIN_CALCULATION_INPUT_SNAPSHOT"),
  ...Array(10).fill("FIN_CALCULATION_RECOMPUTATION"),
  "FIN_MATERIAL_FORMULA_CLOSURE",
  ...Array(10).fill("FIN_METRIC_BINDING"),
  ...Array(10).fill("FIN_CLAIM_SUPPORT"),
  "FIN_TYPED_RELEASE_CARDINALITY",
  "FIN_JUDGMENT_SUPPORT",
  "FIN_PROOF_REQUIREMENT_CLOSURE"
];
const checks = codes.map((checkCode, index) => ({
  selector: { reviewId: REVIEW, checkCode, subjectRefs: [`CALC-${String(index).padStart(2, "0")}`] },
  status: "PASS",
  safeExplanation: null,
  inputRefs: [{ runId: RUN, relationType: "REVIEW_SUBJECT", status: "AVAILABLE", targetRef: `CALC-${String(index).padStart(2, "0")}` }],
  outputRefs: []
}));
const review = {
  schemaVersion: "phase4.5-financial-review-surface/v1", runId: RUN, objectId: OBJECT,
  releasedResultId: `RESULT-${RUN}`, canonicalExecutionRecordId: `CER-${RUN}`,
  reviewId: REVIEW, reviewer: "deterministic-review", verdict: "PASS", checks,
  availability: { status: "READY", reasonCode: null }
};
const component = readFileSync(new URL("../src/components/results/InteractiveFinancialReview.tsx", import.meta.url), "utf8");
const resultsPage = readFileSync(new URL("../src/pages/ResultsWorkspacePage.tsx", import.meta.url), "utf8");
const runWorkspace = readFileSync(new URL("../src/components/ResearchRuntimeWorkspace.tsx", import.meta.url), "utf8");

let count = 0;
const check = (condition, message) => { count += 1; assert.ok(condition, message); };

check(resultsPage.includes("<InteractiveFinancialReview"), "Results B directly renders shared Review");
check(runWorkspace.includes("<InteractiveFinancialReview"), "Run Stage 03 directly renders shared Review");
check(checks.length === 54 && groupFinancialReview(review).reduce((sum, group) => sum + group.checks.length, 0) === 54, "all 54 checks are represented");
check(groupFinancialReview(review).length === 4, "real codes form the smallest four useful groups");
check(JSON.stringify(groupFinancialReview(review)) === JSON.stringify(groupFinancialReview({ ...review, checks: [...checks].reverse() })), "grouping is deterministic independent of input order");

const selected = checks[32].selector;
check(resolveExactReviewCheck(review, selected) === checks[32], "scoped selector resolves one exact check");
check(resolveExactReviewCheck(review, { ...selected, subjectRefs: ["CALC-WRONG"] }) === null, "wrong selector fails closed");
check(resolveExactReviewCheck({ ...review, checks: [...checks, checks[32]] }, selected) === null, "duplicate selector fails closed");
check(reviewSelectorKey({ ...selected, subjectRefs: ["Z", "A"] }) === null, "unsorted selector fails closed");
check(!reviewHasObservableMachineRelation(checks[0]), "missing relation is not fabricated");

check(component.includes("review-mode-full") && component.includes("review-full-content"), "full Review mode is implemented");
check(exceptionReviewChecks(review).length === 0 && component.includes("review-mode-exceptions"), "exception mode filters authoritative status");
check(exceptionReviewChecks({ ...review, checks: [{ ...checks[0], status: "REVIEW" }] }).length === 1, "exception mode includes actual REVIEW status");
check(component.includes("输入 · INPUT") && component.includes("复核逻辑 · PROCESS") && component.includes("结果 · RESULT") && component.includes("复核结论 · VERDICT"), "I/P/R/V hierarchy is present");
check(!/(dangerouslySetInnerHTML|JSON\.stringify\(check|observableProcess\.map|hidden reasoning)/u.test(component), "no raw dump, unsafe field, or hidden CoT exposure");

const reviewUrl = resultsPath(RUN, "review", { reviewId: REVIEW, checkCode: selected.checkCode, subjectRefs: selected.subjectRefs, returnAnchor: "metric-revenue-growth" });
const focus = parseResultsFocus("review", reviewUrl.slice(reviewUrl.indexOf("?")));
check(focus?.reviewId === REVIEW && focus.subjectRefs[0] === selected.subjectRefs[0], "Report to Review preserves exact selector");
check(focus?.returnAnchor === "metric-revenue-growth" && component.includes("查看报告位置"), "Review to Report preserves authoritative return anchor");
check(component.includes("returnAnchor={focused === check ? returnAnchor : null}"), "report return action is limited to the exact focused check");
const foreignReview = { ...review, runId: "RUN-OTHER", reviewId: "REVIEW-RUN-OTHER", checks: checks.map((item) => ({ ...item, selector: { ...item.selector, reviewId: "REVIEW-RUN-OTHER" } })) };
check(resolveExactReviewCheck(foreignReview, selected) === null, "cross-run Review selector is rejected");
check(resultsPage.includes("source.getFinancialReviewSurface(runId, root.value.objectId"), "Review fetch is exact-run and exact-object");
check(!/(fixture|latestRun|fallbackReview)/iu.test(resultsPage + runWorkspace), "no fixture or latest-run fallback");

const projection = { run: { runId: RUN }, object: { objectId: OBJECT }, review: { reviewId: REVIEW, availability: { status: "AVAILABLE" }, status: "PASS" } };
check(reviewGateSatisfied(projection, review), "READY PASS Review satisfies Stage 04 gate");
check(!reviewGateSatisfied(projection, { ...review, verdict: "REVIEW" }), "non-PASS Review cannot satisfy Stage 04 gate");
check(!reviewGateSatisfied(projection, { ...review, runId: "RUN-OTHER" }), "cross-run Review cannot satisfy Stage 04 gate");
check(runWorkspace.includes("(reportDone || completeDone) && reviewDone"), "report existence alone cannot mark Stage 04 done");
check(component.includes("未观察到精确关联") && component.includes("hasMachineRelation && onOpenExecution"), "Review-to-C action is gated by an observable machine relation");
check(checkPresentation("UNKNOWN").groupKey === "GENERAL", "unknown real code remains visible in GENERAL");

assert.equal(count, 27);
console.log(`M4 focused interaction checks: ${count}/27 PASS`);
