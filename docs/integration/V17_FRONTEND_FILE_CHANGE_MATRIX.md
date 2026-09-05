# V17 Frontend File Change Matrix

Status: `FILE_CLASSIFICATION_COMPLETE_IMPLEMENTATION_NOT_AUTHORIZED`

```text
V17_FILES_CLASSIFIED = 65/65
PHASE4_CORE_FILES = 33
PHASE5_DEFERRED_FILES = 2
DEMO_ONLY_FILES = 6
FRONTEND_V17_CURRENT_GATE = BLOCKED_BY_BACKEND_CONTRACT
```

## Authority and counting rules

Baseline hashes below come from immutable Git object
`d854c97789c98cca14fee3f4b3d7f00e0d5d137a`, never from a dirty checkout. The V17 package is
`Verifiable_Financial_Agent_Frontend_V17_Integration_Package_WITH_HANDOFF.zip`, SHA-256
`b90a356d666c30a07362f080fd418a2cf051c9b80483d308eac474dc51d79f31`.

The archive has 65 files. Its manifest lists only 61: it omits itself and three `handoff/` files, and
its README digest is stale (`017d04be…` declared; `21785aae…` actual). This matrix nevertheless
classifies all 65 archive members.

`PHASE4_CORE_FILES=33` counts the future semantic application/test footprint: 22 V17 scaffold
semantic files plus 11 real baseline support/test files omitted by the scaffold. It excludes five
unchanged build/config files, reference CSS, Demo-only files, Phase 5 files, and package documents.
The number is a governed proposal, not implementation authorization.

Abbreviations: `CO` Coordinator; `SCO` Shared Contract Owner; `FE-A` Runtime/SSE; `FE-B` Research
Flow; `FE-C` Results/Trace; `FE-D` Object Core; `FE-E` Acceptance; `P5` future Phase 5 owner;
`DO` Demo owner. `—` means deliberately no application worker/shared owner.

## V17 scaffold application map — 36/36

