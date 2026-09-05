import { findPublicSurfaceLeaks, sha256Bytes, sha256Text } from "./contracts.mjs";

export const MAX_PUBLIC_RESPONSE_HEADER_BYTES = 64 * 1024;
export const MAX_PUBLIC_RESPONSE_BODY_BYTES = 1024 * 1024;
export const MAX_PUBLIC_REQUEST_HEADER_BYTES = 64 * 1024;
export const MAX_PUBLIC_REQUEST_BODY_BYTES = 1024 * 1024;
export const MAX_FRONTEND_SOURCE_BYTES = 8 * 1024 * 1024;

export function pathnameOf(url) {
  return new URL(url).pathname;
}

function redactExactSentinels(value, exactSentinels = []) {
  let safe = String(value);
  for (const sentinel of exactSentinels) {
    if (typeof sentinel === "string" && sentinel.length) {
      safe = safe.split(sentinel).join("[REDACTED_SECRET_SENTINEL]");
    }
  }
  return safe;
}

export function isBusinessApiPath(url) {
  return /\/(?:objects|research-runs)(?:\/|$)/.test(pathnameOf(url));
}

export function isWithinApiBase(url, apiBaseUrl) {
  const candidate = new URL(url);
  const base = new URL(apiBaseUrl);
  const prefix = base.pathname.replace(/\/$/, "") || "/";
  return candidate.origin === base.origin && (
    prefix === "/" || candidate.pathname === prefix || candidate.pathname.startsWith(`${prefix}/`)
  );
}

function isBusinessApiRequest(request, apiBaseUrl) {
  const resourceType = request.resourceType?.() ?? "";
  return isBusinessApiPath(request.url()) || (
    apiBaseUrl !== null
    && new Set(["fetch", "xhr"]).has(resourceType)
    && isWithinApiBase(request.url(), apiBaseUrl)
  );
}

