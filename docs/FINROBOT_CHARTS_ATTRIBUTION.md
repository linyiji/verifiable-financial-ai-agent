# FinRobot Charts — Controlled Port Attribution

The deterministic SVG renderer in `src/adapters/finrobot/charts.py` is a controlled owned port
informed by FinRobot's chart presentation concepts:

- Project: FinRobot
- Copyright: © 2024–2026 AI4Finance Foundation
- License: Apache License 2.0
- Repository: `https://github.com/AI4Finance-Foundation/FinRobot`
- Audited commit: `d221910096de87579b02f8f0674652bf1a175f51`
- Upstream source: `finrobot_equity/core/src/modules/chart_generator.py`
- Relevant upstream symbols: `generate_revenue_ebitda_chart`,
  `generate_ev_ebitda_peer_chart`, `generate_technical_indicators_chart`

License text: <https://www.apache.org/licenses/LICENSE-2.0>

FinRobot and AI4Finance are trademarks of AI4Finance Foundation. This project is not presented as
an official FinRobot distribution or endorsed derivative product.

## Controlled-port differences

No upstream source file is imported, modified, or executed. The port is implemented with the
Python standard library and emits deterministic SVG rather than invoking pandas, numpy, or
matplotlib. It accepts only serialized `CanonicalReportDTO` data passed through the existing
exact-pin `PinnedFinRobotAdapter`; it has no provider, FMP, network, LLM, configuration, credential,
or database dependency.

The SVG embeds the renderer version, exact upstream pin/source, canonical/released record IDs,
semantic hash, and license marker. The returned `ReportArtifactRecord` records the content hash,
semantic hash, renderer version, controlled artifact reference, and canonical/released lineage.
