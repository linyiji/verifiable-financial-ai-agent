"""Controlled professional report port informed by pinned FinRobot layouts.

Presentation structure and visual language are adapted from FinRobot's
``html_renderer.py``, ``html_template_professional.py`` and
``professional_pdf_report.py`` at commit
``d221910096de87579b02f8f0674652bf1a175f51`` (Apache-2.0). This owned port
does not import upstream code: those modules combine rendering with pandas,
provider/file loading, remote assets, and other responsibilities forbidden at
the release boundary.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import tempfile
import textwrap
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel

from src.adapters.finrobot.audit import FINROBOT_PINNED_COMMIT
from src.domain.canonical_execution_record import CanonicalExecutionRecord
from src.domain.financial_semantics import metric_semantics_hash
from src.domain.released_research_result import ReleasedResearchResult
from src.domain.report import (
    CanonicalReportDTO,
    ReportArtifactRecord,
    ReportSourceContribution,
)

RENDERER_VERSION = f"finrobot-professional-port/2.0.0+{FINROBOT_PINNED_COMMIT[:12]}+reviewed-claims"
REPORT_SEMANTIC_SCHEMA = "canonical-report-presentation/v1"
UPSTREAM_ATTRIBUTION = (
    "Presentation design adapted from FinRobot (AI4Finance Foundation), "
    f"Apache-2.0, commit {FINROBOT_PINNED_COMMIT}."
)


class CanonicalReportMappingError(ValueError):
    pass


class ArtifactPathError(ValueError):
    pass


class CanonicalReportMapper:
    """Owned one-way mapping; no provider, LLM, repository, or calculation access."""

    @staticmethod
    def map(
        released: ReleasedResearchResult,
        canonical: CanonicalExecutionRecord,
        *,
        company_name: str | None = None,
        symbol: str | None = None,
        as_of: date | None = None,
        source_contributions: Sequence[ReportSourceContribution] = (),
    ) -> CanonicalReportDTO:
        if released.run_id != canonical.run_id:
            raise CanonicalReportMappingError(
                "ReleasedResearchResult and CanonicalExecutionRecord must share run_id"
            )
        if (
            released.canonical_record_id is not None
            and released.canonical_record_id != canonical.record_id
        ):
            raise CanonicalReportMappingError(
                "ReleasedResearchResult does not reference the supplied canonical record"
            )
        research_object = released.structured_financial_results.get("research_object")
        if not isinstance(research_object, str) or not research_object.strip():
            raise CanonicalReportMappingError(
                "released structured_financial_results must contain research_object"
            )
        if any(
            source.run_id != canonical.run_id or source.report_id != released.result_id
            for source in source_contributions
        ):
            raise CanonicalReportMappingError(
                "report source contributions must share the exact Run and Report identity"
            )
        if len({source.report_anchor for source in source_contributions}) != len(
            source_contributions
        ):
            raise CanonicalReportMappingError("report source anchors must be unique")

        provenance = {
            "semantic_schema": REPORT_SEMANTIC_SCHEMA,
            "runtime_outcome": canonical.runtime_outcome,
            "released_at": released.released_at.isoformat(),
            "object_snapshot_ref": canonical.object_snapshot_ref,
            "goal_ref": canonical.goal_ref,
            "scheme_ref": canonical.scheme_ref,
            "evidence_refs": list(canonical.evidence_refs),
            "decision_refs": list(canonical.decision_refs),
            "agent_output_refs": list(canonical.agent_output_refs),
            "review_refs": list(canonical.review_refs),
            "trace_refs": list(canonical.trace_refs),
            "generated_capability_refs": list(canonical.generated_capability_refs),
            "assumption_refs": list(released.assumption_refs),
        }
        return CanonicalReportDTO(
            canonical_record_id=canonical.record_id,
            released_result_id=released.result_id,
            run_id=canonical.run_id,
            research_object=research_object.strip(),
            company_name=company_name,
            symbol=symbol,
            as_of=as_of,
            structured_financial_results=deepcopy(released.structured_financial_results),
            released_claims=deepcopy(released.released_claims),
            released_metrics=[
                metric.model_dump(mode="python") for metric in released.released_metrics
            ],
            material_claims=[claim.model_dump(mode="python") for claim in released.material_claims],
            material_calculation_dispositions=[
                item.model_dump(mode="python")
                for item in released.material_calculation_dispositions
            ],
            research_source_coverage=(
                released.research_source_coverage.model_dump(mode="python")
                if released.research_source_coverage is not None
                else None
            ),
            judgments=deepcopy(released.judgments),
            risk_output=deepcopy(released.risk_output),
            limitations=deepcopy(released.limitations),
            calculation_refs=list(canonical.calculation_refs),
            proof_refs=list(canonical.proof_refs),
            provenance=provenance,
            source_contributions=tuple(source_contributions),
        )


class ControlledArtifactStore:
    """Write-only report artifact boundary rooted at one explicit directory."""

    def __init__(self, artifact_root: str | Path):
        requested = Path(artifact_root).expanduser()
        if requested == Path(requested.anchor):
            raise ArtifactPathError("filesystem root cannot be used as artifact root")
        requested.mkdir(parents=True, exist_ok=True)
        self.root = requested.resolve(strict=True)
        if not self.root.is_dir():
            raise ArtifactPathError("artifact root must be a directory")

    def write(self, relative_ref: str, content: bytes) -> tuple[str, Path]:
        if not content:
            raise ValueError("report artifact must not be empty")
        relative = PurePosixPath(relative_ref)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ArtifactPathError("artifact path must be a safe relative path")
        target = self.root.joinpath(*relative.parts)
        self._reject_symlink_path(target)
        resolved_parent = target.parent.resolve(strict=False)
        try:
            resolved_parent.relative_to(self.root)
        except ValueError as exc:
            raise ArtifactPathError("artifact path escapes the controlled root") from exc
        resolved_parent.mkdir(parents=True, exist_ok=True)
        self._reject_symlink_path(target)

        if target.exists():
            if not target.is_file() or target.read_bytes() != content:
                raise ArtifactPathError("report artifact bindings are immutable")
            return f"artifact://{relative.as_posix()}", target

        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=resolved_parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o400)
            try:
                os.link(temporary, target)
            except FileExistsError:
                if not target.is_file() or target.read_bytes() != content:
                    raise ArtifactPathError("report artifact bindings are immutable") from None
        finally:
            if temporary.exists():
                temporary.unlink()
        return f"artifact://{relative.as_posix()}", target

    def read_verified(self, record: ReportArtifactRecord) -> bytes:
        target = self.resolve(record.artifact_ref)
        self._reject_symlink_path(target)
        try:
            content = target.read_bytes()
        except OSError as exc:
            raise ArtifactPathError("report artifact is unavailable") from exc
        if len(content) != record.size_bytes or _sha256(content) != record.content_hash:
            raise ArtifactPathError("report artifact failed exact-byte verification")
        return content

    def resolve(self, artifact_ref: str) -> Path:
        prefix = "artifact://"
        if not artifact_ref.startswith(prefix):
            raise ArtifactPathError("unsupported artifact reference")
        relative = PurePosixPath(artifact_ref.removeprefix(prefix))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ArtifactPathError("unsafe artifact reference")
        target = self.root.joinpath(*relative.parts).resolve(strict=False)
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ArtifactPathError("artifact reference escapes the controlled root") from exc
        return target

    def _reject_symlink_path(self, target: Path) -> None:
        current = self.root
        relative = target.relative_to(self.root)
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ArtifactPathError("symlinks are forbidden inside the artifact root")


def _reviewed_metrics(report: CanonicalReportDTO):
    """No legacy prose fallback; claims must close over exact typed metric inputs."""
    metrics = {m.metric_id: m for m in report.released_metrics}
    if len(metrics) != len(report.released_metrics):
        raise CanonicalReportMappingError("Ambiguous released metrics")
    seen = set()
    for claim in report.material_claims:
        metric = metrics.get(claim.metric_id)
        if (
            claim.claim_id in seen
            or claim.run_id != report.run_id
            or metric is None
            or metric.calculation_id not in claim.calculation_refs
            or not set(metric.evidence_ids) <= set(claim.evidence_refs)
            or claim.value != metric.canonical_value
            or claim.unit != metric.canonical_unit
            or claim.period != metric.period
            or claim.period_basis != metric.period_basis
            or claim.actuality != metric.actuality
            or claim.as_of != metric.as_of
            or claim.currency != metric.currency
        ):
            raise CanonicalReportMappingError("Material claim metric binding mismatch")
        seen.add(claim.claim_id)
    used = {c.metric_id for c in report.material_claims}
    return tuple(m for m in report.released_metrics if m.metric_id in used)


class ProfessionalHTMLRenderer:
    """Deterministic, self-contained HTML presentation of one canonical DTO."""

    renderer_version = RENDERER_VERSION

    def render(self, report: CanonicalReportDTO) -> bytes:
        technical_sections = (
            _html_section("Released financial metrics", _reviewed_metrics(report)),
            _html_section("Material claims", report.material_claims),
            _html_section("Research source coverage", report.research_source_coverage),
            _html_section("Limitations", report.limitations),
            _html_section(
                "Verification lineage",
                {
                    "calculation_refs": report.calculation_refs,
                    "proof_refs": report.proof_refs,
                    "provenance": report.provenance,
                },
            ),
        )
        demo_sections = _html_demo_sections(report)
        title = _html_text(report.company_name or report.research_object)
        symbol = _html_text(report.symbol or report.research_object)
        as_of = _html_text(report.as_of.isoformat() if report.as_of is not None else "Not recorded")
        canonical_id = _html_text(report.canonical_record_id)
        released_id = _html_text(report.released_result_id)
        run_id = _html_text(report.run_id)
        attribution = _html_text(UPSTREAM_ATTRIBUTION)
        document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none'; style-src 'unsafe-inline'">
  <title>{title} - Verifiable Financial Research</title>
  <style>
    :root {{ --navy:#0b1b33; --gold:#d2a74a; --ink:#27364b; --muted:#637087;
            --paper:#ffffff; --wash:#f4f6f9; --line:#dce2ea; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--wash); color:var(--ink); font:14px/1.6 Arial,sans-serif; }}
    .report {{ width:min(980px,calc(100% - 32px)); margin:32px auto; background:var(--paper);
               box-shadow:0 12px 36px rgba(11,27,51,.12); }}
    header {{ background:var(--navy); color:white; padding:42px 52px 38px;
              border-bottom:5px solid var(--gold); }}
    .eyebrow {{ color:#ead49a; font-size:11px; font-weight:700; letter-spacing:.16em;
                text-transform:uppercase; }}
    h1 {{ margin:8px 0 4px; font:700 34px/1.18 Georgia,serif; }}
    header p {{ margin:0; color:#d9e0e9; }}
    .identity {{ display:grid; grid-template-columns:repeat(3,1fr); gap:1px;
                 background:var(--line); }}
    .identity div {{ background:white; padding:14px 18px; overflow-wrap:anywhere; }}
    .label {{ display:block; color:var(--muted); font-size:10px; letter-spacing:.08em;
              text-transform:uppercase; }}
    main {{ padding:24px 52px 44px; }}
    section {{ margin:18px 0 28px; break-inside:avoid; }}
    h2 {{ color:var(--navy); font:700 19px/1.3 Georgia,serif; margin:0 0 12px;
          border-left:4px solid var(--gold); padding-left:11px; }}
    h3 {{ color:var(--navy); font-size:13px; margin:16px 0 6px; }}
    dl {{ display:grid; grid-template-columns:minmax(150px,1fr) 2fr; margin:0;
          border-top:1px solid var(--line); }}
    dt,dd {{ margin:0; padding:9px 11px; border-bottom:1px solid var(--line);
             overflow-wrap:anywhere; }}
    dt {{ background:var(--wash); font-weight:700; }}
    ul {{ margin:6px 0; padding-left:22px; }}
    .metric-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
                    gap:12px; }}
    .metric-card {{ border:1px solid var(--line); border-radius:8px; padding:16px;
                    scroll-margin-top:18px; }}
    .metric-card strong {{ display:block; color:var(--navy); font-size:24px; }}
    .source-link,.back-link {{ display:inline-block; margin-top:10px; color:#173f75;
                               font-weight:700; text-decoration:none;
                               border-bottom:1px solid #173f75; }}
    .execution-panel {{ border:1px solid #c9d7e8; border-left:5px solid var(--gold);
                        background:#f8fafc; border-radius:8px; padding:18px;
                        scroll-margin-top:18px; }}
    .execution-panel .status {{ color:#197044; font-weight:700; }}
    .technical-report {{ margin-top:30px; border-top:1px solid var(--line); padding-top:18px; }}
    .technical-report summary {{ cursor:pointer; color:var(--muted); font-weight:700; }}
    .empty {{ color:var(--muted); font-style:italic; }}
    footer {{ border-top:1px solid var(--line); padding:18px 52px 28px;
              color:var(--muted); font-size:11px; }}
    @media print {{
      body {{ background:white; }}
      .report {{ width:100%; margin:0; box-shadow:none; }}
    }}
  </style>
</head>
<body>
<article class="report" data-canonical-record="{canonical_id}" data-released-result="{released_id}">
  <header>
    <div class="eyebrow">Verifiable financial research</div>
    <h1>{title}</h1>
    <p>{symbol} · Professional released-result report</p>
  </header>
  <div class="identity">
    <div><span class="label">Run</span>{run_id}</div>
    <div><span class="label">Canonical record</span>{canonical_id}</div>
    <div><span class="label">Released result</span>{released_id}</div>
  </div>
  <main>
    <div class="identity">
      <div><span class="label">Company</span>{title}</div>
      <div><span class="label">Symbol</span>{symbol}</div>
      <div><span class="label">As-of</span>{as_of}</div>
    </div>
    {demo_sections}
    <details class="technical-report"><summary>查看完整验证记录</summary>
      {"".join(technical_sections)}
    </details>
  </main>
  <footer>{attribution}<br>
    This document presents released research data only; it is not financial advice.
  </footer>
</article>
</body>
</html>
"""
        return document.encode("utf-8")


