import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const renderer = await createServer({ server: { middlewareMode: true }, appType: "custom" });
let List, Detail, decodeResearchObjectDetail;
try {
  ({ ResearchObjectsPage: List } = await renderer.ssrLoadModule("/src/pages/ResearchObjectsPage.tsx"));
  ({ ResearchObjectDetailPage: Detail } = await renderer.ssrLoadModule("/src/pages/ResearchObjectDetailPage.tsx"));
  ({ decodeResearchObjectDetail } = await renderer.ssrLoadModule("/src/types/domain.ts"));
} finally { await renderer.close(); }

const wire = {
  object: { object_id: "OBJ-TEST", symbol: "TEST", company_name: "Test Company", object_type: "public_company", exchange: "TEST", sector: null, currency: "USD", identity_version: 1 },
  latest_released_run_id: null,
  released_result_availability: { status: "NOT_RELEASED", reason_code: "NO_RELEASED_RUN", retryable: false },
  run_count: 0, last_activity: null,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z"
};
const render = (input) => {
  const detail = decodeResearchObjectDetail(input, "OBJ-TEST");
  return [renderToStaticMarkup(createElement(List, { objects: [detail], onOpen() {}, onCreate() {} })),
    renderToStaticMarkup(createElement(Detail, { detail, onBeginResearch() {}, onOpenRun() {} }))];
};
let checks = 0;
const check = (value, message) => { checks++; assert.ok(value, message); };
for (const html of render(wire)) check(html.includes("尚未发布") && html.includes("尚无 Run 活动"), "zero Runs permits true absence on both surfaces");
for (const html of render({ ...wire, run_count: 2 })) check(html.includes("尚未发布") && html.includes("最近活动时间不可用") && !html.includes("尚无 Run 活动"), "unreleased Runs distinguish missing activity from no activity");
const unknown = { ...wire, run_count: 2, released_result_availability: { status: "UNAVAILABLE", reason_code: "RELEASED_RUN_LATEST_UNAVAILABLE", retryable: false } };
for (const html of render(unknown)) check(html.includes("已有发布记录，最新发布时间不可用") && !html.includes("尚未发布") && !html.includes("尚无已发布"), "unknown latest does not deny released history on either surface");
const available = { ...wire, run_count: 1, latest_released_run_id: "RUN-TEST", released_result_availability: { status: "AVAILABLE", reason_code: null, retryable: false } };
for (const html of render(available)) check(html.includes("已有发布结果") && !html.includes("尚未发布"), "known release renders consistently");
assert.throws(() => decodeResearchObjectDetail({ ...unknown, run_count: 0 }, "OBJ-TEST"));checks++;
assert.throws(() => decodeResearchObjectDetail({ ...unknown, released_result_availability: { ...unknown.released_result_availability, reason_code: "UNREVIEWED_REASON" } }, "OBJ-TEST"));checks++;
assert.throws(() => decodeResearchObjectDetail(available, "OBJ-FOREIGN"));checks++;
console.log(`M7-R2 object summary rendered/decoder checks: ${checks}/11 PASS`);
