# Phase 3 Financial Semantics Independent Final Audit

TEAM B independently audited the frozen Phase 3 candidate and authoritative evidence bundle. The decision is **PASS**. All 10 material metrics independently recompute exactly, all mandatory B1–B5 predicates pass, old findings FIN-P2-001 and FIN-P2-002 are closed, and severity counts are P0=0, P1=0, P2=0, P3=0.

## Frozen identity and independence

- Candidate SHA: `4b6721b6db433aae300f94750e1a405b6b450501`
- Candidate tree: `35c47508ed65220c26620f5ec4bdd14cb798480d`
- Source fingerprint: `sha256:3c40c15b3f7517f6dc0ad6340fa712f7da29df356cc45791ffb528aef0794752`
- Authoritative Run: `RUN-6d643419-3db3-4f99-8bc2-f8e18701a532`
- Migration head: `20260904_0006`
- Evidence bundle digest: `sha256:0faae837be5fa9028af8c30d69983ec1738c5706f8df8627084711c99f499094`
- Evidence bundle framing: sorted relative path, then `uint64be(path_length) + path + uint64be(content_length) + content`
- Evidence bundle: 63 files, 4,774,193 bytes
- Detached checkout: clean
- Foreign Run identities in the authoritative bundle: none
- Candidate commit time: `2026-09-05T12:18:45+08:00`; Run creation: `2026-09-05T04:23:02.769305Z`; candidate precedes Run.

The audit used only the assigned detached checkout and isolated Team B evidence copy. No Team A worktree, directory, notes, messages, status, judgment, summary, or receipt was inspected or reused. No source, test, database, provider, Langfuse, historical evidence, or acceptance artifact was modified. No repair, new Run, or Phase 4 work occurred.

The retained internal claims were independently cross-checked: formal acceptance is 52/52 PASS, the internal financial matrix is 13/13 PASS, and the exact Run terminates with `run.completed` at `2026-09-05T04:24:14.941545Z`.

## B1 — Fundamental metrics: 3/3 PASS

The values below were recomputed with `Decimal` from each CalculationRecord's ordered accepted Evidence identities. Rendered report values were not used as calculation authority.

| Metric | Exact independent result | Semantic checks |
|---|---:|---|
| Revenue Growth | `0.6547353579009479145114447075` | `(FY2026 revenue - FY2025 revenue) / FY2025 revenue`; adjacent FY periods; ACTUAL; USD; CURRENCY inputs; common statement series; ordered prior/current inputs |
| EBITDA Margin | `0.6694143689392325574933545740` | `FY2026 EBITDA / FY2026 revenue`; ACTUAL; USD; equal as-of and statement cohort |
| Free Cash Flow Margin | `0.4477025812964832498217080829` | `(102718000000 + -6042000000) / 215938000000`; FY2026; ACTUAL; USD; equal statement cohort; signed-negative capex retained |

The Revenue Growth precondition is `prior_revenue > 0`. Controlled, non-persistent checks independently confirmed that both zero and negative prior revenue fail closed with the owned non-positive-prior-revenue error. The FCF calculation differs from the forbidden absolute-value-capex result, proving the negative outflow was not silently converted with `abs`.

## B2 — Technical metrics: 7/7 PASS

Each metric was independently recomputed in retained Evidence-ID order. Every input is ACCEPTED, ACTUAL, DAILY evidence owned by the audited Run.

| Formula | Evidence | Exact independent result | Method closure |
|---|---:|---:|---|
| `sma_close_50_v1` | 50 close records | `210.5664` | Exact latest 50-observation arithmetic mean |
| `sma_close_200_v1` | 200 close records | `196.67945` | Exact latest 200-observation arithmetic mean |
| `rsi_close_14_simple_average_v1` | 15 close records / 14 changes | `53.677987075484669324900316238141069709885879279527` | Simple average, explicitly not Wilder |
| `macd_line_close_12_26_adjust_false_v1` | 250 close records | `3.8312329766339825859682836` | 12/26 EMA line |
| `macd_signal_close_12_26_9_adjust_false_v1` | 250 close records | `2.994088968765850171279231979` | 9-span EMA of line |
| `macd_histogram_close_12_26_9_adjust_false_v1` | 250 close records | `0.837144007868132414689051621` | Line minus signal |
| `latest_volume_to_average_volume_20_v1` | 20 volume records | `1.0267085312351010380724223296119561419231175575929` | Latest volume divided by 20-volume mean, including latest |

MACD independently closes under precision 28, `ROUND_HALF_EVEN`, `adjust=false`, first-observation seed, spans 12/26/9, and required warmup 34. All three MACD records report warmup satisfied. All 10 released canonical values equal the independent computations, and all released two-decimal display values match the owned `ROUND_HALF_EVEN` display policy.

The six price-based technical metrics retain `RAW_CLOSE` and `UNASSESSED` on their CalculationRecord and ReleasedMetric provenance. Volume Ratio uses only 20 `volume` Evidence records with unit `COUNT`, no currency, and no price/corporate-action metadata.

## B3 — Generated Capability financial semantics: PASS

The retained `GeneratedCapabilitySpecV1` canonical bytes hash to `sha256:166294149a830cac44af2024b2389aacd52545e4cb1c228223b029ba36076bf7`. Independent recompilation with compiler `vfas-generated-capability-compiler` version `1` reproduced the exact retained source bytes (`sha256:d8551c1df602f65ce0a06e2dc3d5d31cbe82cb674b8e9d3ae83832bf09dc2df2`) and test bytes (`sha256:07b836ebb2d9febc8818dde1a4186756bca9e67bec4e55643bb6ee340f79f128`). Recursive JSON object-member reordering preserved canonical meaning and compilation, while reordering the formula IR failed closed.

