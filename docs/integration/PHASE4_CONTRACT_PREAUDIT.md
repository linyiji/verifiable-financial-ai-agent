# Phase 4 Frontend / Backend Contract Pre-Reconciliation Audit

Classification: `PROVISIONAL_CONTRACT_PREAUDIT`

Decision: `PHASE4_CONTRACT_PREAUDIT = READY_WITH_GAPS`

This is a read-only/design-only audit of moving targets. It does not authorize Phase 4 implementation, REST/SSE wiring, contract changes, migrations, fixture changes, branch merges, or commits. `READY_WITH_GAPS` means the source inventories are sufficiently concrete to define a small freeze gate; it does not mean integration should begin before that gate is resolved.

## 1. Inspected baselines

The path supplied as the backend project is the primary checkout, but the active Phase 3 candidate was independently identified from `git worktree list` as `codex/phase3-contracts`. The audit uses that active candidate because it contains the current Phase 3 contracts. The primary checkout is recorded separately to avoid silently substituting a branch.

| Role | Worktree | Branch | HEAD | Dirty | Inspected snapshot |
|---|---|---|---|---|---|
| Project checkout | `/Users/mac/Verifiable_Financial_Agent_System` | `main` | `ed8af4ba8c51ada227f433582654ced0e16ca3c4` | Yes; 2,509 untracked files, dominated by the untracked frontend package and audit/design material | `sha256:2df1385eda34983cf8cdd6f3d83cf36563c30bed234b416b936f9fc5e8223a94` |
| Backend Phase 3 candidate used by this audit | `/Users/mac/Verifiable_Financial_Agent_System_worktrees/phase3-coordinator` | `codex/phase3-contracts` | `5e846326edb70ac3eb7d94910cd6d3008737da22` | Yes; 44 modified + 9 untracked files | `sha256:f0101a685d10b801466f9dad9bd3b8e74221b8bd5ec0b1e9e1b5e4f176fcc592` |
| Frontend V8 remediation candidate | `/Users/mac/Verifiable_Financial_Agent_System_frontend_v8_fixes` | `ws/frontend-v8-preintegration-fixes` | `a850bce3cf0b8a72bc28c7ce16a67e9f83be0c84` | No | `sha256:58acca018c47807112b51dba49fcf63832812f1e49b698edf825a26703e3b309` |

Snapshot hashes cover `HEAD`, porcelain-v2 status, staged and unstaged binary patches, and a sorted `(path, SHA-256)` manifest of every untracked file. Supporting backend hashes are:

- tracked patch: `sha256:292c540e14292d0faffe8bbe5d725db41b0e2ab6a03a9b0b5289bbb5b836de6e`
- untracked manifest: `sha256:45995403ecd66c3ef86a6bf2e680a19f1cdb1152a8d9c125137267f3fb506098`

The backend changed during the audit without a HEAD change: the first observed snapshot was `sha256:dd294b4f9de143f4ce6ba71a3b2624a41cc63bb1844ae15b96ee9cb4f6368894` (39 modified + 9 untracked), an intermediate cut was `sha256:ded06671708c6fdd8d6bac5c854f2626f38a96a71204696e1ef7faf75433d0c9`, and the contract cut used for the final matrices is the later `f0101a…` snapshot above. Two consecutive fingerprints of the final cut matched. The focused reread found strengthened financial/release validation plus package/migration/test edits, with no change to the reported wire-contract conclusions. This is direct evidence for retaining the provisional classification.

Backend candidate dirty manifest:

