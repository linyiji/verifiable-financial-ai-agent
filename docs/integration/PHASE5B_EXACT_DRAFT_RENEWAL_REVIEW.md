# Phase 5B — exact draft lease renewal and review

[简体中文](PHASE5B_EXACT_DRAFT_RENEWAL_REVIEW.zh-CN.md)

Start: `2da5d15760f3d91e3defd1d281eea5799e2399b0` (phase4, clean).

## Contract audit and narrow repair

Existing renewal capability: NO. `expires_at` is part of the immutable public
Draft payload and its canonical hash. There was no separate draft authorization
record. Updating expires_at would invalidate the Owner-required hash. The supplied
`sha256:543ea7...` value is the complete Draft hash, not a separate Scheme-only hash.

The repair adds a separate append-only authorization table, not a replacement
Draft/Scheme. Every authorization binds the exact Draft hash, Scheme ID, Base Run,
Base View and predecessor expiry. It records its authorization time and bounded
new expiry. PostgreSQL rejects updates/deletes to audit rows. Renewal locks the
same Draft row used by confirmation, rejects consumption, corruption, identity
mismatch, a wrong predecessor, and an unexpired lease. An identical idempotency
replay returns the same authorization without extending time.

The immutable Draft payload, original expiry, version, prepare replay and hash
remain unchanged. Confirmation now validates the effective authorization expiry
loaded from durable storage, including exact binding checks, while retaining all
existing hash/version/identity/consumption gates. With no renewal, original expiry
semantics are unchanged. The 30-minute lease policy is unchanged.

Migration: `20260907_0010`, applied after isolated PostgreSQL tests passed.
No existing rows were rewritten by the migration.

## Actual authorization

- Draft: `DRAFT-036cd4bd-fb8b-4c05-a9ba-25c654588342`, version 1
- Scheme: `SCHEME-b7a81dfc-7863-59e2-afd2-0371e796a1b6`
- Draft hash: `sha256:543ea7eda59287104b3cb1c2c1ca2f19da256aaa60359a3b6fa39876ab7ebf21`
- Authorization: `LEASE-0e2bb5a10755b04f754bb905e1b5a8a004676c6fcbd1735ce1e92492f15a9bcf`
- Prior expiry: `2026-09-07T09:51:42.157929Z`
- Authorized at: `2026-09-07T10:09:17.555353Z`
- New effective expiry: `2026-09-07T10:39:17.555353Z` (18:39:17 Shanghai)
- Renewal replay key: `owner-exact-draft-lease-renewal-20260907-1`

The full database Draft equals the original capability artifact byte-for-byte in
canonical content before/after renewal. Decisions remain REUSE0 / REFRESH1 /
REVALIDATE1 / PREVENT1 / UNKNOWN0, with unchanged reasons and source identities.
Base remains OBJ-NVDA / RUN-57aed683-75d6-4b47-acc6-a73053ea492e /
RVV-05bec42f-ab9b-55c5-b502-c439b8abe948. No Goal or Scheme mutation.

## Real product review

`/drafts/{exact-draft-id}` reads the persisted Draft and separate authorization
through `GET /api/research-drafts/{draft_id}`. It shows the exact stored goal,
scope, requirements, decisions, historical sources and technical identities, with
explicit renewal-not-regeneration copy. No confirmation button or model call is
part of this read-only review page. Expiry display uses effective authorization,
not the immutable historical `draft.expires_at`.

The visible in-app browser and dedicated Chrome reviewed the actual PostgreSQL
response. Reload and close/reopen retained identical Draft content and effective
expiry. Browser requests performed zero mutations. The exact historical R1/View
and 0/1/1/1/0 counts were visible. Review-server middleware denies all writes;
it has no model adapters and never starts runtime workers.

Evidence: `artifacts/phase5b_exact_draft_renewal/browser-review.json` and
`exact-draft-review.png`. The lease audit itself is durable PostgreSQL evidence,
not only an artifact file. The earlier MiMo capability artifacts were hash-checked
unchanged. All 36 Run IDs and R1/v1 history fingerprints remain unchanged.

## Verification and next-task boundary

174 focused Python tests and 58 frontend checks pass; typecheck/build and lint
pass. Tests include real PostgreSQL renewal/replay/audit immutability, the actual
confirmation repository, original/renewed expiry rejection, hash/base/consumption
rejection, product API reads, and no model/graph/admission dependencies.

MODEL_CALLS = 0; SCHEME_GENERATION_CALLS = 0; GRAPH_PLANNER_CALLS = 0; R2_CREATED = NO.
No tasks, execution events, Agent outputs, Review, Proof, Report, Release or Memory
v2 are created by renewal. Latest remains exact R1 / View v1. No Phase 5B tag or push.

Next: PHASE_5B_CONFIRM_RENEWED_DRAFT_AND_EXECUTE_R2. Read the effective lease through
the exact review endpoint or durable Draft record; do not judge it solely from the
immutable Draft's old expiry. Recheck immediately before graph planning. Stop if
expired. No prepare or Scheme regeneration. The Owner allows at most one graph
model call; next-task execution must enforce that budget and fail closed on graph
failure (the generic planner's validation retries/deterministic fallback are not
authorization to exceed the Owner's narrower gate). No graph work occurred here.
