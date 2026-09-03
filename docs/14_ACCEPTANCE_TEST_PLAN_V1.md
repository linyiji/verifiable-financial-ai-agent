# 14 — Acceptance & Test Plan V1

## 1. Testing philosophy

Do not stop entire acceptance at first non-critical failure.

Complete as many independent checks as possible, aggregate defects, then repair and rerun.

## 2. Mandatory test layers

### Unit

- domain models
- enums
- graph dependency
- capability registry
- evidence validation
- financial formulas
- review rules
- self-correction
- replan decision
- event serialization

### Integration

- API + DB
- prepare scheme
- confirm run
- runtime scheduling
- SSE
- canonical record
- released result

### Financial

- known input → known result
- period alignment
- actual / forecast
- missing data
- zero denominator
- unit / currency

### Acceptance

End-to-end offline controlled flow.

## 3. Acceptance cases

| ID | Goal |
|---|---|
| AC-001 | Create Research Object |
| AC-002 | Object + Goal → AI/fallback Scheme |
| AC-003 | User confirms Scheme Snapshot |
| AC-004 | Create Research Run |
| AC-005 | Lead Planner generates Initial Planned Graph |
| AC-006 | Independent tasks run in parallel |
| AC-007 | Evidence gate blocks unaccepted data |
| AC-008 | Revenue Growth produced by deterministic Code |
| AC-009 | CalculationRecord links Evidence |
| AC-010 | Task performs Self-Correction without new top-level Task |
| AC-011 | Specialist emits Replan Request |
| AC-012 | Lead approves and Graph Mutation adds child Task |
| AC-013 | Capability Gap appears |
| AC-014 | Generated capability passes tests / task approval |
| AC-015 | Independent Review PASS / REVIEW / BLOCK works |
| AC-016 | Proof policy returns correct requirement |
| AC-017 | Real ZK proof in later phase verifies |
| AC-018 | Release Gate blocks invalid assurance |
| AC-019 | Canonical Execution Record generated |
| AC-020 | B/C projections share same record ID |
| AC-021 | Financial Report generated from released result |
| AC-022 | Object writeback respects Fact/Calc/Forecast/Judgment types |
| AC-023 | SSE can resume / replay ordered events |
| AC-024 | Langfuse failure does not break run |
| AC-025 | Run checkpoint can recover |
| AC-026 | Comparison gate rejects incompatible period/definition |

## 4. Phase 1 minimum acceptance

Must pass before Phase 2:

```text
Object
→ Goal
→ Scheme
→ Confirm
→ Run
→ Planned Graph
→ Parallel runtime
→ Evidence
→ Revenue Growth / Margin Code
→ Self-Correction
→ Replan
→ Review
→ Canonical Record
→ Released Result
```

Real ZK can remain `NOT_IMPLEMENTED` in Phase 1, but must never be faked.

## 5. Evidence of acceptance

Save:

- pytest output
- API test results
- run event log
- fixture hashes
- calculation outputs
- canonical record JSON
- final acceptance report
