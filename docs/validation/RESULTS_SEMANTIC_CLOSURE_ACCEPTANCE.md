# Phase 6A Results semantic closure — offline acceptance

[简体中文](RESULTS_SEMANTIC_CLOSURE_ACCEPTANCE.zh-CN.md) · [Contract](../architecture/RESULTS_WORKSPACE_CONTRACT.md)

Date: 2026-09-09. W2 PASS; W3 historical read-only projection PASS; offline regression PASS.
This is not live NVDA, investor publication, fresh-download or Phase 6B acceptance.

## Observed acceptance

- Historical Run: `RUN-75daae15-9f35-4233-83ff-6d24f2e151ba`, Object `OBJ-NVDA`.
- 10 reviewed claims, 62 original PASS checks, 1,229 exact execution records in eight categories.
- Original FAILED history and Owner-authorized Release recovery remain visible; new model,
  calculation and Proof counters are zero. Final state is RELEASED with research limitations.
- A→B→C and C→A exact-reference navigation passed. Unknown references fail closed.
- Eight in-memory negative cases rejected changed claim text, duplicate calculations/events,
  wrong-task events, changed Review/Evidence/Scheme and nonzero recovery counters.
- PostgreSQL enforced read-only. Before/after aggregate, event, recovery and Memory hashes
  matched; retained Proof manifest and original HTML content hash verified unchanged.
- Six historical GET surfaces and retained HTML download returned HTTP 200. New HTML/PDF
  rendering retained the same 10 typed claims without publishing unreviewed Agent narratives.
- Ten real 1440×900 screenshots were captured and visually inspected. No screenshot content
  injection, Provider calls, new research Runs or historical artifact rewrites occurred.

## Offline regression

Backend command: `TEST_POSTGRESQL_URL=<isolated-test-db> .venv/bin/pytest tests/unit tests/integration tests/phase4/backend_product tests/installer tests/evaluator tests/test_phase3_acceptance_runner.py -q --disable-warnings`

Result: **1,399 passed**, one warning. Frontend M3/M4/M5/M6: 119 checks passed;
new `node --experimental-strip-types scripts/results-semantic.test.mjs`: 14 checks passed.
TypeScript/Vite build, Docker installer image build, Ruff and `git diff --check` passed.
Repository Markdown local-link scan: 464 targets, zero unresolved before adding this receipt;
new receipt and counterpart links were subsequently checked. Exact local credential-value
scan found no exposure in tracked/untracked publishable files or built frontend assets.

## Historical external gate (superseded)

Web Search = CONFIGURED + LIVE_PROVEN; additional Web calls = 0.
AI Search = CONFIGURED + LIVE_HEALTH_UNPROVEN/403. Original body unavailable;
root cause NOT_PROVEN. One AI-only smoke is authorized after Owner external account
access/balance/config confirmation and correction; additional AI calls remain 0.
Do not claim invalid credentials without evidence or advertise healthy AI Search.

Next exact action: `BOCHA_AI_ACCESS_FIX`. Local paid NVDA Runs = 0. GitHub publication,
encrypted registry handoff and fresh-download live acceptance remain unperformed.

## Current Owner-approved Alpha scope

The historical AI access gate above is removed. Bocha Web Search is the supported
Bocha capability in this Alpha (`https://api.bocha.cn/v1/web-search`). No other Bocha
capability or credential is included in the active registry or investor bundle.
FMP uses **four distinct keys**, explicitly approved by Owner; five keys are not
required for this acceptance. Existing bounded credential-pool policies remain unchanged.
MiMo `mimo-v2.5` and TeamoRouter Sol/Luna/Terra retain their task-scoped policies.
