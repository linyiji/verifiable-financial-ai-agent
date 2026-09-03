# WS-O Calculation Provenance Report

## Baseline and boundary

- Branch: `ws/calculation-provenance`
- Base: `5fade58` (`contracts: freeze phase 2.1 semantic hardening`)
- Runtime: Python 3.11.16
- Shared `CalculationRecord` fields were consumed without modification.
- No domain, contract, Settings, dependency, API entry-point, coordinator service, or parallel-status
  file was changed.
- `CONTRACT_CHANGE_REQUEST`: none.

## Delivered provenance

Both accepted native financial capabilities now populate all frozen implementation identity fields:

| Capability | Version | Formula | Source ref | Code hash |
| --- | --- | --- | --- | --- |
| Revenue Growth | `1.0.0` | `revenue_growth_v1` | `src.capabilities.financial.growth:RevenueGrowthCapability` | `sha256:f583ff894c388b8677bde486760ea14fc702278cfaa2229cb007221f1ba20765` |
| EBITDA Margin | `1.0.0` | `ebitda_margin_v1` | `src.capabilities.financial.profitability:EbitdaMarginCapability` | `sha256:135bc5ce8d95a0bc10dc1e7531c94c967fd93459d339d66b948f78400e6607c7` |

`runtime_version` is captured independently as `Python 3.11.16` in this environment.

The `code_hash` is SHA-256 over the exact capability module bytes. It therefore:

- is stable across repeated executions and filesystem locations;
- excludes run IDs, task IDs, calculation IDs, timestamps, financial inputs, outputs, and random
  values;
- changes when the implementation source bytes change;
- uses the `sha256:<64 lowercase hex>` identity format.

Evidence lineage is preserved unchanged in `input_evidence_ids` and
`input_values_snapshot`. No evidence is synthesized by the provenance helper.

## Coordinator-callable lineage linker

`link_calculation_lineage(calculations, review=..., canonical_record=...)` returns deep copies and
attaches the frozen `review_record_id` and `canonical_record_id` fields only after both target
records exist. It validates:

- Review, Canonical, and Calculation run ownership;
- Canonical references the Review;
- Canonical references every linked Calculation;
- Canonical retains every Calculation input Evidence ID;
- established lineage IDs cannot be replaced with different IDs.

Reapplying identical links is idempotent. Original Calculation objects remain unchanged, including
their evidence lineage. `proof_ref` remains null; this workstream does not claim or fabricate ZK.

Coordinator integration is intentionally deferred because `src/application/service.py` is outside
WS-O ownership. The expected wiring point is immediately after Canonical construction:

```python
aggregate.artifacts.calculations = link_calculation_lineage(
    aggregate.artifacts.calculations,
    review=review,
    canonical_record=record,
)
```

This copy assignment occurs before persistence/release output so downstream repositories serialize
the linked records.

## Verification

| Gate | Result |
| --- | --- |
| Provenance/linker module tests | **4 passed** |
| Full repository test suite | **128 passed, 1 skipped** |
| Ruff (`ruff check .`) | **pass** |
| Diff whitespace check | **pass** |
| Secret scan | **pass** |

The one full-suite skip is the pre-existing conditional live PostgreSQL test: the optional asyncpg
driver and PostgreSQL service are not present. It is unrelated to calculation provenance.

Tests prove source-byte determinism, change sensitivity, path independence, run/input independence,
the two exact native capability hashes, Calculation-to-Evidence preservation,
Calculation-to-Review/Canonical linking, immutable copy behavior, idempotence, conflict rejection,
and null `proof_ref` semantics.
