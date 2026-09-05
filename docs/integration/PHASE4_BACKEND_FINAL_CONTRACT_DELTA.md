# Phase 4 Backend Final Contract Delta Reconciliation

Status: `FINAL_DELTA_READY — CONTRACT_FREEZE_BLOCKED`  
Contract family: `phase4-core/v1`  
Event contract family: `phase4-runtime-event/v1`

## Final result

```text
PHASE4_BACKEND_FINAL_DELTA_READY=YES
UAC_CONTRACT_CLOSED=16/18
BD_CONTRACT_CLOSED=12/12
FRONTEND_CONTRACT_CONFLICTS=0
BACKEND_FRONTEND_FIELD_OWNERSHIP=EXACT
PHASE4_BACKEND_CONTRACT_FREEZE_READY=NO
PHASE4_IMPLEMENTATION_ACCEPTED=NO
PHASE4_CORE_ACCEPTANCE=NOT_EXECUTED
WAITING_FOR=REMEDIATION_AND_PASS_REAUDIT_OF_BACKEND_P1_AND_P2_FINDINGS_FOR_BOUND_PHASE3_CANDIDATE; REMEDIATION_AND_PASS_REAUDIT_OF_FINANCIAL_SEMANTICS_P1_AND_P2_FINDINGS_FOR_BOUND_PHASE3_CANDIDATE; OWNER_APPROVED_HASH_BOUND_V17_CONTRACT_INPUT_PACKAGE
```

This is a documentation-only contract decision. It does not authorize or start Phase 4
implementation.

## 1. Authenticated authority and tree state

| Authority | Bound value | Reconciliation result |
|---|---|---|
| Phase 3 candidate commit | `e02314c552d88fb736473bc587c650539615224a` | Git commit object authenticated. |
| Candidate tree | `af74ec7e6bcf40d281c0a1ea5463c794d795718f` | Exact tree of the candidate commit. |
| Candidate parent | `8c4a77ccb70bceb1e8bf496ea528682df95a3405` | Authenticated from the commit object. |
| Previous provisional inspection | `11fe8173a25ff7ac08bae42340ba7c6fae591be5` | Used only as the delta base. |
| Authoritative Run | `RUN-a5e58911-9b0f-4848-90fe-a65f436fa9c2` | Acceptance evidence binds this Run. |
| Migration | `20260904_0005` | Current candidate migration head. |
| Formal acceptance | `52/52 PASS`; financial subset `13/13 PASS` | Formal suite is valid evidence, but it does not override the later independent audit failure. |

The isolated candidate worktree was recorded clean in `candidate_identity.json`. At this
reconciliation, the shared coordinator checkout had no tracked or staged changes before these five
documents were added; it did contain pre-existing untracked frontend and documentation files. Those
files were preserved. “Clean candidate” therefore refers to the authenticated candidate worktree
and tree object, not to deletion or adoption of unrelated untracked files in the shared checkout.

Formal acceptance hashes:

| Evidence | SHA-256 |
|---|---|
| `acceptance_summary.json` | `bf84f2ed890fd0f339d272e9257668764048e1210f3cd1e4353beb6c8aee07ef` |
| `acceptance_matrix.json` | `4fa81c955cf873cfc96df56a72dd291a68ceec4d7581a84124e726bf17202f86` |
| `financial_semantics_matrix.json` | `4b68b78a39287308875a7ee51f653eb09630ff83c2a70d41aac79b720bdab90b` |
| `candidate_identity.json` | `1a61d215066f8ccbd7190e295ef00827dd74aea78f90768daf9c99d658901b28` |

## 2. Independent gates

| Gate | Observed state | Consequence |
|---|---|---|
| Backend Independent Final Audit | `FAIL`; audited SHA/Run match; `P0=0`, `P1=1`, `P2=1`, `P3=0`; no source modified; Phase 4 not authorized | UAC-001 remains open and the candidate must be remediated and independently re-audited to PASS. |
| Financial Semantics Independent Final Audit | `FAIL`; audited SHA/Run match; material metrics `10/10`; `P0=0`, `P1=1`, `P2=2`, `P3=0`; no source modified; Phase 4 not authorized | UAC-001 remains open and the candidate must be remediated and independently re-audited to PASS. |
| V17 contract-input package | Package complete and approval-ready; owner approval `PENDING` | UAC-002 remains open. No implemented V17 candidate is required. |

