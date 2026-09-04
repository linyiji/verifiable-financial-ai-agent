# WS-W2 — FinRobot Controlled Charts

## Upstream and classification

- Read-only checkout verified at `d221910096de87579b02f8f0674652bf1a175f51`.
- Upstream license/NOTICE: Apache-2.0, AI4Finance Foundation © 2024–2026.
- Audited source: `finrobot_equity/core/src/modules/chart_generator.py`.
- Upstream was not modified or imported at runtime.
- Classification after concrete runtime integration: `ACTIVE_REUSE` as an owned controlled port.

Attribution is recorded in `docs/FINROBOT_CHARTS_ATTRIBUTION.md`.

## Runtime path

```text
CanonicalReportDTO
→ CanonicalReportChartAdapter (typed input gate)
→ PinnedFinRobotAdapter (exact pin + charts.render allowlist + deep copy)
→ DeterministicSVGChartBackend
→ controlled content-addressed SVG
→ ReportArtifactRecord + FinRobot port provenance
```

The integration test executes this full path. A mere presence of upstream code is not used as the
activation criterion.

## Safety and determinism

- The public renderer rejects every input type except `CanonicalReportDTO`.
- The backend transport accepts exactly one serialized DTO field and rejects path/ticker/provider
  extras.
- Only numeric values already present under canonical `financial_summary` are rendered. The backend
  does not calculate, forecast, select peers, assign ratings, or interpret indicators.
- Output filenames are derived from content SHA-256; run/canonical path segments use a strict
  allowlist and the resolved target must remain below the configured output root.
- SVG bytes contain no timestamps and are stable for the same DTO, renderer version, and upstream
  pin.
- No provider, FMP, network, LLM, settings, credentials, SQLAlchemy, or database code is imported.
- Report DTO data is deep-copied by the pinned adapter before the backend receives it.

## Artifact lineage

The returned artifact includes:

- `ReportArtifactRecord` with SVG ref, byte hash, semantic hash, renderer version, size,
  canonical-record ID, released-result ID, and run ID;
- exact upstream repository, commit, source module, relevant symbols, and Apache-2.0 marker;
- the same metadata embedded safely in the SVG `<metadata>` element.

## Verification

- Focused unit + real integration tests: 8 passed.
- FinRobot adapter/renderer focused regression: 17 passed.
- Full repository regression: 228 passed, 3 PostgreSQL tests skipped because the isolated
  worktree did not load the live database URL/driver.
- Ruff, compileall, secret scan, and `git diff --check`: PASS.

No CONTRACT_CHANGE_REQUEST is required.
