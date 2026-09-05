# Phase 4 Wave 1 — Codex C Handoff

Status: `C-OWNED ACCEPTANCE PASS; PARENT INTEGRATION REQUIRED`

- Planned branch: `phase4/run-sse`
- Parent-authorized actual branch: `p4-run-sse`
- Worktree: `/Users/mac/Verifiable_Financial_Agent_System_phase4/run-sse`
- Base SHA: `4b6721b6db433aae300f94750e1a405b6b450501`
- Base tree: `35c47508ed65220c26620f5ec4bdd14cb798480d`
- C implementation prerequisite SHA: `ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86`
- Final branch SHA: the signed-off `origin/p4-run-sse` HEAD is recorded in the final
  required task output after this handoff document is committed.

No Parent-only source file was modified. The six C frontend files were materialized
byte-for-byte from approved V17 R2 commit
`d854c97789c98cca14fee3f4b3d7f00e0d5d137a` before semantic edits.

## Files changed

- Frontend runtime/path: `apps/web/scripts/runtime-reducer.test.mjs`,
  `apps/web/src/components/research-path/ResearchPath.tsx`,
  `apps/web/src/components/tasks/TaskDetailDrawer.tsx`,
  `apps/web/src/runtime/RuntimeTransport.ts`,
  `apps/web/src/runtime/SSERuntimeTransport.ts`, and
  `apps/web/src/state/runtimeEventReducer.ts`.
- Event/runtime backend: `contracts/events/runtime_event.schema.json`,
  `src/application/events.py`, `src/domain/runtime_event.py`,
  `src/infrastructure/database/checkpoints.py`,
  `src/infrastructure/database/postgresql_events.py`,
  `src/runtime/checkpoint.py`, `src/runtime/events.py`,
  `src/runtime/lifecycle.py`, `src/runtime/scheduler.py`, `src/runtime/sse.py`, and
  `src/runtime/state.py`.
- Tests/docs: `tests/unit/test_phase4_event_contract.py`,
  `tests/unit/test_phase4_research_path.py`,
  `tests/unit/test_phase4_sse_recovery.py`,
  `codex/workstreams/PHASE4_CODEX_C_INTERNAL_OWNERSHIP.md`,
  `codex/workstreams/PHASE4_CODEX_C_EVENT_SUPPORT_MATRIX.md`, and this handoff.

## Implemented behavior

- **Snapshot:** `createRunRuntimeState` performs a second closed-world check on one B-decoded
  `phase4-run-projection/v1`: Run/Object/Goal/Scheme, planned and actual graph IDs, canonical
  record, graph/task membership and dependencies, path changes, lifecycle, terminal marker,
  projection revision, and event watermark. Tasks are never fabricated from Scheme or events.
- **SSE:** exact `/research-runs/{runId}/events` fetch-stream transport, frozen contract headers,
  incremental UTF-8/SSE parsing, typed public-error decoding, exact same-Run admission, and
  terminal-at-cursor zero-frame closure. A valid REFRESH event closes its stream immediately so
  no later frame can advance beyond the pending atomic snapshot boundary.
- **Events:** complete frozen inventory of 55 raw names: 47 supported and 8 fail-closed
  `UNSUPPORTED_BY_FRONTEND`. Decoder, identity checks, effects, and safe rendering are recorded
  in `PHASE4_CODEX_C_EVENT_SUPPORT_MATRIX.md`.
- **Sequence/cursor:** only the exact next sequence applies. Canonically identical replay is a
  no-op; conflicting duplicate IDs/sequences, unseen old frames, gaps, post-terminal frames,
  malformed/unsupported frames, and wrong Run/Task/graph identities advance neither projection
  nor cursor. Numeric cursors are canonical signed-64-bit strings; opaque cursors must bind an
  accepted event on the same Run.
- **Recovery:** typed invalid/ahead cursor handling, bounded deterministic reconnect backoff,
  stream-generation quarantine, stale-but-visible prior projection, and full same-Run snapshot
  reconciliation. Replacement is validated and swapped atomically; revision, watermark, graph,
  terminal, and all nested identities may not regress or cross Runs.
- **Research Path:** renders only authoritative actual-graph Tasks/dependencies with total frozen
  lifecycle mappings. Task detail uses safe public fields and derives terminal presentation from
  status mapping.
