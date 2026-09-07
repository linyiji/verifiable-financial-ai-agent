from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.phase4_product.memory_contracts import (
    MaterializeMemoryRequest,
    MemoryItem,
    ResearchMemorySnapshot,
    ResearchObjectVersion,
    ResearchViewVersion,
)


def versions():
    identity = dict(
        research_object_id="OBJ-A",
        source_run_id="RUN-A",
        source_released_result_id="RESULT-A",
        source_report_id="REPORT-A",
        source_canonical_record_id="CER-A",
        created_at=datetime.now(UTC),
    )
    obj = ResearchObjectVersion(**identity, object_version=1, object_version_id="ROV-A")
    item = MemoryItem(
        memory_item_id="MI-A",
        category="VERIFIED_CLAIM",
        source_run_id="RUN-A",
        reference_id="CLAIM-A",
        title="Revenue",
        statement="Revenue increased",
        review_id="REVIEW-A",
        report_id="REPORT-A",
    )
    view = ResearchViewVersion(
        **identity,
        research_view_version=1,
        research_view_version_id="RVV-A",
        research_object_version=1,
        as_of="2026-09-06",
        summary=item.statement,
        items=(item,),
    )
    return obj, view


def test_valid_and_empty_pointer():
    obj, view = versions()
    ResearchMemorySnapshot(
        research_object_id="OBJ-A",
        latest_released_run_id="RUN-A",
        latest_research_object_version=1,
        latest_research_view_version=1,
        object_version=obj,
        current_view=view,
    )
    ResearchMemorySnapshot(
        research_object_id="OBJ-A",
        latest_released_run_id=None,
        latest_research_object_version=None,
        latest_research_view_version=None,
        object_version=None,
        current_view=None,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("research_object_id", "OBJ-B"),
        ("latest_released_run_id", "RUN-B"),
        ("latest_research_object_version", 2),
        ("latest_research_view_version", 2),
        ("current_view", None),
    ],
)
def test_pointer_identity_rejected(field, value):
    obj, view = versions()
    data = dict(
        research_object_id="OBJ-A",
        latest_released_run_id="RUN-A",
        latest_research_object_version=1,
        latest_research_view_version=1,
        object_version=obj,
        current_view=view,
    )
    data[field] = value
    with pytest.raises(ValidationError):
        ResearchMemorySnapshot(**data)


@pytest.mark.parametrize("index", [0, 1])
def test_versions_frozen(index):
    with pytest.raises(ValidationError):
        versions()[index].source_run_id = "RUN-B"


@pytest.mark.parametrize("mutation", ["foreign", "duplicate", "unsafe", "extra"])
def test_item_integrity(mutation):
    _, view = versions()
    data = view.model_dump()
    if mutation == "foreign":
        data["items"][0]["source_run_id"] = "RUN-B"
    if mutation == "duplicate":
        data["items"] = (*data["items"], data["items"][0])
    if mutation == "unsafe":
        data["items"][0]["statement"] = "/Users/private/secret.txt"
    if mutation == "extra":
        data["items"][0]["chain_of_thought"] = "private"
    with pytest.raises(ValueError):
        ResearchViewVersion.model_validate(data)


def test_request_closed():
    with pytest.raises(ValidationError):
        MaterializeMemoryRequest(source_run_id="RUN-A", ticker="NVDA")