```text
 M package.json
 M src/adapters/finrobot/charts.py
 M src/adapters/finrobot/professional_reporting.py
 M src/adapters/finrobot/technical.py
 M src/adapters/fmp/provider.py
 M src/adapters/risc0/adapter.py
 M src/application/evidence_collection.py
 M src/application/evidence_routing.py
 M src/application/execution.py
 M src/application/extensions.py
 M src/application/phase3_financial.py
 M src/application/phase3_proof.py
 M src/application/service.py
 M src/assurance/__init__.py
 M src/assurance/release_gate.py
 M src/capabilities/calculation_lineage.py
 M src/capabilities/financial/growth.py
 M src/capabilities/financial/profitability.py
 M src/capabilities/generated/validation.py
 M src/data/ingestion.py
 M src/data/persistence.py
 M src/domain/canonical_execution_record.py
 M src/domain/capability.py
 M src/domain/enums.py
 M src/domain/evidence.py
 M src/domain/released_research_result.py
 M src/domain/report.py
 M src/domain/review.py
 M src/domain/task.py
 M src/infrastructure/database/migrations.py
 M src/output/canonical.py
 M src/output/release.py
 M tests/financial/test_finrobot_technical_indicators.py
 M tests/integration/test_evidence_semantics_persistence.py
 M tests/postgresql/test_postgresql_runtime.py
 M tests/unit/adapters/test_finrobot_professional_reporting.py
 M tests/unit/application/test_evidence_semantics.py
 M tests/unit/test_phase3_contracts.py
 M tests/unit/test_phase3_financial_extension.py
 M zk/revenue_growth/Cargo.toml
 M zk/revenue_growth/build-host.sh
 M zk/revenue_growth/methods/build.rs
 M zk/revenue_growth/methods/guest/Cargo.lock
 M zk/revenue_growth/methods/guest/Cargo.toml
?? alembic/versions/20260904_0005_financial_evidence_semantics.py
?? scripts/run_phase3_acceptance.py
?? src/adapters/risc0/release_manifest.py
?? src/assurance/independent_financial_review.py
?? src/domain/financial_semantics.py
?? src/output/financial_metrics.py
?? tests/test_phase3_acceptance_runner.py
?? zk/revenue_growth/RISC_ZERO_RELEASE_MANIFEST.json
?? zk/revenue_growth/normalize_macos_host.py
```

The conclusions below apply only to those fingerprints. No old SHA was assumed.

## 2. Frontend required-contract inventory

| Consumer / contract | Actual requirement in the remediation candidate | Current implementation state |
|---|---|---|
| `FrontendDataSource` | Object list/search/create/detail/financials/runs; global Run collection; Run/detail/projection; prepare/confirm; Claim list/detail; Review, Execution and ReportArtifact reads | Interface is concrete; `DemoFrontendDataSource` is the only implementation |
| `HttpFrontendDataSource` | Same interface through a future HTTP adapter | Fail-closed placeholder; every method rejects |
| `RuntimeTransport` | Per-Run event subscription with event/error callbacks | Interface has no initial cursor, snapshot watermark, reconnect state, or terminal callback |
| `SSERuntimeTransport` | Browser SSE implementation | Fail-closed placeholder; opens no `EventSource` |
| `RuntimeEvent` | `{event_id, run_id, task_id?, type, timestamp, sequence, payload}` | 23-event frontend union |
| `RuntimeProjection` | Atomic Run + Claims + Reviews + ReportArtifact + Execution + ReleasedResult + events + `lastSequence` | Demo-owned aggregate; no backend DTO exists |
| `reduceRuntimeEvent` | Sole live-state reducer; Run isolation; event-id dedupe; guarded release | Applies events immediately even if sequence is stale/gapped; sorts only after mutation |
| Research Run collection | status/stage/progress/activity/graph version/object identity/timestamps/results availability | `listResearchRuns()` required; Demo only |
| Research Run detail | planned vs actual Tasks, path changes, graph version, proof/release state, observable task history | Demo projection is richer than backend `ResearchRun` |
| Task detail | task identity, status/progress, agent/skill/tool, evidence/calculation refs, correction/replan/error summaries, events | Requires a projection over Task + event log + artifacts |
| Financial Review | per-Claim PASS/uncertainty/review/block plus open/resolved exception history and correction path | Frontend enum and record shape exceed current backend view |
| Claim Trace | exact Claim → report/review/task/evidence/calculation/proof/execution anchors | Typed frontend contract; evidence/calculation bodies remain placeholders |
| `ReportArtifact` | lifecycle, renderer, preview, HTML/PDF availability and same-Run identity | Demo shape combines preview and both representations |
| Research Object | display metadata, data status, run count/latest release | Requires projection over object + runs/results |
| Object history/comparison | versioned Research Views and previous/current differences with same-Run Claim links | Demo Scene 5/6 only |
| Prepare/Confirm | prepare returns visible plan/tasks; confirm uses stable plan identity and creates exactly one Run | Demo in-memory contract uses `planId`; HTTP semantics unresolved |
| Deployment status | mode/source/LLM/trace/sandbox/proof/artifact truth | Not represented in frontend domain types |