| V17 package path | Governed current/target real path | Exists at V8.1 / baseline blob | Classification | Change type | Phase owner | Backend dependency | Shared-file owner | Future worker | Expected test IDs | Risk |
|---|---|---|---|---|---|---|---|---|---|---|
| `apps/web/index.html` | same | YES / `63da8c5a4e22318c44ea40e3e96b1097badea3d9` | `UNCHANGED` | — | CO | N/A | CO | — | typecheck/build | Low; reject title-only overwrite |
| `apps/web/package.json` | same | YES / `b27956355014e2931a087f12dba717ae9e1e099b` | `UNCHANGED` | — | CO | N/A | CO | — | typecheck, runtime, build | Critical if scaffold copied: removes `test:runtime` and changes dependencies |
| `apps/web/src/App.tsx` | same | YES / `a41a3b16232db24c7c94b0e42c0132c7b493c53c` | `MODIFY_EXISTING` | BC, PS, INT, A11Y, RESP | Phase 4 | `WAITING_FOR_BACKEND_FREEZE` | CO | CO final composition | E2E 001–003, 063–073, 101–112; ID 023–028 | Critical; preserve URL/store architecture and isolate Demo |
| `apps/web/src/api/DemoFrontendDataSource.ts` | `apps/web/src/data/DemoFrontendDataSource.ts` | YES mapped / `5c8fa7355331e5c2991b294e61a0f3d70e64aab6` | `DEMO_ONLY` | SCN, BUG | Demo | N/A | DO | DO | `@demo-contract`; E2E 065–066 negative | High leakage/fallback risk |
| `apps/web/src/api/DemoRuntimeTransport.ts` | `apps/web/src/runtime/DemoRuntimeTransport.ts` | YES mapped / `6371bdbd5982e4fc5edea6b9de140ef4ad9e8e4d` | `DEMO_ONLY` | SCN | Demo | N/A | DO | DO | runtime Demo; E2E 066/068 negative | High if production-reachable |
| `apps/web/src/api/FrontendDataSource.ts` | `apps/web/src/data/FrontendDataSource.ts` | YES mapped / `dafca0403730f8857695c811def8f1771f3d232f` | `MODIFY_EXISTING` | BC, PS | Phase 4 | `WAITING_FOR_BACKEND_FREEZE` | SCO | SCO | E2E 002–007, 067, 070–076, 092–096; ID 001–020 | High; Pages must never receive raw JSON |
| `apps/web/src/api/HttpFrontendDataSource.ts` | `apps/web/src/data/HttpFrontendDataSource.ts` | YES mapped / `cb63bd35ffa3ee778a4073fd9a21b1d12c93fbdc` | `MODIFY_EXISTING` | BC, BUG | Phase 4 | `BACKEND_ROUTE_REQUIRED` | SCO review | FE-A | E2E 067, 069–076, 092–096; ID 001–028 | Critical; scaffold casts raw JSON |
| `apps/web/src/api/RuntimeTransport.ts` | `apps/web/src/runtime/RuntimeTransport.ts` | YES mapped / `c0ede0de05a78954239af8e325021f78ce949358` | `MODIFY_EXISTING` | BC, PS | Phase 4 | `WAITING_FOR_BACKEND_FREEZE` | SCO | SCO | SSE 001–020; E2E 068, 077–088 | High; cursor/connection/recovery contract missing |
| `apps/web/src/api/SSERuntimeTransport.ts` | `apps/web/src/runtime/SSERuntimeTransport.ts` | YES mapped / `f3fc26c2b9ed2c99146732119102acff575c1b43` | `MODIFY_EXISTING` | BC, BUG | Phase 4 | `SEMANTIC_CONFLICT` | SCO review | FE-A | SSE 001–020; E2E 068, 077–088 | Critical; `onmessage` misses named events and no resume exists |
| `apps/web/src/components/ClaimTraceDrawer.tsx` | `apps/web/src/components/claims/ClaimTraceDrawer.tsx` | YES mapped / `66c45818e8c1947eb79915cb0b7e8e661c4ba74d` | `MODIFY_EXISTING` | BC, INT, A11Y, BUG | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-C | E2E 048–055, 063, 094–095; ID 020, 024–027 | High; preserve exact anchor/focus/scroll/history |
| `apps/web/src/components/ExecutionRecord.tsx` | same proposed target | NO | `NEW_FILE` | BC, PS, INT, A11Y, RESP | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-C | E2E 047, 054, 063, 069, 094–095, 107–108 | Critical; allowlisted typed display only, no raw stringify/CoT |
| `apps/web/src/components/FinancialReview.tsx` | `apps/web/src/components/review/FinancialReview.tsx` | YES mapped / `733d5c2216586d319a7f5bbe83b7aebd89122a8c` | `MODIFY_EXISTING` | BC, PS, INT, A11Y | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-C | E2E 040–043, 047, 053, 092–095; ID 015–018 | High; no frontend PASS or synthetic per-Claim review |
| `apps/web/src/components/ProfessionalReport.tsx` | same proposed target | NO | `NEW_FILE` | BC, PS, INT, A11Y, RESP | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-C | E2E 045–050, 092–096; ID 013–020 | Critical; scaffold hardcodes authoritative metrics |
| `apps/web/src/components/ResearchCompare.tsx` | same future target | NO | `PHASE5_DEFERRED` | BC, PS, INT | Phase 5 | `PHASE5_DEFERRED` | P5 | P5 | E2E 058–062/097 Phase 5; ID 021–022 | High if enabled in Phase 4 |
| `apps/web/src/components/ResearchMemory.tsx` | same future target | NO | `PHASE5_DEFERRED` | BC, PS, INT | Phase 5 | `PHASE5_DEFERRED` | P5 | P5 | Scene 05/06 Phase 5 | High if presented as backend truth |
| `apps/web/src/components/ResearchPath.tsx` | `apps/web/src/components/research-path/ResearchPath.tsx` | YES mapped / `50ec6352734596c9835af432def0c95651fe1169` | `MODIFY_EXISTING` | BC, PS, INT, A11Y, BUG | Phase 4 | `SEMANTIC_CONFLICT` | — | FE-B | E2E 027–036, 089–091, 104; ID 007–010 | High; only three approved mutation types |
| `apps/web/src/components/ResearchPlanSnapshot.tsx` | same proposed target | NO | `NEW_FILE` | BC, PS, A11Y, RESP | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-B | E2E 024–026, 074–075; ID 002–007 | High; honest Scheme-only preview required |
| `apps/web/src/components/ResearchRuntimeWorkspace.tsx` | same proposed target | NO | `NEW_FILE` | BC, PS, INT, A11Y, RESP | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-B | E2E 026–043, 076–091; ID 007–010 | High; local state may not own canonical Run truth |
| `apps/web/src/components/TaskDetailDrawer.tsx` | `apps/web/src/components/tasks/TaskDetailDrawer.tsx` | YES mapped / `6a3e8767b300c0eaf495fcdfeaa0c90be6de1564` | `MODIFY_EXISTING` | BC, INT, A11Y, BUG | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-B | E2E 034, 036–039, 043, 050, 063; ID 008–010/020 | High; observable process only, no hidden CoT |
| `apps/web/src/components/TraceChain.tsx` | same proposed target | NO | `NEW_FILE` | BC, PS, INT, A11Y | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-C | E2E 047–055, 063, 094–095; ID 020/024 | High; preserve O/R/T/C/V/A/K/E/X and return anchor |
| `apps/web/src/demo/PresenterOverlay.tsx` | same demo-only target | NO | `DEMO_ONLY` | SCN, INT | Demo | N/A | DO | DO | E2E 109–112; presenter isolation; E2E 065–066 negative | Critical; default false and absent from production authority graph |
| `apps/web/src/demo/demoData.ts` | reuse `apps/web/src/state/demo.ts` + `state/demoScenarios/fixtures.ts` | NO exact / mapped `7b81fd1118240b9faa1b883955a7ccb9f487cf82` + `d6b4cdfb50e388c4b74abcc9bfae4eac0497388a` | `DEMO_ONLY` | SCN | Demo | N/A | DO | DO | runtime; six Demo Scenes | Critical; no second Demo authority tree |
| `apps/web/src/demo/scenarioRuntime.ts` | reuse `state/demoScenarios/DemoScenarioStore.ts`/Demo transport; no standalone path | NO exact / nearest `e0d169754dedc4edf73b1e715b0808c6c9f99211` | `DEMO_ONLY` | SCN | Demo | N/A | DO | DO | Demo Scene replay only | Medium; do not duplicate orchestration authority |
| `apps/web/src/demo/scenarios.ts` | `apps/web/src/state/demoScenarios/fixtures.ts` | NO exact / mapped `d6b4cdfb50e388c4b74abcc9bfae4eac0497388a` | `DEMO_ONLY` | SCN | Demo | N/A | DO | DO | Scene 01–06 Demo contract | High; Scene 05/06 never satisfy Phase 4 real gates |
| `apps/web/src/main.tsx` | same | YES / `859ff16fb43366b46fe7ce32f1f686113d88022d` | `UNCHANGED` | — | CO | N/A | CO | — | typecheck/build | Low |
| `apps/web/src/pages/NewResearchTaskPage.tsx` | same | YES / `17259d066c10a28a2b694b8cb748897ae60af20f` | `MODIFY_EXISTING` | BC, PS, INT, A11Y, BUG | Phase 4 | `BACKEND_ROUTE_REQUIRED` | — | FE-B | E2E 008–025, 074–075, 101–103; ID 001–005 | Critical; no `OBJ-NVDA` fallback/fresh retry UUID |
| `apps/web/src/pages/ResearchObjectDetailPage.tsx` | same; released Object Core slice only | YES / `b6f805cb149422a76e5eeb11f58d92e4d57d828d` | `MODIFY_EXISTING` | BC, PS, INT, A11Y, RESP | Phase 4 core slice | `BACKEND_PROJECTION_REQUIRED` | — | FE-D | core E2E 057–063, 070–073, 076, 094, 096, 098; ID 001/006/023–027 | High; real Memory/Compare/versioned View remain Phase 5 |
| `apps/web/src/pages/ResearchObjectsPage.tsx` | same | YES / `579143cfb0582b78bdd65468db67768bdf0106c2` | `MODIFY_EXISTING` | BC, INT, A11Y, RESP | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-D | E2E 003, 056–058, 063–064; ID 001/025–027 | High; no symbol/name/latest fallback |
| `apps/web/src/pages/ResearchRunPage.tsx` | same | YES / `53f8b3b955cec1c5d417c6af3c791e219ceb175b` | `MODIFY_EXISTING` | BC, PS, INT, A11Y, RESP | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-B | E2E 026–043, 076–091, 104; SSE 014; ID 004–010/023–027 | Critical; stage tab state is presentational only |
| `apps/web/src/pages/ResearchRunsPage.tsx` | same | YES / `ddb538626595a4e6e7709d12263e7bd694da5ebb` | `MODIFY_EXISTING` | BC, PS, INT, A11Y, RESP | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-B | E2E 002, 004–007, 076; ID 006/023–027 | High; global collection missing |
| `apps/web/src/pages/ResultsPage.tsx` | same | YES / `a85e338ed10a6385bb5fdd202e2d0bbcd234c1e6` | `MODIFY_EXISTING` | BC, PS, INT, A11Y, RESP, BUG | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-C | E2E 044–055, 063, 092–098, 107–108; ID 013–020/023–028 | Critical; A/B/C one canonical record |
| `apps/web/src/state/runtimeEventReducer.ts` | same | YES / `80c274834d2ec086161f22d75edbc66506946999` | `MODIFY_EXISTING` | BC, PS, BUG | Phase 4 | `SEMANTIC_CONFLICT` | SCO contract review | FE-A | runtime; E2E 077–091; SSE 001–020; ID 007–010 | Critical; preserve dedupe/order/fail-closed and terminal semantics |
| `apps/web/src/styles/v17.css` | no direct target; distribute reviewed deltas across real modular styles | NO | `REFERENCE_ONLY` | UX | Reference | N/A | CO/UX | — | governed viewports/visual regression | High; never wholesale replace modular CSS |
| `apps/web/src/types/domain.ts` | same | YES / `7cd0c7378ba1e5f77a61310f84d4aff10209a408` | `MODIFY_EXISTING` | BC, PS, BUG | Phase 4 | `SEMANTIC_CONFLICT` | SCO | SCO | typecheck, exhaustive DTO/enum, E2E 069–095; ID 001–028 | Critical; package advertises deferred mutations and loses detail |
| `apps/web/tsconfig.json` | same | YES / `d5b5c40566c88878e22a83523770fa1a11936f26` | `UNCHANGED` | — | CO | N/A | CO | — | typecheck/build | Low; reject package downgrade |
| `apps/web/vite.config.ts` | same | YES / `b4c267c1d3525e18463acaf544eb3ccde50ce6e4` | `UNCHANGED` | — | CO | N/A | CO | — | dev proxy/build | Medium; package removes `/api` proxy |

