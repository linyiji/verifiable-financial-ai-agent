# V17 Frontend Interaction Impact Matrix

Status: `PREPARATION_CLASSIFICATION_COMPLETE`

## Governing rules

- Interaction IDs are append-only and never renumbered or reused.
- `015` remains the retired `candidate-next` tombstone.
- `001..014` and `016..070` are the 69 active V8.1 interactions.
- `P4-E2E-001..106` retain their current meanings; `P4-E2E-015` remains a tombstone.
- A logical interaction is counted by handler-equivalent user intent, not DOM node count.
- Repeated A/B/C or Trace navigation renderings remain their existing interaction contract when they
  invoke the same route/tab/context behavior.
- Production and Presenter-enabled inventories are classified separately; Demo evidence cannot
  satisfy a real-backend gate.

`CHANGED` below means the logical intent remains but its data source, backend effect, state model,
accessibility contract, identity handling, or recovery behavior changes. It does not authorize the
change before the backend freeze.

## Complete V8.1 union disposition

The ranges are disjoint and cover every historical ID `001..070` exactly once.

| Interaction IDs | V17 disposition | Reason | Governing gates |
|---|---|---|---|
| `001` | `UNCHANGED` | New Task navigation intent/URL remains | E2E 001 |
| `002..003` | `CHANGED` | Runs/Objects navigation now loads authoritative collections with real states | E2E 002–003, 065–067 |
| `004` | `UNCHANGED` | New-run CTA still opens Object-first flow without mutation | E2E 004 |
| `005..007` | `CHANGED` | Run cards bind real collection/detail/result/action projections | E2E 005–007, 070–076 |
| `008` | `UNCHANGED` | Create modal opening remains local presentation with no POST | E2E 008 |
| `009` | `CHANGED` | Existing Object selection uses authoritative exact Object identity | E2E 009, ID 001–002 |
| `010..011` | `UNCHANGED` | Backdrop/X close and focus restoration remain | E2E 010–011 |
| `012..013` | `CHANGED` | Company search and candidate identity become real HTTP contracts | E2E 012–013, 067 |
| `014` | `UNCHANGED` | Cancel still performs no mutation | E2E 014 |
| `015` | `REMOVED` — retained tombstone | Historical obsolete candidate-detail transition; never reused | E2E 015 tombstone |
| `016` | `CHANGED` | Create confirm becomes real idempotent Object creation | E2E 016, 067 |
| `017..022` | `UNCHANGED` | Goal templates/text and wizard-back local semantics remain | E2E 017–022 |
| `023..025` | `CHANGED` | Next/prepare/regenerate/start use honest draft and durable exactly-once backend semantics | E2E 023–025, 074–075 |
| `026..036` | `CHANGED` | Run stages, research steps, plan/actual path, mutations and Tasks use one authoritative projection | E2E 026–036, 076–091; SSE/ID |
| `037..039` | `UNCHANGED` | Task drawer close/footer/Escape and focus contract remain | E2E 037–039 |
| `040..043` | `CHANGED` | Review modes, filters, Claim/Task links become backend-owned review/check relations | E2E 040–043, 092–095 |
| `044` | `UNCHANGED` | Back to exact Run/history transition remains | E2E 044 |
| `045..054` | `CHANGED` | Artifact A/B/C tabs, Claim, review/task/evidence/calculation/execution navigation bind real canonical IDs and availability | E2E 045–054, 072, 092–096 |
| `055..056` | `UNCHANGED` | Claim close restoration and Object create CTA intent remain | E2E 055–056 |
| `057..063` | `CHANGED` | Object cards/core, research entry, tab content, latest/history/comparison boundary, URL rebuild use authoritative identities; Phase 5 portions stay unavailable | E2E 057–063, 070–076, 097–098 |
| `064` | `UNCHANGED` | Breadcrumb/context semantics remain | E2E 064 |
| `065..067` | `CHANGED` | Clear search, Full mode and Incremental availability read real search/release authority | E2E 101–103 |
| `068` | `UNCHANGED` | Incremental path Task contract remains Phase 5 activated; only real Task is interactive | E2E 104 |
| `069` | `CHANGED` | Retry now repeats exact authoritative read and retains route/entity identity | E2E 105 |
| `070` | `UNCHANGED` | Dismiss remains presentation-only, no domain mutation | E2E 106 |

Totals for active V8.1 interactions:

