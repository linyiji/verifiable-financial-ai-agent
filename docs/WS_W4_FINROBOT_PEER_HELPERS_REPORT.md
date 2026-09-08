# WS-W4 — FinRobot Peer Helper Controlled Port

[简体中文](WS_W4_FINROBOT_PEER_HELPERS_REPORT.zh-CN.md)

## Result

PASS. The owned peer helper port contains only deterministic period alignment,
pivoting, metric-matrix construction, and arithmetic aggregation. It does not
fetch data, discover candidates, select comparables, fill missing values, or
project future periods.

## Pinned source and attribution

- Upstream: AI4Finance Foundation / FinRobot
- License: Apache-2.0
- Exact commit: `d221910096de87579b02f8f0674652bf1a175f51`
- Reviewed symbol:
  `finrobot_equity/core/src/modules/market_data_api.py:combine_peer_financial_data`
- Owned port: `src/adapters/finrobot/peer_port.py`
- Capability: `finrobot_peer_metric_aggregation@1.0.0`

The upstream function mixes FMP calls with pandas record construction and
pivoting. WS-W4 ports only the pure record-to-matrix idea. Provider retrieval
remains in the existing FMP Evidence Layer. `project_ebitda_for_peers` is not
ported because it embeds a projection assumption and would require an explicit
forecast contract.

## Decision matrix

| Concern | Upstream behavior | WS-W4 decision | Runtime status |
| --- | --- | --- | --- |
| Provider retrieval | FMP calls inside peer combiner | REJECTED; use existing Evidence Layer | Not present |
| Candidate discovery | Ticker list supplied to fetch loop | REJECTED; preserve existing candidate source | Not present |
| Comparable selection | Implicit caller responsibility | Preserve `PeerSelectionPolicy` as sole selector | Existing boundary |
| Period alignment | Sparse pandas pivots | PORTED; retain only complete historical periods | Active |
| Pivot / metric matrix | pandas pivot | PORTED to deterministic DTOs, no pandas dependency | Active |
| Aggregation | Not separated | ADAPTED to explicit mean/median/min/max formulas | Active |
| Missing values | Sparse cells/NaN possible | Fail closed or report excluded period; never fill | Active |
| Projection | Average-growth projection helper | REJECTED for this workstream | Not present |

## Input and selection boundary

The port accepts only `SelectedComparableMetric` values. A canonical metric can
be created directly only with the literal `selected=true` guard, representing an
already-selected comparable. The Evidence constructor additionally requires:

1. `EvidenceStatus.ACCEPTED`;
2. `EvidenceCategory.PEER`;
3. an existing `PeerSelectionDecision` for the same symbol;
4. `PeerSelectionDecision.selected == true`.

A rejected decision raises `PeerMetricInputError`. The helper never edits or
replaces the decision. Missing enrichment remains a rejection under the existing
candidate → selection-policy → selected-comparable architecture.

## Actual runtime call path

```text
FMP peer candidate Evidence
  → StockPeersCandidateSource
  → PeerSelectionPolicy
  → selected PeerSelectionDecision
  → SelectedComparableMetric.from_accepted_evidence
  → align_peer_periods
  → pivot_peer_metrics / PeerMetricMatrixDTO
  → CapabilityRegistry
  → ToolRuntime
  → NativeToolBackend
  → PeerMetricAggregationCapability
  → CalculationRecord[]
```

Every numeric aggregate is a `CalculationRecord` with capability and formula
versions, exact input Evidence IDs and values, output unit, implementation hash,
Python runtime, upstream commit URL, and Apache-2.0 attribution. The calculation
parameters explicitly record `projection_policy=PROHIBITED` and
`missing_value_policy=EXCLUDE_INCOMPLETE_PERIOD_NO_FILL`.

## Safety checks

- No `requests`, `httpx`, `aiohttp`, or `urllib` imports in the owned port.
- No provider/configuration/key input exists.
- No candidate source or selection policy implementation exists in the port.
- No FMP connector duplication.
- No implicit forecast, interpolation, or carry-forward.
- Cross-unit/cross-currency aggregation fails closed.
- Evidence outside `CapabilityContext.accepted_evidence_ids` fails closed.
- Upstream checkout was read-only and unchanged.

## Verification

Focused test command:

```text
PYTHONPATH=$PWD .venv/bin/pytest -q \
  tests/financial/test_finrobot_peer_port.py \
  tests/integration/test_finrobot_peer_runtime.py
```

Result: `10 passed`.

Full repository regression: `230 passed, 3 skipped` (the three skips are the
existing opt-in real PostgreSQL checks, which require a configured PostgreSQL
URL and `asyncpg`).

The integration test executes the real candidate → policy → selected metric →
matrix → registry → runtime → native capability path. It proves that a peer with
missing enrichment remains `selected=false`, cannot enter the matrix, and is not
mutated during aggregation. An AST-level dependency assertion verifies that the
port has no HTTP client import.

## Contract change requests

None. WS-W4 changes no shared domain contract, enum, setting, dependency,
database contract, API core, or frontend file.
