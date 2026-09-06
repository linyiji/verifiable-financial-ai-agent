import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { Phase4FrontendDataSource } from "../data/FrontendDataSource";
import { InteractiveResearchReport } from "../components/results/InteractiveResearchReport";
import { executionFocusMatches, reportBundleMatches, selectorMatches } from "../components/results/reportModel";
import { RESULTS_SURFACES, parseResultsFocus, resultsPath, runPath, type ResultsFocus, type ResultsSurfaceRoute } from "../routing/resultsRoute";
import type {
  ExecutionRecordSurfaceV1,
  FinancialReviewSurfaceV1,
  Phase4ResearchObjectDetail,
  ReleasedResultProjectionV1,
  ReportArtifactGroupV1,
  ReportSurfaceV1,
  ResultsSurfaceStatus,
  ResultsWorkspaceV1
} from "../types/domain";

interface ResultsWorkspacePageProps {
  readonly source: Phase4FrontendDataSource;
  readonly backendOrigin: string;
  readonly runId: string;
  readonly surface: ResultsSurfaceRoute;
  readonly onNavigate: (path: string) => void;
  readonly onReplace: (path: string) => void;
}

type Loadable<T> =
  | Readonly<{ status: "LOADING"; value: null }>
  | Readonly<{ status: "READY"; value: T }>
  | Readonly<{ status: "ERROR"; value: null }>;

type SurfacePayload = ReportSurfaceV1 | FinancialReviewSurfaceV1 | ExecutionRecordSurfaceV1;
type ReportSupplement = Readonly<{
  result: ReleasedResultProjectionV1;
  artifacts: ReportArtifactGroupV1;
  review: FinancialReviewSurfaceV1;
}>;

const SURFACE_META: Readonly<Record<ResultsSurfaceRoute, Readonly<{ label: string; eyebrow: string; description: string }>>> = {
  report: {
    label: "A · 研究报告",
    eyebrow: "A · REPORT",
    description: "查看本次 Research Run 已生成并释放的公司研究报告。"
  },
  review: {
    label: "B · 财务复核",
    eyebrow: "B · FINANCIAL REVIEW",
    description: "查看本次 Research Run 的财务复核结论与检查总量。"
  },
  execution: {
    label: "C · 执行记录",
    eyebrow: "C · EXECUTION RECORD",
    description: "查看本次 Research Run 可观察的执行参与者与记录汇总。"
  }
};

const RUN_STATUS_LABELS: Readonly<Record<ResultsWorkspaceV1["runStatus"], string>> = {
  DRAFT: "草稿",
  SCHEME_GENERATING: "方案生成中",
  AWAITING_CONFIRMATION: "等待确认",
  PLANNING: "规划中",
  RUNNING: "研究中",
  REVIEW: "复核中",
  PROVING: "验证中",
  RELEASED: "已完成",
  FAILED: "失败",
  CANCELLED: "已取消"
};

const initialLoad = <T,>(): Loadable<T> => ({ status: "LOADING", value: null });

function availabilityFor(root: ResultsWorkspaceV1, surface: ResultsSurfaceRoute) {
  if (surface === "report") return root.reportSurface.availability;
  if (surface === "review") return root.reviewSurface.availability;
  return root.executionSurface.availability;
}

function availabilityLabel(status: ResultsSurfaceStatus): string {
  if (status === "READY") return "已就绪";
  if (status === "PARTIAL") return "部分可用";
  return "暂不可用";
}

function availabilityClass(status: ResultsSurfaceStatus): string {
  if (status === "READY") return "green";
  if (status === "PARTIAL") return "amber";
  return "neutral";
}

function payloadMatchesSurface(payload: SurfacePayload, surface: ResultsSurfaceRoute): boolean {
  if (surface === "report") return payload.schemaVersion === "phase4.5-report-surface/v1";
  if (surface === "review") return payload.schemaVersion === "phase4.5-financial-review-surface/v1";
  return payload.schemaVersion === "phase4.5-execution-record-surface/v1";
}