## Real baseline support/test files omitted by V17 — candidate footprint 11/11

| Current real path | Exists / baseline blob | V17 relationship | Classification / change type | Phase owner | Backend dependency | Shared owner | Future worker | Expected tests | Risk |
|---|---|---|---|---|---|---|---|---|---|
| `apps/web/src/api/client.ts` | YES / `e445257657518b3489b0a18eb51fa2c8a7db4cbc` | Required adapter/route owner omitted by package | `MODIFY_EXISTING`; BC | Phase 4 | `BACKEND_ROUTE_REQUIRED` | SCO review | FE-A | E2E 067, 074–096 | High |
| `apps/web/src/components/overlays/ArtifactUnavailablePanel.tsx` | YES / `12a34bff410f0d9b497a0a55e28a97fb35cfb7a3` | Availability/error consumer omitted by package | `MODIFY_EXISTING`; BC, A11Y | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | — | FE-C | E2E 051–052/096 | Medium |
| `apps/web/src/components/shell/AppShell.tsx` | YES / `595b03ad294308d9b33924d29a36f8e1f786b12a` | Production shell omitted by package | `MODIFY_EXISTING`; BC, PS, INT | Phase 4 | `BACKEND_PROJECTION_REQUIRED` | CO | CO | E2E 001–003/065–068 | High |
| `apps/web/src/routing/history.ts` | YES / `84a1e2746f2a4d321c1e678ea669c3f86087dea9` | Exact route/context owner omitted by package | `MODIFY_EXISTING`; BC, INT, BUG | Phase 4 | `WAITING_FOR_BACKEND_FREEZE` | CO review | FE-C | E2E 044/049–055/063/094; ID 020/024 | High |
| `apps/web/src/state/status.ts` | YES / `65464789767ed97896c20a3e12c642fedb036f9f` | Total status maps omitted by package | `MODIFY_EXISTING`; BC, BUG | Phase 4 | `WAITING_FOR_BACKEND_FREEZE` | SCO | FE-A | exhaustive enum/unknown tests | High |
| `apps/web/src/styles/v8-baseline.css` | YES / `efd4ee2e96bfc7f2828a64ef2b5759f3c3144bce` | Reviewed V17 visual delta target | `MODIFY_EXISTING`; UX, RESP, A11Y | Phase 4 | N/A | CO/UX | CO | viewport/visual/a11y | Medium |
| `apps/web/src/styles/workspace-pages.css` | YES / `050e127eba96d979e9a7e851e0be6a048948ed81` | New/Runs/Objects V17 visual delta | `MODIFY_EXISTING`; UX, RESP, A11Y | Phase 4 | N/A | CO/UX | FE-B/FE-D | viewport/visual/a11y | Medium |
| `apps/web/src/styles/research-run.css` | YES / `2f2f38d45a2d56b0c661623ec94fec5af4637012` | Run/path V17 visual delta | `MODIFY_EXISTING`; UX, RESP, A11Y | Phase 4 | N/A | CO/UX | FE-B | viewport/visual/a11y | Medium |
| `apps/web/src/styles/results.css` | YES / `a1e739362bf3a5f92484fe1d4a122fb4299c07e3` | A/B/C/trace V17 visual delta | `MODIFY_EXISTING`; UX, RESP, A11Y | Phase 4 | N/A | CO/UX | FE-C | viewport/visual/a11y | Medium |
| `apps/web/src/styles/remediation.css` | YES / `2d053b26dda021c32fa0e5dee15b470f928dee61` | Preserve V8.1 fixes while applying V17 | `MODIFY_EXISTING`; BUG, UX, RESP, A11Y | Phase 4 | N/A | CO/UX | CO | full regression | High if overwritten |
| `apps/web/scripts/runtime-reducer.test.mjs` | YES / `f39e4a58b8d3b0e7e8e501d15f642d6795285cc3` | Existing runtime acceptance owner omitted by package | `MODIFY_EXISTING`; BC, BUG | Phase 4 | `WAITING_FOR_BACKEND_FREEZE` | SCO review | FE-A/FE-E | runtime, SSE 001–020, E2E 077–091 | Critical test contract |

