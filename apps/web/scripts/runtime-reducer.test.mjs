import assert from "node:assert/strict";
import { DemoFrontendDataSource } from "../src/data/DemoFrontendDataSource.ts";
import { assertProjectionIdentity, auxiliaryProjections, demoScenarios, runtimeEventsByRun, SCENARIO_RUN_IDS } from "../src/state/demoScenarios/index.ts";
import { reduceRuntimeEvent } from "../src/state/runtimeEventReducer.ts";
import { readRoute, routeHref } from "../src/routing/history.ts";

const scenario = (id) => structuredClone(demoScenarios.find((item) => item.id === id));
const replay = (projection, events) => events.reduce(reduceRuntimeEvent, structuredClone(projection));

for (const item of demoScenarios) assert.doesNotThrow(() => assertProjectionIdentity(item.initialProjection), `${item.id} identity closure`);
for (const projection of auxiliaryProjections) assert.doesNotThrow(() => assertProjectionIdentity(projection), `${projection.run.id} identity closure`);

const full = scenario("scene-01-full");
const capabilityEvent = full.events.findIndex((event) => event.type === "task.waiting_for_capability");
const atCapability = replay(full.initialProjection, full.events.slice(0, capabilityEvent + 1));
assert.equal(atCapability.run.tasks.length, full.initialProjection.run.tasks.length, "capability wait stays inside the same task");
const fullFinal = replay(full.initialProjection, full.events);
assert.equal(fullFinal.run.status, "COMPLETED");
assert.equal(fullFinal.reportArtifact.status, "READY");
assert.equal(fullFinal.claims.length, 4);
assert.equal(fullFinal.reviews.filter((record) => record.kind === "CLAIM").length, 4);
assert.equal(fullFinal.execution.status, "RELEASED");
assert.equal(fullFinal.releasedResult.status, "AVAILABLE");
assert.equal(fullFinal.reportArtifact.pdfDownloadUrl, undefined, "near-empty PDF must not be presented");
assert.match(fullFinal.reportArtifact.pdfUnavailableReason, /disabled/i);
assert.doesNotThrow(() => assertProjectionIdentity(fullFinal));

const invalidRelease = reduceRuntimeEvent(full.initialProjection, full.events.at(-1));
assert.equal(invalidRelease.run.status, "RESULT_PREPARING", "release.completed cannot bypass atomic prerequisites");
assert.notEqual(invalidRelease.releasedResult.status, "AVAILABLE");
const preparedIndex = full.events.findIndex((event) => event.type === "result.prepared");
const beforePreparation = replay(full.initialProjection, full.events.slice(0, preparedIndex));
const missingArtifactEvent = { ...full.events[preparedIndex], payload: { message: "artifact omitted" } };
const missingArtifactPrepared = reduceRuntimeEvent(beforePreparation, missingArtifactEvent);
const missingArtifactRelease = reduceRuntimeEvent(missingArtifactPrepared, full.events.at(-1));
assert.equal(missingArtifactPrepared.reportArtifact.status, "PENDING", "result.prepared requires an owned artifact payload");
assert.equal(missingArtifactRelease.run.status, "RESULT_PREPARING", "missing artifact blocks atomic release");

