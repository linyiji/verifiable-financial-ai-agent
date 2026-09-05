import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Phase4ApiError, Phase4TransportError } from "./api/client";
import { createPhase4Mutation } from "./data/FrontendDataSource";
import { HttpFrontendDataSource } from "./data/HttpFrontendDataSource";
import { SSERuntimeTransport } from "./runtime/SSERuntimeTransport";
import {
  type ConnectionState,
  type ErrorEnvelope,
  type NormalizedObjectIdentity,
  type PreparedResearchDraft,
  type ReleasedFinancialMetricProjectionV1,
  type RunProjection
} from "./types/domain";

const backendOrigin = window.location.port === "4174"
  ? "http://127.0.0.1:61999"
  : "http://127.0.0.1:8010";
const apiBase = `${backendOrigin}/api`;

type Step = "OBJECT" | "GOAL" | "SCHEME" | "CONFIRM";
type Lifecycle = {
  runId: string;
  requestEpoch: number;
  settled: boolean;
  consumed?: { runId: string; requestEpoch: number; revision: number; sequence: number };
  discarded?: { runId: string; requestEpoch: number; revision: number; sequence: number; reason: string };
};

function pathRunId(): string | null {
  const match = /^\/runs\/([^/]+)$/u.exec(window.location.pathname);
  return match ? decodeURIComponent(match[1]) : null;
}

function safeEnvelope(error: unknown, resourceId?: string): ErrorEnvelope | null {
  if (error instanceof Phase4ApiError) return error.envelope;
  const message = error instanceof Phase4TransportError
    ? "The research backend is currently unavailable."
    : "The request could not be completed safely.";
  return {
    schemaVersion: "phase4-error/v1",
    error: {
      code: "TRANSIENT_BACKEND_ERROR",
      message,
      retryable: true,
      recovery: "RETRY",
      requestId: null,
      resource: resourceId ? { type: "research_run", id: resourceId } : null,
      details: {}
    }
  };
}

function initialConnection(runId: string, sequence: number): ConnectionState {
  return { kind: "IDLE", runId, lastSequence: sequence };
}

