export const RESULTS_SURFACES = ["report", "review", "execution"] as const;

export type ResultsSurfaceRoute = typeof RESULTS_SURFACES[number];

export interface ParsedResultsRoute {
  readonly runId: string;
  readonly surface: ResultsSurfaceRoute;
}

export interface ReportFocus {
  readonly runId: string;
  readonly anchor: string;
}

export interface ReviewFocus {
  readonly runId: string;
  readonly reviewId: string;
  readonly checkCode: string;
  readonly subjectRefs: readonly string[];
  readonly returnAnchor: string | null;
}

export interface ExecutionFocus {
  readonly runId: string;
  readonly actorId: string;
  readonly outputId: string | null;
  readonly eventId: string | null;
  readonly returnAnchor: string | null;
}

export type ResultsFocus = ReportFocus | ReviewFocus | ExecutionFocus | null;

const safeFocusValue = (value: string | null): string | null => {
  if (value === null || value.length === 0 || value.length > 240 || /[\r\n]/u.test(value)) return null;
  return value;
};

export function parseResultsFocus(runId: string, surface: ResultsSurfaceRoute, search: string): ResultsFocus {
  const query = new URLSearchParams(search);
  const returnAnchor = safeFocusValue(query.get("return_anchor"));
  if (surface === "report") {
    const anchor = safeFocusValue(query.get("anchor"));
    return anchor === null ? null : { runId, anchor };
  }
  if (surface === "review") {
    const reviewId = safeFocusValue(query.get("review"));
    const checkCode = safeFocusValue(query.get("check"));
    const subjectRefs = query.getAll("subject").map(safeFocusValue);
    if (reviewId === null || checkCode === null || subjectRefs.length === 0 || subjectRefs.some((item) => item === null)) return null;
    const refs = subjectRefs as string[];
    if (new Set(refs).size !== refs.length || refs.some((item, index) => item !== [...refs].sort()[index])) return null;
    return { runId, reviewId, checkCode, subjectRefs: refs, returnAnchor };
  }
  const actorId = safeFocusValue(query.get("actor"));
  const outputId = safeFocusValue(query.get("output"));
  const eventId = safeFocusValue(query.get("event"));
  if (actorId === null || (outputId === null) !== (eventId === null)) return null;
  return { runId, actorId, outputId, eventId, returnAnchor };
}

export function parseResultsRoute(pathname: string): ParsedResultsRoute | null {
  const match = /^\/runs\/([^/]+)\/results\/(report|review|execution)$/u.exec(pathname);
  if (!match) return null;
  try {
    const runId = decodeURIComponent(match[1]);
    return runId.length > 0 ? { runId, surface: match[2] as ResultsSurfaceRoute } : null;
  } catch {
    return null;
  }
}

export function resultsPath(
  runId: string,
  surface: ResultsSurfaceRoute,
  focus?: ResultsFocus
): string {
  const path = `/runs/${encodeURIComponent(runId)}/results/${surface}`;
  if (focus === undefined || focus === null) return path;
  if (focus.runId !== runId) return path;
  const query = new URLSearchParams();
  if (surface === "report" && "anchor" in focus) query.set("anchor", focus.anchor);
  if (surface === "review" && "reviewId" in focus) {
    query.set("review", focus.reviewId);
    query.set("check", focus.checkCode);
    for (const ref of [...focus.subjectRefs].sort()) query.append("subject", ref);
    if (focus.returnAnchor !== null) query.set("return_anchor", focus.returnAnchor);
  }
  if (surface === "execution" && "actorId" in focus) {
    query.set("actor", focus.actorId);
    if (focus.outputId !== null && focus.eventId !== null) {
      query.set("output", focus.outputId);
      query.set("event", focus.eventId);
    }
    if (focus.returnAnchor !== null) query.set("return_anchor", focus.returnAnchor);
  }
  const suffix = query.toString();
  return suffix.length === 0 ? path : `${path}?${suffix}`;
}

export const RUN_STAGES = ["plan", "research", "review", "report", "complete"] as const;
export type RunStageRoute = typeof RUN_STAGES[number];

export function parseRunStage(search: string): RunStageRoute {
  const stage = new URLSearchParams(search).get("stage");
  return RUN_STAGES.includes(stage as RunStageRoute) ? stage as RunStageRoute : "research";
}

export function runPath(runId: string, stage: RunStageRoute = "research"): string {
  return `/runs/${encodeURIComponent(runId)}?stage=${stage}`;
}