const correctionTaskId = full.initialProjection.run.tasks[0].id;
const correctionStarted = reduceRuntimeEvent(full.initialProjection, {
  event_id: "TEST-SELF-CORRECTION-START", run_id: full.initialProjection.run.id, task_id: correctionTaskId,
  type: "task.self_correcting", timestamp: "2026-09-04T00:00:01.000Z", sequence: 100,
  payload: { change_id: "TEST-SELF-CORRECTION", reason: "Period mismatch" }
});
assert.equal(correctionStarted.run.tasks[0].status, "SELF_CORRECTING");
assert.equal(correctionStarted.run.pathChanges[0].type, "SELF_CORRECTION");
const correctionResolved = reduceRuntimeEvent(correctionStarted, {
  event_id: "TEST-SELF-CORRECTION-END", run_id: full.initialProjection.run.id, task_id: correctionTaskId,
  type: "correction.resolved", timestamp: "2026-09-04T00:00:02.000Z", sequence: 101,
  payload: { change_id: "TEST-SELF-CORRECTION", reason: "Period aligned" }
});
assert.equal(correctionResolved.run.pathChanges[0].status, "RESOLVED");
const unsupportedMutation = reduceRuntimeEvent(full.initialProjection, {
  event_id: "TEST-UNSUPPORTED-MUTATION", run_id: full.initialProjection.run.id, task_id: correctionTaskId,
  type: "replan.requested", timestamp: "2026-09-04T00:00:03.000Z", sequence: 102,
  payload: { mutation_type: "WAIT_FOR_USER", reason: "Future contract" }
});
assert.equal(unsupportedMutation.run.status, "ACTION_REQUIRED", "future mutation types fail closed instead of being misrepresented");
assert.equal(unsupportedMutation.run.pathChanges.length, 0);
assert.equal(unsupportedMutation.execution.releaseGate, "FAILED");

const anchoredHref = routeHref({
  page: "results", runId: SCENARIO_RUN_IDS.trace, tab: "report",
  focusClaimId: `${SCENARIO_RUN_IDS.trace}-CLM-GROWTH`, reportAnchor: "financial-analysis"
});
assert.match(anchoredHref, /reportAnchor=financial-analysis/, "report anchor is addressable");
const anchoredRoute = readRoute({ pathname: `/runs/${SCENARIO_RUN_IDS.trace}`, search: anchoredHref.slice(anchoredHref.indexOf("?")) });
assert.equal(anchoredRoute.reportAnchor, "financial-analysis", "report anchor survives route hydration");

const dynamic = scenario("scene-02-dynamic");
const dynamicFinal = replay(dynamic.initialProjection, dynamic.events);
assert.equal(dynamic.initialProjection.run.initialTasks.length, 7);
assert.equal(dynamicFinal.run.tasks.length, 8);
assert.equal(dynamicFinal.run.tasks.filter((task) => task.isDynamic).length, 1);
assert.equal(dynamicFinal.run.graphVersion, 2);
assert.equal(dynamicFinal.run.pathChanges.filter((change) => change.type === "ADD_TASK").length, 1);
assert.equal(dynamicFinal.run.pathChanges.filter((change) => change.type === "CHANGE_DEPENDENCY").length, 1);
assert.equal(dynamicFinal.run.tasks.find((task) => task.id.endsWith("TASK-E"))?.status, "RUNNING");

const incremental = scenario("scene-06-incremental");
const incrementalSource = auxiliaryProjections.find((projection) => projection.run.id === incremental.initialProjection.run.memory?.sourceRunId);
assert.equal(incrementalSource?.run.scenarioId, "scene-06-incremental", "incremental memory source is scenario-owned");
assert.equal(incrementalSource?.run.pathChanges.filter((change) => change.type === "SELF_CORRECTION").length, 1);
assert.equal(incremental.initialProjection.run.incrementalStrategy?.metrics.find((metric) => metric.label === "Self-Corrections")?.current, "0");

const run026Initial = structuredClone(auxiliaryProjections.find((projection) => projection.run.id === SCENARIO_RUN_IDS.run026));
const run026Final = replay(run026Initial, runtimeEventsByRun.get(SCENARIO_RUN_IDS.run026));
assert.equal(run026Final.run.initialTasks.length, 6, "RUN-026 initial task contract");
assert.equal(run026Final.run.tasks.length, 7, "RUN-026 actual task contract");
assert.equal(run026Final.run.tasks.filter((task) => task.isDynamic).length, 1, "RUN-026 adds B1 exactly once");
assert.ok(run026Final.run.tasks.some((task) => task.id.endsWith("TASK-E")), "RUN-026 keeps E");
assert.ok(run026Final.run.tasks.some((task) => task.id.endsWith("TASK-F")), "RUN-026 keeps F");

