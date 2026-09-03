# Phase 2.1 Semantic Contract Gate

Baseline: `947496f482751493b97223d03ce2f85d2e6ddbfe`

Status: PASS

The Gate adds backward-compatible semantic fields only:

- Run-global Evidence ownership metadata and task-local evidence references.
- Explicit evidence acquisition outcomes without changing scheduler terminal-state semantics.
- Auditable graph edge event types.
- Calculation implementation/runtime and Review/Canonical lineage fields.
- Separate PeerCandidate and PeerSelectionDecision contracts.

Frozen rules remain unchanged: only accepted Evidence enters financial code; deterministic
financial numbers are code-produced; agents cannot bypass assurance; RISC Zero remains
`NOT_IMPLEMENTED`; Frontend remains `DEFERRED_PENDING_FINAL_UX_BASELINE`.

Shared files modified by this Gate are Coordinator-owned. Workstreams must consume them and submit
a `CONTRACT_CHANGE_REQUEST` instead of editing shared contracts.
