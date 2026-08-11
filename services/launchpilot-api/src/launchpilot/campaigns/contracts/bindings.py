from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from launchpilot.shared import DomainError, PlatformProvider, utc_now


@dataclass(frozen=True, slots=True)
class ExternalCampaignBinding:
    """Message linking one LaunchPilot campaign to one platform campaign."""

    id: UUID
    campaign_id: UUID
    connection_id: str
    provider: PlatformProvider
    external_account_ref: str
    external_campaign_ref: str
    display_name: str
    currency_code: str | None = None
    timezone: str | None = None
    attribution_setting: str | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        identity = (
            self.connection_id,
            self.external_account_ref,
            self.external_campaign_ref,
            self.display_name,
        )
        if not all(value.strip() for value in identity):
            raise DomainError("external campaign binding identity must not be blank")

    @classmethod
    def create(
        cls,
        *,
        campaign_id: UUID,
        connection_id: str,
        provider: PlatformProvider,
        external_account_ref: str,
        external_campaign_ref: str,
        display_name: str,
        currency_code: str | None = None,
        timezone: str | None = None,
        attribution_setting: str | None = None,
    ) -> ExternalCampaignBinding:
        return cls(
            id=uuid4(),
            campaign_id=campaign_id,
            connection_id=connection_id,
            provider=provider,
            external_account_ref=external_account_ref,
            external_campaign_ref=external_campaign_ref,
            display_name=display_name,
            currency_code=currency_code,
            timezone=timezone,
            attribution_setting=attribution_setting,
        )


class CampaignBindingDirectory(Protocol):
    """Collaboration boundary for storing and reading platform campaign links."""

    def upsert_campaign_binding(
        self,
        *,
        user_id: str,
        campaign_id: str,
        connection_id: str,
        external_account_ref: str,
        external_campaign_ref: str,
        display_name: str,
        currency_code: str | None = None,
        timezone: str | None = None,
        attribution_setting: str | None = None,
    ) -> ExternalCampaignBinding | None: ...

    def list_campaign_bindings(
        self, *, user_id: str, campaign_id: str
    ) -> tuple[ExternalCampaignBinding, ...]: ...
