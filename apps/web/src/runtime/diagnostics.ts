/** Opt-in, bounded internal metadata; never a product DTO or a payload logger. */
const kinds = new Set(["load_start", "http_start", "http_end", "http_failure", "decode_ok", "decode_failure", "projection_received", "projection_installed", "load_failure", "sse_state", "sse_event"]);
const reasons = new Set(["CANONICAL_RECORD_APPEARED", "CURSOR_REGRESSION", "REVISION_REGRESSION", "REVISION_NOT_ADVANCED", "TERMINAL_NOT_READY", "PROJECTION_OTHER", "RUN_PROGRESS_CONTRACT", "PROTOCOL", "NETWORK", "ABORTED", "API_ERROR", "UNKNOWN"]);
const phases = new Set(["request", "reconcile", "select", "installed"]);
const states = new Set(["IDLE", "CONNECTING", "OPEN", "BACKOFF", "RECOVERING", "FAILED", "TERMINAL"]);
const operations = new Set(["projection", "events", "report-view", "review-view", "execution-view", "results", "result", "artifacts"]);
type Store = { enabled: boolean; runId: string; records: Record<string, unknown>[]; dropped: number };
declare global { interface Window { __vfaRuntimeDiagnostics?: Store } }

export function runtimeDiagnosticReason(error: unknown): string {
  if (!(error instanceof Error)) return "UNKNOWN";
  if (error.name === "ContractDecodeError" && error.message === "$.lifecycle.progress: Run progress contradicts authoritative Tasks/status") return "RUN_PROGRESS_CONTRACT";
  if (error.name === "RuntimeProjectionError") {
    const known: Record<string, string> = {
      "projection unexpectedly exposes a canonical record": "CANONICAL_RECORD_APPEARED",
      "replacement snapshot regresses the accepted Run cursor": "CURSOR_REGRESSION",
      "replacement snapshot regresses projection revision": "REVISION_REGRESSION",
      "advanced event watermark requires an advanced projection revision": "REVISION_NOT_ADVANCED",
      "terminal event requires an authoritative terminal snapshot": "TERMINAL_NOT_READY"
    };
    return known[error.message] ?? "PROJECTION_OTHER";
  }
  if (error.name === "Phase4ProtocolError") return "PROTOCOL";
  if (error.name === "Phase4TransportError") return "NETWORK";
  if (error.name === "Phase4ApiError") return "API_ERROR";
  if (error.name === "AbortError") return "ABORTED";
  return "UNKNOWN";
}

export function diagnosticRequest(path: string): { runId: string; operation: string } | null {
  const match = /^\/api\/research-runs\/(RUN-[A-Za-z0-9-]+)\/(projection|events|report-view|review-view|execution-view|results|result|artifacts)$/.exec(path);
  return match ? { runId: match[1], operation: match[2] } : null;
}

export function recordRuntimeDiagnostic(kind: string, runId: string, fields: Record<string, unknown> = {}): void {
  try {
    const store = typeof window === "undefined" ? undefined : window.__vfaRuntimeDiagnostics;
    if (!store?.enabled || runId !== store.runId || !/^RUN-[A-Za-z0-9-]+$/.test(runId) || !kinds.has(kind)) return;
    if (store.records.length >= 5000) { store.dropped += 1; return; }
    const row: Record<string, unknown> = { kind, run_id: runId, monotonic_ms: performance.now() };
    for (const [key, value] of Object.entries(fields)) {
      if (["sequence", "revision", "status", "attempt", "requestEpoch", "requestId"].includes(key) && Number.isSafeInteger(value) && Number(value) >= 0) row[key] = value;
      if (key === "canonicalPresent" && typeof value === "boolean") row[key] = value;
      if (key === "eventId" && typeof value === "string" && /^EVT-[A-Za-z0-9-]+$/.test(value)) row[key] = value;
      if (key === "reason" && typeof value === "string" && reasons.has(value)) row[key] = value;
      if (key === "phase" && typeof value === "string" && phases.has(value)) row[key] = value;
      if (key === "state" && typeof value === "string" && states.has(value)) row[key] = value;
      if (key === "operation" && typeof value === "string" && operations.has(value)) row[key] = value;
    }
    store.records.push(row);
  } catch { /* Diagnostics must not change application control flow. */ }
}
