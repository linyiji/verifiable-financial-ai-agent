# WS-W3 - FinRobot Professional HTML/PDF Controlled Port

## Outcome

The renderer activation is an owned `PORT_REQUIRED` implementation informed by
the pinned FinRobot presentation modules. It does not import or modify upstream,
does not load report-time data, and does not activate FinRobot's fixed equity
orchestrator.

## Pinned upstream attribution

- Repository: `AI4Finance-Foundation/FinRobot`
- Commit: `d221910096de87579b02f8f0674652bf1a175f51`
- License: Apache-2.0; upstream `NOTICE` identifies FinRobot and AI4Finance as
  trademarks of AI4Finance Foundation.
- Presentation references:
  - `finrobot_equity/core/src/modules/report_structure.py`
  - `finrobot_equity/core/src/modules/html_template_professional.py`
  - `finrobot_equity/core/src/modules/html_renderer.py`
  - `finrobot_equity/core/src/modules/professional_pdf_report.py`
  - `finrobot_equity/core/src/modules/pdf_generator.py`

The owned port retains the useful deep-navy/gold research-report visual system,
ordered sections, verification/source presentation, disclosure, page headers,
and page footers. It rejects upstream coupling to pandas, CDN assets, analysis
files, provider retrieval, rating logic, and valuation logic.

## Runtime call path

```text
ReleasedResearchResult + CanonicalExecutionRecord
-> CanonicalReportMapper.map
-> same frozen CanonicalReportDTO instance
-> ProfessionalReportPublisher.publish
   -> ProfessionalHTMLRenderer.render
   -> ProfessionalPDFRenderer.render
-> ControlledArtifactStore
-> ReportArtifactRecord (HTML) + ReportArtifactRecord (PDF)
```

The renderer has no FMP, network, LLM, database, peer-selection, valuation, or
rating dependency. It only presents already released values and lineage.

## Integrity model

- `content_hash` is SHA-256 over exact artifact bytes.
- `semantic_hash` is SHA-256 over canonical JSON for the immutable report DTO.
- HTML and PDF therefore share a semantic hash while retaining format-specific
  byte hashes.
- The stdlib PDF writer intentionally omits timestamps and random document IDs,
  so identical DTO input also produces byte-identical PDFs.
- Artifact paths are relative to an explicit root; traversal and symlink paths
  are rejected, and writes are atomic with mode `0600`.

## Contract change request

None.

## Verification

- Focused unit and real runtime artifact tests: `8 passed`.
- The generated sample PDF was reopened with `pypdf`: two initial pages were
  structurally valid and all released text was extractable.
- Poppler rendered every page to PNG. Visual review found and removed an orphan
  attribution page; the final one-page sample has readable type, aligned section
  rules, stable margins, a repeated research header, and a numbered footer.
- Full regression: `228 passed, 3 skipped` (the three existing real PostgreSQL
  tests require database settings not present in this isolated worktree).
- Ruff, compileall, secret-value scan, and `git diff --check`: PASS.
