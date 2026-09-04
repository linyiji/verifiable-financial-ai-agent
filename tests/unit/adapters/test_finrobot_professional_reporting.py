from __future__ import annotations

import ast
import hashlib
from datetime import UTC, datetime
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
from src.domain.released_research_result import ReleasedResearchResult


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
    assert parser.sections == 9
    assert "default-src 'none'" in rendered
    assert "https://" not in rendered
    assert "<script>alert" not in rendered
    assert "&lt;script&gt;alert(&quot;owned&quot;)&lt;/script&gt;" in rendered
    assert "RELEASED-HOLD" in rendered
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
    assert b"RELEASED-HOLD" in first
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
