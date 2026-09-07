import { useEffect } from "react";
import type {
  FinancialReviewSurfaceV1,
  ReleasedFinancialMetricProjectionV1,
  ReleasedResultProjectionV1,
  ReportArtifactGroupV1,
  ReportContributionRefV1,
  ReportSurfaceV1,
  ReviewCheckSelectorV1
} from "../../types/domain";
import {
  REVENUE_GROWTH_ANCHOR,
  claimForMetric,
  contributionForMetric,
  exactReviewCheck,
  metricByName
} from "./reportModel";

interface InteractiveResearchReportProps {
  readonly report: ReportSurfaceV1;
  readonly result: ReleasedResultProjectionV1;
  readonly artifacts: ReportArtifactGroupV1;
  readonly review: FinancialReviewSurfaceV1;
  readonly backendOrigin: string;
  readonly requestedAnchor: string | null;
  readonly onOpenExecution: (contribution: ReportContributionRefV1) => void;
  readonly onOpenReview: (selector: ReviewCheckSelectorV1, anchor: string) => void;
}

const metricNames = {
  revenue: "Revenue Growth",
  ebitda: "EBITDA Margin",
  fcf: "Free Cash Flow Margin",
  sma50: "50-Day Simple Moving Average",
  sma200: "200-Day Simple Moving Average",
  rsi: "RSI 14 (Simple Average, not Wilder)",
  macdLine: "MACD Line 12/26 EMA",
  macdSignal: "MACD Signal 9 EMA",
  macdHistogram: "MACD Histogram",
  volume: "Volume Ratio 20"
} as const;

function shown(metric: ReleasedFinancialMetricProjectionV1 | null): string {
  return metric === null ? "—" : `${metric.displayValue}${metric.displayUnit === "%" ? "%" : ` ${metric.displayUnit}`}`;
}

function metricCell(metric: ReleasedFinancialMetricProjectionV1 | null) {
  if (metric === null) return <span>—</span>;
  return <><strong>{shown(metric)}</strong><small>{metric.period} · {metric.actuality}</small></>;
}

