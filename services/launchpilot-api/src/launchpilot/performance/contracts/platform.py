from __future__ import annotations

from dataclasses import dataclass

from launchpilot.shared import DateRange, DomainError, PlatformProvider

from ..models import PlatformSlice


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
