"""Closed, immutable Phase 5A research-asset contracts."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from src.phase4_product.contracts import FrozenWireModel
from src.phase4_product.safety import is_protected_key, safe_text


class MemoryModel(FrozenWireModel):
    @model_validator(mode="after")
    def public_safety(self):
        def visit(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if is_protected_key(key):
                        raise ValueError("protected memory field")
                    visit(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    visit(child)
            elif isinstance(value, str):
                safe_text(value, allow_empty=False, max_length=65536)

        visit(self.model_dump(mode="json"))
        return self


class MaterializeMemoryRequest(MemoryModel):
    source_run_id: str = Field(min_length=1, max_length=128)


class MemoryItem(MemoryModel):
    memory_item_id: str
    category: Literal["VERIFIED_METRIC", "VERIFIED_CLAIM", "RESOLVED_ISSUE"]
    source_run_id: str
    reference_id: str
    title: str
    statement: str
    display_value: str | None = None
    display_unit: str | None = None
    calculation_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    review_id: str
    report_id: str
    report_anchor: str | None = None
    task_id: str | None = None
    agent_output_id: str | None = None


class ResearchObjectVersion(MemoryModel):
    schema_version: Literal["phase5a-object-version/v1"] = "phase5a-object-version/v1"
    research_object_id: str
    object_version: int = Field(ge=1, strict=True)
    object_version_id: str
    source_run_id: str
    source_released_result_id: str
    source_report_id: str
    source_canonical_record_id: str
    created_at: datetime


class ResearchViewVersion(MemoryModel):
    schema_version: Literal["phase5a-view-version/v1"] = "phase5a-view-version/v1"
    research_object_id: str
    research_view_version: int = Field(ge=1, strict=True)
    research_view_version_id: str
    research_object_version: int = Field(ge=1, strict=True)
    source_run_id: str
    source_released_result_id: str
    source_report_id: str
    source_canonical_record_id: str
    as_of: str
    summary: str | None
    items: tuple[MemoryItem, ...]
    unavailable_categories: tuple[
        Literal["PEER_CONTEXT", "PATH_CONTEXT", "REUSABLE_CONTEXT"], ...
    ] = (
        "PEER_CONTEXT",
        "PATH_CONTEXT",
        "REUSABLE_CONTEXT",
    )
    created_at: datetime

    @model_validator(mode="after")
    def lineage(self):
        if len({i.memory_item_id for i in self.items}) != len(self.items):
            raise ValueError("duplicate memory identity")
        for item in self.items:
            if item.source_run_id != self.source_run_id or item.report_id != self.source_report_id:
                raise ValueError("foreign memory lineage")
        return self


class MemoryHistoryRef(MemoryModel):
    research_object_id: str
    source_run_id: str
    status: Literal["RELEASED"] = "RELEASED"
    as_of: str | None
    source_released_result_id: str | None
    research_view_version: int | None
    availability: Literal["AVAILABLE", "UNAVAILABLE_INCOMPATIBLE"]


class ResearchMemorySnapshot(MemoryModel):
    schema_version: Literal["phase5a-memory/v1"] = "phase5a-memory/v1"
    research_object_id: str
    latest_released_run_id: str | None
    latest_research_object_version: int | None
    latest_research_view_version: int | None
    object_version: ResearchObjectVersion | None
    current_view: ResearchViewVersion | None
    historical_released_runs: tuple[MemoryHistoryRef, ...] = ()

    @model_validator(mode="after")
    def closure(self):
        if any(
            h.research_object_id != self.research_object_id for h in self.historical_released_runs
        ) or len({h.source_run_id for h in self.historical_released_runs}) != len(
            self.historical_released_runs
        ):
            raise ValueError("foreign or duplicate memory history")
        values = (
            self.latest_released_run_id,
            self.latest_research_object_version,
            self.latest_research_view_version,
            self.object_version,
            self.current_view,
        )
        if all(v is None for v in values):
            return self
        if any(v is None for v in values):
            raise ValueError("incomplete memory pointer")
        obj, view = self.object_version, self.current_view
        if not (
            obj.research_object_id == view.research_object_id == self.research_object_id
            and obj.source_run_id == view.source_run_id == self.latest_released_run_id
            and obj.object_version
            == view.research_object_version
            == self.latest_research_object_version
            and view.research_view_version == self.latest_research_view_version
            and obj.source_released_result_id == view.source_released_result_id
            and obj.source_report_id == view.source_report_id
            and obj.source_canonical_record_id == view.source_canonical_record_id
        ):
            raise ValueError("memory version identity mismatch")
        return self
