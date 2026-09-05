import { sha256Text } from "./contracts.mjs";

export function pathnameOf(url) {
  return new URL(url).pathname;
}

export function isApiPath(url) {
  return pathnameOf(url).startsWith("/api/");
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

export function safeRequestRecord(request) {
  const headers = request.headers();
  const idempotencyKey = headers["idempotency-key"];
  return Object.freeze({
    method: request.method(),
    pathname: pathnameOf(request.url()),
    contractVersion: headers["x-phase4-contract-version"] ?? null,
    idempotencyKeyPresent: typeof idempotencyKey === "string" && idempotencyKey.length > 0,
    idempotencyKeySha256: idempotencyKey ? sha256Text(idempotencyKey) : null
  });
}

export class BrowserEvidenceLedger {
  constructor(page) {
    this.requests = [];
    this.responses = [];
    this.requestFailures = [];
    this.consoleFailures = [];
    this.pageFailures = [];

    page.on("request", (request) => {
      if (isApiPath(request.url())) this.requests.push(safeRequestRecord(request));
    });
    page.on("response", (response) => {
      if (isApiPath(response.url())) {
        this.responses.push(Object.freeze({
          method: response.request().method(),
          pathname: pathnameOf(response.url()),
          status: response.status()
        }));
      }
    });
    page.on("requestfailed", (request) => {
      if (isApiPath(request.url())) {
        this.requestFailures.push(Object.freeze({
          method: request.method(),
          pathname: pathnameOf(request.url()),
          errorText: request.failure()?.errorText ?? "REQUEST_FAILED"
        }));
      }
    });
    page.on("console", (message) => {
      if (message.type() === "error" || message.type() === "warning") {
        this.consoleFailures.push({ type: message.type(), text: message.text() });
      }
    });
    page.on("pageerror", (error) => this.pageFailures.push(error.message));
  }

  apiMutations() {
    return this.requests.filter((request) => !new Set(["GET", "HEAD", "OPTIONS"]).has(request.method));
  }

  requestsFor(method, pathname) {
    return this.requests.filter((request) => request.method === method && request.pathname === pathname);
  }

  assertNoRuntimeFailures() {
    if (this.consoleFailures.length || this.pageFailures.length) {
      throw new Error(
        `Browser runtime failures: console=${this.consoleFailures.length}, page=${this.pageFailures.length}`
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

export async function loadedFrontendSources(page, apiRequest) {
  const baseOrigin = new URL(page.url()).origin;
  const urls = await page.evaluate(() => {
    const resources = performance.getEntriesByType("resource").map((entry) => entry.name);
    const scripts = [...document.querySelectorAll("script[src]")].map((node) => node.src);
    return [...new Set([...resources, ...scripts])];
  });
  const sourceUrls = urls.filter((url) => {
    const parsed = new URL(url);
    if (parsed.origin !== baseOrigin || parsed.pathname.startsWith("/api/")) return false;
    return /(?:\.(?:js|mjs|jsx|ts|tsx)(?:$|\?)|\/src\/|\/@vite\/)/i.test(url);
  });
  const sources = [];
  for (const url of sourceUrls) {
    const response = await apiRequest.get(url);
    if (response.ok()) sources.push({ path: new URL(url).pathname, source: await response.text() });
  }
  return sources;
}

export function appendQuery(pathname, values) {
  const url = new URL(pathname, "http://contract.invalid");
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null) url.searchParams.set(key, value);
  }
  return `${url.pathname}${url.search}`;
}
