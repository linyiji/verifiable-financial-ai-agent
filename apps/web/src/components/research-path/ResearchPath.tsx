import { useMemo, type ReactNode } from "react";
import { researchPlanLabel } from "../../pages/NewResearchTaskPage";
import { PHASE4_TASK_STATUS_LABELS } from "../../state/status";
import type { PathChangeProjectionV1, RunProjection, RunTaskProjection } from "../../types/domain";

type ProjectionModel =
  | { kind: "ready"; levels: readonly (readonly RunTaskProjection[])[] }
  | { kind: "pending"; message: string }
  | { kind: "unavailable"; message: string };

const AGENT_LABELS: Readonly<Record<string, string>> = {
  research_lead: "Research Lead",
  research_news_analyst: "研究与事件分析师",
  fundamental_analyst: "Fundamental Analyst",
  peer_analyst: "Peer Analyst",
  valuation_analyst: "Valuation Analyst",
  risk_analyst: "Risk Analyst"
};

function agentLabel(value: string): string {
  return AGENT_LABELS[value.trim().toLowerCase()] ?? value.replace(/_/gu, " ");
}

function sameStringSet(left: readonly string[], right: readonly string[]): boolean {
  if (left.length !== right.length) return false;
  const values = new Set(left);
  return values.size === left.length && right.every((value) => values.has(value));
}

function invalid(message: string): ProjectionModel {
  return { kind: "unavailable", message };
}

function projectGraph(projection: RunProjection): ProjectionModel {
  const runId = projection.run.runId;
  if (projection.plannedGraph.runId !== runId) return invalid("Planned Graph identity mismatch");
  if (projection.actualGraph === null) return { kind: "pending", message: "Actual Graph 尚未形成。" };
  if (projection.actualGraph.runId !== runId) return invalid("Actual Graph identity mismatch");
  if (projection.graphVersion !== null && projection.graphVersion !== projection.actualGraph.version) {
    return invalid("Actual Graph version mismatch");
  }

  const taskById = new Map<string, RunTaskProjection>();
  for (const task of projection.tasks) {
    if (task.runId !== runId || taskById.has(task.taskId)) return invalid("Task identity mismatch");
    taskById.set(task.taskId, task);
  }
  const graphTasks = projection.actualGraph.tasks;
  if (taskById.size === 0 || graphTasks.length === 0) return { kind: "pending", message: "研究任务尚未形成。" };
  if (!sameStringSet([...taskById.keys()], graphTasks.map((task) => task.taskId))) {
    return invalid("Actual Graph task set mismatch");
  }

  for (const graphTask of graphTasks) {
    const task = taskById.get(graphTask.taskId);
    if (!task || graphTask.runId !== runId) return invalid("Graph Task identity mismatch");
    if (task.backendStatus !== graphTask.backendStatus || task.status !== graphTask.status || !sameStringSet(task.dependencies, graphTask.dependencies)) {
      return invalid("Atomic Task projection mismatch");
    }
    if (new Set(task.dependencies).size !== task.dependencies.length || task.dependencies.includes(task.taskId)) {
      return invalid("Invalid dependency set");
    }
    if (task.dependencies.some((dependency) => !taskById.has(dependency))) return invalid("Unknown dependency");
  }

  for (const change of projection.pathChanges) {
    if (change.changeKind === "SELF_CORRECTION") {
      if (change.sourceKind !== "CORRECTION" || change.taskRefs.length !== 1 || !taskById.has(change.taskRefs[0]) || change.operations.length !== 0 || change.graphVersionBefore !== null || change.graphVersionAfter !== null) {
        return invalid("Invalid Self-Correction semantics");
      }
      continue;
    }
    if (change.sourceKind !== "REPLAN") return invalid("Invalid Replan authority");
    if (change.decision !== "APPROVED" && change.graphVersionAfter !== null) return invalid("Unapproved Graph change");
    if (change.decision === "APPROVED") {
      const references = [...change.taskRefs, ...change.operations.flatMap((operation) => operation.dependencyTaskId === null ? [operation.taskId] : [operation.taskId, operation.dependencyTaskId])];
      if (references.some((taskId) => !taskById.has(taskId))) return invalid("Unknown Replan Task reference");
    }
  }

  const remaining = new Set(graphTasks.map((task) => task.taskId));
  const completed = new Set<string>();
  const levels: RunTaskProjection[][] = [];
  while (remaining.size > 0) {
    const level = graphTasks
      .filter((task) => remaining.has(task.taskId))
      .filter((task) => task.dependencies.every((dependency) => completed.has(dependency)))
      .map((task) => taskById.get(task.taskId))
      .filter((task): task is RunTaskProjection => task !== undefined);
    if (level.length === 0) return invalid("Actual Graph dependency cycle");
    levels.push(level);
    for (const task of level) {
      remaining.delete(task.taskId);
      completed.add(task.taskId);
    }
  }
  return { kind: "ready", levels };
}