export function Phase4Application() {
  const source = useMemo(() => new HttpFrontendDataSource({ baseUrl: backendOrigin }), []);
  const transport = useMemo(() => new SSERuntimeTransport({ basePath: apiBase }), []);
  const [objects, setObjects] = useState<readonly NormalizedObjectIdentity[]>([]);
  const [selected, setSelected] = useState<NormalizedObjectIdentity | null>(null);
  const [step, setStep] = useState<Step>("OBJECT");
  const [goal, setGoal] = useState("");
  const [asOf] = useState(() => new Date().toISOString().slice(0, 10));
  const [draft, setDraft] = useState<PreparedResearchDraft | null>(null);
  const [projection, setProjection] = useState<RunProjection | null>(null);
  const [runIds, setRunIds] = useState<readonly string[]>([]);
  const [connection, setConnection] = useState<ConnectionState | null>(null);
  const [error, setError] = useState<ErrorEnvelope | null>(null);
  const [quarantine, setQuarantine] = useState<string | null>(null);
  const [lifecycle, setLifecycle] = useState<Lifecycle | null>(null);
  const [results, setResults] = useState<readonly ReleasedFinancialMetricProjectionV1[] | null>(null);
  const [resultTab, setResultTab] = useState(false);
  const epoch = useRef(0);
  const activeRun = useRef<string | null>(null);
  const subscription = useRef<{ unsubscribe(): void } | null>(null);
  const confirmPending = useRef(false);
  const retryLoad = useRef<(() => void) | null>(null);
  const currentProjection = useRef<RunProjection | null>(null);
  const currentConnection = useRef<ConnectionState | null>(null);

  useEffect(() => { currentProjection.current = projection; }, [projection]);
  useEffect(() => { currentConnection.current = connection; }, [connection]);

  const loadObjects = useCallback(async () => {
    setError(null);
    try {
      const collection = await source.listResearchObjects({ limit: 100 });
      setObjects(collection.items.map((item) => item.object));
    } catch (caught) {
      setObjects([]);
      setError(safeEnvelope(caught));
    }
  }, [source]);

  const loadRun = useCallback((runId: string) => {
    subscription.current?.unsubscribe();
    activeRun.current = runId;
    setError(null);
    setResults(null);
    setResultTab(false);
    const requestEpoch = ++epoch.current;
    setLifecycle((prior) => ({
      runId,
      requestEpoch,
      settled: false,
      consumed: prior?.consumed,
      discarded: prior?.discarded
    }));
    const execute = async () => {
      try {
        const value = await source.getRunProjection(runId);
        if (activeRun.current !== runId || requestEpoch !== epoch.current) {
          setLifecycle((prior) => prior ? ({
            ...prior,
            discarded: {
              runId,
              requestEpoch,
              revision: value.projectionRevision,
              sequence: value.projectionSequence,
              reason: "STALE_RESPONSE"
            }
          }) : prior);
          return;
        }
        setProjection(value);
        setConnection(initialConnection(runId, value.projectionSequence));
        setLifecycle((prior) => ({
          runId,
          requestEpoch,
          settled: true,
          consumed: {
            runId,
            requestEpoch,
            revision: value.projectionRevision,
            sequence: value.projectionSequence
          },
          discarded: prior?.discarded
        }));
        const queryTask = new URLSearchParams(window.location.search).get("task");
        setQuarantine(
          queryTask !== null && !value.tasks.some((task) => task.taskId === queryTask)
            ? "IDENTITY_MISMATCH"
            : null
        );
        const collection = await source.listResearchObjectRuns(value.object.objectId, { limit: 100 });
        if (activeRun.current === runId) setRunIds(collection.items.map((item) => item.runId));
        if (value.terminal.isTerminal) {
          setConnection({
            kind: "TERMINAL",
            runId,
            lastSequence: value.projectionSequence,
            outcome: value.terminal.outcome ?? "FAILURE"
          });
          return;
        }
        window.setTimeout(() => {
          if (activeRun.current !== runId || requestEpoch !== epoch.current) return;
          const refresh = () => loadRun(runId);
          const stream = transport.subscribe(
            runId,
            (event) => {
              if (activeRun.current !== runId) return;
              if (event.projectionRefreshRequired || event.effect === "TERMINAL") {
                window.setTimeout(refresh, 0);
              }
            },
            () => undefined,
            {
              initialSequence: value.projectionSequence,
              authoritativeTaskIds: value.tasks.map((task) => task.taskId),
              onStateChange: (state) => {
                if (activeRun.current === runId) setConnection(state);
              },
              onTerminalAtCursor: () => {
                if (activeRun.current === runId) loadRun(runId);
              }
            }
          );
          subscription.current = stream;
        }, 50);
      } catch (caught) {
        if (activeRun.current !== runId || requestEpoch !== epoch.current) return;
        setProjection(null);
        setLifecycle((prior) => prior ? { ...prior, settled: true } : prior);
        setError(safeEnvelope(caught, runId));
      }
    };
    retryLoad.current = () => loadRun(runId);
    void execute();
  }, [source, transport]);

  const navigateRun = useCallback((runId: string) => {
    window.history.pushState({}, "", `/runs/${encodeURIComponent(runId)}`);
    loadRun(runId);
  }, [loadRun]);

  useEffect(() => {
    const onPop = () => {
      const runId = pathRunId();
      if (runId) loadRun(runId);
      else void loadObjects();
    };
    const onOnline = () => {
      const value = currentProjection.current;
      if (value && activeRun.current === value.run.runId) loadRun(value.run.runId);
    };
    window.addEventListener("popstate", onPop);
    window.addEventListener("online", onOnline);
    const initial = pathRunId();
    if (initial) loadRun(initial);
    else void loadObjects();
    return () => {
      subscription.current?.unsubscribe();
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("online", onOnline);
    };
  }, [loadObjects, loadRun]);

  const prepare = async () => {
    if (!selected || !goal.trim()) return;
    setError(null);
    try {
      const value = await source.prepareResearchRun(createPhase4Mutation({
        researchObjectId: selected.objectId,
        researchGoal: goal,
        asOf,
        preferences: {}
      }));
      setDraft(value);
      setStep("SCHEME");
    } catch (caught) { setError(safeEnvelope(caught)); }
  };

  const confirm = async () => {
    if (!draft || confirmPending.current) return;
    confirmPending.current = true;
    setError(null);
    try {
      const value = await source.confirmResearchRun(createPhase4Mutation({
        draftId: draft.draftId,
        draftVersion: draft.draftVersion,
        draftHash: draft.draftHash,
        researchObjectId: draft.objectId,
        confirmScheme: true,
        expectedGoalId: draft.goal.goalId,
        expectedSchemeId: draft.schemeSnapshot.schemeId
      }));
      navigateRun(value.admission.runId);
    } catch (caught) {
      setError(safeEnvelope(caught));
      confirmPending.current = false;
    }
  };

  const loadResults = async () => {
    if (!projection) return;
    setResultTab(true);
    try {
      const result = await source.getReleasedResult(
        projection.run.runId,
        projection.object.objectId
      );
      setResults(result.metrics);
    } catch (caught) {
      setResults(null);
      setError(safeEnvelope(caught, projection.run.runId));
    }
  };

  if (pathRunId() !== null || projection !== null || error?.error.resource?.type === "research_run") {
    return <main className="app">
      {error && <TypedError error={error} onRetry={() => retryLoad.current?.()} onDismiss={() => setError(null)} />}
      {quarantine && <div className="alert" data-testid="identity-quarantine" data-reason={quarantine}>Requested identity was quarantined.</div>}
      {projection && <Workspace
        projection={projection}
        runIds={runIds}
        connection={connection ?? initialConnection(projection.run.runId, projection.projectionSequence)}
        lifecycle={lifecycle}
        resultTab={resultTab}
        results={results}
        onNavigate={navigateRun}
        onResults={() => void loadResults()}
      />}
    </main>;
  }

  return <main className="app"><section className="panel wizard">
    <div className="steps">Object → Goal → Scheme → Confirm → Run</div>
    {error && <TypedError error={error} onRetry={() => void loadObjects()} onDismiss={() => setError(null)} />}
    {step === "OBJECT" && <>
      <h1>Select Research Object</h1>
      <div className="option-list">{objects.map((object) => <button
        type="button"
        className={`option ${selected?.objectId === object.objectId ? "selected" : ""}`}
        data-testid="research-object-option"
        data-object-id={object.objectId}
        key={object.objectId}
        onClick={() => setSelected(object)}
      ><strong>{object.companyName}</strong><div>{object.symbol} · {object.objectId}</div></button>)}</div>
      <div className="actions"><button type="button" className="primary" data-testid="wizard-next" disabled={!selected} onClick={() => setStep("GOAL")}>Next</button></div>
    </>}
    {step === "GOAL" && <>
      <h1>Research Goal</h1>
      <button type="button" className="secondary" data-testid="full-research" onClick={() => setGoal("Full company research")}>Full Research</button>
      <p><label>Research Goal<textarea className="goal" aria-label="Research Goal" value={goal} onChange={(event) => setGoal(event.target.value)} /></label></p>
      <div className="actions"><button type="button" className="primary" data-testid="wizard-next" disabled={!goal.trim()} onClick={() => void prepare()}>Next</button></div>
    </>}
    {step === "SCHEME" && draft && <>
      <h1>Research Scheme</h1>
      <div className="scheme" data-testid="scheme-preview" data-object-id={draft.objectId} data-goal-id={draft.goal.goalId} data-scheme-id={draft.schemeSnapshot.schemeId} data-draft-id={draft.draftId}>
        <strong>Authoritative scheme preview</strong>
        <p>{draft.schemeSnapshot.researchScope.join(" · ")}</p>
      </div>
      <div className="actions"><button type="button" className="primary" data-testid="wizard-next" onClick={() => setStep("CONFIRM")}>Next</button></div>
    </>}
    {step === "CONFIRM" && draft && <>
      <h1>Confirm Scheme</h1><p>One confirmation creates one Run and automatically starts it.</p>
      <div className="actions"><button type="button" className="primary" data-testid="confirm-run" onClick={() => void confirm()}>Confirm Research</button></div>
    </>}
  </section></main>;
}

