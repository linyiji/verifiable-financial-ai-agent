from __future__ import annotations

import ast
import hashlib
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.adapters.finrobot.audit import FINROBOT_PINNED_COMMIT
from src.adapters.finrobot.professional_reporting import (
    RENDERER_VERSION,
    UPSTREAM_ATTRIBUTION,
    ArtifactPathError,
    CanonicalReportMapper,
    ControlledArtifactStore,
    ProfessionalHTMLRenderer,
    ProfessionalPDFRenderer,
    ProfessionalReportPublisher,
)
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.enums import FinancialActuality, FinancialPeriodBasis, FinancialUnit
from src.domain.financial_semantics import MaterialFinancialClaim, ReleasedFinancialMetric
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.report import ReportSourceContribution


class StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.sections = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        self.tags.append(tag)
        if tag == "section":
            self.sections += 1


def records(*, malicious: bool = False):
    injected = '<script>alert("owned")</script>' if malicious else "Accelerating demand"
    canonical = CanonicalExecutionRecord(
        record_id="CAN-1",
        run_id="RUN-1",
        object_snapshot_ref="OBJ-NVDA-1",
        goal_ref="GOAL-1",
        scheme_ref="SCHEME-1",
        planned_graph={"nodes": ["TASK-1"]},
        actual_graph={"nodes": ["TASK-1"]},
        task_refs=["TASK-1"],
        evidence_refs=["EVD-REVENUE", "EVD-MARGIN"],
        calculation_refs=["CALC-GROWTH", "CALC-MARGIN"],
        decision_refs=["DECISION-1"],
        generated_capability_refs=["GEN-MARGIN"],
        review_refs=["REVIEW-1"],
        proof_refs=["PROOF-GROWTH"],
        trace_refs=["TRACE-1"],
        runtime_outcome="COMPLETED",
        created_at=datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
    )
    released = ReleasedResearchResult(
        result_id="REL-1",
        run_id="RUN-1",
        structured_financial_results={
            "research_object": "NVDA",
            "financial_summary": {
                "revenue": "$130.5B",
                "gross_margin": "0.734",
                "rating": "RELEASED-HOLD",
            },
        },
        released_claims=[{"claim": injected, "evidence_refs": ["EVD-REVENUE"]}],
        judgments=[{"judgment": "Demand remains strong", "decision_ref": "DECISION-1"}],
        assumption_refs=["ASSUMPTION-1"],
        risk_output={"risks": ["Customer concentration", "Export controls"]},
        limitations=["Forecast uncertainty", injected if malicious else "Point-in-time data"],
        released_at=datetime(2026, 9, 4, 8, 30, tzinfo=UTC),
    )
    return released, canonical


def test_mapper_uses_only_released_and_canonical_records_and_returns_frozen_dto() -> None:
    released, canonical = records()
    dto = CanonicalReportMapper.map(released, canonical)

    assert dto.research_object == "NVDA"
    assert dto.structured_financial_results == released.structured_financial_results
    assert dto.calculation_refs == canonical.calculation_refs
    assert dto.proof_refs == canonical.proof_refs
    assert dto.provenance["evidence_refs"] == canonical.evidence_refs
    assert dto.provenance["assumption_refs"] == released.assumption_refs
    released.structured_financial_results["financial_summary"]["revenue"] = "MUTATED"
    assert dto.structured_financial_results["financial_summary"]["revenue"] == "$130.5B"
    rendered = ProfessionalHTMLRenderer().render(dto).decode("utf-8")
    assert "FrozenJsonSequence" not in rendered
    assert "<ul>" in rendered
    with pytest.raises(ValidationError):
        dto.research_object = "AMD"


def test_mapper_rejects_cross_run_records() -> None:
    released, canonical = records()
    mismatched = canonical.model_copy(update={"run_id": "RUN-OTHER"})
    with pytest.raises(ValueError, match="share run_id"):
        CanonicalReportMapper.map(released, mismatched)


