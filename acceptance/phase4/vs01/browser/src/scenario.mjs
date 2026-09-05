import { readFile } from "node:fs/promises";
import { isAbsolute } from "node:path";
import {
  ADVERSARIAL_CANONICAL_DECIMAL_PROPERTY,
  assertNoDemoFallback,
  assertSafePublicJson,
  ContractViolation
} from "./contracts.mjs";

export const SCENARIO_SCHEMA_VERSION = "phase4-vs01-frontend-scenario/v1";
export const SECRET_SENTINEL_ENV = "VFAS_VS01_SECRET_SENTINEL";

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

function exactFields(value, fields, path) {
  const missing = fields.filter((field) => !Object.hasOwn(value, field));
  const extra = Object.keys(value).filter((field) => !fields.includes(field));
  if (missing.length || extra.length) {
    throw new ContractViolation(
      "SCENARIO_INVALID",
      path,
      `exact fields required; missing=${missing.join(",") || "none"}; extra=${extra.join(",") || "none"}`
    );
  }
}

export function decodeSecretSentinel(value) {
  const sentinel = requiredString(value, `env.${SECRET_SENTINEL_ENV}`);
  if (sentinel.trim() !== sentinel) {
    throw new ContractViolation("SCENARIO_INVALID", `env.${SECRET_SENTINEL_ENV}`, "sentinel must be canonical");
  }
  return sentinel;
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
  if (parsed.username || parsed.password) {
    throw new ContractViolation("SCENARIO_INVALID", path, "credentials are forbidden in public URLs");
  }
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

function requiredApiBaseUrl(value, path) {
  const raw = requiredString(value, path);
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new ContractViolation("SCENARIO_INVALID", path, "expected absolute API base URL");
  }
  if (!new Set(["http:", "https:"]).has(parsed.protocol) || parsed.username || parsed.password) {
    throw new ContractViolation("SCENARIO_INVALID", path, "expected credential-free HTTP(S) API base URL");
  }
  if (parsed.search || parsed.hash) {
    throw new ContractViolation("SCENARIO_INVALID", path, "API base URL query and fragment are forbidden");
  }
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
  const alternate = requiredObject(input.alternate, "scenario.alternate");
  const foreign = requiredObject(input.foreign, "scenario.foreign");
  const financial = requiredObject(input.financial, "scenario.financial");
  exactFields(financial, ["objectId", "runId", "metricId", "adversarialProperty"], "scenario.financial");
  const decoded = {
    schemaVersion: SCENARIO_SCHEMA_VERSION,
    frontendUrl: requiredUrl(frontendUrl ?? "http://127.0.0.1:4173", "env.VS01_FRONTEND_URL"),
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
    alternate: {
      objectId: requiredString(alternate.objectId, "scenario.alternate.objectId"),
      runId: requiredString(alternate.runId, "scenario.alternate.runId"),
      taskId: requiredString(alternate.taskId, "scenario.alternate.taskId")
    },
    foreign: {
      objectId: requiredString(foreign.objectId, "scenario.foreign.objectId"),
      runId: requiredString(foreign.runId, "scenario.foreign.runId"),
      taskId: requiredString(foreign.taskId, "scenario.foreign.taskId"),
      sentinels: Array.isArray(foreign.sentinels)
        ? foreign.sentinels.map((item, index) => requiredString(item, `scenario.foreign.sentinels[${index}]`))
        : []
    },
    financial: {
      objectId: requiredString(financial.objectId, "scenario.financial.objectId"),
      runId: requiredString(financial.runId, "scenario.financial.runId"),
      metricId: requiredString(financial.metricId, "scenario.financial.metricId"),
      adversarialProperty: requiredString(
        financial.adversarialProperty,
        "scenario.financial.adversarialProperty"
      )
    },
    backendUnavailableFrontendUrl: requiredUrl(
      input.backendUnavailableFrontendUrl,
      "scenario.backendUnavailableFrontendUrl"
    ),
    primaryApiBaseUrl: requiredApiBaseUrl(
      input.primaryApiBaseUrl,
      "scenario.primaryApiBaseUrl"
    ),
    unavailableApiBaseUrl: requiredApiBaseUrl(
      input.unavailableApiBaseUrl,
      "scenario.unavailableApiBaseUrl"
    )
  };

  if (!/^\d{4}-\d{2}-\d{2}$/.test(decoded.asOf)) {
    throw new ContractViolation("SCENARIO_INVALID", "scenario.asOf", "expected YYYY-MM-DD");
  }
  if (decoded.foreign.objectId === decoded.object.objectId) {
    throw new ContractViolation("SCENARIO_INVALID", "scenario.foreign.objectId", "foreign Object must differ");
  }
  if (decoded.alternate.objectId !== decoded.object.objectId) {
    throw new ContractViolation(
      "SCENARIO_INVALID",
      "scenario.alternate.objectId",
      "alternate Run must belong to the selected Object"
    );
  }
  if (
    decoded.alternate.runId === decoded.foreign.runId
    || decoded.alternate.runId === decoded.missingRunId
  ) {
    throw new ContractViolation("SCENARIO_INVALID", "scenario.alternate.runId", "alternate Run must be distinct");
  }
  if (decoded.foreign.runId === decoded.missingRunId) {
    throw new ContractViolation("SCENARIO_INVALID", "scenario.foreign.runId", "foreign Run must not be missing Run");
  }
  if (decoded.financial.adversarialProperty !== ADVERSARIAL_CANONICAL_DECIMAL_PROPERTY) {
    throw new ContractViolation(
      "SCENARIO_INVALID",
      "scenario.financial.adversarialProperty",
      `expected ${ADVERSARIAL_CANONICAL_DECIMAL_PROPERTY}`
    );
  }
  if (
    decoded.financial.runId === decoded.missingRunId
    || decoded.financial.runId === decoded.alternate.runId
    || decoded.financial.runId === decoded.foreign.runId
  ) {
    throw new ContractViolation(
      "SCENARIO_INVALID",
      "scenario.financial.runId",
      "released financial evidence Run must be distinct from missing, live alternate, and foreign quarantine Runs"
    );
  }
  if (frontendUrl && new URL(decoded.backendUnavailableFrontendUrl).origin === new URL(frontendUrl).origin) {
    throw new ContractViolation(
      "SCENARIO_INVALID",
      "scenario.backendUnavailableFrontendUrl",
      "unavailable-backend frontend must use a separately launched origin"
    );
  }
  if (decoded.primaryApiBaseUrl === decoded.unavailableApiBaseUrl) {
    throw new ContractViolation(
      "SCENARIO_INVALID",
      "scenario.unavailableApiBaseUrl",
      "primary and unavailable public API bases must differ"
    );
  }
  return Object.freeze({
    ...decoded,
    object: Object.freeze(decoded.object),
    alternate: Object.freeze(decoded.alternate),
    foreign: Object.freeze({ ...decoded.foreign, sentinels: Object.freeze(decoded.foreign.sentinels) }),
    financial: Object.freeze(decoded.financial)
  });
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
  const decoded = decodeBrowserScenario(parsed, env.VS01_FRONTEND_URL ?? "http://127.0.0.1:4173");
  return Object.freeze({
    ...decoded,
    secretSentinel: decodeSecretSentinel(env[SECRET_SENTINEL_ENV])
  });
}