class ProfessionalPDFRenderer:
    """Dependency-free deterministic A4 PDF presentation of one canonical DTO."""

    renderer_version = RENDERER_VERSION

    def render(self, report: CanonicalReportDTO) -> bytes:
        lines = _pdf_report_lines(report)
        pages = _paginate(lines)
        return _build_pdf(pages, report)


@dataclass(frozen=True, slots=True)
class ProfessionalReportArtifacts:
    html: ReportArtifactRecord
    pdf: ReportArtifactRecord


class ProfessionalReportPublisher:
    """Materialize HTML and PDF from the exact same DTO and nothing else."""

    def __init__(
        self,
        store: ControlledArtifactStore,
        *,
        html_renderer: ProfessionalHTMLRenderer | None = None,
        pdf_renderer: ProfessionalPDFRenderer | None = None,
    ) -> None:
        self._store = store
        self._html = html_renderer or ProfessionalHTMLRenderer()
        self._pdf = pdf_renderer or ProfessionalPDFRenderer()

    def publish(self, report: CanonicalReportDTO) -> ProfessionalReportArtifacts:
        before = _canonical_dto_bytes(report)
        semantic_hash = _sha256(before)
        stem = _safe_segment(report.research_object)
        run_segment = _safe_segment(report.run_id)
        canonical_segment = _safe_segment(report.canonical_record_id)
        base = f"reports/{run_segment}/{stem}-{canonical_segment}"

        html_bytes = self._html.render(report)
        pdf_bytes = self._pdf.render(report)
        if _canonical_dto_bytes(report) != before:
            raise RuntimeError("presentation renderer mutated CanonicalReportDTO")

        html_ref, html_path = self._store.write(f"{base}.html", html_bytes)
        pdf_ref, pdf_path = self._store.write(f"{base}.pdf", pdf_bytes)
        return ProfessionalReportArtifacts(
            html=_artifact_record(
                report,
                artifact_type="text/html",
                artifact_ref=html_ref,
                content=html_bytes,
                size_bytes=html_path.stat().st_size,
                semantic_hash=semantic_hash,
            ),
            pdf=_artifact_record(
                report,
                artifact_type="application/pdf",
                artifact_ref=pdf_ref,
                content=pdf_bytes,
                size_bytes=pdf_path.stat().st_size,
                semantic_hash=semantic_hash,
            ),
        )

    def publish_html(self, report: CanonicalReportDTO) -> ReportArtifactRecord:
        """Materialize only the release-required HTML representation."""

        before = _canonical_dto_bytes(report)
        semantic_hash = _sha256(before)
        stem = _safe_segment(report.research_object)
        run_segment = _safe_segment(report.run_id)
        canonical_segment = _safe_segment(report.canonical_record_id)
        base = f"reports/{run_segment}/{stem}-{canonical_segment}"
        html_bytes = self._html.render(report)
        if _canonical_dto_bytes(report) != before:
            raise RuntimeError("presentation renderer mutated CanonicalReportDTO")
        html_ref, html_path = self._store.write(f"{base}.html", html_bytes)
        record = _artifact_record(
            report,
            artifact_type="text/html",
            artifact_ref=html_ref,
            content=html_bytes,
            size_bytes=html_path.stat().st_size,
            semantic_hash=semantic_hash,
        )
        self._store.read_verified(record)
        return record

    def read_verified(self, record: ReportArtifactRecord) -> bytes:
        return self._store.read_verified(record)


