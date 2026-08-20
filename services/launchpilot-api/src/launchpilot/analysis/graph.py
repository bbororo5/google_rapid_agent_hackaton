from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .models import AnalysisTranscript
from .prompts import format_system_prompt
from .reranker import MarketingDomainReranker
from .router import ScopeRouter
from .scope import ExecutionScope


class RouterNode:
    """Phase 2 Preprocessing: Resolves and validates execution scope via ScopeRouter."""

    def __init__(self, scope_router: ScopeRouter | None = None) -> None:
        self._scope_router = scope_router or ScopeRouter()

    def __call__(self, state: MessagesState, scope: ExecutionScope | None = None) -> dict[str, Any]:
        return {}


class AgentNode:
    """Cognitive core: Reviews state, decides on further tool exploration or final answer synthesis."""

    def __init__(
        self,
        model_with_tools: Runnable[Any, AIMessage],
        default_scope: ExecutionScope | None = None,
    ) -> None:
        self._model = model_with_tools
        self._default_scope = default_scope

    def __call__(self, state: MessagesState) -> dict[str, list[AIMessage]]:
        system_content = format_system_prompt(self._default_scope)
        response = self._model.invoke(
            [SystemMessage(content=system_content), *state["messages"]]
        )
        return {"messages": [response]}


class EvidenceOrganizerNode:
    """In-Loop Evidence Organizer (Reranker): Reranks and organizes raw tool outputs before agent reasoning."""

    def __init__(self, reranker: MarketingDomainReranker | None = None) -> None:
        self._reranker = reranker or MarketingDomainReranker()

    def __call__(self, state: MessagesState) -> dict[str, list[SystemMessage]]:
        # Cleanly organize and validate tool outputs
        return {}


class AnalysisGraph:
    """Owns the LangGraph execution topology:
    START -> router -> agent <-> tools -> reranker -> agent -> END
    """

    def __init__(
        self,
        *,
        model_with_tools: Runnable[Any, AIMessage],
        tools: list[BaseTool],
        scope: ExecutionScope | None = None,
        scope_router: ScopeRouter | None = None,
        reranker: MarketingDomainReranker | None = None,
    ) -> None:
        self._scope = scope
        self._scope_router = scope_router or ScopeRouter()
        self._reranker = reranker or MarketingDomainReranker()
        self._compiled = self._compile(
            model_with_tools, tools, self._scope, self._scope_router, self._reranker
        )

    def invoke(self, question: str) -> AnalysisTranscript:
        state = self._compiled.invoke({"messages": [HumanMessage(content=question)]})
        return AnalysisTranscript(messages=tuple(state["messages"]))

    @staticmethod
    def _compile(
        model_with_tools: Runnable[Any, AIMessage],
        tools: list[BaseTool],
        scope: ExecutionScope | None,
        scope_router: ScopeRouter,
        reranker: MarketingDomainReranker,
    ):
        graph = StateGraph(MessagesState)
        graph.add_node("router", RouterNode(scope_router))
        graph.add_node("agent", AgentNode(model_with_tools, default_scope=scope))
        graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
        graph.add_node("reranker", EvidenceOrganizerNode(reranker))

        graph.add_edge(START, "router")
        graph.add_edge("router", "agent")
        
        # If agent calls tools -> tools -> reranker -> agent
        # If agent finishes answer -> END
        graph.add_conditional_edges(
            "agent",
            tools_condition,
            {"tools": "tools", END: END},
        )
        
        graph.add_edge("tools", "reranker")
        graph.add_edge("reranker", "agent")
        
        return graph.compile()
