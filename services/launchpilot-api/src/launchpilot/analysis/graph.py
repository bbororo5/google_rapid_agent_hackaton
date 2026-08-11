from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .models import AnalysisTranscript
from .prompts import SYSTEM_PROMPT


class AgentNode:
    """Sends the current conversation state to the tool-bound model."""

    def __init__(self, model_with_tools: Runnable[Any, AIMessage]) -> None:
        self._model = model_with_tools

    def __call__(self, state: MessagesState) -> dict[str, list[AIMessage]]:
        response = self._model.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        )
        return {"messages": [response]}


class AnalysisGraph:
    """Owns only the LangGraph execution topology and transcript production."""

    def __init__(
        self,
        *,
        model_with_tools: Runnable[Any, AIMessage],
        tools: list[BaseTool],
    ) -> None:
        self._compiled = self._compile(model_with_tools, tools)

    def invoke(self, question: str) -> AnalysisTranscript:
        state = self._compiled.invoke({"messages": [HumanMessage(content=question)]})
        return AnalysisTranscript(messages=tuple(state["messages"]))

    @staticmethod
    def _compile(model_with_tools: Runnable[Any, AIMessage], tools: list[BaseTool]):
        graph = StateGraph(MessagesState)
        graph.add_node("agent", AgentNode(model_with_tools))
        graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
        graph.add_edge(START, "agent")
        graph.add_conditional_edges(
            "agent", tools_condition, {"tools": "tools", END: END}
        )
        graph.add_edge("tools", "agent")
        return graph.compile()