def _artifact_record(
    report: CanonicalReportDTO,
    *,
    artifact_type: str,
    artifact_ref: str,
    content: bytes,
    size_bytes: int,
    semantic_hash: str,
) -> ReportArtifactRecord:
    content_hash = _sha256(content)
    artifact_kind = "HTML" if artifact_type == "text/html" else "PDF"
    manifest_hash = _sha256(_source_manifest_bytes(report)) if report.source_contributions else None
    return ReportArtifactRecord(
        artifact_id=f"RPT-{artifact_kind}-{content_hash.removeprefix('sha256:')[:20]}",
        run_id=report.run_id,
        artifact_type=artifact_type,
        artifact_ref=artifact_ref,
        content_hash=content_hash,
        renderer_version=RENDERER_VERSION,
        canonical_record_id=report.canonical_record_id,
        released_result_id=report.released_result_id,
        size_bytes=size_bytes,
        semantic_hash=semantic_hash,
        metric_semantics_hash=metric_semantics_hash(tuple(report.released_metrics)),
        anchor_manifest_id=(
            f"RPT-ANCHORS-{manifest_hash.removeprefix('sha256:')[:20]}"
            if manifest_hash is not None
            else None
        ),
        anchor_manifest_hash=manifest_hash,
        source_contributions=list(report.source_contributions),
    )


