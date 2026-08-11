from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from launchpilot.bootstrap.wiring import control_plane
from launchpilot.domain.integrations import ExternalCampaignBinding, PlatformProvider
from launchpilot.infrastructure.control_plane import PostgresControlPlane

from .campaign_context import AuthorizedCampaignScope

router = APIRouter(prefix="/campaigns", tags=["campaign-bindings"])
ControlPlaneDependency = Annotated[PostgresControlPlane, Depends(control_plane)]


class CampaignBindingInput(BaseModel):
    connection_id: str
    external_account_ref: str
    external_campaign_ref: str
    display_name: str
    currency_code: str | None = None
    timezone: str | None = None
    attribution_setting: str | None = None

    @field_validator(
        "connection_id", "external_account_ref", "external_campaign_ref", "display_name"
    )
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("currency_code", "timezone", "attribution_setting")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
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
    def from_domain(cls, binding: ExternalCampaignBinding) -> CampaignBindingOutput:
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
    payload: CampaignBindingInput,
    scope: AuthorizedCampaignScope,
    store: ControlPlaneDependency,
) -> CampaignBindingOutput:
    binding = store.upsert_campaign_binding(
        user_id=str(scope.user_id),
        campaign_id=str(scope.campaign_id),
        **payload.model_dump(),
    )
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="platform connection not found",
        )
    return CampaignBindingOutput.from_domain(binding)


@router.get("/{campaign_id}/bindings", response_model=list[CampaignBindingOutput])
def list_external_campaign_bindings(
    scope: AuthorizedCampaignScope,
    store: ControlPlaneDependency,
) -> list[CampaignBindingOutput]:
    return [
        CampaignBindingOutput.from_domain(item)
        for item in store.list_campaign_bindings(
            user_id=str(scope.user_id), campaign_id=str(scope.campaign_id)
        )
    ]
