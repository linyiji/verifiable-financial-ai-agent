# Phase 5B — exact incremental research

This is an additive planning and memory slice. It uses the existing independent
Run admission, task execution, review, proof, report and release machinery.
No historical Run or version is rewritten. No inferred latest/ticker/title base.

## Explicit base and bounded planning

`POST /api/research-runs/prepare` optionally accepts paired `base_run_id` and
`base_research_view_version` (the immutable RVV identity). The repository resolves
that exact Object/Released Run/view tuple. Missing, foreign or nonreleased sources
fail closed. The new as-of cannot precede the base as-of.

The server builds at most 32 public decisions from that view. No historical events,
raw evidence/provider bodies, private prompts or hidden reasoning are included.
The MVP policy uses:

- REUSE: only an explicitly eligible contextual source, never automatic whole-view reuse.
- REFRESH: retained verified metrics require fresh current-Run acquisition.
- REVALIDATE: retained verified claims require new calculations/review/proof.
- PREVENT: retained period-mismatch corrections require period-consistency checks.
- UNKNOWN: a correction with no supported preventive rule is not reused.

Each decision has an exact R1 source identity and versioned policy authority.
The AI proposes the new research method and an applicability/work explanation for
every decision. It may choose REFRESH/REVALIDATE/UNKNOWN for metrics or claims,
PREVENT/UNKNOWN for supported issues, and REUSE/UNKNOWN for eligible context.
It cannot change source identities or historical statements, or upgrade an original
UNKNOWN. Missing/invalid AI planning does not silently become deterministic
incremental acceptance. The production composition explicitly injects AI scheme
and task planners only for incremental requests; ordinary admission is unchanged.

The context is part of the Scheme snapshot, covered by the existing immutable draft
hash and confirmation. Client preferences are not enriched or repurposed.

The retained NVDA v1 has one metric, one claim and one PERIOD_MISMATCH issue.
Its local validated preview has zero REUSE, one REFRESH, one REVALIDATE and one
PREVENT. Summary is bounded historical background, not a fabricated reuse item.
Empty categories and zero total decisions are valid when memory is absent/sparse.
Structured model output uses closed typed decision records, not an open dictionary.

## Independent execution

Confirmation creates a new UUID Run and new graph/tasks/events using the existing
atomic admission transaction. `ResearchRun.base_run_id` and
`ResearchRun.base_research_view_version` persist in the aggregate through ordinary
runtime saves. Confirm replay returns the same admission. The confirmed Scheme
preserves the bounded context. Initial tasks cannot inherit historical evidence,
outputs or results; their goals retain fresh-acquisition/revalidation/prevention
constraints. Existing review/proof/release requirements are unchanged.

## Memory v2 and comparison

After independent release, the existing explicit materialization endpoint uses the
persisted R2 base relation as advancement authority. Under the Object row lock it
checks the expected current Run/view, release status, Object ownership and consecutive
versions. ObjectVersion, ViewVersion and pointer are committed together. Injected
failures after any stage leave v1 current. Database immutable-version triggers remain.

The returned memory includes the exact base snapshot, confirmed incremental context
and governed comparison rows. Metric keys use category, formula, capability, period,
period basis, actuality, unit and currency; claim keys additionally use claim type.
Duplicate/unknown keys are never guessed. Equal verified metric values are UNCHANGED;
independently validated equal claims are REVALIDATED; unequal values are UPDATED.
Unmatched items are NEW or REMOVED_FROM_CURRENT_VIEW. Resolved issues have no generic
cross-Run logical equivalence and remain exact unmatched references, even if wording
is similar. REMOVED means absent from the current view, never historical deletion.

New optional serialized fields are omitted when absent to preserve frozen historical
wire payloads and draft hash compatibility. Strict frontend decoders validate the
Object/base/view/decision/change identities and safe public boundary. Current and
historical source buttons retain exact Run and report-anchor navigation.

## Verification and quota

Tests cover policy, exact identities, draft hashing, source quarantine, AI prompt
binding, independent task creation, real isolated PostgreSQL prepare/confirm replay,
atomic v2 concurrency/rollback, immutable v1 and formula-key comparison.
`scripts/accept_incremental_research.mjs` records preflight, one guarded live workflow
and final browser acceptance. `scripts/phase5b_history_guard.py` fingerprints R1/v1
and inventories Run IDs without exporting raw historical bodies.

The Phase5B allowance is one new provider Research Run. A first startup wiring error
occurred before provider invocation or Run creation; its narrow composition repair
and reacceptance are recorded separately. A failed actual R2 must stop the slice,
leave v1 current and never automatically cause a replacement Run.
