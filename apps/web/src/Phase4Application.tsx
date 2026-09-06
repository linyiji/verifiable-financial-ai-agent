import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Phase4ApiError, Phase4TransportError } from "./api/client";
import type { ProjectionLifecycle } from "./components/ResearchRuntimeWorkspace";
import { createPhase4Mutation } from "./data/FrontendDataSource";
import { HttpFrontendDataSource } from "./data/HttpFrontendDataSource";
import { NewResearchTaskPage, type NewResearchStep } from "./pages/NewResearchTaskPage";
import { ResearchObjectDetailPage } from "./pages/ResearchObjectDetailPage";
import { ResearchObjectsPage } from "./pages/ResearchObjectsPage";
import { ResearchRunPage } from "./pages/ResearchRunPage";
import { ResearchRunsPage } from "./pages/ResearchRunsPage";
import { SSERuntimeTransport } from "./runtime/SSERuntimeTransport";
import {
  createRunRuntimeState,
  reconcileRunRuntimeState,
  reduceRuntimeEvent,
  selectRunProjection,
  type RunRuntimeState
} from "./state/runtimeEventReducer";
import {
  type ConnectionState,
  type ErrorEnvelope,
  type NormalizedObjectIdentity,
  type Phase4ResearchObjectDetail,
  type PreparedResearchDraft,
  type RunHistoryItem,
  type RunProjection
} from "./types/domain";

const configuredBackendOrigin = import.meta.env.VITE_API_BASE_URL?.trim();
const backendOrigin = configuredBackendOrigin || (window.location.port === "4174"
  ? "http://127.0.0.1:61999"
  : "http://127.0.0.1:8010");
const apiBase = `${backendOrigin}/api`;

const ROUTE_CHANGE_EVENT = "phase4-routechange";

type HistoryState =
  | Readonly<{ phase: "LOADING"; selectedRunId: string; items: readonly RunHistoryItem[] }>
  | Readonly<{ phase: "READY"; selectedRunId: string; items: readonly RunHistoryItem[] }>
  | Readonly<{ phase: "UNAVAILABLE"; selectedRunId: string; items: readonly RunHistoryItem[] }>;

type HistoryError = Readonly<{
  code: "HISTORY_UNAVAILABLE_OR_INCOMPATIBLE";
  message: string;
}>;

function pathRunId(): string | null {
  const match = /^\/runs\/([^/]+)$/u.exec(window.location.pathname);
  return match ? decodeURIComponent(match[1]) : null;
}

function pathObjectId(): string | null {
  const match = /^\/objects\/([^/]+)$/u.exec(window.location.pathname);
  return match ? decodeURIComponent(match[1]) : null;
}

type ProductPage = "NEW" | "RUNS" | "OBJECTS" | "OBJECT" | "RUN";

function currentPage(): ProductPage {
  if (pathRunId() !== null) return "RUN";
  if (pathObjectId() !== null) return "OBJECT";
  if (window.location.pathname === "/runs") return "RUNS";
  if (window.location.pathname === "/objects") return "OBJECTS";
  return "NEW";
}

