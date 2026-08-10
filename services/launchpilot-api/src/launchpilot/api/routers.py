from datetime import date, datetime
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, field_validator

from launchpilot.agent.campaign_analysis import (
    CampaignAnalysisAgent,
    CampaignAnalysisResult,
)
from launchpilot.application.ingestion import (
    AllSourcesFailedError,
    IngestionSource,
    MultiPlatformIngestionService,
)
from launchpilot.application.retrieval import StructuredRetrievalService
from launchpilot.application.services import (
    CampaignService,
    ConversationService,
    ObservationService,
)
from launchpilot.application.text_retrieval import (
    CampaignDocument,
    DocumentType,
    TextRetrievalService,
)
from launchpilot.config import Settings
from launchpilot.domain.errors import NotFoundError
from launchpilot.domain.integrations import ExternalCampaignBinding, PlatformProvider
from launchpilot.domain.models import (
    CampaignObservation,
    Completeness,
    CompletenessStatus,
    Conversation,
    DateRange,
)
from launchpilot.infrastructure.control_plane import ConnectedUser, PostgresControlPlane
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient
from launchpilot.infrastructure.youtube import YouTubeAnalyticsConnector

from .ads_connections import active_access_token, connector_for
from .auth import current_user
from .dependencies import (
    agent_model,
    campaign_service,
    control_plane,
    conversation_service,
    google_oauth_client,
    observation_service,
    settings,
    structured_retrieval_service,
    text_retrieval_service,
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
ControlPlaneDependency = Annotated[PostgresControlPlane, Depends(control_plane)]
UserDependency = Annotated[ConnectedUser, Depends(current_user)]
OAuthDependency = Annotated[GoogleOAuthClient, Depends(google_oauth_client)]
SettingsDependency = Annotated[Settings, Depends(settings)]
RetrievalDependency = Annotated[
    StructuredRetrievalService, Depends(structured_retrieval_service)
]
AgentModelDependency = Annotated[BaseChatModel, Depends(agent_model)]
TextRetrievalDependency = Annotated[
    TextRetrievalService, Depends(text_retrieval_service)
]


def not_found(error: NotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


def require_campaign_access(
    *,
    campaign_id: UUID,
    user: ConnectedUser,
    store: PostgresControlPlane,
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


class CampaignAnalysisInput(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class CampaignDocumentInput(BaseModel):
    document_type: DocumentType
    title: str
    content: str
    source_ref: str

    @field_validator("title", "content", "source_ref")
    @classmethod
    def strip_document_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("document fields must not be blank")
        return value


@router.post(
    "/{campaign_id}/documents",
    response_model=CampaignDocument,
    status_code=status.HTTP_201_CREATED,
)
def add_campaign_document(
    campaign_id: UUID,
    payload: CampaignDocumentInput,
    user: UserDependency,
    store: ControlPlaneDependency,
    campaigns: CampaignDependency,
    text_retrieval: TextRetrievalDependency,
) -> CampaignDocument:
    campaign = require_campaign_access(
        campaign_id=campaign_id, user=user, store=store, service=campaigns
    )
    return text_retrieval.add(
        CampaignDocument(
            campaign_id=campaign.id,
            workspace_id=campaign.workspace_id,
            **payload.model_dump(),
        )
    )


@router.post("/{campaign_id}/documents/reindex")
def reindex_campaign_documents(
    campaign_id: UUID,
    user: UserDependency,
    store: ControlPlaneDependency,
    campaigns: CampaignDependency,
    text_retrieval: TextRetrievalDependency,
) -> dict[str, int]:
    campaign = require_campaign_access(
        campaign_id=campaign_id, user=user, store=store, service=campaigns
    )
    count = text_retrieval.rebuild_projection(
        workspace_id=campaign.workspace_id, campaign_id=campaign.id
    )
    return {"indexed_documents": count}


@router.post("/{campaign_id}/analysis", response_model=CampaignAnalysisResult)
def analyze_campaign(
    campaign_id: UUID,
    payload: CampaignAnalysisInput,
    user: UserDependency,
    store: ControlPlaneDependency,
    campaigns: CampaignDependency,
    retrieval: RetrievalDependency,
    text_retrieval: TextRetrievalDependency,
    model: AgentModelDependency,
) -> CampaignAnalysisResult:
    campaign = require_campaign_access(
        campaign_id=campaign_id, user=user, store=store, service=campaigns
    )
    agent = CampaignAnalysisAgent.from_model(
        model=model,
        retrieval=retrieval,
        text_retrieval=text_retrieval,
        campaign_id=campaign.id,
        workspace_id=campaign.workspace_id,
    )
    try:
        return agent.analyze(payload.question)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Campaign analysis failed.",
        ) from error


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
                missing_reasons=list(item.completeness.missing_reasons),
            )
            for item in service.list_for_campaign(campaign_id)
        ]
    except NotFoundError as error:
        raise not_found(error) from error


class YouTubeObservationRequest(BaseModel):
    connection_id: str
    start: date
    end: date


class MultiPlatformObservationRequest(BaseModel):
    start: date
    end: date


class MultiPlatformObservationOutput(ObservationSummaryOutput):
    warnings: list[str]


class CampaignBindingInput(BaseModel):
    connection_id: str
    external_account_ref: str
    external_campaign_ref: str
    display_name: str
    currency_code: str | None = None
    timezone: str | None = None
    attribution_setting: str | None = None

    @field_validator(
        "connection_id",
        "external_account_ref",
        "external_campaign_ref",
        "display_name",
    )
    @classmethod
    def strip_required_binding_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("currency_code", "timezone", "attribution_setting")
    @classmethod
    def strip_optional_binding_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class CampaignBindingOutput(BaseModel):
    id: UUID
    campaign_id: UUID
    connection_id: str
    provider: PlatformProvider
    external_account_ref: str
    external_campaign_ref: str
    display_name: str
    currency_code: str | None
    timezone: str | None
    attribution_setting: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, binding: ExternalCampaignBinding) -> "CampaignBindingOutput":
        return cls(
            id=binding.id,
            campaign_id=binding.campaign_id,
            connection_id=binding.connection_id,
            provider=binding.provider,
            external_account_ref=binding.external_account_ref,
            external_campaign_ref=binding.external_campaign_ref,
            display_name=binding.display_name,
            currency_code=binding.currency_code,
            timezone=binding.timezone,
            attribution_setting=binding.attribution_setting,
            created_at=binding.created_at,
        )


