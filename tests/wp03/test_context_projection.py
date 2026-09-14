"""Exact source/Memory checkpoints, projection identity and finite body limits."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from src.application.repository import InMemoryApplicationRepository
from src.application.research_context import ContextProjection, ResearchContextPackage, encoded
from src.application.service import ResearchApplicationService
from src.domain.incremental import IncrementalResearchContext
from src.domain.node_binding import BindingDenied, canonical_value
from src.phase4_product.memory_contracts import (
    ResearchMemorySnapshot,
    ResearchObjectVersion,
    ResearchViewVersion,
)
from tests.wp02.test_node_binding import admitted, aggregate


def view(version=1):
    return ResearchViewVersion(
        research_object_id="OBJECT-WP02",
        research_view_version=version,
        research_view_version_id=f"VIEW-{version}",
        research_object_version=version,
        source_run_id=f"HISTORY-{version}",
        source_released_result_id=f"RELEASE-{version}",
        source_report_id=f"REPORT-{version}",
        source_canonical_record_id=f"CER-{version}",
        as_of="2026-09-13",
        summary=None,
        items=(),
        created_at=datetime(2026, 9, 13, tzinfo=UTC),
    )


def snapshot(v):
    return ResearchMemorySnapshot(
        research_object_id=v.research_object_id,
        latest_released_run_id=v.source_run_id,
        latest_research_object_version=v.research_object_version,
        latest_research_view_version=v.research_view_version,
        current_view=v,
        object_version=ResearchObjectVersion(
            research_object_id=v.research_object_id,
            object_version=v.research_object_version,
            object_version_id=f"OBJ-{v.research_object_version}",
            source_run_id=v.source_run_id,
            source_released_result_id=v.source_released_result_id,
            source_report_id=v.source_report_id,
            source_canonical_record_id=v.source_canonical_record_id,
            created_at=v.created_at,
        ),
    )


class MemoryReader:
    def __init__(self, current=1):
        self.base = view()
        self.current = view(current)
        self.calls = 0
        self.move_at = None

    async def read(self, object_id):
        self.calls += 1
        if self.calls == self.move_at:
            self.current = view(3)
        return snapshot(self.current)

    async def read_exact(self, object_id, run_id, view_id):
        return self.base


async def projection(reader=None):
    value = aggregate(("valuation_analysis",))
    if reader:
        value.scheme.incremental_context = IncrementalResearchContext(
            research_object_id="OBJECT-WP02",
            base_run_id="HISTORY-1",
            base_research_view_version="VIEW-1",
            base_version_number=1,
            base_as_of=date(2026, 9, 13),
            target_as_of=date(2026, 9, 14),
            decisions=(),
        )
    repo = InMemoryApplicationRepository()
    _, a = await admitted(repo, value)
    service = ResearchApplicationService(repository=repo, research_memory_reader=reader)
    executor = SimpleNamespace(_service=service, _bound_materials=lambda task: ())
    result = ContextProjection(
        executor, value.runtime.actual_graph.tasks[0], a, "gpt-5.6-sol", "route"
    )
    return result


@pytest.mark.parametrize("current,relation", [(1, "SAME_VIEW"), (2, "ADVANCED")])
async def test_memory_base_current(current, relation):
    reader = MemoryReader(current)
    p = await projection(reader)
    before = canonical_value(snapshot(reader.current))
    package = await p.build()
    assert package.memory_binding.base.view_id == "VIEW-1"
    assert package.memory_binding.current_pointer_observed.view_version == current
    assert package.memory_binding.relation == relation
    await p.checkpoint()
    assert canonical_value(snapshot(reader.current)) == before
    reader.current = view(3)
    with pytest.raises(BindingDenied, match="CONTEXT_STALE_MEMORY"):
        await p.checkpoint()
    assert reader.base.research_view_version_id == "VIEW-1"


async def test_pointer_moves_during_read():
    reader = MemoryReader()
    reader.move_at = 2
    p = await projection(reader)
    with pytest.raises(BindingDenied, match="CONTEXT_STALE_MEMORY"):
        await p.build()


@pytest.mark.parametrize(
    "field,value",
    [("source_run_id", "FOREIGN"), ("research_view_version", 7), ("research_object_id", "OTHER")],
)
async def test_base_wrong_identity(field, value):
    reader = MemoryReader()
    reader.base = reader.base.model_copy(update={field: value})
    p = await projection(reader)
    with pytest.raises(BindingDenied, match="IDENTITY_MISMATCH"):
        await p.build()


async def test_none_and_deterministic_identity():
    p = await projection()
    package = await p.build()
    assert package.memory_binding.mode == "NONE"
    values = package.model_dump(
        exclude={"context_id", "source_manifest_digest", "size_bytes", "created_at"}
    )
    same = ResearchContextPackage.build(**values)
    assert same.context_id == package.context_id
    assert package.size_bytes == len(
        encoded(package.model_dump(exclude={"size_bytes", "created_at"}))
    )
    values["sections"] = ({"different": "presentation"},)
    assert ResearchContextPackage.build(**values).context_id != package.context_id


@pytest.mark.parametrize("limit", ["body", "refs", "items"])
async def test_bounds(limit):
    package = await (await projection()).build()
    values = package.model_dump(
        exclude={"context_id", "source_manifest_digest", "size_bytes", "created_at"}
    )
    if limit == "body":
        values["sections"] = ({"value": "x" * 32769},)
    elif limit == "refs":
        values["evidence_refs"] = (package.goal_ref,) * 129
    else:
        values["sections"] = ({"value": "x"},) * 33
    with pytest.raises(BindingDenied, match="CONTEXT_TOO_LARGE"):
        ResearchContextPackage.build(**values)


async def test_exact_body_edge():
    package = await (await projection()).build()
    values = package.model_dump(
        exclude={"context_id", "source_manifest_digest", "size_bytes", "created_at"}
    )
    values["sections"] = ({"value": ""},)
    baseline = ResearchContextPackage.build(**values).size_bytes
    values["sections"] = ({"value": "x" * (32768 - baseline)},)
    assert ResearchContextPackage.build(**values).size_bytes == 32768
    values["sections"][0]["value"] += "x"
    with pytest.raises(BindingDenied, match="CONTEXT_TOO_LARGE"):
        ResearchContextPackage.build(**values)


async def test_memory_change_during_actual_model(tmp_path, monkeypatch):
    from tests.wp03.test_valuation_retrieval import run_case

    async def configure(service, value, agent):
        p = await projection(MemoryReader())
        fresh = await p.service.repository.get_run_fresh(p.task.run_id)
        service.repository._runs[
            value.run.run_id
        ].scheme.incremental_context = fresh.scheme.incremental_context
        service.research_memory_reader = MemoryReader()

    result, calls, receipts, task = await run_case(tmp_path, monkeypatch, "memory_stale", configure)
    assert len(calls) == 1
    assert task.task_id not in result.node_binding.current_results
    assert receipts[0]["diagnostic_code"] == "CONTEXT_STALE_MEMORY"


@pytest.mark.parametrize("change", ["base_content", "current_content", "missing_reader"])
async def test_memory_checkpoint_rejects_content_or_missing_reader(change):
    reader = MemoryReader()
    p = await projection(reader)
    await p.build()
    if change == "base_content":
        reader.base = reader.base.model_copy(update={"summary": "changed"})
    elif change == "current_content":
        reader.current = reader.current.model_copy(update={"summary": "changed"})
    else:
        p.service.research_memory_reader = None
    with pytest.raises(BindingDenied, match="CONTEXT_STALE_MEMORY|CONTEXT_MEMORY_UNAVAILABLE"):
        await p.checkpoint()


async def test_history_item_stays_historical():
    from src.domain.incremental import IncrementalDecision
    from src.phase4_product.memory_contracts import MemoryItem

    reader = MemoryReader(2)
    item = MemoryItem(
        memory_item_id="old-metric",
        category="VERIFIED_METRIC",
        source_run_id="HISTORY-1",
        reference_id="old-calc",
        title="历史指标",
        statement="历史事实",
        display_value="12",
        display_unit="USD",
        calculation_id="old-calc",
        evidence_ids=("old-evidence",),
        review_id="old-review",
        report_id="REPORT-1",
    )
    reader.base = reader.base.model_copy(update={"items": (item,)})
    p = await projection(reader)
    # Fixture initialization before creating the new exact A; no product Run/database.
    fresh = await p.service.repository.get_run_fresh(p.task.run_id)
    context = fresh.scheme.incremental_context.model_copy(
        update={
            "decisions": (
                IncrementalDecision(
                    decision="REVALIDATE",
                    source_run_id="HISTORY-1",
                    source_identity="old-metric",
                    category="VERIFIED_METRIC",
                    statement="需重新验证",
                    reason="历史",
                ),
            )
        }
    )
    # Recreate local fixture so the admitted Scheme includes this exact context.
    original = reader
    p.memory = None

    async def memory_read(_):
        from src.application.research_context import MemoryBinding, MemoryPointerRef, MemoryViewRef

        return MemoryBinding(
            mode="BOUND",
            reason="CONFIRMED_SCHEME_BASE",
            object_id="OBJECT-WP02",
            base=MemoryViewRef.of(original.base),
            current_pointer_observed=MemoryPointerRef.of(original.current),
            relation="ADVANCED",
        ), original.base

    p.memory_read = memory_read
    fresh.scheme.incremental_context = context

    async def checkpoint():
        p.memory, p.base_view = await memory_read(fresh)
        return fresh

    p.checkpoint = checkpoint
    package = await p.build()
    assert package.claim_metric_refs[0].namespace == "HISTORICAL_BASE"
    assert not package.evidence_refs and not package.calculation_refs
    assert package.memory_binding.current_pointer_observed.view_id == "VIEW-2"


@pytest.mark.parametrize("change", ["goal", "scheme", "task", "graph", "generation", "reservation"])
async def test_projection_rechecks_existing_admission(change):
    p = await projection()
    await p.build()
    raw = p.service.repository._runs[p.task.run_id]
    if change == "goal":
        raw.goal.goal_text = "changed"
    elif change == "scheme":
        raw.scheme.limitations.append("changed")
    elif change == "task":
        raw.runtime.task(p.task.task_id).goal = "changed"
    elif change == "graph":
        raw.runtime.actual_graph.version += 1
    elif change == "generation":
        raw.node_binding.owner_generation += 1
    else:
        raw.node_binding.attempts.clear()
    with pytest.raises(BindingDenied):
        await p.checkpoint()


async def test_unrelated_root_revision_is_not_context_identity():
    p = await projection()
    package = await p.build()
    p.service.repository._runs[p.task.run_id].node_binding.binding_revision += 1
    await p.checkpoint()
    assert p.package.context_id == package.context_id


async def test_memory_retrieval_through_actual_consumer(tmp_path, monkeypatch):
    from src.domain.incremental import IncrementalDecision
    from src.phase4_product.memory_contracts import MemoryItem
    from tests.wp03.test_valuation_retrieval import run_case

    async def configure(service, value, agent):
        reader = MemoryReader(2)
        item = MemoryItem(
            memory_item_id="old-metric",
            category="VERIFIED_METRIC",
            source_run_id="HISTORY-1",
            reference_id="old-calc",
            title="历史指标",
            statement="历史事实",
            display_value="12",
            display_unit="USD",
            calculation_id="old-calc",
            evidence_ids=("old-evidence",),
            review_id="old-review",
            report_id="REPORT-1",
        )
        reader.base = reader.base.model_copy(update={"items": (item,)})
        service.research_memory_reader = reader
        service.repository._runs[
            value.run.run_id
        ].scheme.incremental_context = IncrementalResearchContext(
            research_object_id="OBJECT-WP02",
            base_run_id="HISTORY-1",
            base_research_view_version="VIEW-1",
            base_version_number=1,
            base_as_of=date(2026, 9, 13),
            target_as_of=date(2026, 9, 14),
            decisions=(
                IncrementalDecision(
                    decision="REVALIDATE",
                    source_run_id="HISTORY-1",
                    source_identity="old-metric",
                    category="VERIFIED_METRIC",
                    statement="需重新验证",
                    reason="历史",
                ),
            ),
        )

    result, calls, receipts, task = await run_case(
        tmp_path, monkeypatch, "memory_retrieve", configure
    )
    assert len(calls) == len(receipts) == 2
    assert task.task_id in result.node_binding.current_results
    assert calls[1]["claim_metric_refs"][0]["namespace"] == "HISTORICAL_BASE"
    assert calls[1]["claim_metric_refs"][0]["inclusion_reason"] == "REQUESTED"
    assert any(
        s.get("namespace") == "HISTORICAL_BASE" and s["content"]["display_value"] == "12"
        for s in calls[1]["sections"]
    )
    for b in result.node_binding.resolved_inputs.values():
        assert all(m.payload_snapshot["run_id"] == task.run_id for m in b.material_refs)


async def test_memory_change_immediately_before_result(tmp_path, monkeypatch):
    from tests.wp03.test_valuation_retrieval import run_case

    async def configure(service, value, agent):
        p = await projection(MemoryReader())
        fresh = await p.service.repository.get_run_fresh(p.task.run_id)
        service.repository._runs[
            value.run.run_id
        ].scheme.incremental_context = fresh.scheme.incremental_context
        reader = MemoryReader()
        service.research_memory_reader = reader
        original = agent.retain_valuation_final

        def retain(*args):
            result = original(*args)
            reader.current = view(2)
            return result

        agent.retain_valuation_final = retain

    result, calls, receipts, task = await run_case(
        tmp_path, monkeypatch, "before_result_stale", configure
    )
    assert len(calls) == len(receipts) == 1
    assert task.task_id not in result.node_binding.current_results
    assert not any(output.task_id == task.task_id for output in result.artifacts.agent_outputs)
