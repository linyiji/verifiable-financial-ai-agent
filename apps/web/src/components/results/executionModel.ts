import type {
  ExecutionActorDetailV1,
  ExecutionActorSummaryV1,
  ExecutionRecordSurfaceV1,
  ReportContributionRefV1
} from "../../types/domain";

export type ExecutionActorGroupKey = "RESEARCH_LEAD" | "SPECIALIST" | "SUPPORTING_EXECUTION";

export interface ExecutionActorGroup {
  readonly groupKey: ExecutionActorGroupKey;
  readonly title: string;
  readonly actors: readonly ExecutionActorSummaryV1[];
}

export interface ExecutionRecordCard {
  readonly taskId: string;
  readonly event: ExecutionActorDetailV1["observableProcess"][number] | null;
  readonly output: ExecutionActorDetailV1["outputs"][number] | null;
  readonly contribution: ReportContributionRefV1 | null;
}

const GROUPS: readonly Readonly<{ key: ExecutionActorGroupKey; title: string }>[] = [
  { key: "RESEARCH_LEAD", title: "Research Lead" },
  { key: "SPECIALIST", title: "Specialists" },
  { key: "SUPPORTING_EXECUTION", title: "Supporting Execution" }
];

export function groupExecutionActors(execution: ExecutionRecordSurfaceV1): readonly ExecutionActorGroup[] {
  return GROUPS.flatMap((group) => {
    const actors = execution.actors
      .filter((actor) => actor.actorType === group.key && actor.runId === execution.runId)
      .sort((left, right) => left.displayRole.localeCompare(right.displayRole) || left.actorId.localeCompare(right.actorId));
    return actors.length === 0 ? [] : [{ groupKey: group.key, title: group.title, actors }];
  });
}

export function defaultExecutionActor(execution: ExecutionRecordSurfaceV1): ExecutionActorSummaryV1 | null {
  const catalog = groupExecutionActors(execution).flatMap((group) => group.actors);
  return catalog.find((actor) => actor.actorType === "RESEARCH_LEAD") ?? catalog[0] ?? null;
}

export function exactExecutionActor(execution: ExecutionRecordSurfaceV1, actorId: string): Readonly<{
  actor: ExecutionActorSummaryV1;
  detail: ExecutionActorDetailV1 | null;
}> | null {
  const actors = execution.actors.filter((actor) => actor.actorId === actorId && actor.runId === execution.runId);
  if (actors.length !== 1) return null;
  const actor = actors[0];
  const details = execution.actorDetails.filter((detail) =>
    detail.actorId === actor.actorId && detail.actorType === actor.actorType && detail.runId === execution.runId
  );
  if (details.length > 1) return null;
  return { actor, detail: details[0] ?? null };
}

export function executionRecordCards(detail: ExecutionActorDetailV1): readonly ExecutionRecordCard[] {
  const safeEvents = detail.observableProcess.filter((event) => event.runId === detail.runId);
  const safeOutputs = detail.outputs.filter((output) => output.runId === detail.runId);
  const taskIds = new Set<string>();
  for (const event of safeEvents) if (event.taskId !== null) taskIds.add(event.taskId);
  for (const output of safeOutputs) taskIds.add(output.taskId);
  return [...taskIds].sort().map((taskId) => {
    const events = safeEvents.filter((event) => event.taskId === taskId);
    const outputs = safeOutputs.filter((output) => output.taskId === taskId);
    const event = events.length === 1 ? events[0] : null;
    const output = outputs.length === 1 ? outputs[0] : null;
    const contributions = output === null || event === null ? [] : detail.reportContributions.filter((item) =>
      item.runId === detail.runId && item.actorId === detail.actorId && item.taskId === taskId &&
      item.agentOutputId === output.outputId && item.executionEventId === event?.eventId
    );
    return { taskId, event, output, contribution: contributions.length === 1 ? contributions[0] : null };
  });
}

export function exactExecutionTarget(
  execution: ExecutionRecordSurfaceV1,
  actorId: string,
  outputId: string,
  eventId: string
) {
  const selected = exactExecutionActor(execution, actorId);
  if (selected === null || selected.detail === null) return null;
  const outputs = selected.detail.outputs.filter((item) => item.outputId === outputId && item.runId === execution.runId);
  const events = selected.detail.observableProcess.filter((item) => item.eventId === eventId && item.runId === execution.runId);
  if (outputs.length !== 1 || events.length !== 1 || outputs[0].taskId !== events[0].taskId) return null;
  const output = outputs[0];
  const event = events[0];
  const contributions = selected.detail.reportContributions.filter((item) =>
    item.runId === execution.runId && item.actorId === actorId && item.taskId === output.taskId &&
    item.agentOutputId === outputId && item.executionEventId === eventId
  );
  if (contributions.length > 1) return null;
  return { ...selected, output, event, contribution: contributions[0] ?? null };
}

export function filterExecutionActors(
  groups: readonly ExecutionActorGroup[],
  query: string
): readonly ExecutionActorGroup[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (normalized.length === 0) return groups;
  return groups.flatMap((group) => {
    const actors = group.actors.filter((actor) =>
      `${actor.displayRole} ${actor.actorId} ${actor.status} ${actor.actorType}`.toLocaleLowerCase().includes(normalized)
    );
    return actors.length === 0 ? [] : [{ ...group, actors }];
  });
}

export function inputRefKind(refId: string): string {
  if (refId.startsWith("AGOUT-")) return "Agent Output";
  if (refId.startsWith("CALC-")) return "Calculation";
  if (refId.startsWith("EVD-")) return "Evidence";
  if (refId.startsWith("GOAL-")) return "Goal";
  if (refId.startsWith("SCHEME-")) return "Scheme";
  if (refId.includes(":")) return "Task";
  return "Reference";
}

export function observableExecutionRows(execution: ExecutionRecordSurfaceV1) {
  return execution.actorDetails.flatMap((detail) => {
    if (detail.runId !== execution.runId) return [];
    const actor = execution.actors.find((item) =>
      item.actorId === detail.actorId && item.actorType === detail.actorType && item.runId === execution.runId
    );
    if (actor === undefined) return [];
    return detail.observableProcess.filter((event) => event.runId === execution.runId).map((event) => ({ actor, event }));
  }).sort((left, right) => left.actor.actorId.localeCompare(right.actor.actorId) || left.event.eventId.localeCompare(right.event.eventId));
}
