import { useMemo } from "react";
import { TASK_STATUS_MAP } from "../../types/domain";
import type {
  PathChangeProjectionV1,
  RunProjection,
  RunTaskProjection
} from "../../types/domain";

const TASK_STATUS_LABELS: Record<RunTaskProjection["backendStatus"], string> = {
  CREATED: "Created",
  WAITING: "Waiting",
  READY: "Ready",
  RUNNING: "Running",
  WAITING_FOR_CAPABILITY: "Waiting for capability",
  SELF_CORRECTING: "Self-correcting",
  BLOCKED: "Blocked",
  REVIEW: "Review",
  COMPLETED: "Completed",
  FAILED: "Failed",
  CAPABILITY_BUILD_FAILED: "Capability build failed",
  CANCELLED: "Cancelled"
};

const CHANGE_SEMANTICS: Record<
  PathChangeProjectionV1["changeKind"],
  { label: string; description: string; icon: string; tone: string }
> = {
  SELF_CORRECTION: {
    label: "SELF_CORRECTION",
    description: "Local correction on the same Task and graph identity.",
    icon: "↻",
    tone: "amber"
  },
  ADD_TASK: {
    label: "ADD_TASK",
    description: "Controlled Replan record for a Task addition request.",
    icon: "+",
    tone: "purple"
  },
  CHANGE_DEPENDENCY: {
    label: "CHANGE_DEPENDENCY",
    description: "Controlled Replan record for a dependency change request.",
    icon: "⇢",
    tone: "blue"
  }
};

type ProjectionModel =
  | { kind: "ready"; levels: readonly (readonly RunTaskProjection[])[] }
  | { kind: "pending"; message: string }
  | { kind: "unavailable"; message: string };

function sameStringSet(left: readonly string[], right: readonly string[]) {
  if (left.length !== right.length) return false;
  const values = new Set(left);
  return values.size === left.length && right.every((value) => values.has(value));
}