- **Self-Correction:** projects `task.self_correcting` on the same Task and same graph; durable
  correction detail arrives through the authoritative replacement snapshot. It never mutates
  topology.
- **Replan:** pending/rejected decisions do not mutate topology. Only Lead-approved replan events
  plus a validated replacement snapshot can advance graph version and expose added Tasks/edges.
  Direct specialist graph mutation is absent.
- **Terminal:** terminal events stop the stream and require a same-Run authoritative terminal
  replacement snapshot. Disconnect/backoff never changes Run business status; invalid
  post-terminal events are quarantined.
- **Safety:** payloads are closed allowlists; event receipts/errors retain only bounded IDs,
  enums, codes, and opaque SHA-256 fingerprints. Provider payloads, credentials, exception text,
  prompts, hidden reasoning, financial values, and unsafe result locators are not exposed.

## Verification

- C-owned Python acceptance: `51 passed`.
- Browser runtime acceptance under exact Node `24.18.0`: `117/117` checks.
- Full Python unit suite: `405 passed` (final rerun recorded in the task output).
- Integration suite: `38 passed, 1 Parent-owned legacy fixture failed` because it emits
  `task.started` without frozen `attempt: 1`.
- PostgreSQL schema-contract tests: `5 passed`.
- Full Python collection: `519 passed, 1 Parent-owned fixture failed, 11 skipped`; the sole
  failure is the same frozen `task.started.attempt` fixture mismatch above.
- Ruff lint/format, Python compileall, JSON schema load, and `git diff --check`: pass.
- Isolated strict TypeScript C surface: pass when supplied the two declared B seam types below.
  The real C+B compile remains dependent on B adding those declarations.
- Full production build: not run because Parent-only frontend bootstrap/package/root-composition
  files are intentionally absent from this child branch.

## Parent semantic patch proposals (9)

### C-P01 — Preflight SSE before response headers

```text
SEMANTIC_PATCH_PROPOSAL
target_path: apps/api/routes.py
required_semantic_change: await prepare_completed_run_event_stream before constructing StreamingResponse
required_imports_or_types: prepare_completed_run_event_stream; CursorPreflightError; frozen public error mapper
required_behavior: map INVALID_CURSOR to 400 and CURSOR_AHEAD to 409 before headers; pass prepared.body and merge prepared.response_headers with Cache-Control; preserve terminal-at-cursor zero-frame headers
required_tests: malformed/ahead/foreign cursor envelopes; exact suffix; terminal-at-cursor headers and zero frames
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P02 — Compose exact-Run frontend controller

```text
SEMANTIC_PATCH_PROPOSAL
target_path: apps/web/src/App.tsx
required_semantic_change: compose B snapshot/data source with C reducer and SSERuntimeTransport for the selected exact Run
required_imports_or_types: B FrontendDataSource and RunProjection; C transport/reducer APIs
required_behavior: snapshot N before SSE N+1; synchronously retain REFRESH as pending, fetch/reconcile one same-Run snapshot, then resubscribe; cancel old subscription on Run switch/unmount; no demo fallback
required_tests: exact Run switch, reconnect, refresh, terminal, and stale callback integration
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P03 — Bind the Run workspace to the authoritative projection

```text
SEMANTIC_PATCH_PROPOSAL
target_path: apps/web/src/pages/ResearchRunPage.tsx
required_semantic_change: consume selected C runtime projection/connection and render the C ResearchPath and TaskDetailDrawer contract
required_imports_or_types: RunProjection; ConnectionState; selectRunProjection; ResearchPath; TaskDetailDrawer
required_behavior: render actual graph Tasks/path changes/terminal state only; expose stale/recovery/failed transport state without changing Run state; no Scheme-derived Task fallback and no Results/V17.1 UI
required_tests: snapshot, recovery, self-correction, replan, terminal, and empty authoritative path rendering
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P04 — Integrate Research Path styles

```text
SEMANTIC_PATCH_PROPOSAL
target_path: apps/web/src/styles/research-run.css
required_semantic_change: add scoped layout/state styles required by the C ResearchPath and TaskDetailDrawer markup
required_imports_or_types: none
required_behavior: distinguish active/correcting/blocked/terminal and stale/recovery states accessibly without encoding business truth in CSS
required_tests: production build plus focused visual/keyboard smoke check at desktop and narrow widths
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P05 — Atomic/idempotent terminal finalization

