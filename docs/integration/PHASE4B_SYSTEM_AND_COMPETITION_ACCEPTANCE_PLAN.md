# Phase 4B System and Competition Acceptance Plan

Status: `DESIGN_READY — NOT_IMPLEMENTED — NOT_EXECUTED`  
Authority date: `2026-09-05`

```text
PHASE4A_RUNTIME_ACCEPTED=NO
IG09_PREVIEW_PARITY=NOT_ACTIVATED
IG10_PHASE4B_RELEASE_READY=NO
COMPETITION_RUNTIME_READY=NO
DEPLOYMENT_EXECUTED=NO
LIVE_PROVIDER_CALLS_EXECUTED=0
SOURCE_MODIFIED=NO
```

This future acceptance design authorizes no implementation, deployment, database mutation, provider call, image build, artifact generation or release assembly.

## Phase 4A / Phase 4B boundary

| Boundary | Phase 4A runtime acceptance | Phase 4B release/competition acceptance |
|---|---|---|
| Environment | E2 local full-stack real runtime | E3 Preview parity, then E4 competition/release |
| Purpose | prove Backend/PostgreSQL/HTTP/SSE/browser/finance/Review/trace/artifacts/Scenes 01–04/recovery | prove the exact accepted candidate is reproducible, cold-startable, operationally recoverable and truthful on advertised hosts/modes |
| Entry / exit | IG-00..06 → IG-07 technical → IG-08 Phase 4A | IG-08 → IG-09 parity → IG-10 release ready |
| Access | governed trusted-local single-user | same for private/loopback; remote/public ingress needs a separate governed authentication profile |
| Demo | separate, watermarked, zero gate contribution | separately hashed/partitioned; absent from production-default navigation/data graph |
| Provider | choose before Run, lock provider/model; no invisible switch | same; controlled post-lock failover remains inactive |
| Release claim | no Preview/public/fresh-machine claim | only manifested candidates, platforms and modes that PASS |

Phase 4A is necessary but not sufficient. E3/E4 must rerun affected evidence; lower-environment PASS cannot waive a Preview/fresh-machine failure. `PUBLIC_NETWORK_MODE` permits outbound providers, not public unauthenticated browser ingress.

## Release invariants

- One clean immutable manifest binds source, Backend/Frontend/contracts/migrations/locks, Node/Python/Rust/RISC versions, images/platforms, renderer, fixtures, proof packages, browsers and configuration.
- Operator selects exactly one frozen `PUBLIC_NETWORK_MODE`, `LIMITED_NETWORK_MODE` or `OFFLINE_DEMO_MODE`; no AUTO mode and no in-process mode switch.
- Provider/data failure never silently substitutes another provider, cache, fixture or Demo output. MiMo-preferred/TeamoRouter-secondary selection and actual provider/model are explicit before admission and locked for the Run.
- FMP is LIVE only after a successful current request with provider/scope/time/content-provenance hash. Raw → validation → normalization → conflict → acceptance remains visible.
- Langfuse is fail-open observability and truthfully reports healthy/degraded/unavailable/disabled. It is not business evidence and never receives secrets or hidden reasoning.
- RISC Zero is fail-closed for `MUST_PROVE`; cached verification is valid only for byte-identical fixed inputs/program/journal/commitments and is labelled accordingly.
- HTML is mandatory for release; PDF is optional and independent. Every byte GET repeats identity/state/integrity authorization; no raw path or bytes on failure.
- Presenter/Demo cannot be enabled by URL/query/local storage/runtime response/client flag in a production-default build.
- Startup does not infer a mode, install/build/pull, choose another port, mutate/reset/downgrade/stamp a database, delete volumes, kill unknown processes or repair failures.
- An activated release gate is PASS or FAIL. Skipped, blocked, missing, stale-only, qualified or incomplete evidence fails the release decision.

## System acceptance families

