# Repository publication safety review

[简体中文](PUBLICATION_SAFETY.zh-CN.md)

> Historical-record clarification — 2026-09-08: the CI/publication and open-decision statements below describe this earlier preparation audit and are retained unchanged. The Owner subsequently confirmed AIx Origin Summit Hong Kong · Flux Track · Bronze Award on 2026-09-08; see [recognition](../recognition/AIX_ORIGIN_SUMMIT.md). Current investors/testers are directed to BYOK with privately configured credentials; this record is not evidence of a deployed evaluator gateway or a completed live-user acceptance.

Scope: accepted baseline f783d2cfd07e7e99621a7c053c162ba77f82f7a1, current preparation tree, and all locally available Git refs/history. No remote mutation or history rewrite.

## Secret checks

- Scanned 4,082 text Git objects for provider-key patterns, JWTs, private-key markers, credential assignments and credential-bearing database URLs.
- Reviewed matches as placeholders, code expressions and explicit safety-test fixtures; no actual secret identified.
- A supplemental inline credential/query-assignment scan found only a domain type annotation after triage, not a literal credential.
- Exact-match checked four configured private provider/observability credential values against all reachable Git blobs (including binary content); zero matches. Values were never printed, copied or saved in an audit artifact.
- Current tracked dotenv inventory is .env.example only. Real .env.local/private authority files remain ignored and untracked.
- No new private runtime payloads, prompt/response dumps, production database, raw Alpha participant records or raw screenshot clutter are introduced.
- Existing tracked visual-comparison evidence remains historical evidence, not a live evaluator seed. New investor screenshots are the five approved final product frames only.

SECRET_HISTORY_BLOCKER = NO (no actual secret found by this scoped audit).
This is evidence of performed checks, not a mathematical guarantee of absence or an audit of remote refs unavailable locally. Credential validity was not tested through live provider calls.

## Portability / privacy

Removed the runtime MiMo developer-home default. Evaluators use their own Settings or an explicit private authority file. Historical helper scripts now use normal repository configuration rather than a fixed owner home directory. Archived engineering commands use a portable repository placeholder. Generic fake private-path strings in safety tests are intentional test inputs.

Only model IDs, public configuration base URLs and variable names belong in public examples. Access credentials remain BYOK or owner-issued out of band. Local artifacts and participant observations must be reviewed separately before any future addition.

## CI preparation

Minimal workflow: .github/workflows/local-contracts.yml. It requires no external secrets, PostgreSQL service, live FMP, live providers or proof execution. Installs require ordinary package registry access. Workflow payload was executed locally with Python 3.11 and Node 24.20.0; GitHub-hosted execution has not occurred (no push). CI_STATUS refers to local preparation validation, not a remote green check.

## Open owner decisions

No license chosen automatically. Award rank/official track spelling is not asserted without an authoritative certificate/announcement. Publication must preserve the qualified recognition wording unless evidence is supplied.
