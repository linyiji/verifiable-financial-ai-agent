import assert from "node:assert/strict";
import test from "node:test";
import { decodeBrowserScenario } from "../src/scenario.mjs";

function scenario() {
  return {
    schemaVersion: "phase4-vs01-frontend-scenario/v1",
    object: { objectId: "OBJ-A", symbol: "AAA", companyName: "A Corp" },
    goalText: "Assess A Corp",
    asOf: "2026-09-05",
    missingRunId: "RUN-MISSING",
    foreign: {
      objectId: "OBJ-B",
      runId: "RUN-B",
      taskId: "TASK-B",
      sentinels: ["B Corp only"]
    },
    backendUnavailableFrontendUrl: "http://127.0.0.1:4174"
  };
}

test("scenario admits distinct captured A/B identities and a separate unavailable origin", () => {
  const decoded = decodeBrowserScenario(scenario(), "http://127.0.0.1:4173");
  assert.equal(decoded.object.objectId, "OBJ-A");
  assert.equal(decoded.foreign.runId, "RUN-B");
  assert.equal(decoded.missingErrorCode, "NOT_FOUND");
  assert.ok(Object.isFrozen(decoded));
});

test("scenario rejects same-Object contamination, Demo markers, and same-origin unavailable setup", () => {
  const sameObject = scenario();
  sameObject.foreign.objectId = "OBJ-A";
  assert.throws(() => decodeBrowserScenario(sameObject, "http://127.0.0.1:4173"), /foreign Object must differ/);

  const demo = scenario();
  demo.foreign.sentinels = ["RUN-DEMO-001"];
  assert.throws(() => decodeBrowserScenario(demo, "http://127.0.0.1:4173"), /DEMO_FALLBACK/);

  const sameOrigin = scenario();
  sameOrigin.backendUnavailableFrontendUrl = "http://127.0.0.1:4173/unavailable";
  assert.throws(() => decodeBrowserScenario(sameOrigin, "http://127.0.0.1:4173"), /separately launched origin/);
});
