import { useEffect, useMemo } from "react";
import type { ReactNode } from "react";
import { TASK_STATUS_MAP } from "../../types/domain";
import type {
  PathChangeProjectionV1,
  RunProjection,
  RunTaskProjection
} from "../../types/domain";
import { OverlaySurface } from "../overlays/OverlaySurface";

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

function formatTimestamp(value: string) {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      }).format(timestamp);
}

function stateTitle(task: RunTaskProjection) {
  if (task.backendStatus === "SELF_CORRECTING") return "This Task is correcting locally";
  if (task.backendStatus === "RUNNING") return "This Research Task is running";
  if (task.backendStatus === "WAITING_FOR_CAPABILITY") {
    return "This Task is waiting for supporting capability";
  }
  if (task.backendStatus === "WAITING") return "This Task is waiting for dependencies";
  return TASK_STATUS_LABELS[task.backendStatus];
}

function timelineTone(status: string | null | undefined, type: string) {
  if (type.endsWith(".failed") || status === "FAILED" || status === "CANCELLED") {
    return "warning";
  }
  if (type.endsWith(".completed") || status === "COMPLETED" || status === "RELEASED") {
    return "done";
  }
  if (type.endsWith(".started") || type.endsWith(".progress") || status === "RUNNING") {
    return "live";
  }
  return "waiting";
}

export function TaskDetailDrawer({
  projection,
  taskId,
  claimId,
  targetAnchor,
  onOpenClaim,
  onClose
}: {
  projection: RunProjection;
  taskId: string | null;
  claimId?: string | null;
  targetAnchor?: string | null;
  onOpenClaim?: (claimId: string) => void;
  onClose: () => void;
}) {
  const task = useMemo(() => {
    if (taskId === null) return null;
    const matches = projection.tasks.filter((candidate) => candidate.taskId === taskId);
    return matches.length === 1 ? matches[0] : undefined;
  }, [projection.tasks, taskId]);
  const timeline = useMemo(
    () =>
      task
        ? projection.activity
            .filter((event) => event.taskId === task.taskId)
            .slice()
            .sort((left, right) => left.sequence - right.sequence)
        : [],
    [projection.activity, task]
  );
  const changes = useMemo(
    () =>
      task
        ? projection.pathChanges.filter((change) => change.taskRefs.includes(task.taskId))
        : [],
    [projection.pathChanges, task]
  );

  useEffect(() => {
    if (!task || !targetAnchor) return;
    window.requestAnimationFrame(() =>
      window.requestAnimationFrame(() => {
        const target = document.getElementById(`task-event-${task.taskId}-${targetAnchor}`);
        target?.scrollIntoView({ block: "center" });
        target?.focus();
      })
    );
  }, [task, targetAnchor]);

  if (taskId === null) return null;

  return (
    <OverlaySurface
      kind="drawer"
      titleId="task-drawer-title"
      className="rr-task-drawer"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>关闭</button>
          <span className="small">Exact-Run Task projection · read only</span>
          {claimId && onOpenClaim && (
            <button type="button" className="btn ghost sm" onClick={() => onOpenClaim(claimId)}>
              返回关联 Claim
            </button>
          )}
        </>
      }
    >
      <div className="drawer-head">
        <div>
          <strong id="task-drawer-title">{task ? task.taskType : "Task unavailable"}</strong>
          <div className="small">
            {taskId} · exact Run {projection.run.runId}
          </div>
        </div>
        <button
          type="button"
          className="btn ghost"
          data-autofocus
          onClick={onClose}
          aria-label="关闭任务详情"
        >
          ✕
        </button>
      </div>
      <div className="drawer-body">
        {task === undefined ? (
          <div className="rr-timeline-empty" role="alert">
            This Task is absent or duplicated in the current atomic Run projection. No fallback Task was created.
          </div>
        ) : task === null ? null : task.runId !== projection.run.runId ? (
          <div className="rr-timeline-empty" role="alert">
            This Task belongs to another Run and cannot be displayed here.
          </div>
        ) : (
          <TaskProjectionDetail
            projection={projection}
            task={task}
            timeline={timeline}
            changes={changes}
            targetAnchor={targetAnchor}
          />
        )}
      </div>
    </OverlaySurface>
  );
}

