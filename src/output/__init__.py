"""Canonical output builders and projections.

The output layer consumes frozen domain contracts.  It never reaches back into
repositories to rebuild a view, which keeps the financial and execution views
anchored to one canonical execution record.
"""

from src.output.canonical import CanonicalExecutionRecordBuilder
from src.output.projections import (
    CanonicalRecordProjections,
    ExecutionDetails,
    FinancialReviewView,
    build_canonical_record_projections,
    build_execution_details,
    build_financial_review_view,
)
from src.output.release import ReleasedResearchResultBuilder, ReleaseGateSnapshot
from src.output.report import FinancialReport, FinancialReportRenderer
from src.output.writeback import (
    ObjectWritebackItem,
    ObjectWritebackProposal,
    ObjectWritebackProposalBuilder,
    ValueType,
    WritebackTarget,
)

__all__ = [
    "CanonicalExecutionRecordBuilder",
    "CanonicalRecordProjections",
    "ExecutionDetails",
    "FinancialReport",
    "FinancialReportRenderer",
    "FinancialReviewView",
    "ObjectWritebackItem",
    "ObjectWritebackProposal",
    "ObjectWritebackProposalBuilder",
    "ReleaseGateSnapshot",
    "ReleasedResearchResultBuilder",
    "ValueType",
    "WritebackTarget",
    "build_canonical_record_projections",
    "build_execution_details",
    "build_financial_review_view",
]
