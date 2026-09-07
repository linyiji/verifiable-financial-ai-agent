// Minimal wire fixture adapted from the maintained VS01 contract helper tests.
function taskWire(taskId, status, dependencies = [], progress = 0, parentTaskId = null) {
  return {
    task_id: taskId,
    run_id: "RUN-A",
    parent_task_id: parentTaskId,
    task_type: "fundamental_analysis",
    goal: "Analyze the exact public company",
    assigned_agent: "fundamental_analyst",
    skill_id: "fundamental_analysis_v1",
    dependencies,
    origin: "PLAN",
    reason_code: null,
    status,
    progress,
    attempt_count: 1,
    task_input_evidence_ids: [],
    task_output_evidence_ids: [],
    evidence_acquisition_status: null,
    evidence_source_coverage: {},
    created_at: "2026-09-05T00:00:01Z"
  };
}

function availability(status = "PENDING", reasonCode = "RUN_NONTERMINAL") {
  return { status, reason_code: reasonCode, retryable: false };
}

export function projectionWire() {
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

export function completedTasksWire(status = 'REVIEW') {
  const p = projectionWire();
  p.run.status = p.lifecycle.status = status;
  p.run.stage = p.lifecycle.stage = status === 'RUNNING' ? 'RESEARCH' : 'REVIEW';
  for (const t of [...p.tasks, ...p.actual_graph.tasks]) { t.status = 'COMPLETED'; t.progress = 1; }
  p.lifecycle.progress.completed_tasks = p.tasks.length;
  p.lifecycle.progress.fraction = 1;
  return p;
}

export function releasedWire() {
  const p = completedTasksWire();
  p.projection_revision = 2; p.projection_sequence = 3;
  p.run.status = p.lifecycle.status = 'RELEASED';
  p.run.stage = p.lifecycle.stage = 'COMPLETE';
  p.run.completed_at = p.generated_at;
  p.lifecycle.terminal = true; p.lifecycle.terminal_outcome = 'SUCCESS';
  p.terminal = {is_terminal:true,outcome:'SUCCESS',event_id:'EVENT-3',sequence:3};
  p.activity = [
    {event_id:'EVENT-2',type:'release.completed',sequence:2,timestamp:p.generated_at,task_id:null,message_code:'RELEASE_COMPLETED'},
    {event_id:'EVENT-3',type:'run.completed',sequence:3,timestamp:p.generated_at,task_id:null,message_code:'RUN_COMPLETED',status:'RELEASED'}
  ];
  const available = {status:'AVAILABLE',reason_code:null,retryable:false};
  p.review = {availability:available,review_id:'REVIEW-A',status:'PASS'};
  p.result = {availability:available,released_result_id:'RESULT-A',canonical_record_id:'CER-A',released_at:p.generated_at};
  p.execution = {availability:available,canonical_record_id:'CER-A'};
  p.artifacts = {availability:available,report_id:'RESULT-A',representation_ids:['HTML-A']};
  p.proof = {availability:available,policy:'NOT_REQUIRED',status:'NOT_REQUIRED',proof_refs:[]};
  return p;
}
