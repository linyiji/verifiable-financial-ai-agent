import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { parseResultsFocus, resultsPath } from "../src/routing/resultsRoute.ts";
import {
  defaultExecutionActor,
  exactExecutionActor,
  exactExecutionTarget,
  executionRecordCards,
  filterExecutionActors,
  groupExecutionActors,
  inputRefKind,
  observableExecutionRows
} from "../src/components/results/executionModel.ts";

const RUN = "RUN-57aed683-75d6-4b47-acc6-a73053ea492e";
const ACTOR = "fundamental_analyst";
const OUTPUT = "AGOUT-9ab72a67-87e1-523a-a88f-1c4246a26330";
const EVENT = "EVT-9dc4ef04-5617-4652-9510-61b9905274a0";
const CALC = "CALC-RUN-57aed683-75d6-4b47-acc6-a73053ea492e-GROWTH";
const ANCHOR = "metric-revenue-growth";
const TASK = `${RUN}:fundamentals`;
const actor = (actorId, actorType, displayRole, eventCount = 1, recordCount = 1) => ({
  runId: RUN, actorId, actorType, displayRole, status: "SUCCESS", eventCount, recordCount
});
const actors = [
  actor("research_lead", "RESEARCH_LEAD", "Research Lead", 7, 1),
  actor(ACTOR, "SPECIALIST", "Fundamental Analyst", 40, 1),
  actor("peer_analyst", "SPECIALIST", "Peer Analyst"),
  actor("research_news_analyst", "SPECIALIST", "Research & News Analyst"),
  actor("risk_analyst", "SPECIALIST", "Risk Analyst"),
  actor("valuation_analyst", "SPECIALIST", "Valuation Analyst"),
  actor("fmp_data", "SUPPORTING_EXECUTION", "FMP / Data", 539, 539),
  actor("evidence_pipeline", "SUPPORTING_EXECUTION", "Evidence Pipeline"),
  actor("financial_code_runtime", "SUPPORTING_EXECUTION", "Financial Code Runtime"),
  actor("review", "SUPPORTING_EXECUTION", "Review"),
  actor("proof", "SUPPORTING_EXECUTION", "Proof"),
  actor("release", "SUPPORTING_EXECUTION", "Release")
];
const contribution = {
  runId: RUN, reportId: `RESULT-${RUN}`, artifactId: "RPT-HTML-b9ce5cd45ee1a1a95a8e",
  reportAnchor: ANCHOR, taskId: TASK, actorId: ACTOR, agentOutputId: OUTPUT,
  executionEventId: EVENT, calculationId: CALC, evidenceRefs: ["EVD-1", "EVD-2"],
  reviewId: `REVIEW-${RUN}`
};
const fundamentalDetail = {
  runId: RUN, actorId: ACTOR, actorType: "SPECIALIST",
  inputRefs: [{ runId: RUN, refId: CALC }, { runId: RUN, refId: "EVD-1" }],
  observableProcess: [{ runId: RUN, eventId: EVENT, taskId: TASK, eventType: "task.completed", status: "COMPLETED" }],
  outputs: [{ runId: RUN, outputId: OUTPUT, taskId: TASK, status: "SUCCESS", summary: "Safe summary", keyFindings: ["Finding"], risks: [], limitations: [] }],
  reportContributions: [contribution], quarantinedInputRefCount: 0
};
const leadDetail = {
  runId: RUN, actorId: "research_lead", actorType: "RESEARCH_LEAD", inputRefs: [],
  observableProcess: [{ runId: RUN, eventId: "EVT-LEAD", taskId: `${RUN}:lead`, eventType: "task.completed", status: "COMPLETED" }],
  outputs: [{ runId: RUN, outputId: "AGOUT-LEAD", taskId: `${RUN}:lead`, status: "SUCCESS", summary: null, keyFindings: [], risks: [], limitations: [] }],
  reportContributions: [], quarantinedInputRefCount: 0
};
const execution = {
  schemaVersion: "phase4.5-execution-record-surface/v1", runId: RUN, objectId: "OBJ-NVDA",
  releasedResultId: `RESULT-${RUN}`, canonicalExecutionRecordId: `CER-${RUN}`,
  actors, actorDetails: [fundamentalDetail, leadDetail], availability: { status: "PARTIAL", reasonCode: "REPORT_CONTRIBUTIONS_PARTIAL" }
};

const component = readFileSync(new URL("../src/components/results/InteractiveExecutionRecord.tsx", import.meta.url), "utf8");
const page = readFileSync(new URL("../src/pages/ResultsWorkspacePage.tsx", import.meta.url), "utf8");
const runWorkspace = readFileSync(new URL("../src/components/ResearchRuntimeWorkspace.tsx", import.meta.url), "utf8");

let count = 0;
const check = (condition, message) => { count += 1; assert.ok(condition, message); };

