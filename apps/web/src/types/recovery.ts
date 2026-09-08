/** Safe display projection of the additive backend recovery ledger. */
export interface RecoveryRow {
  id: string; runId: string; taskId: string; profile: string; kind: string;
  attempt: number; check: boolean; route: string | null; model: string | null;
  outcome: string; action: string | null; failure: string | null; reason: string;
  latencyMs: number | null;
  preferredModel?: string | null; actualModel?: string | null; routing?: string | null;
  policyGate?: string | null;
}
const kinds = ["ATTEMPT_STARTED", "ATTEMPT_COMPLETED", "DECISION", "TERMINAL"];
const actions = ["RETRY_SAME_ROUTE", "SWITCH_MODEL", "SWITCH_PROVIDER", "CAPABILITY_CHECK", "WAIT_AND_RETRY", "REPLAN_TASK", "CORRECT_RESEARCH_PATH", "FAIL_TASK", "FAIL_RUN"];
const failures = ["MODEL_IDENTITY_MISMATCH", "READ_TIMEOUT", "PROVIDER_UNAVAILABLE", "REMOTE_PROTOCOL_ERROR", "RATE_LIMIT", "PROVIDER_5XX", "OUTPUT_CONTRACT_FAILURE", "NON_RECOVERABLE_RUNTIME_FAILURE", "RESEARCH_SEMANTIC_FAILURE", "UNKNOWN"];
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid recovery record");
  return value as Record<string, unknown>;
}
function choice(value: unknown, allowed: readonly string[]): string {
  if (typeof value !== "string" || !allowed.includes(value)) throw new Error("Invalid recovery code");
  return value;
}
function identity(value: unknown): string {
  if (typeof value !== "string" || !/^[A-Za-z0-9_:.-]{1,256}$/.test(value)) throw new Error("Invalid recovery identity");
  return value;
}
export function decodeRecoveryEvidence(value: unknown, runId: string, objectId: string): readonly RecoveryRow[] {
  if (!Array.isArray(value) || value.length > 10000) throw new Error("Invalid recovery collection");
  const ids = new Set<string>();
  let scheme: string | undefined;
  return value.map(raw => {
    const r = record(raw), s = record(r.scope);
    if (s.run_id !== runId || s.object_id !== objectId) throw new Error("Recovery identity mismatch");
    const taskId = identity(s.task_id), schemeId = identity(s.scheme_id), id = identity(r.record_id);
    if (!taskId.startsWith(runId + ":") || !/^REC-[0-9a-f-]{36}$/.test(id) || ids.has(id)) throw new Error("Recovery task/record mismatch");
    ids.add(id);
    scheme ??= schemeId;
    if (scheme !== schemeId) throw new Error("Recovery Scheme mismatch");
    const kind = choice(r.kind, kinds);
    const models = ["gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra", "mimo-v2.5", "mimo-v2.5-pro"];
    const route = r.route === null ? null : choice(r.route, ["teamorouter-sol", "teamorouter-luna", "teamorouter-terra", "mimo-direct"]);
    const model = r.model === null ? null : choice(r.model, models);
    if (kind.startsWith("ATTEMPT_")) {
      const pair = route === "teamorouter-sol" ? ["teamorouter", "gpt-5.6-sol"] : route === "teamorouter-luna" ? ["teamorouter", "gpt-5.6-luna"] : route === "teamorouter-terra" ? ["teamorouter", "gpt-5.6-terra"] : ["mimo", model];
      if (!route || !model || r.provider !== pair[0] || model !== pair[1] || (route === "mimo-direct" && !model.startsWith("mimo-"))) throw new Error("Recovery route mismatch");
    }
    const action = r.action === null ? null : choice(r.action, actions);
    if (kind === "DECISION") {
      const decision = record(r.decision), scope = record(decision.scope);
      if (scope.run_id !== runId || scope.object_id !== objectId || scope.task_id !== taskId || scope.scheme_id !== schemeId || decision.action !== action || decision.target_route !== route) throw new Error("Recovery decision mismatch");
    }
    if (typeof r.capability_check !== "boolean" || !Number.isInteger(r.attempt_number) || Number(r.attempt_number) < 0 || Number(r.attempt_number) > 4) throw new Error("Invalid recovery attempt");
    if (r.latency_ms !== null && (typeof r.latency_ms !== "number" || !Number.isFinite(r.latency_ms) || r.latency_ms < 0)) throw new Error("Invalid recovery latency");
    const policy = r.execution_policy == null ? null : record(r.execution_policy);
    const actualModel = r.actual_model == null ? null : choice(r.actual_model, models);
    const routing = r.execution_outcome == null ? null : choice(r.execution_outcome, ["MODEL_EXECUTION_DIRECT", "MODEL_EXECUTION_SUBSTITUTED", "MODEL_IDENTITY_OUT_OF_POLICY", "PROVIDER_IDENTITY_OUT_OF_POLICY"]);
    if (policy) {
      if (policy.provider_route !== route || policy.provider !== r.provider || policy.preferred_model !== model || policy.task_profile !== s.task_profile || policy.version !== "bounded-model-execution/v1" || typeof policy.dynamic_substitution_allowed !== "boolean" || !Array.isArray(policy.authorized_actual_models)) throw new Error("Invalid model policy binding");
      const allowed = policy.authorized_actual_models.map(m => choice(m, models));
      if (r.outcome === "PASS" && (!actualModel || !allowed.includes(actualModel) || (actualModel !== model && (!policy.dynamic_substitution_allowed || routing !== "MODEL_EXECUTION_SUBSTITUTED")))) throw new Error("Execution outside policy");
    }
    return {
      id, runId, taskId, profile: choice(s.task_profile, ["fundamental_analysis", "peer_analysis", "research_news_analysis", "valuation_analysis", "risk_analysis", "risk_follow_up", "report_synthesis", "GENERATED_CAPABILITY:free_cash_flow_margin"]),
      kind, route, model, attempt: Number(r.attempt_number), check: r.capability_check,
      outcome: choice(r.outcome, ["STARTED", "PASS", "FAIL", "ALLOW", "DENY", "CANCELLED"]), action,
      failure: r.failure_class === null ? null : choice(r.failure_class, failures),
      reason: choice(r.reason_code, ["OBSERVED", "POLICY_DENIED", "RECOVERY_BUDGET_EXHAUSTED", "INTERRUPTED_EXECUTION", "NONRECOVERABLE"]),
      latencyMs: r.latency_ms as number | null,
      preferredModel: policy ? model : null, actualModel, routing,
      policyGate: r.policy_gate_result == null ? null : choice(r.policy_gate_result, ["ALLOW", "DENY"])
    };
  });
}
