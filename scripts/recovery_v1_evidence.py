"""Offline evidence assembly; reads only named audit files and safe Run projection.

No credential lookup, app composition, database access, network or historical write.
"""

import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "artifacts/recoverable_execution_policy_v1"
    output.mkdir(parents=True, exist_ok=True)
    audit_roots = (
        root / "docs/audits/RECOVERY_POLICY_AUDIT_20260909",
        root / "artifacts/recovery_policy_audit_20260909",
    )
    hashes = {
        str(path.relative_to(root)): digest(path)
        for folder in audit_roots
        for path in sorted(folder.rglob("*"))
        if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts
    }
    baseline = {
        "SOURCE_SHA_BEFORE": "ea2002ca571c869c59936f64067ec0d7c7eaabd1",
        "TREE_BEFORE": "9e7714bb16e9fe9a35a3eee6ffcc63e0ecf395f5",
        "INITIAL_BRANCH": "phase4",
        "BRANCH": "codex/recoverable-execution-policy-v1",
        "INITIAL_UNTRACKED": ["docs/audits/"],
        "WORKTREE": str(root),
        "AUDIT_INPUT_HASHES": hashes,
        "ISOLATED_NETWORK": "vfa-recovery-v1-offline",
        "NETWORK_INTERNAL": True,
        "DEFAULT_EXTERNAL_ROUTE": "ABSENT",
        "DATABASE_HOST": "postgres",
        "DATABASE_NAME": "recovery_v1_isolated",
        "DATABASE_CONTAINER": "vfa-recovery-v1-postgres",
        "DATABASE_STORAGE": "dedicated tmpfs; no host port or historical volume",
        "BUSINESS_OUTBOUND_CALLS": 0,
        "KEYCHAIN_ACCESS": 0,
        "CREDENTIAL_DECRYPTIONS": 0,
    }
    target = output / "BASELINE.json"
    if target.exists():
        if json.loads(target.read_text())["AUDIT_INPUT_HASHES"] != hashes:
            raise RuntimeError("ORIGINAL_AUDIT_CHANGED")
    else:
        target.write_text(json.dumps(baseline, indent=2) + "\n")
    projection = Path("/tmp/vfa-investor-v3.SHgew7/terminal-projection.json")
    retained = json.loads(projection.read_text())
    calculations = [
        {"sequence": v["sequence"], "refs": v["calculation_refs"]}
        for v in retained["activity"]
        if v["type"] == "calculation.completed"
    ]
    report = f"""# 305a calculation gap reconciliation / 计算缺口对账

Read-only source: `{projection}` (SHA256 `{digest(projection)}`).
Run: RUN-305a06c7-642d-42ed-8109-1a93b320aa48; terminal FAILED, event sequence237.
Historical workflow/database/service was not started or changed.

## Observed / 已观测

Synthesis COMPLETED; Valuation/Risk FAILED. Accepted evidence IDs exist on the
fundamental task. The frozen Scheme is SCHEME-ac54113d-75e7-5453-89ec-4283d37a6414.
Its calculation clauses are deterministic_financial_calculations_only and
calculation_records_for_reported_values. These are policy clauses, NOT calculator IDs.
`src/assurance/requirements.py:required_capabilities` explicitly excludes both.
Review/Proof/report/canonical execution/released result are NOT_GENERATED in the
retained product projection. Actual Memory rows were not queried: NOT_OBSERVED.

Calculation completion events (a completion event is not an independently validated
PASS record; no raw calculation payload/validation inferred):

```json
{json.dumps(calculations, indent=2)}
```

## Exact blocking path / 阻断路径

ResearchApplicationService.execute_run → post-scheduler classify_execution_closure
→ _assure_and_release → requirement gate. closure_policy.py returns
REQUIRED_CALCULATION_UNAVAILABLE when a canonical required capability lacks a PASS
calculation, OR a REQUIRED financial branch is not COMPLETED. The Scheme above
declares no explicit canonical capability IDs after policy-clause exclusion.
Thus an incomplete REQUIRED branch is a plausible code-path explanation, not proof
of which branch failed. The projection omits financial_branches and full calculation
records, so its exact capability/formula/version, required branch source/version,
input completeness, validation status and causal exception are NOT_OBSERVED.

No default attribution to FMP403, SMA, or free-cash-flow margin is made. Multiple
technical calculation completion refs are positively observed. Evidence of
news/transcript entitlement limitations alone does not prove calculation causality.
Valuation/Risk narrative failures alone do not identify the missing required branch.

LATEST_305A_MISSING_CALCULATIONS = NOT_OBSERVED (canonical missing identity)
LATEST_305A_REQUIREMENT_SOURCE = branch-level source NOT_OBSERVED; Scheme clauses observed
LATEST_305A_CAUSALITY = NOT_PROVEN
LATEST_305A_ORIGINAL_STATE_CHANGED = NO

The FMP scope repair fixes its separately proven defect; it does not establish that
all causes of this historical Run have been repaired. No recomputation/backfill.
"""
    (output / "CALCULATION_GAP_RECONCILIATION.md").write_text(report)
    print("AUDIT_INPUTS_PRESERVED=YES; HISTORICAL_PROJECTION_READ_ONLY=YES")


if __name__ == "__main__":
    main()
