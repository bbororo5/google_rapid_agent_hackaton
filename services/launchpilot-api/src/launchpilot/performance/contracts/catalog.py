from dataclasses import dataclass
from typing import Protocol

from .platform import ExternalAccount, ExternalCampaign


@dataclass(frozen=True, slots=True)
class ListAdvertisingAccounts:
    user_id: str
    connection_id: str


@dataclass(frozen=True, slots=True)
class ListAdvertisingCampaigns:
    user_id: str
    connection_id: str
    account_ref: str


class AdvertisingCatalog(Protocol):
    def list_accounts(
        self, query: ListAdvertisingAccounts
    ) -> tuple[ExternalAccount, ...]: ...

    def list_campaigns(
        self, query: ListAdvertisingCampaigns
    ) -> tuple[ExternalCampaign, ...]: ...
