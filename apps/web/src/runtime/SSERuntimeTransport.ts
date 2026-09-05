import type {
  ConnectionState,
  ErrorEnvelope,
  NormalizedRuntimeEventV1
} from "../types/domain";
import {
  PHASE4_CONTRACT_VERSION,
  RUNTIME_EVENT_CONTRACT_VERSION,
  RuntimeEventIngestionGuard,
  RuntimeIngestionError,
  type RuntimeSubscription,
  type RuntimeSubscriptionOptions,
  type RuntimeTransport
} from "./RuntimeTransport";

export interface SSEFrame {
  readonly id?: string;
  readonly event?: string;
  readonly data: string;
}

export interface SSEFrameParserHandlers {
  readonly onFrame: (frame: SSEFrame) => void;
  readonly onComment?: (comment: string) => void;
}

/** Incremental SSE parser supporting split UTF-8 chunks, CR/LF, comments and multiline data. */
export class SSEFrameParser {
  private readonly handlers: SSEFrameParserHandlers;
  private readonly maximumBufferedCharacters: number;
  private buffer = "";
  private eventName: string | undefined;
  private eventId: string | undefined;
  private dataLines: string[] = [];
  private frameCharacterCount = 0;

  constructor(handlers: SSEFrameParserHandlers, maximumBufferedCharacters = 1_048_576) {
    if (!Number.isSafeInteger(maximumBufferedCharacters) || maximumBufferedCharacters < 1) {
      throw new TypeError("maximumBufferedCharacters must be a positive safe integer");
    }
    this.handlers = handlers;
    this.maximumBufferedCharacters = maximumBufferedCharacters;
  }

  push(chunk: string) {
    this.buffer += chunk;
    if (this.buffer.length > this.maximumBufferedCharacters) {
      throw new RuntimeIngestionError("MALFORMED_EVENT", "SSE frame exceeded the safe buffer limit");
    }
    this.consumeLines(false);
  }

  finish() {
    this.consumeLines(true);
    if (this.buffer.length > 0 || this.dataLines.length > 0 || this.eventId || this.eventName) {
      throw new RuntimeIngestionError("MALFORMED_EVENT", "SSE stream ended during an incomplete frame");
    }
  }

  private consumeLines(final: boolean) {
    while (true) {
      const boundary = this.nextLineBoundary(final);
      if (boundary === null) return;
      const line = this.buffer.slice(0, boundary.index);
      this.buffer = this.buffer.slice(boundary.index + boundary.length);
      this.consumeLine(line);
    }
  }

  private nextLineBoundary(final: boolean): { index: number; length: number } | null {
    for (let index = 0; index < this.buffer.length; index += 1) {
      const character = this.buffer[index];
      if (character === "\n") return { index, length: 1 };
      if (character !== "\r") continue;
      if (index + 1 === this.buffer.length && !final) return null;
      return { index, length: this.buffer[index + 1] === "\n" ? 2 : 1 };
    }
    return null;
  }

  private consumeLine(line: string) {
    if (line === "") {
      this.dispatch();
      return;
    }
    if (line.startsWith(":")) {
      this.handlers.onComment?.(line.slice(1).replace(/^ /u, ""));
      return;
    }
    const separator = line.indexOf(":");
    const field = separator < 0 ? line : line.slice(0, separator);
    let value = separator < 0 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    switch (field) {
      case "event":
        this.eventName = value;
        break;
      case "data":
        this.frameCharacterCount += value.length + (this.dataLines.length > 0 ? 1 : 0);
        if (this.frameCharacterCount > this.maximumBufferedCharacters) {
          throw new RuntimeIngestionError("MALFORMED_EVENT", "SSE frame exceeded the safe buffer limit");
        }
        this.dataLines.push(value);
        break;
      case "id":
        if (!value.includes("\u0000")) this.eventId = value;
        break;
      default:
        // SSE specifies that unknown fields, including retry, are ignored.
        break;
    }
  }

