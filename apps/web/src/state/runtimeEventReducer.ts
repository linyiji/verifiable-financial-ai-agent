import type {
  PathChange,
  PathChangeType,
  ResearchClaim,
  ResearchTask,
  ReviewRecord,
  RuntimeEvent,
  RuntimeProjection
} from "../types/domain";

const stringValue = (value: unknown, fallback = "") => typeof value === "string" ? value : fallback;
const numberValue = (value: unknown, fallback = 0) => typeof value === "number" ? value : fallback;
const stringList = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

function mutationType(value: unknown, fallback: PathChangeType): PathChangeType | undefined {
  const values: PathChangeType[] = ["SELF_CORRECTION", "ADD_TASK", "CHANGE_DEPENDENCY"];
  if (value === undefined || value === null || value === "") return fallback;
  return typeof value === "string" && values.includes(value as PathChangeType) ? value as PathChangeType : undefined;
}

function upsertPathChange(run: RuntimeProjection["run"], change: PathChange) {
  const index = run.pathChanges.findIndex((item) => item.changeId === change.changeId);
  if (index >= 0) run.pathChanges[index] = { ...run.pathChanges[index], ...change };
  else run.pathChanges.push(change);
}

function upsertReview(reviews: ReviewRecord[], record: ReviewRecord) {
  const index = reviews.findIndex((item) => item.reviewId === record.reviewId);
  if (index >= 0) reviews[index] = { ...reviews[index], ...record };
  else reviews.push(record);
}

function observableStatus(eventType: RuntimeEvent["type"]): "DONE" | "LIVE" | "WAITING" | "WARNING" {
  if (["task.completed", "correction.resolved", "capability.approved"].includes(eventType)) return "DONE";
  if (eventType === "task.waiting_for_capability" || eventType === "capability.validating") return "WAITING";
  if (eventType === "task.self_correcting" || eventType === "graph.task_added") return "WARNING";
  return "LIVE";
}

function belongsToProjection(value: { objectId: string; symbol: string; runId: string }, state: RuntimeProjection) {
  return value.objectId === state.run.objectId && value.symbol === state.run.symbol && value.runId === state.run.id;
}

function markFact(state: RuntimeProjection, label: string, value: string) {
  const fact = state.run.projectionFacts.find((item) => item.label === label);
  if (fact) Object.assign(fact, { value, status: "AVAILABLE" as const });
}

const PLACEHOLDER_VALUE = /\b(?:unavailable|not generated|missing_projection|has not been generated)\b|^\s*[-—]\s*$/i;

const isMaterialValue = (value: string | undefined) => Boolean(value && !PLACEHOLDER_VALUE.test(value));

/** Structural ownership is necessary but not sufficient for publication. */
export function isSemanticReleaseReady(state: RuntimeProjection) {
  const preview = state.reportArtifact.preview;
  const requiredMetrics = ["Revenue Growth", "EBITDA Margin"];
  const reviewedClaims = state.reviews.filter((record) => record.kind === "CLAIM");
  return [preview.rating, preview.price, preview.target, preview.thesis].every(isMaterialValue)
    && requiredMetrics.every((label) => isMaterialValue(preview.metrics.find((metric) => metric.label === label)?.value))
    && preview.sections.length > 0
    && preview.sections.every((section) => (section.paragraphs ?? []).every((paragraph) => isMaterialValue(paragraph.text)))
    && state.claims.length > 0
    && state.claims.every((claim) => isMaterialValue(claim.title) && isMaterialValue(claim.summary))
    && reviewedClaims.length === state.claims.length
    && reviewedClaims.every((record) => record.status === "PASS" || record.status === "PASS_WITH_UNCERTAINTY");
}

function releaseContractReady(state: RuntimeProjection) {
  const hasMaterialClaims = state.claims.length > 0 && state.claims.every((claim) =>
    state.reviews.some((record) => record.kind === "CLAIM" && record.claimId === claim.claimId && record.status === claim.reviewStatus)
  );
  return state.reportArtifact.status === "READY"
    && state.reportArtifact.preview.sections.length > 0
    && hasMaterialClaims
    && isSemanticReleaseReady(state)
    && state.execution.status === "TERMINAL"
    && state.releasedResult.status === "PREPARING";
}

/**
 * The sole runtime projection reducer. `release.completed` is a guarded atomic
 * transition; no timer or page component can independently mark a Run complete.
 */