def test_html_is_self_contained_structured_and_escapes_all_released_content() -> None:
    released, canonical = records(malicious=True)
    dto = CanonicalReportMapper.map(released, canonical)
    before = dto.model_dump_json()
    rendered = ProfessionalHTMLRenderer().render(dto).decode("utf-8")

    parser = StructureParser()
    parser.feed(rendered)
    assert parser.tags[0] == "html"
    assert {"head", "body", "article", "header", "main", "footer", "section", "dl"} <= set(
        parser.tags
    )
    assert parser.sections == 5
    assert "default-src 'none'" in rendered
    assert "https://" not in rendered
    assert "<script>alert" not in rendered
    assert "&lt;script&gt;alert(&quot;owned&quot;)&lt;/script&gt;" in rendered
    assert "RELEASED-HOLD" not in rendered
    assert canonical.record_id in rendered
    assert released.result_id in rendered
    assert FINROBOT_PINNED_COMMIT in rendered
    assert dto.model_dump_json() == before


def test_pdf_has_valid_signature_released_content_and_deterministic_bytes() -> None:
    released, canonical = records()
    dto = CanonicalReportMapper.map(released, canonical)
    renderer = ProfessionalPDFRenderer()

    first = renderer.render(dto)
    second = renderer.render(dto)

    assert first.startswith(b"%PDF-1.4")
    assert first.rstrip().endswith(b"%%EOF")
    assert b"xref" in first
    assert b"NVDA" in first
    assert b"CALC-GROWTH" in first
    assert b"PROOF-GROWTH" in first
    assert b"RELEASED-HOLD" not in first
    assert first == second
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    assert len(first) > 3_000


def test_publisher_writes_controlled_nonempty_artifacts_with_stable_hashes(
    tmp_path: Path,
) -> None:
    released, canonical = records()
    dto = CanonicalReportMapper.map(released, canonical)
    store = ControlledArtifactStore(tmp_path / "artifacts")
    publisher = ProfessionalReportPublisher(store)

    first = publisher.publish(dto)
    second = publisher.publish(dto)
    html_path = store.resolve(first.html.artifact_ref)
    pdf_path = store.resolve(first.pdf.artifact_ref)

    assert html_path.is_file() and html_path.stat().st_size > 0
    assert pdf_path.is_file() and pdf_path.stat().st_size > 0
    assert first.html.size_bytes == html_path.stat().st_size
    assert first.pdf.size_bytes == pdf_path.stat().st_size
    assert first.html.content_hash == second.html.content_hash
    assert first.pdf.content_hash == second.pdf.content_hash
    assert first.html.semantic_hash == first.pdf.semantic_hash
    assert first.pdf.semantic_hash != first.pdf.content_hash
    assert first.html.renderer_version == RENDERER_VERSION
    assert first.pdf.renderer_version == RENDERER_VERSION
    assert first.html.canonical_record_id == canonical.record_id
    assert first.pdf.released_result_id == released.result_id
    assert _hash(html_path.read_bytes()) == first.html.content_hash
    assert _hash(pdf_path.read_bytes()) == first.pdf.content_hash


