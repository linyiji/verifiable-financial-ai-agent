import {
  Phase4ApiError,
  Phase4TransportError
} from "../api/client";
import { runtimeBackoffDelayMillisecondsV1 } from "./SSERuntimeTransport";

export const MAX_PROJECTION_BACKOFF_ATTEMPT_V1 = 31;

export function retryableProjectionReadFailure(error: unknown): boolean {
  return error instanceof Phase4TransportError
    || (error instanceof Phase4ApiError && error.retryable);
}

export function projectionReadFailureDisposition(
  error: unknown,
  hasValidProjection: boolean
): "RETAIN_STALE" | "FULL_PAGE_UNAVAILABLE" {
  return hasValidProjection && retryableProjectionReadFailure(error)
    ? "RETAIN_STALE"
    : "FULL_PAGE_UNAVAILABLE";
}

export function nextProjectionReadBackoff(
  previousAttempt: number,
  nowMilliseconds: number
): Readonly<{ attempt: number; delayMilliseconds: number; retryAt: string }> {
  if (!Number.isSafeInteger(previousAttempt) || previousAttempt < 0) {
    throw new TypeError("previousAttempt must be a non-negative safe integer");
  }
  if (!Number.isFinite(nowMilliseconds)) {
    throw new TypeError("nowMilliseconds must be finite");
  }
  const attempt = Math.min(previousAttempt + 1, MAX_PROJECTION_BACKOFF_ATTEMPT_V1);
  const delayMilliseconds = runtimeBackoffDelayMillisecondsV1(attempt);
  return Object.freeze({
    attempt,
    delayMilliseconds,
    retryAt: new Date(nowMilliseconds + delayMilliseconds).toISOString()
  });
}
