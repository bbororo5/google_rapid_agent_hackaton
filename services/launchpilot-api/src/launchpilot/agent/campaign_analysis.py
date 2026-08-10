from __future__ import annotations

import json
from datetime import date
from typing import Any, Literal
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, ConfigDict

from launchpilot.application.retrieval import (
    CampaignMetricQuery,
    StructuredRetrievalService,
)
from launchpilot.application.text_retrieval import DocumentType, TextRetrievalService

SYSTEM_PROMPT = """You are LaunchPilot, an evidence-grounded marketing analyst.
For any claim about campaign performance, call get_campaign_performance first.
For memo, brief, or prior-analysis context, search campaign documents and then
resolve the selected original document before using it as evidence.
Never invent, interpolate, or estimate a metric that the tool did not return.
An empty metric list means that the requested period or metric is not stored.
Prefer the user's language. Distinguish the metric period from captured_at.
Cite important claims using [surface | provenance_ref | captured_at].
Mention PARTIAL completeness and missing_reasons when present.
"""


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


class CampaignAnalysisAgent:
    """Minimal Agentic RAG loop: model -> scoped retrieval tool -> model."""

    def __init__(
        self,
        *,
        model_with_tools: Runnable[Any, AIMessage],
        tools: list[BaseTool],
    ) -> None:
        self._graph = self._compile(model_with_tools, tools)

    @classmethod
    def from_model(
        cls,
        *,
        model: BaseChatModel,
        retrieval: StructuredRetrievalService,
        text_retrieval: TextRetrievalService,
        campaign_id: UUID,
        workspace_id: UUID,
    ) -> CampaignAnalysisAgent:
        tools = campaign_retrieval_tools(
            retrieval=retrieval,
            text_retrieval=text_retrieval,
            campaign_id=campaign_id,
            workspace_id=workspace_id,
        )
        return cls(model_with_tools=model.bind_tools(tools), tools=tools)

    def analyze(self, question: str) -> CampaignAnalysisResult:
        state = self._graph.invoke({"messages": [HumanMessage(content=question)]})
        messages = state["messages"]
        final = next(
            (
                message
                for message in reversed(messages)
                if isinstance(message, AIMessage) and not message.tool_calls
            ),
            None,
        )
        if final is None:
            raise RuntimeError("Agent did not produce a final answer")
        return CampaignAnalysisResult(
            answer=_message_text(final),
            evidence=_evidence_from_messages(messages),
        )

    @staticmethod
    def _compile(model_with_tools: Runnable[Any, AIMessage], tools: list[BaseTool]):
        def call_model(state: MessagesState) -> dict[str, list[AIMessage]]:
            response = model_with_tools.invoke(
                [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
            )
            return {"messages": [response]}

        graph = StateGraph(MessagesState)
        graph.add_node("agent", call_model)
        graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
        graph.add_edge(START, "agent")
        graph.add_conditional_edges(
            "agent", tools_condition, {"tools": "tools", END: END}
        )
        graph.add_edge("tools", "agent")
        return graph.compile()


def campaign_retrieval_tools(
    *,
    retrieval: StructuredRetrievalService,
    text_retrieval: TextRetrievalService,
    campaign_id: UUID,
    workspace_id: UUID,
) -> list[BaseTool]:
    @tool
    def get_campaign_performance(
        start_date: date | None = None,
        end_date: date | None = None,
        platforms: list[str] | None = None,
        metric_keys: list[str] | None = None,
    ) -> str:
        """Retrieve exact stored campaign metrics and their evidence.

        Supply both dates only when the user requests an exact metric period.
        Platform examples are GOOGLE_ADS, META_ADS, and YOUTUBE.
        Leave platforms or metric_keys empty to retrieve all available values.
        """
        result = retrieval.get_campaign_performance(
            CampaignMetricQuery(
                campaign_id=campaign_id,
                workspace_id=workspace_id,
                start_date=start_date,
                end_date=end_date,
                platforms=tuple(platforms or ()),
                metric_keys=tuple(metric_keys or ()),
            )
        )
        if result is None:
            return json.dumps({"error": "campaign not found"})
        return result.model_dump_json()

    @tool
    def search_campaign_documents(
        query: str,
        document_types: list[DocumentType] | None = None,
        top_k: int = 5,
    ) -> str:
        """BM25 keyword search over this campaign's memos, briefs, and analyses."""
        hits = text_retrieval.search(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            query=query,
            document_types=tuple(document_types or ()),
            top_k=top_k,
        )
        return json.dumps(
            [item.model_dump(mode="json") for item in hits], ensure_ascii=False
        )

    @tool
    def resolve_campaign_document(document_id: UUID) -> str:
        """Resolve a BM25 hit to its authoritative PostgreSQL source document."""
        document = text_retrieval.resolve(
            document_id=document_id,
            workspace_id=workspace_id,
            campaign_id=campaign_id,
        )
        if document is None:
            return json.dumps({"error": "document not found"})
        return document.model_dump_json()

    return [
        get_campaign_performance,
        search_campaign_documents,
        resolve_campaign_document,
    ]


def _message_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(
        block.get("text", "")
        for block in message.content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _evidence_from_messages(messages: list[Any]) -> tuple[AgentEvidenceRef, ...]:
    evidence: dict[tuple[str, str], AgentEvidenceRef] = {}
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        try:
            payload = json.loads(str(message.content))
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for metric in payload.get("metrics", []):
            item = AgentEvidenceRef(
                kind="METRIC",
                observation_id=metric["observation_id"],
                surface=metric["surface"],
                metric_key=metric["metric_key"],
                source_ref=metric["provenance_ref"],
                captured_at=metric["captured_at"],
            )
            evidence[(item.kind, item.source_ref)] = item
        if {"id", "source_ref", "content"} <= payload.keys():
            item = AgentEvidenceRef(
                kind="DOCUMENT",
                document_id=payload["id"],
                source_ref=payload["source_ref"],
                captured_at=payload["created_at"],
            )
            evidence[(item.kind, item.source_ref)] = item
    return tuple(evidence.values())
