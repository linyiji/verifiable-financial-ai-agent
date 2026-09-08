# Product acceptance

[简体中文](PRODUCT_ACCEPTANCE.zh-CN.md)

Accepted local closure: 2026-09-08, source f783d2cfd07e7e99621a7c053c162ba77f82f7a1. This is a technical acceptance record, not a user-adoption claim.

- Real PostgreSQL/React journey covered Object V2, current view, memories, compare, history, R5 Plan/research/A/B/C, correction/recovery, exact source navigation, refresh, back/forward and close/reopen.
- All 48 public production tables had equal counts/content hashes before browser navigation, after navigation and after screenshot interactions. Projection cache included; zero table mutations.
- No new Run, provider/model call, mutation POST or projection commit during acceptance.
- 221 backend cases and 242 frontend script checks passed; typecheck/build passed.
- Five public-facing selected images are unmodified copies of approved final screenshots. [Provenance](../product/screenshots/PROVENANCE.md).

Authoritative milestone history preserved: released initial knowledge base, three failed attempts, later released current research; Memory v1/v2 unchanged. Historical database and raw evidence remain private/local, not distributed as a product seed.

Known limitations: report source/contribution coverage PARTIAL, complete Claim Trace drawer unavailable, deferred PDF unavailable, unobserved memory categories not invented.

This repository preparation adds BYOK authority configuration tests and repeats focused regression without paid execution. It does not recertify a fresh live provider run. [Deployment boundary](LOCAL_DEPLOYMENT_ACCEPTANCE.md).
