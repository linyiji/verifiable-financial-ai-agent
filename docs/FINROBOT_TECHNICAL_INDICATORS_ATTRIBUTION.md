# FinRobot Technical Indicators — Attribution and Provenance

The owned technical-indicator port in `src/adapters/finrobot/technical.py` was informed by the
formula selection and output names in:

- Project: FinRobot
- Copyright: © 2024–2026 AI4Finance Foundation
- License: Apache License 2.0
- Repository: `https://github.com/AI4Finance-Foundation/FinRobot`
- Audited commit: `d221910096de87579b02f8f0674652bf1a175f51`
- Source: `finrobot_equity/core/src/modules/market_data_api.py`
- Symbol: `get_technical_indicators`

License text: <https://www.apache.org/licenses/LICENSE-2.0>

FinRobot and AI4Finance are trademarks of AI4Finance Foundation. This project is not presented as
an official FinRobot distribution or endorsed derivative product.

## Port boundary

This project does not import or modify the upstream module at runtime. The implementation retains
only independently testable, deterministic formula behavior and replaces pandas/numpy operations
with owned Python `Decimal` code. It excludes all upstream FMP/YFinance calls, API-key/configuration
handling, logging, broad exception swallowing, chart/report integration, and combined heuristic
signals.

The upstream source contains inconsistent implicit pandas EMA adjustment choices between the data
and chart modules. This port therefore freezes and versions the following choices explicitly:

- SMA 50/200: arithmetic mean of the latest closing-price window.
- RSI 14: simple average of gains/losses over the latest 14 price changes; 15 closes required;
  all-gain = 100, all-loss = 0, unchanged = 50.
- MACD 12/26/9: recursive EMA equivalent to pandas `adjust=False`, seeded from the first observed
  close. Every fast EMA, slow EMA, line, signal EMA, and histogram operation runs under
  `macd-decimal-context-v1` with precision `28` and `ROUND_HALF_EVEN`; the implementation does not
  inherit the process-global `Decimal` context.
- Volume Ratio 20: latest volume divided by the mean of the latest 20 volumes, including the latest
  observation.

Every produced `CalculationRecord.source_ref` contains the upstream repository, exact commit,
symbol, and `Apache-2.0` marker; `implementation_hash` hashes the owned checked-in source.

## Phase 3 financial-audit remediation delta

The existing technical semantics oracle (`FS-010`) is strengthened without adding a gate: it now
requires the calculation snapshot and released methodology to bind the policy ID, precision,
rounding, EMA adjustment/seed, 12/26/9 spans, observation count, warm-up status, and technical
price basis. The independent reviewer imports that same versioned policy definition for its owned
recomputation instead of carrying a separate precision constant.
