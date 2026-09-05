# Phase 4 Test Data and Environment Strategy

Status: `DESIGN_ONLY - NOT_IMPLEMENTED - NOT_EXECUTED`  
Scope: Phase 4 real `SCENE-01..04`; Phase 5 `DEFINED_NOT_ACTIVATED`  
Earliest manual product test: `IG-01` in E2

This strategy prevents fixture, Demo, replayed or merely live data from being promoted into a stronger evidence class than it can support.

## Data classes

| Class | May prove | Must not prove |
|---|---|---|
| `CONTRACT_FIXTURE` | schemas, versions, enums, decoder/error/cardinality behavior | business truth, provider, persistence, financial or release truth |
| `SYNTHETIC` | domain rules, transactions, identity negatives, fault recovery, deterministic calculation | current external truth or live availability |
| `CONTROLLED_REAL` | realistic validation/normalization/financial semantics and reproducible E2E | current freshness or live connectivity |
| `LIVE_PROVIDER` | actual configured-provider connectivity, mapping and request provenance | universal provider truth, thesis truth or automatic acceptance |
| `AUTHORITATIVE_ACCEPTANCE` | only the candidate/environment/gates bound in its independently auditable manifest | another candidate, environment or Run without rerun |
| `DEMO_ONLY` | isolated Presenter UX/rehearsal/accessibility | any real Backend/SSE/persistence/financial/PJ/release gate |

`data_class` is separate from existing execution `source_class`: `DEMO_UX_ONLY`, `INTEGRATED`, `PUBLIC_REAL`, `LIMITED_REAL`, `OFFLINE_INTEGRATED`, `CHAOS_SSE`. There is no source-class promotion. A live response is not automatically authoritative.

## Environments

| Environment | Runtime/network | Allowed data | Layers and release effect |
|---|---|---|---|
| `E0_OFFLINE_DETERMINISTIC` | local tools/ephemeral stores; egress denied | contract, synthetic, controlled snapshot; Demo only isolated | L0-L2; no real persistence/SSE/Scene claim |
| `E1_LOCAL_POSTGRESQL` | target PostgreSQL, Backend, worker and controlled artifact store; provider egress denied | contract, synthetic, controlled real | Backend integration/restart/idempotency/identity; supporting only |
| `E2_LOCAL_FULL_STACK_REAL_RUNTIME` | production-path Backend/DB/worker/RISC/renderer/frontend/HTTP/SSE/browser | synthetic faults, controlled real, explicitly budgeted live | primary Phase 4 integration, vertical slice and PJ; IG-01 begins |
| `E3_PREVIEW_PARITY` | immutable builds, Node 24, production composition/config, DB/RISC/browser/observability | controlled real, limited live, authoritative outputs; isolated Presenter | system and Preview acceptance, IG-09 |
| `E4_COMPETITION_RELEASE` | exact release bundle/config/runbook on target | live when claiming LIVE, authoritative evidence, isolated watermarked Demo fallback | cold-start/release rehearsal, IG-10 |

Evidence is rerun when moving up environments. A higher-environment failure is never waived by a lower PASS. Candidate, fixture, contract, migration, dependency, build, provider policy or oracle change invalidates affected evidence.

## Global layer/data map

| Layer | Minimum env | Primary data | Coverage |
|---|---|---|---|
| L0 Static/contract | E0 | contract | hashes, 13 contracts, 55 events, routes, migration |
| L1 Unit | E0 | contract/synthetic | domain/formula/maps/errors |
| L2 Component | E0 | contract/synthetic/controlled | provider adapter, normalization, reducer, artifact, renderer, redaction |
| L3 Backend integration | E1 | synthetic/controlled | transactions, revision/watermark, restart, leases, identity |
| L4 Frontend component/adapter | E0/E1 | contract/synthetic | decode/adapt/store without raw JSON |
| L5 Backend-Frontend integration | E2 | controlled/synthetic faults | real HTTP/SSE/availability/identity |
| L6 Browser E2E | E2 | controlled; live only when required | 12 FE families |
| L7 Vertical slice | E2 | controlled and named live | VS-01..05 |
| L8 Product Journey | E2 | controlled plus separate live | PJ-01..04 |
| L9 Six-Scene | E2 | authoritative acceptance | real Scenes 01-04 only |
| L10 System | E2/E3 | controlled/live/authoritative | complete technical and restart |
| L11 Preview/release | E3/E4 | live/authoritative; isolated Demo | parity, cold start, competition |

