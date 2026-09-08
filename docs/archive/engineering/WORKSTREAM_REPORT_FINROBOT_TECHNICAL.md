# WS-W1 — FinRobot Technical Indicators

## Upstream gate

- Read-only checkout: `/tmp/finrobot-t0.KcINlo`
- Verified commit: `d221910096de87579b02f8f0674652bf1a175f51`
- License/NOTICE: Apache-2.0, AI4Finance Foundation © 2024–2026
- Upstream source: `finrobot_equity/core/src/modules/market_data_api.py`,
  `get_technical_indicators`
- Upstream files were not modified.

Attribution and the explicit formula-version choices are recorded in
`docs/FINROBOT_TECHNICAL_INDICATORS_ATTRIBUTION.md`.

## Owned port

`src/adapters/finrobot/technical.py` implements Python 3.11 `Decimal` calculations without pandas,
numpy, requests, FMP, YFinance, configuration, credentials, or network access:

| Capability | Formula ID(s) | Output |
|---|---|---|
| `technical_sma_50` | `sma_close_50_v1` | one numeric `CalculationRecord` |
| `technical_sma_200` | `sma_close_200_v1` | one numeric `CalculationRecord` |
| `technical_rsi_14` | `rsi_close_14_simple_average_v1` | one numeric `CalculationRecord` |
| `technical_macd_12_26_9` | versioned line/signal/histogram formulas | three numeric `CalculationRecord`s |
| `technical_volume_ratio_20` | `latest_volume_to_average_volume_20_v1` | one numeric `CalculationRecord` |

Input is rejected unless it is oldest-to-newest, paired daily close/volume `EvidenceRecord` data,
all records are `ACCEPTED` `MARKET` evidence, all belong to one run/object, and every ID appears in
the `CapabilityContext.accepted_evidence_ids` allowlist.

Each calculation records capability/version/formula, implementation SHA-256, upstream-pinned
source reference, exact input Evidence IDs, output unit, and Python runtime version.

## Calculation versus Judgment

Calculation capabilities return numbers only. RSI and MACD labels are emitted solely by the
separate versioned `TechnicalIndicatorJudgmentService`, are marked `requires_review`, and reference
their source calculation/evidence IDs. `OVERBOUGHT`, `OVERSOLD`, `BULLISH`, and `BEARISH` never
appear as calculation outputs.

## Runtime path

The integration test executes the real project path:

```text
ordered Accepted Historical Price Evidence
→ CapabilityContext Evidence allowlist
→ CapabilityRegistry
→ ToolRuntime
→ NativeToolBackend
→ owned FinRobot technical capability
→ CalculationRecord(s)
```

## Verification

- Focused formula/evidence/provenance/security tests: 8 passed.
- Real runtime-call integration test: included in the focused suite and passed.
- Financial/runtime/FinRobot-audit regression: 28 passed.
- Full repository regression: 170 passed, 3 PostgreSQL tests skipped because this isolated
  worktree did not load the live database URL/driver.
- Ruff, compileall, and `git diff --check`: PASS.

No shared-contract change was required. The current Phase 3 acceptance flow must request at least
200 historical observations (the prior Phase 2 sample plan requested only five) before SMA200 can
execute; this is an integration configuration requirement, not a shared contract change.
