# Phase 4 Wave 1 — Codex C Event Support Matrix

[简体中文](PHASE4_CODEX_C_EVENT_SUPPORT_MATRIX.zh-CN.md)

Contract: `phase4-runtime-event/v1` / payload schema `1`

Disposition: `47 SUPPORTED`, `8 UNSUPPORTED_BY_FRONTEND`, `0 NOT_APPLICABLE_WAVE1`.
This matrix follows the Final Contract Freeze and the frozen Phase 4 Backend event
mapping. It does not recognize prototype-only aliases.

## Validation and effect legend

- `E`: closed envelope; exact contract/payload versions, event ID, exact Run ID,
  RFC 3339 UTC timestamp, positive sequence, wire `id == sequence`, wire event name,
  frozen effect, refresh bit, and allowlisted payload.
- `T`: an exact Task ID is required and must be present in the current exact-Run
  projection. `graph.task_added` is the sole new-Task advisory exception; its frame
  still cannot fabricate a Task.
- `G`: a positive graph version is required. Edge endpoints must be authoritative
  same-Run Task IDs. The graph body always comes from the replacement snapshot.
- `PATCH`: update only the named validated lifecycle/progress overlay.
- `REFRESH`: retain the prior atomic projection as stale, stop that stream generation,
  fetch and validate one same-Run replacement projection, then atomically swap it.
- `OBSERVE`: retain a bounded safe event receipt only; canonical activity detail remains
  snapshot-owned, with no lifecycle or financial-value mutation.
- `TERMINAL`: require an authoritative terminal replacement projection; stop reconnect.
- Safe rendering is limited to typed IDs, enum/status values, reason/message/failure
  codes, approved safe message, timestamps, and reference arrays. Provider payloads,
  credentials, filesystem data, exception text, prompts, and hidden reasoning are never
  accepted or rendered.

## Complete raw-event disposition