## Positive fixture families

All fixtures are immutable, content-addressed, manifested and have A/B variants with colliding human labels.

- Objects/Runs: O-A/O-B; prepare-only, admitted, running, correcting, replan-pending, reviewing, proving, released, failed, cancelled and terminal-before-review; at least 26 Runs; multiple Runs per Object and equal-time eligible releases for opaque Run-ID tie-break.
- Events: all 55 raw values, 47 supported, eight explicit unsupported, sequences from 1, numeric/opaque equivalent cursors, comments, success/failure terminals, wait/resume, same-Task correction, add-Task/change-dependency Replans and sparse graph events. Retain canonical frame bytes and semantic hashes.
- Fundamental Evidence: adjacent fiscal revenue with positive prior; EBITDA, CFO, signed CapEx and revenue with exact period/actuality/as-of/currency/unit/series; rejected stale/missing/mismatched/conflicting candidates.
- Technical Evidence: ordered observations for SMA50/200, RSI14, MACD and volume ratio 20; raw/adjusted distinction, corporate-action state, warmup/observation count, hostile Decimal values and first/last dates.
- Metrics: ten material outputs with formula/capability/version, Evidence refs, explicit Decimal methodology, K/C/proof IDs and Backend display fields. Mandatory witness is prior 100.00, current 165.47, canonical `0.6547 RATIO`, display `65.47 %`.
- Claim/Review/Proof: single- and multi-Calculation Claims, colliding text, explicit/null primary Task, available/unavailable Judgment, PASS/REVIEW/BLOCK, stable Checks/subjects/input hashes/correction history, NOT_REQUIRED and MUST_PROVE pending/verified/invalid/failed. One Review is Run-level.
- Artifact/Trace: exactly HTML/PDF slots covering both available, PDF not generated, PDF failed and retained unavailable. Each available representation has distinct IDs/attempts/bytes/type/size/SHA/renderer/safe ref and scoped anchors. Include plural Review/Task/Execution anchors.

## Mandatory negative corpus

| Family | Cases |
|---|---|
| Identity | Substitute every B ID into A routes/refs; missing/reparented rows; same-label and latest/first/title/symbol/metric attempts |
| Contract | missing/extra fields; unknown schema/status/availability/unit/method/proof/path-change/event; bad header |
| Admission | empty/reused key with changed body; stale/expired/consumed draft; concurrent confirm; response loss; redelivery/lease expiry |
| Persistence | faults before, within and after commit/ack/publication/finalization; API/worker/DB restart |
| SSE | malformed/noncanonical/foreign/ahead cursors; duplicate/conflicting/gap/disorder/R-T mismatch/sparse/post-terminal |
| Provider | pre-Run MiMo unavailable; visible Teamo secondary; post-lock failure/drift; unknown provider; FMP timeout/auth/rate/malformed; no fixture splice |
| Generated capability | static/sandbox/test/financial failure; secret sentinel; missing source/test preimages; hash/build mismatch |
| Financial | zero/negative prior; period/actuality/currency/series mismatch; nonfinite/float; hostile context; warmup/method/corporate-action failure |
| Review/release | REVIEW/BLOCK; unstable/missing Check; false resolution; input hash mismatch; missing material item; required Proof failure; mixed X/L/V |
| Artifact | HTML failure; PENDING terminal; shared HTML/PDF ID; missing/tampered/swapped/wrong-type bytes; Range/redirect/revoked/raw path |
| Trace | cross-Run C/K/E/V/P; cross-format anchor; missing/changed manifest; inferred primary Task; DOM/text/latest fallback |
| Availability | all valid states plus forbidden terminal PENDING, AVAILABLE with reason, unavailable without identity, empty-success |
| Security | test-only sentinel names/values for Langfuse, FMP, MiMo, Teamo, API keys/passwords/auth/tokens across all exports |
| Phase 5 | memory/version/comparison/incremental/reuse/writeback presented as Phase 4 truth must fail activation/schema validation |

