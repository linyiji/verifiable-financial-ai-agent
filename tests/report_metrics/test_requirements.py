from copy import deepcopy
from datetime import date

import pytest

from src.application.execution_profiles import resolve_report_metric_draft
from src.application.service import ResearchApplicationService
from src.assurance.independent_financial_review import IndependentFinancialReviewer
from src.assurance.release_gate import ReleaseGate
from src.assurance.requirements import requirement_context
from src.capabilities.financial.growth import RevenueGrowthCapability
from src.capabilities.financial.profitability import EbitdaMarginCapability
from src.domain.capability import CapabilityContext
from src.domain.enums import FinancialUnit, ProofRequirement
from src.domain.execution_profile import (
    REPORT_METRIC_MARKER,
    FrozenReportMetricRequirementsV1,
    ScenarioProfile,
    report_metric_value,
)
from src.domain.node_binding import BindingDenied
from src.domain.research_goal import ResearchGoal
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.output import financial_metrics
from tests.unit.test_phase3_financial_extension import _evidence

GROWTH = "revenue_growth_v1"
MARGIN = "ebitda_margin_v1"


def resolve(**changes):
    request = dict(
        schema_version="frozen-report-metric-requirements/v1",
        report_mode="METRIC_FOCUSED",
        required_metric_ids=[GROWTH],
        period="FY2026",
    )
    request.update(changes)
    goal = ResearchGoal(
        goal_id="GOAL",
        research_object_id="OBJ-NVDA",
        goal_text="One metric",
        as_of=date(2026, 9, 4),
        preferences={"report_metric_requirements": request},
    )
    scheme = ResearchSchemeSnapshot(
        scheme_id="SCHEME", research_object_id="OBJ-NVDA", goal_id="GOAL", generated_by="server"
    )
    scheme = resolve_report_metric_draft(scheme, goal, ResearchApplicationService())
    contract = report_metric_value(
        scheme.report_requirements, scheme.assurance_requirements["report_metric_requirements"]
    )
    return contract, scheme


@pytest.fixture
async def bundle():
    evidence = [e for e in _evidence() if e.evidence_id in {"E-REV", "E-REV-PRIOR", "E-EBITDA"}]
    by_id = {e.evidence_id: e for e in evidence}
    context = CapabilityContext(run_id="RUN-1", task_id="RUN-1:fundamentals")
    growth = await RevenueGrowthCapability().execute(
        dict(prior=by_id["E-REV-PRIOR"], current=by_id["E-REV"], calculation_id="GROWTH"), context
    )
    margin = await EbitdaMarginCapability().execute(
        dict(ebitda=by_id["E-EBITDA"], revenue=by_id["E-REV"], calculation_id="MARGIN"), context
    )
    return dict(evidence=evidence, calculations=[growth, margin])


def inputs(bundle, *, contract=None, scheme=None, used=None):
    if contract is None:
        contract, scheme = resolve()
    used = used if used is not None else contract.resolved_required_metric_ids
    metrics, claims, _ = financial_metrics.build_material_financial_release(
        run_id="RUN-1", **bundle, judgments=[], selected_formulas=frozenset(used)
    )
    return dict(
        run_id="RUN-1",
        run_as_of=date(2026, 9, 4),
        **deepcopy(bundle),
        metrics=list(metrics),
        claims=list(claims),
        judgments=[],
        proof_requirements={
            c.calculation_id: ProofRequirement.NOT_REQUIRED for c in bundle["calculations"]
        },
        requirement_context={
            **requirement_context(scheme, []),
            "report_metric_requirements": contract.model_dump(mode="json"),
            "used_metric_ids": list(used),
        },
    )


def review(data):
    return IndependentFinancialReviewer().review(review_id="REVIEW", **data)


def release(data, reviewed):
    return ReleaseGate().evaluate(
        review=reviewed,
        proofs={},
        **{k: v for k, v in data.items() if k not in {"run_id", "calculations"}},
        calculations={c.calculation_id: c for c in data["calculations"]},
    )


