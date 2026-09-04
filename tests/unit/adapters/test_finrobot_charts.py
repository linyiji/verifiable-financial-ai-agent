from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from xml.etree import ElementTree

import pytest

from src.adapters.finrobot.audit import FINROBOT_PINNED_COMMIT, audit_entry_for_operation
from src.adapters.finrobot.charts import (
    FINROBOT_CHART_SOURCE,
    SVG_RENDERER_VERSION,
    CanonicalReportChartAdapter,
    ChartDataUnavailableError,
    ChartOutputPathError,
    DeterministicSVGChartBackend,
)
from src.adapters.finrobot.pinned import PinnedFinRobotAdapter
from src.domain.report import CanonicalReportDTO


def canonical_report(**updates: object) -> CanonicalReportDTO:
    values: dict[str, object] = {
        "canonical_record_id": "CAN-RUN-1",
        "released_result_id": "REL-RUN-1",
        "run_id": "RUN-1",
        "research_object": "NVDA <script>alert(1)</script>",
        "structured_financial_results": {
            "financial_summary": {
                "ebitda_margin": 0.61,
                "revenue_growth": 0.114,
                "status": "reviewed",
            },
            "non_chart_section": {"should_not_render": 999},
        },
        "released_claims": [{"claim_id": "CLAIM-1"}],
        "judgments": [{"judgment_id": "JUDG-1"}],
        "risk_output": {"risk_score": 777},
        "limitations": ["Not investment advice."],
        "calculation_refs": ["CALC-1", "CALC-2"],
        "proof_refs": ["PROOF-1"],
    }
    values.update(updates)
    return CanonicalReportDTO.model_validate(values)


def renderer(output_root: Path) -> CanonicalReportChartAdapter:
    backend = DeterministicSVGChartBackend(output_root)
    pinned = PinnedFinRobotAdapter(
        backend=backend,
        source_revision=FINROBOT_PINNED_COMMIT,
    )
    return CanonicalReportChartAdapter(pinned)


def read_artifact(path: Path) -> bytes:
    return path.read_bytes()


def svg_files(path: Path) -> list[Path]:
    return list(path.rglob("*.svg"))


@pytest.mark.asyncio
async def test_svg_is_deterministic_escaped_and_content_addressed(tmp_path: Path) -> None:
    report = canonical_report()
    service = renderer(tmp_path / "controlled-artifacts")

    first = await service.render(report)
    second = await service.render(report)

    path = Path(first.record.artifact_ref)
    content = read_artifact(path)
    text = content.decode("utf-8")
    assert first.record.content_hash == second.record.content_hash
    assert first.record.semantic_hash == second.record.semantic_hash
    assert first.record.artifact_ref == second.record.artifact_ref
    assert first.record.content_hash == f"sha256:{hashlib.sha256(content).hexdigest()}"
    assert first.record.size_bytes == len(content) > 0
    assert path.is_relative_to((tmp_path / "controlled-artifacts").resolve())
    assert path.suffix == ".svg"
    assert "NVDA &lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "<script>" not in text
    assert "ebitda_margin" in text
    assert "revenue_growth" in text
    assert "should_not_render" not in text
    assert "999" not in text
    assert "777" not in text
    assert FINROBOT_PINNED_COMMIT in text
    assert "upstream_project=FinRobot" in text
    assert "license=Apache-2.0" in text
    parsed = ElementTree.fromstring(content)
    assert parsed.tag == "{http://www.w3.org/2000/svg}svg"


@pytest.mark.asyncio
async def test_public_renderer_accepts_only_canonical_report_dto(tmp_path: Path) -> None:
    service = renderer(tmp_path)
    with pytest.raises(TypeError, match="CanonicalReportDTO"):
        await service.render(  # type: ignore[arg-type]
            {"run_id": "RUN-1", "financial_summary": {"revenue": 1}}
        )


@pytest.mark.asyncio
async def test_backend_transport_rejects_extra_noncanonical_inputs(tmp_path: Path) -> None:
    backend = DeterministicSVGChartBackend(tmp_path)
    entry = audit_entry_for_operation("charts.render")
    report = canonical_report().model_dump(mode="python")

    with pytest.raises(TypeError, match="only serialized"):
        await backend.invoke(
            entry,
            {"canonical_report": report, "ticker": "NVDA"},
        )


@pytest.mark.asyncio
async def test_no_numeric_financial_summary_fails_without_artifact(tmp_path: Path) -> None:
    report = canonical_report(
        structured_financial_results={"financial_summary": {"status": "not_available"}}
    )

    with pytest.raises(ChartDataUnavailableError, match="no numeric metrics"):
        await renderer(tmp_path).render(report)

    assert svg_files(tmp_path) == []


@pytest.mark.asyncio
async def test_output_identifiers_cannot_escape_controlled_root(tmp_path: Path) -> None:
    report = canonical_report(run_id="../../outside")

    with pytest.raises(ChartOutputPathError, match="run_id"):
        await renderer(tmp_path / "root").render(report)

    assert not (tmp_path / "outside").exists()


@pytest.mark.asyncio
async def test_artifact_record_contains_exact_pin_and_port_provenance(tmp_path: Path) -> None:
    artifact = await renderer(tmp_path).render(canonical_report())

    assert artifact.record.renderer_version == SVG_RENDERER_VERSION
    assert artifact.record.artifact_type == "image/svg+xml"
    assert artifact.record.canonical_record_id == "CAN-RUN-1"
    assert artifact.record.released_result_id == "REL-RUN-1"
    assert artifact.upstream_commit == FINROBOT_PINNED_COMMIT
    assert artifact.upstream_source == FINROBOT_CHART_SOURCE
    assert artifact.upstream_repository.endswith("/FinRobot.git")
    assert artifact.license == "Apache-2.0"


def test_chart_backend_imports_no_provider_network_llm_or_database_modules() -> None:
    source_path = Path(__file__).parents[3] / "src/adapters/finrobot/charts.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    forbidden_prefixes = (
        "requests",
        "httpx",
        "socket",
        "urllib",
        "src.adapters.fmp",
        "src.adapters.llm",
        "src.infrastructure.database",
        "sqlalchemy",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported_modules
        for prefix in forbidden_prefixes
    )
