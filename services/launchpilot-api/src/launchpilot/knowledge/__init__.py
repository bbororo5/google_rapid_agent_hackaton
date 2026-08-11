"""Campaign documents and relevance-based retrieval."""

from .models import CampaignDocument, DocumentType, TextSearchHit
from .service import TextRetrievalService

__all__ = [
    "CampaignDocument",
    "DocumentType",
    "TextRetrievalService",
    "TextSearchHit",
]