export function reduceRuntimeEvent(state: RuntimeProjection, event: RuntimeEvent): RuntimeProjection {
  if (event.run_id !== state.run.id || state.events.some((item) => item.event_id === event.event_id)) return state;

  const next = structuredClone(state);
  const run = next.run;
  const payload = event.payload;
  const task = event.task_id ? run.tasks.find((item) => item.id === event.task_id) : undefined;
  let releaseApplied = false;
  next.events.push(event);
  next.events.sort((a, b) => a.sequence - b.sequence);
  next.lastSequence = Math.max(next.lastSequence, event.sequence);
  next.execution.runtimeEventCount = next.events.length;
  run.updatedAt = event.timestamp;

  switch (event.type) {
    case "plan.generated":
      run.stage = "research";
      run.status = "RESEARCHING";
      run.researchStep = "collect";
      break;
    case "task.started":
      if (task) task.status = "RUNNING";
      break;
    case "task.progress":
      if (task) {
        task.status = "RUNNING";
        task.progress = numberValue(payload.progress, task.progress ?? 0);
        task.summary = stringValue(payload.message, task.summary);
      }
      if (payload.fact === "DATA_ACQUIRED") markFact(next, "Financial data", "Acquired");
      break;
    case "task.waiting_for_capability":
      if (task) {
        const capabilityId = stringValue(payload.capability_id, `${run.id}-CAP-UNAVAILABLE`);
        task.status = "WAITING";
        task.supportingActivity = {
          capabilityId, kind: "WAITING_FOR_CAPABILITY", label: stringValue(payload.message, "等待能力准备"), status: "RUNNING",
          lifecycle: [{ status: "PREPARING", label: "Capability preparing", timestamp: event.timestamp }]
        };
      }
      break;
    case "capability.validating":
      if (task?.supportingActivity) {
        task.supportingActivity.kind = "CAPABILITY_VALIDATION";
        task.supportingActivity.label = stringValue(payload.message, task.supportingActivity.label);
        task.supportingActivity.lifecycle.push({ status: "VALIDATING", label: "Capability validating", timestamp: event.timestamp });
      }
      break;
    case "capability.approved":
      if (task?.supportingActivity) {
        task.supportingActivity.status = "COMPLETED";
        task.supportingActivity.label = stringValue(payload.message, "能力已批准，原任务恢复");
        task.supportingActivity.lifecycle.push(
          { status: "APPROVED", label: "Capability approved", timestamp: event.timestamp },
          { status: "RESUMED", label: "Original task resumed", timestamp: event.timestamp }
        );
        task.status = "RUNNING";
      }
      break;
    case "task.self_correcting": {
      if (task) task.status = "SELF_CORRECTING";
      const changeId = stringValue(payload.change_id, event.event_id);
      upsertPathChange(run, { changeId, type: "SELF_CORRECTION", reason: stringValue(payload.reason, "Task self-correction"), status: "OPEN", triggerTaskId: event.task_id, createdAt: event.timestamp });
      break;
    }
    case "correction.resolved": {
      if (task) {
        task.status = "RUNNING";
        task.correctionSummary = stringValue(payload.reason, "Correction resolved");
      }
      const changeId = stringValue(payload.change_id, event.event_id);
      const existing = run.pathChanges.find((item) => item.changeId === changeId);
      upsertPathChange(run, { changeId, type: existing?.type ?? "SELF_CORRECTION", reason: existing?.reason ?? stringValue(payload.reason, "Correction resolved"), status: "RESOLVED", triggerTaskId: existing?.triggerTaskId ?? event.task_id, createdAt: existing?.createdAt ?? event.timestamp, resolvedAt: event.timestamp });
      markFact(next, "Period validation", "Passed after correction");
      break;
    }
    case "replan.requested": {
      const changeId = stringValue(payload.change_id, event.event_id);
      const type = mutationType(payload.mutation_type, "CHANGE_DEPENDENCY");
      if (!type) {
        run.status = "ACTION_REQUIRED";
        run.currentActivity = `Unsupported path mutation · ${stringValue(payload.mutation_type, "UNKNOWN")}`;
        next.execution.releaseGate = "FAILED";
        break;
      }
      upsertPathChange(run, { changeId, type, reason: stringValue(payload.reason, "Research path adjustment requested"), status: "OPEN", triggerTaskId: event.task_id, affectedTaskIds: stringList(payload.affected_task_ids), createdAt: event.timestamp });
      if (task) task.replanSummary = stringValue(payload.reason, "Replan requested");
      break;
    }
    case "replan.approved": {
      const changeId = stringValue(payload.change_id, event.event_id);
      const existing = run.pathChanges.find((item) => item.changeId === changeId);
      const type = existing?.type ?? mutationType(payload.mutation_type, "CHANGE_DEPENDENCY");
      if (!type) {
        run.status = "ACTION_REQUIRED";
        run.currentActivity = `Unsupported path mutation · ${stringValue(payload.mutation_type, "UNKNOWN")}`;
        next.execution.releaseGate = "FAILED";
        break;
      }
      upsertPathChange(run, { changeId, type, reason: existing?.reason ?? stringValue(payload.reason, "Research path adjusted"), status: "APPROVED", triggerTaskId: existing?.triggerTaskId ?? event.task_id, affectedTaskIds: existing?.affectedTaskIds ?? stringList(payload.affected_task_ids), createdAt: existing?.createdAt ?? event.timestamp });
      break;
    }
    case "graph.task_added": {
      const addedTaskId = event.task_id ?? stringValue(payload.task_id);
      if (addedTaskId && !run.tasks.some((item) => item.id === addedTaskId)) {
        const added: ResearchTask = {
          objectId: run.objectId, symbol: run.symbol, runId: run.id, id: addedTaskId,
          name: stringValue(payload.name, "Additional research"), agentLabel: "Additional Peer Evidence",
          skillLabel: "Peer Evidence Skill", toolLabels: ["Demo Financial Projection"], status: "READY",
          summary: stringValue(payload.summary, "由 Research Lead 动态加入"), isDynamic: true,
          dependsOn: stringList(payload.depends_on), evidenceRefs: [], calculationRefs: []
        };
        run.tasks.push(added);
        next.execution.entries.push({ taskId: added.id, title: added.agentLabel!, summary: added.summary!, anchor: `execution-${added.id}`, claimIds: [] });
        next.execution.actualTaskCount = run.tasks.length;
      }
      const changeId = stringValue(payload.change_id, event.event_id);
      upsertPathChange(run, { changeId, type: "ADD_TASK", reason: stringValue(payload.reason, "Evidence gap"), status: "APPLIED", triggerTaskId: stringValue(payload.trigger_task_id) || undefined, addedTaskIds: addedTaskId ? [addedTaskId] : [], affectedTaskIds: stringList(payload.affected_task_ids), createdAt: event.timestamp });
      break;
    }
    case "graph.version_changed": {
      run.graphVersion = numberValue(payload.graph_version, run.graphVersion + 1);
      const dependencies = payload.dependencies;
      const affectedTaskIds: string[] = [];
      if (dependencies && typeof dependencies === "object") {
        for (const [affectedTaskId, value] of Object.entries(dependencies)) {
          const affected = run.tasks.find((item) => item.id === affectedTaskId);
          if (affected) {
            affected.dependsOn = stringList(value);
            affectedTaskIds.push(affectedTaskId);
          }
        }
      }
      const parentChangeId = stringValue(payload.change_id, event.event_id);
      const parent = run.pathChanges.find((item) => item.changeId === parentChangeId);
      if (parent) parent.status = "APPLIED";
      upsertPathChange(run, {
        changeId: `${parentChangeId}-DEPENDENCY`, type: "CHANGE_DEPENDENCY", reason: "Valuation dependency updated to the added evidence task",
        status: "APPLIED", triggerTaskId: parent?.triggerTaskId, affectedTaskIds, createdAt: event.timestamp
      });
      break;
    }
    case "task.completed":
      if (task) {
        task.status = "COMPLETED";
        task.progress = 100;
        task.summary = stringValue(payload.message, task.summary);
        const entry = next.execution.entries.find((item) => item.taskId === task.id);
        if (entry) entry.summary = task.summary ?? entry.summary;
      }
      break;
    case "review.started":
      run.stage = "review";
      run.status = "REVIEWING";
      next.execution.status = "IN_PROGRESS";
      break;
    case "claim.materialized": {
      const claim = payload.claim as ResearchClaim | undefined;
      const review = payload.review as ReviewRecord | undefined;
      if (claim && belongsToProjection(claim, next) && !next.claims.some((item) => item.claimId === claim.claimId)) next.claims.push(structuredClone(claim));
      if (review && belongsToProjection(review, next)) upsertReview(next.reviews, structuredClone(review));
      break;
    }
    case "review.required": {
      run.stage = "review";
      run.status = payload.requires_user === true ? "ACTION_REQUIRED" : "REVIEWING";
      const reviewId = stringValue(payload.review_id, event.event_id);
      upsertReview(next.reviews, {
        objectId: run.objectId, symbol: run.symbol, runId: run.id, reviewId,
        claimId: stringValue(payload.claim_id) || undefined, title: stringValue(payload.title, "Financial review required"),
        status: payload.blocking === true ? "BLOCK" : "REVIEW", kind: "EXCEPTION",
        summary: stringValue(payload.message, "等待复核修正"), taskId: event.task_id, anchor: `review-${reviewId}`
      });
      break;
    }
    case "review.resolved": {
      const reviewId = stringValue(payload.review_id, event.event_id);
      const existing = next.reviews.find((item) => item.reviewId === reviewId);
      upsertReview(next.reviews, {
        objectId: run.objectId, symbol: run.symbol, runId: run.id, reviewId,
        claimId: existing?.claimId ?? (stringValue(payload.claim_id) || undefined), title: existing?.title ?? stringValue(payload.title, "Review exception resolved"),
        status: "RESOLVED", kind: "EXCEPTION", summary: stringValue(payload.message, existing?.summary ?? "异常已修复"),
        taskId: existing?.taskId ?? event.task_id, anchor: existing?.anchor ?? `review-${reviewId}`,
        correctionPath: existing?.correctionPath, resolvedAt: event.timestamp
      });
      if (run.status === "ACTION_REQUIRED") run.status = "REVIEWING";
      break;
    }
    case "report.started":
      run.stage = "report";
      run.status = "GENERATING_REPORT";
      next.reportArtifact.status = "PENDING";
      next.execution.releaseGate = "PENDING";
      break;
    case "result.prepared": {
      const artifact = payload.reportArtifact as RuntimeProjection["reportArtifact"] | undefined;
      if (artifact && belongsToProjection(artifact, next)) {
        next.reportArtifact = structuredClone(artifact);
        const semanticReady = isSemanticReleaseReady(next);
        next.reportArtifact.status = semanticReady ? "READY" : "ERROR";
        next.reportArtifact.generatedAt = semanticReady ? event.timestamp : undefined;
        if (!semanticReady) {
          next.reportArtifact.htmlDownloadUrl = undefined;
          next.reportArtifact.pdfDownloadUrl = undefined;
          next.execution.releaseGate = "FAILED";
        }
      } else {
        next.reportArtifact.status = "PENDING";
      }
      next.execution.status = "TERMINAL";
      if (next.reportArtifact.status !== "ERROR") next.execution.releaseGate = "PENDING";
      next.releasedResult.status = "PREPARING";
      run.status = "RESULT_PREPARING";
      const reportFact = run.projectionFacts.find((fact) => fact.label === "Report chapters");
      if (reportFact) {
        reportFact.value = next.reportArtifact.status === "READY"
          ? `${next.reportArtifact.preview.sections.length} ready`
          : "Blocked · subject-owned financial evidence is unavailable";
        reportFact.status = next.reportArtifact.status === "READY" ? "AVAILABLE" : "UNAVAILABLE";
      }
      break;
    }
    case "release.completed":
      if (releaseContractReady(next)) {
        run.stage = "completed";
        run.status = "COMPLETED";
        run.researchStep = "synthesis";
        run.progress = 100;
        next.execution.status = "RELEASED";
        next.execution.releaseGate = "PASSED";
        next.releasedResult.status = "AVAILABLE";
        next.releasedResult.releasedAt = event.timestamp;
        releaseApplied = true;
      } else {
        run.status = "RESULT_PREPARING";
        run.currentActivity = next.reportArtifact.status === "ERROR"
          ? "Release blocked · subject-owned financial evidence is unavailable or unvalidated"
          : "Release contract waiting for Report, Review, Execution and Result consistency";
      }
      break;
    case "task.created":
      break;
  }

  const progress = payload.run_progress;
  if (typeof progress === "number" && event.type !== "release.completed") run.progress = progress;
  const activity = payload.message;
  if (typeof activity === "string" && !(event.type === "release.completed" && !releaseApplied)) run.currentActivity = activity;
  const researchStep = payload.research_step;
  if (["collect", "prepare", "financial", "analysis", "synthesis"].includes(String(researchStep))) run.researchStep = researchStep as RuntimeProjection["run"]["researchStep"];

  const timelineTask = event.task_id ? run.tasks.find((item) => item.id === event.task_id) : undefined;
  if (timelineTask && event.type !== "task.created") {
    const events = timelineTask.observableEvents ?? [];
    if (!events.some((item) => item.id === event.event_id)) {
      events.push({ id: event.event_id, title: stringValue(payload.message, event.type), meta: event.type, status: observableStatus(event.type), timestamp: event.timestamp, anchor: event.type.replaceAll(".", "-") });
      timelineTask.observableEvents = events;
    }
  }
  return next;
}