def _html_demo_sections(report: CanonicalReportDTO) -> str:
    if report.company_name is None and report.symbol is None and not report.source_contributions:
        return ""
    summary_html = (
        "".join(
            f'<p data-claim-id="{_html_text(c.claim_id)}">{_html_text(c.statement)}</p>'
            for c in report.material_claims
        )
        or '<p class="empty">No reviewed material claims.</p>'
    )

    source_by_calculation = {
        source.calculation_id: source
        for source in report.source_contributions
        if source.calculation_id is not None
    }
    metric_cards: list[str] = []
    for metric in report.released_metrics:
        if not any(c.metric_id == metric.metric_id for c in report.material_claims):
            continue
        source = source_by_calculation.get(metric.calculation_id)
        anchor = source.report_anchor if source is not None else f"metric-{metric.capability_id}"
        link = (
            f'<a class="source-link" href="#{_html_text(source.execution_anchor)}">查看研究来源</a>'
            if source is not None
            else ""
        )
        metric_cards.append(
            f'<article class="metric-card" id="{_html_text(anchor)}" '
            f'data-calculation-id="{_html_text(metric.calculation_id)}">'
            f'<span class="label">{_html_text(metric.name)}</span>'
            f"<strong>{_html_text(metric.display_value)} {_html_text(metric.display_unit)}</strong>"
            f"<span>{_html_text(metric.period)} · {_html_text(metric.actuality.value)}</span>{link}"
            "</article>"
        )
    metrics_html = (
        '<div class="metric-grid">' + "".join(metric_cards) + "</div>"
        if metric_cards
        else '<p class="empty">No authoritative released metrics.</p>'
    )
    source_panels = "".join(_html_source_panel(source) for source in report.source_contributions)
    return "".join(
        (
            (
                '<section id="research-summary"><h2>研究结论 / Research Summary</h2>'
                f"{summary_html}</section>"
            ),
            f'<section id="key-metrics"><h2>Key Metrics</h2>{metrics_html}</section>',
            (
                '<section id="execution-sources"><h2>Report ↔ Execution</h2>'
                f"{source_panels}</section>"
                if source_panels
                else ""
            ),
        )
    )


