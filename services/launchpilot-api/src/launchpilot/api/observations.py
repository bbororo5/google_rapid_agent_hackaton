from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from launchpilot.application.ingestion import (
    AllSourcesFailedError,
    IngestionSource,
    MultiPlatformIngestionService,
)
from launchpilot.application.services import ObservationService
from launchpilot.config import Settings
from launchpilot.domain.errors import NotFoundError
from launchpilot.domain.models import (
    CampaignObservation,
    Completeness,
    CompletenessStatus,
    DateRange,
)
from launchpilot.infrastructure.control_plane import PostgresControlPlane
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient
from launchpilot.infrastructure.youtube import YouTubeAnalyticsConnector

from .ads_connections import active_access_token, connector_for
from .campaign_context import AuthorizedCampaignScope, UserDependency
from .dependencies import (
    control_plane,
    google_oauth_client,
    observation_service,
    settings,
)
from .schemas import ObservationSummaryOutput

router = APIRouter(prefix="/campaigns", tags=["campaign-observations"])
ObservationDependency = Annotated[ObservationService, Depends(observation_service)]
ControlPlaneDependency = Annotated[PostgresControlPlane, Depends(control_plane)]
OAuthDependency = Annotated[GoogleOAuthClient, Depends(google_oauth_client)]
SettingsDependency = Annotated[Settings, Depends(settings)]


class YouTubeObservationRequest(BaseModel):
    connection_id: str
    start: date
    end: date


class MultiPlatformObservationRequest(BaseModel):
    start: date
    end: date


class MultiPlatformObservationOutput(ObservationSummaryOutput):
    warnings: list[str]


@router.get(
    "/{campaign_id}/observations", response_model=list[ObservationSummaryOutput]
)
def list_observations(
    scope: AuthorizedCampaignScope,
    observations: ObservationDependency,
) -> list[ObservationSummaryOutput]:
    try:
        return [
            ObservationSummaryOutput.from_domain(item)
            for item in observations.list_for_campaign(scope.campaign_id)
        ]
    except NotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.post(
    "/{campaign_id}/observations/youtube",
    response_model=ObservationSummaryOutput,
    status_code=status.HTTP_201_CREATED,
)
def fetch_youtube_observation(
    payload: YouTubeObservationRequest,
    scope: AuthorizedCampaignScope,
    user: UserDependency,
    store: ControlPlaneDependency,
    oauth: OAuthDependency,
    observations: ObservationDependency,
    config: SettingsDependency,
) -> ObservationSummaryOutput:
    period = _period(payload.start, payload.end)
    stored = _youtube_connection(
        connection_id=payload.connection_id, user=user, store=store
    )
    connection, token = stored
    token = _fresh_youtube_token(
        connection=connection, token=token, user=user, store=store, oauth=oauth
    )
    try:
        mock_base_url = config.platform_mock_base_url
        fetched = YouTubeAnalyticsConnector(
            channels_url=(
                f"{mock_base_url}/youtube/v3/channels"
                if mock_base_url
                else "https://www.googleapis.com/youtube/v3/channels"
            ),
            analytics_url=(
                f"{mock_base_url}/youtube/analytics/v2/reports"
                if mock_base_url
                else "https://youtubeanalytics.googleapis.com/v2/reports"
            ),
        ).fetch_channel_metrics(
            access_token=token,
            period=period,
            fetch_run_ref=f"youtube-{uuid4()}",
        )
        observation = observations.record(
            CampaignObservation(
                id=uuid4(),
                campaign_id=scope.campaign_id,
                period=period,
                platform_slices=(fetched.platform_slice,),
                completeness=Completeness(status=CompletenessStatus.COMPLETE),
            )
        )
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"YouTube fetch failed: {error}",
        ) from error
    return ObservationSummaryOutput.from_domain(observation)


@router.post(
    "/{campaign_id}/observations/ads",
    response_model=MultiPlatformObservationOutput,
    status_code=status.HTTP_201_CREATED,
)
def fetch_multi_platform_ad_observation(
    payload: MultiPlatformObservationRequest,
    scope: AuthorizedCampaignScope,
    user: UserDependency,
    store: ControlPlaneDependency,
    oauth: OAuthDependency,
    config: SettingsDependency,
    observations: ObservationDependency,
) -> MultiPlatformObservationOutput:
    period = _period(payload.start, payload.end)
    bindings = store.list_campaign_bindings(
        user_id=user.id, campaign_id=str(scope.campaign_id)
    )
    if not bindings:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign has no bound advertising campaigns.",
        )
    sources: list[IngestionSource] = []
    preflight_failures: list[str] = []
    for binding in bindings:
        try:
            provider, token = active_access_token(
                connection_id=binding.connection_id,
                user=user,
                store=store,
                google_oauth=oauth,
            )
            sources.append(
                IngestionSource(
                    binding=binding,
                    connector=connector_for(provider, config),
                    access_token=token,
                )
            )
        except (HTTPException, RuntimeError) as error:
            detail = error.detail if isinstance(error, HTTPException) else str(error)
            preflight_failures.append(f"{binding.provider.value}: {detail}")
    try:
        outcome = MultiPlatformIngestionService(observations).collect(
            campaign_id=scope.campaign_id,
            period=period,
            sources=tuple(sources),
            preflight_failures=tuple(preflight_failures),
        )
    except AllSourcesFailedError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": str(error), "reasons": list(error.reasons)},
        ) from error
    return MultiPlatformObservationOutput(
        **ObservationSummaryOutput.from_domain(outcome.observation).model_dump(),
        warnings=list(outcome.warnings),
    )


def _period(start: date, end: date) -> DateRange:
    try:
        return DateRange(start=start, end=end)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


def _youtube_connection(*, connection_id, user, store):
    try:
        stored = store.get_connection_token(
            connection_id=connection_id, user_id=user.id
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
    connection, _ = stored
    if connection.provider != "YOUTUBE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Connection cannot provide YouTube read access.",
        )
    return stored


def _fresh_youtube_token(*, connection, token, user, store, oauth) -> str:
    if oauth.access_token_expired(token):
        refresh_token = token.get("refresh_token")
        if not isinstance(refresh_token, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="YouTube authorization expired. Reconnect the account.",
            )
        try:
            refreshed = oauth.refresh_access_token(refresh_token)
            store.upsert_connection(
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
    access_token = token.get("access_token")
    if not isinstance(access_token, str):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Connection cannot provide YouTube read access.",
        )
    return access_token