| Family | Required acceptance | Failure/recovery variants | Evidence / blocker |
|---|---|---|---|
| `SYS-01` Candidate/manifest | clean exact commit; canonical manifest; all source/build/lock/migration/image/RISC/fixture/browser/config hashes; two builds agree | dirty/missing input, lock drift, floating image, traversal, platform mismatch, nondeterminism | canonical digest, inventories, clean status, two-build comparison; any unidentified byte blocks |
| `SYS-02` Node 24/frontend | exact Node 24/npm patch, tracked lock, clean install/typecheck/tests/build, identical normalized `dist`, no Demo/Presenter | wrong runtime, lock drift, offline dependency miss, warning/error, mode mismatch, different hash | versions, lock/build hashes, asset/network/browser scan |
| `SYS-03` composition/cold start | explicit mode/config; PostgreSQL → one-shot migration → Backend readiness → artifact/RISC/sandbox → Frontend → smoke | unknown/conflicting mode, port collision, partial start, stale receipt, readiness timeout | preflight/start/health/listener ownership; no runtime install/build/pull/reset |
| `SYS-04` PostgreSQL durability | PG16, one repository/DB head, release volume; exact identities survive API/worker/DB/full restarts; restore writable | divergent head, interrupted transaction, corrupt backup, duplicate terminal/event | migration hashes, cardinalities, snapshots, backup/independent restore/new Run |
| `SYS-05` MiMo/Teamo policy | freeze MiMo preferred → TeamoRouter secondary; safe preflight; actual provider/model/policy persisted before admission | provider unavailable/timeout/429/5xx, invalid output, order permutation, wrapper drops identity, post-lock failure | safe classifications and attempt identity. Re-audit `llm_provider.py`, `llm_integration.py`, `service.py` for observed forwarding/order risks |
| `SYS-06` FMP truth | current authenticated FMP required for LIVE; Limited follows frozen cache policy; Offline has no client/secret | auth/entitlement/rate/no data/malformed/stale cache/network loss/fixture splice | sanitized provenance/hash/time/source labels; core evidence failure blocks Run |
| `SYS-07` Langfuse | healthy only when working; otherwise visible degraded/unavailable/disabled while business continues | init/runtime/flush/network/no-op/duplicate spans/canaries | safe local correlation/status/canary scan; any secret leak blocks |
| `SYS-08` RISC/sandbox | pinned toolchain/host/guest/image/input/output; independent verify; digest-pinned non-root/network-denied/read-only sandbox | mismatch/tamper/timeout/missing image/Docker loss/escape/orphan | manifest/verifier/tamper/proof/sandbox lifecycle; pending adapter is not release implementation |
| `SYS-09` artifacts | durable atomic store; O/R/L/report/A binding; immutable independent slots; integrity/authorization on every GET | full/interruption/tamper/swap/cross-owned/raw path/revoked reference/HTML/PDF failure | metadata/attempt/renderer/byte/render/restart evidence; HTML blocks, PDF never borrows success |
| `SYS-10` browser/product | manifested browser/Playwright; real HTTP/SSE; Scenes 01–04, FE 1–12, Core identity/recovery/accessibility; no Demo | cache/refresh/history/disconnect/restart/errors/unsupported browser/console/stale/mixed identity | trace/screenshots/DOM/a11y/network/console; all Core families and tombstone semantics |
| `SYS-11` Preview parity | same content-addressed build/contracts/migration/renderer/policy/artifacts; rerun Core/PJ/Scenes and activated deployment gates | drift, Preview repair, unapproved public exposure, mode/provider/storage difference | manifest/config/health/hash/rerun and independent parity report |
| `SYS-12` Presenter/Demo isolation | production unreachable; approved Demo is separate build/store/DB/browser with persistent watermark | query/storage enablement, shared data, hidden watermark, Demo accepted real | reachability/bundle/network/mutation scans; reservations 073..076/109..112 stay inactive |
| `SYS-13` network/service recovery | independent classifications and correct readiness/degradation; identity/mode preserved | DNS/timeout/reset/408/429/5xx, SSE disorder, component restarts, disk/browser offline | fault schedule, transitions, counts/timing, reconciliation; no storm/substitution/false health |
| `SYS-14` secrets | protected inputs only; check name/presence/pairing/permissions without value/hash/length; no frontend/sandbox credentials | canaries in key/log/trace/response/SSE/evidence/artifact/config | alias inventory, permissions, scans, redaction version, rotation; one occurrence blocks |
| `SYS-15` fresh machine | every advertised OS/arch/mode from clean bundle; Public and network-denied Offline mandatory; full cold/restart/restore/recovery | missing offline asset, unexpected egress, port owner, timeout, command drift, unrelated impact | FM-001..017, host/network/start/status/down/timing/browser/independent sign-off |

## Deployment-mode acceptance

| Component | Public | Limited | Offline Demo |
|---|---|---|---|
| PostgreSQL | exact durable head | same | same for integrated target |
| FMP | current authenticated fetch for LIVE | exact frozen live/cache/disabled policy; never fixture | no client/secret; manifested fixture only |
| LLM | ordered policy, actual selection before Run | only frozen providers/models | no invocation; deterministic/prebuilt and labelled |
| Langfuse | fail-open, truthful status | per policy | no external call; disabled |
| RISC | current-input proof where required | local exact proof; MUST_PROVE still blocks | exact fixed-input package or explicit policy |
| Sandbox | exact local digest, no pull | same if advertised | packaged only, no cloud generation |
| Frontend | production HTTP/SSE; no Demo | same | integrated backend plus persistent watermark |
| Artifacts | authorized generated HTML; PDF by availability | same | manifested artifacts with fixture disclosure |
| Runtime switch | forbidden | forbidden | forbidden |

Public failure never auto-selects Limited or Offline; the operator stops and starts a separate composition. Existing Runs are never converted.

## Cold start, restart and time budgets

