"""Read-only DB fingerprint of immutable R1/v1 plus Run-budget inventory."""

import json
import subprocess

RUN = "RUN-57aed683-75d6-4b47-acc6-a73053ea492e"


def query(sql):
    return subprocess.check_output(
        [
            "docker",
            "exec",
            "verifiable-financial-postgres",
            "psql",
            "-U",
            "vfa",
            "-d",
            "verifiable_financial_agent",
            "-At",
            "-c",
            sql,
        ],
        text=True,
    ).strip()


def fingerprint(table, condition):
    return json.loads(
        query(
            f"SELECT json_build_object('count',count(*),'md5',"
            "md5(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text))) "
            f"FROM {table} t WHERE {condition}"
        )
    )


tables = (
    "research_runs",
    "runtime_events",
    "evidence_records",
    "calculation_records",
    "review_records",
    "proof_records",
    "proof_verification_records",
    "canonical_execution_records",
    "released_research_results",
    "report_artifact_records",
    "correction_records",
    "replan_records",
)
values = {table: fingerprint(table, f"run_id='{RUN}'") for table in tables}
for table in ("research_object_versions", "research_view_versions"):
    values[table] = fingerprint(table, "object_id='OBJ-NVDA' AND version=1")
values["run_ids"] = json.loads(query("SELECT json_agg(run_id ORDER BY run_id) FROM research_runs"))
print(json.dumps(values, sort_keys=True))
