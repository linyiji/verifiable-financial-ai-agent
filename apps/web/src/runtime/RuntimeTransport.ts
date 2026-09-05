import type { RuntimeEvent } from "../types/domain";

export interface RuntimeSubscription {
  unsubscribe(): void;
}

export interface RuntimeTransport {
  readonly kind: "demo" | "sse";
  subscribe(
    runId: string,
    onEvent: (event: RuntimeEvent) => void,
    onError?: (error: Error) => void
  ): RuntimeSubscription;
}