function TaskProjectionDetail({
  projection,
  task,
  timeline,
  changes,
  targetAnchor
}: {
  projection: RunProjection;
  task: RunTaskProjection;
  timeline: RunProjection["activity"];
  changes: readonly PathChangeProjectionV1[];
  targetAnchor?: string | null;
}) {
  const percent = Math.round(Math.max(0, Math.min(1, task.progress)) * 100);
  const graphContainsTask =
    projection.actualGraph?.tasks.filter((candidate) => candidate.taskId === task.taskId).length === 1;
  if (!graphContainsTask) {
    return (
      <div className="rr-timeline-empty" role="alert">
        This Task is not present exactly once in the authoritative Actual Graph.
      </div>
    );
  }

  return (
    <>
      <div className={`rr-task-state ${task.status.toLowerCase()}`}>
        {task.backendStatus === "SELF_CORRECTING" ? (
          <div className="rr-loop-indicator">↻</div>
        ) : task.backendStatus === "RUNNING" ? (
          <div className="spinner" />
        ) : (
          <div className="rr-state-mark">
            {task.backendStatus === "COMPLETED"
              ? "✓"
              : task.backendStatus === "FAILED" || task.backendStatus === "CAPABILITY_BUILD_FAILED"
                ? "×"
                : task.backendStatus === "BLOCKED" || task.backendStatus === "CANCELLED"
                  ? "!"
                  : "◷"}
          </div>
        )}
        <div>
          <div className="rr-state-line">
            <strong>{stateTitle(task)}</strong>
            <span className="badge neutral">{task.status}</span>
          </div>
          <div className="small">
            Exact raw status {task.backendStatus} · projected status {task.status} · terminal{" "}
            {String(TASK_STATUS_MAP[task.backendStatus].terminal)}
          </div>
          <div
            className="rr-drawer-progress"
            role="progressbar"
            aria-label={`Task progress ${percent}%`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          >
            <span style={{ width: `${percent}%` }} />
            <small>{percent}%</small>
          </div>
        </div>
      </div>

      <div className="trace-card rr-task-trace">
        <TaskSection title="Task purpose">{task.goal}</TaskSection>
        <TaskSection title="Authoritative identity">
          <div className="detail-grid">
            <span>Task</span><strong>{task.taskId}</strong>
            <span>Run</span><strong>{task.runId}</strong>
            <span>Parent Task</span><strong>{task.parentTaskId ?? "None"}</strong>
            <span>Origin</span><strong>{task.origin}</strong>
            <span>Created</span><strong>{formatTimestamp(task.createdAt)}</strong>
          </div>
        </TaskSection>
        <TaskSection title="Assigned execution">
          <div className="detail-grid">
            <span>Agent</span><strong>{task.assignedAgent}</strong>
            <span>Skill</span><strong>{task.skillId}</strong>
            <span>Attempt</span><strong>{task.attemptCount}</strong>
            <span>Evidence acquisition</span><strong>{task.evidenceAcquisitionStatus ?? "Unavailable"}</strong>
          </div>
        </TaskSection>
        <TaskSection title="Task dependencies" empty="No declared dependencies">
          {task.dependencies.length > 0 && <RefList values={task.dependencies} />}
        </TaskSection>
        <TaskSection title="Input Evidence" empty="No input Evidence refs">
          {task.taskInputEvidenceIds.length > 0 && <RefList values={task.taskInputEvidenceIds} />}
        </TaskSection>
        <TaskSection title="Output Evidence" empty="No output Evidence refs">
          {task.taskOutputEvidenceIds.length > 0 && <RefList values={task.taskOutputEvidenceIds} />}
        </TaskSection>
        <TaskSection title="Correction / Replan" empty="No authoritative Path Change records">
          {changes.length > 0 && (
            <div className="task-fact-list">
              {changes.map((change) => (
                <span key={change.pathChangeId}>
                  {change.changeKind} · {change.sourceKind} {change.sourceId} · {change.decision ?? change.status}
                  {change.reasonCode ? ` · ${change.reasonCode}` : ""}
                  {change.sourceKind === "REPLAN" && change.decision !== "APPROVED"
                    ? " · request only; no mutation asserted"
                    : ""}
                </span>
              ))}
            </div>
          )}
        </TaskSection>
      </div>

      <div className="rr-timeline-heading">
        <strong>Trace · observable Task activity</strong>
        <div className="small">
          Safe message codes and authoritative refs only; hidden reasoning and raw provider payloads are not shown.
        </div>
      </div>
      {timeline.length > 0 ? (
        <div className="timeline rr-task-timeline">
          {timeline.map((event) => {
            const refs = [
              ...(event.inputRefs ?? []),
              ...(event.outputRefs ?? []),
              ...(event.evidenceRefs ?? []),
              ...(event.calculationRefs ?? []),
              ...(event.claimRefs ?? []),
              ...(event.judgmentRefs ?? []),
              ...(event.reviewRefs ?? []),
              ...(event.proofRefs ?? []),
              ...(event.artifactRefs ?? []),
              ...(event.traceBundleRefs ?? [])
            ];
            return (
              <div
                className={`timeline-item ${timelineTone(event.status, event.type)} ${targetAnchor === event.eventId ? "is-highlighted" : ""}`}
                id={`task-event-${task.taskId}-${event.eventId}`}
                key={event.eventId}
                tabIndex={-1}
              >
                <div className="rr-event-topline">
                  <div className="timeline-title">{event.messageCode}</div>
                  <time>{formatTimestamp(event.timestamp)}</time>
                </div>
                <div className="timeline-meta">
                  {event.type} · sequence {event.sequence}{event.status ? ` · ${event.status}` : ""}
                </div>
                {refs.length > 0 && <RefList values={refs} />}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rr-timeline-empty">No safe observable activity is available for this Task.</div>
      )}
    </>
  );
}

function RefList({ values }: { values: readonly string[] }) {
  return (
    <div className="chips">
      {values.map((value, index) => <span className="chip2" key={`${value}-${index}`}>{value}</span>)}
    </div>
  );
}

function TaskSection({
  title,
  empty,
  children
}: {
  title: string;
  empty?: string;
  children?: ReactNode;
}) {
  return (
    <div className="trace-section">
      <h4>{title}</h4>
      {children ?? <div className="small rr-empty-copy">{empty ?? "Unavailable"}</div>}
    </div>
  );
}