function taskTone(task: RunTaskProjection): string {
  if (task.status === "COMPLETE") return "done";
  if (task.status === "ACTIVE") return "live";
  if (task.status === "CORRECTING" || task.status === "WAITING_SUPPORT") return "issue";
  if (["BLOCKED", "FAILED", "CANCELLED"].includes(task.status)) return "blocked";
  return "wait";
}

export function ResearchPath({ projection, onOpenTask }: {
  readonly projection: RunProjection;
  readonly onOpenTask?: (task: RunTaskProjection) => void;
}) {
  const model = useMemo(() => projectGraph(projection), [projection]);
  const actualById = useMemo(() => new Map(projection.tasks.map((task) => [task.taskId, task])), [projection.tasks]);
  const actualTasks = model.kind === "ready" ? model.levels.flat() : [];

  return <section className="path-panel compact-path" aria-labelledby="research-path-title" data-testid="research-path" data-run-id={projection.run.runId}>
    <div className="path-head compact-path-head">
      <div><div className="path-title" id="research-path-title">研究路径 · Research Path</div><div className="path-sub">初始计划与实际执行路径来自同一个精确 Research Run。</div></div>
      <span className="badge green">{projection.terminal.isTerminal ? "研究已完成" : "研究进行中"}</span>
    </div>

    <div className="path-comparison">
      <PathColumn
        kind="initial"
        title="初始研究路径"
        graphLabel={`Graph v${projection.plannedGraph.version}`}
        tasks={projection.plannedGraph.tasks}
        projection={projection}
        onOpenTask={(task) => { const actual = actualById.get(task.taskId); if (actual) onOpenTask?.(actual); }}
      />
      {model.kind === "ready"
        ? <PathColumn kind="actual" title="实际研究路径" graphLabel={`Graph v${projection.actualGraph?.version}`} tasks={actualTasks} projection={projection} onOpenTask={onOpenTask} />
        : <section className="compact-path-column actual-path" data-testid="actual-path" data-run-id={projection.run.runId} data-graph-id={projection.actualGraph?.graphId ?? ""} data-graph-version={projection.actualGraph?.version ?? ""}><div className="compact-path-empty"><strong>{model.kind === "pending" ? "实际路径准备中" : "实际路径暂不可用"}</strong><span>{model.kind === "pending" ? model.message : "当前路径未通过安全校验，未展示替代数据。"}</span></div></section>}
    </div>

    <ReplanHero projection={projection} />
    <PathChangeHistory changes={projection.pathChanges} />

    <details className="technical-details path-technical-details">
      <summary>Research Path 技术详情</summary>
      <dl><dt>Run ID</dt><dd>{projection.run.runId}</dd><dt>Projection sequence</dt><dd>{projection.projectionSequence}</dd><dt>Projection revision</dt><dd>{projection.projectionRevision}</dd><dt>Planned Graph ID</dt><dd>{projection.plannedGraph.graphId}</dd><dt>Actual Graph ID</dt><dd>{projection.actualGraph?.graphId ?? "尚未生成"}</dd></dl>
    </details>
  </section>;
}

