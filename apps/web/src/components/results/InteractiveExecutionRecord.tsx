import { useEffect, useMemo, useRef, useState } from "react";
import type { ExecutionRecordSurfaceV1, ReportContributionRefV1 } from "../../types/domain";
import {
  defaultExecutionActor,
  exactExecutionActor,
  exactExecutionTarget,
  executionRecordCards,
  filterExecutionActors,
  groupExecutionActors,
  inputRefKind,
  observableExecutionRows
} from "./executionModel";

export interface ExecutionSelection {
  readonly actorId: string;
  readonly outputId: string | null;
  readonly eventId: string | null;
  readonly returnAnchor: string | null;
}

export interface InteractiveExecutionRecordProps {
  readonly execution: ExecutionRecordSurfaceV1;
  readonly requested: ExecutionSelection | null;
  readonly onSelectActor: (actorId: string) => void;
  readonly onOpenReport: (contribution: ReportContributionRefV1) => void;
}

type ExecutionMode = "COLLABORATION" | "RECORDS";

const actorTypeLabel = (type: string): string => type === "RESEARCH_LEAD"
  ? "Research Lead"
  : type === "SPECIALIST" ? "Specialist" : "Supporting Execution";

export function InteractiveExecutionRecord({ execution, requested, onSelectActor, onOpenReport }: InteractiveExecutionRecordProps) {
  const groups = useMemo(() => groupExecutionActors(execution), [execution]);
  const defaultActor = useMemo(() => defaultExecutionActor(execution), [execution]);
  const exactTarget = requested?.outputId && requested.eventId
    ? exactExecutionTarget(execution, requested.actorId, requested.outputId, requested.eventId)
    : null;
  const requestedActor = requested === null ? null : exactExecutionActor(execution, requested.actorId);
  const requestedInvalid = requested !== null && (requestedActor === null || ((requested.outputId !== null || requested.eventId !== null) && exactTarget === null));
  const selected = requestedInvalid ? null : requestedActor ?? (defaultActor === null ? null : exactExecutionActor(execution, defaultActor.actorId));
  const [mode, setMode] = useState<ExecutionMode>("COLLABORATION");
  const [query, setQuery] = useState("");
  const filteredGroups = useMemo(() => filterExecutionActors(groups, query), [groups, query]);
  const focusRef = useRef<HTMLElement | null>(null);
  const totalEvents = execution.actors.reduce((sum, actor) => sum + actor.eventCount, 0);
  const totalRecords = execution.actors.reduce((sum, actor) => sum + actor.recordCount, 0);
  const totalContributions = execution.actorDetails
    .filter((detail) => detail.runId === execution.runId)
    .flatMap(executionRecordCards)
    .filter((card) => card.contribution !== null).length;

  useEffect(() => {
    if (exactTarget === null) return;
    const timer = window.setTimeout(() => focusRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
    return () => window.clearTimeout(timer);
  }, [exactTarget]);

  return <div className="execution-workspace" data-testid="interactive-execution-record" data-run-id={execution.runId} data-actor-count={execution.actors.length}>
    <section className="execution-summary" aria-label="执行记录摘要">
      <div><span>协作参与者</span><strong>{execution.actors.length}</strong></div>
      <div><span>可观察事件</span><strong>{totalEvents}</strong></div>
      <div><span>执行记录</span><strong>{totalRecords}</strong></div>
      <div><span>报告贡献</span><strong>{totalContributions}</strong></div>
      <p>主要视图按“谁执行”组织；{totalEvents}/{totalRecords} 为精确 Run 的汇总计数，安全明细仅呈现公共契约实际投影的记录。</p>
    </section>

    <div className="execution-toolbar">
      <div className="execution-mode" role="tablist" aria-label="执行记录查看模式">
        <button type="button" role="tab" aria-selected={mode === "COLLABORATION"} className={mode === "COLLABORATION" ? "active" : ""} data-testid="execution-mode-collaboration" onClick={() => setMode("COLLABORATION")}><strong>协作视图</strong><small>Actor → I/P/O</small></button>
        <button type="button" role="tab" aria-selected={mode === "RECORDS"} className={mode === "RECORDS" ? "active" : ""} data-testid="execution-mode-records" onClick={() => setMode("RECORDS")}><strong>可观察记录</strong><small>{observableExecutionRows(execution).length} 条安全明细</small></button>
      </div>
      <label className="execution-search"><span>筛选 Actor</span><input type="search" value={query} placeholder="角色或精确 ID" onChange={(event) => setQuery(event.target.value)} /></label>
    </div>

    {requestedInvalid && <div className="execution-focus-invalid" role="alert" data-testid="execution-focus-invalid">请求的 Actor / AgentOutput / Event 与此 Run 不形成唯一精确关系；未使用近似或跨 Run 回退。</div>}

    {mode === "COLLABORATION" ? <div className="execution-collaboration" data-testid="execution-collaboration-view">
      <aside className="actor-rail" aria-label="执行参与者">
        {filteredGroups.map((group) => <section key={group.groupKey} data-actor-group={group.groupKey}><header><span>{group.title}</span><small>{group.actors.length}</small></header>{group.actors.map((actor) => {
          const detail = exactExecutionActor(execution, actor.actorId)?.detail ?? null;
          const active = selected?.actor.actorId === actor.actorId;
          return <button key={`${actor.actorType}:${actor.actorId}`} type="button" className={`actor-rail-item ${active ? "active" : ""}`} aria-pressed={active} data-actor-id={actor.actorId} onClick={() => onSelectActor(actor.actorId)}>
            <span className="actor-status-dot" aria-hidden="true" /><span><strong>{actor.displayRole}</strong><small>{detail?.observableProcess.at(-1)?.eventType ?? "安全明细未投影"}</small><code>{actor.actorId}</code></span><em>{actor.recordCount}</em>
          </button>;
        })}</section>)}
        {filteredGroups.length === 0 && <div className="actor-rail-empty">没有匹配的当前 Run Actor。</div>}
      </aside>
      <main className="actor-detail">{selected === null ? <div className="execution-unobserved">当前 Run 没有可选择的 Actor。</div> : <ActorDetail
        actor={selected.actor}
        detail={selected.detail}
        exactOutputId={exactTarget?.output.outputId ?? null}
        exactEventId={exactTarget?.event.eventId ?? null}
        focusRef={focusRef}
        onOpenReport={onOpenReport}
      />}</main>
    </div> : <ObservableRecords execution={execution} query={query} />}

    <footer className="execution-observability-note"><strong>可观察边界</strong><span>Process 仅来自 `observable_process` 公共记录；不显示系统提示词、私有 scratchpad、模型内部推理或供应商原始响应。</span></footer>
  </div>;
}

function ActorDetail({ actor, detail, exactOutputId, exactEventId, focusRef, onOpenReport }: {
  readonly actor: ExecutionRecordSurfaceV1["actors"][number];
  readonly detail: ExecutionRecordSurfaceV1["actorDetails"][number] | null;
  readonly exactOutputId: string | null;
  readonly exactEventId: string | null;
  readonly focusRef: { current: HTMLElement | null };
  readonly onOpenReport: (contribution: ReportContributionRefV1) => void;
}) {
  const cards = detail === null ? [] : executionRecordCards(detail);
  const inputRefs = detail === null ? [] : detail.inputRefs.filter((ref) => ref.runId === detail.runId);
  return <>
    <header className="actor-detail-head"><div><span>{actorTypeLabel(actor.actorType)}</span><h3>{actor.displayRole}</h3><code>{actor.actorId}</code></div><div className="actor-detail-stats"><span className="badge green">{actor.status}</span><strong>{actor.eventCount} events · {actor.recordCount} records</strong><small>{detail === null ? "公共契约未投影 Actor 明细" : `${inputRefs.length} inputs · ${cards.filter((card) => card.event !== null).length} process · ${cards.filter((card) => card.output !== null).length} outputs`}</small></div></header>
    {detail === null ? <section className="execution-unobserved" data-testid="execution-detail-not-observed"><strong>输入 / 过程 / 输出明细未观察到</strong><p>当前公共 Execution surface 只提供此 Supporting Actor 的精确身份与汇总计数；不会从汇总事件数中猜测内容。</p><div className="execution-empty-ipo"><span>输入：未观察到</span><span>过程：未观察到</span><span>输出：未观察到</span></div><footer>报告贡献：未观察到明确关系</footer></section> : <>
      {cards.map((card, index) => {
        const focused = card.output?.outputId === exactOutputId && card.event?.eventId === exactEventId;
        return <article key={card.taskId} ref={focused ? (node) => { focusRef.current = node; } : undefined} className={`execution-card ${focused ? "focused" : ""}`} data-testid={focused ? "execution-exact-focus" : "execution-record-card"}>
          <header><span>{String(index + 1).padStart(2, "0")}</span><div><h4>{taskLabel(card.taskId)}</h4><code>{card.taskId}</code></div><span className={`badge ${card.output?.status === "FAILED" ? "red" : "green"}`}>{card.output?.status ?? card.event?.status ?? "NOT_OBSERVED"}</span></header>
          <div className="execution-ipo">
            <section><h5>输入 · INPUT</h5><p>此 Actor 的可追溯输入引用</p><div className="execution-ref-list">{inputRefs.slice(0, 7).map((ref) => <code key={ref.refId}><b>{inputRefKind(ref.refId)}</b>{ref.refId}</code>)}</div>{inputRefs.length > 7 && <details><summary>查看全部 {inputRefs.length} 个安全引用</summary><div className="execution-ref-list expanded">{inputRefs.slice(7).map((ref) => <code key={ref.refId}><b>{inputRefKind(ref.refId)}</b>{ref.refId}</code>)}</div></details>}</section>
            <section><h5>可观察过程 · PROCESS</h5>{card.event === null ? <p>Process not observed</p> : <div className="execution-process-step"><span>1</span><div><strong>{eventLabel(card.event.eventType)}</strong><p>{card.event.status}</p><code>{card.event.eventId}</code></div></div>}</section>
            <section><h5>输出 · OUTPUT</h5>{card.output === null ? <p>Output not observed</p> : <><div className="execution-output-id"><span>AgentOutput</span><code>{card.output.outputId}</code></div><p className="execution-output-summary">{card.output.summary ?? "安全摘要未观察到"}</p><details className="execution-output-detail"><summary>结构化输出详情</summary><OutputList title="关键发现" items={card.output.keyFindings} /><OutputList title="风险" items={card.output.risks} /><OutputList title="限制" items={card.output.limitations} /></details></>}</section>
          </div>
          <footer className={`execution-contribution ${card.contribution === null ? "unobserved" : "observed"}`}>
            <div><span>报告贡献 · REPORT CONTRIBUTION</span>{card.contribution === null ? <strong>未观察到明确的报告贡献关系</strong> : <><strong>{card.contribution.reportAnchor}</strong><code>{card.contribution.reportId} · {card.contribution.artifactId}</code></>}</div>
            {card.contribution !== null && <button type="button" className="btn primary sm" data-testid="execution-open-report-anchor" onClick={() => onOpenReport(card.contribution!)}>查看报告位置</button>}
          </footer>
        </article>;
      })}
      {cards.length === 0 && <div className="execution-unobserved">此 Actor 没有安全可呈现的执行明细。</div>}
    </>}
  </>;
}

function ObservableRecords({ execution, query }: { readonly execution: ExecutionRecordSurfaceV1; readonly query: string }) {
  const normalized = query.trim().toLocaleLowerCase();
  const rows = observableExecutionRows(execution).filter(({ actor, event }) => normalized.length === 0 ||
    `${actor.displayRole} ${actor.actorId} ${event.eventId} ${event.taskId ?? ""} ${event.eventType} ${event.status}`.toLocaleLowerCase().includes(normalized)
  );
  return <section className="execution-records-view" data-testid="execution-records-view"><header><div><span>SECONDARY VIEW</span><h3>可观察执行记录</h3><p>仅列出公共契约投影的 {observableExecutionRows(execution).length} 条 Actor 明细；不把汇总计数伪装成可展开事件。</p></div><span className="badge neutral">{rows.length} records</span></header><div className="execution-table-wrap"><table><thead><tr><th>Actor</th><th>Task</th><th>Event</th><th>Type</th><th>Status</th></tr></thead><tbody>{rows.map(({ actor, event }) => <tr key={event.eventId}><td><strong>{actor.displayRole}</strong><code>{actor.actorId}</code></td><td><code>{event.taskId ?? "NOT_OBSERVED"}</code></td><td><code>{event.eventId}</code></td><td>{event.eventType}</td><td><span className="badge green">{event.status}</span></td></tr>)}</tbody></table></div></section>;
}

function OutputList({ title, items }: { readonly title: string; readonly items: readonly string[] }) {
  if (items.length === 0) return null;
  return <section><h6>{title} · {items.length}</h6><ul>{items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}</ul></section>;
}

function taskLabel(taskId: string): string {
  const name = taskId.split(":").at(-1) ?? taskId;
  return name.split("-").map((part) => part.length === 0 ? part : `${part[0].toUpperCase()}${part.slice(1)}`).join(" ");
}

function eventLabel(eventType: string): string {
  if (eventType === "task.completed") return "任务执行完成并持久化输出";
  return eventType;
}
