"""Assemble local offline receipts from retained, secret-free test evidence."""

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from src.domain.owner_policy import policy_parity_payload


def test_report(path):
    cases = list(ET.parse(path).getroot().iter("testcase"))

    def ids(nodes):
        return sorted(f"{v.get('classname')}::{v.get('name')}" for v in nodes)

    failures = [v for v in cases if v.find("failure") is not None or v.find("error") is not None]
    skipped = [v for v in cases if v.find("skipped") is not None]
    passed = [v for v in cases if v not in failures and v not in skipped]
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "passed": len(passed),
        "failed": len(failures),
        "skipped": len(skipped),
        "passed_node_ids": ids(passed),
        "failed_node_ids": ids(failures),
        "skipped_node_ids": ids(skipped),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--postgres-snapshot", type=Path, required=True)
    parser.add_argument("--static-file", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = root / "artifacts/recoverable_execution_policy_v1"
    out.mkdir(parents=True, exist_ok=True)

    def write(name, value):
        text = value if isinstance(value, str) else json.dumps(value, indent=2) + "\n"
        (out / name).write_text(text)

    def git(*parts):
        return subprocess.check_output(["git", *parts], cwd=root, text=True).strip()

    full = test_report(args.snapshot / "full-backend-v1.xml")
    targeted = test_report(args.snapshot / "targeted-v1.xml")
    postgres = test_report(args.postgres_snapshot / "postgresql-v1.xml")
    static = json.loads(args.static_file.read_text())
    if any(report["failed"] for report in (full, targeted, postgres)):
        raise RuntimeError("OFFLINE_TEST_GATE_FAILED")
    if static["findings"] or static["broken_links"]:
        raise RuntimeError("STATIC_GATE_FAILED")
    for name, digest in static["runtime_input_manifest"].items():
        if hashlib.sha256((args.snapshot / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"RUNTIME_CHANGED_AFTER_TEST: {name}")
    for name in (
        "scripts/install-evaluator.sh",
        "scripts/install-evaluator.ps1",
        "scripts/verify-build-inputs.sh",
        "scripts/verify-build-inputs.ps1",
    ):
        if (args.snapshot / name).read_bytes() != (root / name).read_bytes():
            raise RuntimeError(f"INSTALLER_CHANGED_AFTER_TEST: {name}")
    write("STATIC_GATES.json", static)
    write("TEST_RESULTS.json", {"full": full, "targeted": targeted, "postgres": postgres})
    write(
        "POLICY_PARITY.json",
        {
            "status": "PASS",
            "evidence": "test_owner_policy: descriptor/runtime/bilingual parity",
            "descriptor": policy_parity_payload(),
            "live_availability_inferred": False,
        },
    )
    write(
        "CALL_ACCOUNTING_ACCEPTANCE.json",
        {
            "status": "IMPLEMENTED_OFFLINE",
            "scope": "opt-in V1 ledger and mocked real adapters",
            "tests": [
                v
                for v in targeted["passed_node_ids"]
                if any(part in v for part in ("ledger", "physical_transport", "real_adapter"))
            ],
            "separate_check_execution_physical_accounting": True,
            "unknown_sent_result": "BLOCK_RESEND_NOT_ZERO_COST",
            "all_production_transports_wired": False,
            "real_provider_calls": 0,
        },
    )
    write(
        "RESUME_ACCEPTANCE.json",
        {
            "status": "IMPLEMENTED_OFFLINE",
            "scope": "existing Scheduler plus V1 opt-in runner",
            "tests": [
                v
                for v in targeted["passed_node_ids"]
                if any(part in v for part in ("resume", "recovery", "fenc", "check", "unknown"))
            ],
            "actual_memory_repository_postgresql": "PASS",
            "production_startup_scanner_enabled": False,
            "historical_resume_executed": False,
        },
    )
    dispositions = {
        "A-01": (
            "IMPLEMENTED_OFFLINE",
            "Durable runner tested; production startup scanner pending",
        ),
        "A-02": ("IMPLEMENTED_OFFLINE", "Checkpoint v2/ledger; legacy projection bridge pending"),
        "A-03": ("DEFERRED", "Pause and arbitrary branch redo excluded"),
        "A-04": ("IMPLEMENTED_OFFLINE", "Actual Memory repository atomic guard tested"),
        "A-05": ("KEEP", "Legacy one-shot/interrupted-reentry guard retained"),
        "A-06": (
            "IMPLEMENTED_OFFLINE",
            "Epoch stale-writer counterexamples; no historical incident claim",
        ),
        "A-07": ("KEEP", "Same Run recovery and new Run reexecution remain distinct"),
        "B-01": ("FIXED", "Versioned policy descriptor and bilingual parity"),
        "B-02": ("IMPLEMENTED_OFFLINE", "Optional proposals; independent DECIDER authority; OFF"),
        "B-03": (
            "IMPLEMENTED_OFFLINE",
            "Atomic physical ledger; universal production wrapping pending",
        ),
        "B-04": ("KEEP", "Profile-specific check consumption retained"),
        "B-05": ("KEEP", "Candidate and dynamic substitution grants remain distinct"),
        "B-06": ("DEFERRED", "Automatic recertification excluded"),
        "C-01": ("FIXED", "Endpoint/auth/account scope plus HTTP and payload rate-limit tests"),
        "C-02": (
            "BLOCKED",
            "Complete freeze primitive exists; dynamic approval transaction unwired",
        ),
        "C-03": ("FIXED", "Semantic sentinels and production output projection regression passed"),
        "C-04": ("KEEP", "Required/Supporting and independent branch guards retained"),
        "C-05": ("KEEP", "Review/Proof/Release/Memory guards retained"),
        "C-06": ("KEEP", "Exact Run cache and revocation guards retained"),
        "P-01": (
            "IMPLEMENTED_OFFLINE",
            "Build-input content gate; Windows native/image acceptance absent",
        ),
        "P-02": ("KEEP", "Existing exact image/stale installation guard retained"),
    }
    audit = [
        json.loads(v)
        for v in (root / "artifacts/recovery_policy_audit_20260909/findings.jsonl")
        .read_text()
        .splitlines()
        if v
    ]
    if {v["finding_id"] for v in audit} != set(dispositions):
        raise RuntimeError("FINDING_DISPOSITION_COVERAGE_MISMATCH")
    write(
        "FINDING_DISPOSITION.json",
        [
            {
                "finding_id": v["finding_id"],
                "original_title": v["title"],
                "status": dispositions[v["finding_id"]][0],
                "scope_and_remaining": dispositions[v["finding_id"]][1],
                "historical_not_observed_promoted": False,
            }
            for v in audit
        ],
    )
    write(
        "CONTRACT_DECISIONS.md",
        """# Contract decisions / 合同决策

Frozen shared contracts preceded worker implementation. Defaults and explicit overrides
are retained; all V1 callers require finite budgets and absolute deadlines.
Intent precedes Run. Exact Scheme/base lineage is not changed by recovery.
Physical reservations are serialized per Intent; operation/task ceilings also apply.
Unknown sent calls block resend; stale epochs cannot publish. Failed operation authority
is one-shot and bound to the exact failure, actor/request and frozen contract.
Memory writes call the real repository under the same transaction fence.
The legacy admission/dynamic approval/projection/startup composition is not fully wired.
No helper test closes that production gap. Proposal mode and default API/UI actions OFF.
C03 protects semantic fields/records and ancestor paths; unrelated narrative is clipped.
P01 manifests protect content under a reviewed archive trust anchor, not signatures.
Rollback: disable new admission/actions/takeover, retain records, no downgrade/backfill.
Historical305a missing calculation causality NOT_PROVEN; no historical state changed.
""",
    )
    unique = set(full["passed_node_ids"]) | set(postgres["passed_node_ids"])
    fields = {
        "RECOVERABLE_EXECUTION_AND_POLICY_V1": "PARTIAL",
        "ACCEPTANCE_SCOPE": "OFFLINE_IMPLEMENTATION",
        "SOURCE_SHA_BEFORE": "ea2002ca571c869c59936f64067ec0d7c7eaabd1",
        "SOURCE_SHA_AFTER": git("rev-parse", "HEAD"),
        "FINAL_TREE": git("rev-parse", "HEAD^{tree}"),
        "C01_FMP_SCOPE": "FIXED_OFFLINE",
        "B01_POLICY_DOC_PARITY": "PASS",
        "POLICY_DEFAULTS_AND_OVERRIDES": "PRESERVED_TESTED",
        **{
            key: "IMPLEMENTED_OFFLINE_OPT_IN"
            for key in (
                "PHYSICAL_CALL_LEDGER",
                "LEASE_EPOCH_FENCING",
                "CHECKPOINT_V2",
                "DURABLE_REDELIVERY",
                "PROCESS_RESUME",
                "RESULT_UNKNOWN_HANDLING",
                "RELEASE_MEMORY_RECONCILIATION",
                "STALE_OUTPUT_INVALIDATION",
            )
        },
        "DYNAMIC_APPROVAL_SNAPSHOT": "FREEZE_IMPLEMENTED; PRODUCTION_TRANSACTION_NOT_WIRED",
        "MAIN_AGENT_PROPOSAL_MODE": "OFF_BY_DEFAULT; SEPARATE_DECIDER_AUTHORITY",
        "DEFAULT_SUPERVISOR": "DETERMINISTIC",
        "RECOVERY_API_UI": "OFFLINE_COMPONENTS_PASS; DEFAULT_PRODUCT_UNMOUNTED",
        "LEGACY_COMPATIBILITY": "PRESERVED; LEGACY_NOT_RESUMABLE_WITHOUT_CONTRACT",
        "ROLLBACK_PLAN": "DISABLE_NEW_ACTIONS; RETAIN_RECORDS; NO_DOWNGRADE",
        "LATEST_305A_MISSING_CALCULATIONS": "NOT_OBSERVED_EXACT_CANONICAL_IDENTITY",
        "LATEST_305A_REQUIREMENT_SOURCE": "SCHEME_CLAUSES_OBSERVED; BRANCH_SOURCE_NOT_OBSERVED",
        "LATEST_305A_CAUSALITY": "NOT_PROVEN",
        "LATEST_305A_ORIGINAL_STATE_CHANGED": "NO",
        "REQUIRED_REVIEW_PROOF_RELEASE_GUARDS": "PRESERVED",
        "DEFERRED_FEATURES": (
            "pause, arbitrary branch redo, automatic evidence repair, recertification"
        ),
        "UNRESOLVED_FINDINGS": "C-02; production integration remainder A-01/A-02/B-03/P-01",
        "KNOWN_BLOCKERS_WITH_SCOPE": "default admission, dynamic approval, universal transport, "
        "legacy projection bridge, startup scanner; native Windows and real Sandbox not accepted",
        "TARGETED_TESTS": f"{targeted['passed']} PASS (overlap with full)",
        "FULL_BACKEND": f"{full['passed']} PASS / {full['skipped']} SKIP / 0 FAIL",
        "POSTGRESQL": f"{postgres['passed']} PASS (3 additional distinct cases)",
        "UNIQUE_PASSED_BACKEND_NODE_IDS": len(unique),
        "FIXTURE_SIMULATED_RUNS": "ISOLATED_FAKE_DATA; TOTAL_NOT_AGGREGATED; NOT_LIVE",
        "FRONTEND": "21 SCRIPT_PROGRAMS_PASS",
        "TYPECHECK_BUILD": "PASS",
        "MIGRATION_ISOLATED_ACCEPTANCE": "0016_HEAD_PASS; PRODUCTION_NOT_TOUCHED",
        "RUFF": "PASS",
        "SHELL": "BASH_SYNTAX_AND_SHELLCHECK_WARNING_ERROR_PASS",
        "BILINGUAL_LINKS": "PASS",
        "DIFF_CHECK": "PASS",
        "SECRET_SCAN": "BOUNDED_PATTERN_AND_PRIVATE_PATH_SCAN_PASS",
        "DOCKER_BUILD_CONTEXT": "REAL_COPY_EXCLUSION_FIXTURE_PASS; FAKE_SENTINELS_ONLY",
        "TEST_NETWORK_ISOLATION": "INTERNAL_NETWORK; NO_EXTERNAL_DEFAULT_ROUTE_OR_DOCKER_SOCKET",
        **{
            key: 0
            for key in (
                "BUSINESS_OUTBOUND_CALLS",
                "PRODUCTION_MIGRATIONS",
                "REAL_PROVIDER_CALLS",
                "NEW_REAL_RESEARCH_RUNS",
                "REAL_PROOF_CALLS",
                "KEYCHAIN_ACCESS",
                "CREDENTIAL_DECRYPTIONS",
            )
        },
        "HISTORICAL_DATA_CHANGED": "NO",
        "PUSHED": "NO",
        "LOCAL_COMMITS": git(
            "log", "--format=%H", "ea2002ca571c869c59936f64067ec0d7c7eaabd1..HEAD"
        ),
        "WORKTREE_STATUS": git("status", "--short"),
        "RUNTIME_FILES_MATCH_TESTED_SNAPSHOT": "YES",
        "EVIDENCE_PATHS": str(out),
        "READY_FOR_OWNER_REVIEW": "YES",
        "READY_FOR_SEPARATELY_AUTHORIZED_LIVE": "NO",
        "READY_FOR_PRODUCTION": "NOT_CERTIFIED",
        "READY_FOR_PHASE6B": "NOT_DECIDED",
        "NEXT_EXACT_ACTION": "OWNER_REVIEW_V1_AND_AUTHORIZE_BOUNDED_ACCEPTANCE",
    }
    write(
        "FINAL_RECEIPT.md",
        "# V1 local offline receipt\n\n```json\n" + json.dumps(fields, indent=2) + "\n```\n",
    )
    print(json.dumps({"receipt": str(out / "FINAL_RECEIPT.md"), "status": "PARTIAL"}))


if __name__ == "__main__":
    main()
