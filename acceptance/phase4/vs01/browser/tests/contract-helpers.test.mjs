import assert from "node:assert/strict";
import test from "node:test";
import {
  admitContextProjection,
  assertAdmissionReplayStable,
  assertAtomicProjectionEtag,
  assertNoDemoFallback,
  assertNoPublicSurfaceLeaks,
  assertNoSecondStartRequest,
  ContractViolation,
  decodeAtomicRunProjection,
  decodeConfirmRunResponse,
  decodeErrorEnvelope,
  decodePreparedResearchDraft,
  decodeReleasedFinancialMetricEvidence,
  findFrontendFinancialAuthority,
  findPublicSurfaceLeaks,
  expectedAtomicProjectionEtag,
  isAdversarialCanonicalDecimal
} from "../src/contracts.mjs";

const hash = (character) => `sha256:${character.repeat(64)}`;

function draftWire() {
  return {
    schema_version: "phase4-run-draft/v1",
    draft_id: "DRAFT-A",
    draft_version: 1,
    status: "AWAITING_CONFIRMATION",
    preview_kind: "SCHEME_ONLY",
    planned_graph_availability: {
      status: "NOT_GENERATED",
      reason_code: "PLAN_CREATED_ON_CONFIRM",
      retryable: false
    },
    object_id: "OBJ-A",
    goal: {
      goal_id: "GOAL-A",
      research_object_id: "OBJ-A",
      goal_text: "Assess A",
      goal_type: "comprehensive_equity_research",
      as_of: "2026-09-05",
      preferences: {},
      created_at: "2026-09-05T00:00:00Z"
    },
    scheme_snapshot: {
      scheme_id: "SCHEME-A",
      research_object_id: "OBJ-A",
      goal_id: "GOAL-A",
      research_scope: [],
      data_requirements: [],
      agent_requirements: [],
      skill_requirements: [],
      calculation_requirements: [],
      assurance_requirements: {},
      report_requirements: [],
      limitations: [],
      generated_by: "backend-planner",
      generated_model: null,
      created_at: "2026-09-05T00:00:00Z",
      confirmed_at: null
    },
    prepare_request_hash: hash("a"),
    draft_hash: hash("b"),
    created_at: "2026-09-05T00:00:00Z",
    expires_at: "2026-09-05T00:30:00Z"
  };
}

function confirmWire(replayed = false) {
  return {
    schema_version: "phase4-confirm-response/v1",
    admission: {
      schema_version: "phase4-run-admission/v1",
      admission_id: "ADMISSION-A",
      run_id: "RUN-A",
      object_id: "OBJ-A",
      draft_id: "DRAFT-A",
      draft_version: 1,
      draft_hash: hash("b"),
      goal_id: "GOAL-A",
      scheme_id: "SCHEME-A",
      planned_graph_id: "GRAPH-A-PLANNED",
      status: "PLANNING",
      auto_start: { required: true, admitted: true },
      confirmation_request_hash: hash("c"),
      admitted_at: "2026-09-05T00:00:01Z",
      projection_ref: "/api/research-runs/RUN-A/projection",
      events_ref: "/api/research-runs/RUN-A/events"
    },
    response_meta: {
      schema_version: "phase4-response-meta/v1",
      request_id: "REQUEST-A",
      idempotency_replayed: replayed
    }
  };
}

function taskWire(taskId, status, dependencies = [], progress = 0, parentTaskId = null) {
  return {
    task_id: taskId,
    run_id: "RUN-A",
    research_object_id: "OBJ-A",
    parent_task_id: parentTaskId,
    status,
    progress,
    dependencies
  };
}

function availability(status = "PENDING", reasonCode = "RUN_NONTERMINAL") {
  return { status, reason_code: reasonCode, retryable: false };
}

