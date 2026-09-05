import {
  PHASE4_CONTRACT_VERSION,
  decodeErrorEnvelope,
  type ErrorCode,
  type ErrorEnvelope,
  type ErrorRecovery
} from "../types/domain";

export const phase4ApiRoutes = {
  objects: "/api/objects",
  object: (objectId: string) => `/api/objects/${encodeURIComponent(objectId)}`,
  objectRuns: (objectId: string) => `/api/objects/${encodeURIComponent(objectId)}/runs`,
  prepareRun: "/api/research-runs/prepare",
  runs: "/api/research-runs",
  run: (runId: string) => `/api/research-runs/${encodeURIComponent(runId)}`,
  runProjection: (runId: string) =>
    `/api/research-runs/${encodeURIComponent(runId)}/projection`,
  runResult: (runId: string) =>
    `/api/research-runs/${encodeURIComponent(runId)}/result`
} as const;

export type Phase4HttpMethod = "GET" | "POST";
export type Phase4Fetch = (
  input: RequestInfo | URL,
  init?: RequestInit
) => Promise<Response>;

export interface Phase4ApiClientOptions {
  readonly baseUrl?: string;
  readonly fetch?: Phase4Fetch;
}

export interface Phase4JsonRequest<T> {
  readonly method: Phase4HttpMethod;
  readonly path: string;
  readonly expectedStatuses: readonly number[];
  readonly decode: (value: unknown) => T;
  readonly validateSuccess?: (value: T, status: number, response: Response) => void;
  readonly body?: string;
  readonly idempotencyKey?: string;
  readonly signal?: AbortSignal;
}

interface ErrorProtocol {
  readonly status: number;
  readonly retryable: boolean;
  readonly recovery: ErrorRecovery;
}

const ERROR_PROTOCOL = {
  INVALID_CURSOR: { status: 400, retryable: false, recovery: "SNAPSHOT_RELOAD" },
  UNAUTHENTICATED: { status: 401, retryable: false, recovery: "REAUTHENTICATE" },
  FORBIDDEN: { status: 403, retryable: false, recovery: "NONE" },
  NOT_FOUND: { status: 404, retryable: false, recovery: "NONE" },
  IDENTITY_MISMATCH: { status: 404, retryable: false, recovery: "NONE" },
  UNAVAILABLE: { status: 409, retryable: false, recovery: "NONE" },
  NOT_GENERATED: { status: 409, retryable: false, recovery: "NONE" },
  NOT_RELEASED: { status: 409, retryable: false, recovery: "SNAPSHOT_RELOAD" },
  CONFLICT: { status: 409, retryable: false, recovery: "NONE" },
  CURSOR_AHEAD: { status: 409, retryable: false, recovery: "SNAPSHOT_RELOAD" },
  SCHEMA_INCOMPATIBLE: { status: 409, retryable: false, recovery: "NONE" },
  UNSUPPORTED_EVENT: { status: 409, retryable: false, recovery: "SNAPSHOT_RELOAD" },
  TERMINAL: { status: 409, retryable: false, recovery: "NONE" },
  REQUEST_VALIDATION_ERROR: { status: 422, retryable: false, recovery: "NONE" },
  INTEGRITY_FAILURE: { status: 500, retryable: false, recovery: "SNAPSHOT_RELOAD" },
  INTERNAL_ERROR: { status: 500, retryable: false, recovery: "NONE" },
  TRANSIENT_BACKEND_ERROR: { status: 503, retryable: true, recovery: "RETRY" }
} as const satisfies Record<ErrorCode, ErrorProtocol>;

/** A validated Phase 4 error response. No raw response body is retained. */
export class Phase4ApiError extends Error {
  readonly name = "Phase4ApiError";

  constructor(
    readonly status: number,
    readonly envelope: ErrorEnvelope,
    readonly request: Readonly<{ method: Phase4HttpMethod; path: string }>
  ) {
    super(`Phase 4 API request failed (${envelope.error.code})`);
  }

  get code(): ErrorCode {
    return this.envelope.error.code;
  }

  get retryable(): boolean {
    return this.envelope.error.retryable;
  }

  get recovery(): ErrorRecovery {
    return this.envelope.error.recovery;
  }
}

/** The server replied, but its HTTP or representation contract was invalid. */
export class Phase4ProtocolError extends Error {
  readonly name = "Phase4ProtocolError";

  constructor(
    message: string,
    readonly request: Readonly<{ method: Phase4HttpMethod; path: string }>,
    readonly status: number | null = null
  ) {
    super(message);
  }
}

/** Fetch failed before a contract-authoritative response could be admitted. */
export class Phase4TransportError extends Error {
  readonly name = "Phase4TransportError";

  constructor(
    readonly kind: "NETWORK" | "ABORTED",
    readonly request: Readonly<{ method: Phase4HttpMethod; path: string }>
  ) {
    super(
      kind === "ABORTED"
        ? "Phase 4 API request was aborted"
        : "Phase 4 API request failed before a response was admitted"
    );
  }
}

