import assert from "node:assert/strict";
import { decodeRecoverySummaryV1 } from "../src/runtime/recoveryV1.ts";

const raw = {
  version: "recovery-summary/v1", run_id: "R", intent_id: "I", operation_id: "O",
  contract_hash: "sha256:" + "a".repeat(64), status: "FAILED", original_failure: "READ_TIMEOUT",
  attempt: 1, scope: ["R:T"], reusable_output_refs: [], physical_calls_used: 2,
  physical_calls_limit: 4, deadline: 500, recoverable: false,
  denial_reason: "ACTIONS_NOT_ACCEPTED", accepted_actions: [], execution_started: false
};
assert.equal(decodeRecoverySummaryV1(raw, "R").original_failure, "READ_TIMEOUT");
assert.throws(() => decodeRecoverySummaryV1(raw, "OTHER"));
assert.throws(() => decodeRecoverySummaryV1({ ...raw, status: "FABRICATED_SUCCESS" }, "R"));
assert.throws(() => decodeRecoverySummaryV1({ ...raw, accepted_actions: ["NEW_RUN"] }, "R"));
assert.throws(() => decodeRecoverySummaryV1({ ...raw, accepted_actions: ["AUTHORIZE_FAILED_OPERATION"] }, "R"));
assert.throws(() => decodeRecoverySummaryV1({ ...raw, attempt: -1 }, "R"));
assert.throws(() => decodeRecoverySummaryV1({ ...raw, deadline: Number.NaN }, "R"));
assert.equal(decodeRecoverySummaryV1({ ...raw, recoverable: true, denial_reason: null,
  accepted_actions: ["AUTHORIZE_FAILED_OPERATION"] }, "R").accepted_actions.length, 1);
console.log("Recovery V1 DTO: 8 assertions PASS; no production actions mounted.");