The Backend receipt identified:

1. P1 — generated source and unit-test preimages are not persisted or resolvable; the retained
   `generated://` references, hashes and booleans cannot independently reproduce `P3-CAP-003`,
   `P3-CAP-004`, `P3-CAP-008`, or `P3-CAP-011`.
2. P2 — the configured `LANGFUSE_PUBLIC_KEY` appears as
   `metadata.scope.attributes.public_key` on the root trace and all 88 observations (89 total
   occurrences), even though the candidate redaction policy classifies `public_key` as sensitive.

The Financial Semantics receipt identified:

1. P1 — generated FCF source and unit-test bytes were not retained; unresolved `generated://`
   references and hashes cannot independently reconstruct the executed implementation or verify its
   `implementation_hash`.
2. P2 — `revenue_growth_v1` executes `(current-prior)/abs(prior)`, not the required
   `(current-prior)/prior`; the accepted Run happens to use positive prior revenue.
3. P2 — MACD line and histogram use ambient Decimal precision; output changes with the ambient
   context while the reviewer separately hard-codes precision 28.

The final semantic contract removes ambiguity: generated source/test bytes must be retained and
hash-verifiable; `LANGFUSE_PUBLIC_KEY`/`public_key` must be omitted or irreversibly redacted from the
root trace, every observation and every exported copy; revenue growth preserves the signed prior
denominator; and every material operation uses an explicit `ROUND_HALF_EVEN` Decimal profile—28
digits for fundamental-ratio division and MACD line/histogram subtraction, 50 digits for technical
averaging and EMA recurrence. These are closed contract decisions; the current candidate is
nonconforming evidence and therefore cannot be the freeze-approved parent.

The finalized V17 package is bound for inspection as follows, but is not consumed as approved until
the owner gate closes:

| V17 member | SHA-256 |
|---|---|
| Canonical compact semantic payload | `36cf733d07b4df1ad4cb1065bdd17eceb6bbc98cf6f77fe0dfb1963185757e08` |
| JSON file bytes | `2d5bd33ff2c2b15df74773168ab16408391a45a105ebf8446c06cc55c2067512` |
| Markdown companion bytes | `02f86ca518bd0bbca5e2824b6fba32a48d0b0cfc48a75600da010b9a1240a695` |
| Package manifest bytes | `03520cb26b25a27ad0b4c87ee4c9d297e8bd875181ce8416ff587e87e6b7e75a` |
| Corrected V17 reference manifest | `44be67d6854a284055c19919bcaf979097c710b33d3e5f57c5f7a35fe376f394` |
| FCR `DRAFT-01` | `b20f2a0527638d057b1de62a6b154cdc8d50724d4aa75ee3491122fad3280df1` |

Package completeness is 13/13 normalized contracts, 12/12 Backend dependency records, 6/6
interaction reservations, and 6/6 Scene dispositions. `FRONTEND_IMPLEMENTATION_AUTHORIZED=NO` and
`FRONTEND_CANDIDATE_CREATED=NO` remain correct.

## 3. Candidate delta: `11fe8173…` to `e02314c5…`

There are eleven changed files. Every file was reclassified against the requested dimensions.

