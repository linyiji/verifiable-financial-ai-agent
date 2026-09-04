# Phase 3 Independent-Audit Remediation

This change set closes exactly four independent-audit findings in one new Phase 3
candidate. It does not alter or replace the rejected candidate, its authoritative
Run, or its audit evidence, and it does not authorize Phase 4.

## Canonical findings

- `PH3-REM-F1` — `GENERATED_CAPABILITY_PREIMAGE_RETENTION` (P1): retain the exact
  UTF-8 source and test preimages used by an accepted generated capability build,
  bind their hashes and sizes to the build record, and independently reconstruct
  the sandbox input. This strengthens the existing `P3-CAP-003`, `P3-CAP-004`,
  `P3-CAP-008`, and `P3-CAP-011` gates without creating a new gate namespace.
- `PH3-REM-F2` — `REVENUE_GROWTH_FORMULA_SEMANTICS` (P2): use
  `(current_revenue - prior_revenue) / prior_revenue`, require
  `prior_revenue > 0`, fail closed with a stable reason otherwise, and bind a new
  reproducible RISC Zero image and formal receipt to those semantics. This closes
  through the existing Phase 3 financial-semantics, review, and proof gates.
- `PH3-REM-F3` — `MACD_DECIMAL_CONTEXT_DETERMINISM` (P2): govern the complete MACD
  calculation with `macd-decimal-context-v1`, precision 28, and
  `ROUND_HALF_EVEN`; persist the policy metadata and prove identical results under
  ambient Decimal precisions 10, 28, and 50. This strengthens `FS-010` and the
  existing report/release gates.
- `PH3-REM-F4` — `LANGFUSE_PUBLIC_KEY_REDACTION` (P2): remove configured
  credentials at the final OTLP export boundary while retaining the Langfuse
  public key internally for authentication. Live trace read-back records only
  credential field names and occurrence counts and requires the exact exported
  observation set. This strengthens `P3-INT-005`.

## Persistence and historical evidence

Migration `20260904_0006` follows `20260904_0005` and is forward-only. It adds the
immutable, content-addressed generated source/test artifact store and build
bindings required by F1. F4 adds no database migration.

Rejected candidate `e02314c552d88fb736473bc587c650539615224a`, tree
`af74ec7e6bcf40d281c0a1ea5463c794d795718f`, Run
`RUN-a5e58911-9b0f-4848-90fe-a65f436fa9c2`, and Langfuse trace
`3ea5df8d0354816dbb9f35c56820353d` remain immutable failed-audit evidence. The
historical public-key occurrence is not described as clean, and no credential is
rotated solely because the exposed value was a Langfuse public key. Any discovery
of an actual secret in exported telemetry is a stop condition and security
incident.

The remediated candidate must pass the unchanged 52-gate formal Phase 3 matrix and
both internal financial-semantics and live integration closure. It then requires
new Backend Independent Final Audit and Financial Semantics Independent Final Audit
results against the same candidate and authoritative Run before it can become the
Approved Phase 3 Backend Parent.