async def test_rmr01_02_10_11_exact_singleton(bundle):
    data = inputs(bundle)
    result = review(data)
    assert result.status.value == "PASS"
    assert release(data, result).allowed
    assert len(data["metrics"]) == 1
    assert data["metrics"][0].formula_id == GROWTH
    assert len(result.reviewed_calculation_refs) == 2
    assert result.reviewed_metric_refs == ["METRIC-GROWTH"]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "period",
        "issuer",
        "unit",
        "lineage",
        "version",
        "implementation",
        "run",
        "value",
    ],
)
async def test_rmr03_08_assurance_rejects(bundle, mutation):
    data = inputs(bundle)
    reviewed = review(data)
    if mutation == "missing":
        data["metrics"] = []
    elif mutation == "duplicate":
        data["metrics"].append(data["metrics"][0].model_copy(update={"metric_id": "OTHER"}))
    elif mutation == "period":
        data["metrics"][0] = data["metrics"][0].model_copy(update={"period": "FY2024"})
    elif mutation == "issuer":
        for e in data["evidence"]:
            e.object_id = "OBJ-FOREIGN"
    elif mutation == "unit":
        data["metrics"][0] = data["metrics"][0].model_copy(
            update={"canonical_unit": FinancialUnit.INDEX}
        )
    elif mutation == "lineage":
        data["evidence"] = []
    elif mutation == "version":
        data["calculations"][0].capability_version = "999"
    elif mutation == "implementation":
        data["calculations"][0].implementation_hash = "sha256:foreign"
    elif mutation == "run":
        data["calculations"][0].run_id = "RUN-FOREIGN"
    elif mutation == "value":
        data["calculations"][0].output_value = "not-numeric"
    with pytest.raises((BindingDenied, ValueError)) as failure:
        review(data)
    if mutation == "missing":
        assert failure.value.code == "REPORT_SOURCE_MAP_INCOMPLETE"
    assert not release(data, reviewed).allowed


async def test_rmr12_13_optional_use_is_validated(bundle):
    contract, scheme = resolve(optional_metric_ids=[MARGIN])
    data = inputs(bundle, contract=contract, scheme=scheme)
    assert review(data).status.value == "PASS"
    data = inputs(bundle, contract=contract, scheme=scheme, used=[GROWTH, MARGIN])
    assert review(data).status.value == "PASS"
    data["calculations"][1].input_evidence_ids = ["missing"]
    with pytest.raises(BindingDenied):
        review(data)


@pytest.mark.parametrize("enabled", [False, True])
async def test_rmr14_15_frozen_condition(bundle, enabled):
    contract, scheme = resolve(
        conditional_requirements=[
            dict(
                condition_ref="section:ebitda_margin",
                metric_id=MARGIN,
                requirement_ref="request:margin",
            )
        ],
        enabled_condition_refs=["section:ebitda_margin"] if enabled else [],
    )
    assert (MARGIN in contract.resolved_required_metric_ids) == enabled
    data = inputs(bundle, contract=contract, scheme=scheme)
    assert review(data).status.value == "PASS"
    if enabled:
        data["metrics"] = data["metrics"][:1]
        with pytest.raises(BindingDenied, match="REPORT_SOURCE_MAP_INCOMPLETE"):
            review(data)


async def test_rmr16_tamper_and_retained_review(bundle):
    contract, _ = resolve()
    changed = contract.model_copy(update={"optional_metric_ids": (MARGIN,)})
    with pytest.raises(ValueError):
        FrozenReportMetricRequirementsV1.model_validate(changed.model_dump())
    data = inputs(bundle)
    result = review(data)
    other, _ = resolve(optional_metric_ids=[MARGIN])
    data["requirement_context"]["report_metric_requirements"] = other.model_dump(mode="json")
    assert not release(data, result).allowed


async def test_rmr17_no_universal_growth(bundle):
    contract, scheme = resolve(required_metric_ids=[MARGIN])
    data = inputs(bundle, contract=contract, scheme=scheme)
    assert review(data).status.value == "PASS"
    assert [m.formula_id for m in data["metrics"]] == [MARGIN]


async def test_rmr18_order_independence(bundle, monkeypatch):
    before = inputs(bundle)["metrics"]
    monkeypatch.setattr(
        financial_metrics, "MATERIAL_FORMULAS", tuple(reversed(financial_metrics.MATERIAL_FORMULAS))
    )
    assert inputs(bundle)["metrics"] == before
    assert review(inputs(bundle)).status.value == "PASS"


