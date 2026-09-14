"""Disposable valuation context projection. All reads and commits keep their existing owners."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import model_validator

from src.domain.node_binding import (
    BindingDenied,
    BindingValue,
    canonical_value,
    digest,
    graph_semantics,
)
from src.phase4_product.memory_contracts import ResearchMemorySnapshot, ResearchViewVersion

POLICY = "wp03-valuation-context-interaction/v1"


def encoded(value):
    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


class SourceRef(BindingValue):
    namespace: Literal["CURRENT", "HISTORICAL_BASE", "INTERACTION"]
    owner: str
    object_id: str
    run_id: str
    source_id: str
    source_schema: str
    version: int | None = None
    source_digest: str
    field_selectors: tuple[str, ...] = ("/",)
    inclusion_reason: Literal["REQUIREMENT", "SUPPORT", "LIMITATION", "REQUESTED"]


class MemoryViewRef(BindingValue):
    source_run_id: str
    view_id: str
    version: int
    object_version: int
    released_result_id: str
    report_id: str
    CER_id: str
    view_digest: str

    @classmethod
    def of(cls, view):
        return cls(
            source_run_id=view.source_run_id,
            view_id=view.research_view_version_id,
            version=view.research_view_version,
            object_version=view.research_object_version,
            released_result_id=view.source_released_result_id,
            report_id=view.source_report_id,
            CER_id=view.source_canonical_record_id,
            view_digest=digest(view, "memory-view/v1"),
        )


class MemoryPointerRef(BindingValue):
    source_run_id: str
    view_id: str
    view_version: int
    object_version: int
    released_result_id: str
    report_id: str
    CER_id: str
    view_digest: str

    @classmethod
    def of(cls, view):
        values = MemoryViewRef.of(view).model_dump()
        values["view_version"] = values.pop("version")
        return cls(**values)


class MemoryBinding(BindingValue):
    mode: Literal["NONE", "BOUND"]
    reason: str
    object_id: str
    base: MemoryViewRef | None = None
    current_pointer_observed: MemoryPointerRef | None = None
    relation: Literal["SAME_VIEW", "ADVANCED"] | None = None

    @model_validator(mode="after")
    def closure(self):
        if self.mode == "NONE":
            if self.reason != "NOT_REQUESTED_BY_CONFIRMED_SCHEME" or any(
                v is not None for v in (self.base, self.current_pointer_observed, self.relation)
            ):
                raise ValueError("NONE Memory carries no source authority")
        elif self.base is None or self.current_pointer_observed is None or self.relation is None:
            raise ValueError("incomplete BOUND Memory")
        return self


class FreshnessReceipt(BindingValue):
    guarantee: Literal["EXACT_IDENTITY_AT_READ_CHECKPOINTS"] = "EXACT_IDENTITY_AT_READ_CHECKPOINTS"
    admission_digest: str
    material_digest: str
    memory_digest: str


class ResearchContextPackage(BindingValue):
    context_schema_version: Literal["vefin-research-context/v1"] = "vefin-research-context/v1"
    context_id: str
    context_revision: Literal[1, 2]
    object_id: str
    run_id: str
    task_id: str
    task_fingerprint: str
    consumer_role: Literal["valuation_analyst"] = "valuation_analyst"
    goal_ref: SourceRef
    scheme_ref: SourceRef
    graph_ref: SourceRef
    admission_binding_ref: SourceRef
    dependency_result_refs: tuple[SourceRef, ...]
    memory_binding: MemoryBinding
    evidence_refs: tuple[SourceRef, ...]
    calculation_refs: tuple[SourceRef, ...]
    claim_metric_refs: tuple[SourceRef, ...]
    resolved_issue_refs: tuple[SourceRef, ...]
    ancestor_output_refs: tuple[SourceRef, ...]
    retrieval_history_refs: tuple[SourceRef, ...]
    source_manifest_digest: str
    requested_model: str
    requested_reasoning_profile: str | None = None
    routing_policy_ref: str
    sections: tuple[dict, ...]
    freshness_receipt: FreshnessReceipt
    size_bytes: int
    size_policy: Literal["wp03-valuation-context-interaction/v1"] = POLICY
    created_at: str

    def refs(self):
        return (
            self.goal_ref,
            self.scheme_ref,
            self.graph_ref,
            self.admission_binding_ref,
            *self.dependency_result_refs,
            *self.evidence_refs,
            *self.calculation_refs,
            *self.claim_metric_refs,
            *self.resolved_issue_refs,
            *self.ancestor_output_refs,
            *self.retrieval_history_refs,
        )

    @classmethod
    def build(cls, **values):
        package = cls(
            context_id="", size_bytes=0, created_at="", source_manifest_digest="", **values
        )
        refs = sorted(
            (canonical_value(r) for r in package.refs()),
            key=lambda r: (r["namespace"], r["owner"], r["source_id"], r["field_selectors"]),
        )
        if len(refs) > 128 or len(package.sections) > 32:
            raise BindingDenied("CONTEXT_TOO_LARGE", "source refs/rendered items")
        body = package.model_dump(exclude={"context_id", "size_bytes", "created_at"})
        body["source_manifest_digest"] = digest(refs, "context-manifest/v1")
        body["context_id"] = digest(body, "vefin-research-context/v1")
        size = len(encoded(body))
        if size > 32768:
            raise BindingDenied("CONTEXT_TOO_LARGE", "body")
        return cls(**body, size_bytes=size, created_at=datetime.now(UTC).isoformat())


class ContextProjection:
    """Invocation-local read adapter; never saves, updates or materializes source state."""

    def __init__(self, executor, task, admission, requested_model, route_ref):
        self.executor, self.task, self.admission = executor, task, admission
        self.service = executor._service
        self.requested_model, self.route_ref = requested_model, route_ref
        self.materials = executor._bound_materials(task)
        self.inventory = {}
        self.read_count = 0
        self.memory = None
        self.base_view = None
        self.package = None
        self.rendered = set()

    async def memory_read(self, fresh):
        if fresh.scheme.confirmed_at is None:
            raise BindingDenied("CONTEXT_IDENTITY_UNAVAILABLE", "unconfirmed Scheme")
        context = fresh.scheme.incremental_context
        if context is None:
            return MemoryBinding(
                mode="NONE",
                reason="NOT_REQUESTED_BY_CONFIRMED_SCHEME",
                object_id=self.admission.object_id,
            ), None
        reader = self.service.research_memory_reader
        if reader is None:
            raise BindingDenied("CONTEXT_MEMORY_UNAVAILABLE", "reader")
        oid = self.admission.object_id
        if context.target_as_of != fresh.goal.as_of or fresh.run.as_of != fresh.goal.as_of:
            raise BindingDenied("IDENTITY_MISMATCH", "Memory target as-of")
        if context.research_object_id != oid:
            raise BindingDenied("IDENTITY_MISMATCH", "Memory Object")
        self.read_count += 1
        p0 = ResearchMemorySnapshot.model_validate(canonical_value(await reader.read(oid)))
        self.read_count += 1
        base = ResearchViewVersion.model_validate(
            canonical_value(
                await reader.read_exact(
                    oid, context.base_run_id, context.base_research_view_version
                )
            )
        )
        self.read_count += 1
        p1 = ResearchMemorySnapshot.model_validate(canonical_value(await reader.read(oid)))
        if p0.research_object_id != oid or p1.research_object_id != oid:
            raise BindingDenied("IDENTITY_MISMATCH", "Memory pointer Object")
        if p0.current_view is None or p1.current_view is None:
            raise BindingDenied("CONTEXT_MEMORY_UNAVAILABLE", "EMPTY_CURRENT")
        current = MemoryPointerRef.of(p0.current_view)
        if current != MemoryPointerRef.of(p1.current_view):
            raise BindingDenied("CONTEXT_STALE_MEMORY", "pointer moved during read")
        if (
            base.research_object_id,
            base.source_run_id,
            base.research_view_version_id,
            base.research_view_version,
            base.as_of,
        ) != (
            oid,
            context.base_run_id,
            context.base_research_view_version,
            context.base_version_number,
            context.base_as_of.isoformat(),
        ):
            raise BindingDenied(
                "CONTEXT_STALE_MEMORY" if self.memory else "IDENTITY_MISMATCH", "Memory BASE"
            )
        if (
            current.view_version <= base.research_view_version
            and current.view_id != base.research_view_version_id
        ) or (
            current.view_id == base.research_view_version_id
            and current.view_digest != MemoryViewRef.of(base).view_digest
        ):
            raise BindingDenied(
                "CONTEXT_STALE_MEMORY" if self.memory else "IDENTITY_MISMATCH",
                "Memory BASE/CURRENT relation",
            )
        return MemoryBinding(
            mode="BOUND",
            reason="CONFIRMED_SCHEME_BASE",
            object_id=oid,
            base=MemoryViewRef.of(base),
            current_pointer_observed=current,
            relation="SAME_VIEW"
            if base.research_view_version_id == current.view_id
            else "ADVANCED",
        ), base

    async def checkpoint(self):
        self.read_count += 1
        fresh = await self.service.repository.check_invocation(self.admission)
        self.read_count += 1
        await self.service.repository.verify_materials(self.materials, run_id=self.task.run_id)
        for material in self.materials:
            if material.kind == "EVIDENCE":
                self.read_count += 1
                original = await self.service.evidence_repository.get(material.record_id)
                if original is None or canonical_value(original) != material.payload_snapshot:
                    raise BindingDenied("CONTEXT_IDENTITY_UNAVAILABLE", material.record_id)
        memory, base = await self.memory_read(fresh)
        if self.memory is not None and self.memory != memory:
            raise BindingDenied("CONTEXT_STALE_MEMORY", "bound Memory changed")
        self.memory, self.base_view = memory, base
        return fresh

    def ref(
        self,
        owner,
        identity,
        schema,
        value,
        *,
        reason="SUPPORT",
        namespace="CURRENT",
        version=None,
        run_id=None,
    ):
        return SourceRef(
            namespace=namespace,
            owner=owner,
            object_id=self.admission.object_id,
            run_id=run_id or self.task.run_id,
            source_id=identity,
            source_schema=schema,
            version=version,
            source_digest=digest(value, schema),
            inclusion_reason=reason,
        )

    async def build(self):
        fresh = await self.checkpoint()
        a = self.admission
        refs = {"EVIDENCE": [], "CALCULATION_CORE": [], "AGENT_OUTPUT": []}
        sections = [
            {
                "source_id": a.task_id,
                "task_goal": self.task.goal,
                "as_of": canonical_value(fresh.goal.as_of),
                "goal_text": fresh.goal.goal_text,
                "requirements": {
                    "task": a.authorized_input_requirements.get("task"),
                    "scheme": {
                        k: v
                        for k, v in canonical_value(fresh.scheme).items()
                        if k.endswith("requirements") or k in {"research_scope", "limitations"}
                    },
                },
                "valuation_status": "not_quantified_in_current_scope",
                "quantified_valuation_available": False,
            }
        ]
        for material in self.materials:
            ref = self.ref(
                material.kind, material.record_id, material.record_schema, material.payload_snapshot
            )
            refs[material.kind].append(ref)
            item = canonical_value(material.payload_snapshot)
            if material.kind == "EVIDENCE":
                # Raw artifacts stay with the Evidence owner; no arbitrary location reads.
                item = {
                    k: v
                    for k, v in item.items()
                    if k not in {"raw_artifact_ref", "source_locator", "source_endpoint"}
                }
                metadata = {k: v for k, v in item.items() if k != "normalized_value"}
                sections.append({"source_id": material.record_id, "metadata": metadata})
                if item.get("unit") != "text":
                    sections[-1]["financial_support"] = item
                    self.rendered.add(material.record_id)
            if material.record_id in self.inventory:
                raise BindingDenied("CONTEXT_IDENTITY_UNAVAILABLE", "ambiguous source ID")
            self.inventory[material.record_id] = (ref, item)
            if material.kind == "CALCULATION_CORE":
                sections.append(
                    {"source_id": material.record_id, "calculation": material.payload_snapshot}
                )
                self.rendered.add(material.record_id)
        claims, issues = [], []
        if self.base_view is not None:
            items = {i.memory_item_id: i for i in self.base_view.items}
            for decision in fresh.scheme.incremental_context.decisions:
                if decision.category == "VIEW_CONTEXT":
                    continue
                item = items.get(decision.source_identity)
                if item is None or item.category != decision.category:
                    raise BindingDenied("CONTEXT_IDENTITY_UNAVAILABLE", decision.source_identity)
                ref = self.ref(
                    "ResearchMemoryRepository",
                    item.memory_item_id,
                    "memory-item/v1",
                    item,
                    namespace="HISTORICAL_BASE",
                    version=self.base_view.research_view_version,
                    run_id=item.source_run_id,
                )
                (issues if item.category == "RESOLVED_ISSUE" else claims).append(ref)
                if item.memory_item_id in self.inventory:
                    raise BindingDenied("CONTEXT_IDENTITY_UNAVAILABLE", "ambiguous historical ID")
                self.inventory[item.memory_item_id] = (ref, canonical_value(item))
                sections.append(
                    {
                        "source_id": a.scheme_id,
                        "memory_item_id": item.memory_item_id,
                        "field_selector": "/incremental_context/decisions",
                        "historical_decision": canonical_value(decision),
                    }
                )
        values = dict(
            context_revision=1,
            object_id=a.object_id,
            run_id=a.run_id,
            task_id=a.task_id,
            task_fingerprint=a.task_fingerprint,
            goal_ref=self.ref(
                "Application", a.goal_id, "wp02-node-binding/v1", fresh.goal, reason="REQUIREMENT"
            ),
            scheme_ref=self.ref(
                "Application",
                a.scheme_id,
                "wp02-node-binding/v1",
                fresh.scheme,
                reason="REQUIREMENT",
            ),
            graph_ref=self.ref(
                "Runtime",
                a.graph.graph_id,
                "wp02-node-binding/v1/graph",
                graph_semantics(fresh.runtime.actual_graph),
                version=a.graph.version,
            ),
            admission_binding_ref=self.ref(
                "Repository", a.admission_binding_id, a.schema_version, a
            ),
            dependency_result_refs=tuple(
                self.ref(
                    "Repository",
                    dep.result_id,
                    "wp02-result/v1",
                    fresh.node_binding.results[dep.result_id],
                    version=dep.result_version,
                )
                for dep in a.dependency_result_bindings
            ),
            memory_binding=self.memory,
            evidence_refs=tuple(refs["EVIDENCE"]),
            calculation_refs=tuple(refs["CALCULATION_CORE"]),
            ancestor_output_refs=tuple(refs["AGENT_OUTPUT"]),
            claim_metric_refs=tuple(claims),
            resolved_issue_refs=tuple(issues),
            retrieval_history_refs=(),
            sections=tuple(sections),
            requested_model=self.requested_model,
            routing_policy_ref=self.route_ref,
            freshness_receipt=FreshnessReceipt(
                admission_digest=digest(a),
                material_digest=digest(self.materials),
                memory_digest=digest(self.memory),
            ),
        )
        self.package = ResearchContextPackage.build(**values)
        return self.package