function safeEnvelope(error: unknown, resourceId?: string): ErrorEnvelope | null {
  if (error instanceof Phase4ApiError) return error.envelope;
  const message = error instanceof Phase4TransportError
    ? "研究服务暂时不可用，请稍后重试。"
    : "请求未能安全完成，请重试。";
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
  const [objectDetails, setObjectDetails] = useState<readonly Phase4ResearchObjectDetail[]>([]);
  const [objectsLoading, setObjectsLoading] = useState(false);
  const [runs, setRuns] = useState<readonly RunHistoryItem[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsUnavailable, setRunsUnavailable] = useState(false);
  const [objectDetail, setObjectDetail] = useState<Phase4ResearchObjectDetail | null>(null);
  const [objectRuns, setObjectRuns] = useState<readonly RunHistoryItem[] | null>(null);
  const [objectRunsLoading, setObjectRunsLoading] = useState(false);
  const [objectRunsUnavailable, setObjectRunsUnavailable] = useState(false);
  const [selected, setSelected] = useState<NormalizedObjectIdentity | null>(null);
  const [step, setStep] = useState<NewResearchStep>("OBJECT");
  const [goal, setGoal] = useState("");
  const [asOf] = useState(() => new Date().toISOString().slice(0, 10));
  const [draft, setDraft] = useState<PreparedResearchDraft | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [selectedRunProjection, setSelectedRunProjection] = useState<RunProjection | null>(null);
  const [selectedRunError, setSelectedRunError] = useState<ErrorEnvelope | null>(null);
  const [historyState, setHistoryState] = useState<HistoryState | null>(null);
  const [historyError, setHistoryError] = useState<HistoryError | null>(null);
  const [connection, setConnection] = useState<ConnectionState | null>(null);
  const [error, setError] = useState<ErrorEnvelope | null>(null);
  const [quarantine, setQuarantine] = useState<string | null>(null);
  const [lifecycle, setLifecycle] = useState<ProjectionLifecycle | null>(null);
  const epoch = useRef(0);
  const activeRun = useRef<string | null>(null);
  const subscription = useRef<{ unsubscribe(): void } | null>(null);
  const confirmPending = useRef(false);
  const retryLoad = useRef<(() => void) | null>(null);
  const currentProjection = useRef<RunProjection | null>(null);
  const runtimeState = useRef<RunRuntimeState | null>(null);

  useEffect(() => { currentProjection.current = selectedRunProjection; }, [selectedRunProjection]);

  const loadObjects = useCallback(async () => {
    setError(null);
    setObjectsLoading(true);
    try {
      const collection = await source.listResearchObjects({ limit: 100 });
      setObjectDetails(collection.items);
      setObjects(collection.items.map((item) => item.object));
    } catch (caught) {
      setObjectDetails([]);
      setObjects([]);
      setError(safeEnvelope(caught));
    } finally {
      setObjectsLoading(false);
    }
  }, [source]);

  const loadRuns = useCallback(async () => {
    setRunsLoading(true);
    setRunsUnavailable(false);
    try {
      const collection = await source.listResearchRuns({ limit: 100 });
      setRuns(collection.items);
    } catch {
      setRuns([]);
      setRunsUnavailable(true);
    } finally {
      setRunsLoading(false);
    }
  }, [source]);

  const loadObject = useCallback(async (objectId: string) => {
    setObjectDetail((current) => current?.object.objectId === objectId ? current : null);
    setObjectRuns(null);
    setObjectRunsLoading(true);
    setObjectRunsUnavailable(false);
    try {
      const detail = await source.getResearchObject(objectId);
      if (pathObjectId() !== objectId) return;
      setObjectDetail(detail);
      try {
        const collection = await source.listResearchObjectRuns(objectId, { limit: 100 });
        if (pathObjectId() !== objectId) return;
        setObjectRuns(collection.items);
      } catch {
        if (pathObjectId() !== objectId) return;
        setObjectRuns(null);
        setObjectRunsUnavailable(true);
      }
    } catch (caught) {
      if (pathObjectId() !== objectId) return;
      setObjectDetail(null);
      setError(safeEnvelope(caught, objectId));
    } finally {
      if (pathObjectId() === objectId) setObjectRunsLoading(false);
    }
  }, [source]);

  const loadRun = useCallback((runId: string) => {
    subscription.current?.unsubscribe();
    if (runtimeState.current?.runId !== runId) runtimeState.current = null;
    activeRun.current = runId;
    setError(null);
    setSelectedRunError(null);
    setSelectedRunProjection((current) => current?.run.runId === runId ? current : null);
    setHistoryState({ phase: "LOADING", selectedRunId: runId, items: [] });
    setHistoryError(null);
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
        const priorRuntime = runtimeState.current;
        const initializedRuntime = priorRuntime?.runId === runId
          ? reconcileRunRuntimeState(priorRuntime, value)
          : createRunRuntimeState(value, {
              runId,
              objectId: value.object.objectId,
              goalId: value.goal.goalId,
              schemeId: value.confirmedScheme.schemeId,
              plannedGraphId: value.plannedGraph.graphId,
              actualGraphId: value.actualGraph?.graphId ?? null,
              canonicalRecordId: value.execution.canonicalRecordId
            });
        runtimeState.current = initializedRuntime;
        setSelectedRunProjection(selectRunProjection(initializedRuntime));
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
        void source.listResearchObjectRuns(value.object.objectId, { limit: 100 })
          .then((collection) => {
            if (activeRun.current !== runId || requestEpoch !== epoch.current) return;
            setHistoryState({ phase: "READY", selectedRunId: runId, items: collection.items });
            setHistoryError(null);
          })
          .catch(() => {
            if (activeRun.current !== runId || requestEpoch !== epoch.current) return;
            setHistoryState({ phase: "UNAVAILABLE", selectedRunId: runId, items: [] });
            setHistoryError({
              code: "HISTORY_UNAVAILABLE_OR_INCOMPATIBLE",
              message: "部分历史研究暂不可用。"
            });
          });
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
          const refresh = () => {
            if (activeRun.current === runId && requestEpoch === epoch.current) loadRun(runId);
          };
          const stream = transport.subscribe(
            runId,
            (event) => {
              if (activeRun.current !== runId) return;
              const current = runtimeState.current;
              if (current === null || current.runId !== runId) {
                window.setTimeout(refresh, 0);
                return;
              }
              const next = reduceRuntimeEvent(current, event);
              runtimeState.current = next;
              setSelectedRunProjection(selectRunProjection(next));
              if (next.stale || event.projectionRefreshRequired || event.effect === "TERMINAL") {
                window.setTimeout(refresh, 0);
              }
            },
            () => undefined,
            {
              initialSequence: value.projectionSequence,
              authoritativeTaskIds: value.tasks.map((task) => task.taskId),
              onStateChange: (state) => {
                if (activeRun.current !== runId || requestEpoch !== epoch.current) return;
                setConnection(state);
                if (state.kind === "BACKOFF") window.setTimeout(refresh, 500);
              },
              onTerminalAtCursor: () => {
                if (activeRun.current === runId && requestEpoch === epoch.current) loadRun(runId);
              }
            }
          );
          subscription.current = stream;
        }, 50);
      } catch (caught) {
        if (activeRun.current !== runId || requestEpoch !== epoch.current) return;
        runtimeState.current = null;
        setSelectedRunProjection(null);
        setSelectedRunError(safeEnvelope(caught, runId));
        setHistoryState({ phase: "UNAVAILABLE", selectedRunId: runId, items: [] });
        setHistoryError(null);
        setLifecycle((prior) => prior ? { ...prior, settled: true } : prior);
      }
    };
    retryLoad.current = () => loadRun(runId);
    void execute();
  }, [source, transport]);

  const navigateRun = useCallback((runId: string) => {
    window.history.pushState({}, "", `/runs/${encodeURIComponent(runId)}`);
    window.dispatchEvent(new Event(ROUTE_CHANGE_EVENT));
  }, []);

  const navigatePath = useCallback((path: string) => {
    const current = `${window.location.pathname}${window.location.search}`;
    if (current === path) return;
    window.history.pushState({}, "", path);
    window.dispatchEvent(new Event(ROUTE_CHANGE_EVENT));
  }, []);

  useEffect(() => {
    const onRoute = () => {
      const runId = pathRunId();
      if (runId) {
        loadRun(runId);
        return;
      }
      subscription.current?.unsubscribe();
      subscription.current = null;
      activeRun.current = null;
      runtimeState.current = null;
      epoch.current += 1;
      setSelectedRunProjection(null);
      setSelectedRunError(null);
      setConnection(null);
      setQuarantine(null);
      setLifecycle(null);

      const page = currentPage();
      if (page === "RUNS") {
        void loadObjects();
        void loadRuns();
      } else if (page === "OBJECTS") {
        void loadObjects();
      } else if (page === "OBJECT") {
        const objectId = pathObjectId();
        if (objectId) void loadObject(objectId);
      } else {
        const requestedObject = new URLSearchParams(window.location.search).get("object");
        if (requestedObject === null) {
          setSelected(null);
          setGoal("");
          setDraft(null);
          setStep("OBJECT");
        } else {
          setStep("GOAL");
        }
        setPreparing(false);
        setConfirming(false);
        setDraft(null);
        confirmPending.current = false;
        void loadObjects();
      }
    };
    const onOnline = () => {
      const value = currentProjection.current;
      if (value && activeRun.current === value.run.runId) loadRun(value.run.runId);
    };
    window.addEventListener("popstate", onRoute);
    window.addEventListener(ROUTE_CHANGE_EVENT, onRoute);
    window.addEventListener("online", onOnline);
    onRoute();
    return () => {
      subscription.current?.unsubscribe();
      window.removeEventListener("popstate", onRoute);
      window.removeEventListener(ROUTE_CHANGE_EVENT, onRoute);
      window.removeEventListener("online", onOnline);
    };
  }, [loadObject, loadObjects, loadRun, loadRuns]);

  useEffect(() => {
    if (currentPage() !== "NEW") return;
    const requestedObject = new URLSearchParams(window.location.search).get("object");
    if (requestedObject === null) return;
    const match = objects.find((object) => object.objectId === requestedObject);
    if (match) setSelected(match);
  }, [objects]);

  const prepare = async () => {
    if (!selected || !goal.trim()) return;
    setError(null);
    setPreparing(true);
    try {
      const value = await source.prepareResearchRun(createPhase4Mutation({
        researchObjectId: selected.objectId,
        researchGoal: goal,
        asOf,
        preferences: {}
      }));
      setDraft(value);
      setStep("SCHEME");
    } catch (caught) {
      setError(safeEnvelope(caught));
    } finally {
      setPreparing(false);
    }
  };

  const confirm = async () => {
    if (!draft || confirmPending.current) return;
    confirmPending.current = true;
    setConfirming(true);
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
      setConfirming(false);
    }
  };

  const page = currentPage();

  if (page === "RUN") {
    return <div className="app-content">
      {selectedRunError && <TypedError error={selectedRunError} onRetry={() => retryLoad.current?.()} onDismiss={() => setSelectedRunError(null)} />}
      {error && <TypedError error={error} onRetry={() => retryLoad.current?.()} onDismiss={() => setError(null)} />}
      {quarantine && <div className="alert" data-testid="identity-quarantine" data-reason={quarantine}>请求的 Task 不属于当前 Research Run，已停止显示该 Task。</div>}
      {selectedRunProjection && <ResearchRunPage
        projection={selectedRunProjection}
        connection={connection ?? initialConnection(selectedRunProjection.run.runId, selectedRunProjection.projectionSequence)}
        lifecycle={lifecycle}
        reportBaseUrl={backendOrigin}
      />}
      {!selectedRunProjection && !selectedRunError && <div className="card app-loading" role="status"><div className="spinner" aria-hidden="true" /><span>正在载入当前 Research Run…</span></div>}
    </div>;
  }

  if (page === "RUNS") {
    return <div className="app-content">
      {runsUnavailable && <CollectionUnavailable title="部分研究记录暂不可用" copy="当前无法安全载入历史 Research Run；不会使用其他记录替代。" />}
      <ResearchRunsPage
        runs={runs}
        objectCount={objectDetails.length}
        loading={runsLoading}
        unavailable={runsUnavailable}
        onCreate={() => navigatePath("/")}
        onOpen={(runId) => navigateRun(runId)}
      />
    </div>;
  }

  if (page === "OBJECTS") {
    return <div className="app-content">
      {error && <TypedError error={error} onRetry={() => void loadObjects()} onDismiss={() => setError(null)} />}
      <ResearchObjectsPage
        objects={objectDetails}
        loading={objectsLoading}
        onCreate={() => navigatePath("/")}
        onOpen={(objectId) => navigatePath(`/objects/${encodeURIComponent(objectId)}`)}
      />
    </div>;
  }

  if (page === "OBJECT") {
    return <div className="app-content">
      {error && <TypedError error={error} onRetry={() => { const objectId = pathObjectId(); if (objectId) void loadObject(objectId); }} onDismiss={() => setError(null)} />}
      {objectDetail
        ? <ResearchObjectDetailPage
            detail={objectDetail}
            runs={objectRuns}
            runsLoading={objectRunsLoading}
            runsUnavailable={objectRunsUnavailable}
            onBack={() => navigatePath("/objects")}
            onBeginResearch={(objectId) => navigatePath(`/?object=${encodeURIComponent(objectId)}`)}
            onOpenRun={(runId) => navigateRun(runId)}
          />
        : !error && <div className="card app-loading" role="status"><div className="spinner" aria-hidden="true" /><span>正在载入 Research Object…</span></div>}
    </div>;
  }

  return <div className="app-content">
    {error && <TypedError error={error} onRetry={() => void loadObjects()} onDismiss={() => setError(null)} />}
    <NewResearchTaskPage
      step={step}
      objects={objects}
      selected={selected}
      goal={goal}
      asOf={asOf}
      draft={draft}
      preparing={preparing}
      confirming={confirming}
      onSelectObject={setSelected}
      onGoalChange={setGoal}
      onStepChange={setStep}
      onPrepare={() => void prepare()}
      onConfirm={() => void confirm()}
    />
  </div>;
}

function TypedError({ error, onRetry, onDismiss }: { error: ErrorEnvelope; onRetry(): void; onDismiss(): void }) {
  return <div className="alert" role="alert" data-testid="typed-error" data-error-code={error.error.code} data-resource-id={error.error.resource?.id ?? ""}>
    <div>{error.error.retryable ? "研究服务暂时不可用，请稍后重试。" : "当前内容暂不可用。"}</div>
    <div className="actions"><button type="button" className="secondary" data-testid="error-retry" onClick={onRetry}>重试</button><button type="button" className="secondary" data-testid="error-dismiss" onClick={onDismiss}>关闭</button></div>
  </div>;
}

function CollectionUnavailable({ title, copy }: { readonly title: string; readonly copy: string }) {
  return <div className="collection-unavailable" role="status"><strong>{title}</strong><span>{copy}</span></div>;
}