function projectGraph(projection: RunProjection): ProjectionModel {
  const runId = projection.run.runId;
  if (projection.plannedGraph.runId !== runId) {
    return { kind: "unavailable", message: "Planned Graph belongs to another Run." };
  }
  if (projection.actualGraph === null) {
    return {
      kind: "pending",
      message: "Actual Graph is not available yet. Research Tasks will appear after authoritative graph creation."
    };
  }
  if (projection.actualGraph.runId !== runId) {
    return { kind: "unavailable", message: "Actual Graph belongs to another Run." };
  }
  if (
    projection.graphVersion !== null &&
    projection.graphVersion !== projection.actualGraph.version
  ) {
    return { kind: "unavailable", message: "Actual Graph version does not match the Run projection." };
  }

  const tasks = projection.tasks;
  const graphTasks = projection.actualGraph.tasks;
  if (tasks.length === 0 || graphTasks.length === 0) {
    return {
      kind: "pending",
      message: "No authoritative Research Tasks are available for this Run."
    };
  }

  const taskById = new Map<string, RunTaskProjection>();
  for (const task of tasks) {
    if (task.runId !== runId) {
      return { kind: "unavailable", message: `Task ${task.taskId} belongs to another Run.` };
    }
    if (taskById.has(task.taskId)) {
      return { kind: "unavailable", message: `Task ${task.taskId} is duplicated.` };
    }
    taskById.set(task.taskId, task);
  }

  const graphTaskIds = graphTasks.map((task) => task.taskId);
  if (!sameStringSet([...taskById.keys()], graphTaskIds)) {
    return {
      kind: "unavailable",
      message: "Actual Graph Tasks and the atomic Task projection do not match."
    };
  }

  for (const graphTask of graphTasks) {
    const task = taskById.get(graphTask.taskId);
    if (!task || graphTask.runId !== runId) {
      return { kind: "unavailable", message: `Graph Task ${graphTask.taskId} has invalid identity.` };
    }
    if (
      task.backendStatus !== graphTask.backendStatus ||
      task.status !== graphTask.status ||
      !sameStringSet(task.dependencies, graphTask.dependencies)
    ) {
      return {
        kind: "unavailable",
        message: `Task ${task.taskId} is inconsistent across the atomic projection.`
      };
    }
    if (new Set(task.dependencies).size !== task.dependencies.length) {
      return { kind: "unavailable", message: `Task ${task.taskId} repeats a dependency.` };
    }
    if (task.dependencies.includes(task.taskId)) {
      return { kind: "unavailable", message: `Task ${task.taskId} depends on itself.` };
    }
    const unknown = task.dependencies.find((dependency) => !taskById.has(dependency));
    if (unknown) {
      return {
        kind: "unavailable",
        message: `Task ${task.taskId} references unknown dependency ${unknown}.`
      };
    }
  }

  for (const change of projection.pathChanges) {
    if (
      change.changeKind === "SELF_CORRECTION" &&
      (change.sourceKind !== "CORRECTION" ||
        change.taskRefs.length !== 1 ||
        !taskById.has(change.taskRefs[0]) ||
        change.operations.length !== 0 ||
        change.graphVersionBefore !== null ||
        change.graphVersionAfter !== null)
    ) {
      return {
        kind: "unavailable",
        message: `Path Change ${change.pathChangeId} violates same-Task Self-Correction semantics.`
      };
    }
    if (change.changeKind !== "SELF_CORRECTION" && change.sourceKind !== "REPLAN") {
      return {
        kind: "unavailable",
        message: `Path Change ${change.pathChangeId} has invalid Replan authority.`
      };
    }
    if (
      change.sourceKind === "REPLAN" &&
      change.decision !== "APPROVED" &&
      change.graphVersionAfter !== null
    ) {
      return {
        kind: "unavailable",
        message: `Unapproved Path Change ${change.pathChangeId} claims a resulting Graph version.`
      };
    }
    if (change.sourceKind === "REPLAN" && change.decision === "APPROVED") {
      const boundTaskIds = [
        ...change.taskRefs,
        ...change.operations.flatMap((operation) =>
          operation.dependencyTaskId === null
            ? [operation.taskId]
            : [operation.taskId, operation.dependencyTaskId]
        )
      ];
      const unknownRef = boundTaskIds.find((taskId) => !taskById.has(taskId));
      if (unknownRef) {
        return {
          kind: "unavailable",
          message: `Approved Path Change ${change.pathChangeId} references unknown Task ${unknownRef}.`
        };
      }
    }
  }

  const remaining = new Set(graphTaskIds);
  const completed = new Set<string>();
  const levels: RunTaskProjection[][] = [];
  while (remaining.size > 0) {
    const level = graphTasks
      .filter((task) => remaining.has(task.taskId))
      .filter((task) => task.dependencies.every((dependency) => completed.has(dependency)))
      .map((task) => taskById.get(task.taskId))
      .filter((task): task is RunTaskProjection => task !== undefined);
    if (level.length === 0) {
      return { kind: "unavailable", message: "Actual Graph contains a dependency cycle." };
    }
    levels.push(level);
    for (const task of level) {
      remaining.delete(task.taskId);
      completed.add(task.taskId);
    }
  }
  return { kind: "ready", levels };
}

function formatTimestamp(value: string) {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(timestamp);
}

function taskTone(task: RunTaskProjection) {
  if (task.status === "COMPLETE") return "done";
  if (task.status === "ACTIVE") return "live";
  if (task.status === "CORRECTING" || task.status === "WAITING_SUPPORT") {
    return "issue";
  }
  if (task.status === "BLOCKED" || task.status === "FAILED" || task.status === "CANCELLED") {
    return "blocked";
  }
  return "wait";
}

