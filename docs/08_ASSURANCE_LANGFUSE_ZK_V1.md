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

### Phase 3 remediation: outbound credential redaction

`langfuse-otel-export-redaction-v1` preserves the Langfuse SDK's original
instrumentation-scope `public_key` until `LangfuseSpanProcessor` completes its
project-routing check. The adapter then clones completed spans at the processor's OTLP
exporter boundary, removes credential-shaped fields recursively, and redacts configured
credential values from scope, resource, span, event, link, status, provider, tool, and
embedded JSON payload surfaces. The delegate exporter and its authentication headers are
unchanged.

The existing Phase 3 `P3-INT-005` gate performs a post-flush Langfuse API read-back. The
acceptance-only drain barrier polls the exact trace on the bounded monotonic schedule
`0/2/5/10/20/40/60` seconds and fails closed unless the exact local and remote observation
identity sets converge by the 60-second deadline. It also requires one root trace and exact
Run/trace metadata closure. Every attempt retains its timestamp, elapsed time, counts, and
identity differences; final evidence retains the complete canonical expected and observed
identity collections. Trace payloads and configured credential values are never persisted.
Each of `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `FMP_API_KEY`, and
`TEAMOROUTER_API_KEY` must have zero occurrences. A missing/failed read-back fails the
acceptance gate without changing fail-open behavior for ordinary business execution.

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
