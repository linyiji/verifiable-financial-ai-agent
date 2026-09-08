# Workstream Report — WS-M Evidence Ownership & Runtime Event Semantics

## Scope

Implemented run-global Evidence identity with task-local produced/reference semantics on top of the
existing FMP → ingestion → validation pipeline.

- split live acquisition into `COMPANY`, `PEER`, and `RESEARCH_NEWS` scopes
- assigned every ingested FMP record a producer task, source endpoint, evidence purpose, and
  evidence category
- retained the combined `LiveFMPEvidenceCollector.collect` entry point for Phase regressions
- made evidence ingestion idempotent for the same deterministic Evidence ID
- separated the run-global Evidence store from task input/output Evidence references
- added coordinator-facing acquisition routing and unsequenced runtime event intents
- classified acquisition as `COMPLETED`, `PARTIAL`, `ENTITLEMENT_BLOCKED`, or `FAILED`
- ensured research/news acquisition cannot own revenue or EBITDA evidence
- ensured an entitlement-blocked News task produces neither accepted Evidence nor success events
- made producer → Evidence → task-consumer lineage reconstructable

No frozen domain model, enum, contract schema, Settings, project baseline, API entry point, runtime
execution module, or parallel status file was changed.

## Files

- `src/application/evidence_collection.py`
- `src/application/evidence_routing.py`
- `src/data/ingestion.py`
- `tests/unit/application/test_evidence_semantics.py`
- `tests/integration/test_evidence_semantics_persistence.py`
- `WORKSTREAM_REPORT_EVIDENCE_SEMANTICS.md`

The existing `src/data/persistence.py` already persisted every frozen Evidence ownership field, so
no implementation change was required there; WS-M adds an explicit SQL round-trip regression test.

## Interfaces

- `LiveFMPEvidenceCollector.collect_scope(...) -> EvidenceTaskAcquisitionResult`
- `FixtureEvidenceCollector.collect_scope(...) -> EvidenceTaskAcquisitionResult`
- `evidence_request_plans(..., scope=...) -> tuple[EvidenceRequestPlan, ...]`
- `EvidenceIngestionService.ingest(..., provenance=EvidenceProvenance(...))`
- `EvidenceIngestionResult.created_records`
- `RunEvidenceStore.register_acquisition(...) -> TaskEvidenceRoutingResult`
- `RunEvidenceStore.link_inputs(task_id, evidence_ids)`
- `RunEvidenceStore.select_ids(categories=..., purposes=...)`
- `RunEvidenceStore.lineage(evidence_id) -> EvidenceLineage`
- `EvidenceTaskRouter.route(task, ...) -> TaskEvidenceRoutingResult`
- `TaskEvidenceRoutingResult.apply_to(task)`

`EvidenceEventIntent` deliberately has no sequence number. The coordinator converts each intent to
a `RuntimeEvent` and assigns the authoritative global event sequence. Only newly created,
accepted, not-previously-announced Evidence produces an intent.

## Acquisition Ownership and Outcomes

| Scope | Producer task | Endpoints | Expected outcome in WS-M fixture |
|---|---|---|---|
| Company | `RUN:evidence` | profile, income, balance, cash flow, quote, historical, analyst | `PARTIAL` because stale secondary statement periods are retained as non-accepted audit records |
| Peer | `RUN:peers` | peers | `COMPLETED` |
| Research / News | `RUN:research-news` | news, transcript | `ENTITLEMENT_BLOCKED` for HTTP 402; no fabricated records |

The deterministic endpoint fixture preserves the accepted live semantic total:

- Company-owned accepted Evidence: **40**
- Peer-owned accepted Evidence: **9**
- News/Transcript accepted Evidence: **0**
- Run-global accepted Evidence: **49**
- Unique `evidence.accepted` event intents: **49**

The News task only receives company profile, market, and analyst context as input references. It
does not receive or produce revenue/EBITDA Evidence and never reports a successful acquisition
when both owned endpoints are entitlement-blocked.

## Coordinator Wiring Notes

1. Construct one `RunEvidenceStore` per run and one `EvidenceTaskRouter` with the scoped collector.
2. Before executing a planned task, call `router.route(task, symbol, object_id, as_of)`.
3. Call `routing_result.apply_to(task)` or persist the returned input/output IDs and acquisition
   status through the coordinator's task repository.
4. Convert each returned `EvidenceEventIntent` into exactly one sequenced `RuntimeEvent`; consumer
   references return no Evidence events.
5. Map `ENTITLEMENT_BLOCKED` to an explicit blocked/partial runtime path. It must not be converted
   to a successful News result.
6. Continue passing only accepted `EvidenceRecord` objects to financial and agent code. Provider
   envelopes and raw snapshots stop at the Adapter/Data boundary.

This workstream intentionally does not edit `src/application/execution.py`; WS-N owns that
integration point.

## Tests

PASS:

- scoped endpoint/category ownership and News exclusion of revenue/EBITDA
- 49 accepted run-global Evidence records with 40 Company + 9 Peer ownership
- 49 unique accepted event IDs, with zero duplicate creation or rebroadcast on repeat acquisition
- `PARTIAL`, `COMPLETED`, and `ENTITLEMENT_BLOCKED` classification
- blocked News has no output Evidence and no accepted event intent
- task input/output reference separation and `Task` field application
- producer/source/purpose/category and consumer-reference lineage reconstruction
- SQL round-trip for producer task, endpoint, purpose, category, observed time, and provider time
- original fixture, live FMP, Phase-1, Phase-2, runtime, financial, output, and assurance regressions

Module gate results:

- PASS — WS-M focused tests: **4 passed**
- PASS — full suite: **128 passed, 1 skipped, 2 dependency warnings**
- PASS — Ruff across `src` and `tests`
- PASS — `git diff --check`
- PASS — ownership/forbidden-path diff scan
- PASS — secret-pattern scan of changed source and tests
- PASS — raw-provider boundary inspection

The skipped test requires `TEST_POSTGRESQL_URL` plus `asyncpg`; SQLite validates the SQL mapping in
this module gate. The warnings originate from installed FastAPI/Starlette test-client dependencies.

## Known Gaps

- WS-N still needs to persist the returned task reference fields and convert event intents to the
  coordinator's globally sequenced `RuntimeEvent` stream.
- A process restart can rehydrate Evidence from the repository, but durable task-reference and
  event-announcement indexes remain coordinator/runtime repository responsibilities.
- News and transcript remain unavailable under the tested FMP entitlement. WS-M preserves the
  explicit blocked outcome and does not synthesize substitutes.
- Real PostgreSQL execution is environment-gated; the existing migration/schema contract remains
  unchanged and the metadata round-trip is covered with SQLAlchemy on SQLite.

## Contract Deviations

None. No `CONTRACT_CHANGE_REQUEST` is required.

## Integration Notes

- `LiveFMPEvidenceCollector.collect` remains backward-compatible and still probes all ten Phase-2
  endpoints for existing composition paths.
- `EvidenceIngestionResult.created_records` distinguishes persisted creation from deterministic-ID
  reuse; event generation must use this field, not all accepted records.
- Existing stale/conflict/rejected records remain in the global audit repository but are never
  selected as task inputs and never create `evidence.accepted` intents.
- External provider-calculated fields remain reference-only under their existing
  `provider_reference_*` names.
