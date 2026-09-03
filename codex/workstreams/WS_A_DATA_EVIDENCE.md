# WS-A — Data & Evidence

Ownership:
- `src/data/**`
- `src/adapters/fmp/**`
- evidence-specific tests

Read architecture decisions and data model first.

Implement:
- Provider interface
- Fixture provider
- FMP adapter boundary
- freshness
- validation
- normalization
- conflict detection
- AcceptedEvidenceBundle
- EvidenceRecord persistence

Do not:
- implement Agent planning
- implement scheduler
- calculate official financial metrics
- pass raw provider JSON directly to Agent

Tests:
- valid evidence
- missing fields
- period mismatch
- unit normalization
- rejected evidence
- deterministic fixture replay

Write `WORKSTREAM_REPORT_DATA.md`.
