import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import {
  BrowserEvidenceLedger,
  capturePublicBusinessResponse,
  decodeProjectionLifecycleAttributes,
  discoverFrontendSourceUrls,
  fetchFrontendSources,
  MAX_PUBLIC_REQUEST_BODY_BYTES,
  MAX_PUBLIC_RESPONSE_BODY_BYTES
} from "../src/browser-assertions.mjs";

function lifecycleAttributes(overrides = {}) {
  return {
    runId: "RUN-B",
    requestEpoch: "8",
    settled: "true",
    consumedRunId: "RUN-B",
    consumedRequestEpoch: "8",
    consumedProjectionRevision: "3",
    consumedProjectionSequence: "17",
    discardedRunId: "RUN-A",
    discardedRequestEpoch: "7",
    discardedProjectionRevision: "2",
    discardedProjectionSequence: "11",
    discardReason: "STALE_RESPONSE",
    ...overrides
  };
}

test("public projection lifecycle decoder ties settled and discarded responses to exact Run epochs", () => {
  const decoded = decodeProjectionLifecycleAttributes(lifecycleAttributes());
  assert.deepEqual(decoded, {
    runId: "RUN-B",
    requestEpoch: 8,
    settled: true,
    consumed: { runId: "RUN-B", requestEpoch: 8, projectionRevision: 3, projectionSequence: 17 },
    discarded: {
      runId: "RUN-A",
      requestEpoch: 7,
      projectionRevision: 2,
      projectionSequence: 11,
      reason: "STALE_RESPONSE"
    }
  });
  assert.throws(
    () => decodeProjectionLifecycleAttributes(lifecycleAttributes({ consumedRequestEpoch: "7" })),
    /current consumed response/
  );
  assert.throws(
    () => decodeProjectionLifecycleAttributes(lifecycleAttributes({ discardedProjectionSequence: null })),
    /wholly present or absent/
  );
  assert.throws(
    () => decodeProjectionLifecycleAttributes(lifecycleAttributes({ discardReason: "IGNORED" })),
    /unsupported/
  );
  assert.throws(
    () => decodeProjectionLifecycleAttributes(lifecycleAttributes({ requestEpoch: "08" })),
    /canonical integer/
  );
});

function apiResponse({
  body = "{}",
  headers = { "content-type": "application/json" },
  status = 200,
  url = "http://127.0.0.1:8000/api/objects",
  resourceType = "fetch"
} = {}) {
  const bytes = Buffer.from(body, "utf8");
  return {
    allHeaders: async () => headers,
    body: async () => bytes,
    ok: () => status >= 200 && status < 300,
    request: () => ({ method: () => "GET", resourceType: () => resourceType, url: () => url }),
    status: () => status,
    url: () => url
  };
}

function browserRequest({
  body = null,
  failureText = "net::ERR_ABORTED",
  headers = {},
  method = "POST",
  resourceType = "fetch",
  url = "http://127.0.0.1:8000/api/research-runs/prepare"
} = {}) {
  const bytes = body === null ? null : Buffer.from(body, "utf8");
  return {
    headers: () => headers,
    failure: () => ({ errorText: failureText }),
    method: () => method,
    postDataBuffer: () => bytes,
    resourceType: () => resourceType,
    url: () => url
  };
}

test("frontend source discovery and fetch fail closed and hash exact response bytes", async () => {
  assert.throws(
    () => discoverFrontendSourceUrls("http://127.0.0.1:4173", [], []),
    /no independently fetchable module/
  );
  const urls = discoverFrontendSourceUrls(
    "http://127.0.0.1:4173",
    ["http://127.0.0.1:4173/assets/z.js", "http://127.0.0.1:8000/api/objects"],
    ["http://127.0.0.1:4173/assets/a.js"]
  );
  assert.deepEqual(urls, [
    "http://127.0.0.1:4173/assets/a.js",
    "http://127.0.0.1:4173/assets/z.js"
  ]);

  await assert.rejects(
    () => fetchFrontendSources(urls, {
      get: async () => ({ ok: () => false, status: () => 404 })
    }),
    /source fetch failed/
  );
  await assert.rejects(
    () => fetchFrontendSources([urls[0]], {
      get: async () => ({ ok: () => true, status: () => 200, body: async () => Buffer.alloc(0) })
    }),
    /source is empty/
  );
  const records = await fetchFrontendSources([urls[0]], {
    get: async () => ({
      ok: () => true,
      status: () => 200,
      body: async () => Buffer.from("export const value = 1;\n", "utf8")
    })
  });
  assert.deepEqual(
    { byteLength: records[0].byteLength, sha256: records[0].sha256 },
    {
      byteLength: 24,
      sha256: "5d8f65d2774e206bc9f7a7a4ad39ca2dc563b5c31e46ab57ef4874961237ce29"
    }
  );
  assert.equal(Object.hasOwn(records[0], "buildHash"), false);
});

