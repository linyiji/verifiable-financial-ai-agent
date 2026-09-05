# Phase 4 Backend Final UAC Disposition

Status: `FINAL_DELTA_RECONCILED — FREEZE_INPUTS_PENDING`  
Contract family: `phase4-core/v1`  
Phase 3 candidate: `e02314c552d88fb736473bc587c650539615224a`  
Phase 3 tree: `af74ec7e6bcf40d281c0a1ea5463c794d795718f`  
Authoritative Phase 3 Run: `RUN-a5e58911-9b0f-4848-90fe-a65f436fa9c2`

## Decision rule

`CONTRACT_CLOSED` means the semantic contract is exact enough to freeze and implement. It does not
mean the Phase 4 implementation exists or that Phase 4 acceptance evidence passed. `STILL_OPEN`
means a required authority input is not yet approved or its required independent receipt is absent.
No new UAC identifiers are introduced.

The formal Phase 3 acceptance bundle is bound at 52/52 PASS with migration `20260904_0005`.
Both independent audits issued `FAIL` for the bound SHA/Run. Backend reported one P1 and one P2:
generated source/test preimages are not independently reproducible, and the Langfuse public key is
exposed in the root trace plus all 88 observations. Financial Semantics reported one P1 and two P2:
the same generated FCF source/test defect, `revenue_growth_v1` uses `abs(prior)` instead of the
contract denominator `prior`, and MACD arithmetic does not bind its Decimal context. The governed
V17 input package is complete and hash-bound, but owner approval is still pending. Those facts keep
UAC-001 and UAC-002 open without reopening the other sixteen semantic decisions; the audit findings
are candidate/evidence nonconformities against explicit closed contracts, not unresolved choices.

## Final semantic disposition

