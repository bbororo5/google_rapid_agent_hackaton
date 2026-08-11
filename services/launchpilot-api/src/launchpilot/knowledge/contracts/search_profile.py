from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RetrievalMethod(StrEnum):
    BM25 = "bm25"


class RetrievalProfile(BaseModel):
    """Identifies the retrieval configuration that produced a result."""

    model_config = ConfigDict(frozen=True)

    method: RetrievalMethod
    index_version: str = Field(min_length=1)
    chunker_version: str = Field(min_length=1)
    retriever_version: str = Field(min_length=1)


BM25_WHOLE_DOCUMENT_PROFILE = RetrievalProfile(
    method=RetrievalMethod.BM25,
    index_version="campaign-documents-v1",
    chunker_version="whole-document-v1",
    retriever_version="bm25-v1",
)