test("business response capture scans bounded headers and finite body without retaining raw text", async () => {
  const capture = await capturePublicBusinessResponse(apiResponse({
    body: '{"message":"MIMO raw_provider_payload"}',
    headers: {
      "content-type": "application/json",
      "x-provider-debug": "Qiji"
    }
  }));
  assert.equal(capture.safe.bodyCapture, "FINITE_BODY_SCANNED");
  assert.match(capture.safe.headersSha256, /^[0-9a-f]{64}$/);
  assert.match(capture.safe.bodySha256, /^[0-9a-f]{64}$/);
  assert.equal(Object.values(capture.safe).some((value) => String(value).includes("MIMO")), false);
  assert.deepEqual(
    new Set(capture.findings.map((finding) => finding.code)),
    new Set(["PROVIDER_QIJI", "PROVIDER_MIMO", "RAW_PROVIDER_PAYLOAD"])
  );
  await assert.rejects(
    () => capturePublicBusinessResponse(apiResponse({
      headers: {
        "content-type": "application/json",
        "content-length": String(MAX_PUBLIC_RESPONSE_BODY_BYTES + 1)
      }
    })),
    /body exceeds/
  );
});

test("ledger drain turns an asynchronously found public response leak into failure", async () => {
  const page = new EventEmitter();
  const exactSentinel = "random-vfas-vs01-secret-sentinel-456";
  const ledger = new BrowserEvidenceLedger(page, {
    apiBaseUrl: "http://127.0.0.1:8000/api",
    secretSentinel: exactSentinel
  });
  page.emit("response", apiResponse({
    body: JSON.stringify({ debug: exactSentinel }),
    url: "http://127.0.0.1:4173/public-metadata"
  }));
  await assert.rejects(
    () => ledger.drainAndAssertPublicEvidenceClean(),
    /publicLeaks=1/
  );
  assert.equal(ledger.responses.length, 0, "non-business public fetch must not become binding evidence");
  assert.equal(ledger.publicResponses[0].bodyCapture, "FINITE_BODY_SCANNED");
  assert.match(ledger.publicResponses[0].bodySha256, /^[0-9a-f]{64}$/);
  assert.equal(JSON.stringify(ledger.publicResponses).includes(exactSentinel), false);
});

test("ledger scans request headers and bodies for the exact sentinel without retaining it", async () => {
  const page = new EventEmitter();
  const exactSentinel = "random-vfas-vs01-secret-sentinel-789";
  const ledger = new BrowserEvidenceLedger(page, {
    apiBaseUrl: "http://127.0.0.1:8000/api",
    secretSentinel: exactSentinel
  });
  page.emit("request", browserRequest({
    headers: { "content-type": "application/json", "x-debug-value": exactSentinel },
    body: JSON.stringify({ accidental_debug_value: exactSentinel })
  }));
  await assert.rejects(() => ledger.drainAndAssertPublicEvidenceClean(), /publicLeaks=2/);
  assert.equal(ledger.requests.length, 1);
  assert.equal(ledger.requests[0].bodyBytes > 0, true);
  assert.match(ledger.requests[0].headersSha256, /^[0-9a-f]{64}$/);
  assert.match(ledger.requests[0].bodySha256, /^[0-9a-f]{64}$/);
  assert.equal(JSON.stringify(ledger.requests).includes(exactSentinel), false);

  const oversizedPage = new EventEmitter();
  const bounded = new BrowserEvidenceLedger(oversizedPage, {
    apiBaseUrl: "http://127.0.0.1:8000/api",
    secretSentinel: exactSentinel
  });
  oversizedPage.emit("request", browserRequest({ body: "x".repeat(MAX_PUBLIC_REQUEST_BODY_BYTES + 1) }));
  await assert.rejects(() => bounded.drainAndAssertPublicEvidenceClean(), /capture failed/);
});

test("ledger rejects silent business request failures unless an exact expected failure is allowlisted", async () => {
  const page = new EventEmitter();
  const ledger = new BrowserEvidenceLedger(page, { apiBaseUrl: "http://127.0.0.1:8000/api" });
  const request = browserRequest({
    method: "GET",
    url: "http://127.0.0.1:8000/api/research-runs/RUN-A/events"
  });
  page.emit("requestfailed", request);
  await assert.rejects(() => ledger.drainAndAssertPublicEvidenceClean(), /request=1/);
  await assert.doesNotReject(() => ledger.drainAndAssertPublicEvidenceClean({
    allowedRequestFailures: [{
      method: "GET",
      pathname: "/api/research-runs/RUN-A/events",
      kinds: ["EXPECTED_NAVIGATION_ABORT"]
    }]
  }));
  await assert.rejects(() => ledger.drainAndAssertPublicEvidenceClean({
    allowedRequestFailures: [{
      method: "GET",
      pathname: "/api/research-runs/RUN-B/events",
      kinds: ["EXPECTED_NAVIGATION_ABORT"]
    }]
  }), /request=1/);
});