| Raw event | Disposition | Decoder / identity | State effect | Research Path effect | Terminal effect | Safe rendering |
|---|---|---|---|---|---|---|
| `run.created` | SUPPORTED | E; `{object_id}` | REFRESH | exact snapshot only | none | Object ID only |
| `run.started` | SUPPORTED | E+G; `{}` | PATCH Run=`RUNNING` | exposes authoritative actual Graph after validation | none | graph version/status only |
| `run.status_changed` | SUPPORTED | E; `{status}` nonterminal | PATCH Run lifecycle | stage/status only | none | enum only |
| `run.completed` | SUPPORTED | E; `{status:"RELEASED"}` | TERMINAL | final authoritative path | success only after snapshot release closure | enum/terminal identity only |
| `run.failed` | SUPPORTED | E; `{status,failure_stage,failure_code,safe_message?}` | TERMINAL | final authoritative path | failure or cancellation from status | safe failure fields only |
| `scheme.generation_started` | UNSUPPORTED_BY_FRONTEND | declared raw name, no approved V1 payload | zero mutation/cursor; recover | none | none | quarantine identity only |
| `scheme.generated` | SUPPORTED | E; exact scheme generation fields | REFRESH | none directly | none | typed IDs/codes/time only |
| `scheme.confirmed` | SUPPORTED | E; `{scheme_id}` | REFRESH | none directly | none | Scheme ID only |
| `plan.generated` | SUPPORTED | E; `{graph_id,task_count}` | REFRESH | Tasks/graph only from snapshot | none | graph ID/count only |
| `task.created` | SUPPORTED | E+T-new; `{task_type}` | REFRESH | replacement may add authoritative Task | none | Task ID/type only |
| `task.ready` | SUPPORTED | E+T; `{}` | PATCH Task=`READY` | existing Task state | none | status only |
| `task.started` | SUPPORTED | E+T; `{attempt}` | PATCH Task=`RUNNING` | existing Task state | none | attempt/status only |
| `task.progress` | SUPPORTED | E+T; exact `PROGRESS` or `RETRY_SCHEDULED` form | PATCH progress only for `PROGRESS`; retry retains progress | existing Task progress | none | ratio/stage/message or error code only |
| `task.waiting_for_capability` | SUPPORTED | E+T; `{gap_id}` | PATCH Task=`WAITING_FOR_CAPABILITY` | same Task | none | gap ID/status only |
| `task.resumed` | SUPPORTED | E+T; `{gap_id,registration_id,status:"RUNNING"}` | PATCH Task=`RUNNING` | same Task | none | IDs/status only |
| `task.self_correcting` | SUPPORTED | E+T; `{problem_code}` | PATCH Task=`SELF_CORRECTING` | same Task/same Graph; durable correction comes from snapshot | none | problem code only |
| `task.correction_resolved` | SUPPORTED | E+T; `{correction_id}` | REFRESH | exact correction/path-change record | none | Correction ID only |
| `task.completed` | SUPPORTED | E+T; `{attempt,result_ref?}` | PATCH Task=`COMPLETED`, progress=1 | existing Task terminal | does not terminate Run | attempt only; the safe V1 adapter withholds internal/result locator refs |
| `task.failed` | SUPPORTED | E+T; `{attempt,failure_code,status?,retry_suppressed?}` | PATCH exact Task failure | existing Task terminal | does not alone terminate Run | failure code/flags only |
| `replan.requested` | SUPPORTED | E+T; `{replan_id,decision}` | REFRESH | show exact pending/decision record; no topology inference | none | Replan ID/decision only |
| `replan.approved` | SUPPORTED | E+T; `{replan_id,decided_by}` | REFRESH | consume Lead-authorized replacement graph | none | IDs only |
| `replan.rejected` | UNSUPPORTED_BY_FRONTEND | declared raw name, no approved V1 payload | zero mutation/cursor; recover | no topology effect | none | quarantine identity only |
| `graph.task_added` | SUPPORTED | E+G+T-new; `{replan_id}` | REFRESH | Task exists only if replacement graph contains it | none | IDs/version only |
| `graph.edge_added` | SUPPORTED | E+G+T; exact source/target Task refs | REFRESH | edge only from replacement graph | none | IDs/version only |
| `graph.edge_removed` | SUPPORTED | E+G+T; exact source/target Task refs | REFRESH | edge only from replacement graph | none | IDs/version only |
| `graph.version_changed` | SUPPORTED | E+G; `{replan_id,version_before}` | REFRESH | one atomic authoritative graph version | none | IDs/versions only |
| `evidence.accepted` | SUPPORTED | E; safe Evidence allowlist; optional producer Task must belong to the exact Run | OBSERVE | advances only the safe event receipt; authoritative activity detail remains snapshot-owned | none | approved Evidence fields only |
| `evidence.conflict` | UNSUPPORTED_BY_FRONTEND | declared raw name, no stable V1 payload | zero mutation/cursor; recover | never infer Review/path state | none | quarantine identity only |
| `calculation.started` | SUPPORTED | E+T; `{capability_id}` | OBSERVE | receipt only; activity detail stays snapshot-owned | none | Capability ID only |
| `calculation.completed` | SUPPORTED | E+T; `{calculation_id,capability_id?}` | OBSERVE | receipt only; no financial value | none | IDs only |
| `capability.gap_detected` | SUPPORTED | E+T; exact gap/capability/skill/requester IDs | OBSERVE | same-Task receipt only | none | IDs only |
| `capability.build_requested` | SUPPORTED | E+T; exact IDs/attempt limits/approver | OBSERVE | same-Task receipt only | none | IDs/counts only |
| `capability.build_started` | SUPPORTED | E+T; `{build_id,attempt}` | OBSERVE | same-Task receipt only | none | ID/count only |
| `capability.generated` | SUPPORTED | E+T; safe build/capability/hash fields | OBSERVE | same-Task receipt only | none | IDs/hash only |
| `capability.static_validated` | SUPPORTED | E+T; `{build_id,implementation_hash}` | OBSERVE | same-Task receipt only | none | ID/hash only |
| `capability.sandbox_started` | SUPPORTED | E+T; `{build_id,implementation_hash}` | OBSERVE | same-Task receipt only | none | ID/hash only |
| `capability.test_passed` | SUPPORTED | E+T; `{build_id,implementation_hash}` | OBSERVE | same-Task receipt only | none | ID/hash only |
| `capability.test_failed` | SUPPORTED | E+T; `{build_id,attempt,failure_code}` | OBSERVE | same-Task receipt only | none | ID/count/code only |
| `capability.financial_validated` | SUPPORTED | E+T; `{build_id,implementation_hash}` | OBSERVE | same-Task receipt only | none | ID/hash only |
| `capability.approved` | SUPPORTED | E+T; exact build/registration/approver/scope | OBSERVE | receipt only; does not resume Task | none | IDs/scope only |
| `capability.registered` | SUPPORTED | E+T; exact registration/capability/version/scope | OBSERVE | receipt only; does not resume Task | none | IDs/version/scope only |
| `capability.build_failed` | SUPPORTED | E+T; exact safe failure/terminal and optional attempt IDs | OBSERVE | same-Task receipt only; `terminal:false` cannot fail Task | none | IDs/count/code/flag only |
| `workspace.created` | UNSUPPORTED_BY_FRONTEND | declared raw name, no approved V1 payload | zero mutation/cursor; recover | none | none | quarantine identity only |
| `capability.generation_started` | UNSUPPORTED_BY_FRONTEND | declared raw name, no approved V1 payload | zero mutation/cursor; recover | none | none | quarantine identity only |
| `capability.tested` | UNSUPPORTED_BY_FRONTEND | declared raw name, no approved V1 payload | zero mutation/cursor; recover | none | none | quarantine identity only |
| `capability.validated` | UNSUPPORTED_BY_FRONTEND | declared raw name, no approved V1 payload | zero mutation/cursor; recover | none | none | quarantine identity only |
| `review.started` | SUPPORTED | E; `{}` | REFRESH | none directly | does not terminate Run | status only from snapshot |
| `review.required` | UNSUPPORTED_BY_FRONTEND | declared raw name, no approved V1 payload | zero mutation/cursor; recover | none | none | quarantine identity only |
| `review.resolved` | SUPPORTED | E; `{review_id,status}` | REFRESH | none directly | does not terminate Run | Review ID/verdict only |
| `proof.required` | SUPPORTED | E; exact proof/calculation/formula/policy IDs | REFRESH | none directly | does not terminate Run | IDs only |
| `proof.started` | SUPPORTED | E; `{proof_id,backend}` | REFRESH | none directly | does not terminate Run | Proof ID/backend code only |
| `proof.generated` | SUPPORTED | E; `{proof_id,backend}` | REFRESH | none directly | generated is not verified/terminal | Proof ID/backend code only |
| `proof.verified` | SUPPORTED | E; exact proof/image/receipt/journal/verified/dev fields | REFRESH | none directly | does not terminate Run | IDs/hashes/flags only |
| `proof.failed` | SUPPORTED | E; `{proof_id,failure_code,status}` | REFRESH | none directly | does not alone terminate Run | ID/code/status only |
| `release.completed` | SUPPORTED | E; `{canonical_record_id,result_id}` | REFRESH | exposes release state from replacement | explicitly nonterminal | exact released IDs only |

## Fail-closed rule

Unknown names, the eight unsupported names, incompatible versions, malformed payloads,
wrong Run/Task/graph relationships, conflicting duplicates, stale unseen events, gaps,
and post-terminal events cause zero business mutation and zero cursor advance. The prior
validated projection remains visible as stale while the client performs exact same-Run
snapshot recovery.