def test_html_only_report_links_metric_to_exact_safe_execution_and_back(tmp_path: Path) -> None:
    released, canonical = records()
    source = ReportSourceContribution(
        run_id="RUN-1",
        report_id="REL-1",
        report_anchor="metric-revenue-growth",
        execution_anchor="execution-AGOUT-1",
        report_section="Financial Analysis / Revenue Growth",
        actor_id="fundamental_analyst",
        task_id="TASK-1",
        agent_output_id="AGOUT-1",
        agent_output_artifact_id=f"sha256:{'a' * 64}",
        execution_event_id="EVENT-TASK-1-COMPLETED",
        provider="test-provider",
        actual_model="test-model",
        input_tokens=100,
        output_tokens=40,
        duration_ms=12,
        input_refs=("EVD-REVENUE", "CALC-GROWTH"),
        observable_process=("Strict structured output validation passed.",),
        output_summary="收入增长由权威计算支持。",
        key_findings=("当前收入高于上期。",),
        metric_name="Revenue Growth",
        metric_value="65.47",
        metric_unit="%",
        calculation_id="CALC-GROWTH",
        formula_id="revenue_growth_v1",
        evidence_refs=("EVD-REVENUE",),
        review_id="REVIEW-1",
        review_status="PASS",
        proof_id="PROOF-GROWTH",
        proof_status="VERIFIED",
    )
    dto = CanonicalReportMapper.map(
        released,
        canonical,
        company_name="NVIDIA Corporation",
        symbol="NVDA",
        as_of=date(2026, 9, 4),
        source_contributions=(source,),
    ).model_copy(
        update={
            "released_metrics": (
                ReleasedFinancialMetric(
                    metric_id="METRIC-GROWTH",
                    calculation_id="CALC-GROWTH",
                    name="Revenue Growth",
                    canonical_value="0.6547",
                    canonical_unit=FinancialUnit.RATIO,
                    display_value="65.47",
                    display_unit="%",
                    period="FY2026",
                    period_basis=FinancialPeriodBasis.FY,
                    actuality=FinancialActuality.ACTUAL,
                    as_of=date(2026, 1, 31),
                    currency="USD",
                    formula_id="revenue_growth_v1",
                    capability_id="revenue_growth",
                    evidence_ids=("EVD-REVENUE",),
                ),
            )
        }
    )
    metric = dto.released_metrics[0]
    dto = dto.model_copy(
        update={
            "material_claims": (
                MaterialFinancialClaim(
                    claim_id="CLAIM-GROWTH",
                    run_id="RUN-1",
                    claim_type="metric",
                    statement="Reviewed revenue growth is 65.47 %.",
                    metric_id=metric.metric_id,
                    value=metric.canonical_value,
                    unit=metric.canonical_unit,
                    period=metric.period,
                    period_basis=metric.period_basis,
                    actuality=metric.actuality,
                    as_of=metric.as_of,
                    currency=metric.currency,
                    calculation_refs=(metric.calculation_id,),
                    evidence_refs=metric.evidence_ids,
                ),
            )
        }
    )
    store = ControlledArtifactStore(tmp_path / "artifacts")
    publisher = ProfessionalReportPublisher(store)

    artifact = publisher.publish_html(dto)
    rendered = publisher.read_verified(artifact).decode("utf-8")

    assert 'id="metric-revenue-growth"' in rendered
    assert 'href="#execution-AGOUT-1">查看研究来源</a>' in rendered
    assert 'id="execution-AGOUT-1"' in rendered
    assert 'href="#metric-revenue-growth">返回报告</a>' in rendered
    assert "NVIDIA Corporation" in rendered
    assert "65.47 %" in rendered
    assert "Reviewed revenue growth is 65.47 %." in rendered
    assert source.output_summary not in rendered
    assert source.key_findings[0] not in rendered
    assert "EVENT-TASK-1-COMPLETED" in rendered
    assert artifact.run_id == "RUN-1"
    assert artifact.anchor_manifest_hash is not None
    assert artifact.source_contributions == [source]
    assert "prompt" not in rendered.lower()
    assert "chain-of-thought" not in rendered.lower()


def test_artifact_store_rejects_path_escape_and_symlink(tmp_path: Path) -> None:
    store = ControlledArtifactStore(tmp_path / "artifacts")
    with pytest.raises(ArtifactPathError):
        store.write("../outside.pdf", b"pdf")
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactPathError, match="symlink"):
        store.write("linked/report.pdf", b"pdf")


def test_renderer_module_has_no_refetch_llm_or_database_imports() -> None:
    module_path = Path("src/adapters/finrobot/professional_reporting.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    forbidden_prefixes = (
        "httpx",
        "requests",
        "urllib",
        "socket",
        "sqlalchemy",
        "src.adapters.fmp",
        "src.adapters.llm",
        "src.infrastructure.database",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported_modules
        for prefix in forbidden_prefixes
    )
    source = module_path.read_text(encoding="utf-8")
    assert "FMP_API_KEY" not in source
    assert "complete_structured" not in source
    assert "ValuationEngine" not in source
    assert "rating-badge" not in source
    assert UPSTREAM_ATTRIBUTION in ProfessionalHTMLRenderer().render(
        CanonicalReportMapper.map(*records())
    ).decode("utf-8")


def _hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