export function ResultsWorkspacePage({ source, backendOrigin, runId, surface, onNavigate, onReplace }: ResultsWorkspacePageProps) {
  const [root, setRoot] = useState<Loadable<ResultsWorkspaceV1>>(initialLoad);
  const [object, setObject] = useState<Loadable<Phase4ResearchObjectDetail>>(initialLoad);
  const [payload, setPayload] = useState<Loadable<SurfacePayload>>(initialLoad);
  const [reportSupplement, setReportSupplement] = useState<Loadable<ReportSupplement>>(initialLoad);
  const [retryRevision, setRetryRevision] = useState(0);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    setRoot(initialLoad());
    setObject(initialLoad());
    setPayload(initialLoad());
    void source.getResultsWorkspace(runId, undefined, { signal: controller.signal })
      .then(async (workspace) => {
        if (!current) return;
        setRoot({ status: "READY", value: workspace });
        try {
          const detail = await source.getResearchObject(workspace.objectId, { signal: controller.signal });
          if (current) setObject({ status: "READY", value: detail });
        } catch {
          if (current) setObject({ status: "ERROR", value: null });
        }
      })
      .catch(() => {
        if (current) setRoot({ status: "ERROR", value: null });
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [source, runId, retryRevision]);

  useEffect(() => {
    if (root.status !== "READY") return;
    const availability = availabilityFor(root.value, surface);
    if (availability.status === "UNAVAILABLE") {
      setPayload({ status: "READY", value: null as unknown as SurfacePayload });
      return;
    }
    const controller = new AbortController();
    let current = true;
    setPayload(initialLoad());
    const request = surface === "report"
      ? source.getReportSurface(runId, root.value.objectId, { signal: controller.signal })
      : surface === "review"
        ? source.getFinancialReviewSurface(runId, root.value.objectId, { signal: controller.signal })
        : source.getExecutionRecordSurface(runId, root.value.objectId, { signal: controller.signal });
    void request
      .then((value) => {
        if (current) setPayload({ status: "READY", value });
      })
      .catch(() => {
        if (current) setPayload({ status: "ERROR", value: null });
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [source, runId, surface, root]);

  useEffect(() => {
    if (root.status !== "READY" || surface !== "report") return;
    const controller = new AbortController();
    let current = true;
    setReportSupplement(initialLoad());
    void Promise.all([
      source.getReleasedResult(runId, root.value.objectId, { signal: controller.signal }),
      source.getReportArtifacts(runId, root.value.objectId, { signal: controller.signal }),
      source.getFinancialReviewSurface(runId, root.value.objectId, { signal: controller.signal })
    ]).then(([result, artifacts, review]) => {
      if (current) setReportSupplement({ status: "READY", value: { result, artifacts, review } });
    }).catch(() => {
      if (current) setReportSupplement({ status: "ERROR", value: null });
    });
    return () => {
      current = false;
      controller.abort();
    };
  }, [source, runId, surface, root, retryRevision]);

  const navigateSurface = (next: ResultsSurfaceRoute) => {
    if (next === surface) return;
    if (root.status === "READY" && availabilityFor(root.value, next).status === "UNAVAILABLE") return;
    onReplace(resultsPath(runId, next));
  };

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | null = null;
    const availableIndexes = RESULTS_SURFACES
      .map((item, itemIndex) => root.status === "READY" && availabilityFor(root.value, item).status !== "UNAVAILABLE" ? itemIndex : -1)
      .filter((itemIndex) => itemIndex >= 0);
    if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = availableIndexes.find((itemIndex) => itemIndex > index) ?? availableIndexes[0] ?? null;
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = [...availableIndexes].reverse().find((itemIndex) => itemIndex < index) ?? availableIndexes.at(-1) ?? null;
    if (event.key === "Home") nextIndex = availableIndexes[0] ?? null;
    if (event.key === "End") nextIndex = availableIndexes.at(-1) ?? null;
    if (nextIndex === null) return;
    event.preventDefault();
    const next = RESULTS_SURFACES[nextIndex];
    tabRefs.current[nextIndex]?.focus();
    navigateSurface(next);
  };

  if (root.status === "LOADING") {
    return <section className="results-shell" data-testid="results-root-loading" data-run-id={runId}>
      <div className="card app-loading" role="status"><div className="spinner" aria-hidden="true" /><span>正在载入此 Research Run 的结果工作区…</span></div>
    </section>;
  }

  if (root.status === "ERROR") {
    return <section className="results-shell" data-testid="results-root-error" data-run-id={runId}>
      <div className="results-error card" role="alert"><strong>结果工作区暂时无法载入</strong><p>系统不会改用最新或其他 Research Run。请重试当前 Run。</p><button type="button" className="btn primary" onClick={() => setRetryRevision((value) => value + 1)}>重试当前 Run</button></div>
    </section>;
  }

  if (object.status === "LOADING") {
    return <section className="results-shell" data-testid="results-context-loading" data-run-id={runId}>
      <div className="card app-loading" role="status"><div className="spinner" aria-hidden="true" /><span>正在载入此 Research Run 的对象身份…</span></div>
    </section>;
  }

  if (object.status === "ERROR") {
    return <section className="results-shell" data-testid="results-context-error" data-run-id={runId}>
      <div className="results-error card" role="alert"><strong>结果对象身份暂时无法载入</strong><p>为避免错误归属，系统已停止呈现此 Run 的结果内容。</p><button type="button" className="btn primary" onClick={() => setRetryRevision((value) => value + 1)}>重试当前 Run</button></div>
    </section>;
  }

  const workspace = root.value;
  const availability = availabilityFor(workspace, surface);
  const companyName = object.value.object.companyName;
  const symbol = object.value.object.symbol;
  const meta = SURFACE_META[surface];
  const focus = parseResultsFocus(surface, window.location.search);

  return <section
    className="results-shell"
    data-testid="results-workspace"
    data-run-id={workspace.runId}
    data-object-id={workspace.objectId}
    data-results-surface={surface}
    aria-labelledby="results-title"
  >
    <div className="result-top">
      <div>
        <button type="button" className="breadcrumb breadcrumb-button" onClick={() => onNavigate(runPath(runId))}>Research / Run / 研究结果</button>
        <div className="results-title-line"><div className="company-logo" aria-hidden="true">{symbol.slice(0, 3).toUpperCase()}</div><div><h1 id="results-title">{companyName} · 研究结果</h1><p>{symbol} · 截至 {workspace.asOf}</p></div></div>
      </div>
      <div className="results-status"><span className="badge green"><span className="dot" />{RUN_STATUS_LABELS[workspace.runStatus]}</span><button type="button" className="btn" onClick={() => onNavigate(runPath(runId))}>返回 Research Run</button></div>
    </div>

    <dl className="results-identity" aria-label="结果工作区身份">
      <div><dt>Run ID</dt><dd>{workspace.runId}</dd></div>
      <div><dt>Object ID</dt><dd>{workspace.objectId}</dd></div>
      <div><dt>As-of</dt><dd>{workspace.asOf}</dd></div>
    </dl>

    <div className="result-tabs" role="tablist" aria-label="研究结果视图">
      {RESULTS_SURFACES.map((item, index) => {
        const itemAvailability = availabilityFor(workspace, item);
        const selected = item === surface;
        return <button
          key={item}
          ref={(node) => { tabRefs.current[index] = node; }}
          id={`results-tab-${item}`}
          type="button"
          role="tab"
          className={`result-tab ${selected ? "active" : ""} ${itemAvailability.status === "UNAVAILABLE" ? "unavailable" : ""}`}
          aria-selected={selected}
          aria-controls={`results-panel-${item}`}
          aria-disabled={itemAvailability.status === "UNAVAILABLE"}
          tabIndex={selected ? 0 : -1}
          onClick={() => navigateSurface(item)}
          onKeyDown={(event) => onTabKeyDown(event, index)}
        ><span>{SURFACE_META[item].label}</span><small>{availabilityLabel(itemAvailability.status)}</small></button>;
      })}
    </div>

    <section
      className="card result-pane"
      id={`results-panel-${surface}`}
      role="tabpanel"
      tabIndex={0}
      aria-labelledby={`results-tab-${surface}`}
    >
      <header className="result-pane-head"><div><span>{meta.eyebrow}</span><h2>{meta.label.slice(4)}</h2><p>{meta.description}</p></div><span className={`badge ${availabilityClass(availability.status)}`}>{availabilityLabel(availability.status)}</span></header>
      {availability.status === "UNAVAILABLE"
        ? <UnavailableSurface reasonCode={availability.reasonCode} />
        : payload.status === "LOADING"
          ? <div className="result-surface-state" role="status"><div className="spinner" aria-hidden="true" /><span>正在载入当前视图…</span></div>
          : payload.status === "ERROR"
            ? <div className="result-surface-state error" role="alert"><strong>当前视图暂时无法载入</strong><span>已保留此 Run 身份；不会显示其他运行的数据。</span><button type="button" className="btn sm" onClick={() => setRetryRevision((value) => value + 1)}>重试</button></div>
            : !payloadMatchesSurface(payload.value, surface)
              ? <div className="result-surface-state" role="status"><div className="spinner" aria-hidden="true" /><span>正在切换当前视图…</span></div>
              : surface === "report" && reportSupplement.status === "LOADING"
                ? <div className="result-surface-state" role="status"><div className="spinner" aria-hidden="true" /><span>正在装配结构化报告…</span></div>
                : surface === "report" && reportSupplement.status === "ERROR"
                  ? <div className="result-surface-state error" role="alert"><strong>报告结构化内容暂时无法载入</strong><span>未使用 HTML 解析或其他 Run 数据作为替代。</span><button type="button" className="btn sm" onClick={() => setRetryRevision((value) => value + 1)}>重试</button></div>
                  : <SurfaceHost surface={surface} payload={payload.value} supplement={reportSupplement.status === "READY" ? reportSupplement.value : null} backendOrigin={backendOrigin} focus={focus} runId={runId} onNavigate={onNavigate} onReplace={onReplace} />}
    </section>
  </section>;
}

function UnavailableSurface({ reasonCode }: { readonly reasonCode: string | null }) {
  return <div className="result-surface-state unavailable" role="status"><strong>此结果视图暂不可用</strong><span>当前 Research Run 未提供可安全呈现的该类结果。</span>{reasonCode && <code>{reasonCode}</code>}</div>;
}

function SurfaceHost({ surface, payload, supplement, backendOrigin, focus, runId, onNavigate, onReplace }: {
  readonly surface: ResultsSurfaceRoute;
  readonly payload: SurfacePayload;
  readonly supplement: ReportSupplement | null;
  readonly backendOrigin: string;
  readonly focus: ResultsFocus;
  readonly runId: string;
  readonly onNavigate: (path: string) => void;
  readonly onReplace: (path: string) => void;
}) {
  if (surface === "report") {
    const report = payload as ReportSurfaceV1;
    if (supplement === null) return null;
    if (!reportBundleMatches(report, supplement.result, supplement.artifacts, supplement.review)) {
      return <div className="result-surface-state unavailable" role="alert"><strong>报告身份闭包不一致</strong><span>系统已停止组合这些结果；未尝试跨 Run 回退。</span></div>;
    }
    const requestedAnchor = focus !== null && "anchor" in focus ? focus.anchor : null;
    const preserveReportAnchor = (anchor: string) => onReplace(resultsPath(runId, "report", { anchor }));
    return <InteractiveResearchReport report={report} result={supplement.result} artifacts={supplement.artifacts} review={supplement.review} backendOrigin={backendOrigin} requestedAnchor={requestedAnchor}
      onOpenExecution={(contribution) => {
        if (contribution.executionEventId === null) return;
        preserveReportAnchor(contribution.reportAnchor);
        onNavigate(resultsPath(runId, "execution", {
          actorId: contribution.actorId,
          outputId: contribution.agentOutputId,
          eventId: contribution.executionEventId,
          returnAnchor: contribution.reportAnchor
        }));
      }}
      onOpenReview={(selector) => {
        preserveReportAnchor(report.anchors[0]?.anchor ?? "metric-revenue-growth");
        onNavigate(resultsPath(runId, "review", {
          reviewId: selector.reviewId,
          checkCode: selector.checkCode,
          subjectRefs: selector.subjectRefs,
          returnAnchor: report.anchors[0]?.anchor ?? null
        }));
      }} />;
  }
  if (surface === "review") {
    const review = payload as FinancialReviewSurfaceV1;
    const verdict = review.verdict === "PASS" ? "复核通过" : review.verdict === "REVIEW" ? "需要复核" : "已阻断";
    const requested = focus !== null && "reviewId" in focus ? focus : null;
    const exact = requested === null ? null : review.checks.find((check) => selectorMatches(check.selector, {
      reviewId: requested.reviewId, checkCode: requested.checkCode, subjectRefs: requested.subjectRefs
    })) ?? null;
    return <div className="result-product-host" data-testid="review-product-host"><div className="result-host-copy"><span>复核结论</span><h3>{verdict}</h3><p>{exact === null ? "选择报告中的可复核指标，可定位到精确 scoped selector。" : "已从报告定位到同一 Released Run 的精确复核检查。"}</p>{exact !== null && <div className="focus-receipt" data-testid="review-exact-focus"><span>{exact.selector.checkCode} · {exact.status}</span><code>{exact.selector.reviewId}</code>{exact.selector.subjectRefs.map((ref) => <code key={ref}>{ref}</code>)}</div>}{requested !== null && exact === null && <div className="focus-receipt invalid">请求的复核定位与此 Run 不匹配；未展示近似结果。</div>}</div><div className="result-host-facts single"><div><span>检查总量</span><strong>{review.checks.length}</strong></div></div>{requested?.returnAnchor && <button type="button" className="btn" onClick={() => onNavigate(resultsPath(runId, "report", { anchor: requested.returnAnchor! }))}>返回报告位置</button>}</div>;
  }
  const execution = payload as ExecutionRecordSurfaceV1;
  const eventCount = execution.actors.reduce((total, actor) => total + actor.eventCount, 0);
  const recordCount = execution.actors.reduce((total, actor) => total + actor.recordCount, 0);
  const requested = focus !== null && "actorId" in focus ? focus : null;
  const exact = requested === null ? null : executionFocusMatches(execution, requested.actorId, requested.outputId, requested.eventId);
  return <div className="result-product-host execution-focus-host" data-testid="execution-product-host"><div className="result-host-copy"><span>执行摘要</span><h3>{exact?.actor.displayRole ?? `${execution.actors.length} 个参与角色`}</h3><p>{exact === null ? "仅展示可观察汇总，不包含原始事件流或内部推理内容。" : "已从报告定位到同一 Released Run 的精确 Actor → Output → Event。"}</p>{exact !== null && <div className="focus-receipt" data-testid="execution-exact-focus"><span>{exact.actor.actorId} · {exact.output.status}</span><code>{exact.output.outputId}</code><code>{exact.event.eventId}</code><small>{exact.output.summary}</small></div>}{requested !== null && exact === null && <div className="focus-receipt invalid">请求的执行定位与此 Run 不匹配；未展示近似记录。</div>}</div><div className="result-host-facts"><div><span>事件总量</span><strong>{eventCount}</strong></div><div><span>输出记录</span><strong>{recordCount}</strong></div></div>{requested?.returnAnchor && <button type="button" className="btn" data-testid="execution-return-report" onClick={() => onNavigate(resultsPath(runId, "report", { anchor: requested.returnAnchor! }))}>返回报告位置</button>}</div>;
}