```text
UNCHANGED = 21
CHANGED = 48
ADDED = 0
REMOVED_CURRENT = 0
ACTIVE_CLASSIFIED = 69/69 = 100%
HISTORICAL_TOMBSTONES = 1
V8_1_HISTORICAL_UNION_CLASSIFIED = 70/70 = 100%
```

## V17 additions and monotonic reservations

Inspection of the V17 scaffold confirms the Execution actor buttons and free-text search are separate
handlers/intents. The Presenter selector and three navigation/reset actions are also separate.

| ID | Disposition | Logical contract | Expected behavior | Accessibility/negative behavior | P4 gate | Activation |
|---|---|---|---|---|---|---|
| `071` | `ADDED` | Execution actor-type filter | Filters only already-authorized C rows from the same Object/Run/canonical record; no fetch/domain mutation unless the frozen pagination contract explicitly requires a query | One named selection group; selected state programmatic; keyboard usable; empty result announced; changing filter retains route and search | `P4-E2E-107` | `PHASE4_CORE_REQUIRED` |
| `072` | `ADDED` | Execution free-text search | Searches only safe normalized C fields; never serializes/searches raw hidden input/output; no identity or canonical-state change | Label/description, clearable text, live result count, empty state, focus retained; unsupported server query fails safely | `P4-E2E-108` | `PHASE4_CORE_REQUIRED` |
| `073` | `ADDED` | Presenter Scene selector | Chooses a Demo Scene only; cannot alter production stores/routes/backend records | Named select; valid option only; Demo watermark visible | `P4-E2E-109` | `DEPLOYMENT_ACTIVATED` only when `VITE_ENABLE_PRESENTER=true`; Demo-only result |
| `074` | `ADDED` | Presenter reset | Resets isolated Demo presentation step only | Named button; deterministic start; no production request/mutation | `P4-E2E-110` | Same Demo-only activation |
| `075` | `ADDED` | Presenter previous | Moves one Demo step back; boundary disabled/no-op | Named button; disabled reason/state at first step | `P4-E2E-111` | Same Demo-only activation |
| `076` | `ADDED` | Presenter next | Moves one Demo step forward; boundary disabled/no-op | Named button; disabled reason/state at final step | `P4-E2E-112` | Same Demo-only activation |

`P4-E2E-109..112` use `source_class=DEMO` and `result_class=DEMO_UX_ONLY`. They never enter
`PHASE4_CORE_E2E_RESULT` and cannot prove real Scenes 01–06. The production default for Presenter is
`false`.

No separate IDs are allocated for `TraceChain` A/B/C buttons or repeated Claim/Review/Execution links
when they are handler-equivalent renderings of `047..054`. If implementation introduces a different
effect, route, state transition, or user intent, the Change Request must be amended and the next ID
above `076` allocated before candidate freeze.

## Projected candidate completeness

| Inventory | Exposed rows | Classified | Completeness |
|---|---:|---:|---:|
| Production default (`VITE_ENABLE_PRESENTER=false`) | 71 | 71 | 100% |
| Presenter-enabled Demo | 75 | 75 | 100% |
| All-mode historical union, including tombstone `015` | 76 | 76 | 100% |

Composition:

```text
existing active = 69
new Phase 4 product controls = 2
new Demo-only Presenter controls = 4
retired tombstone = 1
```

These are preparation-time expected inventories. Candidate freeze must repeat a rendered control
inventory at every governed responsive mode. Any unclassified or newly exposed logical control fails
the Candidate gate; it is not silently folded into a range.

## Scene and phase impact

- Interactions feeding Scenes 01–04 are affected and require real `PHASE4_CORE_REQUIRED` evidence.
- `067`, `068`, `P4-E2E-103`, and `P4-E2E-104` retain `PHASE5_ACTIVATED` real behavior. Their Phase 4
  disabled/unavailable and Demo states remain testable but do not claim Incremental integration.
- Presenter IDs `073..076` are Demo-only and deployment-activated by the explicit build flag.
- Deployment gates keep their existing activation; no Presenter result is mixed into them merely
  because the vocabulary value is `DEPLOYMENT_ACTIVATED`.

## Candidate audit requirements

The frozen Candidate must provide a machine-readable inventory tying every rendered logical control
to ID, disposition, page/component, route/backend effect, accessible name/role/value, focus/history
behavior, responsive rendering, Scene, activation, and stable test ID. The independent auditor must
compare baseline and Candidate inventories and verify both 100% equations above.
