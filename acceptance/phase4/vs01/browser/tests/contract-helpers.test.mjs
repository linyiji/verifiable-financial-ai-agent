import assert from "node:assert/strict";
import test from "node:test";
import {
  admitContextProjection,
  assertAdmissionReplayStable,
  assertNoDemoFallback,
  assertNoSecondStartRequest,
  ContractViolation,
  decodeAtomicRunProjection,
  decodeConfirmRunResponse,
  decodeErrorEnvelope,
  decodePreparedResearchDraft,
  findFrontendFinancialAuthority
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
      goal_type: "comprehensive_equity_research"
    },
    scheme_snapshot: {
      scheme_id: "SCHEME-A",
      research_object_id: "OBJ-A",
      goal_id: "GOAL-A",
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

function projectionWire() {
  return {
    projection_schema_version: "phase4-run-projection/v1",
    projection_revision: 1,
    projection_sequence: 2,
    generated_at: "2026-09-05T00:00:02Z",
    object: { object_id: "OBJ-A", symbol: "AAA", company_name: "A" },
    run: {
      run_id: "RUN-A",
      research_object_id: "OBJ-A",
      goal_id: "GOAL-A",
      scheme_id: "SCHEME-A",
      status: "PLANNING",
      stage: "PLANNING",
      planned_graph_id: "GRAPH-A-PLANNED",
      actual_graph_id: "GRAPH-A-ACTUAL"
    },
    goal: { goal_id: "GOAL-A", research_object_id: "OBJ-A" },
    confirmed_scheme: {
      scheme_id: "SCHEME-A",
      goal_id: "GOAL-A",
      research_object_id: "OBJ-A",
      confirmed_at: "2026-09-05T00:00:01Z"
    },
    planned_graph: {
      graph_id: "GRAPH-A-PLANNED",
      run_id: "RUN-A",
      version: 1,
      task_ids: ["TASK-A"],
      edges: []
    },
    actual_graph: {
      graph_id: "GRAPH-A-ACTUAL",
      run_id: "RUN-A",
      version: 1,
      task_ids: ["TASK-A"],
      edges: []
    },
    graph_version: 1,
    tasks: [{ task_id: "TASK-A", run_id: "RUN-A", research_object_id: "OBJ-A", status: "CREATED" }],
    path_changes: [],
    activity: [],
    lifecycle: { status: "PLANNING", stage: "PLANNING" },
    review: {},
    result: {},
    artifacts: {},
    proof: {},
    execution: {},
    terminal: {}
  };
}

const expectedDraft = {
  objectId: "OBJ-A",
  goalText: "Assess A"
};

test("frozen draft, confirmation, and projection admit one identity-closed journey", () => {
  const draft = decodePreparedResearchDraft(draftWire(), expectedDraft);
  const confirmation = decodeConfirmRunResponse(confirmWire(), draft);
  const projection = decodeAtomicRunProjection(projectionWire(), confirmation.admission);
  assert.equal(draft.previewKind, "SCHEME_ONLY");
  assert.equal(draft.plannedGraphAvailability.status, "NOT_GENERATED");
  assert.deepEqual(confirmation.admission.autoStart, { required: true, admitted: true });
  assert.equal(projection.runId, confirmation.admission.runId);
  assert.deepEqual(projection.taskIds, ["TASK-A"]);
  assert.ok(Object.isFrozen(confirmation.admission));
});

test("draft decoder rejects local Tasks, wrong Object/Goal/Scheme, and pre-confirmed Scheme", () => {
  for (const mutate of [
    (wire) => { wire.tasks = []; },
    (wire) => { wire.object_id = "OBJ-B"; },
    (wire) => { wire.goal.research_object_id = "OBJ-B"; },
    (wire) => { wire.scheme_snapshot.goal_id = "GOAL-B"; },
    (wire) => { wire.scheme_snapshot.confirmed_at = "2026-09-05T00:00:00Z"; },
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
    (wire) => { wire.run.status = "RESEARCHING"; },
    (wire) => { wire.run.stage = "RESEARCH"; },
    (wire) => { wire.planned_graph.task_ids.push("TASK-FABRICATED"); },
    (wire) => { wire.tasks.push({ task_id: "TASK-UNGRAPHED", run_id: "RUN-A", status: "CREATED" }); },
    (wire) => { wire.tasks.push(structuredClone(wire.tasks[0])); }
  ]) {
    const wire = projectionWire();
    mutate(wire);
    assert.throws(() => decodeAtomicRunProjection(wire, admission), ContractViolation);
  }
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
});

test("one Confirm admits the Run and no separate Start/Execute mutation exists", () => {
  assert.doesNotThrow(() => assertNoSecondStartRequest([
    { method: "GET", pathname: "/api/objects" },
    { method: "POST", pathname: "/api/research-runs/prepare" },
    { method: "POST", pathname: "/api/research-runs" },
    { method: "GET", pathname: "/api/research-runs/RUN-A/projection" }
  ]));
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
