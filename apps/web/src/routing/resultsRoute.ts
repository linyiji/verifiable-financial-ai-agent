export const RESULTS_SURFACES = ["report", "review", "execution"] as const;

export type ResultsSurfaceRoute = typeof RESULTS_SURFACES[number];

export interface ParsedResultsRoute {
  readonly runId: string;
  readonly surface: ResultsSurfaceRoute;
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

export function resultsPath(runId: string, surface: ResultsSurfaceRoute): string {
  return `/runs/${encodeURIComponent(runId)}/results/${surface}`;
}

export function runPath(runId: string): string {
  return `/runs/${encodeURIComponent(runId)}`;
}