@router.post(
    "/{campaign_id}/bindings",
    response_model=CampaignBindingOutput,
    status_code=status.HTTP_201_CREATED,
)
def bind_external_campaign(
    campaign_id: UUID,
    payload: CampaignBindingInput,
    user: UserDependency,
    store: ControlPlaneDependency,
    campaigns: CampaignDependency,
) -> CampaignBindingOutput:
    require_campaign_access(
        campaign_id=campaign_id, user=user, store=store, service=campaigns
    )
    binding = store.upsert_campaign_binding(
        user_id=user.id,
        campaign_id=str(campaign_id),
        connection_id=payload.connection_id,
        external_account_ref=payload.external_account_ref,
        external_campaign_ref=payload.external_campaign_ref,
        display_name=payload.display_name,
        currency_code=payload.currency_code,
        timezone=payload.timezone,
        attribution_setting=payload.attribution_setting,
    )
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="platform connection not found",
        )
    return CampaignBindingOutput.from_domain(binding)


@router.get("/{campaign_id}/bindings", response_model=list[CampaignBindingOutput])
def list_external_campaign_bindings(
    campaign_id: UUID,
    user: UserDependency,
    store: ControlPlaneDependency,
    campaigns: CampaignDependency,
) -> list[CampaignBindingOutput]:
    require_campaign_access(
        campaign_id=campaign_id, user=user, store=store, service=campaigns
    )
    return [
        CampaignBindingOutput.from_domain(item)
        for item in store.list_campaign_bindings(
            user_id=user.id, campaign_id=str(campaign_id)
        )
    ]


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
    config: SettingsDependency,
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
        missing_reasons=list(observation.completeness.missing_reasons),
    )


@router.post(
    "/{campaign_id}/observations/ads",
    response_model=MultiPlatformObservationOutput,
    status_code=status.HTTP_201_CREATED,
)
def fetch_multi_platform_ad_observation(
    campaign_id: UUID,
    payload: MultiPlatformObservationRequest,
    user: UserDependency,
    store: ControlPlaneDependency,
    oauth: OAuthDependency,
    config: Annotated[Settings, Depends(settings)],
    campaigns: CampaignDependency,
    observations: ObservationDependency,
) -> MultiPlatformObservationOutput:
    require_campaign_access(
        campaign_id=campaign_id, user=user, store=store, service=campaigns
    )
    try:
        period = DateRange(start=payload.start, end=payload.end)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    bindings = store.list_campaign_bindings(
        user_id=user.id, campaign_id=str(campaign_id)
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
            campaign_id=campaign_id,
            period=period,
            sources=tuple(sources),
            preflight_failures=tuple(preflight_failures),
        )
    except AllSourcesFailedError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": str(error), "reasons": list(error.reasons)},
        ) from error
    observation = outcome.observation
    return MultiPlatformObservationOutput(
        id=observation.id,
        campaign_id=observation.campaign_id,
        captured_at=observation.captured_at,
        period=PeriodInput(start=observation.period.start, end=observation.period.end),
        completeness=observation.completeness.status,
        platform_slice_count=len(observation.platform_slices),
        missing_reasons=list(observation.completeness.missing_reasons),
        warnings=list(outcome.warnings),
    )
