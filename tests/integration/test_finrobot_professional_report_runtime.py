from __future__ import annotations

import re
from pathlib import Path

from src.adapters.finrobot.professional_reporting import (
    CanonicalReportMapper,
    ControlledArtifactStore,
    ProfessionalReportPublisher,
)
from tests.unit.adapters.test_finrobot_professional_reporting import records


def test_real_runtime_call_path_materializes_html_and_parseable_pdf(tmp_path: Path) -> None:
    released, canonical = records()

    dto = CanonicalReportMapper.map(released, canonical)
    store = ControlledArtifactStore(tmp_path / "report-artifacts")
    artifacts = ProfessionalReportPublisher(store).publish(dto)

    html_path = store.resolve(artifacts.html.artifact_ref)
    pdf_path = store.resolve(artifacts.pdf.artifact_ref)
    assert html_path.read_bytes().startswith(b"<!doctype html>")
    assert pdf_path.read_bytes().startswith(b"%PDF-1.4")
    assert artifacts.html.semantic_hash == artifacts.pdf.semantic_hash
    assert artifacts.html.content_hash != artifacts.pdf.content_hash

    _verify_pdf_xref(pdf_path.read_bytes())


def _verify_pdf_xref(content: bytes) -> None:
    start_match = re.search(rb"startxref\n(\d+)\n%%EOF\n$", content)
    assert start_match is not None
    xref_offset = int(start_match.group(1))
    assert content[xref_offset:].startswith(b"xref\n")
    xref_lines = content[xref_offset:].splitlines()
    _, object_count = xref_lines[1].split()
    count = int(object_count)
    assert count >= 7
    entries = xref_lines[3 : 3 + count - 1]
    for object_id, entry in enumerate(entries, start=1):
        offset = int(entry.split()[0])
        assert content[offset:].startswith(f"{object_id} 0 obj\n".encode())
    assert content.count(b"/Type /Page ") == (count - 5) // 2
