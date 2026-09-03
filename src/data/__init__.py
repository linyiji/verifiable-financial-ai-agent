"""Evidence-gated provider ingestion.

Only :class:`EvidenceIngestionService` returns data intended for downstream consumers.
Provider snapshots remain internal to this package and must never be passed to agents or
financial capabilities.
"""

from src.data.ingestion import EvidenceIngestionResult, EvidenceIngestionService
from src.data.provider import Provider, ProviderRequest

__all__ = [
    "EvidenceIngestionResult",
    "EvidenceIngestionService",
    "Provider",
    "ProviderRequest",
]
