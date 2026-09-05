"""Durable Phase 4 product backend surface.

Root application registration is intentionally left to the Phase 4 Parent because
the shared API/bootstrap files are classified PARENT_ONLY.
"""

from src.phase4_product.contracts import (
    LOCAL_ACCESS_SCOPE,
    PHASE4_CONTRACT_VERSION,
    PHASE4_EVENT_CONTRACT_VERSION,
    AtomicRunProjectionV1,
    AvailabilityV1,
    ConfirmRunResponseV1,
    ErrorEnvelopeV1,
    FinancialReviewProjectionV1,
    ReportArtifactGroupV1,
    ResearchRunDraftV1,
    TraceBundleV1,
)
from src.phase4_product.errors import ProductError
from src.phase4_product.projections import ReleaseCandidateSourceV1

__all__ = [
    "LOCAL_ACCESS_SCOPE",
    "PHASE4_CONTRACT_VERSION",
    "PHASE4_EVENT_CONTRACT_VERSION",
    "AtomicRunProjectionV1",
    "AvailabilityV1",
    "ConfirmRunResponseV1",
    "ErrorEnvelopeV1",
    "FinancialReviewProjectionV1",
    "ProductError",
    "ReleaseCandidateSourceV1",
    "ReportArtifactGroupV1",
    "ResearchRunDraftV1",
    "TraceBundleV1",
]