function PathColumn({ kind, title, graphLabel, tasks, projection, onOpenTask }: {
  readonly kind: "initial" | "actual";
  readonly title: string;
  readonly graphLabel: string;
  readonly tasks: readonly RunTaskProjection[];
  readonly projection: RunProjection;
  readonly onOpenTask?: (task: RunTaskProjection) => void;
}) {
  const graph = kind === "initial" ? projection.plannedGraph : projection.actualGraph;
  return <section
    className={`compact-path-column ${kind === "initial" ? "initial-path" : "actual-path"}`}
    data-testid={kind === "initial" ? "initial-path" : "actual-path"}
    data-run-id={projection.run.runId}
    data-graph-id={graph?.graphId ?? ""}
    data-graph-version={graph?.version ?? ""}
  >
    <div className="compact-column-head"><div><span>{title}</span><strong>{graphLabel}</strong></div><span>{tasks.length} Tasks</span></div>
    <div className="compact-node-list">
      {tasks.map((task, index) => <CompactTaskNode key={task.taskId} task={task} planned={kind === "initial"} index={index + 1} onOpen={() => onOpenTask?.(task)} />)}
    </div>
  </section>;
}

function CompactTaskNode({ task, planned, index, onOpen }: {
  readonly task: RunTaskProjection;
  readonly planned: boolean;
  readonly index: number;
  readonly onOpen: () => void;
}) {
  return <button
    type="button"
    className={`compact-task-node ${taskTone(task)} ${task.origin === "REPLAN" ? "added" : ""}`}
    onClick={onOpen}
    aria-label={`查看 ${researchPlanLabel(task.taskType)} Task`}
    data-testid={planned ? "planned-research-task" : "research-task"}
    data-run-id={task.runId}
    data-task-id={task.taskId}
    data-task-status={task.backendStatus}
    data-task-progress={String(task.progress)}
    data-parent-task-id={task.parentTaskId ?? ""}
    data-dependency-ids={JSON.stringify(task.dependencies)}
    data-task-origin={task.origin}
  >
    <span className="compact-node-index">{String(index).padStart(2, "0")}</span>
    <span className="compact-node-copy"><strong>{researchPlanLabel(task.taskType)}</strong><small>{agentLabel(task.assignedAgent)}</small></span>
    <span className={`compact-node-status ${taskTone(task)}`}>{planned ? "计划" : PHASE4_TASK_STATUS_LABELS[task.status]}</span>
    {task.origin === "REPLAN" && <span className="compact-added-flag">+ 新增</span>}
  </button>;
}

