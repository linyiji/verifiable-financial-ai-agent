import type { RuntimeEvent } from "../types/domain";
import type { RuntimeSubscription, RuntimeTransport } from "./RuntimeTransport";

/** Contract-only placeholder. No EventSource is opened during PRE-INTEGRATION. */
export class SSERuntimeTransport implements RuntimeTransport {
  readonly kind = "sse" as const;

  subscribe(
    _runId: string,
    _onEvent: (event: RuntimeEvent) => void,
    onError?: (error: Error) => void
  ): RuntimeSubscription {
    onError?.(new Error("SSERuntimeTransport is deferred until FRONTEND_V8_BACKEND_INTEGRATION"));
    return { unsubscribe() {} };
  }
}