function projectionWire() {
  const plannedTasks = [
    taskWire("TASK-A", "CREATED"),
    taskWire("TASK-B", "CREATED", ["TASK-A"])
  ];
  const actualTasks = [
    taskWire("TASK-A", "RUNNING", [], 0.25),
    taskWire("TASK-B", "WAITING", ["TASK-A"])
  ];
  return {
    projection_schema_version: "phase4-run-projection/v1",
    projection_revision: 1,
    projection_sequence: 2,
    generated_at: "2026-09-05T00:00:02Z",
    object: {
      object_id: "OBJ-A",
      symbol: "AAA",
      company_name: "A Corp",
      object_type: "public_company",
      exchange: "NASDAQ",
      sector: null,
      currency: "USD",
      identity_version: 1
    },
    run: {
      run_id: "RUN-A",
      research_object_id: "OBJ-A",
      goal_id: "GOAL-A",
      scheme_id: "SCHEME-A",
      status: "PLANNING",
      stage: "PLANNING",
      as_of: "2026-09-05",
      planned_graph_id: "GRAPH-A-PLANNED",
      actual_graph_id: "GRAPH-A-ACTUAL",
      execution_target: "SERVER_SANDBOX",
      created_at: "2026-09-05T00:00:01Z",
      started_at: null,
      completed_at: null,
      updated_at: "2026-09-05T00:00:02Z"
    },
    goal: {
      goal_id: "GOAL-A",
      research_object_id: "OBJ-A",
      goal_type: "comprehensive_equity_research",
      goal_text: "Assess A",
      as_of: "2026-09-05",
      preferences: {},
      created_at: "2026-09-05T00:00:00Z"
    },
    confirmed_scheme: {
      scheme_id: "SCHEME-A",
      goal_id: "GOAL-A",
      research_object_id: "OBJ-A",
      research_scope: [],
      data_requirements: [],
      agent_requirements: [],
      skill_requirements: [],
      calculation_requirements: [],
      assurance_requirements: {},
      report_requirements: [],
      limitations: [],
      generated_by: "backend-planner",
      generated_model: null,
      created_at: "2026-09-05T00:00:00Z",
      confirmed_at: "2026-09-05T00:00:01Z"
    },
    planned_graph: {
      graph_id: "GRAPH-A-PLANNED",
      run_id: "RUN-A",
      version: 1,
      tasks: plannedTasks
    },
    actual_graph: {
      graph_id: "GRAPH-A-ACTUAL",
      run_id: "RUN-A",
      version: 1,
      tasks: actualTasks
    },
    graph_version: 1,
    tasks: structuredClone(actualTasks),
    path_changes: [],
    activity: [],
    lifecycle: {
      status: "PLANNING",
      stage: "PLANNING",
      progress: {
        method: "ACTUAL_TASK_MEAN_V1",
        completed_tasks: 0,
        total_tasks: 2,
        fraction: 0.125
      },
      terminal: false,
      terminal_outcome: null,
      safe_failure: null
    },
    review: { availability: availability(), review_id: null, status: null },
    result: {
      availability: availability(),
      released_result_id: null,
      canonical_record_id: null,
      released_at: null
    },
    artifacts: {
      availability: availability("NOT_GENERATED"),
      report_id: null,
      representation_ids: []
    },
    proof: {
      availability: availability("NOT_GENERATED"),
      policy: "UNKNOWN",
      status: null,
      proof_refs: []
    },
    execution: { availability: availability("NOT_GENERATED"), canonical_record_id: null },
    terminal: { is_terminal: false, outcome: null, event_id: null, sequence: null }
  };
}

const expectedDraft = {
  objectId: "OBJ-A",
  goalText: "Assess A",
  asOf: "2026-09-05",
  preferences: {}
};

test("frozen draft, confirmation, and projection admit one identity-closed journey", () => {
  const draft = decodePreparedResearchDraft(draftWire(), expectedDraft);
  const confirmation = decodeConfirmRunResponse(confirmWire(), draft);
  const projection = decodeAtomicRunProjection(projectionWire(), confirmation.admission);
  assert.equal(draft.previewKind, "SCHEME_ONLY");
  assert.equal(draft.plannedGraphAvailability.status, "NOT_GENERATED");
  assert.deepEqual(confirmation.admission.autoStart, { required: true, admitted: true });
  assert.equal(projection.runId, confirmation.admission.runId);
  assert.deepEqual(projection.taskIds, ["TASK-A", "TASK-B"]);
  assert.deepEqual(projection.tasks, [
    { taskId: "TASK-A", runId: "RUN-A", status: "RUNNING", progress: 0.25, parentTaskId: null, dependencyIds: [] },
    { taskId: "TASK-B", runId: "RUN-A", status: "WAITING", progress: 0, parentTaskId: null, dependencyIds: ["TASK-A"] }
  ]);
  assert.equal(projection.plannedGraph.runId, "RUN-A");
  assert.deepEqual(projection.actualGraph.edges, [
    { sourceTaskId: "TASK-A", targetTaskId: "TASK-B" }
  ]);
  assert.equal(expectedAtomicProjectionEtag(projection), '"p4:RUN-A:1:2"');
  assert.doesNotThrow(() => assertAtomicProjectionEtag('"p4:RUN-A:1:2"', projection));
  assert.throws(() => assertAtomicProjectionEtag('"p4:RUN-A:1:3"', projection), ContractViolation);
  assert.ok(Object.isFrozen(projection.tasks));
  assert.ok(Object.isFrozen(projection.tasks[1].dependencyIds));
  assert.ok(Object.isFrozen(confirmation.admission));
});