## 3. Backend actual-contract inventory

| Backend concept | Actual candidate contract | Integration significance |
|---|---|---|
| `ResearchObject` | `object_id`, symbol, company name, exchange, sector, currency, identity version, timestamps | Strong core identity; lacks frontend industry/country and derived UI state |
| `ResearchRun` | `run_id`, `research_object_id`, goal/scheme ids, `RunStatus`, as-of, graph ids, execution target, start/completion | Core record only; no frontend stage/progress/activity |
| Scheme / plan | `ResearchRunDraft` contains Goal + `ResearchSchemeSnapshot`; planned graph is created only during confirm | Semantically different from frontend prepare-visible `ResearchPlan` |
| Task / graph | Typed `Task`, immutable planned graph, mutable versioned actual graph and replan records | Sufficient basis for Run/Task projection; dynamic event payloads are not self-contained |
| `RuntimeEvent` | Same six envelope fields; much larger enum; per-Run monotonic sequence | Envelope matches except graph version; event meanings/payloads need normalization |
| Checkpoint | Run/task/actual graph/review/proof/cost snapshot with PostgreSQL store | Internal recovery primitive; no coherent frontend snapshot route |
| `EvidenceRecord` | Run + object + producer task, temporal/period/unit/currency semantics and artifact ref | Strong lineage source |
| `CalculationRecord` | Run + task + capability/formula/input evidence/output/unit/review/canonical/proof refs | Strong deterministic lineage source |
| Judgment | `list[JsonObject]` inside completed artifacts/released result; ids are conventionally extracted | No typed, independently queryable Judgment contract |
| Claim | `MaterialFinancialClaim` with run, metric, value/unit/period/as-of and calculation/evidence/judgment refs | Strong financial claim, but no object/task/review/proof/report anchors |
| `ReviewRecord` | One run-level record with reviewed refs, checks and PASS/REVIEW/BLOCK | Not a per-Claim or exception-history UI projection |
| `ProofRecord` | Run + calculation + proof identity/bindings/status; separate verification and artifact records | Strong proof lineage; Claim association is indirect through calculation |
| `CanonicalExecutionRecord` | Run, object snapshot ref, both graphs and all lineage ref sets | Correct authority for Execution and Trace assembly |
| `ReleasedResearchResult` | Run + canonical record + typed metrics/claims/dispositions/source coverage/judgments/limitations | Correct release authority |
| `CanonicalReportDTO` | Immutable mapper output from released result + canonical record | Correct renderer input, not the frontend report DTO |
| `ReportArtifactRecord` | Immutable representation with run, MIME-like type, internal ref, hashes, renderer version, canonical/result ids, size/time | Compatible basis for a Phase 4 delivery envelope; raw record is unsafe/incomplete for direct exposure |
| Generated Capability | Typed gap/build/generated/sandbox/validation/registration records and detailed event lifecycle | Backend lifecycle now exists; frontend vocabulary is stale |
| Capability waiting/resume | Original Task enters `WAITING_FOR_CAPABILITY`, lifecycle is supporting activity, then same Task resumes | Matches the product invariant that no Research Task is created |
| SSE | Persisted replay, numeric SSE id = sequence, `Last-Event-ID`, comment heartbeat and terminal close in API stream | Strong base; snapshot/watermark and frontend cursor contract are missing |
| PostgreSQL | Run aggregates, tasks/dependencies, events, checkpoints, evidence, calculations, review, canonical/released, capability/proof/artifact records | Persistence exists; some app defaults still use in-memory SQLite and service idempotency is process-local |
| Deployment status | `OperatingMode` enum only | Frozen status projection remains future design, not implemented behavior |