export function apiRouteUrl(apiBaseUrl, relativePath) {
  const base = new URL(apiBaseUrl);
  const basePath = base.pathname.replace(/\/$/, "");
  const suffix = String(relativePath).replace(/^\//, "");
  base.pathname = `${basePath}/${suffix}`.replace(/\/+/g, "/");
  base.search = "";
  base.hash = "";
  return base.toString();
}

export function apiRoutePathname(apiBaseUrl, relativePath) {
  return pathnameOf(apiRouteUrl(apiBaseUrl, relativePath));
}

export function isExactApiRoute(url, apiBaseUrl, relativePath) {
  return new URL(url).toString() === apiRouteUrl(apiBaseUrl, relativePath);
}

export async function responseJson(response) {
  const contentType = (await response.headerValue("content-type")) ?? "";
  if (!/^application\/json(?:;|$)/i.test(contentType)) {
    throw new Error(`Expected JSON response from ${pathnameOf(response.url())}; received ${contentType || "no Content-Type"}`);
  }
  return response.json();
}

export function postDataJson(request) {
  const text = request.postData();
  if (!text) throw new Error(`Expected JSON request body for ${request.method()} ${pathnameOf(request.url())}`);
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Invalid JSON request body for ${request.method()} ${pathnameOf(request.url())}`);
  }
}

export function safeRequestRecord(request, ordinal = null, exactSentinels = []) {
  const headers = normalizedHeaders(request.headers());
  const headerText = JSON.stringify(headers);
  const body = request.postDataBuffer?.() ?? null;
  const idempotencyKey = headers["idempotency-key"];
  const lastEventId = headers["last-event-id"];
  const parsed = new URL(request.url());
  return Object.freeze({
    ordinal,
    method: request.method(),
    origin: parsed.origin,
    pathname: redactExactSentinels(parsed.pathname, exactSentinels),
    contractVersion: headers["x-phase4-contract-version"] ?? null,
    accept: headers.accept ? redactExactSentinels(headers.accept, exactSentinels) : null,
    lastEventId: lastEventId ? redactExactSentinels(lastEventId, exactSentinels) : null,
    headerBytes: Buffer.byteLength(headerText, "utf8"),
    headersSha256: sha256Text(headerText),
    bodyBytes: body?.byteLength ?? 0,
    bodySha256: body ? sha256Bytes(body) : null,
    idempotencyKeyPresent: typeof idempotencyKey === "string" && idempotencyKey.length > 0,
    idempotencyKeySha256: idempotencyKey ? sha256Text(idempotencyKey) : null
  });
}

function scanPublicRequest(request, exactSentinels) {
  const path = redactExactSentinels(pathnameOf(request.url()), exactSentinels);
  const headers = normalizedHeaders(request.headers());
  const headerText = JSON.stringify(headers);
  const headerBytes = Buffer.byteLength(headerText, "utf8");
  if (headerBytes > MAX_PUBLIC_REQUEST_HEADER_BYTES) {
    throw new Error(`Public request headers exceed ${MAX_PUBLIC_REQUEST_HEADER_BYTES} bytes at ${path}`);
  }
  const findings = findPublicSurfaceLeaks(
    [{ path: `browser.request-headers:${path}`, source: headerText }],
    exactSentinels
  );
  const body = request.postDataBuffer?.() ?? null;
  if (body && body.byteLength > MAX_PUBLIC_REQUEST_BODY_BYTES) {
    throw new Error(`Public request body exceeds ${MAX_PUBLIC_REQUEST_BODY_BYTES} bytes at ${path}`);
  }
  if (body) {
    findings.push(...findPublicSurfaceLeaks(
      [{ path: `browser.request-body:${path}`, source: body.toString("utf8") }],
      exactSentinels
    ));
  }
  return findings;
}

export function assertApiBaseRequests(apiBaseUrl, apiRequests) {
  if (!apiRequests.length) throw new Error("API binding proof observed no business API request");
  const binding = new URL(apiBaseUrl);
  const apiPathPrefix = binding.pathname.replace(/\/$/, "") || "/";
  for (const request of apiRequests) {
    const pathMatches = apiPathPrefix === "/"
      || request.pathname === apiPathPrefix
      || request.pathname.startsWith(`${apiPathPrefix}/`);
    if (request.origin !== binding.origin || !pathMatches) {
      throw new Error(`Business API request escaped the reviewed API base: ${request.method} ${request.origin}${request.pathname}`);
    }
  }
}

function normalizedHeaders(headers) {
  return Object.fromEntries(
    Object.entries(headers)
      .map(([name, value]) => [name.toLowerCase(), String(value)])
      .sort(([left], [right]) => left.localeCompare(right))
  );
}

export async function capturePublicBusinessResponse(response, suppliedHeaders = null, exactSentinels = []) {
  const path = redactExactSentinels(pathnameOf(response.url()), exactSentinels);
  const headers = normalizedHeaders(suppliedHeaders ?? await response.allHeaders());
  const headerText = JSON.stringify(headers);
  const headerBytes = Buffer.byteLength(headerText, "utf8");
  if (headerBytes > MAX_PUBLIC_RESPONSE_HEADER_BYTES) {
    throw new Error(`Public response headers exceed ${MAX_PUBLIC_RESPONSE_HEADER_BYTES} bytes at ${path}`);
  }
  const findings = findPublicSurfaceLeaks(
    [{ path: `browser.response-headers:${path}`, source: headerText }],
    exactSentinels
  );
  const contentType = headers["content-type"] ?? "";
  const safe = {
    headerBytes,
    headersSha256: sha256Text(headerText),
    bodyBytes: null,
    bodySha256: null,
    bodyCapture: "ACTIVE_EVENT_STREAM_NOT_BUFFERED"
  };
  if (/^text\/event-stream(?:;|$)/i.test(contentType)) return { safe, findings };

  const contentLength = headers["content-length"];
  if (contentLength !== undefined && /^\d+$/.test(contentLength)) {
    if (Number(contentLength) > MAX_PUBLIC_RESPONSE_BODY_BYTES) {
      throw new Error(`Public response body exceeds ${MAX_PUBLIC_RESPONSE_BODY_BYTES} bytes at ${path}`);
    }
  }
  const body = await response.body();
  if (body.byteLength > MAX_PUBLIC_RESPONSE_BODY_BYTES) {
    throw new Error(`Public response body exceeds ${MAX_PUBLIC_RESPONSE_BODY_BYTES} bytes at ${path}`);
  }
  findings.push(...findPublicSurfaceLeaks(
    [{ path: `browser.response-body:${path}`, source: body.toString("utf8") }],
    exactSentinels
  ));
  safe.bodyBytes = body.byteLength;
  safe.bodySha256 = sha256Bytes(body);
  safe.bodyCapture = "FINITE_BODY_SCANNED";
  return { safe, findings };
}

function consoleFailureKind(text) {
  if (/net::ERR_(?:INTERNET_DISCONNECTED|NETWORK_CHANGED)/.test(text)) {
    return "EXPECTED_BROWSER_OFFLINE";
  }
  if (/net::ERR_(?:CONNECTION_REFUSED|CONNECTION_RESET|CONNECTION_TIMED_OUT|NAME_NOT_RESOLVED)/.test(text)) {
    return "EXPECTED_BACKEND_UNAVAILABLE";
  }
  if (/net::ERR_ABORTED/.test(text)) {
    return "EXPECTED_NAVIGATION_ABORT";
  }
  return "UNEXPECTED";
}

function requestFailureMatches(failure, rule) {
  const prefix = rule.pathnamePrefix?.replace(/\/$/, "") || "/";
  return (rule.method === undefined || failure.method === rule.method)
    && (rule.origin === undefined || failure.origin === rule.origin)
    && (rule.pathname === undefined || failure.pathname === rule.pathname)
    && (rule.pathnamePrefix === undefined || (
      prefix === "/"
      || failure.pathname === prefix
      || failure.pathname.startsWith(`${prefix}/`)
    ))
    && (rule.kinds === undefined || rule.kinds.includes(failure.kind));
}

export class BrowserEvidenceLedger {
  constructor(page, { apiBaseUrl = null, secretSentinel = null } = {}) {
    this.apiBaseUrl = apiBaseUrl;
    this.exactSentinels = secretSentinel === null ? [] : [secretSentinel];
    this.allRequests = [];
    this.requests = [];
    this.responses = [];
    this.publicResponses = [];
    this.requestFailures = [];
    this.consoleFailures = [];
    this.pageFailures = [];
    this.publicSurfaceLeaks = [];
    this.responseCaptureFailures = [];
    this.pendingResponseCaptures = new Set();
    let ordinal = 0;

    page.on("request", (request) => {
      ordinal += 1;
      const protocol = new URL(request.url()).protocol;
      if (protocol !== "http:" && protocol !== "https:") return;
      this.publicSurfaceLeaks.push(...findPublicSurfaceLeaks(
        [{ path: "browser.request-url", source: request.url() }],
        this.exactSentinels
      ));
      let record;
      try {
        this.publicSurfaceLeaks.push(...scanPublicRequest(request, this.exactSentinels));
        record = safeRequestRecord(request, ordinal, this.exactSentinels);
      } catch (error) {
        this.responseCaptureFailures.push(Object.freeze({
          pathname: redactExactSentinels(pathnameOf(request.url()), this.exactSentinels),
          errorSha256: sha256Text(error instanceof Error ? error.message : String(error))
        }));
        return;
      }
      this.allRequests.push(record);
      if (isBusinessApiRequest(request, this.apiBaseUrl)) this.requests.push(record);
    });
    page.on("response", (response) => {
      const request = response.request();
      const business = isBusinessApiRequest(request, this.apiBaseUrl);
      let record = business
        ? {
          method: response.request().method(),
          origin: new URL(response.url()).origin,
          pathname: redactExactSentinels(pathnameOf(response.url()), this.exactSentinels),
          status: response.status(),
          headerBytes: null,
          headersSha256: null,
          bodyBytes: null,
          bodySha256: null,
          bodyCapture: "PENDING"
        }
        : null;
      if (record) this.responses.push(record);
      let pending;
      pending = (async () => {
        const headers = normalizedHeaders(await response.allHeaders());
        const contentType = headers["content-type"] ?? "";
        const resourceType = request.resourceType?.() ?? "";
        const inspect = business
          || new Set(["fetch", "xhr"]).has(resourceType)
          || /^(?:application\/[^;]*json|text\/event-stream)(?:;|$)/i.test(contentType)
          || /^application\/[^;]+\+json(?:;|$)/i.test(contentType);
        if (!inspect) return;
        if (!record) {
          record = {
            method: request.method(),
            origin: new URL(response.url()).origin,
            pathname: redactExactSentinels(pathnameOf(response.url()), this.exactSentinels),
            status: response.status(),
            headerBytes: null,
            headersSha256: null,
            bodyBytes: null,
            bodySha256: null,
            bodyCapture: "PENDING"
          };
        }
        this.publicResponses.push(record);
        const { safe, findings } = await capturePublicBusinessResponse(
          response,
          headers,
          this.exactSentinels
        );
        Object.assign(record, safe);
        this.publicSurfaceLeaks.push(...findings);
      })()
        .catch((error) => {
          if (record) record.bodyCapture = "CAPTURE_FAILED";
          this.responseCaptureFailures.push(Object.freeze({
            pathname: redactExactSentinels(pathnameOf(response.url()), this.exactSentinels),
            errorSha256: sha256Text(error instanceof Error ? error.message : String(error))
          }));
        })
        .finally(() => {
          if (record) Object.freeze(record);
          this.pendingResponseCaptures.delete(pending);
        });
      this.pendingResponseCaptures.add(pending);
    });
    page.on("requestfailed", (request) => {
      if (isBusinessApiRequest(request, this.apiBaseUrl)) {
        const failureText = request.failure()?.errorText ?? "REQUEST_FAILED";
        const findings = findPublicSurfaceLeaks(
          [{ path: "browser.requestFailure", source: failureText }],
          this.exactSentinels
        );
        this.publicSurfaceLeaks.push(...findings);
        this.requestFailures.push(Object.freeze({
          method: request.method(),
          origin: new URL(request.url()).origin,
          pathname: redactExactSentinels(pathnameOf(request.url()), this.exactSentinels),
          kind: consoleFailureKind(failureText),
          errorSha256: sha256Text(failureText),
          leakCodes: findings.map((finding) => finding.code)
        }));
      }
    });
    page.on("console", (message) => {
      if (message.type() === "error" || message.type() === "warning") {
        const consoleText = message.text();
        const findings = findPublicSurfaceLeaks(
          [{ path: "browser.console", source: consoleText }],
          this.exactSentinels
        );
        this.publicSurfaceLeaks.push(...findings);
        this.consoleFailures.push({
          type: message.type(),
          kind: consoleFailureKind(consoleText),
          textSha256: sha256Text(consoleText),
          leakCodes: findings.map((finding) => finding.code)
        });
      }
    });
    page.on("pageerror", (error) => {
      const findings = findPublicSurfaceLeaks(
        [{ path: "browser.pageerror", source: error.message }],
        this.exactSentinels
      );
      this.publicSurfaceLeaks.push(...findings);
      this.pageFailures.push({
        messageSha256: sha256Text(error.message),
        leakCodes: findings.map((finding) => finding.code)
      });
    });
  }

  apiMutations() {
    return this.requests.filter((request) => !new Set(["GET", "HEAD", "OPTIONS"]).has(request.method));
  }

  requestsFor(method, pathname) {
    return this.requests.filter((request) => request.method === method && request.pathname === pathname);
  }

  assertApiBinding(apiBaseUrl) {
    if (this.apiBaseUrl !== null && this.apiBaseUrl !== apiBaseUrl) {
      throw new Error("API binding assertion differs from the ledger's reviewed API base");
    }
    assertApiBaseRequests(apiBaseUrl, this.requests);
  }

  async drainAndAssertPublicEvidenceClean(options = {}) {
    while (this.pendingResponseCaptures.size) {
      await Promise.all([...this.pendingResponseCaptures]);
    }
    if (this.responseCaptureFailures.length) {
      throw new Error(`Public request/response evidence capture failed: count=${this.responseCaptureFailures.length}`);
    }
    this.assertNoRuntimeFailures(options);
  }

  assertNoRuntimeFailures({
    allowExpectedBrowserOffline = false,
    allowExpectedBackendUnavailable = false,
    allowedRequestFailures = []
  } = {}) {
    if (this.pendingResponseCaptures.size) {
      throw new Error("Public response evidence must be drained before runtime assertions");
    }
    const allowedKinds = new Set([
      ...(allowExpectedBrowserOffline ? ["EXPECTED_BROWSER_OFFLINE"] : []),
      ...(allowExpectedBackendUnavailable ? ["EXPECTED_BACKEND_UNAVAILABLE"] : [])
    ]);
    const consoleFailures = this.consoleFailures.filter((failure) => !allowedKinds.has(failure.kind));
    const requestFailures = this.requestFailures.filter((failure) =>
      !allowedRequestFailures.some((rule) => requestFailureMatches(failure, rule))
    );
    if (consoleFailures.length || requestFailures.length || this.pageFailures.length || this.publicSurfaceLeaks.length) {
      throw new Error(
        `Browser runtime failures: console=${consoleFailures.length}, request=${requestFailures.length}, page=${this.pageFailures.length}, publicLeaks=${this.publicSurfaceLeaks.length}`
      );
    }
  }
}

export async function contractControl(page, testId, role, accessibleName) {
  const byRole = page.getByRole(role, { name: accessibleName });
  if (await byRole.count()) return byRole.first();
  return page.getByTestId(testId).first();
}

export function cssAttributeValue(value) {
  return String(value)
    .replace(/\\/g, "\\\\")
    .replace(/"/g, "\\\"")
    .replace(/\n/g, "\\a ")
    .replace(/\r/g, "\\d ");
}

export function identityLocator(page, testId, attribute, value) {
  return page.locator(
    `[data-testid="${cssAttributeValue(testId)}"][${attribute}="${cssAttributeValue(value)}"]`
  );
}

function canonicalDomInteger(value, path, minimum) {
  if (typeof value !== "string" || !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new Error(`${path} must be a canonical integer attribute`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum) {
    throw new Error(`${path} must be a safe integer >= ${minimum}`);
  }
  return parsed;
}

function nullableDomString(value, path) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value !== "string" || value.trim() !== value) throw new Error(`${path} must be canonical`);
  return value;
}

export function decodeProjectionLifecycleAttributes(attributes) {
  if (attributes === null || typeof attributes !== "object" || Array.isArray(attributes)) {
    throw new Error("projection lifecycle attributes must be an object");
  }
  const runId = nullableDomString(attributes.runId, "projection lifecycle runId");
  if (runId === null) throw new Error("projection lifecycle runId is required");
  const requestEpoch = canonicalDomInteger(attributes.requestEpoch, "projection lifecycle requestEpoch", 1);
  if (!new Set(["true", "false"]).has(attributes.settled)) {
    throw new Error("projection lifecycle settled must be true or false");
  }
  const settled = attributes.settled === "true";
  const consumedRaw = [
    nullableDomString(attributes.consumedRunId, "projection lifecycle consumedRunId"),
    nullableDomString(attributes.consumedRequestEpoch, "projection lifecycle consumedRequestEpoch"),
    nullableDomString(attributes.consumedProjectionRevision, "projection lifecycle consumedProjectionRevision"),
    nullableDomString(attributes.consumedProjectionSequence, "projection lifecycle consumedProjectionSequence")
  ];
  if (consumedRaw.filter((item) => item !== null).length % consumedRaw.length !== 0) {
    throw new Error("projection lifecycle consumed response tuple must be wholly present or absent");
  }
  const consumed = consumedRaw[0] === null ? null : {
    runId: consumedRaw[0],
    requestEpoch: canonicalDomInteger(consumedRaw[1], "projection lifecycle consumedRequestEpoch", 1),
    projectionRevision: canonicalDomInteger(consumedRaw[2], "projection lifecycle consumedProjectionRevision", 1),
    projectionSequence: canonicalDomInteger(consumedRaw[3], "projection lifecycle consumedProjectionSequence", 0)
  };
  if (settled && (consumed === null || consumed.runId !== runId || consumed.requestEpoch !== requestEpoch)) {
    throw new Error("settled projection lifecycle must identify the current consumed response");
  }
  const discardedRaw = [
    nullableDomString(attributes.discardedRunId, "projection lifecycle discardedRunId"),
    nullableDomString(attributes.discardedRequestEpoch, "projection lifecycle discardedRequestEpoch"),
    nullableDomString(attributes.discardedProjectionRevision, "projection lifecycle discardedProjectionRevision"),
    nullableDomString(attributes.discardedProjectionSequence, "projection lifecycle discardedProjectionSequence"),
    nullableDomString(attributes.discardReason, "projection lifecycle discardReason")
  ];
  if (discardedRaw.filter((item) => item !== null).length % discardedRaw.length !== 0) {
    throw new Error("projection lifecycle discarded response tuple must be wholly present or absent");
  }
  const discarded = discardedRaw[0] === null ? null : {
    runId: discardedRaw[0],
    requestEpoch: canonicalDomInteger(discardedRaw[1], "projection lifecycle discardedRequestEpoch", 1),
    projectionRevision: canonicalDomInteger(discardedRaw[2], "projection lifecycle discardedProjectionRevision", 1),
    projectionSequence: canonicalDomInteger(discardedRaw[3], "projection lifecycle discardedProjectionSequence", 0),
    reason: discardedRaw[4]
  };
  if (discarded && !new Set(["STALE_RESPONSE", "IDENTITY_MISMATCH"]).has(discarded.reason)) {
    throw new Error("projection lifecycle discard reason is unsupported");
  }
  return Object.freeze({ runId, requestEpoch, settled, consumed: consumed && Object.freeze(consumed), discarded: discarded && Object.freeze(discarded) });
}

export async function loadedFrontendSources(page, apiRequest, exactSentinels = []) {
  const baseOrigin = new URL(page.url()).origin;
  const discovered = await page.evaluate(() => {
    const resources = performance.getEntriesByType("resource").map((entry) => entry.name);
    const scripts = [...document.querySelectorAll("script[src]")].map((node) => node.src);
    return { resources, scripts };
  });
  const sourceUrls = discoverFrontendSourceUrls(baseOrigin, discovered.resources, discovered.scripts);
  return fetchFrontendSources(sourceUrls, apiRequest, exactSentinels);
}

export function discoverFrontendSourceUrls(baseOrigin, resourceUrls, scriptUrls) {
  const sourceUrls = [...new Set([...resourceUrls, ...scriptUrls])].filter((url) => {
    const parsed = new URL(url);
    if (parsed.origin !== baseOrigin || isBusinessApiPath(url)) return false;
    return /(?:\.(?:js|mjs|jsx|ts|tsx)(?:$|\?)|\/src\/|\/@vite\/)/i.test(url);
  }).sort();
  if (!sourceUrls.length) {
    throw new Error("Frontend source discovery produced no independently fetchable module");
  }
  return sourceUrls;
}

export async function fetchFrontendSources(sourceUrls, apiRequest, exactSentinels = []) {
  const sources = [];
  for (const url of sourceUrls) {
    const response = await apiRequest.get(url);
    if (!response.ok()) {
      const path = redactExactSentinels(new URL(url).pathname, exactSentinels);
      throw new Error(`Frontend source fetch failed with HTTP ${response.status()} at ${path}`);
    }
    const body = await response.body();
    if (!body.byteLength) {
      throw new Error(`Frontend source is empty at ${redactExactSentinels(new URL(url).pathname, exactSentinels)}`);
    }
    if (body.byteLength > MAX_FRONTEND_SOURCE_BYTES) {
      throw new Error(
        `Frontend source exceeds ${MAX_FRONTEND_SOURCE_BYTES} bytes at ${redactExactSentinels(new URL(url).pathname, exactSentinels)}`
      );
    }
    sources.push(Object.freeze({
      path: redactExactSentinels(new URL(url).pathname, exactSentinels),
      source: body.toString("utf8"),
      byteLength: body.byteLength,
      sha256: sha256Bytes(body)
    }));
  }
  if (sources.length !== sourceUrls.length || !sources.length) {
    throw new Error("Frontend source evidence is incomplete");
  }
  return Object.freeze(sources);
}

export function appendQuery(pathname, values) {
  const url = new URL(pathname, "http://contract.invalid");
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null) url.searchParams.set(key, value);
  }
  return `${url.pathname}${url.search}`;
}
