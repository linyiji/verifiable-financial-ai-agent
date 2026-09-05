import assert from "node:assert/strict";
import test from "node:test";
import {
  apiRoutePathname,
  apiRouteUrl,
  assertApiBaseRequests,
  isExactApiRoute
} from "../src/browser-assertions.mjs";
import { decodeBrowserScenario, decodeSecretSentinel } from "../src/scenario.mjs";

function scenario() {
  return {
    schemaVersion: "phase4-vs01-frontend-scenario/v1",
    object: { objectId: "OBJ-A", symbol: "AAA", companyName: "A Corp" },
    goalText: "Assess A Corp",
    asOf: "2026-09-05",
    missingRunId: "RUN-MISSING",
    alternate: {
      objectId: "OBJ-A",
      runId: "RUN-A-ALTERNATE",
      taskId: "TASK-A-ALTERNATE"
    },
    foreign: {
      objectId: "OBJ-B",
      runId: "RUN-B",
      taskId: "TASK-B",
      sentinels: ["B Corp only"]
    },
    financial: {
      objectId: "OBJ-C",
      runId: "RUN-C-RELEASED",
      metricId: "METRIC-C-ADVERSARIAL",
      adversarialProperty: "NUMBER_STRING_ROUNDTRIP_CHANGES"
    },
    backendUnavailableFrontendUrl: "http://127.0.0.1:4174",
    primaryApiBaseUrl: "http://127.0.0.1:8000/api",
    unavailableApiBaseUrl: "http://127.0.0.1:65534/api"
  };
}

test("scenario admits distinct captured A/B identities and a separate unavailable origin", () => {
  const decoded = decodeBrowserScenario(scenario(), "http://127.0.0.1:4173");
  assert.equal(decoded.object.objectId, "OBJ-A");
  assert.equal(decoded.alternate.runId, "RUN-A-ALTERNATE");
  assert.equal(decoded.foreign.runId, "RUN-B");
  assert.equal(decoded.financial.metricId, "METRIC-C-ADVERSARIAL");
  assert.equal(decoded.missingErrorCode, "NOT_FOUND");
  assert.equal(decoded.primaryApiBaseUrl, "http://127.0.0.1:8000/api");
  assert.equal(decoded.unavailableApiBaseUrl, "http://127.0.0.1:65534/api");
  assert.ok(Object.isFrozen(decoded));
});

test("scenario rejects same-Object contamination, Demo markers, and same-origin unavailable setup", () => {
  const sameObject = scenario();
  sameObject.foreign.objectId = "OBJ-A";
  assert.throws(() => decodeBrowserScenario(sameObject, "http://127.0.0.1:4173"), /foreign Object must differ/);

  const crossObjectAlternate = scenario();
  crossObjectAlternate.alternate.objectId = "OBJ-B";
  assert.throws(
    () => decodeBrowserScenario(crossObjectAlternate, "http://127.0.0.1:4173"),
    /alternate Run must belong/
  );

  const reusedAlternate = scenario();
  reusedAlternate.alternate.runId = reusedAlternate.foreign.runId;
  assert.throws(() => decodeBrowserScenario(reusedAlternate, "http://127.0.0.1:4173"), /must be distinct/);

  const reusedForeignFinancial = scenario();
  reusedForeignFinancial.financial.runId = reusedForeignFinancial.foreign.runId;
  assert.throws(
    () => decodeBrowserScenario(reusedForeignFinancial, "http://127.0.0.1:4173"),
    /foreign quarantine Runs/
  );

  const unsupportedAdversarialProperty = scenario();
  unsupportedAdversarialProperty.financial.adversarialProperty = "TRUST_SCENARIO_VALUE";
  assert.throws(
    () => decodeBrowserScenario(unsupportedAdversarialProperty, "http://127.0.0.1:4173"),
    /NUMBER_STRING_ROUNDTRIP_CHANGES/
  );

  const scenarioValueIsNotAuthority = scenario();
  scenarioValueIsNotAuthority.financial.canonicalValue = "0.6547000000000000";
  assert.throws(
    () => decodeBrowserScenario(scenarioValueIsNotAuthority, "http://127.0.0.1:4173"),
    /extra=canonicalValue/
  );

  const demo = scenario();
  demo.foreign.sentinels = ["RUN-DEMO-001"];
  assert.throws(() => decodeBrowserScenario(demo, "http://127.0.0.1:4173"), /DEMO_FALLBACK/);

  const sameOrigin = scenario();
  sameOrigin.backendUnavailableFrontendUrl = "http://127.0.0.1:4173/unavailable";
  assert.throws(() => decodeBrowserScenario(sameOrigin, "http://127.0.0.1:4173"), /separately launched origin/);

  const credentialUrl = scenario();
  credentialUrl.backendUnavailableFrontendUrl = "http://operator:password@127.0.0.1:4174";
  assert.throws(() => decodeBrowserScenario(credentialUrl, "http://127.0.0.1:4173"), /credentials are forbidden/);

  const queryApi = scenario();
  queryApi.primaryApiBaseUrl = "http://127.0.0.1:8000/api?binding=other";
  assert.throws(() => decodeBrowserScenario(queryApi, "http://127.0.0.1:4173"), /query and fragment/);

  const sameApi = scenario();
  sameApi.unavailableApiBaseUrl = sameApi.primaryApiBaseUrl;
  assert.throws(() => decodeBrowserScenario(sameApi, "http://127.0.0.1:4173"), /must differ/);
});

test("secret sentinel environment value is required and canonical without being stored in scenario JSON", () => {
  assert.equal(decodeSecretSentinel("random-vs01-sentinel-123"), "random-vs01-sentinel-123");
  assert.throws(() => decodeSecretSentinel(undefined), /expected non-empty string/);
  assert.throws(() => decodeSecretSentinel(" padded-secret "), /sentinel must be canonical/);
});

test("reviewed public API base proof is independent of frontend binding implementation", () => {
  const apiRequest = {
    ordinal: 4,
    method: "GET",
    origin: "http://127.0.0.1:8000",
    pathname: "/api/objects"
  };
  assert.doesNotThrow(() => assertApiBaseRequests("http://127.0.0.1:8000/api", [apiRequest]));
  assert.throws(() => assertApiBaseRequests("http://127.0.0.1:8000/api", [
    { ...apiRequest, origin: "http://127.0.0.1:8001" }
  ]), /escaped the reviewed API base/);
  assert.throws(() => assertApiBaseRequests("http://127.0.0.1:8000/api", [
    { ...apiRequest, pathname: "/other/objects" }
  ]), /escaped the reviewed API base/);
  assert.equal(
    apiRouteUrl("http://127.0.0.1:8000/api", "/research-runs/RUN-A/projection"),
    "http://127.0.0.1:8000/api/research-runs/RUN-A/projection"
  );
  assert.equal(
    apiRoutePathname("http://127.0.0.1:8000/api", "/objects"),
    "/api/objects"
  );
  assert.equal(
    isExactApiRoute(
      "http://127.0.0.1:8000/api/research-runs/RUN-A/events",
      "http://127.0.0.1:8000/api",
      "/research-runs/RUN-A/events"
    ),
    true
  );
});
