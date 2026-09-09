"""Opt-in V1 contracts. No defaults invent execution authority or total budgets."""

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def fingerprint(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


class ContractDenied(ValueError):
    """Safe machine-readable denial; never includes request bodies or secrets."""


class Immutable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class CallPurpose(StrEnum):
    CAPABILITY_CHECK = "CAPABILITY_CHECK"
    TASK_EXECUTION = "TASK_EXECUTION"
    PLANNING = "PLANNING"
    DECISION = "DECISION"
    DATA_REQUEST = "DATA_REQUEST"


class ExecutionBudget(Immutable):
    physical_calls: int = Field(gt=0)
    execution_calls: int = Field(ge=0)
    check_calls: int = Field(ge=0)
    decision_calls: int = Field(ge=0)
    max_cost: float | None = Field(default=None, ge=0)


class ExecutionContract(Immutable):
    version: Literal["recoverable-execution/v1"] = "recoverable-execution/v1"
    intent_id: str = Field(min_length=1, max_length=128)
    run_id: str | None
    task_id: str = Field(min_length=1, max_length=256)
    operation_id: str = Field(min_length=1, max_length=256)
    scheme_id: str = Field(min_length=1)
    scheme_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    object_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    graph_version: int = Field(ge=0)
    graph_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    required_outputs: tuple[str, ...]
    dependencies: tuple[str, ...]
    input_hashes: dict[str, str]
    schema_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    formula_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    code_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    policy_version: str = Field(min_length=1)
    policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_identity: str = Field(min_length=1)
    task_profile: str = Field(min_length=1)
    candidates: tuple[str, ...] = Field(min_length=1)
    dynamic_grants: dict[str, tuple[str, ...]]
    budget: ExecutionBudget
    task_budget: ExecutionBudget
    deadline: float = Field(gt=0)
    task_deadline: float = Field(gt=0)
    per_call_timeout: float = Field(gt=0)
    compatibility: str = Field(min_length=1)
    check_consumption: Literal["SEPARATE_EXECUTION", "EXACT_VALIDATED_ONCE"]

    @model_validator(mode="after")
    def identities(self):
        if self.run_id and not self.task_id.startswith(self.run_id + ":"):
            raise ValueError("task must belong to exact run")
        if len(set(self.candidates)) != len(self.candidates):
            raise ValueError("duplicate candidate")
        if any(not v.startswith("sha256:") or len(v) != 71 for v in self.input_hashes.values()):
            raise ValueError("input references must have content digests")
        if any(
            k not in self.candidates or any(v not in self.candidates for v in values)
            for k, values in self.dynamic_grants.items()
        ):
            raise ValueError("substitution grant outside candidate authority")
        return self

    @property
    def contract_hash(self):
        return fingerprint(self)


class LeaseToken(Immutable):
    intent_id: str
    operation_id: str
    owner: str
    epoch: int = Field(gt=0)


class PlanningContract(ExecutionContract):
    """Pre-admission identity without inventing an already generated Scheme/Graph."""

    planning_phase: Literal["SCHEME", "GRAPH"]
    run_id: None = None
    scheme_id: str | None
    scheme_hash: str | None
    graph_version: Literal[0] = 0
    graph_hash: None = None

    @model_validator(mode="after")
    def planning_identity(self):
        if self.planning_phase == "SCHEME":
            if self.scheme_id is not None or self.scheme_hash is not None:
                raise ValueError("Scheme planning cannot invent the generated Scheme identity")
        elif (
            not self.scheme_id
            or not self.scheme_hash
            or len(self.scheme_hash) != 71
            or not self.scheme_hash.startswith("sha256:")
        ):
            raise ValueError("Graph planning must bind the exact confirmed Scheme")
        return self


def invalidated_closure(changed: set[str], dependencies: dict[str, tuple[str, ...]]) -> set[str]:
    result = set(changed)
    while True:
        expanded = result | {key for key, deps in dependencies.items() if result.intersection(deps)}
        if expanded == result:
            return result
        result = expanded


def reusable(saved: ExecutionContract, current: ExecutionContract) -> bool:
    return saved.contract_hash == current.contract_hash