## 4. FBG-001..008 reassessment

| FBG | Provisional state | Reassessment |
|---|---|---|
| FBG-001 Research Run collection | `STILL_OPEN` | Backend has object-scoped `GET /objects/{object_id}/runs` and repository support, but no authoritative global collection, filters/pagination, progress/activity, or results-availability projection. |
| FBG-002 SSE resume / projection recovery | `PARTIALLY_RESOLVED` | Backend now has durable per-Run sequence, replay, `Last-Event-ID`, heartbeat and terminal close. A coherent snapshot + watermark, frontend initial-cursor API, gap handling and deterministic recovery remain undefined. |
| FBG-003 Capability waiting | `CONTRACT_CHANGED` | Backend now owns a detailed lifecycle (`gap_detected` through `task.resumed`). Frontend still assumes synthetic `capability.validating`, handles only three lifecycle events, and cannot consume the real payloads. |
| FBG-004 ReportArtifact | `PARTIALLY_RESOLVED` | Backend has immutable HTML/PDF artifact records and renderers, but publishing is not in the normal API path and the frontend-safe lifecycle/authorization/object-binding/preview/anchor response does not exist. |
| FBG-005 Financial Review projection | `PARTIALLY_RESOLVED` | Backend has typed review checks and reviewed ref sets, but the exposed view contains only ref arrays. Per-Claim records, exceptions, uncertainty, correction path, user-action semantics and resolved history remain projections. |
| FBG-006 Claim Trace | `PARTIALLY_RESOLVED` | Typed Claim/metric/evidence/calculation/proof/canonical lineage now exists. Direct task/review/proof/report anchor linkage, typed Judgment and detail endpoints remain missing. |
| FBG-007 Versioned Research Object | `PARTIALLY_RESOLVED` | Multiple Runs and per-Run writeback proposals persist, but no applied version store or comparison DTO exists. Keep true memory/comparison in Phase 5; do not make POT a Phase 4 dependency. |
| FBG-008 Prepare/Confirm identity & idempotency | `CONTRACT_CHANGED` | Backend uses `draft_id` + scheme confirmation and creates the planned graph only on confirm; frontend uses a prepare-visible `planId`. Backend idempotency is process-local and does not bind key to request/draft or define expiry/retry conflict. |

No FBG is closed because no matching end-to-end HTTP/SSE contract exists.

## 5. Highest-risk semantic deltas

1. Backend Task progress is a float in `0..1`; frontend displays the event value as percent in `0..100`.
2. Backend emits `task.correction_resolved`; frontend accepts `correction.resolved`.
3. Backend `review.resolved` records completion of the run-level review; frontend treats that name as resolution of an exception record.
4. Backend graph events use `replan_id` and `version_after`; frontend expects `change_id`, `graph_version` and dependency data and otherwise invents a display Task.
5. Backend lifecycle has `run.completed`/`run.failed`; the frontend event union omits both and guards completion through `release.completed` plus data not present in that event.
6. Backend emits no `claim.materialized`, `report.started`, or `result.prepared`; those frontend transitions require snapshot refresh or a deliberately introduced Phase 4 projection event.
7. Backend `RunStatus`, `TaskStatus`, `ReviewStatus` and frontend display enums are not wire-compatible and must never be cast directly.