def _html_source_panel(source: ReportSourceContribution) -> str:
    token_usage = (
        f"{source.input_tokens if source.input_tokens is not None else 'N/A'} input / "
        f"{source.output_tokens if source.output_tokens is not None else 'N/A'} output"
    )
    details = {
        "Actor / Agent": source.actor_id,
        "Task": source.task_id,
        "Status": source.status,
        "Input": source.input_refs,
        "Observable Process": "Retained execution reference; no new analysis performed.",
        "Output": source.agent_output_id or source.calculation_id,
        "Report Contribution": "See typed material claims and exact calculation references.",
        "Provider / Model": f"{source.provider} / {source.actual_model or 'Not applicable'}",
        "Token Usage": token_usage,
        "Duration": f"{source.duration_ms} ms"
        if source.duration_ms is not None
        else "Not observed",
        "Agent Output ID": source.agent_output_id,
        "Agent Output Artifact": source.agent_output_artifact_id,
        "Execution Event ID": source.execution_event_id,
        "Calculation ID": source.calculation_id,
        "Formula ID": source.formula_id,
        "Evidence Refs": source.evidence_refs,
        "Review": (
            f"{source.review_id} / {source.review_status}"
            if source.review_id and source.review_status
            else "Not attached"
        ),
        "Proof": (
            f"{source.proof_id} / {source.proof_status}"
            if source.proof_id and source.proof_status
            else "Not attached"
        ),
    }
    return (
        f'<article class="execution-panel" id="{_html_text(source.execution_anchor)}" '
        f'data-run-id="{_html_text(source.run_id)}" '
        f'data-task-id="{_html_text(source.task_id)}" '
        f'data-agent-output-id="{_html_text(source.agent_output_id)}" '
        f'data-execution-event-id="{_html_text(source.execution_event_id)}">'
        f"<h3>{_html_text(source.report_section)} · Exact Execution Record</h3>"
        + (
            '<p class="status">CALCULATION SUCCESS · narrative unavailable</p>'
            if source.agent_output_id is None
            else '<p class="status">SUCCESS · exact same-Run identity verified</p>'
        )
        + f"{_html_value(details)}"
        f'<a class="back-link" href="#{_html_text(source.report_anchor)}">返回报告</a>'
        "</article>"
    )