| Changed file | Classification | Contract effect |
|---|---|---|
| `scripts/run_phase3_acceptance.py` | acceptance-only; Generated Capability acceptance; runtime-observability acceptance | No public contract change. Oracle now accepts one active generated record while retaining failed attempts and binds scheme observation to the Run. |
| `src/application/phase3_financial.py` | financial metric; Generated Capability | No wire field change. Adds the high-precision Decimal validation fixture/oracle path. |
| `src/application/service.py` | application service; runtime observability | No API/DTO change. Adds internal optional `observation_run_id` correlation and rejects blank values. |
| `src/capabilities/generated/builder.py` | Generated Capability; financial metric | No wire change. Generated financial source is instructed to use Decimal-only arithmetic without float, `round`, or `quantize`. |
| `src/capabilities/generated/orchestration.py` | Generated Capability; persistence semantics; runtime observability | No event name/payload change. Persists sandbox `runtime_version` on the active generated record and retains non-active attempts as `BUILD_FAILED`. |
| `src/capabilities/generated/validation.py` | Generated Capability; financial metric | No wire change. Decimal schemas must import the owned Decimal runtime. |
| `tests/integration/test_generated_validation_pipeline.py` | acceptance-only; Generated Capability; financial metric | No production contract change. |
| `tests/integration/test_runtime_observability.py` | acceptance-only; runtime observability | No production contract change. |
| `tests/unit/generated/test_orchestration.py` | acceptance-only; Generated Capability; persistence semantics | No production contract change. |
| `tests/unit/generated/test_validation.py` | acceptance-only; Generated Capability; financial metric | No production contract change. |
| `tests/unit/test_phase3_financial_extension.py` | acceptance-only; financial metric; Generated Capability | No production contract change. |

Dimension result:

| Requested dimension | Delta effect |
|---|---|
| API | None. |
| DTO | None. |
| Domain | None. |
| Persistence | Internal generated-record lifecycle semantics changed in `orchestration.py`; no migration or public schema change. |
| Migration | None; head remains `20260904_0005`. |
| RuntimeEvent | No enum, event name, or payload change. |
| SSE | None. |
| Review | None. |
| Proof | None. |
| ReleasedResult | None. |
| Artifact | No ReportArtifact change. The audit's missing generated source/test bytes are capability-provenance evidence, now an explicit release-contract requirement. |
| Financial metric | Yes: Decimal/generation validation was strengthened; the independent audit nevertheless found signed-denominator and context defects outside this delta. |
| Generated Capability | Yes: prompt, validation, active/failed record persistence, runtime-version binding and acceptance changed. |
| Acceptance-only code | Yes: five test/acceptance files. |

No `EXISTING_BACKEND` conclusion from the `11fe8173…` inspection was carried forward silently.

## 4. Backend fact recheck at `e02314c5…`

| Surface | Revalidated fact |
|---|---|
| Run status | 10 raw values: `DRAFT`, `SCHEME_GENERATING`, `AWAITING_CONFIRMATION`, `PLANNING`, `RUNNING`, `REVIEW`, `PROVING`, `RELEASED`, `FAILED`, `CANCELLED`. |
| Task status | 12 raw values: `CREATED`, `WAITING`, `READY`, `RUNNING`, `WAITING_FOR_CAPABILITY`, `SELF_CORRECTING`, `BLOCKED`, `REVIEW`, `COMPLETED`, `FAILED`, `CAPABILITY_BUILD_FAILED`, `CANCELLED`. |
| RuntimeEvent | 55 declared values. The authoritative Run emits 640 events, 42 distinct types, with contiguous sequence `1..640`. The final V1 event contract supports 47 and explicitly rejects 8 as `UNSUPPORTED_EVENT`. |
| Evidence | 539 accepted records in the authoritative Run. |
| Calculation | 10 material records, all formal status PASS. |
| Claim | 10 typed `MATERIAL_FINANCIAL_METRIC` Claims. |
| Review | One Review, status `PASS`. |
| Proof | One required revenue-growth Proof, status `VERIFIED`. |
| CER | One canonical execution record. |
| ReleasedResult | One released result bound to the Run/CER lineage. |
| ReportArtifact | Three records: SVG chart, HTML report, PDF report. |
| Migration schema | Alembic head `20260904_0005`. |
| SSE replay | Full 640; numeric resume 320; same-Run opaque resume 320; tail heartbeat observed. Current frame remains `id:<sequence>`, `event:<raw type>`, `data:<unversioned RuntimeEvent JSON>`. |
| Idempotency | Current service cache is process-local, keyed by `(operation,key)`, not durable and not request-bound. This remains a Phase 4 implementation gap under closed UAC-007 semantics. |
| FastAPI composition | Default composition remains in-memory SQLite plus in-memory event/checkpoint stores; API description remains Phase 1; current confirm response is lowercase `planning`; Phase 4 public projection, trace and artifact-delivery routes are absent. |

