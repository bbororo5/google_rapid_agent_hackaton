from datetime import date
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from launchpilot.application.services import (
    CampaignService,
    ConversationService,
    ObservationService,
)
from launchpilot.domain.errors import NotFoundError
from launchpilot.domain.models import (
    CampaignObservation,
    Completeness,
    CompletenessStatus,
    Conversation,
    DateRange,
)
from launchpilot.infrastructure.control_plane import ConnectedUser, SqliteControlPlane
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient
from launchpilot.infrastructure.youtube import YouTubeAnalyticsConnector

from .auth import current_user
from .dependencies import (
    campaign_service,
    control_plane,
    conversation_service,
    google_oauth_client,
    observation_service,
)
from .schemas import (
    CampaignCreateInput,
    CampaignOutput,
    ConversationCreateInput,
    ConversationOutput,
    ObservationSummaryOutput,
    PeriodInput,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
CampaignDependency = Annotated[CampaignService, Depends(campaign_service)]
ConversationDependency = Annotated[ConversationService, Depends(conversation_service)]
ObservationDependency = Annotated[ObservationService, Depends(observation_service)]
ControlPlaneDependency = Annotated[SqliteControlPlane, Depends(control_plane)]
UserDependency = Annotated[ConnectedUser, Depends(current_user)]
OAuthDependency = Annotated[GoogleOAuthClient, Depends(google_oauth_client)]


def not_found(error: NotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


def require_campaign_access(
    *,
    campaign_id: UUID,
    user: ConnectedUser,
    store: SqliteControlPlane,
    service: CampaignService,
):
    """Return only campaigns visible to the caller; hide cross-workspace existence."""
    try:
        campaign = service.get(campaign_id)
    except NotFoundError as error:
        raise not_found(error) from error
    if not store.has_workspace_access(
        user_id=user.id, workspace_id=str(campaign.workspace_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="campaign not found"
        )
    return campaign


@router.post("", response_model=CampaignOutput, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreateInput,
    user: UserDependency,
    store: ControlPlaneDependency,
    service: CampaignDependency,
) -> CampaignOutput:
    if not store.has_workspace_access(
        user_id=user.id, workspace_id=str(payload.workspace_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found"
        )
    return CampaignOutput.from_domain(service.create(payload.to_domain()))


@router.get("", response_model=list[CampaignOutput])
def list_campaigns(
    user: UserDependency,
    store: ControlPlaneDependency,
    service: CampaignDependency,
) -> list[CampaignOutput]:
    workspace_ids = {UUID(item.id) for item in store.list_workspaces(user.id)}
    return [
        CampaignOutput.from_domain(campaign)
        for campaign in service.list_for_workspaces(workspace_ids)
    ]


@router.get("/{campaign_id}", response_model=CampaignOutput)
def get_campaign(
    campaign_id: UUID,
    user: UserDependency,
    store: ControlPlaneDependency,
    service: CampaignDependency,
) -> CampaignOutput:
    return CampaignOutput.from_domain(
        require_campaign_access(
            campaign_id=campaign_id, user=user, store=store, service=service
        )
    )


@router.post(
    "/{campaign_id}/conversations",
    response_model=ConversationOutput,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    campaign_id: UUID,
    payload: ConversationCreateInput,
    user: UserDependency,
    store: ControlPlaneDependency,
    campaigns: CampaignDependency,
    service: ConversationDependency,
) -> ConversationOutput:
    require_campaign_access(
        campaign_id=campaign_id, user=user, store=store, service=campaigns
    )
    try:
        conversation = Conversation.create(campaign_id=campaign_id, title=payload.title)
        return ConversationOutput.from_domain(service.create(conversation))
    except NotFoundError as error:
        raise not_found(error) from error


@router.get("/{campaign_id}/conversations", response_model=list[ConversationOutput])
def list_conversations(
    campaign_id: UUID,
    user: UserDependency,
    store: ControlPlaneDependency,
    campaigns: CampaignDependency,
    service: ConversationDependency,
) -> list[ConversationOutput]:
    require_campaign_access(
        campaign_id=campaign_id, user=user, store=store, service=campaigns
    )
    try:
        return [
            ConversationOutput.from_domain(item)
            for item in service.list_for_campaign(campaign_id)
        ]
    except NotFoundError as error:
        raise not_found(error) from error


@router.get(
    "/{campaign_id}/observations", response_model=list[ObservationSummaryOutput]
)
def list_observations(
    campaign_id: UUID,
    user: UserDependency,
    store: ControlPlaneDependency,
    campaigns: CampaignDependency,
    service: ObservationDependency,
) -> list[ObservationSummaryOutput]:
    require_campaign_access(
        campaign_id=campaign_id, user=user, store=store, service=campaigns
    )
    try:
        return [
            ObservationSummaryOutput(
                id=item.id,
                campaign_id=item.campaign_id,
                captured_at=item.captured_at,
                period=PeriodInput(start=item.period.start, end=item.period.end),
                completeness=item.completeness.status,
                platform_slice_count=len(item.platform_slices),
            )
            for item in service.list_for_campaign(campaign_id)
        ]
    except NotFoundError as error:
        raise not_found(error) from error


class YouTubeObservationRequest(BaseModel):
    connection_id: str
    start: date
    end: date


@router.post(
    "/{campaign_id}/observations/youtube",
    response_model=ObservationSummaryOutput,
    status_code=status.HTTP_201_CREATED,
)
def fetch_youtube_observation(
    campaign_id: UUID,
    payload: YouTubeObservationRequest,
    user: UserDependency,
    store: ControlPlaneDependency,
    oauth: OAuthDependency,
    campaigns: CampaignDependency,
    service: ObservationDependency,
) -> ObservationSummaryOutput:
    require_campaign_access(
        campaign_id=campaign_id, user=user, store=store, service=campaigns
    )
    try:
        period = DateRange(start=payload.start, end=payload.end)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    try:
        stored = store.get_connection_token(
            connection_id=payload.connection_id, user_id=user.id
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="YouTube connection not found.",
        )
    connection, token = stored
    if connection.provider != "YOUTUBE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Connection cannot provide YouTube read access.",
        )
    if oauth.access_token_expired(token):
        refresh_token = token.get("refresh_token")
        if not isinstance(refresh_token, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="YouTube authorization expired. Reconnect the account.",
            )
        try:
            refreshed = oauth.refresh_access_token(refresh_token)
            connection = store.upsert_connection(
                user_id=user.id,
                provider=connection.provider,
                token=refreshed,
                granted_scopes=connection.granted_scopes,
                account_ref=connection.account_ref,
            )
            token = {**token, **refreshed}
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="YouTube authorization refresh failed.",
            ) from error
    if not isinstance(token.get("access_token"), str):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Connection cannot provide YouTube read access.",
        )
    try:
        fetched = YouTubeAnalyticsConnector().fetch_channel_metrics(
            access_token=token["access_token"],
            period=period,
            fetch_run_ref=f"youtube-{uuid4()}",
        )
        observation = CampaignObservation(
            id=uuid4(),
            campaign_id=campaign_id,
            period=period,
            platform_slices=(fetched.platform_slice,),
            completeness=Completeness(status=CompletenessStatus.COMPLETE),
        )
        service.record(observation)
    except NotFoundError as error:
        raise not_found(error) from error
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"YouTube fetch failed: {error}",
        ) from error
    return ObservationSummaryOutput(
        id=observation.id,
        campaign_id=observation.campaign_id,
        captured_at=observation.captured_at,
        period=PeriodInput(start=observation.period.start, end=observation.period.end),
        completeness=observation.completeness.status,
        platform_slice_count=len(observation.platform_slices),
    )