test("draft decoder rejects local Tasks, wrong Object/Goal/Scheme, and pre-confirmed Scheme", () => {
  for (const mutate of [
    (wire) => { wire.tasks = []; },
    (wire) => { wire.object_id = "OBJ-B"; },
    (wire) => { wire.goal.research_object_id = "OBJ-B"; },
    (wire) => { wire.scheme_snapshot.goal_id = "GOAL-B"; },
    (wire) => { wire.scheme_snapshot.confirmed_at = "2026-09-05T00:00:00Z"; },
    (wire) => { delete wire.goal.as_of; },
    (wire) => { wire.goal.as_of = "2026-02-30"; },
    (wire) => { wire.goal.preferences = { unexpected: true }; },
    (wire) => { wire.goal.extra = "not frozen"; },
    (wire) => { wire.scheme_snapshot.research_scope = {}; },
    (wire) => { wire.scheme_snapshot.data_requirements = [42]; },
    (wire) => { wire.scheme_snapshot.assurance_requirements = []; },
    (wire) => { wire.scheme_snapshot.generated_model = 42; },
    (wire) => { delete wire.scheme_snapshot.report_requirements; },
    (wire) => { wire.scheme_snapshot.extra = true; },
    (wire) => { wire.schema_version = "phase4-run-draft/v2"; }
  ]) {
    const wire = draftWire();
    mutate(wire);
    assert.throws(() => decodePreparedResearchDraft(wire, expectedDraft), ContractViolation);
  }
});

test("confirmation decoder rejects false auto-start and every changed admission identity", () => {
  const draft = decodePreparedResearchDraft(draftWire(), expectedDraft);
  for (const mutate of [
    (wire) => { wire.admission.auto_start.admitted = false; },
    (wire) => { wire.admission.object_id = "OBJ-B"; },
    (wire) => { wire.admission.goal_id = "GOAL-B"; },
    (wire) => { wire.admission.scheme_id = "SCHEME-B"; },
    (wire) => { wire.admission.draft_hash = hash("d"); },
    (wire) => { wire.admission.projection_ref = "/api/research-runs/RUN-B/projection"; }
  ]) {
    const wire = confirmWire();
    mutate(wire);
    assert.throws(() => decodeConfirmRunResponse(wire, draft), ContractViolation);
  }
});

test("an exact replay changes only response metadata", () => {
  const draft = decodePreparedResearchDraft(draftWire(), expectedDraft);
  const first = decodeConfirmRunResponse(confirmWire(false), draft);
  const replay = decodeConfirmRunResponse(confirmWire(true), draft);
  assert.doesNotThrow(() => assertAdmissionReplayStable(first, replay));
  const changed = structuredClone(replay);
  changed.admission.runId = "RUN-B";
  assert.throws(() => assertAdmissionReplayStable(first, changed), /immutable admission changed/);
});