Cold start: verify manifest/platform/runtime/offline assets → non-mutating explicit-mode preflight → acquire owned lock → start healthy PostgreSQL → approved forward migration and head equality → Backend readiness/components → artifact/RISC/sandbox assurance → prebuilt Frontend/mode alignment → static/API/SSE smoke → one mode-appropriate journey → sanitized receipt. Failure stops only resources created by that invocation, preserves volumes/evidence and returns failure.

Restart matrix covers Backend/worker at commit boundaries, PostgreSQL without volume recreation, full down/up, browser hard/new context, SSE pre-terminal/terminal, artifact write/promote, Langfuse loss, FMP/LLM before and after lock, and Docker/sandbox/RISC loss. PASS requires exact durable identities, no duplicate effect/event/terminal/artifact, stable mode/provider provenance, correct recovery UI, and a subsequent successful new Run. Shutdown stops only receipt-owned resources and never removes durable/evidence volumes.

Initial maximums: public preflight 180s; offline preflight 120s; cold start 180s; warm start 90s; readiness 15s; SSE recovery 10s; local artifact 30s; fixed proof verification 60s; prove+verify 120s; sandbox 180s; graceful shutdown 60s. Timeout is failure.

## IG-09 Preview parity

IG-09 requires IG-08 PASS; identical candidate identity; contract/migration/build/renderer/policy parity; all applicable Core/system/browser/Scene/Journey reruns; activated P4-E2E-099/100; provider/mode truthfulness; Demo isolation; secret scan; and independent Preview PASS. Only explicit hashed environment configuration may differ. Source/build/contract/migration/renderer/oracle change creates a new candidate. Preview stays private/trusted until a separate access-control profile is accepted.

## IG-10 release readiness

IG-10 requires IG-09 plus canonical manifest, reproducible Backend/Node24 Frontend, every advertised platform/mode fresh-machine PASS, cold/warm recovery, PostgreSQL backup/restore, provider/FMP truth, Langfuse fail-open/security, RISC/sandbox, HTML/PDF policy, browser/journeys, Demo isolation, operator recovery, complete evidence and independent release PASS. A failing mode/platform is removed from the advertised manifest and the new candidate is re-audited. READY does not mean DEPLOYED.

## Future controlled provider failover

```text
CONTROLLED_PROVIDER_FAILOVER_ACTIVATION=DEFINED_NOT_ACTIVATED
CONTROLLED_PROVIDER_FAILOVER_RESULT=null
CURRENT_PHASE4_POST_LOCK_PROVIDER_SWITCH=PROHIBITED
```

Future activation needs a separately frozen contract/event/UI/evidence delta and immutable `providerBefore`, `providerAfter`, `modelBefore`, `modelAfter`, `taskId`, `attemptId`, `failureReason`, `timestamp`, `policyId`. It must add a new attempt, preserve O/R/T and the failed attempt, expose the change in UI/evidence, forbid silent FMP/Review/Proof/financial-authority substitution, and pass restart/replay plus independent audit. Missing or invisible provenance fails the Run. This freezes no Phase 4 wire schema.

## Current blockers

UAC-001; unexecuted IG-07/08; existing deployment readiness failures; incomplete API composition/operator implementation; no clean release candidate/locks/offline bundle; provider identity/order pre-audit risks; unproved FMP/Langfuse/RISC/sandbox/artifact truth; no implemented real browser suite; inactive P4-E2E-099/100 and Presenter reservations; trusted-local access not public authorization; controlled failover inactive.

```text
SYSTEM_ACCEPTANCE_FAMILIES_DEFINED=15/15
PHASE4A_PHASE4B_BOUNDARY_DEFINED=YES
DEPLOYMENT_MODES_DEFINED=3/3
IG09_PREVIEW_PARITY_DEFINED=YES
IG10_PHASE4B_RELEASE_GATE_DEFINED=YES
COLD_START_DEFINED=YES
WARM_RESTART_DEFINED=YES
POSTGRESQL_DURABILITY_DEFINED=YES
NODE24_FRONTEND_REPRODUCIBILITY_DEFINED=YES
MIMO_PREFERRED_TEAMO_SECONDARY_DEFINED=YES
FMP_TRUTHFULNESS_DEFINED=YES
LANGFUSE_FAIL_OPEN_DEFINED=YES
RISC_FAIL_CLOSED_DEFINED=YES
ARTIFACT_ACCEPTANCE_DEFINED=YES
PRESENTER_ISOLATION_DEFINED=YES
DEMO_WATERMARKING_DEFINED=YES
CONTROLLED_PROVIDER_FAILOVER_DEFINED=YES
CONTROLLED_PROVIDER_FAILOVER_ACTIVATED=NO
INVISIBLE_PROVIDER_FAILOVER_ALLOWED=NO
PHASE4B_SYSTEM_RELEASE_PLAN_READY=YES
COMPETITION_RUNTIME_READY=NO
DEPLOYMENT_EXECUTED=NO
LIVE_PROVIDER_CALLS_EXECUTED=0
PRODUCTION_SOURCE_MODIFIED=NO
```
