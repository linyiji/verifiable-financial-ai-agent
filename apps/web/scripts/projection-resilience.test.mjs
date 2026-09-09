import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  Phase4ApiError,
  Phase4ProtocolError,
  Phase4TransportError
} from "../src/api/client.ts";
import {
  MAX_PROJECTION_BACKOFF_ATTEMPT_V1,
  nextProjectionReadBackoff,
  projectionReadFailureDisposition
} from "../src/runtime/projectionRefreshPolicy.ts";

const request = { method: "GET", path: "/api/research-runs/RUN-A/projection" };
const retryable = new Phase4ApiError(503, {
  schemaVersion: "phase4-error/v1",
  error: {
    code: "TRANSIENT_BACKEND_ERROR", message: "bounded", retryable: true,
    recovery: "RETRY", requestId: null, resource: null, details: {}
  }
}, request);
const nonretryable = new Phase4ApiError(409, {
  schemaVersion: "phase4-error/v1",
  error: {
    code: "SCHEMA_INCOMPATIBLE", message: "bounded", retryable: false,
    recovery: "NONE", requestId: null, resource: null, details: {}
  }
}, request);

assert.equal(
  projectionReadFailureDisposition(new Phase4TransportError("NETWORK", request), true),
  "RETAIN_STALE"
);
assert.equal(projectionReadFailureDisposition(retryable, true), "RETAIN_STALE");
assert.equal(projectionReadFailureDisposition(retryable, false), "FULL_PAGE_UNAVAILABLE");
assert.equal(projectionReadFailureDisposition(nonretryable, true), "FULL_PAGE_UNAVAILABLE");
assert.equal(
  projectionReadFailureDisposition(new Phase4ProtocolError("invalid", request), true),
  "FULL_PAGE_UNAVAILABLE"
);

assert.deepEqual(nextProjectionReadBackoff(0, 0), {
  attempt: 1, delayMilliseconds: 1_000, retryAt: "1970-01-01T00:00:01.000Z"
});
assert.equal(nextProjectionReadBackoff(10, 0).delayMilliseconds, 30_000);
assert.equal(
  nextProjectionReadBackoff(MAX_PROJECTION_BACKOFF_ATTEMPT_V1, 0).attempt,
  MAX_PROJECTION_BACKOFF_ATTEMPT_V1
);

const application = await readFile(new URL("../src/Phase4Application.tsx", import.meta.url), "utf8");
assert.match(application, /setSelectedRunProjection\(selectRunProjection\(retained\)\)/u);
assert.match(application, /lastSequence: retained\.committedSequence/u);
assert.match(application, /kind: "BACKOFF"/u);
assert.match(application, /window\.setTimeout/u);
assert.match(application, /initialSequence: value\.projectionSequence/u);

console.log("Projection last-known-good resilience PASS (13 checks)");