function ReplanHero({ projection }: { readonly projection: RunProjection }) {
  const correction = projection.pathChanges.find((change) => change.sourceKind === "CORRECTION");
  const replan = projection.pathChanges.find((change) => change.sourceKind === "REPLAN");
  if (!correction && !replan) return <div className="path-note">本次研究未发生路径调整。</div>;
  const requested = replan ? boundActivity(projection, "replan.requested", replan.sourceId) : undefined;
  const approved = replan ? boundActivity(projection, "replan.approved", replan.sourceId) : undefined;
  const addedOperation = replan?.operations.find((operation) => operation.operation === "add_node");
  const addedTask = addedOperation ? projection.tasks.find((task) => task.taskId === addedOperation.taskId) : undefined;
  const graphChanged = replan !== undefined && replan.graphVersionBefore !== null && replan.graphVersionAfter !== null;
  const steps: ReactNode[] = [];

  if (correction) {
    steps.push(<article key="correction" className="replan-flow-step correction" data-testid="path-correction-summary" data-run-id={projection.run.runId} data-correction-id={correction.sourceId} data-task-id={correction.taskRefs[0] ?? ""} data-reason-code={correction.reasonCode ?? ""} data-correction-status={correction.status}><span>1</span><div><small>Correction</small><strong>{correction.reasonCode ?? "数据问题"}</strong><em>{correction.status}</em></div></article>);
  }
  if (replan && requested) {
    steps.push(<article key="requested" className="replan-flow-step" data-testid="replan-requested" data-run-id={projection.run.runId} data-replan-id={replan.sourceId} data-event-id={requested.eventId} data-event-sequence={requested.sequence}><span>2</span><div><small>路径调整请求</small><strong>Replan Requested</strong><em>风险信号需要进一步验证</em></div></article>);
  }
  if (replan?.decision === "APPROVED" && approved) {
    steps.push(<article key="approved" className="replan-flow-step approved" data-testid="replan-approved" data-run-id={projection.run.runId} data-replan-id={replan.sourceId} data-event-id={approved.eventId} data-event-sequence={approved.sequence} data-decision={replan.decision}><span>3</span><div><small>Research Lead</small><strong>Approved</strong><em>路径调整通过</em></div></article>);
  }
  if (replan && addedOperation && addedTask) {
    steps.push(<article key="added" className="replan-flow-step added" data-testid="added-task" data-run-id={projection.run.runId} data-replan-id={replan.sourceId} data-operation={addedOperation.operation} data-task-id={addedOperation.taskId} data-task-origin={addedTask.origin}><span>4</span><div><small>+ Task</small><strong>{researchPlanLabel(addedTask.taskType)}</strong><em>新增研究节点</em></div></article>);
  }
  if (replan && graphChanged) {
    steps.push(<article key="graph" className="replan-flow-step graph" data-testid="graph-version-change" data-run-id={projection.run.runId} data-replan-id={replan.sourceId} data-graph-version-before={replan.graphVersionBefore ?? ""} data-graph-version-after={replan.graphVersionAfter ?? ""}><span>5</span><div><small>Actual Path</small><strong>Graph v{replan.graphVersionBefore} → v{replan.graphVersionAfter}</strong><em>{projection.actualGraph?.tasks.length ?? projection.tasks.length} Tasks</em></div></article>);
  }

  return <section className="replan-hero" aria-labelledby="replan-hero-title">
    <div className="replan-hero-heading"><div><span>PATH ADJUSTMENT</span><h3 id="replan-hero-title">研究路径发生调整</h3><p>数据问题被修正后，研究团队按已记录的审批与安全图操作更新实际路径。</p></div>{replan?.decision === "APPROVED" && <span className="badge purple">已批准</span>}</div>
    <div className="replan-flow">
      {steps.map((step, index) => <div className="replan-flow-entry" key={index}>{index > 0 && <span className="replan-arrow" aria-hidden="true">→</span>}{step}</div>)}
    </div>
  </section>;
}

function boundActivity(projection: RunProjection, type: string, sourceId: string) {
  return projection.activity.find((activity) => activity.type === type && activity.outputRefs?.includes(sourceId));
}

function PathChangeHistory({ changes }: { readonly changes: readonly PathChangeProjectionV1[] }) {
  return <details className="path-history">
    <summary><span>路径变更记录 · {changes.length}</span><small>默认收起，按需查看审计详情</small></summary>
    <div className="path-history-list">
      {changes.length === 0
        ? <div className="path-note">本次研究没有路径变更记录。</div>
        : changes.map((change, index) => <article className="path-history-item" key={change.pathChangeId}>
            <span className="history-change-number">{index + 1}</span>
            <div><strong>{change.changeKind === "SELF_CORRECTION" ? "期间数据修正" : change.changeKind === "ADD_TASK" ? "新增风险跟进任务" : "研究依赖调整"}</strong><small>{change.changeKind === "SELF_CORRECTION" ? "Correction" : "Research Lead Replan"}</small></div>
            <span className={`badge ${change.changeKind === "SELF_CORRECTION" ? "green" : "purple"}`}>{change.changeKind === "SELF_CORRECTION" ? change.status : `REPLAN ${change.decision ?? change.status}`}</span>
            <details className="path-change-detail"><summary>查看详情</summary><dl><dt>Path Change ID</dt><dd>{change.pathChangeId}</dd><dt>Source ID</dt><dd>{change.sourceId}</dd><dt>Reason</dt><dd>{change.reasonCode ?? "—"}</dd><dt>Task refs</dt><dd>{change.taskRefs.join(" · ") || "—"}</dd></dl>{change.operations.length > 0 && <div className="operation-list"><strong>安全操作记录</strong>{change.operations.map((operation, operationIndex) => <code key={`${operation.operation}-${operationIndex}`}>{operation.operation} · {operation.taskId}{operation.dependencyTaskId ? ` · dependency ${operation.dependencyTaskId}` : ""}</code>)}</div>}</details>
          </article>)}
    </div>
  </details>;
}
