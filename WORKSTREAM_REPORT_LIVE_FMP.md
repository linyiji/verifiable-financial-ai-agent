# Workstream Report — WS-I Live FMP Integration

## Scope

Implemented a credential-injected, evidence-gated live FMP integration while preserving the
Python 3.11 / Phase-1 fixture baseline.

- unified `AUTO | FMP | FIXTURE` provider selection
- typed `FMPSettings` injection; adapters perform no environment or dotenv reads
- stable endpoint definitions for profile, income, balance, cash flow, peers, quote, historical,
  analyst consensus, news, and earnings transcript
- typed authentication, entitlement, rate-limit, not-found, no-data, and provider-error outcomes
- raw response envelope → Phase-2-only artifact → freshness → validation → normalization →
  conflict detection → accepted evidence
- text, symbol, and boolean normalization needed by non-statement endpoints
- external provider-calculated metrics explicitly named `provider_reference_*`; they cannot be
  mistaken for authoritative native calculations
- bounded real NVDA vertical slice using accepted FMP evidence plus existing native Revenue Growth
  and EBITDA Margin capabilities

No shared Settings file, domain contract, enum, API entry point, package baseline, or execution
status file was changed.

## Files

- `src/adapters/fmp/models.py`
- `src/adapters/fmp/provider.py`
- `src/adapters/fmp/selection.py`
- `src/adapters/fmp/__init__.py`
- `src/data/normalization.py`
- `src/data/freshness.py`
- `tests/unit/data/test_live_fmp_integration.py`
- `tests/integration/live_fmp/test_nvda_evidence_calculation_flow.py`
- `tests/integration/live_fmp/run_nvda_vertical_slice.py`
- `WORKSTREAM_REPORT_LIVE_FMP.md`

Ignored live outputs are isolated under `artifacts/phase2/live_fmp/`; Phase-1 acceptance artifacts
were not read or overwritten.

## Interfaces

- `HttpxFMPTransport(FMPSettings).request(...) -> FMPResponseEnvelope`
- `FMPProvider.probe(ProviderRequest) -> FMPFetchResult`
- `FMPProvider.fetch(ProviderRequest) -> RawProviderSnapshot`
- `select_financial_provider(...) -> FinancialProviderSelection`
- `classify_access(http_status, payload) -> (FMPAccessStatus, error_code)`

The legacy Phase-1 `get_json` transport double remains supported so the original fixture/FMP
boundary test is unchanged and still passes.

## Module Gate

Runtime:

- Python `3.11.16`
- tests run with `PYTHONPATH=.` against this isolated checkout

Results:

- PASS — WS-I and original FMP adapter tests: **16 passed in 0.12s**
- PASS — full suite: **92 passed, 2 dependency deprecation warnings in 0.78s**
- PASS — `python -m ruff check .`: **All checks passed**
- PASS — `git diff --check`
- PASS — owned Python source compilation
- PASS — adapter direct-environment-read scan
- PASS — `.env.local` remains ignored/untracked
- PASS — actual configured secret byte-match scan across WS-I code/tests/live artifacts
- PASS — live artifact query-material scan (`apikey=` absent)

The two warnings originate in the installed FastAPI/Starlette test-client dependencies and are
unrelated to WS-I.

## Bounded Live NVDA Run

Run ID: `RUN-PHASE2-LIVE-FMP-20260903T163032Z`

Exactly one sequential request was attempted for each required endpoint. No live retry was made.
Only sanitized statuses, counts, evidence IDs, and deterministic calculation outputs were emitted.

| Endpoint | HTTP | Classification | Mapped | Accepted | Non-accepted | Notes |
|---|---:|---|---:|---:|---:|---|
| Profile | 200 | `AVAILABLE` | 12 | 12 | 0 | artifacted and accepted |
| Income | 200 | `AVAILABLE` | 10 | 4 | 6 | historical records outside explicit 800-day slice policy rejected |
| Balance | 200 | `AVAILABLE` | 6 | 3 | 3 | normal freshness gate applied |
| Cash flow | 200 | `AVAILABLE` | 6 | 3 | 3 | provider FCF is reference-only in current code |
| Peers | 200 | `AVAILABLE` | 9 | 9 | 0 | symbol evidence only |
| Quote | 200 | `AVAILABLE` | 3 | 3 | 0 | P/E and market cap are reference-only |
| Historical | 200 | `AVAILABLE` | 10 | 10 | 0 | close/volume evidence |
| Analyst | 404 | `NOT_FOUND` | 0 | 0 | 0 | initial deprecated route; see correction below |
| News | 402 | `ENTITLEMENT_DENIED` | 0 | 0 | 0 | explicit subscription classification |
| Transcript | 402 | `ENTITLEMENT_DENIED` | 0 | 0 | 0 | explicit subscription classification |