test("projection decoder rejects wrong resource, unsupported state, and fabricated graph Task", () => {
  const admission = decodeConfirmRunResponse(
    confirmWire(),
    decodePreparedResearchDraft(draftWire(), expectedDraft)
  ).admission;
  for (const mutate of [
    (wire) => { wire.run.run_id = "RUN-B"; },
    (wire) => { wire.object.object_id = "OBJ-B"; },
    (wire) => { wire.run.goal_id = "GOAL-B"; },
    (wire) => { wire.run.scheme_id = "SCHEME-B"; },
    (wire) => { delete wire.run.actual_graph_id; },
    (wire) => { wire.run.status = "RESEARCHING"; },
    (wire) => { wire.run.stage = "RESEARCH"; },
    (wire) => { wire.planned_graph.tasks.push(taskWire("TASK-FABRICATED", "CREATED")); },
    (wire) => { wire.tasks.push(taskWire("TASK-UNGRAPHED", "CREATED")); },
    (wire) => { wire.tasks.push(structuredClone(wire.tasks[0])); }
  ]) {
    const wire = projectionWire();
    mutate(wire);
    assert.throws(() => decodeAtomicRunProjection(wire, admission), ContractViolation);
  }
});

test("projection Task status/dependency truth is mandatory, unique, same-Run, and graph-consistent", () => {
  const admission = decodeConfirmRunResponse(
    confirmWire(),
    decodePreparedResearchDraft(draftWire(), expectedDraft)
  ).admission;
  const mutations = [
    (wire) => { delete wire.tasks[0].status; },
    (wire) => { wire.tasks[0].status = "LOCALLY_GUESSED"; wire.actual_graph.tasks[0].status = "LOCALLY_GUESSED"; },
    (wire) => { delete wire.tasks[0].dependencies; },
    (wire) => { delete wire.tasks[0].progress; },
    (wire) => { wire.tasks[0].progress = 1.01; wire.actual_graph.tasks[0].progress = 1.01; },
    (wire) => { delete wire.tasks[0].parent_task_id; },
    (wire) => { wire.tasks[1].parent_task_id = "TASK-FOREIGN"; wire.actual_graph.tasks[1].parent_task_id = "TASK-FOREIGN"; },
    (wire) => { wire.tasks[1].parent_task_id = "TASK-B"; wire.actual_graph.tasks[1].parent_task_id = "TASK-B"; },
    (wire) => { wire.tasks[1].dependencies = ["TASK-A", "TASK-A"]; },
    (wire) => { wire.tasks[1].dependencies = ["TASK-B"]; },
    (wire) => { wire.tasks[1].dependencies = ["TASK-FOREIGN"]; },
    (wire) => { wire.tasks[1].run_id = "RUN-B"; },
    (wire) => { wire.tasks[1].task_id = " TASK-B"; wire.actual_graph.tasks[1].task_id = " TASK-B"; },
    (wire) => { wire.tasks[1].status = "READY"; },
    (wire) => { wire.tasks[1].dependencies = []; }
  ];
  for (const mutate of mutations) {
    const wire = projectionWire();
    mutate(wire);
    assert.throws(() => decodeAtomicRunProjection(wire, admission), ContractViolation);
  }
});

test("projection decoder closes exact top/object/run/Goal/Scheme/graph/lifecycle/owned/terminal shapes", () => {
  const admission = decodeConfirmRunResponse(
    confirmWire(),
    decodePreparedResearchDraft(draftWire(), expectedDraft)
  ).admission;
  const mutations = [
    (wire) => { wire.extra = true; },
    (wire) => { delete wire.activity; },
    (wire) => { wire.object.extra = true; },
    (wire) => { delete wire.object.identity_version; },
    (wire) => { wire.object.identity_version = 1.5; },
    (wire) => { delete wire.run.execution_target; },
    (wire) => { wire.run.completed_at = "2026-09-05T00:00:02Z"; },
    (wire) => { wire.goal.extra = true; },
    (wire) => { wire.goal.as_of = "2026-09-04"; },
    (wire) => { delete wire.confirmed_scheme.generated_by; },
    (wire) => { wire.confirmed_scheme.confirmed_at = null; },
    (wire) => { delete wire.planned_graph.graph_id; },
    (wire) => { wire.planned_graph.edges = []; },
    (wire) => { wire.actual_graph.version = 2; },
    (wire) => { wire.actual_graph.tasks[1].dependencies = []; },
    (wire) => { delete wire.lifecycle.progress; },
    (wire) => { wire.lifecycle.progress.method = "ELAPSED_TIME"; },
    (wire) => { wire.lifecycle.progress.total_tasks = 3; },
    (wire) => { wire.lifecycle.progress.fraction = 0.5; },
    (wire) => { wire.review.availability.extra = true; },
    (wire) => { wire.review.availability.reason_code = null; },
    (wire) => { delete wire.result.released_at; },
    (wire) => { wire.artifacts.availability = availability("AVAILABLE", null); },
    (wire) => { wire.proof.policy = "INFERRED"; },
    (wire) => { wire.execution.availability = availability("AVAILABLE", null); },
    (wire) => { wire.terminal.extra = true; },
    (wire) => { wire.terminal.outcome = "SUCCESS"; }
  ];
  for (const mutate of mutations) {
    const wire = projectionWire();
    mutate(wire);
    assert.throws(() => decodeAtomicRunProjection(wire, admission), ContractViolation);
  }
});

