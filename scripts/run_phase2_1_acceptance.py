"""Run the real Phase-2.1 NVDA chain and evaluate semantic acceptance gates."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from scripts.run_phase2_acceptance import run as run_phase2
from src.capabilities.provenance import calculation_source_provenance
from src.domain.runtime_event import RuntimeEventType


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _event_sequence(events: list[dict[str, Any]], event_type: str, task_suffix: str) -> int:
    return next(
        int(event["sequence"])
        for event in events
        if event["type"] == event_type
        and str(event.get("task_id") or "").endswith(task_suffix)
    )


def _evaluate(output: Path, summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence = _read_json(output / "accepted_evidence.json")
    calculations = _read_json(output / "calculation_records.json")
    events = _read_json(output / "runtime_events.json")
    canonical = _read_json(output / "canonical_execution_record.json")
    released = _read_json(output / "released_research_result.json")
    task_outputs = _read_json(output / "task_outputs.json")
    tasks = {task["task_id"]: task for task in canonical["actual_graph"]["tasks"]}
    company_id = next(
        item["producer_task_id"]
        for item in evidence
        if item["evidence_category"] == "FINANCIAL_STATEMENT"
    )
    peer_id = next(
        (
            item["producer_task_id"]
            for item in evidence
            if item["evidence_category"] == "PEER"
        ),
        next(
            task_id
            for task_id, task in tasks.items()
            if task["task_type"] == "peer_analysis"
        ),
    )
    news_id = next(
        task_id
        for task_id, task in tasks.items()
        if task["evidence_acquisition_status"] == "ENTITLEMENT_BLOCKED"
    )
    news_analysis_id = next(
        task_id
        for task_id, task in tasks.items()
        if task["task_type"] == "research_news_analysis"
    )
    synthesis_id = next(
        task_id for task_id, task in tasks.items() if task["task_type"] == "report_synthesis"
    )
    follow_up_id = next(task_id for task_id in tasks if task_id.endswith(":risk-follow-up"))
    evidence_events = [
        event for event in events if event["type"] == RuntimeEventType.EVIDENCE_ACCEPTED.value
    ]
    event_evidence_ids = [str(event["payload"]["evidence_id"]) for event in evidence_events]
    evidence_by_id = {item["evidence_id"]: item for item in evidence}
    company_outputs = set(tasks[company_id]["task_output_evidence_ids"])
    peer_outputs = set(tasks[peer_id]["task_output_evidence_ids"])
    news_outputs = set(tasks[news_id]["task_output_evidence_ids"])
    peer_analysis_id = next(
        task_id for task_id, task in tasks.items() if task["task_type"] == "peer_analysis"
    )
    peer_output = task_outputs[peer_analysis_id]
    edge_events = [
        event
        for event in events
        if event["type"]
        in {
            RuntimeEventType.GRAPH_EDGE_ADDED.value,
            RuntimeEventType.GRAPH_EDGE_REMOVED.value,
        }
    ]
    hashes_reproducible = all(
        calculation_source_provenance(
            Path("src/capabilities/financial")
            / ("growth.py" if item["capability_id"] == "revenue_growth" else "profitability.py"),
            source_ref=item["source_ref"],
        ).code_hash
        == item["code_hash"]
        for item in calculations
    )
    scheme = summary["llm"]["scheme"]
    planner = summary["llm"]["planner"]
    gates = {
        "P2.1-001": (
            all(evidence_by_id[item]["producer_task_id"] == company_id for item in company_outputs)
            and all(evidence_by_id[item]["producer_task_id"] == peer_id for item in peer_outputs),
            "Evidence producer ownership matches scoped acquisition tasks.",
        ),
        "P2.1-002": (
            len(event_evidence_ids) == len(set(event_evidence_ids)) == len(evidence),
            "Accepted Evidence is emitted exactly once per run-global identity.",
        ),
        "P2.1-003": (
            tasks[news_id]["evidence_acquisition_status"] == "ENTITLEMENT_BLOCKED"
            and not news_outputs
            and task_outputs[news_analysis_id]["status"] == "entitlement_blocked"
            and not task_outputs[news_analysis_id]["accepted_evidence_ids"]
            and task_outputs[news_analysis_id]["limitation"] is True
            and "offline fixture" not in json.dumps(released).lower(),
            "Entitlement-blocked News propagates as an explicit analysis/release limitation.",
        ),
        "P2.1-004": (
            follow_up_id in tasks[synthesis_id]["dependencies"]
            and tasks[follow_up_id]["parent_task_id"]
            not in tasks[synthesis_id]["dependencies"]
            and not any(
                event["type"] == RuntimeEventType.GRAPH_EDGE_ADDED.value
                and event["payload"].get("predecessor_task_id")
                == tasks[follow_up_id]["parent_task_id"]
                and event["payload"].get("successor_task_id") == synthesis_id
                for event in edge_events
            ),
            "Mandatory follow-up replaces the direct Risk-to-Synthesis dependency.",
        ),
        "P2.1-005": (
            _event_sequence(events, RuntimeEventType.TASK_COMPLETED.value, ":risk-follow-up")
            < _event_sequence(
                events,
                RuntimeEventType.TASK_STARTED.value,
                synthesis_id.split(":")[-1],
            ),
            "Synthesis starts only after the mandatory follow-up completes.",
        ),
        "P2.1-006": (
            summary["actual_graph_version"] > 1 and len(edge_events) >= 3,
            "Graph version and edge add/remove events are auditable.",
        ),
        "P2.1-007": (
            all(item["code_hash"] for item in calculations),
            "All deterministic CalculationRecords carry code hashes.",
        ),
        "P2.1-008": (
            hashes_reproducible,
            "Recorded hashes reproduce from the checked-in capability source bytes.",
        ),
        "P2.1-009": (
            all(item["review_record_id"] and item["canonical_record_id"] for item in calculations),
            "Calculation lineage reaches Review and Canonical records.",
        ),
        "P2.1-010": (
            scheme["structured_validation"] == "PASS"
            and scheme["failure_classification"] is None
            and not scheme["preflight_failure"],
            "Scheme route reports a validated real-provider result.",
        ),
        "P2.1-011": (
            bool(scheme["attempted_models"])
            and scheme["actual_model"] in scheme["attempted_models"]
            and planner["structured_validation"] == "PASS"
            and not planner["deterministic_fallback"]
            and bool(planner["attempted_models"])
            and planner["actual_model"] in planner["attempted_models"],
            "Scheme and real Planner audits contain their actual model attempts.",
        ),
        "P2.1-012": (
            bool(peer_output["candidates"])
            and len(peer_output["candidates"])
            == len(peer_output["selection_decisions"])
            and all(
                selected["candidate_symbol"]
                in {
                    decision["candidate_symbol"]
                    for decision in peer_output["selection_decisions"]
                    if decision["selected"]
                }
                for selected in peer_output["selected_comparables"]
            ),
            "Peer candidates, decisions, and selected comparables remain separate.",
        ),
        "P2.1-013": (
            all(
                item["unit"] == "COUNT"
                for item in evidence
                if item["normalized_field"] == "full_time_employees"
            ),
            "Employee headcount normalization uses COUNT.",
        ),
    }
    return {
        gate: {"status": "PASS" if passed else "FAIL", "evidence": detail}
        for gate, (passed, detail) in gates.items()
    }


async def run(output: Path) -> dict[str, Any]:
    summary = await run_phase2(output)
    acceptance = _evaluate(output, summary)
    failed = [gate for gate, result in acceptance.items() if result["status"] != "PASS"]
    report = {"summary": summary, "acceptance": acceptance, "failed": failed}
    _write_json(output / "phase2_1_acceptance.json", report)
    if failed:
        raise RuntimeError(f"Phase-2.1 semantic gates failed: {failed}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase2_1/acceptance/latest"),
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.output)), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
