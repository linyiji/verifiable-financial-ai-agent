# WS-F — Canonical Record & Output

[简体中文](WS_F_OUTPUT_CANONICAL.zh-CN.md)

Ownership:
- `src/output/**`
- canonical execution domain model if foundation delegates it
- output tests

Implement:
- CanonicalExecutionRecord builder
- ReleasedResearchResult
- FinancialReviewView projection
- ExecutionDetails projection
- FinancialReport data model
- ObjectWritebackProposal

Test:
- B/C same canonical record id
- no recomputation from separate sources
- judgment/fact distinction preserved

Write `WORKSTREAM_REPORT_OUTPUT.md`.
