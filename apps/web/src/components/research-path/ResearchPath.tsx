import { useMemo, useState } from "react";
import type {
  PathChange,
  PathChangeType,
  ResearchRun,
  ResearchTask
} from "../../types/domain";
import { TASK_STATUS_LABELS as STATUS_LABELS } from "../../state/status";

type View = "actual" | "initial" | "compare";

const CHANGE_SEMANTICS: Record<
  PathChangeType,
  { label: string; shortLabel: string; description: string; icon: string; tone: string }
> = {
  SELF_CORRECTION: {
    label: "SELF_CORRECTION · 原任务自我修正",
    shortLabel: "SELF_CORRECTION",
    description: "保持任务目标不变，在原任务内回退、修复并重试。",
    icon: "↻",
    tone: "amber"
  },
  ADD_TASK: {
    label: "ADD_TASK · 新增研究任务",
    shortLabel: "ADD_TASK",
    description: "Research Lead 因证据缺口正式增加研究任务。",
    icon: "+",
    tone: "purple"
  },
  CHANGE_DEPENDENCY: {
    label: "CHANGE_DEPENDENCY · 调整依赖",
    shortLabel: "CHANGE_DEPENDENCY",
    description: "后续任务改为等待新的证据或研究任务。",
    icon: "⇢",
    tone: "blue"
  }
};

function taskTone(task: ResearchTask) {
  if (task.isDynamic) return "added";
  if (task.status === "COMPLETED") return "done";
  if (task.status === "RUNNING") return "live";
  if (task.status === "SELF_CORRECTING") return "issue";
  if (task.status === "BLOCKED" || task.status === "FAILED") return "blocked";
  return "wait";
}