function assertJsonMediaType(
  response: Response,
  request: Readonly<{ method: Phase4HttpMethod; path: string }>,
  requireUtf8: boolean
): void {
  const contentType = response.headers.get("Content-Type");
  if (contentType === null) {
    throw new Phase4ProtocolError(
      "Phase 4 JSON response omitted Content-Type",
      request,
      response.status
    );
  }

  const [rawMediaType, ...rawParameters] = contentType.split(";");
  const mediaType = rawMediaType.trim().toLowerCase();
  const parameters = new Map(
    rawParameters.map((parameter) => {
      const [name, ...valueParts] = parameter.split("=");
      return [
        name.trim().toLowerCase(),
        valueParts.join("=").trim().replace(/^"|"$/gu, "").toLowerCase()
      ] as const;
    })
  );

  const charset = parameters.get("charset");
  if (
    mediaType !== "application/json" ||
    (requireUtf8 ? charset !== "utf-8" : charset !== undefined && charset !== "utf-8")
  ) {
    throw new Phase4ProtocolError(
      "Phase 4 JSON response has an incompatible media type",
      request,
      response.status
    );
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function assertIdempotencyKey(value: string | undefined): string {
  if (value === undefined || value.trim().length === 0 || /[\r\n]/u.test(value)) {
    throw new TypeError("A non-empty Idempotency-Key is required for Phase 4 mutations");
  }
  return value;
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
}

export class Phase4ApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: Phase4Fetch;
  private readonly idempotentBodies = new Map<string, string>();

  constructor(options: Phase4ApiClientOptions = {}) {
    this.baseUrl = normalizeBaseUrl(options.baseUrl ?? "");
    this.fetchImpl = options.fetch ?? globalThis.fetch.bind(globalThis);
  }

  async requestJson<T>(options: Phase4JsonRequest<T>): Promise<T> {
    const request = Object.freeze({ method: options.method, path: options.path });
    const headers = new Headers({
      Accept: "application/json",
      "X-Phase4-Contract-Version": PHASE4_CONTRACT_VERSION
    });

    if (options.method === "POST") {
      const key = assertIdempotencyKey(options.idempotencyKey);
      if (options.body === undefined) {
        throw new TypeError("A JSON body is required for Phase 4 mutations");
      }
      headers.set("Content-Type", "application/json; charset=utf-8");
      headers.set("Idempotency-Key", key);

      const operationKey = JSON.stringify([options.method, options.path, key]);
      const retainedBody = this.idempotentBodies.get(operationKey);
      if (retainedBody !== undefined && retainedBody !== options.body) {
        throw new Phase4ProtocolError(
          "An Idempotency-Key cannot be reused with a different request body",
          request
        );
      }
      this.idempotentBodies.set(operationKey, options.body);
    } else if (options.body !== undefined || options.idempotencyKey !== undefined) {
      throw new TypeError("Phase 4 reads cannot carry a mutation body or Idempotency-Key");
    }

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${options.path}`, {
        method: options.method,
        headers,
        body: options.body,
        credentials: "same-origin",
        redirect: "error",
        signal: options.signal
      });
    } catch (error: unknown) {
      throw new Phase4TransportError(isAbort(error) ? "ABORTED" : "NETWORK", request);
    }

    // The frozen contract requires the explicit UTF-8 parameter on success.
    // Error envelopes may omit it, but may never declare a different charset.
    assertJsonMediaType(response, request, response.ok);

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new Phase4ProtocolError(
        "Phase 4 response body is not valid JSON",
        request,
        response.status
      );
    }

    if (!response.ok) {
      let envelope: ErrorEnvelope;
      try {
        envelope = decodeErrorEnvelope(payload);
      } catch {
        throw new Phase4ProtocolError(
          "Phase 4 error response does not match the frozen error envelope",
          request,
          response.status
        );
      }
      const protocol = ERROR_PROTOCOL[envelope.error.code];
      if (
        protocol.status !== response.status ||
        protocol.retryable !== envelope.error.retryable ||
        protocol.recovery !== envelope.error.recovery
      ) {
        throw new Phase4ProtocolError(
          "Phase 4 error response contradicts the frozen HTTP recovery tuple",
          request,
          response.status
        );
      }
      throw new Phase4ApiError(response.status, envelope, request);
    }

    if (!options.expectedStatuses.includes(response.status)) {
      throw new Phase4ProtocolError(
        "Phase 4 response used an unexpected success status",
        request,
        response.status
      );
    }
    if (response.headers.get("X-Phase4-Contract-Version") !== PHASE4_CONTRACT_VERSION) {
      throw new Phase4ProtocolError(
        "Phase 4 response omitted the selected contract version",
        request,
        response.status
      );
    }

    let decoded: T;
    try {
      decoded = options.decode(payload);
    } catch {
      throw new Phase4ProtocolError(
        "Phase 4 success response does not match the frozen response contract",
        request,
        response.status
      );
    }
    options.validateSuccess?.(decoded, response.status, response);
    return decoded;
  }
}
