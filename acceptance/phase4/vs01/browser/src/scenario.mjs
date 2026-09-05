import { readFile } from "node:fs/promises";
import { isAbsolute } from "node:path";
import { assertNoDemoFallback, assertSafePublicJson, ContractViolation } from "./contracts.mjs";

export const SCENARIO_SCHEMA_VERSION = "phase4-vs01-frontend-scenario/v1";

function requiredString(value, path) {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new ContractViolation("SCENARIO_INVALID", path, "expected non-empty string");
  }
  return value;
}

function requiredObject(value, path) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new ContractViolation("SCENARIO_INVALID", path, "expected object");
  }
  return value;
}

function requiredUrl(value, path) {
  const raw = requiredString(value, path);
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new ContractViolation("SCENARIO_INVALID", path, "expected absolute URL");
  }
  if (!new Set(["http:", "https:"]).has(parsed.protocol)) {
    throw new ContractViolation("SCENARIO_INVALID", path, "only HTTP(S) is accepted");
  }
  parsed.username = "";
  parsed.password = "";
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

export function decodeBrowserScenario(value, frontendUrl) {
  const input = requiredObject(value, "scenario");
  if (input.schemaVersion !== SCENARIO_SCHEMA_VERSION) {
    throw new ContractViolation("SCENARIO_INVALID", "scenario.schemaVersion", `expected ${SCENARIO_SCHEMA_VERSION}`);
  }
  assertSafePublicJson(input, "scenario");
  assertNoDemoFallback(JSON.stringify(input), "scenario");

  const object = requiredObject(input.object, "scenario.object");
  const foreign = requiredObject(input.foreign, "scenario.foreign");
  const decoded = {
    schemaVersion: SCENARIO_SCHEMA_VERSION,
    object: {
      objectId: requiredString(object.objectId, "scenario.object.objectId"),
      symbol: requiredString(object.symbol, "scenario.object.symbol"),
      companyName: requiredString(object.companyName, "scenario.object.companyName")
    },
    goalText: requiredString(input.goalText, "scenario.goalText"),
    asOf: requiredString(input.asOf, "scenario.asOf"),
    missingRunId: requiredString(input.missingRunId, "scenario.missingRunId"),
    missingErrorCode: input.missingErrorCode === undefined
      ? "NOT_FOUND"
      : requiredString(input.missingErrorCode, "scenario.missingErrorCode"),
    foreign: {
      objectId: requiredString(foreign.objectId, "scenario.foreign.objectId"),
      runId: requiredString(foreign.runId, "scenario.foreign.runId"),
      taskId: requiredString(foreign.taskId, "scenario.foreign.taskId"),
      sentinels: Array.isArray(foreign.sentinels)
        ? foreign.sentinels.map((item, index) => requiredString(item, `scenario.foreign.sentinels[${index}]`))
        : []
    },
    backendUnavailableFrontendUrl: requiredUrl(
      input.backendUnavailableFrontendUrl,
      "scenario.backendUnavailableFrontendUrl"
    )
  };

  if (!/^\d{4}-\d{2}-\d{2}$/.test(decoded.asOf)) {
    throw new ContractViolation("SCENARIO_INVALID", "scenario.asOf", "expected YYYY-MM-DD");
  }
  if (decoded.foreign.objectId === decoded.object.objectId) {
    throw new ContractViolation("SCENARIO_INVALID", "scenario.foreign.objectId", "foreign Object must differ");
  }
  if (decoded.foreign.runId === decoded.missingRunId) {
    throw new ContractViolation("SCENARIO_INVALID", "scenario.foreign.runId", "foreign Run must not be missing Run");
  }
  if (frontendUrl && new URL(decoded.backendUnavailableFrontendUrl).origin === new URL(frontendUrl).origin) {
    throw new ContractViolation(
      "SCENARIO_INVALID",
      "scenario.backendUnavailableFrontendUrl",
      "unavailable-backend frontend must use a separately launched origin"
    );
  }
  return Object.freeze({ ...decoded, object: Object.freeze(decoded.object), foreign: Object.freeze(decoded.foreign) });
}

export async function loadBrowserScenario(env = process.env) {
  const path = requiredString(env.VS01_BROWSER_SCENARIO_FILE, "env.VS01_BROWSER_SCENARIO_FILE");
  if (!isAbsolute(path)) {
    throw new ContractViolation("SCENARIO_INVALID", "env.VS01_BROWSER_SCENARIO_FILE", "path must be absolute");
  }
  const text = await readFile(path, "utf8");
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new ContractViolation("SCENARIO_INVALID", path, "file is not valid JSON");
  }
  return decodeBrowserScenario(parsed, env.VS01_FRONTEND_URL ?? "http://127.0.0.1:4173");
}
