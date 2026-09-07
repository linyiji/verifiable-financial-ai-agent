from copy import deepcopy
from datetime import date
from types import SimpleNamespace as N

import pytest

from src.phase4_product.errors import ProductError
from src.phase4_product.memory import build_memory_versions


def source():
    root = dict(run_id="RUN-A", object_id="OBJ-A", released_result_id="RESULT-A")
    p = N(
        run=N(
            status="RELEASED", run_id="RUN-A", research_object_id="OBJ-A", as_of=date(2026, 9, 6)
        ),
        object=N(object_id="OBJ-A"),
        terminal=N(is_terminal=True),
        result=N(canonical_record_id="CER-A"),
        path_changes=[],
    )
    metric = N(
        run_id="RUN-A",
        metric_id="METRIC-A",
        calculation_id="CALC-A",
        evidence_refs=["EVD-A"],
        claim_refs=["CLAIM-A"],
        name="Revenue",
        display_value="65.47",
        display_unit="%",
        period="FY2026",
        proof=N(status="VERIFIED", proof_refs=["PROOF-A"]),
    )
    claim = N(
        run_id="RUN-A",
        claim_id="CLAIM-A",
        metric_id="METRIC-A",
        calculation_refs=["CALC-A"],
        evidence_refs=["EVD-A"],
        statement="Revenue increased 65.47%",
    )
    r = N(
        **root,
        canonical_record_id="CER-A",
        metrics=[metric],
        claims=[claim],
        availability=N(status="AVAILABLE"),
    )
    report = N(
        **root,
        canonical_execution_record_id="CER-A",
        report_id="REPORT-A",
        artifact_id="HTML-A",
        anchors=[],
        source_contributions=[],
    )
    review = N(**root, canonical_execution_record_id="CER-A", review_id="REVIEW-A", verdict="PASS")
    execution = N(**root, canonical_execution_record_id="CER-A", actor_details=[])
    return [p, r, report, review, execution]


def test_released_verified_subset():
    data = source()
    obj, view = build_memory_versions("OBJ-A", "RUN-A", *data)
    assert [i.category for i in view.items] == ["VERIFIED_METRIC", "VERIFIED_CLAIM"]
    assert all(i.source_run_id == "RUN-A" for i in view.items)
    data[1].metrics[0].proof.status = "NOT_REQUIRED"
    assert build_memory_versions("OBJ-A", "RUN-A", *data)[1].items == ()
    assert obj.source_released_result_id == "RESULT-A"


@pytest.mark.parametrize("status", ["RUNNING", "REVIEW", "PROOF", "FAILED", "CANCELLED"])
def test_nonrelease_rejected(status):
    data = source()
    data[0].run.status = status
    with pytest.raises(ProductError):
        build_memory_versions("OBJ-A", "RUN-A", *data)


@pytest.mark.parametrize("position", range(1, 5))
def test_foreign_surface(position):
    data = source()
    data[position].run_id = "RUN-B"
    with pytest.raises(ProductError):
        build_memory_versions("OBJ-A", "RUN-A", *data)


@pytest.mark.parametrize("field", ["run_id", "metric_id", "calculation_refs", "evidence_refs"])
def test_foreign_claim_ref(field):
    data = source()
    setattr(data[1].claims[0], field, "FOREIGN" if field.endswith("id") else ["FOREIGN"])
    with pytest.raises(ProductError):
        build_memory_versions("OBJ-A", "RUN-A", *data)


def test_cross_object_and_incomplete_release():
    with pytest.raises(ProductError):
        build_memory_versions("OBJ-B", "RUN-A", *source())
    data = source()
    data[0].result.canonical_record_id = None
    with pytest.raises(ProductError):
        build_memory_versions("OBJ-A", "RUN-A", *data)


def test_source_not_mutated():
    data = source()
    before = deepcopy(data)
    build_memory_versions("OBJ-A", "RUN-A", *data)
    assert data == before
