"""Closed read-only Results references, including aggregate (empty-subject) checks."""

from copy import deepcopy

import pytest

from src.phase4_product.results_semantics import ResultsSemantics, compare


def package():
    selector = {
        "review_id": "REVIEW-A",
        "check_code": "FIN_CLAIM_SUPPORT",
        "subject_refs": ["CLAIM-A"],
    }
    return {
        "run_id": "RUN-A",
        "object_id": "OBJ-A",
        "company_name": "Example",
        "symbol": "EX",
        "as_of": "2026-09-09",
        "result_id": "RESULT-A",
        "review_id": "REVIEW-A",
        "review_status": "PASS",
        "publication": "RELEASED",
        "limitations": [],
        "recovery": None,
        "memory_refs": [],
        "html_artifact_id": "HTML-A",
        "legacy_export": False,
        "blocks": [
            {
                "claim_id": "CLAIM-A",
                "metric_id": "METRIC-A",
                "title": "Growth",
                "statement": "Reviewed statement",
                "calculation_id": "CALC-A",
                "evidence_refs": ["EVD-A"],
                "review_selectors": [selector],
                "execution_refs": ["EVENT-A"],
            }
        ],
        "checks": [
            {
                "selector": selector,
                "status": "PASS",
                "comparison": [],
                "execution_refs": ["EVENT-A"],
            }
        ],
        "records": [
            {
                "ref": ref,
                "category": category,
                "label": ref,
                "status": "PASS",
                "process": "Retained",
                "output": "0",
                "input_refs": [],
                "report_claim_refs": [],
            }
            for ref, category in (
                ("CALC-A", "Deterministic Code"),
                ("EVD-A", "Data Providers"),
                ("EVENT-A", "Runtime & Recovery"),
            )
        ],
    }


def test_closed_package_and_zero_comparison():
    assert ResultsSemantics.model_validate(package()).blocks[0].claim_id == "CLAIM-A"
    rows = compare({"value": 0, "tolerance": "0.0001"}, {"value": 0, "prompt": "private"})
    assert next(r for r in rows if r.field == "value").actual == "0"
    assert all(r.field != "prompt" for r in rows)


def test_failed_supporting_record_preserved_in_released_limited_package():
    data = package()
    data["publication"] = "RELEASED_WITH_LIMITATIONS"
    data["limitations"] = ["Supporting narrative unavailable after bounded recovery"]
    data["records"].append(
        {
            "ref": "TASK-SUPPORT",
            "category": "Runtime & Recovery",
            "label": "Supporting task",
            "status": "FAILED",
            "process": "Bounded recovery exhausted",
            "output": "Unavailable",
            "input_refs": [],
            "report_claim_refs": [],
        }
    )
    result = ResultsSemantics.model_validate(data)
    assert result.run_id == "RUN-A" and result.review_id == "REVIEW-A"
    assert result.records[-1].status == "FAILED"
    assert result.limitations and result.blocks[0].claim_id == "CLAIM-A"


def test_failed_required_package_cannot_expose_released_semantics():
    from types import SimpleNamespace

    from src.application.models import CompletedRunArtifacts
    from src.domain.enums import RunStatus
    from src.phase4_product.results_semantics import build_semantics

    aggregate = SimpleNamespace(
        run=SimpleNamespace(run_id="RUN-A", status=RunStatus.FAILED),
        artifacts=CompletedRunArtifacts(),
    )
    with pytest.raises(Exception, match="Semantic Results require an exact released Run"):
        build_semantics(aggregate, None, [], [], [], [])


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign_event",
        "foreign_evidence",
        "duplicate_record",
        "duplicate_check",
        "blocked_claim",
        "foreign_review",
        "invented_contribution",
        "foreign_input",
        "unknown_category",
        "missing_review",
    ],
)
def test_rejects_broken_reference_closure(mutation):
    p = deepcopy(package())
    if mutation == "foreign_event":
        p["blocks"][0]["execution_refs"] = ["EVENT-OTHER"]
    elif mutation == "foreign_evidence":
        p["blocks"][0]["evidence_refs"] = ["EVD-OTHER"]
    elif mutation == "duplicate_record":
        p["records"].append(p["records"][0])
    elif mutation == "duplicate_check":
        p["checks"].append(p["checks"][0])
    elif mutation == "blocked_claim":
        p["checks"][0]["status"] = "BLOCK"
    elif mutation == "foreign_review":
        p["checks"][0]["selector"]["review_id"] = "REVIEW-OTHER"
    elif mutation == "invented_contribution":
        p["records"][0]["report_claim_refs"] = ["CLAIM-OTHER"]
    elif mutation == "foreign_input":
        p["records"][0]["input_refs"] = ["CALC-OTHER"]
    elif mutation == "unknown_category":
        p["records"][0]["category"] = "Invented"
    elif mutation == "missing_review":
        p["blocks"][0]["review_selectors"] = []
    with pytest.raises(ValueError):
        ResultsSemantics.model_validate(p)


def test_empty_subject_is_valid_aggregate_selector():
    p = package()
    p["checks"].append(
        {
            "selector": {"review_id": "REVIEW-A", "check_code": "AGGREGATE", "subject_refs": []},
            "status": "PASS",
            "comparison": [],
            "execution_refs": [],
        }
    )
    assert len(ResultsSemantics.model_validate(p).checks) == 2