```text
SEMANTIC_PATCH_PROPOSAL
target_path: src/application/service.py
required_semantic_change: route release, failure, and cancellation through one A-owned durable terminal finalizer
required_imports_or_types: RunProjection/event watermark persistence; RuntimeEventType.RUN_COMPLETED and RUN_FAILED; frozen availability/error types
required_behavior: atomically and idempotently publish terminal Run state, projection revision/watermark, availability, and exactly one terminal event; never emit terminal before durable state; emit safe run.failed for post-scheduler failures
required_tests: success/failure/cancellation, crash boundaries, retry/idempotency, restart, terminal snapshot/event closure
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P06 — Signed-64-bit event row

```text
SEMANTIC_PATCH_PROPOSAL
target_path: src/application/persistence.py
required_semantic_change: change RuntimeEventRow.sequence from SQL Integer to BigInteger
required_imports_or_types: sqlalchemy.BigInteger
required_behavior: persist the complete frozen signed-64-bit sequence/cursor range
required_tests: metadata type assertion and PostgreSQL boundary migration test
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P07 — Signed-64-bit event counter

```text
SEMANTIC_PATCH_PROPOSAL
target_path: src/infrastructure/database/models.py
required_semantic_change: change RuntimeEventCounterRow.last_sequence from SQL Integer to BigInteger
required_imports_or_types: sqlalchemy.BigInteger
required_behavior: allocate the complete frozen signed-64-bit sequence range consistently with RuntimeEventRow and the C trigger bigint local
required_tests: metadata type assertion and allocator boundary test
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P08 — Append-only sequence-width migration

```text
SEMANTIC_PATCH_PROPOSAL
target_path: alembic/versions
required_semantic_change: Parent allocates a new append-only revision widening runtime_events.sequence and runtime_event_counters.last_sequence to BIGINT and reinstalls the C allocator function/trigger
required_imports_or_types: Parent-assigned revision/down_revision; install_postgresql_runtime_event_sequence semantics
required_behavior: online-safe upgrade preserves values, constraints, uniqueness, foreign keys, and per-Run next sequence; no existing revision rewrite
required_tests: upgrade from current head with populated rows, allocator continuation, downgrade policy decision, schema inspection
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

### C-P09 — Repair and extend the shared runtime integration fixture

```text
SEMANTIC_PATCH_PROPOSAL
target_path: tests/integration/test_runtime_execution.py
required_semantic_change: make legacy public-event fixtures satisfy frozen payloads and cover prepared route behavior
required_imports_or_types: frozen RuntimeEvent payload rules and API client fixture
required_behavior: run.started carries graph version, task.started carries attempt: 1; cursor errors are pre-header envelopes and terminal cursor returns required headers with zero frames
required_tests: existing replay/heartbeat case plus invalid/ahead cursor and terminal-at-cursor route cases
source_child: C
source_commit: ad6a12043b7f5192bd2a8f89ce76448d4bcd4f86
```

## Cross-child dependencies and blockers

- **Backend A:** publish a complete `phase4-run-projection/v1` for the same Run with exact
  identity closure, authoritative planned/actual graphs and Tasks, path changes, monotonically
  paired projection revision/event watermark, and atomic terminal availability. Compose C's
  durable event/checkpoint stores with A's durable transaction boundary.
- **Frontend B:** add `NormalizedRuntimeEventV1` and the total `ConnectionState` union to
  `apps/web/src/types/domain.ts` (B already provides `ErrorEnvelope`, `RunProjection`, and total
  status maps); return the exact decoded Run projection from the production data source without
  demo fallback.
- **Migration:** `YES`. Current Parent-owned PostgreSQL event/counter columns are 32-bit while the
  frozen schema/cursor accepts `1..9223372036854775807`. C changed only its trigger local to
  `bigint`; C-P06 through C-P08 must be applied by Parent.
- **Authority conflicts:** none. Missing B declarations, terminal transaction composition, route
  wiring, and database width are integration gaps, not competing frozen-contract definitions.
- **Known blockers to VS01:** C-P01/C-P05, B's two seam declarations and snapshot adapter, A's
  authoritative atomic snapshot/finalizer, the Parent migration decision, and the repaired shared
  fixture. Codex C does not claim VS01.

No new Research Run was created. No Results A/B/C, V17.1 Collaboration, Qiji, or Phase 5 behavior
was implemented.