The detailed field matrix and event mapping are in the companion documents.

## 6. ReportArtifact delta against the frozen deployment design

Overall classification: `SPEC_UPDATE_REQUIRED`. The internal Phase 3 storage record is a `COMPATIBLE_DELTA`, but the frozen deployment DTO does not include the Claim-anchor relationship required by the frontend. Direct exposure of `ReportArtifactRecord` would be a `BLOCKER`.

The actual record already supplies immutable representation identity, `run_id`, MIME type, content hash, byte size, renderer version, canonical record id, released result id and generated time (`created_at`). A Phase 4 projection can safely map these without changing the Phase 3 record. It must additionally:

- verify and add `research_object_id` through Run/canonical binding;
- define `report_id = released_result_id` or explicitly choose a distinct report-version id;
- split `artifact_type` into reviewed `format` and `content_type`;
- normalize `sha256:<hex>` only at the adapter boundary if the frozen DTO retains bare hex;
- split the combined renderer version into `{name, version}` without guessing;
- expose `availability` and safe `failure_code`;
- replace the internal `artifact://...` reference with an opaque, authorized same-origin reference;
- group HTML and PDF as separate representations;
- carry an explicit Claim-anchor manifest; the current rendered HTML has no per-Claim deep-link contract.

`semantic_hash` and `metric_semantics_hash` are compatible integrity extensions but require explicit review before becoming public fields.

| Frozen/required field | Actual Phase 3 source | Delta class | Resolution |
|---|---|---|---|
| artifact ID | `artifact_id` | `MATCH` | Preserve as opaque representation id. |
| object ID | Indirect through Run/canonical `object_snapshot_ref` | `COMPATIBLE_DELTA` | Verify the join and add `research_object_id` in delivery projection. |
| run ID | `run_id` | `MATCH` | Preserve. |
| report ID | `released_result_id`; no separate report version | `COMPATIBLE_DELTA` | Explicitly define `report_id` as released result id or choose a distinct version id. |
| format | Encoded in `artifact_type` | `COMPATIBLE_DELTA` | Map reviewed MIME values to HTML/PDF. |
| content type | `artifact_type` (`text/html` or `application/pdf`) | `COMPATIBLE_DELTA` | Freeze charset handling for HTML. |
| hash | `content_hash` as `sha256:<hex>` | `COMPATIBLE_DELTA` | Preserve or normalize prefix at one boundary. |
| size | `size_bytes` | `MATCH` | Preserve and verify against delivered bytes. |
| renderer | Combined `renderer_version` | `COMPATIBLE_DELTA` | Split name/version through an explicit mapping. |
| generated time | inherited `created_at` | `COMPATIBLE_DELTA` | Map to `generated_at` as RFC 3339 UTC. |
| availability | Record existence only | `COMPATIBLE_DELTA` for wrapper; raw `BLOCKER` | Delivery projection owns pending/available/unavailable/failed state. |
| authorized reference | Internal `artifact://...` | `BLOCKER` if exposed | Mint/resolve an opaque same-origin reference with the same identity authorization. |
| Claim anchors | Not in actual record or frozen DTO | `SPEC_UPDATE_REQUIRED` | Add a reviewed adjacent anchor manifest or extend the grouped report projection; scope it to report/artifact/Claim. |

## 7. Object versioning boundary

Current backend support:

- multiple durable Runs per object;
- per-Run canonical/released records;
- an `ObjectWritebackProposal` with canonical-state and versioned-metric targets;
- object-scoped Run listing;
- current API responses that return proposals and a lossy list of financial-summary versions.

Not currently supported:

- an applied versioned Research Object store;
- a stable Research View snapshot DTO;
- prior/current comparison records;
- changed/unchanged Claim identity rules;
- incremental memory/reuse decisions backed by durable object history.