export function InteractiveResearchReport({
  report, result, artifacts, review, backendOrigin, requestedAnchor, onOpenExecution, onOpenReview
}: InteractiveResearchReportProps) {
  const revenue = metricByName(result, metricNames.revenue);
  const ebitda = metricByName(result, metricNames.ebitda);
  const fcf = metricByName(result, metricNames.fcf);
  const technical = [metricNames.sma50, metricNames.sma200, metricNames.rsi, metricNames.macdLine,
    metricNames.macdSignal, metricNames.macdHistogram, metricNames.volume]
    .map((name) => metricByName(result, name)).filter((metric): metric is ReleasedFinancialMetricProjectionV1 => metric !== null);
  const heroContribution = revenue === null ? null : contributionForMetric(report, revenue);
  const heroClaim = revenue === null ? null : claimForMetric(result, revenue.metricId);
  const heroReview = revenue === null ? null : exactReviewCheck(review, revenue);
  const html = artifacts.representations.find((item) => item.format === "HTML") ?? null;
  const pdf = artifacts.representations.find((item) => item.format === "PDF") ?? null;
  const anchorIsAuthoritative = requestedAnchor !== null && report.anchors.some((item) => item.anchor === requestedAnchor);

  useEffect(() => {
    if (!anchorIsAuthoritative || requestedAnchor === null) return;
    const timer = window.setTimeout(() => document.getElementById(requestedAnchor)?.scrollIntoView({ block: "center" }), 20);
    return () => window.clearTimeout(timer);
  }, [anchorIsAuthoritative, requestedAnchor]);

  const openExecution = () => heroContribution !== null && onOpenExecution(heroContribution);
  const releasedDate = result.releasedAt.slice(0, 10);

  return <article className="report-paper" data-testid="interactive-research-report" data-report-id={report.reportId}>
    <header className="report-document-head">
      <div className="report-kicker-row"><span className="report-eyebrow">AI EQUITY RESEARCH</span><span>Released {releasedDate} · As-of {report.asOf}</span></div>
      <h2>{report.companyName}</h2>
      <div className="report-document-meta"><span className="ticker-pill">{report.symbol}</span><span>Verifiable financial research · Exact Released Run</span></div>
      <div className="report-actions" aria-label="报告导出">
        {html?.availability.status === "AVAILABLE" && html.authorizedRef !== null
          ? <a className="btn" data-testid="export-report-html" href={`${backendOrigin}${html.authorizedRef}`} target="_blank" rel="noreferrer">导出 HTML</a>
          : <button className="btn" disabled>HTML 暂不可用</button>}
        {pdf?.availability.status === "AVAILABLE" && pdf.authorizedRef !== null
          ? <a className="btn" href={`${backendOrigin}${pdf.authorizedRef}`} target="_blank" rel="noreferrer">下载 PDF</a>
          : <button className="btn" data-testid="pdf-unavailable" disabled title={pdf?.availability.reasonCode ?? "PDF_NOT_AVAILABLE"}>下载 PDF · 暂未生成</button>}
      </div>
    </header>

    <section className="report-summary" aria-labelledby="report-summary-heading">
      <span>RELEASED RESEARCH SUMMARY</span>
      <h3 id="report-summary-heading">核心研究结论</h3>
      <p>{heroClaim?.statement ?? "当前没有可展示的已发布核心结论。"}</p>
    </section>

    <section className="report-key-metrics" aria-label="关键财务指标">
      <div className="report-metric hero-metric">{metricCell(revenue)}</div>
      <div className="report-metric">{metricCell(ebitda)}</div>
      <div className="report-metric">{metricCell(fcf)}</div>
    </section>

    <section className="report-source-map" data-testid="report-source-map">
      <div className="report-section-heading"><div><span>SOURCE MAP</span><h3>结构化输出如何进入报告</h3></div><span className="badge amber">PARTIAL · A ← C</span></div>
      <p className="report-section-lede">只呈现后端明确投影的贡献关系；不展示隐藏推理，也不补造缺失的 Specialist 来源。</p>
      <div className="report-source-flow">
        {heroContribution === null ? <div className="report-source-missing">此 Run 没有可定位的报告贡献。</div> : <>
          <button type="button" className="report-source-card" data-testid="report-source-contribution" onClick={openExecution}>
            <span>SPECIALIST</span><strong>Fundamental Analyst</strong><small>Growth / Margin / Cash Flow · 查看 C 执行记录 →</small>
          </button>
          <span className="report-source-arrow" aria-hidden="true">→</span>
          <div className="report-source-node"><strong>Released Claim</strong><small>{heroClaim?.claimId ?? "—"}</small></div>
          <span className="report-source-arrow" aria-hidden="true">→</span>
          <div className="report-source-node final"><strong>Final Report</strong><small>Review / Proof / Release Gate</small></div>
        </>}
      </div>
      <p className="report-source-note">Coverage status: {report.availability.reasonCode ?? "READY"} · {report.sourceContributions.length} authoritative contribution</p>
    </section>

    <nav className="report-toc" aria-label="报告目录">
      <span><b>01</b> Financial Analysis</span><span><b>02</b> Technical Context</span><span><b>03</b> Claims & Evidence</span><span><b>04</b> Lineage & Limitations</span>
    </nav>

    <section id={REVENUE_GROWTH_ANCHOR} className={`report-section ${anchorIsAuthoritative ? "report-focus" : ""}`} data-testid="revenue-growth-section">
      <div className="report-section-heading"><div><span>01 · FINANCIAL ANALYSIS</span><h3>Revenue, profitability & cash generation</h3></div>{heroReview !== null && <button type="button" className="report-review-link" data-testid="report-to-review" onClick={() => onOpenReview(heroReview.selector, REVENUE_GROWTH_ANCHOR)}>查看金融复核 →</button>}</div>
      <div className="report-financial-grid">
        {[revenue, ebitda, fcf].map((metric) => metric === null ? null : <button key={metric.metricId} type="button" className={`report-financial-row ${metric === revenue && heroContribution !== null ? "interactive" : ""}`} onClick={metric === revenue ? openExecution : undefined}>
          <span><strong>{metric.name}</strong><small>{metric.period} · as of {metric.asOf}</small></span><b>{shown(metric)}</b><em>{metric.proof.status}</em>
        </button>)}
      </div>
      {heroClaim !== null && <div className="report-callout"><strong>Financial interpretation</strong><p>{heroClaim.statement} EBITDA and free-cash-flow margins are shown only from the exact typed Released Result for the same Run.</p></div>}
    </section>

    <section className="report-section">
      <div className="report-section-heading"><div><span>02 · TECHNICAL CONTEXT</span><h3>Released deterministic indicators</h3></div><span className="report-asof">As-of {technical[0]?.asOf ?? report.asOf}</span></div>
      <div className="technical-metric-grid">{technical.map((metric) => <div key={metric.metricId}><span>{metric.name}</span><strong>{shown(metric)}</strong><small>{metric.technicalPriceBasis ?? metric.periodBasis}</small></div>)}</div>
      <div className="report-section-note">Technical indicators are descriptive inputs, not an investment recommendation. Corporate-action status and method limitations remain attached to each typed metric.</div>
    </section>

    <section className="report-section">
      <div className="report-section-heading"><div><span>03 · MATERIAL CLAIMS</span><h3>Claim register</h3></div><span className="report-asof">{result.claims.length} released claims</span></div>
      <div className="report-claim-list">{result.claims.map((claim) => <div key={claim.claimId}><span>{claim.statement}</span><small>{claim.period} · {claim.calculationRefs.length} calculation · {claim.evidenceRefs.length} evidence</small></div>)}</div>
    </section>

    <footer className="report-lineage">
      <div><span>04 · LINEAGE</span><h3>Release identity & boundaries</h3></div>
      <dl><div><dt>Run</dt><dd>{report.runId}</dd></div><div><dt>Result</dt><dd>{report.releasedResultId}</dd></div><div><dt>Execution</dt><dd>{report.canonicalExecutionRecordId}</dd></div><div><dt>Report artifact</dt><dd>{report.artifactId}</dd></div></dl>
      <div className="report-limitations"><strong>Limitations</strong>{result.limitations.map((item) => <p key={item}>{item}</p>)}</div>
      <p className="report-disclaimer">Research artifact for demonstration and verification. Not investment advice.</p>
    </footer>
  </article>;
}