function TypedError({ error, onRetry, onDismiss }: { error: ErrorEnvelope; onRetry(): void; onDismiss(): void }) {
  return <div className="alert" role="alert" data-testid="typed-error" data-error-code={error.error.code} data-resource-id={error.error.resource?.id ?? ""}>
    <div>{error.error.message}</div>
    <div className="actions"><button type="button" className="secondary" data-testid="error-retry" onClick={onRetry}>Retry</button><button type="button" className="secondary" data-testid="error-dismiss" onClick={onDismiss}>Dismiss</button></div>
  </div>;
}

function Workspace({ projection, runIds, connection, lifecycle, resultTab, results, onNavigate, onResults }: {
  projection: RunProjection;
  runIds: readonly string[];
  connection: ConnectionState;
  lifecycle: Lifecycle | null;
  resultTab: boolean;
  results: readonly ReleasedFinancialMetricProjectionV1[] | null;
  onNavigate(runId: string): void;
  onResults(): void;
}) {
  const runId = projection.run.runId;
  return <div className="workspace">
    <aside className="panel"><strong>Runs</strong><nav className="run-nav">{runIds.map((id) => <a
      href={`/runs/${encodeURIComponent(id)}`}
      className="run-link"
      data-testid="run-navigation-item"
      data-run-id={id}
      key={id}
      onClick={(event) => { event.preventDefault(); onNavigate(id); }}
    >{id}</a>)}</nav></aside>
    <section className="panel workspace-main" data-testid="run-workspace" data-run-id={runId} data-object-id={projection.object.objectId} data-goal-id={projection.goal.goalId} data-scheme-id={projection.confirmedScheme.schemeId} data-run-status={projection.run.backendStatus} data-run-stage={projection.run.stage} data-projection-revision={projection.projectionRevision} data-projection-sequence={projection.projectionSequence}>
      <h1>{projection.object.companyName} Research Workspace</h1>
      <div className="metadata"><span>{runId}</span><span>{projection.run.backendStatus}</span><span>Graph v{projection.graphVersion}</span></div>
      <div className="connection" role="status" aria-live="polite" data-testid="runtime-connection" data-run-id={runId} data-connection-state={connection.kind} data-last-sequence={connection.lastSequence} data-stale={connection.kind === "BACKOFF" || connection.kind === "RECOVERING" ? "true" : "false"}>Runtime connection: {connection.kind}</div>
      <div role="status" data-testid="projection-lifecycle" data-run-id={lifecycle?.runId ?? runId} data-request-epoch={lifecycle?.requestEpoch ?? 0} data-settled={String(lifecycle?.settled ?? false)} data-consumed-run-id={lifecycle?.consumed?.runId ?? ""} data-consumed-request-epoch={lifecycle?.consumed?.requestEpoch ?? ""} data-consumed-projection-revision={lifecycle?.consumed?.revision ?? ""} data-consumed-projection-sequence={lifecycle?.consumed?.sequence ?? ""} data-last-discarded-run-id={lifecycle?.discarded?.runId ?? ""} data-last-discarded-request-epoch={lifecycle?.discarded?.requestEpoch ?? ""} data-last-discarded-projection-revision={lifecycle?.discarded?.revision ?? ""} data-last-discarded-projection-sequence={lifecycle?.discarded?.sequence ?? ""} data-last-discard-reason={lifecycle?.discarded?.reason ?? ""}>Projection {lifecycle?.settled ? "settled" : "loading"}</div>
      <div className="tabs" role="tablist"><button type="button" role="tab" aria-selected={!resultTab}>Research Path</button><button type="button" role="tab" aria-selected={resultTab} data-testid="result-tab" onClick={onResults}>Results</button></div>
      {!resultTab ? <section data-testid="research-path" data-run-id={runId}>
        <h2>Research Path</h2><div className="task-grid">{projection.tasks.map((task) => <article className="task" key={task.taskId} data-testid="research-task" data-run-id={runId} data-task-id={task.taskId} data-task-status={task.backendStatus} data-task-progress={String(task.progress)} data-parent-task-id={task.parentTaskId ?? ""} data-dependency-ids={JSON.stringify(task.dependencies)}><strong>{task.taskType}</strong><div>{task.backendStatus}</div><div className="muted">{task.taskId}</div></article>)}</div>
      </section> : <section className="metric-list">{results?.map((metric) => <article className="metric" key={metric.metricId} data-testid="released-financial-metric" data-metric-id={metric.metricId} data-run-id={metric.runId} data-canonical-value={metric.canonicalValue}><strong>{metric.name}</strong><span data-testid="canonical-financial-value">{metric.canonicalValue}</span></article>)}</section>}
    </section>
  </div>;
}
