export interface IncrementalDecision {
  readonly decision: "REUSE" | "REFRESH" | "REVALIDATE" | "PREVENT" | "UNKNOWN";
  readonly source_run_id: string;
  readonly source_identity: string;
  readonly category: "VIEW_CONTEXT" | "VERIFIED_METRIC" | "VERIFIED_CLAIM" | "RESOLVED_ISSUE";
  readonly statement: string;
  readonly reason: string;
  readonly authority: "phase5b-exact-memory-policy/v1";
}
export interface IncrementalContext {
  readonly prior_summary?: string;
  readonly research_object_id: string;
  readonly base_run_id: string;
  readonly base_research_view_version: string;
  readonly base_version_number: number;
  readonly base_as_of: string;
  readonly target_as_of: string;
  readonly decisions: readonly IncrementalDecision[];
}
export {decodeIncrementalContext} from "./domain";
