from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .models import AnalysisTranscript
from .prompts import format_system_prompt
from .router import ScopeRouter
from .scope import ExecutionScope


class RouterNode:
    """Resolves and validates execution scope (workspace, time, campaign) before agent invocation."""

    def __init__(self, scope_router: ScopeRouter | None = None) -> None:
        self._scope_router = scope_router or ScopeRouter()

    def __call__(self, state: MessagesState, scope: ExecutionScope | None = None) -> dict[str, Any]:
        # Return state intact (pass-through topology)
        return {}


class AgentNode:
    """Sends the conversation state to the tool-bound model with dynamic scoped system prompt."""

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


class AnalysisGraph:
    """Owns the LangGraph execution topology: START -> router -> agent -> (tools <-> agent) -> END."""

    def __init__(
        self,
        *,
        model_with_tools: Runnable[Any, AIMessage],
        tools: list[BaseTool],
        scope: ExecutionScope | None = None,
        scope_router: ScopeRouter | None = None,
    ) -> None:
        self._scope = scope
        self._scope_router = scope_router or ScopeRouter()
        self._compiled = self._compile(
            model_with_tools, tools, self._scope, self._scope_router
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
    ):
        graph = StateGraph(MessagesState)
        graph.add_node("router", RouterNode(scope_router))
        graph.add_node("agent", AgentNode(model_with_tools, default_scope=scope))
        graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))

        graph.add_edge(START, "router")
        graph.add_edge("router", "agent")
        graph.add_conditional_edges(
            "agent", tools_condition, {"tools": "tools", END: END}
        )
        graph.add_edge("tools", "agent")
        return graph.compile()
