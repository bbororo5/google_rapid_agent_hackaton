"""Public search messages and facade owned by the knowledge module."""

from .models import (
    CampaignDocument,
    DocumentType,
    RetrievalProfile,
    TextSearchHit,
)
from .ports import RetrievalObserver, RetrievalSearchObservation
from .service import TextRetrievalService

__all__ = [
    "CampaignDocument",
    "DocumentType",
    "RetrievalObserver",
    "RetrievalProfile",
    "RetrievalSearchObservation",
    "TextRetrievalService",
    "TextSearchHit",
]