Additional baseline files remain governed but are not expected semantic changes: `OverlaySurface.tsx`
(`480c8c…`), `run-runtime-test.mjs` (`a08322…`), `package-lock.json` (`eb66c2…`), and the Demo
event/store/index files (`2f678e…`, `e0d169…`, `f3c507…`). A changed lockfile would require a new
declared scope and candidate freeze. No Playwright path exists today; FE-E must choose a real path only
when implementation is authorized.

## Package reference/governance artifact disposition — 29/29

| Archive artifact | Current real path / existence | Baseline hash when applicable | Classification | Owner | Backend dependency | Worker/tests/risk |
|---|---|---|---|---|---|---|
| `MANIFEST_V17.json` | none | — | `GOVERNANCE_ONLY` | CO | N/A | Validate checksums; High: incomplete/stale |
| `README.md` | collides with repository `README.md` | `c693a958b8b8edd6347c8efe0bf0b7037d5f7dc3` | `REFERENCE_ONLY` | CO | N/A | Never overwrite; High |
| `backend_contracts/README.md` | none | — | `REFERENCE_ONLY` | SCO | N/A | Stub guidance only |
| `backend_contracts/models.py` | none | — | `REFERENCE_ONLY` | SCO/backend | `WAITING_FOR_BACKEND_FREEZE` | Never create duplicate canonical models; High |
| `backend_contracts/__pycache__/models.cpython-313.pyc` | none | — | `OUT_OF_SCOPE` | — | N/A | Exclude compiled debris |
| `codex/FRONTEND_BACKEND_INTEGRATION_PROMPT_V17.md` | none | — | `GOVERNANCE_ONLY` | CO | N/A | Operational input only |
| `docs/00_READ_FIRST.md` | collides with approved architecture file | `5dbfcb50d156a26ac225e7814740b4215e501efe` | `REFERENCE_ONLY` | CO | N/A | Never overwrite; High |
| `docs/01_V8_TO_V17_COMPLETE_CHANGELOG.md` | none | — | `REFERENCE_ONLY` | CO | N/A | Product intent only |
| `docs/02_FRONTEND_V17_MODULE_MAP.md` | none | — | `REFERENCE_ONLY` | CO | N/A | Proposed paths conflict with actual tree |
| `docs/03_BACKEND_REQUIREMENTS_V17.md` | none | — | `REFERENCE_ONLY` | SCO | `WAITING_FOR_BACKEND_FREEZE` | Not backend availability proof |
| `docs/04_FRONTEND_BACKEND_CONTRACT_MATRIX.md` | none | — | `REFERENCE_ONLY` | SCO | `WAITING_FOR_BACKEND_FREEZE` | Target contract only |
| `docs/05_API_CONTRACT_V17.md` | none | — | `REFERENCE_ONLY` | SCO | `WAITING_FOR_BACKEND_FREEZE` | Suggested routes only |
| `docs/06_SSE_EVENT_CONTRACT_V17.md` | none | — | `REFERENCE_ONLY` | SCO/FE-A | `SEMANTIC_CONFLICT` | Conflicts with actual event semantics |
| `docs/07_RESEARCH_MEMORY_INCREMENTAL_BACKEND.md` | none | — | `REFERENCE_ONLY` | P5 | `PHASE5_DEFERRED` | No activation |
| `docs/08_FINANCIAL_REVIEW_EXECUTION_TRACE_BACKEND.md` | none | — | `REFERENCE_ONLY` | SCO/FE-C | `BACKEND_PROJECTION_REQUIRED` | Target only |
| `docs/09_REPORT_CLAIM_TRACE_BACKEND.md` | none | — | `REFERENCE_ONLY` | SCO/FE-C | `BACKEND_PROJECTION_REQUIRED` | Target only |
| `docs/10_DEMO_VS_PRODUCT_UI_BOUNDARY.md` | none | — | `REFERENCE_ONLY` | CO | N/A | Isolation input |
| `docs/11_FILE_RELATIONSHIP_AND_DATAFLOW.md` | none | — | `REFERENCE_ONLY` | CO | N/A | Does not supersede actual tree |
| `docs/12_MIGRATION_PLAN_V8_TO_V17.md` | none | — | `REFERENCE_ONLY` | CO | N/A | Superseded by governed boundary |
| `docs/13_ACCEPTANCE_CHECKLIST_V17.md` | none | — | `REFERENCE_ONLY` | FE-E | `WAITING_FOR_BACKEND_FREEZE` | Does not replace P4 gates |
| `docs/14_OPEN_GAPS_AND_NON_GOALS.md` | none | — | `REFERENCE_ONLY` | CO | N/A | Gap input |
| `docs/15_V8_FILE_TO_V17_FILE_MAPPING.md` | none | — | `REFERENCE_ONLY` | CO | N/A | Inaccurate against actual V8.1 paths |
| `docs/16_BACKEND_MODULE_RELATIONSHIP.md` | none | — | `REFERENCE_ONLY` | SCO | `WAITING_FOR_BACKEND_FREEZE` | Conceptual only |
| `docs/17_HTML_TO_TSX_MAPPING.md` | none | — | `REFERENCE_ONLY` | CO/UX | N/A | Decomposition input only |
| `handoff/01_GPT_HANDOFF_V17.md` | none | — | `GOVERNANCE_ONLY` | CO | N/A | Handoff input |
| `handoff/02_GPT_EXECUTION_INSTRUCTION_V17.md` | none | — | `GOVERNANCE_ONLY` | CO | N/A | Handoff input |
| `handoff/03_COPY_PASTE_STARTER_PROMPT.md` | none | — | `GOVERNANCE_ONLY` | CO | N/A | Handoff input |
| `references_v8.html` | `frontend_reference/financial_agent_workspace_v8_dynamic_path.html` | blob `d18cb58e359d4caf89df7db84731e84356a77bac`; SHA-256 `d4131743…` | `REFERENCE_ONLY` | CO/UX | N/A | Exact content match; never source |
| `references_v17.html` | none | package SHA-256 `1cc44c95017b2178e39138b1310e02c55d849dd71af50b63c074686a215ed18d` | `REFERENCE_ONLY` | CO/UX | N/A | Hardcoded Demo/financial state; never source |

