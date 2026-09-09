# Recoverable execution and policy V1 — offline acceptance

[简体中文](RECOVERABLE_EXECUTION_AND_POLICY_V1_ACCEPTANCE.zh-CN.md) ·
[Architecture and integration boundaries](../architecture/RECOVERABLE_EXECUTION_AND_POLICY_V1.md) ·
[Versioned policy](../architecture/OWNER_POLICY_V1.md)

Date: 2026-09-09. Result: **PARTIAL / OFFLINE_IMPLEMENTATION**.
Baseline: `ea2002ca571c869c59936f64067ec0d7c7eaabd1`.
Branch: `codex/recoverable-execution-policy-v1`. Exact local candidate commit/tree
are recorded in the local FINAL_RECEIPT after committing; there is no publication.

## Measured gates

- Targeted new V1/FMP/policy gate: 148 parameterized cases passed. These overlap
  the full backend count; they are not 148 additional independent cases.
- Full backend: 1720 passed, 20 skipped, 0 failed. Two dependency deprecation warnings.
- Separate isolated PostgreSQL gate: 11 passed, including the three cases skipped
  by the full suite's default SQLite Settings, migration chain and real Memory repository.
  The other eight cases overlap the full suite. Union: 1723 passed test node IDs,
  17 unexecuted optional cases. These are test cases, not research executions.
- Frontend: all 21 existing/new `scripts/*.test.mjs` programs passed; their printed
  assertion counts are not aggregated as separate backend cases. TypeScript/Vite build passed.
- Ruff, changed Bash syntax/ShellCheck, new bilingual links, diff and bounded secret/path
  scan are final local gates. ShellCheck's existing SC2016 in install-evaluator.sh
  intentionally stores a literal future shell PATH statement; warning/error gate excludes info.
- Docker build-context fixture: COPY excluded fake credentials, `.env`, `.vfacred`,
  `.git`, node_modules, dist and artifacts; build RUN used `--network none`.

The 17 optional unexecuted cases comprise eight real RISC Zero receipt tests (real
Proof forbidden) and nine Docker-daemon Sandbox/generated-pipeline cases (no host
Docker socket exposed to test containers). Fake Proof/Sandbox, locked artifact/input,
installer and A/B/C regression cases remain in the passing full suite. This is **not**
a real Proof or real Sandbox isolation acceptance claim. Native PowerShell execution
is NOT_OBSERVED; Python/contract fixtures cover the Windows script contract only.

## Test isolation and reproduction

`scripts/recovery_v1_offline.py` creates a sanitized source snapshot: no plaintext
registry, real encrypted bundle, `.env`, database or original `.git` is copied.
The test container initializes its own Git index so static reviewed-artifact tests
inspect this source, not a developer checkout. Dependencies were installed in the
dedicated `tests/offline/Dockerfile.recovery-v1` image, not the running product.

Tests use Docker internal network `vfa-recovery-v1-offline`, no external default route,
no host ports, no Docker socket, capabilities dropped and no-new-privileges.
Only dedicated PostgreSQL16 database `recovery_v1_isolated` on host alias `postgres`
is reachable; data is in a new tmpfs container. Credentials are explicit fake literals.
Admission-only production-composition fixtures hold a cancellable fake HTTP boundary;
they do not fabricate successful financial/model results. No real provider is reached.

Inside that isolated test container, run targeted tests, then `python -m pytest -q`.
For the independent PostgreSQL gate set DATABASE_URL to the same explicit isolated
TEST_POSTGRESQL_URL and run `tests/postgresql/test_postgresql_runtime.py`,
`tests/postgresql/test_generated_artifact_migration.py`, and
`tests/recoverable_v1/test_resume_memory_postgresql.py`.
Frontend uses Node24, locked npm dependencies, the test-only TypeScript loader and
`npm run build`. Do not point these tests at an investor/developer database.

Migration0016 was applied only to this new test database. It adds the V1 ledger table;
no historical contract/budget/epoch is backfilled. Rollback disables V1 actions and
retains data, never destructive downgrade. Legacy missing contracts stay non-resumable.

## Corrections found by regression

Product defects repaired: endpoint403 credential poisoning; payload200 rate-limit
slot omission; explicit post-construction RecoveryBudget override precedence; semantic
compaction swallowing financial identities. The first C03 implementation over-retained
unrelated narrative and exceeded the existing bound; the production projection fixture
caught that regression and it was corrected, not waived by raising the bound.

Environment fixes: Node, Git and OpenTelemetry test dependencies; isolated PostgreSQL;
explicit fake provider configuration; sanitized Git index. Stale fixtures: migration
head0016, configured database/user instead of hard-coded developer identities, and an
admission-only producer barrier for exact sequential-read watermark assertions.
No test was deleted; Required/Review/Proof/Release guards were not lowered.

## What is and is not accepted

Offline evidence supports scoped FMP health, policy/doc parity, atomic physical
reservations, lease/epoch fencing, checkpoint v2, saved-result reconciliation,
Scheduler-based redelivery, one-shot failure authorization, and actual Memory repository
transaction guards. Unknown sent results block resending; this is not external exactly-once.
Model proposals require separate DECIDER authority and remain OFF. The existing
deterministic supervisor stays default. API/UI action components remain unmounted.

Production admission, dynamic-approval transaction integration, universal transport
wrapping, legacy projection bridging and startup scanner activation remain incomplete.
Those gaps are not closed by helper tests. No new runtime image is certified or published.
Pause, arbitrary branch redo, automatic evidence repair and recertification are deferred.

Historical Run305a: completed calculation event references are retained, but the exact
missing canonical calculation and branch requirement source are NOT_OBSERVED in its
saved projection. Causality remains **NOT_PROVEN**; the original FAILED state is unchanged.
Original audit files and their SHA256 inventory are preserved. Fixture-created Run IDs
are simulated test data, not Live; a total fixture-Run count is not aggregated.

REAL_PROVIDER_CALLS = 0; NEW_REAL_RESEARCH_RUNS = 0; REAL_PROOF_CALLS = 0;
KEYCHAIN_ACCESS = 0; CREDENTIAL_DECRYPTIONS = 0; PRODUCTION_MIGRATIONS = 0;
HISTORICAL_DATA_CHANGED = NO; PUSHED = NO.

Local evidence is under `artifacts/recoverable_execution_policy_v1/` (not public
credentials). Review readiness YES; separately authorized Live readiness NO;
production NOT_CERTIFIED; Phase6B NOT_DECIDED.

NEXT_EXACT_ACTION = OWNER_REVIEW_V1_AND_AUTHORIZE_BOUNDED_ACCEPTANCE.
Stop here; do not restore a historical Run, create a Live, publish or start Phase6B.