  private dispatch() {
    if (this.dataLines.length === 0) {
      this.eventName = undefined;
      this.eventId = undefined;
      return;
    }
    const frame = Object.freeze({
      id: this.eventId,
      event: this.eventName,
      data: this.dataLines.join("\n")
    });
    this.eventName = undefined;
    this.eventId = undefined;
    this.dataLines = [];
    this.frameCharacterCount = 0;
    this.handlers.onFrame(frame);
  }
}

export class RuntimeSSEHttpError extends Error {
  readonly status: number;
  readonly code: RuntimeErrorCodeV1;
  readonly retryable: boolean;
  readonly recovery: RuntimeErrorRecoveryV1;

  constructor(options: {
    readonly status: number;
    readonly code: RuntimeErrorCodeV1;
    readonly message: string;
    readonly retryable: boolean;
    readonly recovery: RuntimeErrorRecoveryV1;
  }) {
    super(options.message);
    this.name = "RuntimeSSEHttpError";
    this.status = options.status;
    this.code = options.code;
    this.retryable = options.retryable;
    this.recovery = options.recovery;
  }
}

interface ErrorEnvelopeWire {
  readonly schema_version: "phase4-error/v1";
  readonly error: {
    readonly code: RuntimeErrorCodeV1;
    readonly message: string;
    readonly retryable: boolean;
    readonly recovery: RuntimeErrorRecoveryV1;
    readonly request_id: string | null;
    readonly resource: { readonly type: string; readonly id: string } | null;
    readonly details: Readonly<Record<string, unknown>>;
  };
}

export const RUNTIME_ERROR_POLICY_V1 = Object.freeze({
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
} as const);

export type RuntimeErrorCodeV1 = keyof typeof RUNTIME_ERROR_POLICY_V1;
export type RuntimeErrorRecoveryV1 =
  typeof RUNTIME_ERROR_POLICY_V1[RuntimeErrorCodeV1]["recovery"];

type RuntimeFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export interface SSERuntimeTransportOptions {
  readonly basePath?: string;
  readonly fetchImplementation?: RuntimeFetch;
  readonly maximumBufferedCharacters?: number;
  readonly now?: () => number;
}

export const RUNTIME_BACKOFF_BASE_MILLISECONDS_V1 = 1_000;
export const RUNTIME_BACKOFF_MAXIMUM_MILLISECONDS_V1 = 30_000;