| UAC | Decision | Contract decision state | Implementation evidence | Bound semantic decision | Exact remaining dependency |
|---|---|---|---|---|---|
| `UAC-001` | `STILL_OPEN` | `CONTRACT_DECISION_READY / BOTH_INDEPENDENT_AUDITS_FAILED` | `NOT_APPLICABLE_TO_THIS_ROW` | Bind candidate `e02314c…`, tree `af74ec7…`, Run `RUN-a5e58911…`, migration `20260904_0005`, and formal 52/52 acceptance. Backend is `FAIL` (`P1=1`, `P2=1`); Financial Semantics is `FAIL` (`P1=1`, `P2=2`). Formal acceptance does not waive either receipt. | Remediate every Backend and Financial Semantics finding, then obtain independent `PASS` receipts explicitly bound to the resulting approved Phase 3 SHA/tree/Run. |
| `UAC-002` | `STILL_OPEN` | `CONTRACT_DECISION_READY / CONTRACT_INPUT_OWNER_APPROVAL_PENDING` | `NOT_APPLICABLE_TO_THIS_ROW` | Consume canonical V17 package hash `36cf733d…` binding corrected manifest `44be67d6…`, FCR `DRAFT-01`, 13/13 normalized contracts, 12/12 BDs and interaction/Scene dispositions; no V17 implementation candidate SHA is required. | Owner approval/freeze of the hash-bound V17 package. |
| `UAC-003` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | `VersionProtocolV1`: stable `/api`; exact request token `phase4-core/v1`; fail-closed 409 for malformed/unsupported values; exact response headers and DTO versions. | Phase 4 negotiation implementation and acceptance only. |
| `UAC-004` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | `CursorProtocolV1`: snapshot-at-N, strict numeric or exact same-Run opaque resume, pre-header validation, cursor-ahead rejection, terminal close, no clamp/from-zero fallback. | Phase 4 cursor/SSE implementation and `P4-SSE-001..020` evidence only. |
| `UAC-005` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | Confirm returns immutable `RunAdmissionV1` plus transport-only `ResponseMetaV1`; replay metadata never mutates admission. | Phase 4 DTO/persistence and response-loss/restart evidence only. |
| `UAC-006` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | Access mode is exactly `phase4-local-single-user-trusted/v1`; server scope `LOCAL_SINGLE_USER`; no client actor/tenant/workspace authority; exact nested identity remains mandatory. | Phase 4 identity/artifact negative evidence only. |
| `UAC-007` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | `RunSchedulerAdmissionV1`: durable request-bound admission, fenced lease/redelivery, exactly one logical Run start and one auto-start outcome. | Durable Phase 4 implementation and crash/redelivery evidence only. |
| `UAC-008` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | Backend owns revision, sequence, graph and path changes; `ACTUAL_TASK_MEAN_V1` owns fraction; adapter alone derives presentation percent. | Phase 4 projection implementation and ownership evidence only. |
| `UAC-009` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | One per-Run serialized PostgreSQL transaction publishes aggregate changes, RuntimeEvents and one projection-revision increment with an MVCC-consistent watermark. | Phase 4 transactional implementation and race/rollback/restart evidence only. |
| `UAC-010` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | Total Run, Task, Review, Proof, availability and all 55 raw RuntimeEvent dispositions are frozen; unknown values fail closed and recover from an authoritative snapshot. | Phase 4 map implementation and exhaustive fixtures only. |
| `UAC-011` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | `TerminalFailureV1`: exactly one durable finalizer and `run.failed`, zero `run.completed`, terminal event last, no later business event. | Phase 4 all-path failure and duplicate/restart evidence only. |
| `UAC-012` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | `ClaimDetailV1` closes exact same-Run Claim/Metric/Calculation/Evidence/Task relations; typed Judgment detail is available or explicitly unavailable; no inferred primary Task. | Phase 4 Claim/Judgment projection and negative evidence only. |
| `UAC-013` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | `FinancialReviewProjectionV1` has stable Check identity, typed subjects, immutable original status, exact correction/exception history, input hash, and A/B/C joins. | Durable Check/history implementation and evidence only. |
| `UAC-014` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | `TraceBundleV1` closes exact same-Run lineage and a hash-bound representation-scoped anchor manifest with plural Review/Task/Execution anchors. | Phase 4 routes, manifests and substitution/integrity/restart evidence only. |
| `UAC-015` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | `authorized_ref` is a non-bearer same-origin path; every byte GET rechecks scope/identity/availability/integrity; internal locators never cross the wire. | Artifact delivery/storage implementation and negative evidence only. |
| `UAC-016` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | Artifact policy is `phase4-html-required-pdf-optional/v1`; HTML/PDF have independent append-only attempts, identities, availability, failure and terminal rules. | Phase 4 renderer/attempt persistence and fault/restart evidence only. |
| `UAC-017` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | `phase4-release-eligibility/v1`; exact eligible-set selection by `(released_at DESC, run_id DESC)`; ten-member FULL material manifest; lossless financial projection; generated source/test bytes are immutable and hash-verifiable; revenue growth divides by signed `prior`; every material formula uses an explicit half-even Decimal profile (precision 28 for fundamental-ratio division and MACD line/histogram subtraction; precision 50 for technical averaging/EMA recurrence). | Phase 4 release-validation record, selector and financial acceptance only. The bound Phase 3 independent financial receipt demonstrates three nonconformities; it is not Phase 4 implementation acceptance. |
| `UAC-018` | `CONTRACT_CLOSED` | `FINAL_SEMANTICS_EXACT` | `PENDING` | One `ErrorEnvelopeV1`, total HTTP/retry/recovery table, identity concealment, availability invariants and safe redaction. `LANGFUSE_PUBLIC_KEY`/`public_key` is sensitive despite its name and must be omitted or irreversibly redacted from the root trace, every observation and every exported telemetry copy. | Phase 4 error/availability/telemetry implementation and negative evidence only. The bound candidate fails this redaction contract. |

## Orthogonality check

The historically implementation-bound rows `UAC-007`, `UAC-009`, `UAC-011`, `UAC-015`, and
`UAC-016` are `CONTRACT_CLOSED` with `implementation_evidence=PENDING`. This is intentional and
does not recreate the contract/implementation deadlock.

```text
UAC_TOTAL=18
UAC_CONTRACT_CLOSED=16/18
UAC_STILL_OPEN=2/18
UAC_STILL_OPEN_IDS=UAC-001,UAC-002
UAC_IMPLEMENTATION_EVIDENCE_PENDING=16
UAC_SEMANTIC_DECISION_REQUIRED=0
```
