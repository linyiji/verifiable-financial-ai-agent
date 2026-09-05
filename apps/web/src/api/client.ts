/** Future integration route map only. PRE-INTEGRATION code does not call these URLs. */
export const futureApiRoutes = {
  objectSearch: "/api/objects/search",
  objects: "/api/objects",
  object: (objectId: string) => `/api/objects/${encodeURIComponent(objectId)}`,
  objectFinancials: (objectId: string) => `/api/objects/${encodeURIComponent(objectId)}/financials`,
  objectRuns: (objectId: string) => `/api/objects/${encodeURIComponent(objectId)}/runs`,
  prepareRun: "/api/research-runs/prepare",
  runs: "/api/research-runs",
  run: (runId: string) => `/api/research-runs/${encodeURIComponent(runId)}`,
  runEvents: (runId: string) => `/api/research-runs/${encodeURIComponent(runId)}/events`,
  claims: (runId: string) => `/api/research-runs/${encodeURIComponent(runId)}/claims`,
  claim: (runId: string, claimId: string) => `/api/research-runs/${encodeURIComponent(runId)}/claims/${encodeURIComponent(claimId)}`,
  report: (runId: string) => `/api/research-runs/${encodeURIComponent(runId)}/report`,
  review: (runId: string) => `/api/research-runs/${encodeURIComponent(runId)}/review-view`,
  execution: (runId: string) => `/api/research-runs/${encodeURIComponent(runId)}/execution-view`,
  reportHtml: (runId: string) => `/api/research-runs/${encodeURIComponent(runId)}/report/html`,
  reportPdf: (runId: string) => `/api/research-runs/${encodeURIComponent(runId)}/report/pdf`
} as const;
