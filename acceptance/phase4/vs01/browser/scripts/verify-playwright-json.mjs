import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const expected = new Set([
  ...Array.from({ length: 10 }, (_, index) => `VS01-FE-${String(index + 3).padStart(3, "0")}`),
  "VS01-DYN-001",
  "VS01-REC-008",
  "VS01-REC-009",
  "VS01-ID-003"
]);
const outputRoot = process.env.VS01_BROWSER_ARTIFACT_DIR ?? "artifacts";
const reportPath = resolve(outputRoot, "playwright-result.json");
const report = JSON.parse(await readFile(reportPath, "utf8"));
const observed = new Map();

function visit(value) {
  if (Array.isArray(value)) {
    for (const item of value) visit(item);
    return;
  }
  if (value === null || typeof value !== "object") return;
  if (Array.isArray(value.annotations)) {
    for (const annotation of value.annotations) {
      if (annotation?.type !== "vs01-control") continue;
      observed.set(annotation.description, (observed.get(annotation.description) ?? 0) + 1);
    }
  }
  for (const item of Object.values(value)) visit(item);
}

visit(report);
const missing = [...expected].filter((controlId) => observed.get(controlId) !== 1);
const unexpected = [...observed].filter(([controlId, count]) => !expected.has(controlId) || count !== 1);
if (missing.length || unexpected.length) {
  throw new Error(
    `Playwright control annotations invalid: missing=${missing.join(",") || "none"}; unexpected=${JSON.stringify(unexpected)}`
  );
}
process.stdout.write(`Playwright JSON controls verified: ${[...expected].join(", ")}\n`);
