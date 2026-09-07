"""Released public source projections → compact immutable research asset."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from src.phase4_product.errors import product_error
from src.phase4_product.memory_contracts import (
    MemoryItem,
    ResearchObjectVersion,
    ResearchViewVersion,
)


def build_memory_versions(object_id, run_id, projection, result, report, review, execution):
    if projection.run.status != "RELEASED" or not projection.terminal.is_terminal:
        raise product_error("NOT_RELEASED", "memory requires an authoritative released Run")
    if (
        projection.run.run_id != run_id
        or projection.object.object_id != object_id
        or projection.run.research_object_id != object_id
    ):
        raise product_error("IDENTITY_MISMATCH", "memory source Object or Run mismatch")
    sources = (result, report, review, execution)
    if any(s.run_id != run_id or s.object_id != object_id for s in sources):
        raise product_error("IDENTITY_MISMATCH", "memory source surface identity mismatch")
    if (
        any(s.released_result_id != result.released_result_id for s in sources)
        or any(
            s.canonical_execution_record_id != result.canonical_record_id
            for s in (report, review, execution)
        )
        or projection.result.canonical_record_id != result.canonical_record_id
        or review.verdict != "PASS"
        or result.availability.status != "AVAILABLE"
    ):
        raise product_error("INTEGRITY_FAILURE", "memory release closure mismatch")
    metrics = {m.metric_id: m for m in result.metrics}
    claims = {c.claim_id: c for c in result.claims}
    if len(metrics) != len(result.metrics) or len(claims) != len(result.claims):
        raise product_error("INTEGRITY_FAILURE", "duplicate retained material identity")
    for item in (*result.metrics, *result.claims, *report.source_contributions):
        if item.run_id != run_id:
            raise product_error("IDENTITY_MISMATCH", "foreign memory source reference")
    for claim in claims.values():
        metric = metrics.get(claim.metric_id)
        if (
            metric is None
            or claim.claim_id not in metric.claim_refs
            or tuple(claim.calculation_refs) != (metric.calculation_id,)
            or set(claim.evidence_refs) != set(metric.evidence_refs)
        ):
            raise product_error("INTEGRITY_FAILURE", "claim metric lineage mismatch")
    for contribution in report.source_contributions:
        if (
            contribution.report_id != report.report_id
            or contribution.artifact_id != report.artifact_id
            or contribution.report_anchor not in {a.anchor for a in report.anchors}
            or contribution.calculation_id not in {m.calculation_id for m in metrics.values()}
        ):
            raise product_error("IDENTITY_MISMATCH", "foreign report contribution")
        details = [
            d
            for d in execution.actor_details
            if d.actor_id == contribution.actor_id and d.run_id == run_id
        ]
        if len(details) != 1 or not any(
            o.output_id == contribution.agent_output_id
            and o.run_id == run_id
            and o.task_id == contribution.task_id
            for o in details[0].outputs
        ):
            raise product_error("IDENTITY_MISMATCH", "memory contribution output mismatch")

    def ident(prefix, ref):
        return prefix + str(uuid5(NAMESPACE_URL, f"phase5a:{object_id}:{run_id}:{ref}"))

    def lineage(metric):
        links = [
            c for c in report.source_contributions if c.calculation_id == metric.calculation_id
        ]
        # No first-match/approximate source selection for ambiguous contributions.
        c = links[0] if len(links) == 1 else None
        return dict(
            calculation_id=metric.calculation_id,
            evidence_ids=tuple(metric.evidence_refs),
            report_anchor=c.report_anchor if c else None,
            task_id=c.task_id if c else None,
            agent_output_id=c.agent_output_id if c else None,
        )

    common = dict(source_run_id=run_id, report_id=report.report_id, review_id=review.review_id)
    items = []
    for metric in result.metrics:
        if metric.proof.status != "VERIFIED" or not metric.proof.proof_refs:
            continue
        items.append(
            MemoryItem(
                **common,
                **lineage(metric),
                memory_item_id=ident("MI-", metric.metric_id),
                category="VERIFIED_METRIC",
                reference_id=metric.metric_id,
                title=metric.name,
                statement=(
                    f"{metric.name}: {metric.display_value} {metric.display_unit} · {metric.period}"
                ),
                display_value=metric.display_value,
                display_unit=metric.display_unit,
            )
        )
        for claim in result.claims:
            if claim.metric_id == metric.metric_id:
                items.append(
                    MemoryItem(
                        **common,
                        **lineage(metric),
                        memory_item_id=ident("MI-", claim.claim_id),
                        category="VERIFIED_CLAIM",
                        reference_id=claim.claim_id,
                        title=metric.name,
                        statement=claim.statement,
                    )
                )
    for change in projection.path_changes:
        if change.source_kind == "CORRECTION" and change.status == "RESOLVED":
            items.append(
                MemoryItem(
                    **common,
                    memory_item_id=ident("MI-", change.source_id),
                    category="RESOLVED_ISSUE",
                    reference_id=change.source_id,
                    title="Resolved research issue",
                    statement=change.reason_code or "RESOLVED",
                    task_id=change.task_refs[0] if len(change.task_refs) == 1 else None,
                )
            )
    now = datetime.now(UTC)
    identity = dict(
        research_object_id=object_id,
        source_run_id=run_id,
        source_released_result_id=result.released_result_id,
        source_report_id=report.report_id,
        source_canonical_record_id=result.canonical_record_id,
        created_at=now,
    )
    obj = ResearchObjectVersion(
        **identity, object_version=1, object_version_id=ident("ROV-", "object-v1")
    )
    view = ResearchViewVersion(
        **identity,
        research_view_version=1,
        research_view_version_id=ident("RVV-", "view-v1"),
        research_object_version=1,
        as_of=projection.run.as_of.isoformat(),
        summary=" ".join(i.statement for i in items if i.category == "VERIFIED_CLAIM") or None,
        items=tuple(items),
    )
    return obj, view
