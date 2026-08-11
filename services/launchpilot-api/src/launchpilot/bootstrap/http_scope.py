from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from launchpilot.bootstrap.wiring import campaign_access_service
from launchpilot.campaigns.contracts.access import CampaignScope, CampaignScopeResolver
from launchpilot.identity.auth_api import current_user
from launchpilot.identity.models import ConnectedUser
from launchpilot.shared import NotFoundError

UserDependency = Annotated[ConnectedUser, Depends(current_user)]
CampaignAccessDependency = Annotated[
    CampaignScopeResolver, Depends(campaign_access_service)
]


def authorized_campaign_scope(
    campaign_id: UUID,
    user: UserDependency,
    access: CampaignAccessDependency,
) -> CampaignScope:
    try:
        return access.authorize(user_id=UUID(user.id), campaign_id=campaign_id)
    except NotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


AuthorizedCampaignScope = Annotated[CampaignScope, Depends(authorized_campaign_scope)]
