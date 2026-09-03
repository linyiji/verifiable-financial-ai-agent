# Infrastructure Real-Integration Parallel Status

Updated: 2026-09-04 (Asia/Shanghai)

| WS | Worker | Branch | Worktree | Status | Tests | Blocker |
|---|---|---|---|---|---|---|
| Infra Gate | Coordinator | `main` | `/Users/mac/Verifiable_Financial_Agent_System` | PASS | container/config/runtime read-only gate PASS | none |
| R PostgreSQL Real Integration | Harvey | `ws/postgresql-real-integration` | `/Users/mac/Verifiable_Financial_Agent_System_worktrees/postgresql-real-integration` | MERGED | PostgreSQL 16.15; 9 real tests; INFRA-001..007 PASS | transactional outbox/UoW deferred |
| S Langfuse Real Integration | McClintock | `ws/langfuse-real-integration` | `/Users/mac/Verifiable_Financial_Agent_System_worktrees/langfuse-real-integration` | MERGED | Japan smoke CONNECTED; native generation/fail-open tests PASS | none |
| Phase 2.1 Semantic Hardening | Coordinator | `main` | `/Users/mac/Verifiable_Financial_Agent_System` | PASS | P2.1-001..015 PASS; full regression 159 passed | none |
| Unified NVDA Real Run | Coordinator | `main` | `/Users/mac/Verifiable_Financial_Agent_System` | PASS | RELEASED; 120 DB events; restart/SSE PASS; one trace/57 refs | FMP News/Transcript entitlement explicitly limited |
| T0 FinRobot Runtime Reuse Audit | Coordinator | `main` | `/Users/mac/Verifiable_Financial_Agent_System` | PASS | pin/runtime paths/9 adapter tests verified | no FinRobot module currently ACTIVE_REUSE |

Frontend, Generated Capability, RISC Zero, POT, and Comparison remain out of scope.