test("projection PathChange requires exact 13 fields and only authority-backed operation encodings", () => {
  const admission = decodeConfirmRunResponse(
    confirmWire(),
    decodePreparedResearchDraft(draftWire(), expectedDraft)
  ).admission;
  const pathChange = {
    path_change_id: "REPLAN-A",
    source_kind: "REPLAN",
    source_id: "REPLAN-A",
    change_kind: "ADD_TASK",
    status: "APPROVED",
    decision: "APPROVED",
    reason_code: "CAPABILITY_GAP",
    task_refs: ["TASK-B"],
    operations: [{ operation: "add_node", task_id: "TASK-B" }],
    graph_version_before: 1,
    graph_version_after: 1,
    created_at: "2026-09-05T00:00:01Z",
    resolved_at: "2026-09-05T00:00:02Z"
  };
  const valid = projectionWire();
  valid.path_changes = [pathChange];
  const decoded = decodeAtomicRunProjection(valid, admission).pathChanges[0];
  assert.equal(decoded.pathChangeId, "REPLAN-A");
  assert.equal(decoded.sourceId, "REPLAN-A");
  for (const mutate of [
    (change) => { change.extra = true; },
    (change) => { change.source_id = "REPLAN-B"; },
    (change) => { change.source_kind = "CORRECTION"; },
    (change) => { change.task_refs = ["TASK-FOREIGN"]; },
    (change) => { change.operations[0].task_id = "TASK-FOREIGN"; },
    (change) => { change.operations[0].extra = true; },
    (change) => {
      change.change_kind = "CHANGE_DEPENDENCY";
      change.task_refs = ["TASK-A", "TASK-B"];
      change.operations = [{ operation: "add_edge", from: "TASK-A", to: "TASK-B" }];
    },
    (change) => { change.graph_version_after = 2; }
  ]) {
    const wire = projectionWire();
    wire.path_changes = [structuredClone(pathChange)];
    mutate(wire.path_changes[0]);
    assert.throws(() => decodeAtomicRunProjection(wire, admission), ContractViolation);
  }
});

test("released terminal projection requires complete explicit release identity and terminal closure", () => {
  const wire = projectionWire();
  wire.run.status = "RELEASED";
  wire.run.stage = "COMPLETE";
  wire.run.started_at = "2026-09-05T00:00:01Z";
  wire.run.completed_at = "2026-09-05T00:00:02Z";
  for (const task of [...wire.actual_graph.tasks, ...wire.tasks]) {
    task.status = "COMPLETED";
    task.progress = 1;
  }
  Object.assign(wire.lifecycle, {
    status: "RELEASED",
    stage: "COMPLETE",
    progress: { method: "ACTUAL_TASK_MEAN_V1", completed_tasks: 2, total_tasks: 2, fraction: 1 },
    terminal: true,
    terminal_outcome: "SUCCESS"
  });
  wire.review = { availability: availability("AVAILABLE", null), review_id: "REVIEW-A", status: "PASS" };
  wire.result = {
    availability: availability("AVAILABLE", null),
    released_result_id: "RESULT-A",
    canonical_record_id: "CANONICAL-A",
    released_at: "2026-09-05T00:00:02Z"
  };
  wire.artifacts = {
    availability: availability("AVAILABLE", null),
    report_id: "RESULT-A",
    representation_ids: ["ARTIFACT-HTML-A"]
  };
  wire.proof = {
    availability: availability("AVAILABLE", null),
    policy: "MUST_PROVE",
    status: "VERIFIED",
    proof_refs: ["PROOF-A"]
  };
  wire.execution = {
    availability: availability("AVAILABLE", null),
    canonical_record_id: "CANONICAL-A"
  };
  wire.terminal = { is_terminal: true, outcome: "SUCCESS", event_id: "EVENT-A", sequence: 2 };
  assert.equal(decodeAtomicRunProjection(wire).terminal.outcome, "SUCCESS");
  for (const mutate of [
    (candidate) => { candidate.run.completed_at = null; },
    (candidate) => { candidate.result.canonical_record_id = null; },
    (candidate) => { candidate.result.availability = availability("NOT_RELEASED"); },
    (candidate) => { candidate.execution.canonical_record_id = "CANONICAL-B"; },
    (candidate) => { candidate.terminal.sequence = 3; },
    (candidate) => { candidate.terminal.event_id = null; },
    (candidate) => { candidate.lifecycle.terminal_outcome = "FAILURE"; },
    (candidate) => { candidate.review.status = "BLOCK"; },
    (candidate) => { candidate.artifacts.availability = availability("NOT_GENERATED"); },
    (candidate) => { candidate.proof.policy = "UNKNOWN"; candidate.proof.status = null; candidate.proof.proof_refs = []; },
    (candidate) => { candidate.proof.status = "INVALID"; },
    (candidate) => { candidate.proof.proof_refs = []; },
    (candidate) => { candidate.execution.availability = availability("NOT_GENERATED"); },
    (candidate) => { candidate.lifecycle.safe_failure = { failure_code: "IMPOSSIBLE_SUCCESS_FAILURE" }; }
  ]) {
    const candidate = structuredClone(wire);
    mutate(candidate);
    assert.throws(() => decodeAtomicRunProjection(candidate), ContractViolation);
  }
});

