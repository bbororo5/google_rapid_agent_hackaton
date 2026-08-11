from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from launchpilot.shared import NotFoundError

from .service import CampaignService


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


class CampaignAccessService:
    def __init__(
        self, campaigns: CampaignService, workspace_access: WorkspaceAccessReader
    ) -> None:
        self._campaigns = campaigns
        self._workspace_access = workspace_access

    def authorize(self, *, user_id: UUID, campaign_id: UUID) -> CampaignScope:
        campaign = self._campaigns.get(campaign_id)
        if not self._workspace_access.allows(
            user_id=user_id, workspace_id=campaign.workspace_id
        ):
            raise NotFoundError("campaign not found")
        return CampaignScope(
            user_id=user_id,
            workspace_id=campaign.workspace_id,
            campaign_id=campaign.id,
        )