/** Deterministic exponential delay for the failed connection attempt, capped at 30 seconds. */
export function runtimeBackoffDelayMillisecondsV1(failedAttempt: number) {
  if (!Number.isSafeInteger(failedAttempt) || failedAttempt < 1) {
    throw new TypeError("failedAttempt must be a positive safe integer");
  }
  const exponent = Math.min(failedAttempt - 1, 30);
  return Math.min(
    RUNTIME_BACKOFF_MAXIMUM_MILLISECONDS_V1,
    RUNTIME_BACKOFF_BASE_MILLISECONDS_V1 * (2 ** exponent)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSafeText(value: unknown): value is string {
  return typeof value === "string"
    && value.length > 0
    && value.length <= 4096
    && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(value);
}

function hasExactFields(value: Record<string, unknown>, fields: readonly string[]) {
  const expected = new Set(fields);
  return Object.keys(value).length === expected.size
    && Object.keys(value).every((field) => expected.has(field));
}

function isRuntimeErrorCode(value: unknown): value is RuntimeErrorCodeV1 {
  return typeof value === "string"
    && Object.prototype.hasOwnProperty.call(RUNTIME_ERROR_POLICY_V1, value);
}

function isRuntimeResource(value: unknown): value is { readonly type: string; readonly id: string } {
  return isRecord(value)
    && hasExactFields(value, ["type", "id"])
    && isSafeText(value.type)
    && isSafeText(value.id);
}

function decodeErrorEnvelope(input: unknown, status: number): RuntimeSSEHttpError {
  if (
    isRecord(input)
    && hasExactFields(input, ["schema_version", "error"])
    && input.schema_version === "phase4-error/v1"
    && isRecord(input.error)
    && hasExactFields(input.error, [
      "code", "message", "retryable", "recovery", "request_id", "resource", "details"
    ])
    && isRuntimeErrorCode(input.error.code)
    && isSafeText(input.error.message)
    && typeof input.error.retryable === "boolean"
    && typeof input.error.recovery === "string"
    && (input.error.request_id === null || isSafeText(input.error.request_id))
    && (input.error.resource === null || isRuntimeResource(input.error.resource))
    && isRecord(input.error.details)
  ) {
    const wire = input as unknown as ErrorEnvelopeWire;
    const policy = RUNTIME_ERROR_POLICY_V1[wire.error.code];
    if (
      status === policy.status
      && wire.error.retryable === policy.retryable
      && wire.error.recovery === policy.recovery
    ) {
      return new RuntimeSSEHttpError({
        status,
        code: wire.error.code,
        message: wire.error.message,
        retryable: wire.error.retryable,
        recovery: wire.error.recovery
      });
    }
  }
  return new RuntimeSSEHttpError({
    status,
    code: "INTERNAL_ERROR",
    message: "The runtime stream request failed without a valid safe error envelope",
    retryable: false,
    recovery: "NONE"
  });
}

function isCanonicalSequence(value: string) {
  return /^(?:0|[1-9][0-9]*)$/u.test(value)
    && Number.isSafeInteger(Number(value));
}

function isNumericLike(value: string) {
  return /^[+-]?[0-9]+(?:\.[0-9]+)?$/u.test(value);
}

/** Build the exact Last-Event-ID header without accepting malformed numeric aliases. */
export function runtimeCursorHeaderV1(
  runId: string,
  options: RuntimeSubscriptionOptions
): string {
  if (!Number.isSafeInteger(options.initialSequence) || options.initialSequence < 0) {
    throw new RuntimeIngestionError("MALFORMED_EVENT", "Snapshot cursor must be a nonnegative safe integer");
  }
  const cursor = options.resumeCursor;
  if (cursor === undefined) return String(options.initialSequence);
  if (cursor.length === 0 || cursor.trim() !== cursor || cursor.length > 256) {
    throw new RuntimeIngestionError("MALFORMED_EVENT", "Resume cursor is malformed");
  }
  if (isCanonicalSequence(cursor)) {
    if (Number(cursor) !== options.initialSequence) {
      throw new RuntimeIngestionError("SEQUENCE_CONFLICT", "Numeric resume cursor conflicts with snapshot sequence");
    }
    return cursor;
  }
  if (isNumericLike(cursor) || !/^[A-Za-z0-9._:-]{1,256}$/u.test(cursor)) {
    throw new RuntimeIngestionError("MALFORMED_EVENT", "Resume cursor is not a canonical sequence or opaque event ID");
  }
  const exactAccepted = options.acceptedEvents?.some(
    (event) => event.runId === runId
      && event.eventId === cursor
      && event.sequence === options.initialSequence
  );
  if (!exactAccepted) {
    throw new RuntimeIngestionError("EVENT_ID_CONFLICT", "Opaque resume cursor is not bound to the exact Run cursor");
  }
  return cursor;
}

function recoveryReason(error: RuntimeIngestionError):
  "SEQUENCE_GAP" | "UNKNOWN_EVENT" | "SCHEMA_INCOMPATIBLE" | "PROJECTION_MISMATCH" {
  if (["SEQUENCE_GAP", "SEQUENCE_CONFLICT", "STALE_EVENT", "EVENT_ID_CONFLICT", "EVENT_AFTER_TERMINAL"].includes(error.reason)) {
    return "SEQUENCE_GAP";
  }
  if (error.reason === "UNSUPPORTED_EVENT") return "UNKNOWN_EVENT";
  if (error.reason === "SCHEMA_INCOMPATIBLE") return "SCHEMA_INCOMPATIBLE";
  return "PROJECTION_MISMATCH";
}

function terminalOutcome(event: NormalizedRuntimeEventV1): "SUCCESS" | "FAILURE" | "CANCELLED" {
  if (event.type === "run.completed") return "SUCCESS";
  const payload = event.payload as Readonly<Record<string, unknown>>;
  return payload.status === "CANCELLED" ? "CANCELLED" : "FAILURE";
}

function state(options: RuntimeSubscriptionOptions, value: ConnectionState) {
  options.onStateChange?.(value);
}

function safeConnectionError(error: RuntimeSSEHttpError): ErrorEnvelope {
  return {
    schemaVersion: "phase4-error/v1",
    error: {
      code: error.code,
      message: error.message,
      retryable: error.retryable,
      recovery: error.recovery,
      requestId: null,
      resource: null,
      details: {}
    }
  };
}

function safeTransientDisconnectError() {
  return new RuntimeSSEHttpError({
    status: 503,
    code: "TRANSIENT_BACKEND_ERROR",
    message: "The runtime stream disconnected before terminal closure",
    retryable: true,
    recovery: "RETRY"
  });
}

/** One exact fetch-stream connection; Parent composition owns resubscribe and snapshot recovery. */
export class SSERuntimeTransport implements RuntimeTransport {
  readonly kind = "sse" as const;
  private readonly basePath: string;
  private readonly fetchImplementation: RuntimeFetch;
  private readonly maximumBufferedCharacters: number;
  private readonly now: () => number;
  private activeGeneration = 0;
  private activeAbort: AbortController | null = null;

  constructor(options: SSERuntimeTransportOptions = {}) {
    this.basePath = (options.basePath ?? "/api").replace(/\/+$/u, "");
    this.fetchImplementation = options.fetchImplementation ?? globalThis.fetch.bind(globalThis);
    this.maximumBufferedCharacters = options.maximumBufferedCharacters ?? 1_048_576;
    this.now = options.now ?? Date.now;
  }

  subscribe(
    runId: string,
    onEvent: (event: NormalizedRuntimeEventV1) => void,
    onError: ((error: Error) => void) | undefined,
    options: RuntimeSubscriptionOptions
  ): RuntimeSubscription {
    this.activeAbort?.abort();
    const generation = ++this.activeGeneration;
    const controller = new AbortController();
    this.activeAbort = controller;
    let manuallyClosed = false;
    const isActive = () => generation === this.activeGeneration && !controller.signal.aborted;
    const externalAbort = () => controller.abort();
    if (options.signal?.aborted) controller.abort();
    else options.signal?.addEventListener("abort", externalAbort, { once: true });

    const guard = new RuntimeEventIngestionGuard({
      runId,
      initialSequence: options.initialSequence,
      authoritativeTaskIds: options.authoritativeTaskIds,
      acceptedEvents: options.acceptedEvents
    });

    const closed = this.consume({
      runId,
      guard,
      controller,
      options,
      isActive,
      onEvent
    }).catch((error: unknown) => {
      if (controller.signal.aborted || manuallyClosed || generation !== this.activeGeneration) return;
      const normalized = error instanceof RuntimeIngestionError
        || error instanceof RuntimeSSEHttpError
        ? error
        : safeTransientDisconnectError();
      if (
        normalized instanceof RuntimeSSEHttpError
        && (normalized.code === "INVALID_CURSOR" || normalized.code === "CURSOR_AHEAD")
      ) {
        state(options, {
          kind: "RECOVERING",
          runId,
          lastSequence: guard.lastSequence,
          reason: "CURSOR_REJECTED"
        });
      } else if (
        normalized instanceof RuntimeSSEHttpError
        && normalized.code === "UNSUPPORTED_EVENT"
      ) {
        state(options, {
          kind: "RECOVERING",
          runId,
          lastSequence: guard.lastSequence,
          reason: "UNKNOWN_EVENT"
        });
      } else if (normalized instanceof RuntimeSSEHttpError && !normalized.retryable) {
        state(options, {
          kind: "FAILED",
          runId,
          lastSequence: guard.lastSequence,
          error: safeConnectionError(normalized)
        });
      } else if (normalized instanceof RuntimeSSEHttpError) {
        const failedAttempt = options.attempt ?? 1;
        const nextAttempt = failedAttempt + 1;
        const retryAtMilliseconds = this.now()
          + runtimeBackoffDelayMillisecondsV1(failedAttempt);
        if (
          !Number.isSafeInteger(nextAttempt)
          || !Number.isFinite(retryAtMilliseconds)
          || Math.abs(retryAtMilliseconds) > 8_640_000_000_000_000
        ) {
          state(options, {
            kind: "FAILED",
            runId,
            lastSequence: guard.lastSequence,
            error: safeConnectionError(new RuntimeSSEHttpError({
              status: 500,
              code: "INTERNAL_ERROR",
              message: "The runtime retry schedule is invalid",
              retryable: false,
              recovery: "NONE"
            }))
          });
        } else {
          state(options, {
            kind: "BACKOFF",
            runId,
            lastSequence: guard.lastSequence,
            retryAt: new Date(retryAtMilliseconds).toISOString(),
            attempt: nextAttempt,
            error: safeConnectionError(normalized)
          });
        }
      } else if (normalized instanceof RuntimeIngestionError) {
        state(options, {
          kind: "RECOVERING",
          runId,
          lastSequence: guard.lastSequence,
          reason: recoveryReason(normalized)
        });
      }
      onError?.(normalized);
    }).finally(() => {
      options.signal?.removeEventListener("abort", externalAbort);
      if (generation === this.activeGeneration) this.activeAbort = null;
    });

    return {
      closed,
      unsubscribe: () => {
        if (manuallyClosed) return;
        manuallyClosed = true;
        controller.abort();
        if (generation === this.activeGeneration) this.activeGeneration += 1;
      }
    };
  }

  private async consume(input: {
    readonly runId: string;
    readonly guard: RuntimeEventIngestionGuard;
    readonly controller: AbortController;
    readonly options: RuntimeSubscriptionOptions;
    readonly isActive: () => boolean;
    readonly onEvent: (event: NormalizedRuntimeEventV1) => void;
  }) {
    if (!input.isActive()) return;
    const attempt = input.options.attempt ?? 1;
    if (!Number.isSafeInteger(attempt) || attempt < 1) {
      throw new RuntimeIngestionError("MALFORMED_EVENT", "Connection attempt must be positive");
    }
    state(input.options, {
      kind: "CONNECTING",
      runId: input.runId,
      lastSequence: input.guard.lastSequence,
      attempt
    });
    const response = await this.fetchImplementation(
      `${this.basePath}/research-runs/${encodeURIComponent(input.runId)}/events`,
      {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          Accept: "text/event-stream",
          "Last-Event-ID": runtimeCursorHeaderV1(input.runId, input.options),
          "X-Phase4-Contract-Version": PHASE4_CONTRACT_VERSION
        },
        signal: input.controller.signal
      }
    );
    if (!input.isActive()) return;
    if (!response.ok) {
      let body: unknown;
      try {
        body = await response.json();
      } catch {
        body = null;
      }
      throw decodeErrorEnvelope(body, response.status);
    }
    if (!response.headers.get("content-type")?.toLowerCase().startsWith("text/event-stream")) {
      throw new RuntimeIngestionError("SCHEMA_INCOMPATIBLE", "Runtime response is not an SSE stream");
    }
    if (response.headers.get("X-Phase4-Contract-Version") !== PHASE4_CONTRACT_VERSION) {
      throw new RuntimeIngestionError("SCHEMA_INCOMPATIBLE", "Runtime response contract version is missing or incompatible");
    }
    if (response.headers.get("X-Phase4-Event-Contract-Version") !== RUNTIME_EVENT_CONTRACT_VERSION) {
      throw new RuntimeIngestionError("SCHEMA_INCOMPATIBLE", "Runtime event contract version is missing or incompatible");
    }

    const terminalAtCursor = response.headers.get("X-Run-Terminal");
    const terminalSequence = response.headers.get("X-Terminal-Sequence");
    if ((terminalAtCursor === null) !== (terminalSequence === null)) {
      throw new RuntimeIngestionError("SCHEMA_INCOMPATIBLE", "Terminal cursor headers are incomplete");
    }
    if (terminalAtCursor !== null) {
      if (terminalAtCursor !== "true" || terminalSequence !== String(input.guard.lastSequence)) {
        throw new RuntimeIngestionError("SCHEMA_INCOMPATIBLE", "Terminal cursor headers are inconsistent");
      }
      input.controller.abort();
      input.options.onTerminalAtCursor?.(input.guard.lastSequence);
      return;
    }
    if (!response.body) {
      throw new RuntimeIngestionError("SCHEMA_INCOMPATIBLE", "Runtime SSE response has no readable body");
    }

    state(input.options, {
      kind: "OPEN",
      runId: input.runId,
      lastSequence: input.guard.lastSequence,
      lastHeartbeatAt: null
    });
    const decoder = new TextDecoder("utf-8", { fatal: true });
    let terminal = false;
    const parser = new SSEFrameParser(
      {
        onComment: (comment) => {
          if (!input.isActive() || terminal || comment !== "heartbeat") return;
          const receivedAt = new Date().toISOString();
          input.options.onHeartbeat?.(receivedAt);
          state(input.options, {
            kind: "OPEN",
            runId: input.runId,
            lastSequence: input.guard.lastSequence,
            lastHeartbeatAt: receivedAt
          });
        },
        onFrame: (frame) => {
          if (!input.isActive()) return;
          if (frame.id === undefined || frame.event === undefined) {
            throw new RuntimeIngestionError("MALFORMED_EVENT", "Business SSE frame requires id and event fields");
          }
          let wire: unknown;
          try {
            wire = JSON.parse(frame.data);
          } catch {
            throw new RuntimeIngestionError("MALFORMED_EVENT", "Business SSE data is not valid JSON");
          }
          const result = input.guard.ingest(wire, frame, input.onEvent);
          if (result.kind === "DUPLICATE") {
            input.options.onDuplicate?.(result.event);
            return;
          }
          if (result.event.effect === "TERMINAL") {
            terminal = true;
            state(input.options, {
              kind: "TERMINAL",
              runId: input.runId,
              lastSequence: result.lastSequence,
              outcome: terminalOutcome(result.event)
            });
          } else {
            state(input.options, {
              kind: "OPEN",
              runId: input.runId,
              lastSequence: result.lastSequence,
              lastHeartbeatAt: null
            });
          }
        }
      },
      this.maximumBufferedCharacters
    );

    const reader = response.body.getReader();
    while (input.isActive()) {
      const { done, value } = await reader.read();
      if (done) break;
      try {
        parser.push(decoder.decode(value, { stream: true }));
      } catch (error) {
        if (error instanceof RuntimeIngestionError) throw error;
        throw new RuntimeIngestionError("MALFORMED_EVENT", "Runtime SSE is not valid UTF-8");
      }
      if (terminal) {
        await reader.cancel().catch(() => undefined);
        break;
      }
    }
    if (!input.isActive()) {
      await reader.cancel();
      return;
    }
    try {
      parser.push(decoder.decode());
    } catch (error) {
      if (error instanceof RuntimeIngestionError) throw error;
      throw new RuntimeIngestionError("MALFORMED_EVENT", "Runtime SSE is not valid UTF-8");
    }
    parser.finish();
    if (!terminal) throw safeTransientDisconnectError();
  }
}