test("terminal unsuccessful lifecycle reaches one only after every authoritative Task is terminal", () => {
  const wire = projectionWire();
  wire.run.status = "FAILED";
  wire.run.stage = "FAILED";
  wire.run.started_at = "2026-09-05T00:00:01Z";
  wire.run.completed_at = "2026-09-05T00:00:02Z";
  for (const taskSet of [wire.actual_graph.tasks, wire.tasks]) {
    taskSet[0].status = "FAILED";
    taskSet[0].progress = 0.25;
    taskSet[1].status = "COMPLETED";
    taskSet[1].progress = 1;
  }
  Object.assign(wire.lifecycle, {
    status: "FAILED",
    stage: "FAILED",
    progress: { method: "ACTUAL_TASK_MEAN_V1", completed_tasks: 1, total_tasks: 2, fraction: 1 },
    terminal: true,
    terminal_outcome: "FAILURE",
    safe_failure: { failure_code: "SAFE_FAILURE" }
  });
  wire.review = { availability: availability("NOT_GENERATED"), review_id: null, status: null };
  wire.result.availability = availability("NOT_RELEASED");
  wire.terminal = { is_terminal: true, outcome: "FAILURE", event_id: "EVENT-FAILED", sequence: 2 };
  assert.equal(decodeAtomicRunProjection(wire).lifecycle.progress.fraction, 1);
  const nonterminalTask = structuredClone(wire);
  nonterminalTask.tasks[0].status = "RUNNING";
  nonterminalTask.actual_graph.tasks[0].status = "RUNNING";
  assert.throws(() => decodeAtomicRunProjection(nonterminalTask), /authoritative Task mean/);

  const releasedResult = structuredClone(wire);
  releasedResult.result = {
    availability: availability("AVAILABLE", null),
    released_result_id: "RESULT-FAILED",
    canonical_record_id: "CANONICAL-FAILED",
    released_at: "2026-09-05T00:00:02Z"
  };
  assert.throws(() => decodeAtomicRunProjection(releasedResult), /only RELEASED Run/);

  const availableArtifacts = structuredClone(wire);
  availableArtifacts.artifacts = {
    availability: availability("AVAILABLE", null),
    report_id: "REPORT-FAILED",
    representation_ids: ["ARTIFACT-FAILED"]
  };
  assert.throws(() => decodeAtomicRunProjection(availableArtifacts), /unsuccessful terminal Run/);
});

