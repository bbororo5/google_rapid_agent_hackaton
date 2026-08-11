from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from launchpilot.bootstrap.config import Settings
from launchpilot.bootstrap.http_scope import AuthorizedCampaignScope, UserDependency
from launchpilot.bootstrap.platform_http_errors import platform_access_http_error
from launchpilot.bootstrap.wiring import (
    ads_ingestion_source_planner,
    identity_store,
    observation_service,
    platform_access_tokens,
    settings,
)
from launchpilot.campaigns.public import CampaignBindingDirectory
from launchpilot.performance.adapters.youtube import YouTubeAnalyticsConnector
from launchpilot.performance.ingestion import (
    AccessTokenProvider,
    AdsIngestionSourcePlanner,
    AllSourcesFailedError,
    MultiPlatformIngestionService,
    PlatformAccessError,
)
from launchpilot.performance.models import (
    CampaignObservation,
    Completeness,
    CompletenessStatus,
)
from launchpilot.performance.observation_service import ObservationService
from launchpilot.performance.schemas import ObservationSummaryOutput
from launchpilot.shared import DateRange, NotFoundError

router = APIRouter(prefix="/campaigns", tags=["campaign-observations"])
ObservationDependency = Annotated[ObservationService, Depends(observation_service)]
CampaignBindingsDependency = Annotated[
    CampaignBindingDirectory, Depends(identity_store)
]
SettingsDependency = Annotated[Settings, Depends(settings)]
AccessTokensDependency = Annotated[AccessTokenProvider, Depends(platform_access_tokens)]
SourcePlannerDependency = Annotated[
    AdsIngestionSourcePlanner, Depends(ads_ingestion_source_planner)
]


class ObservationPeriodRequest(BaseModel):
    start: date
    end: date

    def to_domain(self) -> DateRange:
        return DateRange(start=self.start, end=self.end)


class YouTubeObservationRequest(ObservationPeriodRequest):
    connection_id: str


class MultiPlatformObservationRequest(ObservationPeriodRequest):
    pass


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
    access_tokens: AccessTokensDependency,
    observations: ObservationDependency,
    config: SettingsDependency,
) -> ObservationSummaryOutput:
    try:
        period = payload.to_domain()
        access = access_tokens.resolve(
            connection_id=payload.connection_id,
            user_id=user.id,
            allowed_providers=frozenset({"YOUTUBE"}),
        )
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
            access_token=access.access_token,
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
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except PlatformAccessError as error:
        raise platform_access_http_error(error) from error
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
    bindings: CampaignBindingsDependency,
    source_planner: SourcePlannerDependency,
    observations: ObservationDependency,
) -> MultiPlatformObservationOutput:
    try:
        period = payload.to_domain()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    campaign_bindings = bindings.list_campaign_bindings(
        user_id=user.id, campaign_id=str(scope.campaign_id)
    )
    if not campaign_bindings:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign has no bound advertising campaigns.",
        )
    plan = source_planner.plan(user_id=user.id, bindings=tuple(campaign_bindings))
    try:
        outcome = MultiPlatformIngestionService(observations).collect(
            campaign_id=scope.campaign_id,
            period=period,
            sources=plan.sources,
            preflight_failures=plan.failures,
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
