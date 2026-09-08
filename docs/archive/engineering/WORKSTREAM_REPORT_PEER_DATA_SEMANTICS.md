# WS-Q — Peer Selection and Data Normalization Report

## Outcome

**PASS** for the Phase-2.1 WS-Q module gate.

FMP Stock Peers is now explicitly a candidate source. A deterministic policy produces one frozen
`PeerSelectionDecision` per candidate, and only positively selected candidates enter the comparable
universe. Raw provider symbols are never promoted directly into the final universe.

## Delivered implementation

| File | Responsibility |
|---|---|
| `src/data/peers.py` | candidate-source protocol, FMP Stock Peers source, policy, result boundary |
| `src/adapters/fmp/provider.py` | CURRENT observation timestamps and field-semantic unit mapping |
| `src/data/ingestion.py` | carries source endpoint, observation time, and provider time into Evidence |
| `tests/unit/data/test_peer_data_semantics.py` | unit and provider-ingestion semantics |
| `tests/integration/test_peer_selection_pipeline.py` | frozen Evidence → candidates → decisions → selected universe |

## Peer-selection boundary

```text
accepted FMP Stock Peers Evidence
                ↓
StockPeersCandidateSource
                ↓
PeerCandidate[]             ← enriched evidence-backed company facts
                ↓
PeerSelectionPolicy         ← subject facts + business-relevance assessment
                ↓
PeerSelectionDecision[]
                ↓ selected=true only
selected_comparables[]
```

The source accepts only Evidence that is:

- `ACCEPTED`;
- produced by provider `fmp`;
- identified as source endpoint `peers`;
- a canonical `peer_symbol_*` field; and
- unit `SYMBOL`.

It excludes the subject symbol and de-duplicates repeated provider candidates. Enrichment populates
the frozen candidate fields for industry, sector, market cap, data availability, metric
comparability, and source Evidence IDs.

The deterministic policy considers:

- exact industry match, or sector match as the broader classification fallback;
- explicit business relevance;
- configurable market-cap ratio range, default `0.20x–5.00x`;
- evidence-backed data availability; and
- availability of every required comparable metric.

Each structured decision contains only the frozen fields `candidate_symbol`, `selected`,
`reason_summary`, `selection_source`, and `source_evidence_ids`. The concise audit summary records
check outcomes; it contains no hidden chain-of-thought.

## Coordinator wiring API

Coordinator should construct evidence-backed facts and call:

```python
result = PeerSelectionService().select(
    subject=subject_facts,
    stock_peer_evidence=accepted_peer_evidence,
    facts_by_symbol=candidate_facts,
    business_relevance=relevance_by_symbol,
    required_metrics=frozenset({"revenue", "ebitda", "pe"}),
)
```

The outputs have intentionally different meanings:

| Output | Coordinator use |
|---|---|
| `result.candidates` | candidate audit/review only |
| `result.decisions` | persist and expose selection rationale |
| `result.selected_comparables` | the only input permitted for peer calculations/reporting |

Coordinator must not treat `stock_peer_evidence` or `result.candidates` as the final universe.
`PeerCompanyFacts.source_evidence_ids` should contain accepted profile/market/metric Evidence IDs;
facts without lineage are marked `data_available=false` and cannot be selected.

## Unit normalization audit

| Provider field | Canonical meaning | Unit |
|---|---|---|
| `fullTimeEmployees` including numeric text | headcount | `COUNT` |
| `volume`, `avgVolume` including numeric text | traded count | `COUNT` |
| `symbol` | security identifier | `SYMBOL` |
| `companyName` | label | `TEXT` |
| `price`, `marketCap` | monetary amount | source currency |
| `beta`, `pe` | provider reference ratio | `RATIO` |

Field semantics are evaluated before Python value type. This fixes the former
`full_time_employees: TEXT` error while preserving rejection of non-numeric values during canonical
normalization.

## CURRENT timestamp semantics

| Field | Meaning |
|---|---|
| `retrieved_at` | when this system received the provider response |
| `provider_timestamp` | exact provider-supplied quote/update instant, otherwise `None` |
| `observed_at` | provider timestamp when present, otherwise retrieval instant |
| `as_of` | calendar date derived from `observed_at` for CURRENT records |

Two observations on the same day therefore retain different exact instants. CURRENT data is no
longer backdated with `min(request.as_of, retrieved_at.date())`; a snapshot observed after a
historical request date is rejected by the existing future-dated Evidence policy rather than being
made to appear historically available.

## Verification

```text
$ PYTHONPATH=. pytest -q tests/unit/data/test_peer_data_semantics.py \
    tests/unit/data/test_live_fmp_integration.py \
    tests/integration/test_peer_selection_pipeline.py
19 passed in 0.11s

$ PYTHONPATH=. pytest -q
129 passed, 1 skipped, 2 dependency deprecation warnings

$ ruff check .
All checks passed!

$ ruff format --check <WS-Q changed Python files>
PASS

$ git diff --check
PASS
```

The skip is the pre-existing real PostgreSQL test, which requires `TEST_POSTGRESQL_URL` and
`asyncpg`. The warnings originate in the installed FastAPI/Starlette TestClient dependency surface.

## Ownership, contract, and secret gates

- Frozen `PeerCandidate`, `PeerSelectionDecision`, and `EvidenceRecord` contracts are consumed
  unchanged.
- `src/domain/**`, `contracts/**`, Settings, `pyproject.toml`, `apps/api/main.py`,
  `src/application/execution.py`, and `PARALLEL_EXECUTION_STATUS.md` are unchanged.
- No provider credentials, environment previews, or raw secrets are logged or persisted.
- Changed-source credential scan: PASS.
- Contract changes or deviations: **NONE**.

## Existing logic reuse

| Existing module | Decision | Method | Action |
|---|---|---|---|
| FMP `/stable/stock-peers` mapping | ADAPTER_REUSE | candidate Evidence source | retain, narrow semantics |
| `PeerCandidate` | DIRECT_REUSE | candidate boundary | keep frozen |
| `PeerSelectionDecision` | DIRECT_REUSE | policy output | keep frozen |
| Evidence ingestion and freshness gate | ADAPTER_REUSE | metadata propagation | extend |
| field normalization | ADAPTER_REUSE | field-semantic unit priority | correct |
| provider raw peer list as final universe | REPLACE_REQUIRED | deterministic policy boundary | prohibit |

## Deferred

- Coordinator persistence and API exposure of candidates/decisions.
- Live candidate enrichment collection for every peer symbol. The selection API is ready to consume
  accepted profile, market-cap, and metric Evidence after Coordinator schedules those requests.
- Metric-specific peer calculation capabilities; WS-Q selects their permissible input universe but
  does not author financial results.