test("stale and wrong-resource candidate projections leave the last valid state untouched", () => {
  const current = Object.freeze({ runId: "RUN-A", revision: 7 });
  const context = { currentRequestEpoch: 4, objectId: "OBJ-A", runId: "RUN-A" };
  const stale = admitContextProjection(current, {
    requestEpoch: 3,
    objectId: "OBJ-A",
    runId: "RUN-A",
    projection: { runId: "RUN-A", revision: 6 }
  }, context);
  const wrong = admitContextProjection(current, {
    requestEpoch: 4,
    objectId: "OBJ-B",
    runId: "RUN-B",
    projection: { runId: "RUN-B", revision: 9 }
  }, context);
  assert.deepEqual(stale, { accepted: false, reason: "STALE_RESPONSE", projection: current });
  assert.deepEqual(wrong, { accepted: false, reason: "IDENTITY_MISMATCH", projection: current });
  assert.strictEqual(stale.projection, current);
  assert.strictEqual(wrong.projection, current);
});

test("typed error vocabulary enforces its HTTP, retry, recovery, and safe-details tuple", () => {
  const wire = {
    schema_version: "phase4-error/v1",
    error: {
      code: "NOT_FOUND",
      message: "Run was not found",
      retryable: false,
      recovery: "NONE",
      request_id: "REQUEST-MISSING",
      resource: { type: "ResearchRun", id: "RUN-MISSING" },
      details: { reason_code: "RUN_NOT_FOUND" }
    }
  };
  assert.equal(decodeErrorEnvelope(wire, 404).code, "NOT_FOUND");
  const wrongRecovery = structuredClone(wire);
  wrongRecovery.error.recovery = "RETRY";
  assert.throws(() => decodeErrorEnvelope(wrongRecovery, 404), ContractViolation);
  const unsafe = structuredClone(wire);
  unsafe.error.details.authorization_header = "redacted-but-key-is-forbidden";
  assert.throws(() => decodeErrorEnvelope(unsafe, 404), /UNSAFE_PUBLIC_CONTENT/);
  const unsafeText = structuredClone(wire);
  unsafeText.error.details.safe_message = "Traceback (most recent call last): /Users/operator/app.py";
  assert.throws(() => decodeErrorEnvelope(unsafeText, 404), /UNSAFE_PUBLIC_CONTENT/);
  const providerLeak = structuredClone(wire);
  providerLeak.error.message = "Langfuse provider response failed";
  assert.throws(() => decodeErrorEnvelope(providerLeak, 404), /PUBLIC_SURFACE_LEAK/);
});

test("one Confirm admits the Run and no separate Start/Execute mutation exists", () => {
  assert.doesNotThrow(() => assertNoSecondStartRequest([
    { method: "GET", pathname: "/api/objects" },
    { method: "POST", pathname: "/api/research-runs/prepare" },
    { method: "POST", pathname: "/api/research-runs" },
    { method: "GET", pathname: "/api/research-runs/RUN-A/projection" }
  ]));
  assert.doesNotThrow(() => assertNoSecondStartRequest([
    { method: "POST", pathname: "/reviewed-prefix/research-runs" }
  ], "/reviewed-prefix/research-runs"));
  assert.throws(() => assertNoSecondStartRequest([
    { method: "POST", pathname: "/api/research-runs" },
    { method: "POST", pathname: "/api/research-runs/RUN-A/start" }
  ]), /SECOND_START/);
});

test("Demo fallback markers and frontend financial arithmetic are independently detected", () => {
  assert.throws(() => assertNoDemoFallback("new DemoFrontendDataSource()"), /DEMO_FALLBACK/);
  assert.deepEqual(findFrontendFinancialAuthority([
    { path: "safe.ts", source: "const text = metric.displayValue + metric.displayUnit;" }
  ]), []);
  assert.deepEqual(findFrontendFinancialAuthority([
    { path: "bad.ts", source: "const pct = Number(metric.canonicalValue) * 100;" }
  ]), [
    { code: "CANONICAL_NUMERIC_COERCION", path: "bad.ts" },
    { code: "CANONICAL_ARITHMETIC", path: "bad.ts" },
    { code: "RATIO_TO_PERCENT", path: "bad.ts" }
  ]);
});