export function ResearchPath({
  projection,
  onOpenTask
}: {
  projection: RunProjection;
  onOpenTask?: (task: RunTaskProjection) => void;
}) {
  const model = useMemo(() => projectGraph(projection), [projection]);
  const correctionsByTask = useMemo(() => {
    const changes = new Map<string, PathChangeProjectionV1[]>();
    for (const change of projection.pathChanges) {
      if (change.changeKind !== "SELF_CORRECTION" || change.taskRefs.length !== 1) continue;
      const taskId = change.taskRefs[0];
      const current = changes.get(taskId) ?? [];
      current.push(change);
      changes.set(taskId, current);
    }
    return changes;
  }, [projection.pathChanges]);
  const replans = useMemo(
    () => projection.pathChanges.filter((change) => change.sourceKind === "REPLAN"),
    [projection.pathChanges]
  );

  return (
    <section className="path-panel rr-path-panel" aria-labelledby="research-path-title">
      <div className="path-head">
        <div>
          <div className="path-title" id="research-path-title">Research Path</div>
          <div className="path-sub">
            Exact Run {projection.run.runId} · Tasks and dependencies come only from the atomic Actual Graph projection.
          </div>
        </div>
        <div className="path-meta" aria-label="Research Path projection metadata">
          <span className="badge neutral">Sequence {projection.projectionSequence}</span>
          <span className="badge neutral">Revision {projection.projectionRevision}</span>
          <span className="badge neutral">
            Graph {projection.actualGraph ? `v${projection.actualGraph.version}` : "pending"}
          </span>
        </div>
      </div>

      <RunTerminalState projection={projection} />

      {model.kind !== "ready" ? (
        <div className="rr-path-empty" role={model.kind === "unavailable" ? "alert" : "status"}>
          <strong>{model.kind === "unavailable" ? "Research Path unavailable" : "Research Path pending"}</strong>
          <span>{model.message}</span>
        </div>
      ) : (
        <div className="path-cluster rr-path-cluster">
          <div className="path-cluster-title">
            <div>
              <strong>Actual Research Path</strong>
              <div className="micro">
                Graph {projection.actualGraph?.graphId} · dependency levels preserve authoritative snapshot order.
              </div>
            </div>
            <span className="badge neutral">{projection.tasks.length} Tasks</span>
          </div>
          {model.levels.map((level, index) => (
            <div className="rr-path-level" key={`level-${index + 1}`}>
              <div className="micro">Dependency level {index + 1}</div>
              <div className="path-grid">
                {level.map((task) => (
                  <div className="rr-task-node-stack" key={task.taskId}>
                    <TaskNode task={task} onOpenTask={onOpenTask} />
                    {(correctionsByTask.get(task.taskId) ?? []).map((change) => (
                      <div className="rr-self-correction-loop" key={change.pathChangeId}>
                        <span aria-hidden="true">↻</span>
                        <div>
                          <strong>Same-Task Self-Correction</strong>
                          <span>
                            {change.reasonCode ?? "Reason unavailable"} · {change.status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <PathChangeHistory changes={projection.pathChanges} replans={replans} />
    </section>
  );
}

function RunTerminalState({ projection }: { projection: RunProjection }) {
  const taskExecutionTerminal =
    projection.tasks.length > 0 &&
    projection.tasks.every((task) => TASK_STATUS_MAP[task.backendStatus].terminal);
  if (projection.terminal.isTerminal) {
    return (
      <div className="auto-replan rr-auto-replan" role="status">
        <div>
          <strong>Run terminal · {projection.terminal.outcome ?? projection.lifecycle.status}</strong>
          <div className="small">
            Authoritative terminal state at {projection.lifecycle.stage}
            {projection.terminal.sequence === null ? "" : ` · sequence ${projection.terminal.sequence}`}
          </div>
        </div>
        <span className="badge neutral">{projection.lifecycle.status}</span>
      </div>
    );
  }
  return (
    <div className="path-note" role="status">
      <strong>Run remains nonterminal.</strong>{" "}
      {taskExecutionTerminal
        ? `Task execution is terminal; review, proof, or release closure is still pending at ${projection.lifecycle.stage}.`
        : `Current authoritative stage: ${projection.lifecycle.stage}.`}
    </div>
  );
}

function TaskNode({
  task,
  onOpenTask
}: {
  task: RunTaskProjection;
  onOpenTask?: (task: RunTaskProjection) => void;
}) {
  const percent = Math.round(Math.max(0, Math.min(1, task.progress)) * 100);
  return (
    <button
      type="button"
      className={`branch-node rr-branch-node ${taskTone(task)}`}
      onClick={() => onOpenTask?.(task)}
      aria-label={`Open Task ${task.taskId}`}
    >
      <div className="rr-node-topline">
        <span className="micro">{task.taskId}</span>
        {task.origin === "REPLAN" && <span className="flag">+ REPLAN</span>}
      </div>
      <div className="bn">{task.taskType}</div>
      <div className="bs">{task.goal}</div>
      <div className="rr-node-status">
        Raw status · {TASK_STATUS_LABELS[task.backendStatus]} ({task.backendStatus})
      </div>
      <div className="rr-node-status">Projected status · {task.status}</div>
      <div
        className="rr-node-progress"
        role="progressbar"
        aria-label={`Task progress ${percent}%`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <span style={{ width: `${percent}%` }} />
      </div>
      <div className="micro">
        {task.dependencies.length > 0
          ? `Depends on ${task.dependencies.join(" · ")}`
          : "No declared dependencies"}
      </div>
    </button>
  );
}

function PathChangeHistory({
  changes,
  replans
}: {
  changes: readonly PathChangeProjectionV1[];
  replans: readonly PathChangeProjectionV1[];
}) {
  return (
    <div className="rr-path-history">
      <div className="rr-section-heading">
        <div>
          <strong>Path Change History</strong>
          <span>
            Read-only correction and Lead-controlled Replan records. Topology always comes from the Actual Graph snapshot.
          </span>
        </div>
        <span className="badge neutral">{changes.length} records</span>
      </div>
      {changes.length === 0 ? (
        <div className="rr-path-empty">No authoritative Path Change records are available.</div>
      ) : (
        changes.map((change) => {
          const semantic = CHANGE_SEMANTICS[change.changeKind];
          const isApprovedReplan =
            change.sourceKind === "REPLAN" && change.decision === "APPROVED";
          const isUnapprovedReplan = change.sourceKind === "REPLAN" && !isApprovedReplan;
          return (
            <div className={`path-change rr-path-change ${semantic.tone}`} key={change.pathChangeId}>
              <div className="pc-type">
                <span className={`rr-change-chip ${semantic.tone}`}>
                  <span aria-hidden="true">{semantic.icon}</span>{semantic.label}
                </span>
              </div>
              <div>
                <div className="pc-title">
                  {change.reasonCode ?? "Reason code unavailable"} · {change.sourceKind} {change.sourceId}
                </div>
                <div className="pc-sub">
                  {semantic.description} · {formatTimestamp(change.createdAt)}
                </div>
                <div className="rr-change-links">
                  {change.taskRefs.map((taskId) => <span key={taskId}>Task · {taskId}</span>)}
                </div>
                {change.operations.length > 0 && (
                  <div className="task-fact-list">
                    <span>
                      {isApprovedReplan
                        ? "Approved operation records"
                        : "Requested operations only · no mutation asserted"}
                    </span>
                    {change.operations.map((operation, index) => (
                      <span key={`${operation.operation}-${operation.taskId}-${index}`}>
                        {operation.operation} · {operation.taskId}
                        {operation.dependencyTaskId ? ` · dependency ${operation.dependencyTaskId}` : ""}
                      </span>
                    ))}
                  </div>
                )}
                {isUnapprovedReplan && (
                  <div className="small">
                    No topology effect is inferred from this {change.decision ?? "UNDECIDED"} Replan record.
                  </div>
                )}
              </div>
              <span className="badge neutral">
                {change.decision ?? change.status}
              </span>
            </div>
          );
        })
      )}
      {replans.length > 0 && (
        <div className="path-note">
          {replans.length} Replan record{replans.length === 1 ? "" : "s"}; only approved graph state present in the
          atomic projection is rendered above.
        </div>
      )}
    </div>
  );
}
