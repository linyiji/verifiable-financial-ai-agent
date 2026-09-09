/** Opt-in projection only. Never maps recovery to a new research admission. */
export type RecoverySummaryV1 = Readonly<{
  version: "recovery-summary/v1";
  run_id: string;
  intent_id: string;
  operation_id: string;
  contract_hash: string;
  status: "PENDING" | "CLAIMED" | "COMPLETE" | "FAILED";
  original_failure: string | null;
  attempt: number;
  scope: readonly string[];
  reusable_output_refs: readonly string[];
  physical_calls_used: number;
  physical_calls_limit: number;
  deadline: number;
  recoverable: boolean;
  denial_reason: string | null;
  accepted_actions: readonly "AUTHORIZE_FAILED_OPERATION"[];
  execution_started: false;
}>;

export function decodeRecoverySummaryV1(raw: unknown, runId: string): RecoverySummaryV1 {
  if (typeof raw !== "object" || raw === null) throw new Error("RECOVERY_CONTRACT_INVALID");
  const x = raw as Record<string, unknown>;
  const strings = (v: unknown): v is string[] => Array.isArray(v)
    && v.every(item => typeof item === "string");
  if (x.version !== "recovery-summary/v1" || x.run_id !== runId
      || typeof x.intent_id !== "string" || typeof x.operation_id !== "string"
      || typeof x.contract_hash !== "string" || !/^sha256:[a-f0-9]{64}$/.test(x.contract_hash)
      || !["PENDING", "CLAIMED", "COMPLETE", "FAILED"].includes(String(x.status))
      || !(x.original_failure === null || typeof x.original_failure === "string")
      || !(x.denial_reason === null || typeof x.denial_reason === "string")
      || !strings(x.scope) || !strings(x.reusable_output_refs)
      || !strings(x.accepted_actions)
      || x.accepted_actions.some(action => action !== "AUTHORIZE_FAILED_OPERATION")
      || typeof x.recoverable !== "boolean" || x.execution_started !== false
      || ![x.attempt, x.physical_calls_used, x.physical_calls_limit].every(
        n => typeof n === "number" && Number.isSafeInteger(n) && n >= 0)
      || typeof x.deadline !== "number" || !Number.isFinite(x.deadline)
      || (!x.recoverable && x.accepted_actions.length !== 0)) {
    throw new Error("RECOVERY_CONTRACT_INVALID");
  }
  return Object.freeze(x) as RecoverySummaryV1;
}
