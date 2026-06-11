"""Turn context loading and prompt context rendering.

The loader is a declared sequence of context-loading steps. The prompt builder
is a declared sequence of sections. This keeps orchestration context assembly
object-oriented without hiding workflow order inside one procedural method.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import TurnContext
from app.runtime.repository import AgentRuntimeRepository, get_runtime_repository
from app.runtime.state import PhaseType, compact_state_summary, resolve_scope
from app.runtime.thread_store import ThreadRecord


class ContextLoadStep(Protocol):
    async def apply(self, turn: TurnContext) -> None:
        ...


class PromptSection(Protocol):
    def render(self, turn: TurnContext) -> str | None:
        ...


class StateHintPolicy:
    """Classifies the conversational state for lightweight chat steering."""

    def classify(self, record: ThreadRecord, has_scope: bool) -> str:
        has_plan = bool(
            record.state.active_artifact_id
            or record.state.phase_artifacts[PhaseType.EXPERIMENT_PLAN.value].get("experiment_plan")
        )
        if has_plan:
            return "plan_ready"
        has_signals = bool(record.state.phase_artifacts[PhaseType.DATA_ANALYSIS.value].get("signals"))
        if has_signals:
            return "analysis_done"
        if has_scope:
            return "ready_to_analyze"
        return "need_campaign"


@dataclass(slots=True)
class LoadPersistedState:
    emitter: StreamEmitter

    async def apply(self, turn: TurnContext) -> None:
        record = turn.record
        await self.emitter.progress(record, "turn.load_state", "Loading thread state", "running")
        persisted_state = await turn.repository.load_state(record.thread_id)
        if persisted_state:
            record.state = persisted_state
            if persisted_state.scope:
                record.set_context(persisted_state.scope.workspace_id, persisted_state.scope.campaign_id)
        turn.expected_revision = record.state.revision
        await self.emitter.progress(record, "turn.load_state", "Loaded thread state", "done")


@dataclass(slots=True)
class ResolveTurnScope:
    emitter: StreamEmitter

    async def apply(self, turn: TurnContext) -> None:
        record = turn.record
        await self.emitter.progress(record, "turn.resolve_scope", "Resolving campaign context", "running")
        turn.scope = resolve_scope(record.thread_id, record.workspace_id, record.campaign_id, record.state)
        if turn.scope:
            record.set_context(turn.scope.workspace_id, turn.scope.campaign_id)
            return
        await self.emitter.progress(record, "turn.resolve_scope", "Campaign context missing", "failed")


@dataclass(slots=True)
class LoadScopedRuntimeContext:
    emitter: StreamEmitter
    memory_limit: int = 12

    async def apply(self, turn: TurnContext) -> None:
        if not turn.scope:
            return

        record = turn.record
        record.state = await turn.repository.create_or_load_state(turn.scope)
        record.state.scope = turn.scope
        turn.campaign_context = await turn.repository.load_campaign_context(turn.scope)
        turn.recent_messages = await turn.repository.load_recent_messages(turn.scope, limit=self.memory_limit)
        turn.expected_revision = record.state.revision
        await self.emitter.progress(
            record,
            "turn.resolve_scope",
            "Resolved campaign context",
            "done",
            f"{turn.scope.workspace_id}/{turn.scope.campaign_id}",
        )
        await self.emitter.progress(
            record,
            "turn.load_memory",
            "Loaded recent conversation memory",
            "done",
            f"{len(turn.recent_messages)} message(s)",
        )


@dataclass(slots=True)
class ApplyStateHint:
    policy: StateHintPolicy

    async def apply(self, turn: TurnContext) -> None:
        turn.state_hint = self.policy.classify(turn.record, turn.has_scope)


@dataclass(frozen=True, slots=True)
class StateHintSection:
    def render(self, turn: TurnContext) -> str:
        return f"[state_hint]\n{turn.state_hint}"


@dataclass(frozen=True, slots=True)
class StateSummarySection:
    def render(self, turn: TurnContext) -> str:
        return f"[thread_state]\n{compact_state_summary(turn.record.state)}"


@dataclass(frozen=True, slots=True)
class CampaignSection:
    def render(self, turn: TurnContext) -> str | None:
        if not turn.campaign_context:
            return None
        name = turn.campaign_context.name or turn.campaign_context.campaign_id
        return f"[campaign]\n{name}"


@dataclass(frozen=True, slots=True)
class RecentMessagesSection:
    max_messages: int = 8
    max_chars: int = 240

    def render(self, turn: TurnContext) -> str | None:
        lines = []
        for message in turn.recent_messages[-self.max_messages :]:
            content = " ".join(message.content.split())[: self.max_chars]
            if content:
                lines.append(f"- {message.role}: {content}")
        if not lines:
            return None
        return "[recent_messages]\n" + "\n".join(lines)


@dataclass(frozen=True, slots=True)
class AttachmentsSection:
    def render(self, turn: TurnContext) -> str | None:
        kinds = self._attachment_kinds(turn.attachments)
        if not kinds:
            return None
        return "[attachments]\n" + ", ".join(kinds)

    def _attachment_kinds(self, attachments: tuple) -> list[str]:
        kinds = {
            getattr(item, "kind", None)
            or (item.get("kind") if isinstance(item, dict) else "unknown")
            for item in attachments
        }
        return sorted(kind for kind in kinds if kind)


class PromptContextBuilder:
    """Renders LLM context from a declared list of prompt sections."""

    def __init__(self, sections: tuple[PromptSection, ...] | None = None) -> None:
        self._sections = sections or (
            StateHintSection(),
            StateSummarySection(),
            CampaignSection(),
            RecentMessagesSection(),
            AttachmentsSection(),
        )

    def build_interpreter_context(self, turn: TurnContext) -> str:
        return "\n\n".join(
            rendered
            for section in self._sections
            if (rendered := section.render(turn))
        )


class TurnContextLoader:
    """Creates a TurnContext by applying declared context-loading steps."""

    def __init__(
        self,
        emitter: StreamEmitter,
        repository_provider: Callable[[], AgentRuntimeRepository] = get_runtime_repository,
        steps: tuple[ContextLoadStep, ...] | None = None,
    ) -> None:
        self._repository_provider = repository_provider
        self._steps = steps or (
            LoadPersistedState(emitter),
            ResolveTurnScope(emitter),
            LoadScopedRuntimeContext(emitter),
            ApplyStateHint(StateHintPolicy()),
        )

    async def load(self, record: ThreadRecord, content: str, attachments: tuple = ()) -> TurnContext:
        turn = TurnContext(
            record=record,
            content=content,
            attachments=attachments,
            repository=self._repository_provider(),
            expected_revision=record.state.revision,
        )
        for step in self._steps:
            await step.apply(turn)
        return turn
