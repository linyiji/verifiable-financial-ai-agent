import assert from "node:assert/strict";
import { createServer } from "vite";
const server = await createServer({ server: { middlewareMode: true }, appType: "custom" });
try {
  const { HttpFrontendDataSource } = await server.ssrLoadModule("/src/data/HttpFrontendDataSource.ts");
  const requests = [];
  const source = new HttpFrontendDataSource({ fetch: async (url, init) => {
    requests.push({ url, init });
    throw new TypeError("mock transport stop");
  } });
  for (const run of ["RUN-A", "RUN-A", "RUN-B"]) {
    await assert.rejects(source.materializeResearchMemory("OBJ-A", run));
  }
  assert.equal(requests.length, 3);
  assert.equal(requests[0].init.method, "POST");
  assert.equal(requests[0].url, "/api/objects/OBJ-A/memory/materialize");
  assert.deepEqual(JSON.parse(requests[0].init.body), { source_run_id: "RUN-A" });
  const keys = requests.map(r => r.init.headers.get("Idempotency-Key"));
  assert.ok(keys[0]);
  assert.equal(keys[0], keys[1]);
  assert.notEqual(keys[0], keys[2]);
  console.log("Memory writeback request checks: 7/7 PASS");
} finally { await server.close(); }
