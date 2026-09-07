"""Exact released formula/period keys; never fuzzy title or statement matching."""

import json
from collections import Counter

from src.phase4_product.memory_contracts import MemoryChange


def compare_memory(base, current, base_result, current_result):
    def indexed(view, result):
        if (view.source_run_id, view.research_object_id, view.source_released_result_id) != (
            result.run_id,
            result.object_id,
            result.released_result_id,
        ):
            raise ValueError("comparison result identity mismatch")
        metrics = {m.metric_id: m for m in result.metrics}
        claims = {c.claim_id: c for c in result.claims}
        rows = []
        for item in view.items:
            key, value = None, None
            if item.category != "RESOLVED_ISSUE":
                claim = claims.get(item.reference_id) if item.category == "VERIFIED_CLAIM" else None
                metric = metrics.get(claim.metric_id if claim else item.reference_id)
                if (
                    metric is None
                    or metric.run_id != view.source_run_id
                    or metric.calculation_id != item.calculation_id
                    or metric.proof.status != "VERIFIED"
                ):
                    raise ValueError("comparison item has no exact verified metric")
                key = json.dumps(
                    [
                        item.category,
                        metric.formula_id,
                        metric.capability_id,
                        metric.period,
                        metric.period_basis,
                        metric.actuality,
                        metric.canonical_unit,
                        metric.currency,
                        claim.claim_type if claim else None,
                    ],
                    separators=(",", ":"),
                )
                value = metric.canonical_value
            rows.append((item, key, value))
        counts = Counter(key for _, key, _ in rows if key)
        return [(item, key if counts[key] == 1 else None, value) for item, key, value in rows]

    previous, latest = indexed(base, base_result), indexed(current, current_result)
    lookup = {key: (item, value) for item, key, value in latest if key}
    used = set()
    changes = []
    for item, key, value in previous:
        match = lookup.get(key) if key else None
        if match:
            now, now_value = match
            used.add(now.memory_item_id)
            state = (
                "UPDATED"
                if value != now_value
                else ("REVALIDATED" if item.category == "VERIFIED_CLAIM" else "UNCHANGED")
            )
            changes.append(
                MemoryChange(
                    category=item.category,
                    change=state,
                    logical_key=key,
                    base_item_id=item.memory_item_id,
                    current_item_id=now.memory_item_id,
                )
            )
        else:
            changes.append(
                MemoryChange(
                    category=item.category,
                    change="REMOVED_FROM_CURRENT_VIEW",
                    logical_key=key,
                    base_item_id=item.memory_item_id,
                    current_item_id=None,
                )
            )
    for item, key, _ in latest:
        if item.memory_item_id not in used:
            changes.append(
                MemoryChange(
                    category=item.category,
                    change="NEW",
                    logical_key=key,
                    base_item_id=None,
                    current_item_id=item.memory_item_id,
                )
            )
    return tuple(changes)
