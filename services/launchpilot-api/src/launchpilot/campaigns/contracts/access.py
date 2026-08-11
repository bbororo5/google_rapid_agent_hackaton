from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CampaignScope:
    """Authorized identity and tenant boundary passed to downstream use cases."""

    user_id: UUID
    workspace_id: UUID
    campaign_id: UUID


class WorkspaceAccessReader(Protocol):
    def allows(self, *, user_id: UUID, workspace_id: UUID) -> bool: ...


class CampaignScopeResolver(Protocol):
    def authorize(self, *, user_id: UUID, campaign_id: UUID) -> CampaignScope: ...
