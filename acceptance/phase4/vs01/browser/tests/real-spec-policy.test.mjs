import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const specUrl = new URL("./vs01-frontend.real.spec.mjs", import.meta.url);

test("production-counting browser spec cannot install response mocks or direct business state", async () => {
  const source = await readFile(specUrl, "utf8");
  const forbidden = [
    /page\s*\.\s*route\s*\(/,
    /context\s*\.\s*route\s*\(/,
    /route\s*\.\s*fulfill\s*\(/,
    /setContent\s*\(/,
    /addInitScript\s*\(/,
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
});