function sameDependencies(left: string[] = [], right: string[] = []) {
  return [...left].sort().join("|") === [...right].sort().join("|");
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

export function ResearchPath({
  run,
  onOpenTask
}: {
  run: ResearchRun;
  onOpenTask?: (task: ResearchTask) => void;
}) {
  const [view, setView] = useState<View>("actual");
  const [showChanges, setShowChanges] = useState(true);
  const [showSemantics, setShowSemantics] = useState(false);
  const initialTasks = useMemo(
    () => run.initialTasks.length > 0 ? run.initialTasks : run.tasks.filter((task) => !task.isDynamic),
    [run.initialTasks, run.tasks]
  );
  const addedTasks = useMemo(() => run.tasks.filter((task) => task.isDynamic), [run.tasks]);
  const selfCorrections = useMemo(
    () => run.pathChanges.filter((change) => change.type === "SELF_CORRECTION"),
    [run.pathChanges]
  );
  const observedTypes = useMemo(() => Array.from(new Set(run.pathChanges.map((change) => change.type))), [run.pathChanges]);

  return (
    <section className="path-panel rr-path-panel" aria-labelledby="research-path-title">
      <div className="path-head">
        <div>
          <div className="path-title" id="research-path-title">Research Path</div>
          <div className="path-sub">
            初始计划是执行前快照；实际路径只展示本 Run 已发生且有 projection record 的变化语义。
          </div>
        </div>
        <div className="path-meta" aria-label="研究路径统计">
          <span className="badge neutral">Initial {initialTasks.length}</span>
          <span className={addedTasks.length ? "badge purple" : "badge neutral"}>Added {addedTasks.length}</span>
          <span className={selfCorrections.length ? "badge amber" : "badge neutral"}>Corrections {selfCorrections.length}</span>
          <span className="badge neutral">Graph v{run.graphVersion}</span>
        </div>
      </div>

      <div className="rr-path-toolbar">
        <div className="segmented" role="tablist" aria-label="Research Path 视图">
          {(["actual", "initial", "compare"] as View[]).map((item, index, views) => (
            <button
              type="button"
              role="tab"
              id={`research-path-tab-${item}`}
              aria-controls={`research-path-panel-${item}`}
              aria-selected={view === item}
              tabIndex={view === item ? 0 : -1}
              key={item}
              className={view === item ? "active" : ""}
              onClick={() => setView(item)}
              onKeyDown={(event) => {
                if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
                event.preventDefault();
                const next = views[(index + (event.key === "ArrowRight" ? 1 : -1) + views.length) % views.length];
                setView(next);
                window.requestAnimationFrame(() => document.getElementById(`research-path-tab-${next}`)?.focus());
              }}
            >
              {item === "actual" ? "Actual Path" : item === "initial" ? "Initial Plan" : "Compare Changes"}
            </button>
          ))}
        </div>
        <div className="rr-path-actions">
          {observedTypes.length > 0 && <button type="button" className="btn ghost sm" onClick={() => setShowSemantics((open) => !open)}>
            {showSemantics ? "收起语义" : `本 Run 变化语义 (${observedTypes.length})`}
          </button>}
          <button type="button" className="btn ghost sm" onClick={() => setShowChanges((open) => !open)}>
            {showChanges ? "收起变化记录" : `变化记录 (${run.pathChanges.length})`}
          </button>
        </div>
      </div>

      {showSemantics && <MutationLegend types={observedTypes} />}

      <div className="path-body" id={`research-path-panel-${view}`} role="tabpanel" aria-labelledby={`research-path-tab-${view}`}>
        {view === "initial" && <InitialPath tasks={initialTasks} onOpenTask={onOpenTask} />}
        {view === "actual" && (run.mode === "INCREMENTAL" ? <IncrementalPath run={run} onOpenTask={onOpenTask} /> : <ActualPath run={run} tasks={run.tasks} onOpenTask={onOpenTask} />)}
        {view === "compare" && (
          <PathComparison initialTasks={initialTasks} actualTasks={run.tasks} onOpenTask={onOpenTask} />
        )}
      </div>

      {showChanges && (
        <PathChangeHistory
          changes={run.pathChanges}
          tasks={run.tasks}
          onOpenTask={onOpenTask}
        />
      )}
    </section>
  );
}

function MutationLegend({ types }: { types: PathChangeType[] }) {
  return (
    <div className="rr-mutation-legend" aria-label="路径变化类型说明">
      {types.map((type) => {
        const semantic = CHANGE_SEMANTICS[type];
        return (
          <div className={`rr-mutation-help ${semantic.tone}`} key={type}>
            <span className="rr-mutation-icon" aria-hidden="true">{semantic.icon}</span>
            <div>
              <strong>{semantic.label}</strong>
              <span>{semantic.description}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function IncrementalPath({ run, onOpenTask }: { run: ResearchRun; onOpenTask?: (task: ResearchTask) => void }) {
  const steps = ["Previous Research Memory", "Freshness Check", "Changed Data", "Growth Update", "Valuation Update", "Risk Update", "Claim Comparison", "Updated Result"];
  return <div className="incremental-path"><div className="incremental-path__banner"><div><strong>Incremental Research Path</strong><span>Demo / Pre-Integration projection · visually distinct from Full Research</span></div><span className="badge purple">Memory-aware</span></div><div className="incremental-flow">{steps.map((step, index) => { const task = run.tasks.find((candidate) => candidate.name === step); const content = <><span>{String(index + 1).padStart(2, "0")}</span><strong>{step}</strong><small>{task ? task.status : index === 0 ? run.memory?.sourceRunId : "Projection milestone"}</small></>; return task ? <button type="button" key={step} onClick={() => onOpenTask?.(task)}>{content}</button> : <div className="incremental-milestone" key={step}>{content}</div>; })}</div></div>;
}

function InitialPath({
  tasks,
  onOpenTask
}: {
  tasks: ResearchTask[];
  onOpenTask?: (task: ResearchTask) => void;
}) {
  return (
    <div className="path-cluster rr-path-cluster">
      <div className="path-cluster-title">
        <div>
          <strong>Initial Research Plan</strong>
          <div className="micro">执行开始前冻结的任务与依赖，不会被实际路径覆盖。</div>
        </div>
        <span className="badge neutral">Plan v1</span>
      </div>
      <div className="path-grid">
        {tasks.map((task) => (
          <TaskNode key={task.id} task={task} planned onOpenTask={onOpenTask} />
        ))}
      </div>
    </div>
  );
}

function ActualPath({
  run,
  tasks,
  onOpenTask
}: {
  run: ResearchRun;
  tasks: ResearchTask[];
  onOpenTask?: (task: ResearchTask) => void;
}) {
  const taskNames = new Map(tasks.map((task) => [task.id, task.name]));
  const correctionByTask = new Map<string, PathChange[]>();
  for (const change of run.pathChanges) {
    if (change.type !== "SELF_CORRECTION" || !change.triggerTaskId) continue;
    const entries = correctionByTask.get(change.triggerTaskId) ?? [];
    entries.push(change);
    correctionByTask.set(change.triggerTaskId, entries);
  }
  const structuralChanges = run.pathChanges.filter((change) => change.type !== "SELF_CORRECTION");
  const pathChanged = run.graphVersion > 1 || structuralChanges.length > 0 || tasks.some((task) => task.isDynamic);

  return (
    <>
      {structuralChanges.length > 0 && (
        <div className="auto-replan rr-auto-replan">
          <div>
            <strong>AI 已调整研究路径</strong>
            <div className="small">
              当前实际路径来自 Runtime projection；所有变化会保留到复核和执行记录。
            </div>
          </div>
          <span className="badge purple">{structuralChanges.length} Path Changes</span>
        </div>
      )}
      <div className="path-cluster rr-path-cluster">
        <div className="path-cluster-title">
          <div>
            <strong>Actual Research Path</strong>
            <div className="micro">任务卡仅代表正式研究任务；能力准备显示为任务内 supporting activity。</div>
          </div>
          <span className={pathChanged ? "badge purple" : "badge neutral"}>
            {pathChanged ? "Path changed" : "As planned"}
          </span>
        </div>
        <div className="path-grid">
          {tasks.map((task) => (
            <div className="rr-task-node-stack" key={task.id}>
              <TaskNode task={task} taskNames={taskNames} onOpenTask={onOpenTask} />
              {(correctionByTask.get(task.id) ?? []).map((change) => (
                <div className="rr-self-correction-loop" key={change.changeId}>
                  <span aria-hidden="true">↻</span>
                  <div>
                    <strong>原任务自我修正</strong>
                    <span>{change.reason} · {change.status}</span>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      {structuralChanges.length > 0 && (
        <div className="path-note">
          <strong>为什么与初始计划不同：</strong>{" "}
          {structuralChanges.map((change) => change.reason).join("；")}。
        </div>
      )}
    </>
  );
}

function TaskNode({
  task,
  planned = false,
  taskNames,
  onOpenTask
}: {
  task: ResearchTask;
  planned?: boolean;
  taskNames?: Map<string, string>;
  onOpenTask?: (task: ResearchTask) => void;
}) {
  const dependencies = task.dependsOn ?? [];
  const detail = dependencies.length > 0
    ? `依赖 ${dependencies.map((id) => taskNames?.get(id) ?? id).join("、")}`
    : planned ? "初始任务" : STATUS_LABELS[task.status];

  return (
    <button
      type="button"
      className={`branch-node rr-branch-node ${planned ? "planned" : taskTone(task)}`}
      onClick={() => onOpenTask?.(task)}
      aria-label={`打开任务 ${task.name}`}
    >
      <div className="rr-node-topline">
        <span className="micro">{task.id}</span>
        {task.isDynamic && <span className="flag">+ ADDED</span>}
      </div>
      <div className="bn">{task.name}</div>
      <div className="bs">{detail}</div>
      {!planned && <div className="rr-node-status">Status · {STATUS_LABELS[task.status]}</div>}
      {!planned && task.progress !== undefined && task.status !== "COMPLETED" && (
        <div className="rr-node-progress" role="progressbar" aria-label={`进度 ${task.progress}%`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={task.progress}>
          <span style={{ width: `${Math.max(0, Math.min(100, task.progress))}%` }} />
        </div>
      )}
      {!planned && task.supportingActivity && (
        <div className={`rr-supporting-activity ${task.supportingActivity.status.toLowerCase()}`}>
          <span aria-hidden="true">◇</span>
          <span>
            <strong>Supporting activity</strong>
            {task.supportingActivity.label}
          </span>
        </div>
      )}
    </button>
  );
}

function PathComparison({
  initialTasks,
  actualTasks,
  onOpenTask
}: {
  initialTasks: ResearchTask[];
  actualTasks: ResearchTask[];
  onOpenTask?: (task: ResearchTask) => void;
}) {
  return (
    <div className="path-compare rr-path-compare">
      <div className="path-compare-col">
        <h4>Initial Plan</h4>
        <div className="mini-flow">
          {initialTasks.map((task) => (
            <button type="button" className="mini-flow-row rr-mini-flow-row" key={task.id} onClick={() => onOpenTask?.(task)}>
              <span className="mini-dot" />
              <span><strong>{task.name}</strong><small>{task.dependsOn?.length ? `依赖 ${task.dependsOn.join("、")}` : "原始任务"}</small></span>
            </button>
          ))}
        </div>
      </div>
      <div className="path-compare-col">
        <h4>Actual Path</h4>
        <div className="mini-flow">
          {actualTasks.map((task) => {
            const initial = initialTasks.find((candidate) => candidate.id === task.id);
            const dependencyChanged = Boolean(initial && !sameDependencies(initial.dependsOn, task.dependsOn));
            return (
              <button type="button" className="mini-flow-row rr-mini-flow-row" key={task.id} onClick={() => onOpenTask?.(task)}>
                <span className={`mini-dot ${task.isDynamic ? "purple" : dependencyChanged ? "amber" : task.status === "COMPLETED" ? "green" : ""}`} />
                <span>
                  <strong>{task.isDynamic ? "+ " : ""}{task.name}</strong>
                  <small>
                    {task.isDynamic ? "ADDED by graph.task_added" : dependencyChanged ? "Dependency changed" : STATUS_LABELS[task.status]}
                  </small>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function PathChangeHistory({
  changes,
  tasks,
  onOpenTask
}: {
  changes: PathChange[];
  tasks: ResearchTask[];
  onOpenTask?: (task: ResearchTask) => void;
}) {
  const taskById = new Map(tasks.map((task) => [task.id, task]));

  return (
    <div className="rr-path-history">
      <div className="rr-section-heading">
        <div>
          <strong>Path Change History</strong>
          <span>变化在 Run 完成后仍可审计；自纠不会生成新任务卡。</span>
        </div>
        <span className="badge neutral">{changes.length} records</span>
      </div>
      {changes.length === 0 ? (
        <div className="rr-path-empty">实际执行与初始计划一致，暂无路径变化。</div>
      ) : changes.map((change) => {
        const semantic = CHANGE_SEMANTICS[change.type];
        const trigger = change.triggerTaskId ? taskById.get(change.triggerTaskId) : undefined;
        const relatedIds = [...(change.addedTaskIds ?? []), ...(change.affectedTaskIds ?? [])];
        return (
          <div className={`path-change rr-path-change ${semantic.tone}`} key={change.changeId}>
            <div className="pc-type">
              <span className={`rr-change-chip ${semantic.tone}`}>
                <span aria-hidden="true">{semantic.icon}</span>{semantic.shortLabel}
              </span>
            </div>
            <div>
              <div className="pc-title">{change.reason}</div>
              <div className="pc-sub">
                {change.type === "SELF_CORRECTION" ? "原任务内修复" : semantic.description}
                {" · "}{formatTimestamp(change.createdAt)}
              </div>
              {(trigger || relatedIds.length > 0) && (
                <div className="rr-change-links">
                  {trigger && (
                    <button type="button" onClick={() => onOpenTask?.(trigger)}>
                      触发：{trigger.name}
                    </button>
                  )}
                  {relatedIds.map((id) => {
                    const task = taskById.get(id);
                    return task ? (
                      <button type="button" key={id} onClick={() => onOpenTask?.(task)}>
                        {change.addedTaskIds?.includes(id) ? "新增" : "影响"}：{task.name}
                      </button>
                    ) : <span key={id}>{id}</span>;
                  })}
                </div>
              )}
            </div>
            <span className={`badge ${change.status === "OPEN" ? "amber" : change.status === "RESOLVED" ? "green" : "purple"}`}>
              {change.status}
            </span>
          </div>
        );
      })}
    </div>
  );
}
