from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from launchpilot.bootstrap.http_scope import AuthorizedCampaignScope, UserDependency
from launchpilot.bootstrap.wiring import (
    campaign_service,
    conversation_service,
    identity_store,
)
from launchpilot.campaigns.contracts.management import (
    CampaignCatalog,
    ConversationCatalog,
)
from launchpilot.campaigns.models import Conversation
from launchpilot.identity.contracts.workspaces import WorkspaceDirectory
from launchpilot.shared import NotFoundError

from .schemas import (
    CampaignCreateInput,
    CampaignOutput,
    ConversationCreateInput,
    ConversationOutput,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
CampaignDependency = Annotated[CampaignCatalog, Depends(campaign_service)]
ConversationDependency = Annotated[
    ConversationCatalog, Depends(conversation_service)
]
WorkspaceDirectoryDependency = Annotated[
    WorkspaceDirectory, Depends(identity_store)
]


@router.post("", response_model=CampaignOutput, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreateInput,
    user: UserDependency,
    workspaces: WorkspaceDirectoryDependency,
    campaigns: CampaignDependency,
) -> CampaignOutput:
    if not workspaces.has_workspace_access(
        user_id=user.id, workspace_id=str(payload.workspace_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found"
        )
    return CampaignOutput.from_domain(campaigns.create(payload.to_domain()))


@router.get("", response_model=list[CampaignOutput])
def list_campaigns(
    user: UserDependency,
    workspaces: WorkspaceDirectoryDependency,
    campaigns: CampaignDependency,
) -> list[CampaignOutput]:
    workspace_ids = {UUID(item.id) for item in workspaces.list_workspaces(user.id)}
    return [
        CampaignOutput.from_domain(campaign)
        for campaign in campaigns.list_for_workspaces(workspace_ids)
    ]


@router.get("/{campaign_id}", response_model=CampaignOutput)
def get_campaign(
    scope: AuthorizedCampaignScope,
    campaigns: CampaignDependency,
) -> CampaignOutput:
    return CampaignOutput.from_domain(campaigns.get(scope.campaign_id))


@router.post(
    "/{campaign_id}/conversations",
    response_model=ConversationOutput,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreateInput,
    scope: AuthorizedCampaignScope,
    conversations: ConversationDependency,
) -> ConversationOutput:
    try:
        conversation = Conversation.create(
            campaign_id=scope.campaign_id, title=payload.title
        )
        return ConversationOutput.from_domain(conversations.create(conversation))
    except NotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.get("/{campaign_id}/conversations", response_model=list[ConversationOutput])
def list_conversations(
    scope: AuthorizedCampaignScope,
    conversations: ConversationDependency,
) -> list[ConversationOutput]:
    try:
        return [
            ConversationOutput.from_domain(item)
            for item in conversations.list_for_campaign(scope.campaign_id)
        ]
    except NotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
