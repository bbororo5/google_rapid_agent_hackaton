from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True, slots=True)
class AnalysisScope:
    """Server-authorized boundary that is never exposed as an LLM tool argument."""

    user_id: UUID
    workspace_id: UUID
    campaign_id: UUID


@dataclass(frozen=True, slots=True)
class AnalysisTranscript:
    messages: tuple[BaseMessage, ...]

    def final_answer(self) -> str:
        final = next(
            (
                message
                for message in reversed(self.messages)
                if isinstance(message, AIMessage) and not message.tool_calls
            ),
            None,
        )
        if final is None:
            raise RuntimeError("Agent did not produce a final answer")
        if isinstance(final.content, str):
            return final.content
        return "".join(
            block.get("text", "")
            for block in final.content
            if isinstance(block, dict) and block.get("type") == "text"
        )


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