## Fixture manifest and lifecycle

Each record contains fixture/revision, class, allowed source classes/environments/layers/gates, activation, generator/seed, origin/capture method, provider/endpoint class, capture/retrieval/as-of, license/retention, schema/canonicalization, size/SHA, O/R IDs, raw-provider/secret flags, sanitizer, parent/supersession, expiry and Demo watermark.

Exact bytes are immutable. Ordered arrays retain order; sets are canonicalized. Load only when environment/layer/gate/activation match. Expired controlled data never becomes current/live. Licensed raw bodies are retained only when permitted; otherwise note the reproducibility limit and use authorized audit access. Generated source/test bytes, artifact bytes and RISC receipts are retained exactly whenever gates depend on them.

Lifecycle: prepare -> validate manifest -> provision environment -> bind Candidate/contracts -> execute -> sanitize/content-address evidence -> verify bundle -> independent audit. Authoritative outputs never silently return to the input catalog as fresh data.

## Live-provider quota and lock policy

Each live budget names provider, endpoint/model, environment, gates, max requests/retries/tokens, window, owner, stop threshold and credential alias. E0/E1 use zero calls; E2 defaults controlled-real; E3 uses minimal parity calls; E4 only predeclared preflight/rehearsal calls. Parallel/speculative calls and retry storms are forbidden.

MiMo is preferred and TeamoRouter secondary. Provider/model selection and lock occur before Run. Visible pre-Run secondary selection may be allowed; post-lock failure never silently switches. Controlled provider failover is not activated. Missing mandatory live evidence never switches to fixtures; it is a blocker before activation and `FAIL/REQUIRED_EVIDENCE_ABSENT` at release.

## Isolation, cleanup and secrets

Every attempt has separate DB/schema, artifact/generated/RISC roots, browser partition, SSE proxy namespace, trace Run and fixture mount. Never use developer data. Cleanup follows successful evidence retention; failed attempt manifests/hashes remain.

Demo uses separate build hash/storage/DB, persistent watermark and Demo IDs; it cannot be activated by URL/query/local storage/runtime response or mutate real state. No Demo artifact satisfies a real byte request.

Evidence refs are relative, immutable and content-addressed. Sanitization is allowlist/versioned. Exclude credentials, DSNs, cookies, bearer/refresh/private tokens, prompts, CoT, stack traces and internal paths. Secret tests use sentinels, never real values. Langfuse remains non-authoritative and fail-open for business execution; any export credential leak fails security.

## Existing seeds and limits

Useful non-grandfathered patterns include `src/data/fixtures.py`, `tests/fixtures/nvda_financials.json`, evidence-ingestion tests, `tests/fixtures/risc0_revenue_growth_input.json`, live-FMP vertical-slice helpers and generated-sandbox tests. They do not by themselves satisfy the full Phase 4 material, identity, methodology or environment contract.

Phase 5 sentinels, if retained, are E0-only forward-compatibility/schema-rejection data with `DEFINED_NOT_ACTIVATED`, `result=null` and no Phase 4 release membership. Demo Scenes 05/06 remain `DEMO_ONLY/DEMO_UX_ONLY`.

```text
ENVIRONMENTS_DEFINED=5/5
DATA_CLASSES_SEPARATED=6/6
GLOBAL_TEST_LAYERS_MAPPED=12/12
PHASE4_REAL_SCENES_SUPPORTED=4/4
PHASE5_REAL_DATA_ACTIVATED=0
DEMO_AS_REAL_EVIDENCE=0
LIVE_PROVIDER_CALLS_EXECUTED=0
AUTHORITATIVE_RUN_STARTED=NO
PRODUCTION_SOURCE_MODIFIED=NO
```
