from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage

from launchpilot.analysis.use_case import AgentEvidenceRef


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


__all__ = ["AgentEvidenceRef", "AnalysisTranscript"]
