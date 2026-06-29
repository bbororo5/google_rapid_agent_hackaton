"""Shared objects for the declarative turn workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.runtime.state_cache import StateCache
from app.runtime.repository import (
    AgentRuntimeRepository,
    CampaignContext,
    ThreadMessage,
)
from app.runtime.state import (
    DelegationDecision,
    ChangeDecision,
    ScopeContext,
    ProposedChange,
)
from app.runtime.thread_store import ThreadRecord
from app.telemetry import AgentTraceContext


class CancelledTurn(Exception):
    """Raised internally when a cancel is observed between workflow stages."""


@dataclass(slots=True)
class TurnContext:
    record: ThreadRecord
    content: str
    attachments: tuple
    repository: AgentRuntimeRepository
    state_cache: StateCache
    scope: ScopeContext | None = None
    campaign_context: CampaignContext | None = None
    recent_messages: list[ThreadMessage] = field(default_factory=list)
    expected_revision: int = 0
    state_hint: str = "need_campaign"
    trace_context: AgentTraceContext | None = None

    @property
    def has_scope(self) -> bool:
        return self.scope is not None

    @property
    def trace_metadata(self) -> dict[str, Any]:
        metadata = {
            "thread_id": self.record.thread_id,
            "workspace_id": self.record.workspace_id,
            "campaign_id": self.record.campaign_id,
            "stage": "TURN",
        }
        if self.trace_context is not None:
            metadata.update(self.trace_context.metadata(
                thread_id=self.record.thread_id,
                workspace_id=self.record.workspace_id,
                campaign_id=self.record.campaign_id,
            ))
        return metadata


@dataclass(slots=True)
class TurnDecision:
    delta: ProposedChange
    reducer: ChangeDecision
    delegation: DelegationDecision

    @property
    def trace_metadata(self) -> dict[str, Any]:
        return {
            "agent.state.revision_before": self.reducer.revision_before,
            "agent.state.revision_after": self.reducer.revision_after,
            "agent.delta.intent": self.delta.intent.value,
            "agent.delta.response_mode": self.delta.response_mode.value,
            "agent.reducer.decision": self.reducer.decision.value,
            "agent.delegation.mode": self.delegation.mode.value,
            "phase": self.reducer.state.current_phase.value,
        }


@dataclass(slots=True)
class TurnOutcome:
    trace_output: dict[str, Any]
    commit_state: bool = True