Phase 4 should require only correct object/run collection, latest released-run selection, and exact same-Run linking. Scene 5/6 history/comparison stays Demo-only until Phase 5 Object Memory. POT is not a Phase 4 prerequisite.

## 8. Deployment status boundary

The backend defines `OperatingMode` values, but neither candidate exposes or projects the frozen fields `deployment_mode`, `data_source`, `llm_status`, `trace_status`, `sandbox_status`, `proof_policy`, `proof_status`, or `artifact_status`. The current `/health` response is liveness-only. These fields remain `FUTURE_RP2`; Phase 4 must not fabricate them from missing data.

## 9. Smallest safe Phase 4 contract set

### `MUST_FREEZE_BEFORE_PHASE4`

- identity joins and fail-closed cross-Run/object rules;
- explicit enum/progress normalization maps;
- prepare/confirm request, response, expiry/version and durable idempotency semantics;
- global Run collection and one coherent Run projection shape;
- projection watermark + SSE initial cursor, ordering, gap and recovery protocol;
- normalized event names/payloads, especially correction, review, terminal and capability lifecycle;
- lossless released financial metric projection;
- per-Claim review/trace projection and report/execution anchor ownership;
- frontend-safe ReportArtifact group, availability and authorized delivery contract.

### `CAN_ADAPT_DURING_PHASE4`

- route naming differences behind `api/client.ts`;
- snake_case ↔ camelCase conversion;
- UI-only labels, duration formatting and derived stage text after the authoritative status map is frozen;
- pagination control presentation and non-authoritative empty/loading text;
- separate detail routes versus one backend composition service, provided one atomic frontend projection is returned.

### `PHASE5+`

- true Object Memory, applied writeback and version history;
- prior/current comparison and Claim-revision classification;
- durable incremental reuse/refresh/revalidate strategy;
- richer typed Judgment model if not required for the Phase 4 trace subset.

### `DEPLOYMENT_RP2+`

- operator-visible deployment/component status;
- mode-alignment/readiness surfaces;
- release manifest and artifact-store operational status;
- public/limited/offline policy projection.

## 10. Provisional conclusion and next action

There is no evidence of an irreconcilable frontend/backend model. The backend has enough authoritative primitives to avoid duplicating domain truth, but the wire projections are not yet safe to implement. The result is therefore:

```text
PHASE4_CONTRACT_PREAUDIT = READY_WITH_GAPS
PROVISIONAL = true
PHASE4_IMPLEMENTATION_AUTHORIZED = false
```

When final backend and frontend candidate SHAs exist, perform only a focused delta reconciliation:

1. re-fingerprint both candidates;
2. diff only the source contracts and findings referenced by these five documents;
3. reclassify changed matrix rows and FBG states;
4. freeze the `MUST_FREEZE_BEFORE_PHASE4` set;
5. do not reopen Phase 3, frontend remediation, deployment design, or Demo fixture scope unless a delta directly invalidates one of these findings.

## Evidence index

Frontend evidence: `apps/web/src/types/domain.ts`, `data/FrontendDataSource.ts`, `data/HttpFrontendDataSource.ts`, `runtime/RuntimeTransport.ts`, `runtime/SSERuntimeTransport.ts`, `state/runtimeEventReducer.ts`, and `docs/frontend_v8/*` in the frontend candidate.

Backend evidence: `src/domain/*`, `src/runtime/*`, `src/application/{service,events,persistence,models}.py`, `src/infrastructure/database/*`, `src/output/*`, `src/capabilities/generated/orchestration.py`, `src/adapters/finrobot/professional_reporting.py`, `contracts/api/models.py`, and `apps/api/routes.py` in the Phase 3 candidate.

Frozen deployment evidence: `docs/deployment/COMPETITION_RELEASE_IMPLEMENTATION_PLAN.md` and `docs/deployment/DEPLOYMENT_MODE_CONTRACT.md` in the supplied project checkout.
