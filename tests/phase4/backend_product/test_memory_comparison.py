from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.phase4_product.memory import build_memory_versions
from src.phase4_product.memory_comparison import compare_memory
from tests.phase4.backend_product.test_memory_source import source


def pair():
    first = source()
    metric = first[1].metrics[0]
    for key, value in dict(
        formula_id="revenue_growth",
        capability_id="financial_calculations",
        period_basis="FY",
        actuality="ACTUAL",
        canonical_unit="PERCENT",
        currency=None,
        canonical_value="65.47",
    ).items():
        setattr(metric, key, value)
    first[1].claims[0].claim_type = "financial_metric"

    def new(value):
        if isinstance(value, SimpleNamespace):
            return SimpleNamespace(**{k: new(v) for k, v in vars(value).items()})
        if isinstance(value, list):
            return [new(v) for v in value]
        if isinstance(value, str) and value != "OBJ-A":
            return value.replace("-A", "-B")
        return value

    second = new(first)
    v1 = build_memory_versions("OBJ-A", "RUN-A", *first)[1]
    v2 = build_memory_versions("OBJ-A", "RUN-B", *second, version=2)[1]
    return v1, v2, first[1], second[1]


def test_governed_formula_period_comparison_independent_validation():
    values = pair()
    original = deepcopy(values)
    changes = compare_memory(*values)
    assert [c.change for c in changes] == ["UNCHANGED", "REVALIDATED"]
    assert all(c.logical_key and c.base_item_id != c.current_item_id for c in changes)
    assert values == original


def test_updated_value_is_not_unchanged():
    values = pair()
    values[3].metrics[0].canonical_value = "70.0"
    assert [c.change for c in compare_memory(*values)] == ["UPDATED", "UPDATED"]


@pytest.mark.parametrize(
    "key",
    [
        "formula_id",
        "period",
        "period_basis",
        "actuality",
        "canonical_unit",
        "currency",
        "capability_id",
    ],
)
def test_similar_words_never_override_governed_difference(key):
    values = pair()
    setattr(values[3].metrics[0], key, "DIFFERENT")
    assert [c.change for c in compare_memory(*values)] == ["REMOVED_FROM_CURRENT_VIEW"] * 2 + [
        "NEW"
    ] * 2


@pytest.mark.parametrize("key", ["run_id", "object_id", "released_result_id"])
def test_foreign_results_rejected(key):
    values = pair()
    setattr(values[3], key, "FOREIGN")
    with pytest.raises(ValueError):
        compare_memory(*values)
