# WS-B — Agentic Planning

Ownership:
- `src/agentic/**`
- agentic unit tests

Implement:
- SchemeGenerator interface + deterministic fallback
- ResearchLeadPlanner
- PlannedTaskGraph output
- Specialist agent interfaces
- Skill contract
- SelfCorrectionDecision
- ReplanRequest
- Agent / Skill registry
- structured decisions

Rules:
- Initial Plan First
- Specialist cannot mutate graph
- no hidden chain-of-thought storage
- no financial number generation in Agent code

Write `WORKSTREAM_REPORT_AGENTIC.md`.
