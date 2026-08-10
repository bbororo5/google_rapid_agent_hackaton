from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from launchpilot.application.analysis import AnalysisScope, CampaignAccessService
from launchpilot.domain.errors import NotFoundError
from launchpilot.infrastructure.control_plane import ConnectedUser

from .auth import current_user
from .dependencies import campaign_access_service

UserDependency = Annotated[ConnectedUser, Depends(current_user)]
CampaignAccessDependency = Annotated[
    CampaignAccessService, Depends(campaign_access_service)
]


def authorized_campaign_scope(
    campaign_id: UUID,
    user: UserDependency,
    access: CampaignAccessDependency,
) -> AnalysisScope:
    try:
        return access.authorize(user_id=UUID(user.id), campaign_id=campaign_id)
    except NotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


AuthorizedCampaignScope = Annotated[AnalysisScope, Depends(authorized_campaign_scope)]
