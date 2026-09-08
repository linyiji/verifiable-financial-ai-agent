# WS-G — Integration

[简体中文](WS_G_INTEGRATION.zh-CN.md)

Ownership:
- `src/application/**`
- API orchestration
- integration tests
- acceptance tests

Prerequisite:
All workstreams A–F merged and module gates passed.

Integrate:

```text
POST object
→ prepare run
→ scheme generation
→ confirm
→ planner
→ runtime
→ parallel tasks
→ evidence
→ deterministic calculations
→ self-correction
→ replan child task
→ review
→ canonical record
→ released result
→ SSE complete
```

Do not bypass modules by duplicating logic in API routes.

Run full integration and acceptance suite.

Write `WORKSTREAM_REPORT_INTEGRATION.md`.
