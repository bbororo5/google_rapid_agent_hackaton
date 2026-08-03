from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from launchpilot.application.services import CampaignService, ConversationService, ObservationService
from launchpilot.domain.errors import NotFoundError
from launchpilot.domain.models import Conversation

from .dependencies import campaign_service, conversation_service, observation_service
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


def not_found(error: NotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.post("", response_model=CampaignOutput, status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignCreateInput, service: CampaignDependency) -> CampaignOutput:
    return CampaignOutput.from_domain(service.create(payload.to_domain()))


@router.get("", response_model=list[CampaignOutput])
def list_campaigns(service: CampaignDependency) -> list[CampaignOutput]:
    return [CampaignOutput.from_domain(campaign) for campaign in service.list()]


@router.get("/{campaign_id}", response_model=CampaignOutput)
def get_campaign(campaign_id: UUID, service: CampaignDependency) -> CampaignOutput:
    try:
        return CampaignOutput.from_domain(service.get(campaign_id))
    except NotFoundError as error:
        raise not_found(error) from error


@router.post("/{campaign_id}/conversations", response_model=ConversationOutput, status_code=status.HTTP_201_CREATED)
def create_conversation(
    campaign_id: UUID,
    payload: ConversationCreateInput,
    service: ConversationDependency,
) -> ConversationOutput:
    try:
        conversation = Conversation.create(campaign_id=campaign_id, title=payload.title)
        return ConversationOutput.from_domain(service.create(conversation))
    except NotFoundError as error:
        raise not_found(error) from error


@router.get("/{campaign_id}/conversations", response_model=list[ConversationOutput])
def list_conversations(campaign_id: UUID, service: ConversationDependency) -> list[ConversationOutput]:
    try:
        return [ConversationOutput.from_domain(item) for item in service.list_for_campaign(campaign_id)]
    except NotFoundError as error:
        raise not_found(error) from error


@router.get("/{campaign_id}/observations", response_model=list[ObservationSummaryOutput])
def list_observations(campaign_id: UUID, service: ObservationDependency) -> list[ObservationSummaryOutput]:
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