check(page.includes("<InteractiveExecutionRecord"), "Results C renders the interactive execution surface");
check(component.includes("execution-collaboration-view") && component.includes("Actor → I/P/O"), "actor-centered collaboration is the primary mode");
const groups = groupExecutionActors(execution);
check(groups.length === 3, "all three actor groups are present");
check(groups[0].groupKey === "RESEARCH_LEAD" && groups[0].actors.length === 1, "Research Lead is first and exact");
check(groups[1].groupKey === "SPECIALIST" && groups[1].actors.length === 5, "five Specialists are represented");
check(groups[2].groupKey === "SUPPORTING_EXECUTION" && groups[2].actors.length === 6, "six Supporting Execution actors are represented");
check(JSON.stringify(groups) === JSON.stringify(groupExecutionActors({ ...execution, actors: [...actors].reverse() })), "actor grouping and order are deterministic");
check(groupExecutionActors({ ...execution, actors: [...actors, { ...actors[0], actorId: "foreign", runId: "RUN-OTHER" }] }).flatMap((group) => group.actors).length === 12, "foreign-run actors are excluded from the rail");
check(defaultExecutionActor(execution)?.actorId === "research_lead", "Research Lead is the natural default selection");
check(exactExecutionActor(execution, ACTOR)?.detail === fundamentalDetail, "exact specialist actor resolves its public detail");
check(exactExecutionActor(execution, "fmp_data")?.detail === null, "supporting actor remains selectable without fabricated detail");
check(exactExecutionActor(execution, "missing") === null, "unknown actor fails closed");

const cards = executionRecordCards(fundamentalDetail);
check(cards.length === 1 && cards[0].taskId === TASK, "I/P/O is joined only by an exact task identity");
check(cards[0].contribution === contribution, "authoritative report contribution is attached to the exact output and event");
check(exactExecutionTarget(execution, ACTOR, OUTPUT, EVENT)?.contribution === contribution, "hero A-to-C target resolves exactly");
check(exactExecutionTarget(execution, ACTOR, "AGOUT-WRONG", EVENT) === null, "wrong AgentOutput fails closed");
check(exactExecutionTarget(execution, ACTOR, OUTPUT, "EVT-WRONG") === null, "wrong Event fails closed");
check(exactExecutionTarget({ ...execution, actorDetails: [{ ...fundamentalDetail, outputs: [...fundamentalDetail.outputs, fundamentalDetail.outputs[0]] }, leadDetail] }, ACTOR, OUTPUT, EVENT) === null, "duplicate exact target fails closed");
check(exactExecutionActor({ ...execution, actors: [...actors, actors[1]] }, ACTOR) === null, "duplicate actor identity fails closed");
check(executionRecordCards({ ...fundamentalDetail, reportContributions: [] })[0].contribution === null, "missing report contribution is not fabricated");

const focusUrl = resultsPath(RUN, "execution", { runId: RUN, actorId: ACTOR, outputId: OUTPUT, eventId: EVENT, returnAnchor: ANCHOR });
const focus = parseResultsFocus(RUN, "execution", focusUrl.slice(focusUrl.indexOf("?")));
check(focus?.actorId === ACTOR && focus.outputId === OUTPUT && focus.eventId === EVENT, "Report-to-Execution preserves exact hero identity");
check(focus?.returnAnchor === ANCHOR, "exact A-to-C handoff preserves return context");
const actorUrl = resultsPath(RUN, "execution", { runId: RUN, actorId: "risk_analyst", outputId: null, eventId: null, returnAnchor: null });
const actorFocus = parseResultsFocus(RUN, "execution", actorUrl.slice(actorUrl.indexOf("?")));
check(actorFocus?.actorId === "risk_analyst" && actorFocus.outputId === null && actorFocus.eventId === null, "actor selection is refresh-stable without invented output identity");
check(parseResultsFocus(RUN, "execution", "?actor=x&output=y") === null, "partial output/event focus is rejected");
check(filterExecutionActors(groups, "fundamental")[0].actors[0].actorId === ACTOR, "actor filter uses real identity fields");
check(observableExecutionRows(execution).length === 2, "secondary records project only available public detail");
check(observableExecutionRows({ ...execution, actorDetails: [...execution.actorDetails, { ...leadDetail, runId: "RUN-OTHER" }] }).length === 2, "secondary records reject foreign-run detail");
check(inputRefKind(CALC) === "Calculation" && inputRefKind("EVD-1") === "Evidence", "input refs receive truthful type labels");

check(component.includes("输入 · INPUT") && component.includes("可观察过程 · PROCESS") && component.includes("输出 · OUTPUT") && component.includes("报告贡献 · REPORT CONTRIBUTION"), "detail hierarchy includes Input, observable Process, Output, and Report Contribution");
check(component.includes("公共契约未投影 Actor 明细") && component.includes("报告贡献：未观察到明确关系"), "missing supporting detail is explicitly disclosed");
check(component.includes("不显示系统提示词、私有 scratchpad、模型内部推理或供应商原始响应"), "hidden chain-of-thought boundary is explicit");
check(!/(dangerouslySetInnerHTML|reasoningTrace|chainOfThought|rawProviderResponse)/u.test(component + page), "unsafe raw or hidden reasoning fields are never rendered");
check(page.includes("source.getExecutionRecordSurface(runId, root.value.objectId"), "Execution fetch is exact-run and exact-object");
check(page.includes("anchor: contribution.reportAnchor"), "Execution-to-Report uses the authoritative contribution anchor");
check(runWorkspace.includes("open-execution-workspace") && runWorkspace.includes("onOpenExecution"), "Run provides a natural direct entry to Results C");
check(component.includes("requestedInvalid ? null"), "invalid requested focus does not fall back to a different Actor");
check(!/(latestRun|fallbackExecution|fixtureExecution)/iu.test(page + component + runWorkspace), "no latest-run, fixture, or approximate Execution fallback exists");

assert.equal(count, 37);
console.log(`M5 focused execution checks: ${count}/37 PASS`);
