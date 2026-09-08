# Phase 5B Run lineage decoder repair

[简体中文](PHASE5B_RUN_LINEAGE_DECODER_REPAIR.zh-CN.md)

Start: `phase4`, `a0ae8aadf6da1881fc27a90f7a4c7cf94dc549d9`, tree
`e2376d9dc79e9d0cfb43a6731ec324a3f2fb8874`; clean before edits.

## Contract audit

Root cause: `RUN_PROJECTION_FRONTEND_STRICT_DECODER_DRIFT`; first rejected
field `$.run.base_run_id`. The exact accepted backend delta is
`base_run_id`, `base_research_view_version`, `reexecution_of_run_id`.
`project_run_detail` emits these optional fields; the atomic projection
embeds that detail. Collection/history items have a separate explicit
shape and do not inherit these fields. Results use the atomic Run shape.
No backend production semantics or migration changed.

Both shared detail and embedded decoders now explicitly admit these fields,
preserving absence/null and existing opaque-ID validation. Knowledge-base
identities must be paired; self-lineage and a predecessor equal to the
knowledge base are rejected. Unknown fields still fail closed. The existing
re-execution component consumes the shared decoder and shows Scheme, base,
view and independent execution predecessor, without modifying its two-stage
authorization/admission workflow.

## Acceptance

- Frontend: 17 lineage tests, 6 existing re-execution interaction tests,
  119 M3/M4/M5/M6 regression checks: **142 passed**.
- Backend: reexecution, reexecution API, graph/runtime bindings, single-call
  graph, memory API and provider foundation suites: **61 passed**.
- Total focused checks: **203 passed**. Typecheck and production build passed.
- Initial backend test launch lacked `TEST_POSTGRESQL_URL`; rerun with the
  configured connection and disposable isolated schemas passed. No public
  production tables were used for fixture writes.
- Real Chrome acceptance used the product frontend and a temporary
  production-backed GET-only API, without scheduler or providers. Initial
  temporary server configuration lacked the persisted application repository;
  correcting the harness enabled historical Memory result reads.
- Exact failed R2 detail and atomic projection decoded; status FAILED,
  Scheme `SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6`, base
  `RUN-57aed683-75d6-4b47-acc6-a73053ea492e`, view
  `RVV-05bec42f-ab9b-55c5-b502-c439b8abe948`, predecessor absent.
- Screenshot inspected: failed history, exact lineage and enabled
  “重新执行” visible. Neither authorization nor admission action clicked.
- Legacy R1 detail/projection decoded with absent lineage. The existing
  normalized frontend status is COMPLETED for backend RELEASED. Memory
  confirms R1 RELEASED, current View v1 and latest version 1.
- Future re-execution is tested with local fixtures only.
- Browser recorded zero mutation requests. Migration remains 20260907_0011,
  already applied; authorizations remain 0; Runs remain 37. All 22 historical
  table fingerprints, failed R2, consumed Draft, Scheme and R1/v1 unchanged.
  Memory v2 absent. Provider/model calls and new production Runs: 0.

Local ignored evidence: `artifacts/phase5b_lineage_decoder/browser.json`,
`failed-r2.png`, GET-only harness and browser script; before/after snapshots
in `artifacts/phase5b_reexecution_authorization/`.

Next: `PHASE_5B_FAILED_R2_REEXECUTION_AUTHORIZATION_RESUME`.
This repair does not authorize or execute that next task.