test("released financial decoder captures one real adversarial wire decimal as a lossless string", () => {
  const metric = {
    run_id: "RUN-C-RELEASED",
    metric_id: "METRIC-C-ADVERSARIAL",
    name: "Adversarial Precision Metric",
    canonical_value: "0.6547000000000000",
    canonical_unit: "RATIO",
    display_value: "65.47000000000000",
    display_unit: "%",
    period: "FY2026",
    period_basis: "FY",
    actuality: "ACTUAL",
    as_of: "2026-09-05",
    currency: "USD",
    formula_id: "ebitda_margin_v1",
    capability_id: "ebitda_margin",
    calculation_id: "CALC-C",
    evidence_refs: ["EVIDENCE-C"],
    claim_refs: ["CLAIM-C"],
    proof: {
      policy_id: "phase4-proof-policy/v1",
      requirement: "MUST_PROVE",
      status: "VERIFIED",
      proof_refs: ["PROOF-C"]
    },
    method_metadata: null,
    technical_price_basis: null,
    corporate_action_status: null,
    corporate_action_guard_refs: [],
    limitations: []
  };
  const response = { result: { released_metrics: [metric] }, report: {} };
  assert.equal(isAdversarialCanonicalDecimal(metric.canonical_value), true);
  assert.equal(isAdversarialCanonicalDecimal("0.6547"), false);
  const decoded = decodeReleasedFinancialMetricEvidence(response, {
    runId: metric.run_id,
    metricId: metric.metric_id,
    adversarialProperty: "NUMBER_STRING_ROUNDTRIP_CHANGES"
  });
  assert.equal(decoded.canonicalValue, "0.6547000000000000");
  assert.notEqual(String(Number(decoded.canonicalValue)), decoded.canonicalValue);
  for (const mutate of [
    (wire) => { wire.result.released_metrics[0].canonical_value = 0.6547; },
    (wire) => { wire.result.released_metrics[0].canonical_value = "0.6547"; },
    (wire) => { wire.result.released_metrics[0].run_id = "RUN-FOREIGN"; },
    (wire) => { wire.result.released_metrics[0].proof.status = "VALID"; },
    (wire) => { wire.result.released_metrics[0].extra = true; },
    (wire) => { wire.result.released_metrics.push(structuredClone(wire.result.released_metrics[0])); }
  ]) {
    const wire = structuredClone(response);
    mutate(wire);
    assert.throws(() => decodeReleasedFinancialMetricEvidence(wire, {
      runId: metric.run_id,
      metricId: metric.metric_id,
      adversarialProperty: "NUMBER_STRING_ROUNDTRIP_CHANGES"
    }), ContractViolation);
  }
});

test("public UI, DOM, source, and error surfaces reject provider, credential, hidden-reasoning, and internal diagnostics", () => {
  assert.doesNotThrow(() => assertNoPublicSurfaceLeaks("Research is temporarily unavailable"));
  const exactSentinel = "random-vfas-vs01-secret-sentinel-123";
  assert.deepEqual(
    findPublicSurfaceLeaks([{ path: "visible-ui", source: `leaked=${exactSentinel}` }], [exactSentinel]),
    [{ code: "EXACT_SECRET_SENTINEL", path: "visible-ui" }]
  );
  assert.throws(
    () => assertNoPublicSurfaceLeaks(`leaked=${exactSentinel}`, "dom", [exactSentinel]),
    /EXACT_SECRET_SENTINEL/
  );
  const findings = findPublicSurfaceLeaks([{ path: "/assets/application.js", source: `
    Qiji MIMO TeamoRouter FMP Langfuse
    Authorization header; API key; Bearer abcdefghijklmnop; sk-abcdefghijklmnop
    system prompt; scratch_reasoning; chain-of-thought; raw provider payload
    Traceback (most recent call last): /Users/operator/private.py
    SELECT secret_value FROM internal_table
  ` }]);
  const codes = new Set(findings.map((finding) => finding.code));
  for (const expected of [
    "PROVIDER_QIJI",
    "PROVIDER_MIMO",
    "PROVIDER_TEAMOROUTER",
    "PROVIDER_FMP",
    "PROVIDER_LANGFUSE",
    "CREDENTIAL_BEARER",
    "CREDENTIAL_API_KEY",
    "CREDENTIAL_TOKEN_SHAPE",
    "HIDDEN_REASONING",
    "RAW_PROVIDER_PAYLOAD",
    "STACK_TRACE",
    "INTERNAL_PATH",
    "RAW_SQL"
  ]) assert.equal(codes.has(expected), true, `missing detector ${expected}`);
});