Accepted evidence total: **44**.

The bounded probe exposed that `analyst-stock-recommendations` is retired. The implementation was
corrected to the current stable `grades-consensus` route and mapper (`strongBuy`, `buy`, `hold`,
`sell`, `strongSell`) and is covered by unit tests. It was intentionally **not live-reprobed** after
the correction to honor the no-retry instruction; its current live entitlement remains unverified.

## Calculation Evidence and Results

### Revenue Growth

- Calculation ID: `CALC-PHASE2-NVDA-REVENUE-GROWTH`
- Capability: `revenue_growth` version `1.0.0`
- Prior revenue evidence: `EVD-a8f95ea1-6f79-5e45-8102-259986ae3b57`
- Current revenue evidence: `EVD-d5926930-f6e3-5b70-8793-b3a0831f29a3`
- Result: `0.6547353579009479145114447075` ratio

### EBITDA Margin

- Calculation ID: `CALC-PHASE2-NVDA-EBITDA-MARGIN`
- Capability: `ebitda_margin` version `1.0.0`
- EBITDA evidence: `EVD-0f5de59d-2de7-55f1-90eb-f974b4d071f1`
- Revenue evidence: `EVD-d5926930-f6e3-5b70-8793-b3a0831f29a3`
- Result: `0.6694143689392325574933545740` ratio

Both values were produced by existing deterministic native code from accepted evidence. No FMP
ratio/growth value was used as an authoritative calculation.

## Existing Logic Reuse Matrix

| Existing Module | Decision | Reuse Method | Compatibility | Action |
|---|---|---|---|---|
| Phase-1 `FMPProvider` | `ADAPTER_REUSE` | extend transport/provider boundary | Python 3.11 PASS | preserve legacy test double, add live envelope |
| `EvidenceIngestionService` | `DIRECT_REUSE` | raw artifact and evidence gate | PASS | unchanged |
| validation/conflict pipeline | `DIRECT_REUSE` | same status hard gate | PASS | unchanged |
| normalization | `PORT_REQUIRED` | add text/symbol/boolean units | PASS | adapted without domain change |
| `FixtureProvider` | `DIRECT_REUSE` | AUTO/FIXTURE fallback | PASS | preserve Phase 1 |
| `FMPSettings` | `DIRECT_REUSE` | typed injection | PASS | shared file unchanged |
| Revenue Growth capability | `DIRECT_REUSE` | accepted EvidenceRecord inputs | PASS | used live |
| EBITDA Margin capability | `DIRECT_REUSE` | accepted EvidenceRecord inputs | PASS | used live |

## Contract Compliance

- Raw FMP payloads remain in Adapter/Data code and the ignored raw artifact store.
- No provider JSON is passed to financial capabilities.
- Only `EvidenceStatus.ACCEPTED` records enter the native calculations.
- External FMP-derived metrics use the `provider_reference_*` naming boundary.
- Provider messages are not surfaced in errors or reports; only stable local error codes are used.
- API keys are never included in source locators, snapshots, hashes, reports, artifacts, or logs.
- Frozen domain models/enums remain unchanged.

## Known Gaps

- News and transcript require a higher FMP entitlement for the configured account.
- The corrected analyst consensus route was not live-reprobed in this bounded run.
- `ProviderRequest` has no explicit historical `from/to` or transcript fiscal-calendar object; this
  increment maps historical `limit/as_of` and parses transcript quarter/year from
  `expected_period`.
- Application/API composition remains coordinator-owned. WS-I supplies provider selection and
  injection interfaces but does not edit `apps/api/main.py` or the shared application service.
- Current freshness rules are coarse TTLs. Filing-aware restatement freshness remains future work.

## Contract Deviations

None. No frozen contract change is required.

## Integration Notes

1. At the coordinator-owned composition root, call `select_financial_provider` with
   `settings.fmp`; do not read environment variables in the adapter.
2. Keep live artifacts in a provider/run namespace distinct from Phase-1 acceptance artifacts.
3. Use `probe` when endpoint availability must be reported without collapsing entitlement and
   authentication failures into a generic exception.
4. Pass `EvidenceIngestionResult.accepted.records`—never `RawProviderSnapshot`—to financial code.
5. Treat all `provider_reference_*` records as informational inputs only unless an explicit native
   calculation independently verifies them.
