# SPDX-FileCopyrightText: 2024-2026 AI4Finance Foundation
# SPDX-License-Identifier: Apache-2.0

"""Controlled deterministic SVG chart port inspired by pinned FinRobot charts.

This module reuses the audited presentation concept and palette direction, not
the upstream pandas/matplotlib implementation.  It has no provider, network,
LLM, configuration, or database dependencies and accepts only the project's
post-release ``CanonicalReportDTO`` through the public adapter.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from html import escape
from pathlib import Path

from pydantic import ConfigDict

from src.adapters.finrobot.audit import (
    FINROBOT_PINNED_COMMIT,
    FINROBOT_REPOSITORY,
    FinRobotAuditEntry,
)
from src.adapters.finrobot.pinned import PinnedFinRobotAdapter
from src.data.hashing import canonical_json
from src.domain.base import DomainModel, JsonObject
from src.domain.financial_semantics import metric_semantics_hash
from src.domain.report import CanonicalReportDTO, ReportArtifactRecord

FINROBOT_CHART_SOURCE = "finrobot_equity/core/src/modules/chart_generator.py"
FINROBOT_CHART_SYMBOLS = (
    "generate_revenue_ebitda_chart",
    "generate_ev_ebitda_peer_chart",
    "generate_technical_indicators_chart",
)
SVG_RENDERER_VERSION = "vfas-finrobot-svg-port-1.0.0"
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_MAX_METRICS = 12


class ChartRenderError(RuntimeError):
    pass


class ChartDataUnavailableError(ChartRenderError):
    pass


class ChartOutputPathError(ChartRenderError):
    pass


class ChartBackendArtifact(DomainModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_ref: str
    content_hash: str
    semantic_hash: str
    metric_semantics_hash: str
    size_bytes: int
    renderer_version: str
    upstream_repository: str
    upstream_commit: str
    upstream_source: str
    upstream_symbols: list[str]
    license: str


class RenderedChartArtifact(DomainModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record: ReportArtifactRecord
    upstream_repository: str
    upstream_commit: str
    upstream_source: str
    upstream_symbols: list[str]
    license: str


class DeterministicSVGChartBackend:
    """Concrete no-network backend for the audited ``charts.render`` operation."""

    def __init__(self, output_root: Path) -> None:
        root = output_root.expanduser().resolve()
        if root.exists() and not root.is_dir():
            raise ChartOutputPathError("chart output root exists and is not a directory")
        self._output_root = root

    @property
    def output_root(self) -> Path:
        return self._output_root

    async def invoke(self, entry: FinRobotAuditEntry, inputs: JsonObject) -> ChartBackendArtifact:
        if entry.operation_id != "charts.render":
            raise ChartRenderError("SVG chart backend only supports charts.render")
        if entry.source_module != FINROBOT_CHART_SOURCE:
            raise ChartRenderError("audited FinRobot chart source does not match backend pin")
        if set(inputs) != {"canonical_report"}:
            raise TypeError("chart backend accepts only serialized CanonicalReportDTO input")
        report = CanonicalReportDTO.model_validate(inputs["canonical_report"])
        metrics = _financial_summary_metrics(report)
        released_metric_hash = metric_semantics_hash(tuple(report.released_metrics))
        semantic_hash = _sha256(
            canonical_json(
                {
                    "renderer_version": SVG_RENDERER_VERSION,
                    "upstream_commit": FINROBOT_PINNED_COMMIT,
                    "canonical_record_id": report.canonical_record_id,
                    "released_result_id": report.released_result_id,
                    "research_object": report.research_object,
                    "metrics": [(label, str(value)) for label, value in metrics],
                    "metric_semantics_hash": released_metric_hash,
                }
            )
        )
        svg = _render_svg(report, metrics, semantic_hash=semantic_hash)
        content = svg.encode("utf-8")
        content_hash = _sha256(content)
        target = self._target(report, content_hash)
        _write_content_addressed(target, content, root=self._output_root)
        return ChartBackendArtifact(
            artifact_ref=str(target),
            content_hash=content_hash,
            semantic_hash=semantic_hash,
            metric_semantics_hash=released_metric_hash,
            size_bytes=len(content),
            renderer_version=SVG_RENDERER_VERSION,
            upstream_repository=FINROBOT_REPOSITORY,
            upstream_commit=FINROBOT_PINNED_COMMIT,
            upstream_source=FINROBOT_CHART_SOURCE,
            upstream_symbols=list(FINROBOT_CHART_SYMBOLS),
            license="Apache-2.0",
        )

    def _target(self, report: CanonicalReportDTO, content_hash: str) -> Path:
        run_segment = _safe_segment(report.run_id, name="run_id")
        canonical_segment = _safe_segment(
            report.canonical_record_id,
            name="canonical_record_id",
        )
        digest = content_hash.removeprefix("sha256:")[:20]
        target = (
            self._output_root
            / "runs"
            / run_segment
            / "charts"
            / canonical_segment
            / f"financial-summary-{digest}.svg"
        )
        resolved = target.resolve()
        try:
            resolved.relative_to(self._output_root)
        except ValueError as exc:  # pragma: no cover - safe segments make this defensive
            raise ChartOutputPathError("chart target escapes configured output root") from exc
        return resolved


class CanonicalReportChartAdapter:
    """Typed public boundary over the existing exact-pin FinRobot adapter."""

    def __init__(self, adapter: PinnedFinRobotAdapter) -> None:
        if adapter.source_revision != FINROBOT_PINNED_COMMIT:
            raise ValueError("chart adapter is not bound to the audited FinRobot revision")
        self._adapter = adapter

    async def render(self, report: CanonicalReportDTO) -> RenderedChartArtifact:
        if not isinstance(report, CanonicalReportDTO):
            raise TypeError("chart renderer input must be CanonicalReportDTO")
        raw_result = await self._adapter.execute(
            "charts.render",
            {"canonical_report": report.model_dump(mode="python")},
        )
        result = ChartBackendArtifact.model_validate(raw_result)
        if result.upstream_commit != FINROBOT_PINNED_COMMIT:
            raise ChartRenderError("chart artifact provenance does not match the audited pin")
        if result.renderer_version != SVG_RENDERER_VERSION:
            raise ChartRenderError("chart artifact renderer version is not supported")
        artifact_id = f"CHART-{result.content_hash.removeprefix('sha256:')[:24]}"
        record = ReportArtifactRecord(
            artifact_id=artifact_id,
            run_id=report.run_id,
            artifact_type="image/svg+xml",
            artifact_ref=result.artifact_ref,
            content_hash=result.content_hash,
            semantic_hash=result.semantic_hash,
            metric_semantics_hash=result.metric_semantics_hash,
            renderer_version=result.renderer_version,
            canonical_record_id=report.canonical_record_id,
            released_result_id=report.released_result_id,
            size_bytes=result.size_bytes,
        )
        return RenderedChartArtifact(
            record=record,
            upstream_repository=result.upstream_repository,
            upstream_commit=result.upstream_commit,
            upstream_source=result.upstream_source,
            upstream_symbols=result.upstream_symbols,
            license=result.license,
        )


def _financial_summary_metrics(report: CanonicalReportDTO) -> tuple[tuple[str, Decimal], ...]:
    if report.released_metrics:
        return tuple(
            (
                (
                    f"{metric.name} [{metric.period}; {metric.as_of.isoformat()}; "
                    f"{metric.display_unit}; {metric.metric_id}]"
                ),
                Decimal(metric.display_value),
            )
            for metric in report.released_metrics[:_MAX_METRICS]
        )
    summary = report.structured_financial_results.get("financial_summary")
    if not isinstance(summary, Mapping):
        raise ChartDataUnavailableError("canonical financial_summary is unavailable")
    metrics = _flatten_numeric(summary)
    if not metrics:
        raise ChartDataUnavailableError("canonical financial_summary has no numeric metrics")
    return tuple(metrics[:_MAX_METRICS])


def _flatten_numeric(
    value: JsonObject,
    *,
    prefix: tuple[str, ...] = (),
) -> list[tuple[str, Decimal]]:
    output: list[tuple[str, Decimal]] = []
    for key in sorted(value):
        item = value[key]
        path = (*prefix, str(key))
        if isinstance(item, Mapping):
            output.extend(_flatten_numeric(item, prefix=path))
            continue
        number = _optional_decimal(item)
        if number is not None:
            output.append((" / ".join(path), number))
    return output


def _optional_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        raise ChartRenderError("canonical chart metrics must be finite")
    return number


def _render_svg(
    report: CanonicalReportDTO,
    metrics: tuple[tuple[str, Decimal], ...],
    *,
    semantic_hash: str,
) -> str:
    width = 960
    row_height = 48
    height = 124 + len(metrics) * row_height
    plot_left = Decimal(300)
    plot_width = Decimal(520)
    values = [value for _, value in metrics]
    low = min(Decimal(0), *values)
    high = max(Decimal(0), *values)
    with localcontext() as context:
        context.prec = 50
        span = high - low
        scale = Decimal(0) if span == 0 else plot_width / span
        zero_x = plot_left if span == 0 else plot_left + (-low * scale)

        rows: list[str] = []
        for index, (label, value) in enumerate(metrics):
            y = Decimal(94 + index * row_height)
            value_x = zero_x if span == 0 else plot_left + ((value - low) * scale)
            bar_x = min(zero_x, value_x)
            bar_width = abs(value_x - zero_x)
            rows.extend(
                (
                    f'<text class="metric" x="20" y="{_coord(y + 19)}">{escape(label)}</text>',
                    f'<rect class="bar" x="{_coord(bar_x)}" y="{_coord(y)}" '
                    f'width="{_coord(bar_width)}" height="28" rx="4"/>',
                    f'<text class="value" x="842" y="{_coord(y + 19)}">'
                    f"{escape(_display_decimal(value))}</text>",
                )
            )

    metadata = escape(
        "; ".join(
            (
                f"renderer={SVG_RENDERER_VERSION}",
                "upstream_project=FinRobot",
                f"upstream_commit={FINROBOT_PINNED_COMMIT}",
                f"upstream_source={FINROBOT_CHART_SOURCE}",
                f"canonical_record_id={report.canonical_record_id}",
                f"released_result_id={report.released_result_id}",
                f"semantic_hash={semantic_hash}",
                "license=Apache-2.0",
            )
        )
    )
    title = escape(f"{report.research_object} Canonical Financial Metrics")
    return "\n".join(
        (
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img">',
            f"<title>{title}</title>",
            f"<metadata>{metadata}</metadata>",
            "<style>"
            ".background{fill:#ffffff}.title{font:700 22px sans-serif;fill:#002855}"
            ".metric{font:14px sans-serif;fill:#1f2937}.value{font:600 14px monospace;fill:#111827}"
            ".bar{fill:#00629b}.axis{stroke:#64748b;stroke-width:1}"
            "</style>",
            f'<rect class="background" x="0" y="0" width="{width}" height="{height}"/>',
            f'<text class="title" x="20" y="42">{title}</text>',
            f'<line class="axis" x1="{_coord(zero_x)}" y1="76" '
            f'x2="{_coord(zero_x)}" y2="{height - 18}"/>',
            *rows,
            "</svg>",
            "",
        )
    )


def _safe_segment(value: str, *, name: str) -> str:
    if value in {".", ".."} or not _SAFE_SEGMENT.fullmatch(value):
        raise ChartOutputPathError(f"{name} is not safe for artifact storage")
    return value


def _write_content_addressed(target: Path, content: bytes, *, root: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != content:
            raise ChartRenderError("content-addressed chart hash collision")
        return
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".chart-",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        resolved_temporary = temporary_path.resolve()
        try:
            resolved_temporary.relative_to(root)
        except ValueError as exc:  # pragma: no cover - tempfile dir is already controlled
            raise ChartOutputPathError("temporary chart path escaped output root") from exc
        temporary_path.replace(target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _coord(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _display_decimal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return "0" if value.is_zero() else rendered
