"""Exact, versioned values for the bounded fixed-graph execution path.

These values grant no execution authority without the Application repository's
fresh transaction. Audit time, delivery leases and provider retries are not versions.
"""

import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA = "wp02-node-binding/v1"


class BindingDenied(ValueError):
    retryable = False

    def __init__(self, code: str, subject: str = ""):
        self.code, self.subject = code, subject
        super().__init__(f"{code}: {subject}")


def canonical_value(value):
    """Closed JSON adapter; never stringifies unknown objects or non-finite values."""
    if isinstance(value, Enum):
        return canonical_value(value.value)
    if isinstance(value, BaseModel):
        return canonical_value(value.model_dump(mode="python"))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise BindingDenied("IDENTITY_MISMATCH", "non-finite decimal")
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, (tuple, list)):
        return [canonical_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: canonical_value(item) for key, item in value.items()}
    raise BindingDenied("IDENTITY_MISMATCH", f"noncanonical {type(value).__name__}")


def digest(value, tag: str = SCHEMA) -> str:
    data = json.dumps(
        {"schema": tag, "value": canonical_value(value)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


TASK_FIELDS = (
    "task_id",
    "run_id",
    "parent_task_id",
    "task_type",
    "goal",
    "assigned_agent",
    "skill_id",
    "dependencies",
    "origin",
    "reason_code",
    "output_requirements",
)
CALCULATION_FIELDS = (
    "calculation_id",
    "run_id",
    "task_id",
    "capability_id",
    "capability_version",
    "formula_id",
    "input_evidence_ids",
    "input_values_snapshot",
    "parameters",
    "output_value",
    "output_unit",
    "status",
)


def task_semantics(task) -> dict:
    values = {key: getattr(task, key) for key in TASK_FIELDS}
    if getattr(task, "wp04_method_requirement", None) is not None:
        values["wp04_method_requirement"] = task.wp04_method_requirement
    return canonical_value(values)


def task_fingerprint(task) -> str:
    return digest(task_semantics(task), SCHEMA + "/task")


def graph_semantics(graph) -> dict:
    return {
        "run_id": graph.run_id,
        "graph_id": graph.graph_id,
        "version": graph.version,
        "tasks": [
            task_semantics(task) for task in sorted(graph.tasks, key=lambda item: item.task_id)
        ],
    }


def calculation_core(record) -> dict:
    identity = record.implementation_hash or record.code_hash
    if not identity:
        raise BindingDenied("IDENTITY_MISMATCH", record.calculation_id)
    return canonical_value(
        {
            **{key: getattr(record, key) for key in CALCULATION_FIELDS},
            "implementation_hash": identity,
            "implementation_identity_source": (
                "implementation_hash" if record.implementation_hash else "code_hash"
            ),
        }
    )


class BindingValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GraphIdentity(BindingValue):
    run_id: str
    graph_id: str
    version: int = Field(ge=1)
    semantic_hash: str

    @classmethod
    def of(cls, graph):
        return cls(
            run_id=graph.run_id,
            graph_id=graph.graph_id,
            version=graph.version,
            semantic_hash=digest(graph_semantics(graph), SCHEMA + "/graph"),
        )


class OwnerToken(BindingValue):
    run_id: str
    execution_mode: Literal["DEFAULT"] = "DEFAULT"
    owner_generation: int = Field(ge=1)
    owner_id: str = Field(min_length=1)


class BindingReference(BindingValue):
    schema_version: Literal["wp02-node-binding/v1"] = SCHEMA
    run_id: str
    binding_revision: int = Field(ge=0)
    binding_hash: str


class OutputRecord(BindingValue):
    kind: Literal["EVIDENCE", "CALCULATION_CORE", "AGENT_OUTPUT", "TASK_OUTPUT_SNAPSHOT"]
    record_id: str
    content_digest: str
    location: str
    record_schema: str
    payload_snapshot: dict


class DependencyBinding(BindingValue):
    producer_task_id: str
    result_id: str
    result_version: int = Field(ge=1)
    result_digest: str
    producer_owner: str
    status: Literal["COMMITTED"] = "COMMITTED"
    admission_binding_id: str
    resolved_input_binding_ids: tuple[str, ...]


class AdmissionBinding(BindingValue):
    schema_version: Literal["wp02-admission/v1"] = "wp02-admission/v1"
    admission_binding_id: str
    object_id: str
    run_id: str
    goal_id: str
    goal_hash: str
    scheme_id: str
    scheme_hash: str
    graph: GraphIdentity
    task_id: str
    task_fingerprint: str
    owner: OwnerToken
    attempt_reservation_id: str
    authorized_input_requirements: dict
    preexisting_inputs: tuple[OutputRecord, ...] = ()
    dependency_result_bindings: tuple[DependencyBinding, ...] = ()
    policy_refs: dict


class AttemptReservation(BindingValue):
    admission: AdmissionBinding
    execution_started: bool = False
    status: Literal["RESERVED", "DISPATCHED", "COMMITTED", "RESULT_UNKNOWN", "FAILED"]
    generation: int = Field(default=1, ge=1)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    prior_reservation_id: str | None = None
    recovery: dict | None = None


class ResolvedInputBinding(BindingValue):
    schema_version: Literal["wp02-resolved-input/v1"] = "wp02-resolved-input/v1"
    resolved_input_binding_id: str
    admission_binding_id: str
    reservation_id: str
    step_id: str
    material_refs: tuple[OutputRecord, ...]
    payload_snapshot: dict
    input_digest: str


class ResultBinding(BindingValue):
    schema_version: Literal["wp02-result/v1"] = "wp02-result/v1"
    result_id: str
    producer_task_id: str
    run_id: str
    graph: GraphIdentity
    task_fingerprint: str
    admission_binding_id: str
    resolved_input_binding_ids: tuple[str, ...]
    owner_generation: int
    reservation_id: str
    result_version: int = Field(ge=1)
    result_digest: str
    output_records: tuple[OutputRecord, ...]
    producer_owner: str
    status: Literal["COMMITTED"] = "COMMITTED"
    supersedes_refs: tuple[str, ...] = ()
    invalidates_refs: tuple[str, ...] = ()
    observed_execution: dict = Field(default_factory=dict)

    def dependency(self):
        return DependencyBinding(
            **{key: getattr(self, key) for key in DependencyBinding.model_fields}
        )


class NodeBindingState(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    schema_version: Literal["wp02-node-binding/v1"] = SCHEMA
    run_id: str
    execution_mode: Literal["DEFAULT", "RECOVERABLE_V1", "UNKNOWN"]
    owner_generation: int = Field(ge=0)
    owner_id: str | None
    lifecycle: Literal["UNCLAIMED", "ACTIVE", "CLOSED", "RESULT_UNKNOWN", "RECOVERY_PENDING"]
    binding_revision: int = Field(ge=0)
    scheduler_started: bool = False
    frozen_graph: GraphIdentity
    execution_snapshot: dict | None = None
    scenario_snapshot_digest: str | None = None
    execution_profile_snapshot_digest: str | None = None
    attempts: dict[str, AttemptReservation] = Field(default_factory=dict)
    attempt_history: dict[str, AttemptReservation] = Field(default_factory=dict)
    resolved_inputs: dict[str, ResolvedInputBinding] = Field(default_factory=dict)
    results: dict[str, ResultBinding] = Field(default_factory=dict)
    current_results: dict[str, str] = Field(default_factory=dict)
    invalidation_refs: list[str] = Field(default_factory=list)

    def reference(self):
        return BindingReference(
            run_id=self.run_id, binding_revision=self.binding_revision, binding_hash=digest(self)
        )


def value_identity(value, *excluded: str):
    return digest(
        {key: item for key, item in canonical_value(value).items() if key not in excluded},
        value.schema_version,
    )


def check_value_identity(value, field: str, *excluded: str):
    if getattr(value, field) != value_identity(value, field, *excluded):
        raise BindingDenied("IDENTITY_MISMATCH", field)