The compiled implementation expresses `(operating_cash_flow + signed capital_expenditure) / revenue`, emits `RATIO`, rejects zero revenue, and preserves negative-outflow capex. Controlled execution over the live retained input produced `0.4477025812964832498217080829`, exactly equal to the CalculationRecord runtime result and independent owned oracle. The retained build binds provider `mimo`, requested model `mimo-v2.5`, and actual model `mimo-v2.5`.

## B4 — Review, proof, release, and report: PASS

The independent-financial-review-v2 record contains 54 passing checks and covers exactly 539 Evidence records, 10 calculations, 10 metrics, and 10 claims. Reconstructing its canonical input snapshot independently produced `sha256:3dafcb553c8fe26b64aa4f52270f467865710ef5b274f064f834fe8efc83cfd1`, exactly matching the retained review hash.

The proof policy marks exactly Revenue Growth as `MUST_PROVE`. Its proof input commitment independently reconstructs to `sha256:688ef341b649a8299d74ecd1b52a0788e628df2962f4236add011be38314e77f`; expected output commitment is `sha256:d7254f824d221d591e8c1854a9f29ec94054d9926b6c38623f44255cc42b7538`. The RISC Zero proof is VERIFIED, its 256,610-byte receipt hashes to `sha256:293d45b31db3cfd717e049032b37d7a14b2c269a76e4612b88728498e66a9ea4`, and its journal hash is `sha256:d5506980597f998c2819a32e7f0803306c3205ceb39329df6068fd2b9c0d7a73`. Review precedes proof; verification precedes release.

CER, ReleasedResult, and CanonicalReportDTO bind the same Run. Their calculation/metric/claim/proof closures are 10/10, 10/10, 10/10, and 1/1. The ReleasedResult and DTO retain identical structured financial results, material metrics, and material claims.

- Canonical DTO semantic hash: `sha256:8abd709bde026decccbef693c1b44412b974fba8fc099c233d899938ed4e8079`
- Released metric semantics hash: `sha256:8e797d0d6ed8a94a7dfa7c55b1be6aff238d89d07ca4f4ba292e0a8263483680`
- SVG semantic hash: `sha256:5653b97b86ccbe0e80769c35fcd7ce762b09d64fffe689947ddaa2532c533024`
- SVG: 4,023 bytes, `sha256:e0e6644332fa37bda285b90b088591577436d9cd5ee0ccd8904feaf4efa06969`
- HTML: 191,709 bytes, `sha256:4ee6f9315562eb3dd634f6e2f59adc065e1b79df299fbef094ed8e1e0488812a`
- PDF: 484,625 bytes, `sha256:5998d0482a5afa7ad27d3bdb19bdf9f9c48c68d32a98169360f8dad5656be2fe`

All three artifacts bind the same Run/CER/ReleasedResult identities and contain all 10 released display metrics. HTML and PDF share the exact DTO semantic hash, all artifacts share the exact metric-semantics hash, and the retained no-refetch/render gates pass. No report-only mutation was found.

## B5 — Phase 2.1 regressions: PASS

P2.1-012 remains closed: peer candidates (9), selection decisions (9), and selected comparables (0) remain separate. All decisions are explicit rejections, all candidates lack the required enrichment, and the result is `no_selected_comparables_due_missing_enrichment`; no selected comparable was fabricated.

P2.1-013 remains closed: the single `full_time_employees` Evidence record has value `42000`, unit `COUNT`, period and period basis `CURRENT`, actuality `ACTUAL`, absent currency, and status `ACCEPTED`.

## Previous finding closure

FIN-P2-001 is **CLOSED**. `fundamental_result.calculation_refs` contains exactly the three fundamental calculations. `technical_result.calculation_refs` contains exactly the seven technical calculations. The sets are disjoint and their union is the exact 10-calculation canonical set; no technical calculation appears under the fundamental result.

FIN-P2-002 is **CLOSED**. Volume Ratio independently recomputes to the exact released value using its 20 authoritative volume Evidence references. Unsupported `RAW_CLOSE` and `UNASSESSED` attribution is absent from the Volume Ratio calculation snapshot and released metric, while genuinely price-based metrics retain valid metadata. The remediation changed only Volume Ratio metadata expansion, not the numeric formula; CalculationRecord, ReleasedMetric, Review, CER, SVG, HTML, and PDF remain consistent.

## Decision and mutation record

- `FINANCIAL_SEMANTICS_INDEPENDENT_FINAL_AUDIT = PASS`
- `FINANCIAL_MATERIAL_METRICS = 10/10 PASS`
- `FUNDAMENTAL_METRICS = 3/3 PASS`
- `TECHNICAL_METRICS = 7/7 PASS`
- `GENERATED_CAPABILITY_FINANCIAL_SEMANTICS = PASS`
- `REVIEW_PROOF_RELEASE_REPORT = PASS`
- `P2_1_REGRESSION = PASS`
- `FIN_P2_001 = CLOSED`
- `FIN_P2_002 = CLOSED`
- `P0=0, P1=0, P2=0, P3=0`
- `SOURCE_MODIFIED = NO`
- `TESTS_MODIFIED = NO`
- `DATABASE_MODIFIED = NO`
- `PROVIDER_MODIFIED = NO`
- `LANGFUSE_MODIFIED = NO`
- `EVIDENCE_OR_ACCEPTANCE_MODIFIED = NO`
- `NEW_RUN_CREATED = NO`
- `PHASE4_STARTED = NO`

Receipt hashes use SHA256 over the exact frozen file bytes and are reported out-of-band only after both receipts are complete. This avoids self-referential receipt content.
