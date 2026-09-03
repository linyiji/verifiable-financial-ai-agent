# 08 — Assurance, Langfuse & ZK V1

## 1. Control-plane principle

> Agent has autonomy over execution, not over assurance.

## 2. Financial Review

### Deterministic checks

- evidence accepted
- numeric consistency
- calculation status
- period consistency
- actual / estimate consistency
- unit / currency
- required field completeness
- report number / calculation consistency

### Semantic checks

- claim supported by evidence
- logic leap
- evidence conflict
- claim strength
- limitation disclosure
- judgment vs fact confusion

States:

```text
PASS
REVIEW
BLOCK
```

## 3. Review repair loop

```text
Review Finding
→ Correction Request
→ Original Task / Agent
→ Self-Correction
→ Resubmit
→ Review Again
```

If correction changes scope/dependencies → Replan.

## 4. Langfuse

Role:

> Technical observability / trace evidence.

Instrument:

- run
- planning
- agent generation
- skill
- tool
- financial code
- correction
- replan
- review
- proof adapter
- report render

Langfuse is not business source of truth.

Canonical Execution Record stores trace references.

## 5. Langfuse fail-open

Observability must not break research execution.

Implement:

- LangfuseTraceAdapter
- NoopTraceAdapter

No credentials → Noop.

## 6. ZK proof boundary

MVP recommended proof:

```text
Accepted evidence commitment
→ deterministic revenue growth program
→ numeric output commitment
→ receipt
→ verification
```

or final numeric consistency check.

Do not attempt to prove full LLM narrative.

## 7. ZK semantics

Can prove:

- known program executed
- committed input was used
- output / journal matches verified receipt

Cannot prove:

- provider data is objectively true
- investment thesis is objectively correct
- hallucinations are impossible

## 8. Release Gate

```text
Review required statuses satisfied
AND
all MUST_PROVE proofs valid
AND
no hard block
→ RELEASE
```
