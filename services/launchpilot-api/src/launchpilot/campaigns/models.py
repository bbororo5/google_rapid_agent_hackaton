from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from launchpilot.shared import DateRange, DomainError, utc_now


@dataclass(frozen=True, slots=True)
class CampaignResourceBinding:
    connection_id: UUID
    resource_ref: str
    label: str | None = None

    def __post_init__(self) -> None:
        if not self.resource_ref.strip():
            raise DomainError("resource_ref must not be blank")


@dataclass(frozen=True, slots=True)
class Campaign:
    id: UUID
    workspace_id: UUID
    name: str
    goal: str
    period: DateRange
    target_metrics: tuple[str, ...] = ()
    resource_bindings: tuple[CampaignResourceBinding, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.goal.strip():
            raise DomainError("campaign name and goal must not be blank")
        if any(not metric.strip() for metric in self.target_metrics):
            raise DomainError("target metric must not be blank")

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID,
        name: str,
        goal: str,
        period: DateRange,
        target_metrics: tuple[str, ...] = (),
        resource_bindings: tuple[CampaignResourceBinding, ...] = (),
    ) -> Campaign:
        return cls(
            id=uuid4(),
            workspace_id=workspace_id,
            name=name,
            goal=goal,
            period=period,
            target_metrics=target_metrics,
            resource_bindings=resource_bindings,
        )


class TurnRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True, slots=True)
class Turn:
    id: UUID
    conversation_id: UUID
    role: TurnRole
    content: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise DomainError("turn content must not be blank")


@dataclass(frozen=True, slots=True)
class Conversation:
    id: UUID
    campaign_id: UUID
    title: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise DomainError("conversation title must not be blank")

    @classmethod
    def create(cls, *, campaign_id: UUID, title: str) -> Conversation:
        return cls(id=uuid4(), campaign_id=campaign_id, title=title)
