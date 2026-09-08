# WS-U3 — Generated Capability Validation and Scoped Registry

## Result

Implemented the U1 validation and registry ports against the U2 Docker sandbox.
No frozen shared domain contract, enum, Settings, dependency, database, or
frontend file was changed.

The validation pipeline is fail-closed and ordered:

1. AST static validation and declared-import enforcement
2. trusted host syntax compilation without execution
3. generated unit tests in Docker
4. deterministic edge fixtures in Docker
5. trusted invariant execution
6. canonical deterministic double-run comparison
7. output schema validation
8. exact output-unit validation
9. normalized source/implementation SHA-256 binding and runtime metadata
10. trusted financial-policy validation

The validation record captures the Python runtime, normalized source hash,
implementation hash, capability version, formula ID, and validation schema
version. Any failure raises a stage-specific error and never emits a successful
handoff.

`ScopedCapabilityRegistry` resolves TASK, then RUN, then the existing global
Native registry. Generated registrations never mutate or promote into the
global registry.

`SandboxValidatedGeneratedCapability` executes every call through the Docker
backend and returns a `CalculationRecord` carrying implementation/source
provenance, evidence IDs, output unit, formula, capability version, Python
runtime, and schema version.

The Code Builder system contract now states the two required entrypoints, and
the Docker runner reports its actual CPython patch version in structured output.

## Verification

- Focused U1/U2/U3 plus real Docker suite: `69 passed`
- Full regression: `231 passed, 3 skipped` (the three existing real PostgreSQL
  tests require database settings not present in this isolated worktree)
- Ruff, compileall, and `git diff --check`: PASS

## Contract change request

None.
