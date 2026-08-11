from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from launchpilot.shared import DateRange, DomainError, utc_now

from .models import PlatformSlice


class PlatformProvider(StrEnum):
    YOUTUBE = "YOUTUBE"
    GOOGLE_ADS = "GOOGLE_ADS"
    META_ADS = "META_ADS"


@dataclass(frozen=True, slots=True)
class ExternalAccount:
    provider: PlatformProvider
    account_ref: str
    name: str
    currency_code: str | None = None
    timezone: str | None = None

    def __post_init__(self) -> None:
        if not self.account_ref.strip() or not self.name.strip():
            raise DomainError("external account identity must not be blank")


@dataclass(frozen=True, slots=True)
class ExternalCampaign:
    provider: PlatformProvider
    account_ref: str
    campaign_ref: str
    name: str
    status: str

    def __post_init__(self) -> None:
        values = (self.account_ref, self.campaign_ref, self.name, self.status)
        if not all(value.strip() for value in values):
            raise DomainError("external campaign identity must not be blank")


@dataclass(frozen=True, slots=True)
class ExternalCampaignBinding:
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


@dataclass(frozen=True, slots=True)
class CampaignMetricRequest:
    account_ref: str
    campaign_ref: str
    period: DateRange
    fetch_run_ref: str

    def __post_init__(self) -> None:
        identity = (self.account_ref, self.campaign_ref, self.fetch_run_ref)
        if not all(value.strip() for value in identity):
            raise DomainError("campaign metric request identity must not be blank")


@dataclass(frozen=True, slots=True)
class ConnectorFetchResult:
    platform_slice: PlatformSlice
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(not warning.strip() for warning in self.warnings):
            raise DomainError("connector warning must not be blank")
