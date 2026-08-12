from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True, slots=True)
class AnalyzeCampaign:
    user_id: UUID
    campaign_id: UUID
    question: str


class AgentEvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["METRIC", "DOCUMENT"]
    source_ref: str
    captured_at: str
    observation_id: UUID | None = None
    document_id: UUID | None = None
    surface: str | None = None
    metric_key: str | None = None


class CampaignAnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: str
    evidence: tuple[AgentEvidenceRef, ...]


class CampaignAnalyzer(Protocol):
    """Campaign-analysis capability exposed to delivery components."""

    def handle(self, command: AnalyzeCampaign) -> CampaignAnalysisResult: ...