def _html_section(title: str, value: Any) -> str:
    body = _html_value(value)
    return f"<section><h2>{_html_text(title)}</h2>{body}</section>"


def _html_value(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        if not value:
            return '<p class="empty">No released data.</p>'
        rows = []
        for key in sorted(value, key=str):
            rows.append(f"<dt>{_html_text(_label(key))}</dt><dd>{_html_value(value[key])}</dd>")
        return f"<dl>{''.join(rows)}</dl>"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return '<p class="empty">None recorded.</p>'
        return "<ul>" + "".join(f"<li>{_html_value(item)}</li>" for item in value) + "</ul>"
    if value is None:
        return '<span class="empty">Not recorded</span>'
    return _html_text(value).replace("\n", "<br>")


def _html_text(value: Any) -> str:
    return html.escape(_display_text(value), quote=True)


def _display_text(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value)
    return "".join(character for character in text if character in "\n\t" or ord(character) >= 32)


def _label(value: Any) -> str:
    return _display_text(value).replace("_", " ").strip().title()


@dataclass(frozen=True, slots=True)
class _PDFLine:
    kind: Literal["title", "subtitle", "section", "body", "small"]
    text: str


def _pdf_report_lines(report: CanonicalReportDTO) -> list[_PDFLine]:
    lines = [
        _PDFLine("title", report.research_object),
        _PDFLine("subtitle", "Professional released-result report"),
        _PDFLine("small", f"Run: {report.run_id}"),
        _PDFLine("small", f"Canonical: {report.canonical_record_id}"),
        _PDFLine("small", f"Released: {report.released_result_id}"),
    ]
    sections = (
        ("Released financial metrics", _reviewed_metrics(report)),
        ("Material claims", report.material_claims),
        ("Research source coverage", report.research_source_coverage),
        ("Limitations", report.limitations),
        (
            "Verification lineage",
            {
                "calculation_refs": report.calculation_refs,
                "proof_refs": report.proof_refs,
                "provenance": report.provenance,
            },
        ),
    )
    for title, value in sections:
        lines.append(_PDFLine("section", title))
        flattened = _flatten_for_pdf(value)
        lines.extend(_PDFLine("body", item) for item in flattened or ["No released data."])
    lines.append(_PDFLine("section", "Attribution and disclosure"))
    lines.append(_PDFLine("small", UPSTREAM_ATTRIBUTION))
    lines.append(
        _PDFLine(
            "small",
            "This document presents released research data only; it is not financial advice.",
        )
    )
    return lines


def _flatten_for_pdf(value: Any, prefix: str = "", depth: int = 0) -> list[str]:
    if depth > 8:
        return [f"{prefix}: [nested data omitted]" if prefix else "[nested data omitted]"]
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        lines: list[str] = []
        for key in sorted(value, key=str):
            label = _label(key)
            path = f"{prefix} / {label}" if prefix else label
            lines.extend(_flatten_for_pdf(value[key], path, depth + 1))
        return lines
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return [f"{prefix}: None recorded" if prefix else "None recorded"]
        lines = []
        for index, item in enumerate(value, start=1):
            item_prefix = f"{prefix} [{index}]" if prefix else f"Item {index}"
            lines.extend(_flatten_for_pdf(item, item_prefix, depth + 1))
        return lines
    rendered = _display_text(value) if value is not None else "Not recorded"
    return [f"{prefix}: {rendered}" if prefix else rendered]


def _paginate(lines: list[_PDFLine]) -> list[list[_PDFLine]]:
    pages: list[list[_PDFLine]] = [[]]
    remaining = 660
    widths = {"title": 46, "subtitle": 72, "section": 68, "body": 94, "small": 106}
    costs = {"title": 30, "subtitle": 22, "section": 24, "body": 13, "small": 11}
    for item in lines:
        text = _pdf_safe(item.text)
        wrapped = textwrap.wrap(
            text,
            width=widths[item.kind],
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=True,
        ) or [""]
        if item.kind == "section" and remaining < 50:
            pages.append([])
            remaining = 660
        for index, part in enumerate(wrapped):
            kind = item.kind if index == 0 else ("body" if item.kind != "small" else "small")
            cost = costs[kind]
            if remaining < cost:
                pages.append([])
                remaining = 660
            pages[-1].append(_PDFLine(kind, part))
            remaining -= cost
    return [page for page in pages if page]


def _build_pdf(pages: list[list[_PDFLine]], report: CanonicalReportDTO) -> bytes:
    objects: dict[int, bytes] = {}
    page_ids: list[int] = []
    next_id = 5
    for page_number, page in enumerate(pages, start=1):
        page_id = next_id
        stream_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        stream = _pdf_page_stream(page, page_number, len(pages), report)
        objects[stream_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {stream_id} 0 R >>"
        ).encode("ascii")

    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    objects[3] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    objects[4] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id in range(1, max(objects) + 1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _pdf_page_stream(
    lines: list[_PDFLine],
    page_number: int,
    page_count: int,
    report: CanonicalReportDTO,
) -> bytes:
    commands = [
        "q",
        "0.043 0.106 0.200 rg 0 790 595 52 re f",
        "0.824 0.655 0.290 rg 0 786 595 4 re f",
        "BT /F2 15 Tf 1 1 1 rg 42 811 Td (VERIFIABLE FINANCIAL RESEARCH) Tj ET",
        "Q",
    ]
    y = 758
    style = {
        "title": ("F2", 22, "0.043 0.106 0.200", 30),
        "subtitle": ("F1", 11, "0.390 0.440 0.530", 22),
        "section": ("F2", 13, "0.043 0.106 0.200", 24),
        "body": ("F1", 9, "0.150 0.205 0.285", 13),
        "small": ("F1", 8, "0.390 0.440 0.530", 11),
    }
    for item in lines:
        font, size, color, spacing = style[item.kind]
        if item.kind == "section":
            commands.append(f"0.824 0.655 0.290 RG 1.5 w 42 {y - 5} m 553 {y - 5} l S")
        commands.append(
            f"BT /{font} {size} Tf {color} rg 46 {y} Td ({_pdf_escape(item.text)}) Tj ET"
        )
        y -= spacing
    footer = (
        f"{report.research_object} | {report.canonical_record_id} | "
        f"Page {page_number} of {page_count}"
    )
    commands.extend(
        [
            "0.850 0.875 0.910 RG 0.5 w 42 46 m 553 46 l S",
            f"BT /F1 7 Tf 0.390 0.440 0.530 rg 46 31 Td ({_pdf_escape(footer)}) Tj ET",
        ]
    )
    return "\n".join(commands).encode("cp1252", errors="replace")


def _pdf_safe(value: str) -> str:
    return value.encode("cp1252", errors="replace").decode("cp1252")


def _pdf_escape(value: str) -> str:
    normalized = re.sub(r"\s+", " ", _display_text(value)).strip()
    return _pdf_safe(normalized).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    if not segment:
        raise ArtifactPathError("report identifier cannot form a safe artifact path")
    return segment[:96]


def _canonical_dto_bytes(report: CanonicalReportDTO) -> bytes:
    return json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _source_manifest_bytes(report: CanonicalReportDTO) -> bytes:
    return json.dumps(
        [source.model_dump(mode="json") for source in report.source_contributions],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
