import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const specUrl = new URL("./vs01-frontend.real.spec.mjs", import.meta.url);
const assertionsUrl = new URL("../src/browser-assertions.mjs", import.meta.url);
const scenarioUrl = new URL("../src/scenario.mjs", import.meta.url);

test("production-counting browser spec cannot install response mocks or direct business state", async () => {
  const [source, assertionsSource, scenarioSource] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(assertionsUrl, "utf8"),
    readFile(scenarioUrl, "utf8")
  ]);
  const forbidden = [
    /page\s*\.\s*route\s*\(/,
    /context\s*\.\s*route\s*\(/,
    /route\s*\.\s*fulfill\s*\(/,
    /Fetch\.enable/,
    /setRequestInterception/,
    /replayXHR/,
    /setContent\s*\(/,
    /addInitScript\s*\(/,
    /test\s*\.\s*skip/,
    /DemoFrontendDataSource/,
    /DemoRuntimeTransport/,
    /DemoScenarioStore/,
    /directStore|setProjectionForTest|injectFixture/i
  ];
  for (const pattern of forbidden) assert.doesNotMatch(source, pattern);
  assert.match(source, /waitForResponse/);
  assert.match(source, /decodePreparedResearchDraft/);
  assert.match(source, /decodeConfirmRunResponse/);
  assert.match(source, /decodeAtomicRunProjection/);
  assert.match(source, /backendUnavailableFrontendUrl/);
  assert.match(source, /primaryApiBaseUrl/);
  assert.match(source, /unavailableApiBaseUrl/);
  assert.match(scenarioSource, /VFAS_VS01_SECRET_SENTINEL/);
  assert.match(source, /loadedFrontendSources\(page, request, \[scenario\.secretSentinel\]\)/);
  assert.match(source, /scenario\.alternate\.runId/);
  assert.match(source, /scenario\.alternate\.objectId/);
  assert.match(source, /scenario\.financial\.runId/);
  assert.match(source, /scenario\.financial\.metricId/);
  assert.equal(
    (source.match(/secretSentinel: scenario\.secretSentinel/g) ?? []).length,
    7,
    "every ledger must exact-scan the runner secret sentinel"
  );
  assert.match(source, /assertApiBinding/);
  assert.match(source, /findPublicSurfaceLeaks/);
  assert.equal(
    (source.match(/await ledger\.drainAndAssertPublicEvidenceClean\(/g) ?? []).length,
    7,
    "every real spec must await public response evidence before receiving control credit"
  );
  assert.doesNotMatch(source, /ledger\.assertNoRuntimeFailures\(/);
  assert.doesNotMatch(source, /admitContextProjection/);
  assert.doesNotMatch(source, /decodeFrontendRuntimeBinding|frontendRuntimeConfigPath|frontend_build_sha256|binding_mode/);
  assert.match(source, /context\.setOffline\(true\)/);
  assert.match(source, /context\.setOffline\(false\)/);
  assert.match(source, /last-event-id/);
  assert.match(source, /text\/event-stream/);
  assert.match(source, /newCDPSession/);
  assert.match(source, /Network\.emulateNetworkConditionsByRule/);
  assert.doesNotMatch(source, /Network\.emulateNetworkConditions"/);
  assert.match(source, /appliedNetworkConditionsId/);
  assert.match(source, /run-navigation-item/);
  assert.match(source, /data-task-status/);
  assert.match(source, /data-task-progress/);
  assert.match(source, /data-parent-task-id/);
  assert.match(source, /data-dependency-ids/);
  assert.match(source, /data-projection-sequence/);
  assert.match(source, /data-connection-state/);
  assert.equal(
    (source.match(/await assertLiveResponsePending\(/g) ?? []).length,
    2,
    "switch and offline evidence must prove the observed SSE response is still live"
  );
  assert.doesNotMatch(source, /\.request\(\)\.finished\(\)/);
  assert.match(source, /researchPath\.getByTestId\("research-task"\)/);
  assert.match(source, /DYN-001 requires at least one authoritative projected Task/);
  assert.match(source, /new MutationObserver\(\(records\)/);
  assert.match(source, /attributeOldValue: true/);
  assert.match(source, /observedWorkspace\.attributeMutations/);
  assert.match(source, /observedWorkspace\.childMutations/);
  assert.match(source, /observedWorkspace\.routes/);
  assert.match(source, /data-request-epoch/);
  assert.match(source, /data-consumed-request-epoch/);
  assert.match(source, /data-last-discarded-request-epoch/);
  assert.match(source, /data-last-discarded-projection-sequence/);
  assert.match(source, /waitForDiscardedProjectionLifecycle/);
  assert.doesNotMatch(source, /crossPublicDomSettlementBarrier|waitForTimeout\(/);
  assert.doesNotMatch(source, /setInterval\(/);
  assert.match(source, /observeNextProjectionResponse/);
  assert.doesNotMatch(source, /possibleFinalProjection/);
  assert.match(assertionsSource, /Frontend source discovery produced no independently fetchable module/);
  assert.match(assertionsSource, /Frontend source fetch failed/);
  assert.match(assertionsSource, /sha256Bytes\(body\)/);
  assert.match(assertionsSource, /response\.allHeaders\(\)/);
  assert.match(assertionsSource, /response\.body\(\)/);
  assert.match(assertionsSource, /MAX_PUBLIC_RESPONSE_BODY_BYTES/);
  assert.match(assertionsSource, /ACTIVE_EVENT_STREAM_NOT_BUFFERED/);
  assert.match(assertionsSource, /publicResponses/);
  assert.match(assertionsSource, /new Set\(\["fetch", "xhr"\]\)/);
  assert.match(assertionsSource, /scanPublicRequest/);
  assert.match(assertionsSource, /request\.postDataBuffer/);
  assert.match(assertionsSource, /MAX_PUBLIC_REQUEST_BODY_BYTES/);
  assert.match(assertionsSource, /allowedRequestFailures/);
  assert.match(assertionsSource, /requestFailures\.length/);
  assert.match(assertionsSource, /EXACT_SECRET_SENTINEL|exactSentinels/);
  assert.match(source, /decodeReleasedFinancialMetricEvidence/);
  assert.match(source, /canonical-financial-value/);
  assert.match(source, /String\(Number\(metric\.canonicalValue\)\)/);
  assert.equal((source.match(/^\s*test\("/gm) ?? []).length, 7, "real suite must contain exactly seven strict specs");

  const expectedControls = new Set([
    ...Array.from({ length: 10 }, (_, index) => `VS01-FE-${String(index + 3).padStart(3, "0")}`),
    "VS01-DYN-001",
    "VS01-REC-008",
    "VS01-REC-009",
    "VS01-ID-003"
  ]);
  const annotatedControls = new Map();
  for (const call of source.matchAll(/controlEvidence\(([\s\S]*?)\)\s*,\s*async/g)) {
    for (const match of call[1].matchAll(/"(VS01-[A-Z]+-[0-9]{3})"/g)) {
      annotatedControls.set(match[1], (annotatedControls.get(match[1]) ?? 0) + 1);
    }
  }
  assert.deepEqual(new Set(annotatedControls.keys()), expectedControls);
  for (const [controlId, count] of annotatedControls) {
    assert.equal(count, 1, `${controlId} must be annotated exactly once`);
  }
});
