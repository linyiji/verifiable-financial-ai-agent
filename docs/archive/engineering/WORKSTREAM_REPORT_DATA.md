# Workstream Report — Data & Evidence

## Scope

Implemented WS-A's provider-to-evidence path under the frozen Python 3.11 baseline:

- provider-neutral request and provider protocol
- deterministic fixture provider
- FMP transport/provider adapter boundary
- configurable dataset freshness policies
- validation, canonical unit normalization, period/currency/value conflict detection
- accepted-evidence hard gate
- content-addressed local raw artifact storage
- in-memory and async SQLAlchemy evidence repositories
- deterministic, offline evidence and persistence tests

Raw provider payloads remain inside `src/data/**` and `src/adapters/fmp/**`. The public ingestion
result exposes domain `EvidenceRecord` values plus validation diagnostics; only records with
`EvidenceStatus.ACCEPTED` enter `AcceptedEvidenceBundle`.

## Files

- `src/data/provider.py` — provider request, quarantined snapshot, provider protocol
- `src/data/fixtures.py` — deterministic fixture replay
- `src/data/freshness.py` — per-dataset TTL policy
- `src/data/normalization.py` — fields, dates, periods, scaled currency, percent and bps
- `src/data/validation.py` — validation decisions and duplicate conflict handling
- `src/data/ingestion.py` — evidence gate and persistence coordination
- `src/data/artifacts.py` — content-addressed raw snapshot storage
- `src/data/repository.py` — evidence repository protocol and in-memory implementation
- `src/data/persistence.py` — async SQLAlchemy mapping/repository
- `src/adapters/fmp/provider.py` — HTTP transport and statement mapping boundary
- `tests/unit/data/**` — evidence-specific tests

No frozen `src/domain/**` file was modified.

## Interfaces

- `Provider.fetch(ProviderRequest) -> RawProviderSnapshot`
- `EvidenceIngestionService.ingest(...) -> EvidenceIngestionResult`
- `RawArtifactStore.put_raw_snapshot(...) -> str`
- `EvidenceRepository.add/get/list/list_by_run`
- `FMPTransport.get_json(path, params) -> Any`

Downstream integration should consume `EvidenceIngestionResult.accepted`, not provider snapshots or
the raw-record diagnostics. Formal financial capabilities must use accepted evidence IDs from that
bundle.

## Tests

Environment:

- Python: `<repository-root>/.venv/bin/python` (`3.11.16`)
- Import resolution: `PYTHONPATH=.` so this isolated checkout is tested

Results:

- PASS — `python -m pytest -q`: **19 passed in 0.22s**
- PASS — WS-A tests: **13 passed in 0.22s** (included in the 19-test full suite)
- PASS — `python -m ruff check .`: **All checks passed**
- PASS — `python -m compileall -q src/data src/adapters/fmp`
- PASS — changed-path audit: no changes outside WS-A ownership and this report
- PASS — import-boundary audit: no production package outside `src/data/**` and
  `src/adapters/fmp/**` imports `RawProviderSnapshot`, the FMP adapter, or provider internals
- FAIL — none
- SKIP — live FMP call (requires an external credential and network; deterministic transport test
  covers the adapter contract)

## Existing Logic Reuse Matrix

| Existing Module | Decision | Reuse Method | Compatibility | Action |
|---|---|---|---|---|
| `src/domain/evidence.py` | `DIRECT_REUSE` | direct domain output | Python 3.11 PASS | keep frozen |
| `src/domain/enums.py::EvidenceStatus` | `DIRECT_REUSE` | direct status gate | Python 3.11 PASS | keep frozen |
| `src/infrastructure/database/base.py` | `ADAPTER_REUSE` | SQLAlchemy row/repository mapper | Python 3.11 PASS | wrap |
| `tests/fixtures/nvda_financials.json` | `DIRECT_REUSE` | deterministic fixture provider | PASS | keep |
| documented FinRobot/FMP connector candidate | `ADAPTER_REUSE` | `FMPProvider`/`FMPTransport` boundary | source not present in checkout; runtime audit pending | connect later without leaking imports |
| prior repository data/evidence implementation | `PORT_REQUIRED` | none found in audited checkout | not applicable | no equivalent logic rewritten |

## Known gaps

- The live FMP schema is isolated behind `FMPTransport`, but only financial-statement endpoints are
  mapped in this increment. Profile, market-price, news, estimates, and peer endpoints remain later
  adapters.
- Coarse TTLs and duplicate conflicts are implemented. Production source priority, filing
  restatements, TTM-versus-FY semantics, and adjusted-versus-unadjusted policies remain integration
  work.
- Structurally invalid raw rows (for example, a missing `value`) are retained in the raw artifact
  and returned as rejection diagnostics. They cannot become a frozen `EvidenceRecord` because that
  contract requires a normalized field/value/unit.
- SQLAlchemy table creation is tested directly. The integration workstream must add the table to
  the project's migration lifecycle.
- No FinRobot checkout exists in this branch, so no direct Python 3.11 import/runtime audit of its
  connector code was possible. The boundary is ready for reuse through a later adapter.

## Contract deviations

None. No `CONTRACT_CHANGE_REQUEST` is required.

The implementation deliberately does not add validation/conflict-detail fields to the frozen
`EvidenceRecord`. Detailed issues stay in `EvidenceIngestionResult.diagnostics`; the frozen status
enum is used for durable decisions.

## Integration notes

1. Configure a provider and repository at the application composition root.
2. Configure `LocalRawArtifactStore(artifact_root)` for local runs; replace it with an object-store
   implementation in production without changing ingestion.
3. Pass only `result.accepted` to Agent/Capability layers.
4. Persist `result.records`; records with `CONFLICT` or `REJECTED` remain available for review but
   must not enter formal reasoning.
5. Provide FMP credentials only to `HttpxFMPTransport`; API keys are never included in source
   locators, hashes, records, or artifacts by this workstream.
