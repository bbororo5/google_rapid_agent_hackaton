from __future__ import annotations

from dataclasses import dataclass

from .contracts import ExternalAccount, ExternalCampaign
from .ingestion import AccessTokenProvider, AdsConnectorProvider, PlatformAccess

_ADVERTISING_PROVIDERS = frozenset({"GOOGLE_ADS", "META_ADS"})


@dataclass(frozen=True, slots=True)
class ListAdvertisingAccounts:
    user_id: str
    connection_id: str


@dataclass(frozen=True, slots=True)
class ListAdvertisingCampaigns:
    user_id: str
    connection_id: str
    account_ref: str


class AdvertisingCatalogService:
    """Coordinates identity credentials and platform connectors for discovery."""

    def __init__(
        self,
        access_tokens: AccessTokenProvider,
        connectors: AdsConnectorProvider,
    ) -> None:
        self._access_tokens = access_tokens
        self._connectors = connectors

    def list_accounts(
        self, query: ListAdvertisingAccounts
    ) -> tuple[ExternalAccount, ...]:
        access = self._resolve_access(query.user_id, query.connection_id)
        return self._connectors.create(access.provider).list_accounts(
            access_token=access.access_token
        )

    def list_campaigns(
        self, query: ListAdvertisingCampaigns
    ) -> tuple[ExternalCampaign, ...]:
        access = self._resolve_access(query.user_id, query.connection_id)
        return self._connectors.create(access.provider).list_campaigns(
            access_token=access.access_token,
            account_ref=query.account_ref,
        )

    def _resolve_access(self, user_id: str, connection_id: str) -> PlatformAccess:
        return self._access_tokens.resolve(
            connection_id=connection_id,
            user_id=user_id,
            allowed_providers=_ADVERTISING_PROVIDERS,
        )
