# Phase 4 E2E Gate Activation Matrix

Status: **AUTHORITATIVE — FROZEN — DESIGN ONLY**  
Companion gate semantics: `PHASE4_E2E_ACCEPTANCE_SPEC.md`  
Specification date: 2026-09-04 (Asia/Shanghai)

## 1. Purpose and invariants

This matrix removes the circular dependency between Phase 4A core integration, Phase 5 Object
Memory, and later deployment release profiles. It changes only when an already-defined acceptance
contract becomes release-blocking.

- `P4-E2E-001..100` remain stable. No gate is deleted, renumbered, or weakened.
- A gate's `activation_scope` is its earliest release-blocking owner, not the only phase in which it
  may be executed. Later candidates rerun applicable earlier gates as a regression baseline.
- Frontend-only Demo scenarios remain UX-contract evidence and never satisfy a real-backend gate.
- A future gate that is not activated is `DEFINED_NOT_ACTIVATED`; it is not `FAIL`, `BLOCKED`,
  `SKIPPED`, or a waiver.
- Once its activation condition is true, a gate is `REQUIRED` and its final result may only be
  `PASS` or `FAIL`.

The following namespaces and semantics are frozen:

- `P4-E2E-001..100`;
- `SCENE-01..06`;
- `P4-SSE-001..020`;
- `P4-ID-001..028`;
- the `activation_scope` values, activation conditions, and result-state semantics in this matrix.

Phase 4A activates real-backend `SCENE-01..04` only. Real-backend `SCENE-05..06` activate in Phase
5. `P4-E2E-099..100` activate for the later deployment release scope. In every pre-activation
case, `DEFINED_NOT_ACTIVATED` is distinct from `FAIL`, `BLOCKED`, and `SKIPPED`.

## 2. Activation scopes

| `activation_scope` | Activation condition | Release-blocking aggregate |
|---|---|---|
| `PHASE4_CORE_REQUIRED` | Phase 4A integrated-product acceptance begins | `PHASE4_CORE_E2E_RESULT` |
| `PHASE5_ACTIVATED` | `PHASE5_OBJECT_MEMORY_IMPLEMENTED` | `PHASE5_EXTENSION_E2E_RESULT` |
| `DEPLOYMENT_ACTIVATED` | Phase 4B, RP2+, or Competition Release declares the applicable deployment profile | `DEPLOYMENT_E2E_RESULT` |

The activation state machine is:

```text
DEFINED_NOT_ACTIVATED --activation condition--> REQUIRED --execution--> PASS | FAIL
```

`DEFINED_NOT_ACTIVATED` has no pass/fail value and contributes neither success nor failure to an
earlier aggregate.

## 3. Exhaustive gate activation mapping

Ranges below are inclusive and exhaustively cover every stable ID from `P4-E2E-001` through
`P4-E2E-100`. The assertion text remains exactly the assertion text in the acceptance specification.

| Gate or gate variant | `activation_scope` | Boundary note |
|---|---|---|
| `P4-E2E-001..057` | `PHASE4_CORE_REQUIRED` | Core navigation, Object/Run workflow, runtime, review, reports, artifacts, and Claim Trace controls |
| `P4-E2E-058` — FULL variant | `PHASE4_CORE_REQUIRED` | Start full research for the same Object |
| `P4-E2E-058` — INCREMENTAL variant | `PHASE5_ACTIVATED` | Requires backend incremental mode and an authoritative prior-run seed |
| `P4-E2E-059` — Overview, Financials, object-scoped History, and backend release-derived current Research View | `PHASE4_CORE_REQUIRED` | Core preserves exact Object/current-Run context but must not synthesize or require a versioned Research View |
| `P4-E2E-059` — backend-versioned Research View variant | `PHASE5_ACTIVATED` | Requires `ResearchViewVersion`/equivalent authoritative version semantics |
| `P4-E2E-060..061` | `PHASE4_CORE_REQUIRED` | Latest released Run consistency and exact historical Run opening; no version model is implied |
| `P4-E2E-062` | `PHASE5_ACTIVATED` | Comparison Claim navigation requires authoritative `ComparisonDataset` semantics |
| `P4-E2E-063..096` | `PHASE4_CORE_REQUIRED` | Core browser navigation, source, identity, prepare/confirm, SSE, graph, correction, capability, finance, trace, A/B/C, and artifact gates |
| `P4-E2E-097` | `PHASE5_ACTIVATED` | Versioned Object writeback, immutable version history, and explicit comparison pair |
| `P4-E2E-098` | `PHASE4_CORE_REQUIRED` | Durable Object/Run/report/artifact reopening from backend persistence |
| `P4-E2E-099..100` | `DEPLOYMENT_ACTIVATED` | Deployment truth and Public/Limited/Offline policy; not a Phase 4A entry condition |