## Explicit Phase 5 names without Phase 4 paths

`ResearchViewVersion` is already a scaffold type within `types/domain.ts`; its real behavior is
`PHASE5_DEFERRED`. No production path is invented for `ResearchObjectVersion`, `ComparisonDataset`,
`IncrementalResearchSeed`, Freshness, Reuse, Refresh, Revalidate, Prevent, Claim Diff, or Object
Writeback. Existing occurrences are Demo/reference only. `ResearchObjectDetailPage.tsx` is Phase 4
only for the released Object Core slice.

## Classification totals

```text
V17_PACKAGE_FILES_CLASSIFIED = 65/65
UNCHANGED = 5
MODIFY_EXISTING = 17
NEW_FILE = 5
REFERENCE_ONLY = 24
PHASE5_DEFERRED = 2
DEMO_ONLY = 6
GOVERNANCE_ONLY = 5
OUT_OF_SCOPE = 1

V17_SCAFFOLD_TS_TSX = 31
EXACT_APPROVED_PATH = 10
MAPPED_TO_EXISTING_DIFFERENT_PATH = 12
NO_EXACT_BASELINE_FILE = 9

PHASE4_CORE_PACKAGE_SEMANTIC_FILES = 22
ADDITIONAL_REAL_SUPPORT_TEST_FILES = 11
PHASE4_CORE_FILES = 33
```

No scaffold file is authorized for direct copying. In particular, reject the package's hard-coded
financial values and Object fallback, fresh idempotency key on retry, raw JSON casts/stringification,
Demo imports in normal composition, native named-event-blind SSE, reducer regressions, unsupported
mutation types, and false terminal transition on `release.completed`.
