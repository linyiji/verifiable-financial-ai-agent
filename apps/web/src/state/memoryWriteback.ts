import type { RunProjection } from "../types/domain";

/** Historical reads are never a Memory write trigger. Only a release observed
 * on an already-active, nonterminal Run may initiate the explicit write path. */
export function isObservedIncrementalRelease(previous: RunProjection | null, current: RunProjection | null): boolean {
  return Boolean(previous && current
    && previous.run.runId === current.run.runId
    && previous.object.objectId === current.object.objectId
    && !previous.terminal.isTerminal
    && current.run.backendStatus === "RELEASED"
    && current.confirmedScheme.incrementalContext);
}