Mixed gates `P4-E2E-058` and `P4-E2E-059` retain one ID and one original semantic contract. Their
named variants make the backend dependency explicit; this is not a new gate or a renumbering.

## 4. Six stable Scene activations

| Scene | Frontend-only Demo | Real-backend `activation_scope` | Real-backend pre-activation state |
|---|---|---|---|
| `SCENE-01` Full Research | Current Demo UX acceptance | `PHASE4_CORE_REQUIRED` | n/a |
| `SCENE-02` Dynamic Path | Current Demo UX acceptance | `PHASE4_CORE_REQUIRED` | n/a |
| `SCENE-03` Self-Correction + Review | Current Demo UX acceptance | `PHASE4_CORE_REQUIRED` | n/a |
| `SCENE-04` Claim Trace | Current Demo UX acceptance | `PHASE4_CORE_REQUIRED` | n/a |
| `SCENE-05` Object Accumulation | Current Demo UX acceptance | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED` |
| `SCENE-06` Incremental Research | Current Demo UX acceptance | `PHASE5_ACTIVATED` | `DEFINED_NOT_ACTIVATED` |

The six Scene IDs and their acceptance semantics remain stable. Demo results are always reported
separately and never roll up into any real-backend result.

## 5. Phase 4 Core Object slice

Phase 4 Core requires an authoritative Research Object collection and these Object/Run relations:

- object-scoped Run history;
- exact historical Run opening by `runId`;
- authoritative `latest_released_run_id` used consistently by title, KPIs, current research display,
  Claim links, and the latest-research action;
- exact same-Run Claim and `ReportArtifact` links;
- `source_run_id` preservation wherever a core projection exposes a source Run;
- refresh, fresh-browser reopen, and backend-restart persistence of those identities.

This core slice is covered by the core variants of `P4-E2E-003`, `057`, `059`, `060`, `061`, `063`,
`070..073`, `076`, `094`, `096`, and `098`. It does **not** require
`ResearchObjectVersion`, `ResearchViewVersion`, `ComparisonDataset`, `IncrementalResearchSeed`, or
backend-driven `REUSE`/`REFRESH`/`REVALIDATE`/`PREVENT`. Those are Phase 5 extension contracts.

## 6. Result model and roll-up rules

Every real result record includes:

```json
{
  "gate_id": "P4-E2E-097",
  "variant": "object-history-writeback",
  "activation_scope": "PHASE5_ACTIVATED",
  "activation_state": "DEFINED_NOT_ACTIVATED | REQUIRED",
  "result": null
}
```

When `activation_state` is `DEFINED_NOT_ACTIVATED`, `result` must be `null`. When it is `REQUIRED`,
the final `result` must be `PASS` or `FAIL`.

| Aggregate | Before activation | PASS rule |
|---|---|---|
| `PHASE4_CORE_E2E_RESULT` | Required from Phase 4A start | Real `SCENE-01..04` and every `PHASE4_CORE_REQUIRED` gate/variant pass in one manifested candidate |
| `PHASE5_EXTENSION_E2E_RESULT` | `DEFINED_NOT_ACTIVATED` | After `PHASE5_OBJECT_MEMORY_IMPLEMENTED`, real `SCENE-05..06`, every Phase 5 gate/variant, and the applicable non-regressed core baseline pass |
| `DEPLOYMENT_E2E_RESULT` | `DEFINED_NOT_ACTIVATED` | For the declared Phase 4B/RP2+/Competition profile, `P4-E2E-099..100` and the applicable non-regressed core network/SSE/identity/artifact/persistence baseline pass |

`PHASE4_CORE_PRODUCT_ACCEPTED` becomes `YES` only when `PHASE4_CORE_E2E_RESULT == PASS`. It does not
depend on either future aggregate. Activation of a later aggregate does not change the historical
Phase 4 Core result.

## 7. Design declaration

No application, backend, frontend, Playwright, schema, route, or deployment implementation is
authorized or included by this activation delta.

The only expected future gate-design delta is triggered by approval of a new Frontend Baseline.
Newly added Frontend interaction contracts must receive new monotonically increasing
`P4-E2E` IDs above `P4-E2E-100`. Existing `P4-E2E-001..100` IDs, meanings, ordering, and activation
assignments must not be renumbered or repurposed during that reconciliation.

```text
PHASE4_E2E_SPEC_READY = YES
PHASE4_CORE_GATE_SET_DEFINED = YES
PHASE5_EXTENSION_GATES_DEFINED = YES
DEPLOYMENT_EXTENSION_GATES_DEFINED = YES
PHASE4_E2E_DESIGN = FROZEN
WAITING_FOR_APPROVED_BACKEND_AND_FRONTEND_CANDIDATES = TRUE
```