const dataSource = new DemoFrontendDataSource();
for (const event of full.events) await dataSource.applyRuntimeEvent(full.initialProjection.run.id, event);
const reopened = await dataSource.getRunProjection(full.initialProjection.run.id);
assert.equal(reopened.run.status, fullFinal.run.status);
assert.equal(reopened.run.graphVersion, fullFinal.run.graphVersion);
assert.equal(reopened.run.tasks.length, fullFinal.run.tasks.length);
assert.equal(reopened.reviews.length, fullFinal.reviews.length);
assert.equal(reopened.reportArtifact.status, fullFinal.reportArtifact.status);
assert.equal(reopened.execution.status, fullFinal.execution.status);

const broadcomSearch = await dataSource.searchObjects("AVGO");
assert.equal(broadcomSearch[0]?.symbol, "AVGO");
const avgo = await dataSource.createObject(broadcomSearch[0]);
await assert.rejects(() => dataSource.prepareResearchRun({ objectId: avgo.id, goal: "Incremental without history", template: "COMPREHENSIVE", mode: "INCREMENTAL" }), /released source Run/, "AVGO cannot inherit another object's memory");
const avgoPlan = await dataSource.prepareResearchRun({ objectId: avgo.id, goal: "Assess Broadcom without cross-company fallback", template: "COMPREHENSIVE" });
const avgoRun = await dataSource.createResearchRun({ objectId: avgo.id, goal: avgoPlan.goal, planId: avgoPlan.planId });
const avgoProjection = await dataSource.getRunProjection(avgoRun.id);
assert.equal(avgoProjection.run.symbol, "AVGO");
assert.ok(avgoProjection.run.tasks.every((task) => task.objectId === avgo.id && task.symbol === "AVGO" && task.runId === avgoRun.id));
assert.equal(avgoProjection.reportArtifact.preview.symbol, "AVGO");
for (const event of runtimeEventsByRun.get(avgoRun.id)) await dataSource.applyRuntimeEvent(avgoRun.id, event);
const avgoFinal = await dataSource.getRunProjection(avgoRun.id);
assert.equal(avgoFinal.run.status, "RESULT_PREPARING", "semantically empty AVGO research must fail closed");
assert.equal(avgoFinal.reportArtifact.status, "ERROR");
assert.equal(avgoFinal.releasedResult.status, "PREPARING");
assert.equal(avgoFinal.execution.releaseGate, "FAILED");
assert.equal(avgoFinal.reportArtifact.htmlDownloadUrl, undefined);
assert.ok(avgoFinal.claims.every((claim) => claim.reviewStatus === "REVIEW"), "unavailable claims cannot receive PASS");
assert.ok(avgoFinal.reviews.filter((record) => record.kind === "CLAIM").every((record) => record.status === "REVIEW"), "unavailable reviews remain open");
assert.doesNotThrow(() => assertProjectionIdentity(avgoFinal));
assert.equal(avgoFinal.reportArtifact.preview.company, "Broadcom Inc.");
assert.equal(avgoFinal.reportArtifact.preview.symbol, "AVGO");
assert.doesNotMatch(JSON.stringify(avgoFinal), /NVIDIA|NVDA/);
await assert.rejects(() => dataSource.prepareResearchRun({ objectId: avgo.id, goal: "Incremental Broadcom follow-up", template: "COMPREHENSIVE", mode: "INCREMENTAL" }), /released source Run/, "blocked AVGO release cannot become incremental memory");

const amdProjection = auxiliaryProjections.find((projection) => projection.run.id === SCENARIO_RUN_IDS.amd);
await assert.rejects(() => dataSource.getClaim(amdProjection.run.id, `${SCENARIO_RUN_IDS.trace}-CLM-GROWTH`), /not found/, "claim lookup must be keyed by runId and claimId");

console.log(`scenario acceptance: 6 scenes identity-closed; full ${fullFinal.events.length} events; dynamic ${dynamicFinal.run.initialTasks.length}→${dynamicFinal.run.tasks.length}; RUN-026 6→7; durable reopen PASS; AVGO semantic release fail-closed PASS`);
