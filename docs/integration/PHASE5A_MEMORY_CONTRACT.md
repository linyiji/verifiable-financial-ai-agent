# Phase 5A memory contract (v1)

[简体中文](PHASE5A_MEMORY_CONTRACT.zh-CN.md)

Parent-frozen after read-only persistence, lineage and V17 audits.

The exact accepted source is RUN-57aed683-75d6-4b47-acc6-a73053ea492e,
authoritatively owned by OBJ-NVDA. Reuse operational Phase 4 released-result
and A/B/C validators, not the unused release-validation-row requirement.
Never rewrite historical aggregates, reports, outputs or proof records.

Add immutable ResearchObjectVersion and ResearchViewVersion records and one
explicit pointer row per Object. Positive integer versions identify append-only
assets; stable version IDs are derived from exact Object/Run identity. Source
Run/result/report/canonical identity is retained. A view references one exact
object version. Compact memory items reference authoritative metric/claim or
resolved correction, never copy a full aggregate or private execution payload.

Only independently VERIFIED metrics and their exact supported claims enter the
verified categories. Released-but-not-proof-verified is not VERIFIED. Missing
peer/path/reusable categories are NOT_OBSERVED, not generated to fill space.

Materialization is explicit POST /api/objects/{object_id}/memory/materialize,
with closed body {source_run_id}; GET /api/objects/{object_id}/memory reads the
durable pointer. This extends the existing Object API family. Same Object/Run
is durably unique and returns the original versions. First exact source binds
the pointer. A different source while bound is CONFLICT, with no mutation.
No cross-Run ordering authority exists: future explicit advancement is deferred,
not inferred from dates, strings, ticker or arrays. No new research execution.

Lock exact Object; validate source; create ObjectVersion + ViewVersion + pointer
in one transaction. Enforce append-only versions in PostgreSQL; rollback any
partial write. Use database reads, not application object/run identity caches.
The new memory pointer supersedes timestamp-derived latest summaries in real
Object API reads. Pure frozen Phase 4 summary helpers remain unchanged.

Preserve V17 Object header, overview/history tabs and Start New Research. Add
Current Research View and Research Memory under overview; source links go to
exact Results/authoritative report anchor. Existing incompatible historical rows
remain visible. No incremental/reuse execution, compare, plan-from-memory or
prototype facts. Source metadata and availability must remain explicit.

Serial gates: models/tests → migration/repository/tests → source service/tests
→ API/tests → frontend/build → real browser/reopen/idempotency → regression/freeze.

## Accepted implementation and operations

Migration: `20260907_0009` after `20260905_0008`, applied through the repository
PostgreSQL migration helper. No backfill is performed by migration or a GET.
POST the exact source selection explicitly; an already-bound different source
returns safe CONFLICT. Same-source retries return the original persisted asset,
including created_at and IDs. No provider/model call is involved.

Object memory GET includes compact Released history references. Incompatible
history remains visible with unavailable result identity. The existing Object
history list continues to show failed/cancelled and incompatible rows too.
No selection derives from that list's display order.

Accepted slice retains one proof-verified revenue metric, its matching claim,
and one resolved period-mismatch issue. Peer/path/reusable context is explicitly
not retained in v1. Sources remain accessible through the original exact Results.

Maintained focused tests: `test_memory_contracts.py`, `test_memory_source.py`,
`test_memory_api.py`, `test_memory_postgresql.py` (TEST_POSTGRESQL_URL, isolated
temporary schemas), and `apps/web/scripts/research-memory.test.mjs`.
Real retained acceptance: `node scripts/accept_research_memory.mjs`, with API
8010, web 4173 and dedicated Chrome debugging 9227. The accepted Run must first
be explicitly materialized. This script retries materialization but never starts
research or creates a provider Run.