@pytest.mark.parametrize(
    "change",
    [
        {"required_metric_ids": [GROWTH, GROWTH]},
        {"schema_version": "unknown"},
        {"report_mode": "ALL"},
        {"enabled_condition_refs": ["unknown"]},
        {"required_metric_ids": ["undefined_v1"]},
        {"optional_metric_ids": [GROWTH]},
    ],
)
def test_invalid_draft_rejected(change):
    with pytest.raises(BindingDenied):
        resolve(**change)


def test_marker_boundary_and_legacy_serialization():
    contract, _ = resolve()
    assert "report_metric_requirements" not in ScenarioProfile(task_categories=()).model_dump()
    assert report_metric_value([], None) is None
    for markers, payload in [
        ([REPORT_METRIC_MARKER], None),
        ([], contract),
        (["frozen_report_metric_requirements/v2"], contract),
    ]:
        with pytest.raises(BindingDenied):
            report_metric_value(markers, payload)


async def test_must_prove_obligation_never_dropped(bundle):
    data = inputs(bundle)
    data["proof_requirements"]["GROWTH"] = ProofRequirement.MUST_PROVE
    reviewed = review(data)
    assert reviewed.required_proof_calculation_refs == ["GROWTH"]
    assert not release(data, reviewed).allowed


async def test_report_cannot_use_deterministic_review_label(bundle):
    data = inputs(bundle)
    reviewed = review(data).model_copy(
        update={
            "reviewer": "deterministic-reviewer",
            "checks": [],
            "reviewed_metric_refs": [],
            "reviewed_claim_refs": [],
            "required_proof_calculation_refs": [],
        }
    )
    assert not release(data, reviewed).allowed


async def test_rmr17_margin_without_growth_calculation(bundle):
    contract, scheme = resolve(required_metric_ids=[MARGIN])
    bundle["calculations"] = [c for c in bundle["calculations"] if c.formula_id == MARGIN]
    data = inputs(bundle, contract=contract, scheme=scheme)
    assert review(data).status.value == "PASS"
    assert release(data, review(data)).allowed


@pytest.mark.parametrize(
    "field,value",
    [
        ("actuality", "ESTIMATE"),
        ("period_basis", "QUARTER"),
    ],
)
async def test_rmr07_semantic_type(bundle, field, value):
    from src.domain.enums import FinancialActuality, FinancialPeriodBasis

    enum = FinancialActuality if field == "actuality" else FinancialPeriodBasis
    data = inputs(bundle)
    changes = {field: enum(value)}
    if field == "period_basis":
        changes["period"] = "Q1FY2026"
    data["metrics"][0] = data["metrics"][0].model_copy(update=changes)
    with pytest.raises(BindingDenied):
        review(data)


def test_confirm_rejects_redigested_draft_business_change():
    from src.application.execution_profiles import validate_report_draft_correspondence
    from src.domain.node_binding import digest

    contract, _ = resolve(optional_metric_ids=[MARGIN])
    data = contract.model_dump()
    data["resolved_required_metric_ids"] = (MARGIN,)
    data["optional_metric_ids"] = (GROWTH,)
    data["contract_digest"] = digest(
        {k: v for k, v in data.items() if k != "contract_digest"},
        "frozen-report-metric-requirements/v1",
    )
    tampered = FrozenReportMetricRequirementsV1.model_validate(data)
    goal = ResearchGoal(
        goal_id="GOAL",
        research_object_id="OBJ-NVDA",
        goal_text="One metric",
        as_of=date(2026, 9, 4),
        preferences={
            "report_metric_requirements": {
                "required_metric_ids": [GROWTH],
                "optional_metric_ids": [MARGIN],
                "period": "FY2026",
            }
        },
    )
    with pytest.raises(BindingDenied):
        validate_report_draft_correspondence(tampered, goal)


async def test_nonreport_calculation_obligation_preserved(bundle):
    data = inputs(bundle)
    data["requirement_context"]["required_calculations"] = ["explicit_missing_capability"]
    assert review(data).status.value == "BLOCK"
