import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { decodeRecoveryEvidence } from "../src/types/recovery.ts";

const run = "RUN-test", object = "OBJ-test";
const scope = { run_id: run, object_id: object, task_id: run + ":peers", scheme_id: "SCHEME-test", task_profile: "peer_analysis" };
const row = { record_id: "REC-00000000-0000-0000-0000-000000000001", scope, kind: "ATTEMPT_COMPLETED", route: "mimo-direct", provider: "mimo", model: "mimo-v2.5", attempt_number: 1, capability_check: false, action: null, outcome: "FAIL", failure_class: "READ_TIMEOUT", reason_code: "OBSERVED", latency_ms: 60000 };
let checks = 0;
function check(fn) { fn(); checks++; }
check(() => assert.equal(decodeRecoveryEvidence([row], run, object)[0].failure, "READ_TIMEOUT"));
check(() => assert.deepEqual(decodeRecoveryEvidence([], run, object), []));
for (const change of [
  { scope: { ...scope, run_id: "RUN-other" } },
  { scope: { ...scope, object_id: "OBJ-other" } },
  { scope: { ...scope, task_id: "RUN-other:peers" } },
  { route: "arbitrary-provider" }, { model: "gpt-5.6-sol" }, { provider: "teamorouter" },
  { failure_class: "private exception text" }, { action: "ARBITRARY_ACTION" },
  { kind: "raw_prompt" }, { outcome: "invented_success" }, { latency_ms: -1 },
  { attempt_number: 10 }, { capability_check: "true" }
]) check(() => assert.throws(() => decodeRecoveryEvidence([{ ...row, ...change }], run, object)));
check(() => assert.throws(() => decodeRecoveryEvidence([row, row], run, object)));
check(() => assert.throws(() => decodeRecoveryEvidence([row, { ...row, record_id: "REC-00000000-0000-0000-0000-000000000002", scope: { ...scope, scheme_id: "SCHEME-other" } }], run, object)));
const decision = { ...row, record_id: "REC-00000000-0000-0000-0000-000000000002", kind: "DECISION", route: "teamorouter-sol", provider: null, model: null, action: "SWITCH_PROVIDER", outcome: "ALLOW", failure_class: null, attempt_number: 0, latency_ms: null, decision: { scope, action: "SWITCH_PROVIDER", target_route: "teamorouter-sol" } };
check(() => assert.equal(decodeRecoveryEvidence([decision], run, object)[0].action, "SWITCH_PROVIDER"));
check(() => assert.throws(() => decodeRecoveryEvidence([{ ...decision, decision: { ...decision.decision, scope: { ...scope, object_id: "OBJ-other" } } }], run, object)));
const safe = decodeRecoveryEvidence([{ ...row, prompt: "SENTINEL_SECRET", raw_response: "SENTINEL_SECRET" }, decision], run, object);
check(() => assert.ok(!JSON.stringify(safe).includes("SENTINEL_SECRET")));
const server = await createServer({ server: { middlewareMode: true }, appType: "custom" });
try {
  const { RecoveryTimeline } = await server.ssrLoadModule("/src/components/results/RuntimeRecoveryEvidence.tsx");
  const html = renderToStaticMarkup(createElement(RecoveryTimeline, { rows: safe }));
  check(() => assert.ok(html.includes("同 Run 运行恢复") && html.includes("READ_TIMEOUT")));
  check(() => assert.ok(html.includes("切换供应商") && html.includes("Policy Gate: ") && html.includes("ALLOW")));
  check(() => assert.ok(html.includes(run + ":peers") && !html.includes("SENTINEL_SECRET")));
  const empty = renderToStaticMarkup(createElement(RecoveryTimeline, { rows: [] }));
  check(() => assert.ok(empty.includes("未记录恢复决策") && !empty.includes("恢复成功")));
} finally { await server.close(); }
console.log(`Recovery evidence checks: ${checks}/${checks} PASS`);