The exact ordered list of all 55 raw RuntimeEvent values is embedded in the hash-bound `enum_map`
payload in the machine manifest. The final SSE contract remains snapshot-at-N followed by a strict
suffix, pre-header cursor validation, no clamping or replay-from-zero fallback, terminal close, and
sequence-free heartbeat comments.

## 5. Contract closure and frontend parity

- UAC: 16/18 semantically closed. `UAC-001` is open on independent audit acceptance;
  `UAC-002` is open on V17 owner approval. No additional UAC ID was created.
- BD: 12/12 semantically closed. Missing routes and executable evidence remain implementation work,
  not contract ambiguity.
- Frontend: 13/13 normalized contracts compared field-by-field. Identity, type, nullability, enum,
  availability, unknown handling and ownership have zero semantic conflicts.
- Historically implementation-bound `UAC-007`, `009`, `011`, `015`, and `016` are contract-closed
  with implementation evidence pending; the contract/implementation deadlock is not recreated.

The independent financial failure is not hidden by the zero frontend-conflict count: it blocks the
parent/audit gate even though the final wire-to-adapter contract is exact.

## 6. Immutable contract hashes

Canonical inline payloads use UTF-8 compact JSON, recursively sorted object keys and preserved array
order. File hashes cover exact bytes. The machine manifest identifies the scope for every entry.

| Contract component | SHA-256 |
|---|---|
| API schema contract | `2a1265753c1b7b6e0756ea9c40886dcbcbdf4773e81e467b7df8fddd92763048` |
| Runtime Event contract | `f6bbca7123051c90d3321781b3e47d4028a457f2ee8a0f51a37acf836b38cf2e` |
| Error/availability contract | `5cd8dd06203707b3b9597bc4dbfdc343d7c84884bf2c73982a22cff2f9ffd79a` |
| Access-mode decision | `c32ac85f7930ab151fbb769350bed270549bdb132489c5c769ec7ef1e042415d` |
| Final UAC disposition | `226a586e696f92fe6249f7c043ea005291858e7c1bcf46d5a825d1ecf595146c` |
| BD/UAC crosswalk | `a3e76d8a9eda32ffa85be9e2d744dd2a26a22554ad30676e50ddce4d97941b59` |
| Field ownership matrix | `e91ed0321a96067f93eb0b1a284c7374b1919688e2db52c9e4e9cda360d93569` |
| Route inventory | `0a96e2ac182290820a01a4e6869b3053c55a3dc994b0bf7095acec73c809c4b1` |
| Enum map | `656b14d7787b3a0db3b9d8b0b50ba4c97911aedc5f7c11318cbfa2e904582f6f` |
| `VersionProtocolV1` | `ebac4e85f21f9cc145043c9b39d3ca8d04030f8c332b951bb326ab0f4de958fb` |
| `CursorProtocolV1` | `5578976fb01c7ebacaac039a93f21c57cbb2ff51868f7a64513e61660aa42b01` |
| Artifact policy | `1c912c1864aa2c5940182148706757d3f6c92e7c620d275f9c60503e0f30959a` |
| Release policy | `0a823de3f31ec730d32164eec15a0090bd7841ece715603ba57633dd19a9ac63` |
| Financial projection contract | `1c165059432174062625f2a0a969454e831eb2db7a89d9eb52119c6e2f6bfdcf` |

Aggregate contract-set hash over the sorted canonical array of `{id,sha256}` entries:

```text
0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741
```

## 7. Freeze decision

The delta reconciliation itself is complete. Contract Freeze is not ready because both independent
audits are material `FAIL` receipts requiring remediation and PASS re-audits, and the hash-bound V17
package has not been owner-approved. Formal 52/52 acceptance, 12/12 BD closure, exact field
ownership and zero frontend contract conflicts do not waive any of those gates.

No production source, migration, test, configuration or frontend implementation file was modified
by this reconciliation.
