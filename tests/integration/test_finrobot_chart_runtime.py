from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters.finrobot.audit import FINROBOT_PINNED_COMMIT
from src.adapters.finrobot.charts import (
    SVG_RENDERER_VERSION,
    CanonicalReportChartAdapter,
    DeterministicSVGChartBackend,
)
from src.adapters.finrobot.pinned import PinnedFinRobotAdapter
from src.domain.report import CanonicalReportDTO


def inspect_artifact(path: Path) -> tuple[bool, int, str]:
    return path.is_file(), path.stat().st_size, path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_real_pinned_adapter_runtime_call_produces_svg_artifact(tmp_path: Path) -> None:
    backend = DeterministicSVGChartBackend(tmp_path / "artifacts")
    runtime_adapter = PinnedFinRobotAdapter(
        backend=backend,
        source_revision=FINROBOT_PINNED_COMMIT,
    )
    chart_runtime = CanonicalReportChartAdapter(runtime_adapter)
    report = CanonicalReportDTO(
        canonical_record_id="CAN-P3-NVDA",
        released_result_id="REL-P3-NVDA",
        run_id="RUN-P3-NVDA",
        research_object="NVDA",
        structured_financial_results={
            "financial_summary": {
                "revenue_growth": 0.114,
                "ebitda_margin": 0.621,
                "technical_indicators": {
                    "rsi_14": 58.2,
                    "volume_ratio_20": 1.08,
                },
            }
        },
        calculation_refs=["CALC-GROWTH", "CALC-MARGIN", "CALC-RSI", "CALC-VOLUME"],
        proof_refs=["PROOF-REVENUE-GROWTH"],
        provenance={"source": "released_and_canonical_only"},
    )

    artifact = await chart_runtime.render(report)

    path = Path(artifact.record.artifact_ref)
    is_file, size, content = inspect_artifact(path)
    assert is_file
    assert size == artifact.record.size_bytes
    assert artifact.record.content_hash.startswith("sha256:")
    assert artifact.record.renderer_version == SVG_RENDERER_VERSION
    assert artifact.upstream_commit == FINROBOT_PINNED_COMMIT
    assert "NVDA Canonical Financial Metrics" in content
