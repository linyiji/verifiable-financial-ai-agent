# Phase 2.1 Parallel Execution Status

Updated: 2026-09-04 (Asia/Shanghai)

| WS | Worker | Branch | Worktree | Status | Tests | Blocker |
|---|---|---|---|---|---|---|
| Contract Gate | Coordinator | `main` | `/Users/mac/Verifiable_Financial_Agent_System` | PASS | 124 passed; 1 expected skip; Ruff PASS | none |
| M Evidence Ownership | Franklin | `ws/evidence-semantics` | `/Users/mac/Verifiable_Financial_Agent_System_worktrees/evidence-semantics` | MERGED | 4 focused; 128 branch full; Coordinator semantic integration PASS; Ruff/secret PASS | none |
| N Replan Integrity | Harvey | `ws/replan-integrity` | `/Users/mac/Verifiable_Financial_Agent_System_worktrees/replan-integrity` | MERGED | 17 focused; 130 branch full; Ruff/secret PASS | durable external UoW deferred |
| O Calculation Provenance | McClintock | `ws/calculation-provenance` | `/Users/mac/Verifiable_Financial_Agent_System_worktrees/calculation-provenance` | MERGED | 4 focused; 128 branch full; Ruff/secret PASS | none |
| P Scheme Route Repair | McClintock | `ws/scheme-route-repair` | `/Users/mac/Verifiable_Financial_Agent_System_worktrees/scheme-route-repair` | RUNNING | pending | none |
| Q Peer/Data Semantics | Harvey | `ws/peer-data-semantics` | `/Users/mac/Verifiable_Financial_Agent_System_worktrees/peer-data-semantics` | MERGED | 19 focused; 129 branch full; Coordinator integration PASS; Ruff/format/secret PASS | live peer enrichment remains a known gap |

Frontend, RISC Zero, and Generated Capability Sandbox remain out of scope.
