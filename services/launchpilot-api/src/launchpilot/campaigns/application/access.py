from __future__ import annotations

from uuid import UUID

from launchpilot.shared import NotFoundError

from ..contracts.access import CampaignScope, WorkspaceAccessReader
from ..service import CampaignService


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
